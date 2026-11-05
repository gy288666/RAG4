"""Source-checked partial views. These never resume or complete a failed task."""
from typing import Literal
from pydantic import Field
from app.chunking.models import Identifier, Snapshot, content_id
from .artifacts import ArtifactComposer, ComparisonArtifact, VerificationReport
from .evidence import EvidenceCorpus
from .tasks import ResearchTask


_FAILURE_HEADER = '# 失败任务的部分比较稿\n\n原研究任务仍为failed；本稿只复用成功检查点，其余声明未获语义核验，不代表任务完成。\n\n'


class PartialArtifactView(Snapshot):
    view_id: Identifier
    view_version: Literal['failed-research-partial-view-v1'] = 'failed-research-partial-view-v1'
    task_id: Identifier
    task_revision: int = Field(strict=True,ge=0)
    source_task_status: Literal['failed'] = 'failed'
    artifact: ComparisonArtifact
    markdown: str
    retained_documents: tuple[Identifier, ...]
    unverified_documents: tuple[Identifier, ...]
    task_marked_completed: Literal[False] = False
    artifact_attached_to_task: Literal[False] = False
    quality_gate_passed: Literal[False] = False
    model_calls: Literal[0] = 0
    embedding_calls: Literal[0] = 0

    def expected_id(self):
        return content_id('partialview_', self.model_dump(mode='json', exclude={'view_id'}))


def partial_verification(task: ResearchTask, corpus: EvidenceCorpus) -> VerificationReport:
    """Keep committed reports; withhold every other claim, never infer support."""
    from app.research.artifacts import VerificationReport,Verdict,_numbers
    from app.research.result_conditions import audit_result_conditions
    if task.status!='failed' or task.verification is not None or task.artifact is not None:
        raise ValueError('Only a failed task without final verification/artifact may be exported')
    if corpus.corpus_id!=task.corpus_id:raise ValueError('Partial export corpus differs')
    documents={s.document_id for s in task.sources}
    corpus.require_scope(task.user_id,tuple(documents))
    batches={b.document_id:b for b in task.verification_batches}
    if len(batches)!=len(task.verification_batches):raise ValueError('Duplicate checkpoints')
    for batch in task.verification_batches:batch.validate_scope(task)
    reports=[b.verification for b in task.verification_batches]
    for claim in task.claims:
        claim.citation.validate_source(corpus,claim.document_id)
        if claim.document_id not in documents or claim.claim_id!=claim.expected_id(corpus.corpus_id):
            raise ValueError('Partial export claim scope differs')
    verdicts=[v for r in reports for v in r.verdicts]
    audits=[a for r in reports for a in r.condition_audits]
    for claim in task.claims:
        if claim.document_id in batches:continue
        reason='document_verification_unavailable_after_task_failure'
        if not _numbers(claim.statement)<=_numbers(claim.citation.quote):
            reason='numeric_value_not_in_quote'
        elif claim.facet=='result' and task.completion.result_condition_policy=='explicit-row-v1':
            audit=audit_result_conditions(corpus,claim);audits.append(audit)
            if audit.status not in {'passed','not_applicable'}:
                reason='result_condition_'+audit.status+':'+audit.reason
        verdicts.append(Verdict(claim_id=claim.claim_id,status='insufficient',reason=reason))
    version={'numeric-model-v2':'exact-source-numeric-and-model-v2','source-checks-v3':'exact-source-checks-v3',
             'source-handles-v4':'exact-source-handles-v4','facet-handles-v5':'exact-facet-handles-v5'}[task.completion.verification_protocol]
    return VerificationReport(verifier_version=version,verdicts=tuple(verdicts),
        total=len(task.claims),supported=sum(v.status=='supported' for v in verdicts),
        assessments=tuple(a for r in reports for a in r.assessments),
        context_policy=task.completion.verification_context_policy,contexts=tuple(c for r in reports for c in r.contexts),
        result_condition_policy=task.completion.result_condition_policy,condition_audits=tuple(audits),
        warnings=tuple(sorted({'failed_task_partial_export_unverified_documents_withheld',
                              'not_a_completed_research_task','semantic_support_requires_human_review'}|{w for r in reports for w in r.warnings})))


def build_partial_view(task: ResearchTask, corpus: EvidenceCorpus) -> PartialArtifactView:
    """Compose a deterministic read view; every unsupported document stays a gap."""
    verification = partial_verification(task, corpus)
    artifact = ArtifactComposer().compose(corpus, task.goal, tuple(s.document_id for s in task.sources),
        {s.document_id: s.title for s in task.sources}, task.claims, verification)
    retained = tuple(b.document_id for b in task.verification_batches)
    view = PartialArtifactView(view_id='pending', task_id=task.id, task_revision=task.revision,
        artifact=artifact, markdown=_FAILURE_HEADER+artifact.markdown, retained_documents=retained,
        unverified_documents=tuple(sorted({s.document_id for s in task.sources}-set(retained))))
    return view.model_copy(update={'view_id': view.expected_id()})
