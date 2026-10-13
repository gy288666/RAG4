"""Trusted worker boundary: bind current operator credentials to frozen model identity."""
import json

from app.core.database import session_scope
from app.models.user import User, STATUS_ENABLED
from app.services import config_service, index_rebuild_service as rebuilds
from app.services.embedding_service import build_endpoint
from app.services.index_build_service import EmbeddingSpec


def execute_configured_rebuild(user_id: int, task_id: str, *, store=None):
    """Execute one pending/failed task with freshly loaded server credentials.

    No URL or credential is accepted from a task caller. Existing running/terminal
    tasks are returned without model access. run_rebuild owns the SQL CAS claim.
    This is an operator/worker API, not a replacement for HTTP authentication.
    """
    task = rebuilds.get_rebuild(user_id, task_id)
    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None or user.status != STATUS_ENABLED:
            raise PermissionError("Account is not enabled")
        if task.status not in {"pending", "failed"} or task.cancel_requested:
            return task
        config = config_service.load_runtime_config(db)
        spec = EmbeddingSpec.model_validate(json.loads(task.request_json)["embedding"])
        if (config.embedding_provider != "remote"
                or spec.endpoint != build_endpoint(config.embedding_base_url, "/embeddings")
                or spec.model_id != config.embedding_model
                or spec.version != config.embedding_version):
            raise ValueError("Frozen model configuration no longer matches current configuration")
        api_key = config.embedding_api_key
        if not api_key or not api_key.strip():
            raise ValueError("Configured embedding credential is missing")
    return rebuilds.run_rebuild(user_id, task_id, api_key=api_key, store=store)
