# 企业知识库智能助手设计文档

## 1. 项目目标

在现有 `m-agent/` 项目中增量实现一个基于 FastAPI 的企业知识库智能助手，用一个可运行项目串联此前阶段中的核心知识：

- 多模型接入、流式输出、重试与成本记录
- Prompt、结构化输出与上下文工程
- LCEL、Tool Calling 与 LangGraph 状态图
- 会话记忆、摘要记忆与用户隔离
- 文档加载、分块、Embedding、Milvus 检索与重排
- ReAct、条件路由、引用检查与有限反思
- MCP 工具发现和统一工具注册
- 中间件、权限、审计、限流与错误处理

首版支持 Markdown、TXT 和 PDF 文档，支持私人知识库、公共知识库及二者混合检索。系统采用多用户基础隔离，并提供将私人文档申请发布到公共知识库的管理员审批流程。

## 2. 范围

### 2.1 首版必须实现

- FastAPI HTTP API 与 SSE 流式问答
- API Key 身份认证
- `user`、`admin` 两种角色
- Markdown、TXT、PDF 上传、解析、分块和索引
- Milvus Standalone 向量存储
- SQLite 业务元数据存储
- 本地原始文件存储
- DeepSeek、OpenAI 对话模型工厂
- 本地 BGE Embedding，预留 OpenAI Embedding
- 本地 BGE Reranker，可配置关闭
- `private`、`shared`、`hybrid` 三种检索范围
- 会话历史、滑动窗口和摘要记忆
- LangGraph 问答与工具调用工作流
- 回答来源引用及引用有效性检查
- 公共知识库发布审批
- 本地工具与可选 MCP 工具适配
- 结构化日志、审计、限流、健康检查
- Docker Compose 启动 Milvus
- 无外部模型 API Key 时仍可运行的默认测试

### 2.2 只预留接口，不在首版实现

- 网页抓取
- OCR 图片识别
- DOCX、XLSX、PPTX 等 Office 文档解析
- 阿里云 OSS
- Celery、RQ 等外部任务队列
- 完整 Web 前端
- 企业 SSO、OAuth2、多租户计费

## 3. 架构原则

项目采用模块化单体架构。FastAPI 是统一入口，业务模块运行在同一个应用中，但存储、任务、文档加载、模型和工具均通过协议或抽象接口隔离。

`m-agent/` 是项目根目录。新增正式包位于 `m-agent/src/m_agent/`，测试位于 `m-agent/tests/`。现有代码按模块逐步迁移和复用，不另建 `code/阶段15-实战项目/project_01_knowledge_assistant/`。

`m-agent/agents/chat_agent.py` 是受保护的遗留文件：不得修改、移动、重命名或删除。现有 CLI 可以继续调用该 `ChatAgent`；新的 FastAPI 知识库工作流在 `src/m_agent/agents/` 下独立实现，不以修改旧类作为集成手段。

首版的异步索引任务由进程内后台任务实现。业务层只依赖 `TaskQueue` 接口，后续可替换为 Celery 或 RQ，而不修改文档服务的调用方式。

Milvus 只负责向量、分块文本和检索元数据，不作为业务状态的数据源。SQLite 是用户、文档、任务、审批、会话和审计状态的权威来源。原始文件只能通过 `ObjectStorage` 接口访问。

## 4. 模块边界

项目包含以下模块：

- `api`：FastAPI 路由、依赖注入、请求响应模型和 SSE。
- `auth`：API Key 校验、身份上下文、角色和资源权限。
- `documents`：上传、查询、删除、重新索引和发布申请。
- `ingestion`：解析、清洗、分块、Embedding 和 Milvus 写入流水线。
- `loaders`：Loader 协议、注册中心以及 TXT、Markdown、PDF 实现。
- `storage`：`ObjectStorage` 协议和本地文件系统实现。
- `tasks`：`TaskQueue` 协议和进程内任务实现。
- `retrieval`：范围过滤、候选召回、融合、去重、重排和来源组装。
- `agents`：LangGraph 状态、节点、条件边和回答流程。
- `tools`：本地工具、工具注册中心和 MCP 工具适配器。
- `sessions`：会话、消息、摘要记忆和上下文预算。
- `approvals`：公共发布申请、批准、拒绝和公共副本管理。
- `middleware`：请求追踪、日志、错误转换、限流和审计。
- `repositories`：SQLite 和 Milvus 访问适配层。

所有业务模块使用明确的服务接口协作，API 路由不得直接操作 SQLite 或 Milvus 客户端。

### 4.1 现有 `m-agent` 迁移边界

以下现有能力迁入 `src/m_agent/` 后继续使用：

- `models/llm.py`：保留多 Provider 模型工厂思路，修正 Provider 映射并改为配置注入。
- `config/settings.py`：迁移为 Pydantic Settings，取消全局可变单例。
- `utils/retry.py`：保留 Tenacity 同步和异步重试策略。
- `utils/logger.py`：迁移为支持 `request_id` 的结构化日志。
- `callbacks/token_counter.py`：保留 Token 提取能力，并将结果接入运行指标。
- `tools/registry.py`：扩展角色、超时、来源和 MCP 命名空间。
- `tools/base.py`：保留时间工具；计算器替换为 AST 白名单实现；模拟翻译不进入默认生产工具集。

迁移采用测试护栏：先为现有行为补充特征测试，再创建新包实现，最后切换新调用方。旧模块只有在没有调用方且用户另行批准时才可删除。

`m-agent/agents/chat_agent.py` 不参与迁移。新知识库 Agent 使用单独的状态、节点、图构建器、运行时和流式适配器，避免产生对旧文件的任何修改。

## 5. 文档生命周期

### 5.1 状态

文档索引状态按以下顺序变化：

`uploaded → queued → parsing → chunking → embedding → indexed`

发生异常时进入 `failed`。删除过程为：

`deleting → deleted`

每次状态变化必须写入 SQLite，并保留最新的安全错误描述。详细异常堆栈只写入服务日志。

### 5.2 上传和索引

1. API 验证身份、文件 MIME 类型、大小和目标知识库范围。
2. 普通用户只能上传 `private` 文档；管理员可上传 `private` 或 `shared` 文档。
3. 原始文件通过 `ObjectStorage` 保存。
4. SQLite 创建 `Document` 和 `IngestionTask`。
5. 文档服务通过 `TaskQueue` 提交索引任务。
6. Loader 注册中心根据 MIME 类型选择解析器。
7. 文本依次经过清洗、分块和元数据补全。
8. Embedding 服务批量生成向量并写入 Milvus。
9. 全部写入成功后，SQLite 将文档更新为 `indexed`。

系统使用 `owner_id + scope + file_hash` 检测重复上传。任务使用幂等键，重试时不得创建重复 Chunk。

重新索引必须生成新文档版本。新版本完整写入并验证成功后才切换为有效版本，随后清理旧版本向量。

### 5.3 删除

删除操作先将 SQLite 状态改为 `deleting`，再异步删除 Milvus 向量和原始文件。全部完成后改为 `deleted`。重复删除必须安全返回同一结果。

## 6. 可扩展加载与存储

### 6.1 Loader

所有加载器实现统一协议，输入为存储对象描述，输出为标准化文档页列表。注册中心使用 MIME 类型和文件扩展名选择加载器。

首版实现：

- `TextLoader`
- `MarkdownLoader`
- `PdfLoader`

下列扩展只注册能力描述，不提供实现：

- `WebLoader`
- `OcrImageLoader`
- `DocxLoader`
- `SpreadsheetLoader`
- `PresentationLoader`

未安装的加载能力必须返回明确的 `LOADER_NOT_AVAILABLE` 错误，而不是退回错误的文本解析。

### 6.2 ObjectStorage

`ObjectStorage` 至少提供保存、读取、删除和存在性检查。首版 `LocalStorage` 使用随机存储键，不直接使用用户提供的文件名作为磁盘路径。

预留 `AliyunOSSStorage` 实现位置，但首版不依赖阿里云 SDK。业务模块不得根据存储类型拼接本地路径或 OSS URL。

## 7. 任务队列

`TaskQueue` 负责提交文档索引、重新索引、删除和公共副本创建任务。接口返回稳定的 `task_id`。

首版 `InProcessTaskQueue` 使用 FastAPI 进程内后台执行机制。任务状态仍保存在 SQLite，因此 API 重启后能够识别未完成任务并将其标记为可重试，而不是错误地显示完成。

后续 Celery 或 RQ 实现必须遵循相同任务输入、幂等键和状态回调契约。

## 8. 检索设计

### 8.1 范围

- `private`：强制过滤 `scope=private AND user_id=当前认证用户`。
- `shared`：强制过滤 `scope=shared`。
- `hybrid`：分别检索私人和公共范围，再合并候选。

客户端不得指定实际检索使用的 `user_id`。私人过滤条件只能由认证上下文生成。

### 8.2 Hybrid 流程

1. 私人知识库召回 Top 8。
2. 公共知识库召回 Top 8。
3. 按 `document_id + chunk_hash` 去重。
4. 启用 Reranker 时，使用 BGE Reranker 统一评分。
5. 选取最终 Top 6 作为模型上下文。

关闭 Reranker 时，系统对两个检索结果做归一化分数融合，并保证私人和公共结果都不会因为分数尺度不同而被系统性排除。

### 8.3 引用

每个返回给模型的片段具有稳定的引用编号。最终响应中的引用包括：

- 文档显示名称
- `private` 或 `shared` 范围
- 页码或 Markdown 章节
- 片段编号

API 不返回本地文件路径、对象存储内部键、Milvus 主键或其他用户标识。

## 9. Agent 工作流

LangGraph 使用显式状态图。状态至少包含：

- `user_id`
- `session_id`
- `query`
- `knowledge_scope`
- `intent`
- `messages`
- `conversation_summary`
- `retrieved_chunks`
- `tool_calls`
- `tool_results`
- `answer`
- `citations`
- `iteration_count`
- `errors`

节点流程：

1. 加载身份、会话与上下文。
2. 识别普通对话、知识库问答、文档管理帮助或工具任务。
3. 知识问答结合历史消息改写查询。
4. 按请求范围检索并重排。
5. 工具任务从本地与 MCP 工具中选择允许的工具。
6. 基于检索证据或工具结果生成回答。
7. 验证引用编号与证据是否真实存在。
8. 保存消息、引用、Token 数据和审计记录。

引用检查失败时最多允许一次回答修正。工具调用也有固定最大次数，状态图不得存在无限循环。

知识库没有足够证据时，Agent 必须明确说明无法根据当前范围确认，并建议用户切换范围、上传资料或改写问题。

## 10. 工具与 MCP

首版本地工具包括：

- 知识库检索
- 文档详情
- 当前用户文档列表
- 当前时间

所有工具通过统一注册中心管理，包含名称、描述、参数 Schema、权限、超时和标签。

MCP 适配器通过配置连接外部 MCP Server，动态发现工具并转换为内部工具描述。工具名必须使用服务器命名空间，例如 `knowledge/search`。MCP 默认关闭，连接失败不得阻断普通对话和知识库问答。

工具执行必须经过白名单、Pydantic 参数校验、超时和最大调用次数控制。

## 11. 记忆与上下文工程

记忆分为：

- 最近消息窗口
- 会话摘要
- 外部知识库检索结果

聊天消息不会自动写入 Milvus，避免未经验证的对话内容污染长期知识。

记忆与上下文管理必须优先使用 LangChain/LangGraph 官方组件实现，不自行开发一套平行的 Memory 框架：

- 使用 LangGraph Checkpointer 按 `thread_id` 持久化会话图状态和消息。
- 使用 LangChain/LangGraph 提供的消息裁剪、Token 计数与摘要能力控制上下文窗口。
- 使用 LangGraph Store 接口承载需要跨会话保留的用户级记忆；首版不把普通聊天内容自动提升为长期记忆。
- SQLite 中的 `Session` 继续保存会话所有权、标题和业务统计；消息正文以 LangGraph Checkpoint 状态为准，避免双写形成两个权威来源。
- 所有官方组件都封装在项目的 `sessions` 适配层后，业务节点不直接依赖具体 Checkpointer 或 Store 实现，便于后续切换持久化后端。

上下文按以下优先级组装：

1. 系统规则和安全约束
2. 用户身份和知识库范围
3. 会话摘要
4. 最近消息
5. 检索证据或工具结果
6. 当前问题和输出格式

Token 超过预算时，依次裁剪旧消息和低分检索片段。权限规则、当前问题和必要的引用映射不可裁剪。

## 12. 公共知识库审批

普通用户可针对自己的 `indexed` 私人文档提交发布申请。管理员可以批准或拒绝。

批准时不直接改变私人文档的范围，而是创建独立的公共文档版本：

1. 创建公共副本记录。
2. 异步索引公共副本。
3. 公共版本成功进入 `indexed` 后，审批状态变为 `approved`。
4. 索引失败时审批进入 `publish_failed`，管理员可以重试。

原私人文档继续由原用户拥有。公共副本可由管理员单独撤回，不影响私人文档。申请、审核、发布、失败、重试和撤回均写入审计日志。

## 13. API

所有业务接口使用 `/api/v1` 前缀。

### 13.1 身份

- `POST /api/v1/users`
- `POST /api/v1/api-keys`
- `GET /api/v1/me`

### 13.2 文档

- `POST /api/v1/documents`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `DELETE /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/reindex`
- `GET /api/v1/tasks/{task_id}`

### 13.3 公共发布

- `POST /api/v1/documents/{document_id}/publication-requests`
- `GET /api/v1/publication-requests`
- `POST /api/v1/publication-requests/{request_id}/approve`
- `POST /api/v1/publication-requests/{request_id}/reject`

### 13.4 会话与问答

- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}/messages`
- `DELETE /api/v1/sessions/{session_id}`
- `POST /api/v1/chat`
- `POST /api/v1/chat/stream`

问答请求显式包含 `knowledge_scope`，允许值为 `private`、`shared`、`hybrid`，默认值为 `hybrid`。

SSE 事件类型至少包含：

- `start`
- `status`
- `token`
- `citation`
- `tool_call`
- `error`
- `done`

### 13.5 运维

- `GET /health/live`
- `GET /health/ready`
- `GET /api/v1/audit-logs`

## 14. 数据模型

### 14.1 SQLite

- `User`：用户 ID、显示名称、角色和状态。
- `ApiKey`：用户 ID、密钥哈希、可识别前缀、创建和失效时间。
- `Document`：所有者、范围、版本、哈希、存储键、状态和有效版本标记。
- `IngestionTask`：任务类型、状态、进度、幂等键、重试次数和错误信息。
- `PublicationRequest`：申请人、私人文档、公共副本、审核人、状态和意见。
- `Session`：所有者、标题和业务统计；消息及摘要状态由 LangGraph Checkpointer 管理。
- LangGraph Checkpoint 表：由官方 Checkpointer 管理图状态和消息正文。
- `MessageMetric`：关联会话与运行 ID，保存引用、工具调用摘要和成本数据，不复制消息正文。
- `AuditLog`：操作者、动作、资源、结果和请求追踪 ID。
- `OutboxEvent`：待提交任务事件和投递状态。

### 14.2 Milvus

每个 Chunk 至少包含：

- `chunk_id`
- `document_id`
- `document_version`
- `chunk_index`
- `chunk_hash`
- `scope`
- `user_id`
- `text`
- `source_name`
- `page_number`
- `section`
- `created_at`
- `embedding_model`
- `embedding`

公共文档的 `user_id` 使用统一空值。Milvus Collection 的向量维度必须从所选 Embedding 配置初始化，并在启动检查中验证。

## 15. 权限与安全

- API Key 只在创建时返回一次，数据库只保存安全哈希。
- 普通用户只能管理自己的私人文档和会话。
- 普通用户可以读取公共知识库，但不能直接写入。
- 管理员可以管理公共文档、审批申请和查看审计日志。
- 管理员默认不能读取任意用户的私人聊天内容。
- 所有资源访问必须同时检查角色和资源所有权。
- 上传限制文件大小、MIME 类型和扩展名，并使用随机存储键防止路径穿越。
- 文档内容视为不可信数据。检索片段不得覆盖系统规则或要求调用未授权工具。
- 日志禁止记录 API Key、完整私人文档、Embedding 向量和未脱敏的敏感字段。

## 16. 错误处理与韧性

统一错误响应：

```json
{
  "error": {
    "code": "DOCUMENT_NOT_READY",
    "message": "文档仍在建立索引",
    "request_id": "req_xxx",
    "details": {}
  }
}
```

错误类型覆盖认证、授权、参数、文件解析、任务、模型、Embedding、Milvus、MCP 和内部错误。

- 模型调用采用指数退避，并可切换备用 Provider。
- Embedding 按批次重试，任务可从失败状态重新执行。
- Milvus 仅对连接超时等瞬时错误重试。
- MCP 设置超时和熔断。
- 文档任务通过幂等键防止重复向量。
- 上传和问答分别按 API Key 限流。

## 17. 可观测性

- 输出 JSON 结构化日志。
- 每个请求生成 `request_id`，贯穿 API、任务、检索、Agent 和审计。
- 记录节点耗时、候选数量、重排分数、Token 用量、模型和 Provider。
- 通过配置选择是否启用 LangSmith tracing。
- `/health/live` 只检查应用进程。
- `/health/ready` 检查 SQLite、Milvus、Collection Schema 和必要模型配置。

## 18. 测试策略

### 18.1 单元测试

覆盖 Loader、分块、权限、检索范围、融合去重、引用验证、上下文裁剪和所有领域状态转换。

### 18.2 契约测试

`ObjectStorage`、`TaskQueue`、Embedding、Reranker 和 MCP 适配器的每个实现必须通过共享行为测试。

### 18.3 集成测试

使用测试 SQLite 和 Milvus 验证上传、索引、范围过滤、重新索引和删除。

### 18.4 API 测试

验证认证、用户隔离、审批、同步问答、SSE 事件顺序、错误响应和限流。

### 18.5 Agent 图测试

使用 Fake LLM、Fake Retriever 和 Fake Tool 验证所有条件边、证据不足分支、引用修正和最大循环次数。

### 18.6 安全测试

覆盖伪造 `user_id`、跨用户文档读取、越权发布、路径穿越、Prompt 注入和未授权工具调用。

### 18.7 端到端验收

使用两个普通用户和一个管理员：

1. 两个用户分别上传私人文档。
2. 验证双方无法检索或管理对方文档。
3. 管理员上传公共文档。
4. 验证三种检索范围返回正确来源。
5. 用户提交私人文档发布申请。
6. 管理员批准并等待公共副本完成索引。
7. 另一用户可在公共范围检索到新文档，但无法读取原私人记录。
8. 验证问答引用、SSE 顺序和审计记录。

默认测试不依赖真实外部 LLM、OSS 或 MCP Server。

## 19. 分阶段交付

1. 为现有 `m-agent` 建立依赖锁定、pytest 基线和特征测试。
2. 创建 `src/m_agent/` 包并迁移配置、模型、重试、日志和 Token 统计。
3. 迁移工具注册与内置工具，同时保持原 CLI 可运行。
4. 建立 FastAPI、SQLite、认证和健康检查。
5. 文件存储抽象、文档上传和 Loader 注册中心。
6. `TaskQueue` 与文档索引状态机。
7. Milvus、Embedding、分块和基础检索。
8. 私有、公共、混合检索与 BGE 重排。
9. LangGraph 原生会话、摘要记忆和上下文预算。
10. 新建知识库 Agent、引用检查与 SSE；不修改旧 `chat_agent.py`。
11. 工具注册中心和可选 MCP 集成。
12. 公共发布审批、公共副本和审计。
13. 中间件、限流、容错和完整测试。
14. Docker Compose、运行文档和综合验收练习。

每个交付阶段都必须先写失败测试，再完成最小实现，运行相关测试，并更新对应学习说明。各阶段应形成可独立验证的增量，不把所有集成工作留到最后。

## 20. 完成标准

满足以下条件时视为首版完成：

- `m-agent/agents/chat_agent.py` 与迁移开始前逐字节一致。
- 原有 `m-agent/main.py` CLI 兼容路径仍可启动，且不依赖新 FastAPI 服务。
- `docker compose up -d` 可以启动 Milvus 依赖。
- FastAPI 应用可通过单一命令启动。
- 未配置外部模型 API Key 时默认测试全部通过。
- Markdown、TXT、PDF 可以完成上传、异步索引、状态查询和删除。
- 两个用户的私人数据在 API、SQLite 查询和 Milvus 检索三层均隔离。
- `private`、`shared`、`hybrid` 返回符合范围的结果及有效引用。
- 公共发布申请只有管理员可以审批，批准后生成独立公共副本。
- 同步与 SSE 问答均可工作，SSE 事件顺序稳定。
- 本地工具可调用，MCP 未配置或连接失败时系统仍可正常问答。
- 所有关键状态变化和高风险操作都有审计记录。
- README 提供环境配置、启动、测试、示例请求和常见故障说明。
