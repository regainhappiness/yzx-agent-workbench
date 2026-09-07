"""
===========================================================================
工具定义层 — 三种工具定义方式 + 内置示例工具
===========================================================================

LangChain 工具定义的三种方式:
  方式1: @tool 装饰器 (推荐, 90% 的场景)
  方式2: StructuredTool.from_function() (包装已有函数)
  方式3: 继承 BaseTool (需要初始化状态时)

内置示例工具:
  - get_current_time: 获取当前时间
  - calculator:        简单数学计算
  - text_translator:   模拟文本翻译

使用:
    from tools import get_current_time, calculator, BUILTIN_TOOLS

    result = get_current_time.invoke({})
    result = calculator.invoke({"expression": "2**10"})
===========================================================================
"""
from datetime import datetime
from langchain_core.tools import tool, StructuredTool


# ══════════════════════════════════════════════════════════════════
# 方式 1: @tool 装饰器 — 最简洁的方式
# ══════════════════════════════════════════════════════════════════

@tool
def get_current_time() -> str:
    """获取当前日期和时间，返回 ISO 格式的时间字符串。返回时区：Asia/Shanghai (UTC+8)"""
    now = datetime.now()
    return f"当前时间: {now.strftime('%Y年%m月%d日 %H:%M:%S')} (星期{['一','二','三','四','五','六','日'][now.weekday()]})"


@tool
def calculator(expression: str) -> str:
    """执行数学计算。支持的运算: + - * / ** (幂) % (取余) // (整除)

    参数:
        expression: 数学表达式字符串，例如 "2 + 3 * 4" 或 "2**10"

    返回: 计算结果
    """
    # 安全检查: 只允许数学表达式中的字符
    allowed_chars = set("0123456789+-*/().%^ ")
    # 将 ** 替换为 ^ 检查后再换回来 (允许幂运算)
    clean = expression.replace("**", "^")

    for char in clean:
        if char not in allowed_chars:
            return f"计算错误: 表达式包含不允许的字符 '{char}'"

    try:
        # 安全评估 (仅用于数学表达式，生产环境应使用更安全的方式)
        result = eval(expression, {"__builtins__": {}}, {})
        return f"计算结果: {expression} = {result}"
    except Exception as e:
        return f"计算错误: {e}"


# ══════════════════════════════════════════════════════════════════
# 方式 2: StructuredTool.from_function() — 包装已有函数
# ══════════════════════════════════════════════════════════════════

def _translate(text: str, target_lang: str = "英文") -> str:
    """模拟翻译功能 (实际项目对接翻译 API)"""
    # 这是一个模拟实现，真实项目应调用翻译 API
    demo_translations = {
        ("你好", "英文"): "Hello",
        ("谢谢", "英文"): "Thank you",
        ("再见", "英文"): "Goodbye",
        ("人工智能", "英文"): "Artificial Intelligence",
    }
    key = (text.strip(), target_lang)
    if key in demo_translations:
        return f"翻译结果 ({target_lang}): {demo_translations[key]}"
    return f"翻译结果 ({target_lang}): [{text}] (模拟翻译，实际项目请对接翻译 API)"


text_translator = StructuredTool.from_function(
    func=_translate,
    name="text_translator",
    description="将文本翻译成指定语言。参数: text (要翻译的文本), target_lang (目标语言，默认'英文')",
)


# ══════════════════════════════════════════════════════════════════
# 内置工具集
# ══════════════════════════════════════════════════════════════════
BUILTIN_TOOLS = [get_current_time]

# 工具元数据 (用于 ToolRegistry)
BUILTIN_TOOLS_META = {
    "get_current_time": {
        "category": "utility",
        "tags": ["时间", "日期", "工具"],
        "version": "1.0.0",
    },
}
