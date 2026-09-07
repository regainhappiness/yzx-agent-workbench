"""
===========================================================================
L3: step_tracker — 跟踪步骤执行状态
===========================================================================

SubAgent.execute 节点使用。
管理子步骤的状态跟踪和历史记录格式化。
===========================================================================
"""


class StepTracker:
    """步骤执行状态跟踪器

    使用:
        tracker = StepTracker()
        tracker.start_step(1, "查询数据库")
        # ... 执行 ...
        tracker.complete_step(1, "查询结果: 100条记录")
        print(tracker.format_history())
    """

    def __init__(self):
        self._steps: dict[int, dict] = {}
        self._current_step: int = 0

    @property
    def current_step(self) -> int:
        return self._current_step

    def start_step(self, step_id: int, description: str) -> None:
        """标记步骤开始执行"""
        self._current_step = step_id
        self._steps[step_id] = {
            "step_id": step_id,
            "description": description,
            "status": "running",
            "result": None,
        }

    def complete_step(self, step_id: int, result: str) -> None:
        """标记步骤完成"""
        if step_id in self._steps:
            self._steps[step_id]["status"] = "completed"
            self._steps[step_id]["result"] = result

    def fail_step(self, step_id: int, error: str) -> None:
        """标记步骤失败"""
        if step_id in self._steps:
            self._steps[step_id]["status"] = "failed"
            self._steps[step_id]["result"] = error

    def get_completed_results(self) -> dict[str, str]:
        """获取所有已完成步骤的结果 {step_id: result}"""
        return {
            str(s["step_id"]): s["result"]
            for s in self._steps.values()
            if s["status"] == "completed" and s["result"]
        }

    def format_history(self) -> str:
        """格式化已完成的步骤历史 (注入 execute prompt)"""
        completed = [
            s for s in self._steps.values()
            if s["status"] in ("completed", "failed")
        ]
        if not completed:
            return "（尚无已完成的步骤）"

        lines = []
        for s in sorted(completed, key=lambda x: x["step_id"]):
            status_icon = "✓" if s["status"] == "completed" else "✗"
            lines.append(
                f"[{status_icon}] 步骤 {s['step_id']}: {s['description']}\n"
                f"    结果: {s['result'] or '(无)'}"
            )
        return "\n".join(lines)

    def all_completed(self, total_steps: int) -> bool:
        """检查所有步骤是否都已完成"""
        completed_count = sum(
            1 for s in self._steps.values()
            if s["status"] == "completed"
        )
        return completed_count >= total_steps


def format_step_history(step_results: dict[str, str]) -> str:
    """将 {step_id: result} dict 格式化为历史文本"""
    if not step_results:
        return "（无历史步骤）"
    lines = []
    for step_id, result in step_results.items():
        lines.append(f"步骤 {step_id} 结果:\n{result}")
    return "\n\n".join(lines)
