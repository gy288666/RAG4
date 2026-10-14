"""Owner-scoped SQL checkpoint CAS; model calls never hold SQL transactions."""
import hashlib

from sqlalchemy import func, select, update

from app.core.database import session_scope
from app.models.research_task import ResearchTaskRecord
from .agent import TaskConflict, validate_task_plan
from .tasks import ResearchTask


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SQLResearchTaskStore:
    def create(self, task):
        validate_task_plan(task)
        if task.status != "pending" or task.revision != 0:
            raise ValueError("New tasks must be pending")
        payload = task.model_dump_json()
        with session_scope() as db:
            db.add(ResearchTaskRecord(id=task.id, user_id=task.user_id, status=task.status, revision=0,
                payload_json=payload, payload_sha256=digest(payload)))
        return self.load(task.user_id, task.id)

    def load(self, user_id, task_id):
        with session_scope() as db:
            row = db.get(ResearchTaskRecord, task_id)
            if row is None or row.user_id != user_id:
                raise LookupError("Research task not found")
            if digest(row.payload_json) != row.payload_sha256:
                raise ValueError("Research checkpoint integrity failed")
            task = ResearchTask.model_validate_json(row.payload_json)
            if (task.id, task.user_id, task.status, task.revision) != (row.id, row.user_id, row.status, row.revision):
                raise ValueError("Research checkpoint identity failed")
            validate_task_plan(task)
            return task

    def save_checkpoint(self, task, *, expected_revision):
        task = task.model_copy(update={"revision": expected_revision + 1})
        validate_task_plan(task)
        payload = task.model_dump_json()
        if len(payload) > 1_000_000:
            raise ValueError("Research checkpoint size budget exceeded")
        with session_scope() as db:
            changed = db.execute(update(ResearchTaskRecord).where(ResearchTaskRecord.id == task.id,
                ResearchTaskRecord.user_id == task.user_id, ResearchTaskRecord.revision == expected_revision).values(
                status=task.status, revision=task.revision, payload_json=payload, payload_sha256=digest(payload))).rowcount
            if not changed:
                raise TaskConflict("Research checkpoint revision changed")
        return task

    def listing(self, user_id, *, limit=20, offset=0):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Invalid pagination")
        with session_scope() as db:
            scope = ResearchTaskRecord.user_id == user_id
            total = db.scalar(select(func.count()).select_from(ResearchTaskRecord).where(scope))
            rows = db.scalars(select(ResearchTaskRecord).where(scope).order_by(
                ResearchTaskRecord.created_at.desc(), ResearchTaskRecord.id.desc()).offset(offset).limit(limit)).all()
            return [{"id": r.id, "status": r.status, "revision": r.revision} for r in rows], total
