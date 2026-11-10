"""Owner review history and a source-checked overlay; never overwrite evidence.

Owner decisions are personal review records, not independent evaluation labels.
Reset appends a new event. A withdrawal restricts a derived artifact only.
"""
from datetime import datetime,timezone
from typing import Literal
from pydantic import AwareDatetime,Field,field_validator
from app.chunking.models import Snapshot,Identifier,content_id
from .artifacts import Claim,ArtifactSource,ComparisonArtifact,ArtifactComposer


class ClaimReviewEvent(Snapshot):
    event_id: Identifier
    version: Literal['owner-claim-review-v1']='owner-claim-review-v1'
    task_id: Identifier
    source_artifact_id: Identifier
    claim_id: Identifier
    actor_id: int=Field(strict=True,gt=0)
    sequence: int=Field(strict=True,ge=1,le=100)
    task_revision: int=Field(strict=True,gt=0)
    previous_event_id: Identifier|None=None
    decision: Literal['retain','withdraw','reset']
    reason: str=Field(min_length=1,max_length=1000)
    reviewed_at: AwareDatetime

    @field_validator('reason')
    @classmethod
    def nonblank_reason(cls,value):
        if not value.strip():raise ValueError('Review reason must not be blank')
        return value

    def expected_id(self):
        return content_id('claim_review_',self.model_dump(mode='json',exclude={'event_id'}))


def validate_review_history(task):
    if not task.claim_reviews:return
    for event in task.claim_reviews:
        ClaimReviewEvent.model_validate(event.model_dump(mode='python'))
    if task.status!='completed' or task.artifact is None:
        raise ValueError('Owner reviews require a completed artifact')
    allowed={c.claim_id for c in task.artifact.citations}
    previous=None;revision=task.claim_reviews[0].task_revision-1
    for index,event in enumerate(task.claim_reviews,1):
        if (event.event_id!=event.expected_id() or event.sequence!=index
                or event.task_id!=task.id or event.actor_id!=task.user_id
                or event.source_artifact_id!=task.artifact.artifact_id or event.claim_id not in allowed
                or event.previous_event_id!=previous or event.task_revision!=revision+1):
            raise ValueError('Owner review history identity or scope mismatch')
        previous=event.event_id;revision=event.task_revision
    if revision!=task.revision:raise ValueError('Owner review revision mismatch')


def append_claim_review(task,claim_id,decision,reason):
    validate_review_history(task)
    if (task.status!='completed' or task.artifact is None
            or claim_id not in {c.claim_id for c in task.artifact.citations}):
        raise ValueError('Claim is not a cited conclusion of a completed artifact')
    if len(task.claim_reviews)>=100:raise ValueError('Owner review history budget exhausted')
    event=ClaimReviewEvent(event_id='pending',task_id=task.id,source_artifact_id=task.artifact.artifact_id,
        claim_id=claim_id,actor_id=task.user_id,sequence=len(task.claim_reviews)+1,
        task_revision=task.revision+1,previous_event_id=task.claim_reviews[-1].event_id if task.claim_reviews else None,
        decision=decision,reason=reason,reviewed_at=datetime.now(timezone.utc))
    event=event.model_copy(update={'event_id':event.expected_id()})
    updated=task.model_copy(update={'revision':task.revision+1,'claim_reviews':(*task.claim_reviews,event)})
    validate_review_history(updated)
    return updated


class ClaimReviewItem(Snapshot):
    claim: Claim
    source: ArtifactSource
    review_status: Literal['unreviewed','retained','withdrawn']
    latest_event_id: Identifier|None=None


class ClaimReviewView(Snapshot):
    view_id: Identifier
    version: Literal['owner-claim-review-v1']='owner-claim-review-v1'
    task_id: Identifier
    task_revision: int=Field(strict=True,ge=0)
    source_artifact_id: Identifier
    items: tuple[ClaimReviewItem,...]
    events: tuple[ClaimReviewEvent,...]
    artifact: ComparisonArtifact
    annotation_status: Literal['owner_review_overlay']='owner_review_overlay'
    quality_gate_passed: Literal[False]=False
    model_calls: Literal[0]=0
    embedding_calls: Literal[0]=0

    def expected_id(self):
        return content_id('claim_review_view_',self.model_dump(mode='json',exclude={'view_id'}))


def build_review_view(task,corpus) -> ClaimReviewView:
    """Rebuild both baseline and overlay from the unchanged candidate/source set."""
    validate_review_history(task)
    if task.status!='completed' or task.artifact is None or task.verification is None:
        raise ValueError('Completed machine artifact required')
    documents=tuple(s.document_id for s in task.sources);titles={s.document_id:s.title for s in task.sources}
    composer=ArtifactComposer()
    baseline=composer.compose(corpus,task.goal,documents,titles,task.claims,task.verification)
    if baseline!=task.artifact:raise ValueError('Machine artifact differs from frozen source reconstruction')
    latest={event.claim_id:event for event in task.claim_reviews}
    withdrawn={key for key,event in latest.items() if event.decision=='withdraw'}
    artifact=baseline
    if withdrawn:
        verdicts=tuple(v.model_copy(update={'status':'insufficient','reason':'owner_review_withdrawn'})
            if v.claim_id in withdrawn else v for v in task.verification.verdicts)
        report=task.verification.model_copy(update={'verdicts':verdicts,
            'supported':sum(v.status=='supported' for v in verdicts),
            'warnings':(*task.verification.warnings,'owner_review_overlay_not_independent_gold')})
        artifact=composer.compose(corpus,task.goal,documents,titles,task.claims,report)
    sources={s.claim_id:s for s in baseline.citation_sources}
    items=tuple(ClaimReviewItem(claim=claim,source=sources[claim.claim_id],
        review_status={'retain':'retained','withdraw':'withdrawn','reset':'unreviewed'}[latest[claim.claim_id].decision]
            if claim.claim_id in latest else 'unreviewed',
        latest_event_id=latest[claim.claim_id].event_id if claim.claim_id in latest else None)
        for claim in baseline.citations)
    view=ClaimReviewView(view_id='pending',task_id=task.id,task_revision=task.revision,
        source_artifact_id=baseline.artifact_id,items=items,events=task.claim_reviews,artifact=artifact)
    return view.model_copy(update={'view_id':view.expected_id()})
