"""Conservative retry admission. No models, timestamps-as-leases or auto loops.

Each natural attempt has two CAS writes. Each retry adds exactly one. An extra
control/checkpoint write invalidates this proof, so legacy paused/resumed tasks
are refused rather than assuming an old provider request has stopped.
"""
from typing import Literal
from datetime import datetime
from app.chunking.models import Snapshot
from .tasks import RetryEvent

PAID_TOOLS = {'compare_evidence', 'verify_evidence', 'verify_document'}
NETWORK_ERRORS = {'ConnectTimeout', 'ReadTimeout', 'WriteTimeout', 'PoolTimeout', 'ConnectError', 'ReadError', 'ModelRuntimeTimeout'}


def finished_attempt(step):
    try:
        start, end = datetime.fromisoformat(step.started_at), datetime.fromisoformat(step.finished_at)
        return start.tzinfo is not None and end.tzinfo is not None and end >= start
    except (ValueError, TypeError):
        return False


class RetryDecision(Snapshot):
    task_id: str
    task_revision: int
    eligible: bool
    reason: Literal['available', 'not_failed', 'attempt_not_finished', 'unaccounted_history', 'not_network_failure', 'insufficient_budget']
    failed_step_id: str | None
    remaining_tools: int
    required_tools: int
    remaining_model_calls: int
    required_model_calls: int
    sources_validated: bool = False


def retry_decision(task):
    from .agent import validate_task_plan
    validate_task_plan(task)
    unfinished = [s for s in task.steps if s.status != 'succeeded']
    failed = [s for s in task.steps if s.status == 'failed']
    tools_left = task.budget.max_steps - task.tool_calls_used
    models_left = task.budget.max_model_calls - task.model_calls_used
    models_needed = sum(s.tool_name in PAID_TOOLS for s in unfinished)
    reason = 'available'
    if task.status != 'failed':
        reason = 'not_failed'
    elif (len(failed) != 1 or not unfinished or unfinished[0] != failed[0]
            or any(s.status not in {'failed', 'pending'} for s in unfinished)
            or not finished_attempt(failed[0])
            or failed[0].result is None or failed[0].result.status != 'failed'
            or task.verification is not None or task.artifact is not None):
        reason = 'attempt_not_finished'
    elif task.revision != 2 * task.tool_calls_used + len(task.retry_events):
        reason = 'unaccounted_history'
    else:
        result = failed[0].result
        # JsonResearchModel exposes only a generic RuntimeError; inspect its
        # persisted final call classification, never classify arbitrary errors.
        network = result.error_type in NETWORK_ERRORS
        if result.error_type == 'RuntimeError' and result.model_calls:
            last = result.model_calls[-1]
            network = last.get('status') == 'failed' and last.get('error_type') in NETWORK_ERRORS
        if not network:
            reason = 'not_network_failure'
        elif tools_left < len(unfinished) or models_left < models_needed:
            reason = 'insufficient_budget'
    return RetryDecision(task_id=task.id, task_revision=task.revision, eligible=reason == 'available', reason=reason,
        failed_step_id=failed[0].id if len(failed) == 1 else None, remaining_tools=tools_left,
        required_tools=len(unfinished), remaining_model_calls=models_left, required_model_calls=models_needed)


def retry_candidate(task):
    from .agent import TaskConflict
    if not retry_decision(task).eligible:
        raise TaskConflict('Finished network retry not admissible')
    failed = next(s for s in task.steps if s.status == 'failed')
    event = RetryEvent(failed_revision=task.revision, tool_calls_used=task.tool_calls_used,
        model_calls_used=task.model_calls_used, failed_step=failed)
    return task.model_copy(update={'status': 'pending', 'error_code': None,
        'steps': tuple(s.model_copy(update={'status': 'pending', 'result': None, 'started_at': None, 'finished_at': None})
                       if s.id == failed.id else s for s in task.steps),
        'retry_events': task.retry_events + (event,)})
