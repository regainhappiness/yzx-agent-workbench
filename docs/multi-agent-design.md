# 多智能体 Plan-and-Solve 系统 — 修改清单

## 概述

在现有 m-agent-workbench 基础上新增**层级 Plan-and-Solve 多智能体系统**。MainAgent 负责任务分析、规划、调度、综合，SubAgent 负责执行各自的子任务（Plan-and-Solve 模式）。

### 关键设计决策

- MainAgent 调用 SubAgent 采用**显式规划+执行**（非 LLM tool_calls 决策）
- 流式输出为**分级展示**（主规划 → SubAgent 进度 → 子结果 → 最终答案）
- 先设计通用可扩展框架，具体 SubAgent 类型后续按需添加
- 每个 SubAgent 实例拥有**独立的 ToolRegistry**，L4 API tools 不跨类型共享

---

## 新增文件 (20 个)

### 核心 Agent 层 — `src/agents/multi_agent/`

| 文件 | 说明 |
|------|------|
| `__init__.py` | 公开导出 + `create_default_registry()` 工厂函数 |
| `states.py` | `MainAgentState` + `SubAgentState` TypedDict (15 + 9 字段) |
| `schemas.py` | 6 个 Pydantic 模型：`PlanStep`, `SubStep`, `TaskAnalysis`, `DelegationRequest`, `SubAgentResult`, `SynthesisResult` |
| `events.py` | `MultiAgentEvent` StrEnum — 20 种 SSE 事件类型 (`start`, `plan_created`, `dispatching`, `subagent_*`, `synthesizing`, `token`, `error`, `done` 等) |
| `sub_agent_registry.py` | `SubAgentRegistry` + `SubAgentMeta` — subagent 类型注册与发现 |
| `sub_agent.py` | `SubAgent(BaseAgent)` — Plan-and-Solve 执行器，LangGraph 图: `plan → execute(ReAct) → evaluate → report` |
| `main_agent.py` | `MainAgent(BaseAgent)` — 编排器，LangGraph 图: `analyze → plan → execute → synthesize`，失败时 `replan → plan` |

### L2 多智能体规划 tools — `src/tools/multi_agent_planning/`

| 文件 | 核心功能 |
|------|---------|
| `__init__.py` | 公开导出 |
| `task_analyzer.py` | 分析用户任务 → 判断是否需要 subagent (`TaskAnalysisOutput`) |
| `subagent_matcher.py` | 匹配任务到最佳 subagent → 生成执行计划 (`SubagentMatchOutput`) |
| `delegation_builder.py` | 构建给 subagent 的委托指令 |
| `result_aggregator.py` | 综合多个 subagent 结果 → 最终回答 (`AggregationOutput`) |
| `plan_adjuster.py` | 失败时调整计划 (`AdjustedPlanOutput`) |

### L3 单智能体规划 tools — `src/tools/single_agent_planning/`

| 文件 | 核心功能 |
|------|---------|
| `__init__.py` | 公开导出 |
| `task_decomposer.py` | 将分配任务分解为子步骤 (`DecompositionOutput`) |
| `step_tracker.py` | `StepTracker` 类 — 步骤状态跟踪 + 历史格式化 |
| `self_evaluator.py` | 自评结果质量 → 决定是否需要修正 (`EvaluationOutput`) |

### L1/L4 工具包

| 文件 | 说明 |
|------|------|
| `src/tools/general/__init__.py` | L1 通用 tools — 从现有 `BUILTIN_TOOLS` 导入，所有 Agent 共享 |
| `src/tools/backend_api/__init__.py` | L4 后端 API tools 占位 — 各 subagent 按需扩展 |

### 服务集成

| 文件 | 说明 |
|------|------|
| `src/server/services/multi_agent_service.py` | `MultiAgentService` — MainAgent 服务包装，按 `user_id` 缓存实例，提供 `chat()` / `chat_stream()` |
| `src/server/api/multi_agent.py` | `POST /api/v1/multi-agent/chat/stream` SSE 流式端点，含请求模型 `MultiAgentRequest` |

### 前端

| 文件 | 说明 |
|------|------|
| `front/src/views/MultiAgentView.vue` | 多智能体对话界面 — 左侧 subagent 信息面板，右侧分级展示：分析→计划→调度→SubAgent 进度→Token→最终回答 |

---

## 修改文件 (6 个)

### `src/agents/__init__.py`

新增导出：`MainAgentState`, `SubAgentState`, `PlanStep`, `SubStep`, `TaskAnalysis`, `DelegationRequest`, `SubAgentResult`, `SynthesisResult`, `MultiAgentEvent`, `EVENT_SCHEMAS`, `SubAgentRegistry`, `SubAgentMeta`

### `src/server/main.py`

```python
# 新增 import
from .services.multi_agent_service import MultiAgentService

# lifespan startup (ChatService 之后):
from ..agents.multi_agent import create_default_registry

sub_agent_registry = create_default_registry()
storage_sqlite_dir = os.getenv("STORAGE_SQLITE_DIR", os.path.join(os.getcwd(), "data"))
multi_agent_service = MultiAgentService(
    sub_agent_registry=sub_agent_registry,
    store_type=repo_backend,
    sqlite_path=os.path.join(storage_sqlite_dir, "multi_agent.db") if repo_backend == "sqlite" else None,
)
logger.info("Multi-Agent 服务已启用 (subagents=%d)", sub_agent_registry.count)

# 挂载到 app.state:
app.state.multi_agent_service = multi_agent_service

# shutdown 清理:
if multi_agent_service:
    multi_agent_service.close_all()

# 健康检查新增:
"multi_agent": "ok" if request.app.state.multi_agent_service else "unconfigured"
```

### `src/server/api/__init__.py`

```python
from .multi_agent import router as multi_agent_router
api_router.include_router(multi_agent_router, tags=["多智能体"])
```

### `src/server/deps.py`

```python
def get_multi_agent_service(request: Request):
    """获取 MultiAgentService"""
    return request.app.state.multi_agent_service
```

### `front/src/constants/agents.ts`

```typescript
import { PhGraph as GraphIcon } from '@phosphor-icons/vue'

// 注册到应用中心:
{
    id: 'multi-agent',
    name: 'Multi-Agent',
    shortName: '多智能体',
    description: '层级 Plan-and-Solve 编排：主智能体规划调度，子智能体分工执行。',
    routeName: 'multi-agent',
    icon: GraphIcon,
    capabilities: ['任务编排', '多Agent协作', '分级规划执行'],
}
```

### `front/src/router/index.ts`

```typescript
import MultiAgentView from '../views/MultiAgentView.vue'
// 新增路由:
{ path: 'apps/multi-agent', name: 'multi-agent', component: MultiAgentView }
```

---

## 架构

```
POST /api/v1/multi-agent/chat/stream
        │
        ▼
MultiAgentService ──缓存──▶ MainAgent (LangGraph)
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
                 analyze → plan → execute ──dispatch──▶ SubAgent (LangGraph)
                               │    │                     │
                               │    │         plan → execute(ReAct) → evaluate → report
                               │    ▼                        │
                               └── synthesize              L1 + L4 tools
                                    │
                                    ▼
                                  最终回答
```

### 四层工具体系

| Level | 名称 | 使用方 | 形式 |
|-------|------|--------|------|
| L1 | 通用 tools | MainAgent + 所有 SubAgent 共享 | `@tool` / `bind_tools` |
| L2 | 多智能体规划 | MainAgent graph node 内部 | Prompt + `with_structured_output()` |
| L3 | 单智能体规划 | SubAgent graph node 内部 | Prompt + `with_structured_output()` |
| L4 | 后端 API tools | 特定 SubAgent 专属 | `@tool` / `bind_tools` |

### SSE 事件流 (分级展示)

```
start → analyzing → analysis_done → plan_created
  → dispatching → subagent_start → subagent_plan
    → subagent_step → token → tool_call
  → subagent_done → (下一个 subagent...)
→ synthesizing → synthesis_done → done
```

---

## 新增 SubAgent 类型

```python
# 1. 定义 L4 API tools
from langchain_core.tools import tool

@tool
def sql_query(sql: str) -> str:
    """执行 SQL 查询并返回结果"""
    ...

DATA_ANALYST_TOOLS = [sql_query, ...]

# 2. 注册到 SubAgentRegistry
from src.agents.multi_agent import SubAgentMeta, SubAgent

registry.register(SubAgentMeta(
    subagent_type="data_analyst",
    display_name="数据分析助手",
    description="擅长数据库查询、统计分析、图表生成",
    capabilities=["data_query", "statistics"],
    factory=lambda: SubAgent(
        name="DataAnalyst",
        subagent_type="data_analyst",
        description="数据分析助手",
        capabilities=["data_query", "statistics"],
        api_tools=DATA_ANALYST_TOOLS,
    ),
))
```
