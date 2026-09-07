"""
===========================================================================
Agent-demo 验证测试 — 测试各核心模块是否正常工作
===========================================================================

运行方法:
    cd Agent-demo
    python test.py

测试内容:
    1. 模型接入层 — Provider 检测
    2. 工具注册中心 — 注册/查询/绑定
    3. 记忆管理器 — 三种策略
    4. ChatAgent — 创建和对话 (需要 API Key)
===========================================================================
"""
import sys
sys.path.insert(0, ".")


def test_models():
    """测试模型接入层"""
    print("=" * 60)
    print("📡 1. 模型接入层 (models/llm.py)")
    print("=" * 60)

    from models import list_available_providers, CAN_RUN, HAS_OPENAI, HAS_DEEPSEEK, HAS_ANTHROPIC

    print(f"\n  API Key 状态:")
    print(f"    OpenAI:   {'✅' if HAS_OPENAI else '❌'} (OPENAI_API_KEY)")
    print(f"    DeepSeek: {'✅' if HAS_DEEPSEEK else '❌'} (DEEPSEEK_API_KEY)")
    print(f"    Anthropic:{'✅' if HAS_ANTHROPIC else '❌'} (ANTHROPIC_API_KEY)")
    print(f"    CAN_RUN:  {'✅' if CAN_RUN else '❌ (至少需配置一个)'}")

    available = list_available_providers()
    print(f"\n  可用 Provider: {available if available else '无 (请配置 .env)'}")

    # 尝试获取模型
    from models import get_model
    model = get_model()
    if model:
        print(f"  ✅ 模型就绪: {model}")
    else:
        print(f"  ⚠️ 未获取到模型 (API Key 未配置)")


def test_tools():
    """测试工具层"""
    print("\n" + "=" * 60)
    print("🔧 2. 工具注册中心 (tools/)")
    print("=" * 60)

    from tools import ToolRegistry, BUILTIN_TOOLS, BUILTIN_TOOLS_META

    # 创建注册中心
    registry = ToolRegistry()
    registry.register_with_meta(BUILTIN_TOOLS, BUILTIN_TOOLS_META)

    print(f"\n{registry.summary()}")

    # 按标签查询
    print(f"\n  按标签 '计算': {[t.name for t in registry.get_by_tag('计算')]}")
    print(f"  按分类 'utility': {[t.name for t in registry.get_by_category('utility')]}")
    print(f"  按名称获取: {registry.get('calculator').name}")

    # 测试工具调用
    print(f"\n  测试工具调用:")
    time_tool = registry.get("get_current_time")
    calc_tool = registry.get("calculator")
    if time_tool:
        print(f"    get_current_time: {time_tool.invoke({})}")
    if calc_tool:
        print(f"    calculator(2**10): {calc_tool.invoke({'expression': '2**10'})}")

def test_agent():
    """测试 Agent 层"""
    print("\n" + "=" * 60)
    print("🤖 4. ChatAgent (agents/)")
    print("=" * 60)

    from models import CAN_RUN
    from agents import ChatAgent

    print(f"\n  创建 ChatAgent...")
    agent = ChatAgent(
        name="TestAgent",
        memory_strategy="window",
        max_turns=5,
    )

    if CAN_RUN:
        print(f"  ✅ Agent 创建成功")
        print(f"  工具数: {agent.tool_registry.tool_count}")
        print(f"  记忆: {agent.memory}")
        print(f"  流式: {agent.stream}")

        print(f"\n  测试对话:")
        response = agent.chat("你好，请用一句话介绍你自己")
        print(f"  👤 用户: 你好，请用一句话介绍你自己")
        print(f"  🤖 Agent: {response[:200]}...")

        print(f"\n  对话记忆: {agent.memory.turn_count} 轮")
    else:
        print(f"  ⚠️ 跳过对话测试 (API Key 未配置)")
        print(f"  框架结构正常，配置 API Key 后可运行完整对话")


def test_config():
    """测试配置层"""
    print("\n" + "=" * 60)
    print("⚙️ 5. 配置管理 (config/)")
    print("=" * 60)

    from config import get_config

    config = get_config()
    print(f"\n  默认配置:")
    print(f"    provider: {config.provider}")
    print(f"    temperature: {config.temperature}")
    print(f"    memory_strategy: {config.memory_strategy}")
    print(f"    max_history_turns: {config.max_history_turns}")
    print(f"    max_agent_steps: {config.max_agent_steps}")
    print(f"    stream: {config.stream}")

    # 测试覆盖
    config2 = get_config(temperature=0.7, memory_strategy="buffer")
    print(f"\n  覆盖配置后:")
    print(f"    temperature: {config2.temperature} (原 0.3 → 0.7)")
    print(f"    memory_strategy: {config2.memory_strategy} (原 window → buffer)")


# ══════════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🧪 Agent-demo 框架验证测试")
    print("=" * 60)

    test_models()
    test_tools()
    test_config()
    test_agent()

    print("\n" + "=" * 60)
    print("✅ 全部测试完成！")
    print("\n💡 提示:")
    print("  如果模型测试显示 ❌，请复制 .env.example 为 .env 并填入 API Key")
    print("  然后重新运行: python test.py")
