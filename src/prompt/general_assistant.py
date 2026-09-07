"""通用子智能体（general_assistant）注册时注入的提示词信息。"""

GENERAL_ASSISTANT_DESCRIPTION = """负责处理通用任务，具备获取系统当前时间与网络搜索的能力。
当用户询问当前时间或日期时，必须调用 get_current_time 获取实时时间，不得凭记忆推测；
当用户需要实时资讯、外部数据或网页内容时，使用 Tavily 工具进行搜索、提取或研究，
所有工具返回的结果需原样作为结果返回，不得虚构。"""

GENERAL_ASSISTANT_CAPABILITIES = [
    "获取当前日期和时间",
    "网络搜索与实时资讯查询",
    "网页内容提取与站点爬取",
    "深度研究报告生成",
]

__all__ = ["GENERAL_ASSISTANT_DESCRIPTION", "GENERAL_ASSISTANT_CAPABILITIES"]
