"""
===========================================================================
配置管理 — 全局配置项集中管理
===========================================================================
"""
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    """Agent 框架全局配置

    使用方式:
        config = AppConfig()
        config.memory_strategy = "window"
        或
        config = AppConfig(memory_strategy="summary", max_history_turns=20)
    """

    # ═══ 模型配置 ═══
    provider: str = "auto"          # 模型 Provider: auto / openai / deepseek / anthropic
    model_name: str | None = None   # 具体模型名 (None=使用默认模型)
    temperature: float = 0.3        # 生成温度 (0=确定性, 1=创意性)

    # ═══ 记忆配置 ═══
    # memory_strategy: str = "window"    # 记忆策略: buffer / window / summary
    # max_history_turns: int = 10        # 滑动窗口保留的最大对话轮数

    # ═══ Agent 配置 ═══
    max_agent_steps: int = 10          # Agent 最大推理步数 (防止死循环)
    system_prompt: str | None = None   # 自定义系统提示词 (None=使用默认)
    stream: bool = True                # 是否默认使用流式输出

    # ═══ 日志配置 ═══
    log_level: str = "INFO"            # 日志级别: DEBUG / INFO / WARNING / ERROR
    log_format: str = "simple"         # 日志格式: simple / detailed

    # ═══ 工具配置 ═══
    auto_load_builtin_tools: bool = True  # 是否自动加载内置工具


# 全局单例
_default_config: AppConfig | None = None


def get_config(**overrides) -> AppConfig:
    """获取配置单例 (支持覆盖默认值)

    用法:
        config = get_config()                    # 使用默认配置
        config = get_config(temperature=0.7)     # 覆盖部分配置
    """
    global _default_config
    if _default_config is None:
        _default_config = AppConfig(**overrides)
    else:
        for key, value in overrides.items():
            if hasattr(_default_config, key):
                setattr(_default_config, key, value)
    return _default_config
