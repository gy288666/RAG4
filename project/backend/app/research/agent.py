"""One tool per durable checkpoint; cancellation fences late publications."""
from datetime import datetime, timezone
from time import perf_counter
from typing import Protocol

from .artifacts import Claim, ComparisonArtifact, VerificationReport
from .graph import GraphRelation
from .tasks import BundleRef, ResearchTask, ToolResult, comparison_plan
from .tools import ToolContext, comparison_tools


class TaskConflict(ValueError):
    """Reload status/revision before another mutation."""


class ResearchTaskStore(Protocol):
    def load(self, user_id: int, task_id: str) -> ResearchTask: ...
    def save_checkpoint(self, task: ResearchTask, *, expected_revision: int) -> ResearchTask: ...


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_task_plan(task):
    expected = comparison_plan(task.sources, task.goal)
    fields = {"id", "objective", "tool_name", "arguments", "dependencies"}
    if [s.model_dump(include=fields) for s in task.steps] != [s.model_dump(include=fields) for s in expected]:
        raise ValueError("Task plan differs from approved comparison policy")
    if len(expected) > task.budget.max_steps or len(task.sources) + 1 > task.budget.max_model_calls:
        raise ValueError("Budget cannot cover the comparison plan")


def _apply_tool_result(task, tool_name, result):
    if result.status != "succeeded":
        return {}, result
    changes = {}
    if tool_name == "search_evidence":
        ref = BundleRef.model_validate(result.data["bundle"])
        changes["bundles"] = task.bundles + (ref,)
        summary = {"bundle_id": ref.bundle_id}
    elif tool_name == "compare_evidence":
        claims = tuple(Claim.model_validate(c) for c in result.data["claims"])
        changes["claims"] = task.claims + claims
        changes["relations"] = task.relations + tuple(GraphRelation.model_validate(r) for r in result.data["relations"])
        summary = {"claim_ids": [c.claim_id for c in claims], "relation_count": len(result.data["relations"])}
    elif tool_name == "verify_evidence":
        changes["verification"] = VerificationReport.model_validate(result.data["verification"])
        summary = {"supported": changes["verification"].supported, "total": changes["verification"].total}
    else:
        changes["artifact"] = ComparisonArtifact.model_validate(result.data["artifact"])
        summary = {"artifact_id": changes["artifact"].artifact_id}
    return changes, result.model_copy(update={"data": summary})


class ResearchAgent:
    """Read-only fixed-plan executor. Retrying is explicit, never a hidden loop.

    A process interruption leaves a running step visible. Pause fences that
    attempt; resume resets its status and consumes another attempt budget. No
    reliable queue, background schedule or automatic crash recovery is implied.
    """
    def __init__(self, store, context_factory, registry=None):
        self.store, self.context_factory = store, context_factory
        self.registry = registry or comparison_tools()

    def step(self, user_id, task_id):
        task = self.store.load(user_id, task_id)
        validate_task_plan(task)
        if task.status in {"completed", "cancelled", "paused", "failed"}:
            return task
        if any(s.status == "running" for s in task.steps):
            raise TaskConflict("A tool is already running")
        index = next((n for n, s in enumerate(task.steps) if s.status == "pending"), None)
        if index is None:
            raise ValueError("Task has no executable step")
        step = task.steps[index]
        done = {s.id for s in task.steps if s.status == "succeeded"}
        if not set(step.dependencies) <= done:
            raise ValueError("Step dependencies not completed")
        uses_model = step.tool_name in {"compare_evidence", "verify_evidence"}
        if (task.tool_calls_used >= task.budget.max_steps
                or uses_model and task.model_calls_used >= task.budget.max_model_calls):
            return self.store.save_checkpoint(task.model_copy(update={"status": "failed", "error_code": "research_budget_exhausted"}), expected_revision=task.revision)
        steps = list(task.steps)
        steps[index] = step.model_copy(update={"status": "running", "started_at": now(), "finished_at": None, "result": None})
        claimed = self.store.save_checkpoint(task.model_copy(update={"status": "running", "steps": tuple(steps),
            "tool_calls_used": task.tool_calls_used + 1, "model_calls_used": task.model_calls_used + int(uses_model), "error_code": None}),
            expected_revision=task.revision)
        execution_started = perf_counter()
        try:
            context = self.context_factory(claimed)
            if context.corpus.corpus_id != claimed.corpus_id or context.corpus.user_id != user_id:
                raise ValueError("Execution corpus changed")
            result = self.registry.execute(step.tool_name, context, step.arguments)
            if context.assert_fresh is not None:
                context.assert_fresh()
        except Exception as error:
            result = ToolResult(status="failed", elapsed_ms=0, error_code="research_context_unavailable",
                error_type=type(error).__name__)
        result = result.model_copy(update={"elapsed_ms": round((perf_counter() - execution_started) * 1000)})
        try:
            changes, result = _apply_tool_result(claimed, step.tool_name, result)
        except (ValueError, KeyError, TypeError) as error:
            changes = {}
            result = result.model_copy(update={"status": "failed", "data": {},
                "error_code": "research_tool_result_invalid", "error_type": type(error).__name__})
        steps[index] = steps[index].model_copy(update={"status": result.status, "result": result, "finished_at": now()})
        final = "failed" if result.status == "failed" else "completed" if step.tool_name == "compose_artifact" else "running"
        candidate = claimed.model_copy(update={**changes, "steps": tuple(steps), "status": final, "error_code": result.error_code})
        try:
            return self.store.save_checkpoint(candidate, expected_revision=claimed.revision)
        except TaskConflict:
            # Pause/cancel wins over an in-flight result. No second publish.
            return self.store.load(user_id, task_id)

    def control(self, user_id, task_id, action, expected_revision):
        task = self.store.load(user_id, task_id)
        if task.revision != expected_revision:
            raise TaskConflict("Task revision changed")
        if action not in {"pause", "resume", "cancel"}:
            raise ValueError("Unknown control action")
        if task.status in {"completed", "cancelled"}:
            raise TaskConflict("Terminal task cannot be changed")
        steps = list(task.steps)
        if action == "resume":
            if task.status not in {"paused", "failed"}:
                raise TaskConflict("Task is not paused or failed")
            if task.error_code == "research_budget_exhausted":
                raise TaskConflict("Create a new task with an appropriate budget")
            status = "pending"
            for n, s in enumerate(steps):
                if s.status in {"running", "failed"}:
                    steps[n] = s.model_copy(update={"status": "pending"})
        else:
            status = "paused" if action == "pause" else "cancelled"
            for n, s in enumerate(steps):
                if s.status == "running" or action == "cancel" and s.status == "pending":
                    steps[n] = s.model_copy(update={"status": "cancelled" if action == "cancel" else "pending", "finished_at": now()})
        return self.store.save_checkpoint(task.model_copy(update={"status": status, "steps": tuple(steps), "error_code": None}),
            expected_revision=task.revision)
