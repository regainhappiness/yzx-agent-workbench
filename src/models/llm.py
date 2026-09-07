"""
===========================================================================
模型接入层 — 多 Provider 模型工厂
===========================================================================

支持的 Provider:
  - openai     (gpt-4o-mini, gpt-4o 等)      → 需 OPENAI_API_KEY
  - deepseek   (deepseek-chat)                → 需 DEEPSEEK_API_KEY (推荐，便宜)
  - anthropic  (claude-haiku, claude-sonnet)  → 需 ANTHROPIC_API_KEY
  - ollama     (本地部署)                       → 无需 API Key

自动检测逻辑 (provider="auto"):
  DeepSeek → OpenAI → Anthropic → Ollama (按优先级)

使用:
    from models import get_model, list_available_providers

    model = get_model()                         # 自动选择
    model = get_model(provider="deepseek")      # 指定 Provider
    model = get_model(temperature=0.7)          # 调整参数

    providers = list_available_providers()      # 查看可用 Provider
===========================================================================
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件 (先尝试 Agent-demo 目录，再尝试父目录)
_load_paths = [".env", "../.env"]
for _p in _load_paths:
    if os.path.exists(_p):
        load_dotenv(_p)
        break
else:
    load_dotenv()  # 默认行为

from ..utils.logger import get_logger

logger = get_logger(__name__)

# ══════════════════════════════════════════════════════════════════
# Provider 配置表
# ══════════════════════════════════════════════════════════════════
PROVIDER_CONFIG = {
    "openai": {
        "name": "ChatGPT",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
        "module": "langchain_openai",
        "class": "ChatOpenAI",
        "base_url": None,  # 使用官方默认
    },
    "deepseek": {
        "name": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "module": "langchain_deepseek",
        "class": "ChatDeepSeek",
        "base_url": "https://api.deepseek.com",
    },
    "anthropic": {
        "name": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-haiku-4-5-20251001",
        "module": "langchain_anthropic",
        "class": "ChatAnthropic",
        "base_url": None,
    },
}

# ══════════════════════════════════════════════════════════════════
# 可用性检测
# ══════════════════════════════════════════════════════════════════
HAS_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
HAS_DEEPSEEK = bool(os.getenv("DEEPSEEK_API_KEY"))
HAS_ANTHROPIC = bool(os.getenv("ANTHROPIC_API_KEY"))
CAN_RUN = HAS_OPENAI or HAS_DEEPSEEK or HAS_ANTHROPIC

# 自动选择的优先级顺序
_AUTO_PROVIDER_ORDER = ["openai", "deepseek", "anthropic"]


def list_available_providers() -> list[str]:
    """列出当前可用的 Provider (已配置 API Key 的)

    返回: Provider 标识符列表，按推荐优先级排序
    """
    available = []
    for provider_id in _AUTO_PROVIDER_ORDER:
        cfg = PROVIDER_CONFIG[provider_id]
        if os.getenv(cfg["env_key"]):
            available.append(provider_id)
    return available


def get_model(
    provider: str = "auto",
    temperature: float = 0.3,
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
):
    """获取模型实例 —— 多 Provider 工厂函数

    参数:
        provider:    Provider 标识符 (auto / openai / deepseek / anthropic)
                     auto 时优先读取环境变量 LLM_PROVIDER，未设置才自动检测
        temperature: 生成温度 (0.0~1.0)
        api_key:     运行时 API Key；未提供时回退到对应环境变量
        base_url:    运行时 API 地址；未提供时使用 Provider 默认地址
        **kwargs:    传递给模型构造函数的额外参数 (如 model, max_tokens 等)

    返回:
        LangChain ChatModel 实例，如果没有任何可用 Provider 则返回 None

    示例:
        model = get_model()                          # 自动选择 (OpenAI > DeepSeek)
        model = get_model(provider="openai")         # 强制 OpenAI
        model = get_model(temperature=0.0)           # 确定性输出
        model = get_model(model="gpt-4o")            # 指定模型
    """
    # 环境变量指定的 provider（LLM_PROVIDER）优先于 auto 自动检测
    if provider == "auto":
        provider = os.getenv("LLM_PROVIDER", "auto")

    # 自动选择 Provider（显式未指定且环境变量未设置时）
    if provider == "auto":
        available = list_available_providers()
        if not available:
            logger.warning("❌ 没有可用的模型 Provider！请配置 .env 中的 API Key")
            logger.warning("   支持的 Provider: OPENAI_API_KEY / DEEPSEEK_API_KEY / ANTHROPIC_API_KEY")
            return None
        provider = available[0]  # 按优先级取第一个
        logger.info(f"🔍 自动选择 Provider: {provider} ({PROVIDER_CONFIG[provider]['name']})")

    # 获取配置
    cfg = PROVIDER_CONFIG.get(provider)
    if cfg is None:
        logger.error(f"❌ 未知 Provider: {provider}，可选: {list(PROVIDER_CONFIG.keys())}")
        return None

    # 检查 API Key
    resolved_api_key = api_key or os.getenv(cfg["env_key"])
    if not resolved_api_key:
        logger.error(f"❌ {cfg['name']} 的 API Key 未配置 (环境变量: {cfg['env_key']})")
        return None

    # 动态导入并实例化
    try:
        module = __import__(cfg["module"], fromlist=[cfg["class"]])
        ModelClass = getattr(module, cfg["class"])

        model_name = kwargs.pop("model", cfg["default_model"])
        model_kwargs = {
            "model": model_name,
            "temperature": temperature,
            "api_key": resolved_api_key,
        }

        resolved_base_url = base_url or cfg["base_url"]
        if resolved_base_url:
            model_kwargs["base_url"] = resolved_base_url

        model_kwargs.update(kwargs)

        model = ModelClass(**model_kwargs)
        logger.info(f"✅ 模型就绪: {cfg['name']}/{model_name} (temperature={temperature})")
        return model

    except ImportError:
        logger.error(f"❌ 缺少依赖: pip install {cfg['module']}")
        return None
    except Exception as e:
        logger.error(f"❌ 模型初始化失败: {e}")
        return None
