#!/usr/bin/env python
"""
===========================================================================
Agent-demo — 通用 AI Agent 框架 交互式入口
===========================================================================

启动后进入交互式对话模式，支持:
  - 多轮对话记忆 (LangGraph Checkpointer — 短期记忆)
  - 长期记忆 (LangGraph Store — InMemoryStore / PostgresStore)
  - 会话隔离 (通过 thread_id)
  - 工具调用 (时间、计算、翻译)
  - 流式输出
  - 内置命令 (/help, /reset, /tools, /memory, /exit)

使用:
    python main.py                              # 默认配置 (内存存储)
    python main.py --provider openai            # 指定模型 Provider
    python main.py --store-type postgres        # 使用 PostgreSQL 持久化
    python main.py --no-stream                  # 禁用流式输出
===========================================================================
"""
import sys
import time
import argparse

# 确保能导入同目录下的模块
sys.path.insert(0, "../src")

from ..src.config import get_config
from ..src.models import get_model, list_available_providers, CAN_RUN
from ..src.agents import ChatAgent
from ..src.utils.logger import get_logger

logger = get_logger("Main")


# ══════════════════════════════════════════════════════════════════
# 内置命令处理
# ══════════════════════════════════════════════════════════════════
def handle_command(cmd: str, agent: ChatAgent) -> bool:
    """处理内置命令，返回 True 表示继续对话，False 表示退出"""
    cmd = cmd.strip().lower()

    if cmd in ("/exit", "/quit", "/q"):
        print("\n👋 再见！")
        return False

    elif cmd in ("/help", "/h"):
        print("""
┌──────────────────────────────────────────────────────────┐
│                    内置命令                                │
├──────────────────────────────────────────────────────────┤
│ /help, /h     显示此帮助信息                              │
│ /reset, /r    重置对话历史                                │
│ /tools, /t    显示可用工具列表                            │
│ /memory, /m   显示当前记忆状态                            │
│ /tokens, /tk  显示 Token 消耗统计                          │
│ /stream       切换流式输出开关                            │
│ /exit, /q     退出程序                                    │
└──────────────────────────────────────────────────────────┘
        """.strip())

    elif cmd in ("/reset", "/r"):
        agent.reset()
        print("🔄 对话历史已重置")

    elif cmd in ("/tools", "/t"):
        print(agent.tool_registry.summary())

    elif cmd in ("/memory", "/m"):
        info = agent.get_session_info()
        print(f"📊 记忆状态:")
        print(f"   store_type: {info['store_type']}")
        print(f"   thread_id:  {info['thread_id']}")
        print(f"   消息数:     {info['message_count'] or 0}")
        print(f"   有状态:     {'✅' if info['has_state'] else '❌'}")
        summary = agent.get_summary()
        if summary:
            print(f"📝 对话摘要:\n{summary}")

    elif cmd in ("/tokens", "/tk"):
        stats = agent.get_token_stats()
        print(stats["summary"])
        if stats["call_count"] > 0:
            print(f"   最近一次: 入={stats['last_call']['input']} "
                  f"出={stats['last_call']['output']} "
                  f"计={stats['last_call']['total']}")

    elif cmd == "/stream":
        agent.stream = not agent.stream
        status = "✅ 开启" if agent.stream else "❌ 关闭"
        print(f"📡 流式输出: {status}")

    else:
        print(f"❓ 未知命令: {cmd} (输入 /help 查看帮助)")

    return True


# ══════════════════════════════════════════════════════════════════
# 启动信息
# ══════════════════════════════════════════════════════════════════
def print_banner(agent: ChatAgent):
    """打印启动横幅"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║           🤖 Agent-demo — AI Agent 交互式对话                 ║
║                                                              ║
║  输入消息开始对话 | /help 查看命令 | /exit 退出               ║
╚══════════════════════════════════════════════════════════════╝
    """.strip())
    print()

    # 系统状态
    if CAN_RUN:
        providers = list_available_providers()
        print(f"🤖 模型: {', '.join(providers)} (可用)")
    else:
        print(f"⚠️ 模型: 未配置 API Key (模拟模式)")

    info = agent.get_session_info()
    print(f"🧠 记忆: {info['store_type']} (thread_id={info['thread_id']})")
    print(f"🔧 工具: {agent.tool_registry.tool_count} 个 {agent.tool_registry.list_names()}")
    print(f"📡 流式: {'开' if agent.stream else '关'}")
    print()
    print("─" * 50)


# ══════════════════════════════════════════════════════════════════
# 主循环
# ══════════════════════════════════════════════════════════════════
def main():
    """主入口 — 交互式对话循环"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Agent-demo 交互式对话")
    parser.add_argument("--provider", default="auto",
                        help="模型 Provider (auto/openai/deepseek/anthropic)")
    parser.add_argument("--temperature", type=float, default=0.3,
                        help="生成温度")
    parser.add_argument("--store-type", default="memory",
                        help="存储类型 (memory/postgres, 默认 memory)")
    parser.add_argument("--postgres-conn", default=None,
                        help="PostgreSQL 连接字符串 (store-type=postgres 时使用)")
    parser.add_argument("--max-steps", type=int, default=10,
                        help="Agent 最大推理步数")
    parser.add_argument("--no-stream", action="store_true",
                        help="禁用流式输出")
    parser.add_argument("--no-tools", action="store_true",
                        help="不加载内置工具")
    args = parser.parse_args()

    # 构建 agent 参数
    agent_kwargs = dict(
        name="DemoAgent",
        provider=args.provider,
        temperature=args.temperature,
        store_type=args.store_type,
        max_agent_steps=args.max_steps,
        stream=True,
        load_builtin_tools=not args.no_tools,
        verbose_tokens=True,
    )
    if args.postgres_conn:
        agent_kwargs["postgres_conn"] = args.postgres_conn

    # 创建 Agent
    logger.info("🔧 初始化 ChatAgent...")
    agent = ChatAgent(**agent_kwargs)
    agent.initialize()

    # 打印启动信息
    print_banner(agent)

    # 交互循环
    while True:
        try:
            user_input = input("👤 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        # 处理内置命令
        if user_input.startswith("/"):
            if not handle_command(user_input, agent):
                break
            print()
            continue

        # 调用 Agent
        print("🤖 Agent: ", end="", flush=True)

        start_time = time.time()

        if agent.stream:
            # 流式输出
            full_response = ""
            try:
                for chunk in agent.chat_stream(user_input):
                    print(chunk, end="", flush=True)
                    full_response += chunk
            except Exception as e:
                print(f"\n❌ 错误: {e}")
                continue
            elapsed = (time.time() - start_time) * 1000
            print(f"\n⏱️ ({elapsed:.0f}ms)")
        else:
            # 非流式输出
            try:
                response = agent.chat(user_input)
                print(response)
            except Exception as e:
                print(f"\n❌ 错误: {e}")
                continue
            elapsed = (time.time() - start_time) * 1000
            print(f"⏱️ ({elapsed:.0f}ms)")
        print()


if __name__ == "__main__":
    main()
