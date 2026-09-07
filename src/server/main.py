"""
===========================================================================
FastAPI 服务入口 — Agent-demo HTTP API
===========================================================================
启动:
    uvicorn src.server.main:app --reload --port 8000
===========================================================================
"""

import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import api_router
from .middleware import LoggingMiddleware, AuthMiddleware, setup_cors
from .services import (
    AuthService, SessionService, ChatService, MultiAgentWorkspaceService,
)
from ..rag.retrieval import RetrievalService
from .services.multi_agent_service import MultiAgentService
from .services.runtime_config_service import RuntimeConfigService
from .services.secret_cipher import SecretCipher
from ..tools.mcp import load_mcp_config, McpAdapter
from .repositories import (
    InMemoryUserRepo, InMemoryApiKeyRepo, InMemorySessionRepo,
    InMemoryDocumentRepo, InMemoryChunkRepo, InMemoryTaskRepo,
    InMemoryRuntimeConfigRepo,
    InMemorySessionMessageRepo, InMemoryMultiAgentTurnRepo,
    InMemoryConversationSummaryRepo,
    InMemoryMultiAgentWorkspaceRepo, InMemoryMultiAgentAttachmentRepo,
    SqliteDb,
    SqliteUserRepo, SqliteApiKeyRepo, SqliteSessionRepo,
    SqliteDocumentRepo, SqliteChunkRepo, SqliteTaskRepo,
    SqliteRuntimeConfigRepo,
    SqliteSessionMessageRepo, SqliteMultiAgentTurnRepo,
    SqliteConversationSummaryRepo,
    SqliteMultiAgentWorkspaceRepo, SqliteMultiAgentAttachmentRepo,
)
from ..rag.storage import create_storage
from ..rag.parsing import (
    ParserRegistry, TextParser, MarkdownParser, MinerUParser,
    MinerUAgentParser,
    register_placeholders,
)
from ..rag.chunking import ChunkerRegistry
from ..rag.embedding import BailianEmbedding
from ..rag.milvus import MilvusClient
from ..rag.tasks import InProcessTaskQueue, TaskWorker
from ..rag.documents import DocumentService
from .exceptions import AppError
from .schemas import ErrorResponse, ErrorDetail

load_dotenv()

logger = logging.getLogger("server")


def configure_logging() -> None:
    """Configure application logs even when the process already owns handlers.

    ``logging.basicConfig`` is intentionally a no-op when an IDE, Uvicorn, or a
    test runner has installed a root handler.  Setting the application logger's
    level explicitly keeps ``server.*`` INFO records visible in those hosts.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # ── 确保 root logger level 不至于阻挡子 logger 的 INFO 日志传播 ──
    # basicConfig 在 root 已有 handler 时是 no-op，不会改写 root level，
    # 但 root level 默认 WARNING，会导致 server.* 的 INFO 日志在
    # 传播到 root 时被静默丢弃，所以这里显式降级。
    root = logging.getLogger()
    if root.level > level:
        root.setLevel(level)
    application_logger = logging.getLogger("server")
    application_logger.setLevel(level)
    application_logger.disabled = False


# ═══════════════════════════════════════════════════════════════
# Lifespan
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 初始化/清理服务"""
    # Startup
    configure_logging()

    # ── 仓库 (SQLite 持久化 / 内存回退) ──
    repo_backend = os.getenv("REPOSITORY_BACKEND", "sqlite").lower()
    sqlite_db: SqliteDb | None = None

    if repo_backend == "sqlite":
        sqlite_db = SqliteDb()
        await sqlite_db.init_schema()
        user_repo = SqliteUserRepo(sqlite_db)
        api_key_repo = SqliteApiKeyRepo(sqlite_db)
        session_repo = SqliteSessionRepo(sqlite_db)
        doc_repo = SqliteDocumentRepo(sqlite_db)
        chunk_repo = SqliteChunkRepo(sqlite_db)
        task_repo = SqliteTaskRepo(sqlite_db)
        runtime_config_repo = SqliteRuntimeConfigRepo(sqlite_db)
        session_message_repo = SqliteSessionMessageRepo(sqlite_db)
        multi_agent_turn_repo = SqliteMultiAgentTurnRepo(sqlite_db)
        conversation_summary_repo = SqliteConversationSummaryRepo(sqlite_db)
        multi_agent_workspace_repo = SqliteMultiAgentWorkspaceRepo(sqlite_db)
        multi_agent_attachment_repo = SqliteMultiAgentAttachmentRepo(sqlite_db)
        logger.info("存储后端: SQLite → %s", sqlite_db.db_path)
    else:
        user_repo = InMemoryUserRepo()
        api_key_repo = InMemoryApiKeyRepo()
        session_repo = InMemorySessionRepo()
        doc_repo = InMemoryDocumentRepo()
        chunk_repo = InMemoryChunkRepo()
        task_repo = InMemoryTaskRepo()
        runtime_config_repo = InMemoryRuntimeConfigRepo()
        session_message_repo = InMemorySessionMessageRepo()
        multi_agent_turn_repo = InMemoryMultiAgentTurnRepo()
        conversation_summary_repo = InMemoryConversationSummaryRepo()
        multi_agent_workspace_repo = InMemoryMultiAgentWorkspaceRepo()
        multi_agent_attachment_repo = InMemoryMultiAgentAttachmentRepo()
        logger.info("存储后端: 内存 (REPOSITORY_BACKEND=memory)")

    # ── Auth ──
    auth_service = AuthService(
        user_repo=user_repo,
        api_key_repo=api_key_repo,
    )

    session_service = SessionService(session_repo=session_repo)

    workspace_roots = [
        item.strip() for item in os.getenv(
            "MULTI_AGENT_WORKSPACE_ROOTS", os.getcwd(),
        ).split(os.pathsep) if item.strip()
    ]
    multi_agent_workspace_service = MultiAgentWorkspaceService(
        workspace_repo=multi_agent_workspace_repo,
        attachment_repo=multi_agent_attachment_repo,
        session_service=session_service,
        storage_dir=os.getenv(
            "MULTI_AGENT_ATTACHMENT_DIR",
            os.path.join(os.getcwd(), "storage", "multi_agent_attachments"),
        ),
        allowed_roots=workspace_roots,
        max_attachment_bytes=(
            int(os.getenv("MULTI_AGENT_ATTACHMENT_MAX_MB", "50")) * 1024 * 1024
        ),
    )

    # ── 可热切换的运行时配置 ──
    storage_sqlite_dir = os.getenv(
        "STORAGE_SQLITE_DIR", os.path.join(os.getcwd(), "data")
    )
    runtime_config_service = RuntimeConfigService(
        repository=runtime_config_repo,
        cipher=(
            SecretCipher.from_environment(storage_sqlite_dir)
            if repo_backend == "sqlite"
            else SecretCipher.ephemeral()
        ),
        mcp_adapter_factory=McpAdapter,
    )
    mcp_cfg = load_mcp_config(os.getenv("MCP_CONFIG_PATH", "./mcp.json"))
    await runtime_config_service.initialize(mcp_cfg)

    # ── Embedding (百炼) ──
    embedding = None
    if os.getenv("BAILIAN_API_KEY"):
        embedding = BailianEmbedding(
            api_key=os.getenv("BAILIAN_API_KEY", ""),
        )
        logger.info("百炼 Embedding 已配置: model=%s dim=%d",
                     embedding.model_name, embedding.dimension)

    # ── Milvus ──
    milvus = None
    if os.getenv("MILVUS_HOST"):
        vector_dim = int(os.getenv("MILVUS_VECTOR_DIM", "1024"))
        milvus = MilvusClient(
            host=os.getenv("MILVUS_HOST", "localhost"),
            port=int(os.getenv("MILVUS_PORT", "19530")),
            user=os.getenv("MILVUS_USER", ""),
            password=os.getenv("MILVUS_PASSWORD", ""),
            vector_dim=vector_dim,
        )
        milvus.connect()
        app.state.milvus_connected = True
        logger.info("Milvus 已连接: %s:%s (entities=%d)",
                     os.getenv("MILVUS_HOST", "localhost"),
                     os.getenv("MILVUS_PORT", "19530"),
                     milvus.entity_count)
    else:
        app.state.milvus_connected = False
        logger.info("Milvus 未配置 (设置 MILVUS_HOST 启用)")

    # ── 检索服务 ──
    retrieval = None
    rewrite_llm = None
    if embedding and milvus:
        retrieval = RetrievalService(embedding, milvus, doc_repo)
        logger.info("基础检索服务已启用")

        # ── Query 改写 LLM (用于高阶检索) ──
        rewrite_model = os.getenv("REWRITE_MODEL", "")
        if rewrite_model:
            try:
                from ..models import get_model
                rewrite_model_kwargs = runtime_config_service.model_config
                if rewrite_model_kwargs:
                    rewrite_llm = get_model(
                        **{**rewrite_model_kwargs, "temperature": 0.1},
                    )
                    logger.info("Query 改写 LLM 已就绪")
            except Exception as e:
                logger.warning("Query 改写 LLM 初始化失败: %s", e)

        # ── 高阶检索 (包装基础检索 + Query 改写) ──
        if rewrite_llm:
            from ..rag.retrieval import AdvancedRetrievalService
            retrieval = AdvancedRetrievalService(retrieval, rewrite_llm)
            logger.info("高阶检索服务已启用 (Query 改写 + 多路检索 + RRF 合并)")

    # ── Chat (注入检索) ──
    chat_service = ChatService(
        retrieval_service=retrieval,
        model_kwargs=runtime_config_service.model_config,
        store_type=repo_backend,
        sqlite_path=(
            os.path.join(storage_sqlite_dir, "chat_agent.db")
            if repo_backend == "sqlite"
            else None
        ),
    )

    # ── Multi-Agent (Plan-and-Solve 多智能体编排) ──
    sub_agent_registry = runtime_config_service.registry
    multi_agent_service = MultiAgentService(
        sub_agent_registry=sub_agent_registry,
        store_type=repo_backend,
        sqlite_path=os.path.join(storage_sqlite_dir, "multi_agent.db") if repo_backend == "sqlite" else None,
        model_kwargs=runtime_config_service.model_config,
        message_repo=session_message_repo,
        turn_repo=multi_agent_turn_repo,
        summary_repo=conversation_summary_repo,
        session_service=session_service,
        workspace_service=multi_agent_workspace_service,
        max_context_tokens=int(os.getenv("MULTI_AGENT_CONTEXT_MAX_TOKENS", "6000")),
        max_history_turns=int(os.getenv("MULTI_AGENT_MAX_HISTORY_TURNS", "10")),
    )
    runtime_config_service.bind_services(chat_service, multi_agent_service)
    logger.info("Multi-Agent 服务已启用 (subagents=%d)", sub_agent_registry.count)

    # ── 文档管理 ──
    storage = create_storage()

    parser_registry = ParserRegistry()
    parser_registry.register(
        TextParser(), extensions=[".txt"], mime_types=["text/plain"],
    )
    parser_registry.register(
        MarkdownParser(), extensions=[".md"], mime_types=["text/markdown"],
    )
    # ── PDF 解析: MinerU v4 (需 API Key) → 不可用时回退到 Agent 轻量 API ──
    if os.getenv("MINERU_API_KEY"):
        parser_registry.register(
            MinerUParser(
                api_url=os.getenv("MINERU_API_URL", ""),
                api_key=os.getenv("MINERU_API_KEY", ""),
                model_version=os.getenv("MINERU_MODEL_VERSION", "vlm"),
                language=os.getenv("MINERU_LANGUAGE", "ch"),
            ),
            extensions=[".pdf"], mime_types=["application/pdf"],
        )
        logger.info("PDF 解析: MinerU v4 (精准模式)")
    else:
        parser_registry.register(
            MinerUAgentParser(
                api_url=os.getenv("MINERU_AGENT_API_URL", ""),
                language=os.getenv("MINERU_LANGUAGE", "ch"),
            ),
            extensions=[".pdf"], mime_types=["application/pdf"],
        )
        logger.info("PDF 解析: MinerU Agent 轻量 API (MINERU_API_KEY 未配置, 自动回退)")

    parser_registry.register(
        MinerUAgentParser(
            api_url=os.getenv("MINERU_AGENT_API_URL", ""),
            language=os.getenv("MINERU_LANGUAGE", "ch"),
        ),
        extensions=[".png", ".jpg", ".jpeg", ".docx", ".pptx", ".xlsx"],
        mime_types=[
            "image/png", "image/jpeg",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ],
    )
    register_placeholders(parser_registry)

    chunker_registry = ChunkerRegistry()

    # ── 索引管线 (需要 embedding + milvus 同时就绪) ──
    if embedding and milvus:
        task_worker = TaskWorker(
            doc_repo=doc_repo, chunk_repo=chunk_repo,
            storage=storage, parser_registry=parser_registry,
            chunker_registry=chunker_registry,
            embedding_service=embedding,
            milvus_client=milvus,
        )
        task_queue = InProcessTaskQueue(
            worker=task_worker,
            task_repo=task_repo,
            max_concurrency=int(os.getenv("DOCUMENT_TASK_CONCURRENCY", "2")),
        )
        doc_service = DocumentService(
            doc_repo=doc_repo, chunk_repo=chunk_repo,
            storage=storage, task_queue=task_queue,
            milvus_client=milvus,
        )
        logger.info("文档索引管线已就绪 (解析→分块→Embedding→Milvus)")
    else:
        task_queue = None
        doc_service = None
        logger.warning(
            "索引管线未启用: embedding=%s, milvus=%s — 文档上传功能不可用",
            "on" if embedding else "off",
            "on" if milvus else "off",
        )

    # ── 挂载到 app.state ──
    app.state.auth_service = auth_service
    app.state.session_service = session_service
    app.state.chat_service = chat_service
    app.state.storage = storage
    app.state.parser_registry = parser_registry
    app.state.chunker_registry = chunker_registry
    app.state.task_queue = task_queue
    app.state.doc_service = doc_service
    app.state.retrieval_service = retrieval
    app.state.embedding = embedding
    app.state.milvus = milvus
    app.state.multi_agent_service = multi_agent_service
    app.state.multi_agent_workspace_service = multi_agent_workspace_service
    app.state.runtime_config_service = runtime_config_service
    app.state.mcp_tools = runtime_config_service.mcp_tools
    app.state.sqlite_db = sqlite_db

    logger.info("🚀 FastAPI 服务已启动 (auth=persistent, "
                "embedding=%s, milvus=%s, retrieval=%s)",
                "on" if embedding else "off",
                "on" if milvus else "off",
                "on" if retrieval else "off")

    if task_queue:
        await task_queue.recover()

    try:
        yield
    finally:
        # 先停止接收并等待后台任务，再关闭它们依赖的 Milvus/SQLite。
        if task_queue:
            await task_queue.close()
        if milvus:
            milvus.disconnect()
        if multi_agent_service:
            await multi_agent_service.close_all()
        if chat_service:
            await chat_service.close_all()
        await runtime_config_service.close()
        if sqlite_db:
            await sqlite_db.close()
        logger.info("🛑 FastAPI 服务已关闭")


# ═══════════════════════════════════════════════════════════════
# Application
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Agent-demo API",
    description="AI Agent 问答服务 — 认证, 会话管理, 流式问答",
    version="0.1.0",
    lifespan=lifespan,
)

# Starlette 后注册的中间件位于外层，因此按内层到外层注册。
app.add_middleware(AuthMiddleware)
app.add_middleware(LoggingMiddleware)
setup_cors(app)


# ── 异常处理 ──

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                details=exc.details,
            )
        ).model_dump(),
    )


# ── 路由 ──

app.include_router(api_router)


# ── 健康检查 ──

@app.get("/health/live")
async def health_live():
    """存活检查 — 应用进程是否运行"""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(request: Request):
    """就绪检查 — 依赖是否可用"""
    return {
        "status": "ok",
        "checks": {
            "chat_agent": "ok",
            "embedding": "ok" if request.app.state.embedding else "unconfigured",
            "milvus": "ok" if request.app.state.milvus_connected else "unconfigured",
            "retrieval": "ok" if request.app.state.retrieval_service else "unconfigured",
            "multi_agent": "ok" if request.app.state.multi_agent_service else "unconfigured",
        },
    }
