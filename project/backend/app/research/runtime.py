"""Phase 2 snapshot adapter for research; never activates or rebuilds indexes."""
from hashlib import file_digest
import logging
from time import perf_counter

from sqlalchemy import select

from app.core.database import session_scope
from app.modeling.adapters import RemoteEmbeddingAdapter
from app.models.document import Document
from app.models.index_job import DocumentIndexJob
from app.models.user import User, STATUS_ENABLED
from app.services import config_service
from app.services.embedding_service import build_endpoint
from app.services.index_build_service import EmbeddingSpec, _valid_vector
from app.services.index_job_service import load_chunk_set
from app.services.index_version_service import load_version_snapshot
from app.services.vector_store import get_vector_store
from app.utils.ids import generate_id
from .agent import ResearchAgent
from .evidence import EvidenceCorpus, HybridEvidenceEngine, VectorHit
from .graph import MemoryGraphStore
from .lexical import LexicalEvidenceRetriever
from .model import CompletionSpec, JsonResearchModel
from .store import SQLResearchTaskStore, digest
from .tasks import ResearchTask, SourceBinding, TaskBudget, comparison_plan
from .tools import ToolContext

logger = logging.getLogger(__name__)


def _claim_review_snapshot(user_id,task_id,*,expected_revision=None,source_artifact_id=None,claim_id=None,vector_store=None,task_store=None):
    from .agent import TaskConflict
    tasks=task_store if task_store is not None else SQLResearchTaskStore()
    task=tasks.load(user_id,task_id)
    if (task.status!='completed' or task.artifact is None or task.verification is None
            or expected_revision is not None and task.revision!=expected_revision
            or source_artifact_id is not None and task.artifact.artifact_id!=source_artifact_id):
        raise TaskConflict('Completed artifact/revision required for owner review')
    if claim_id is not None and claim_id not in {c.claim_id for c in task.artifact.citations}:
        raise LookupError('Cited conclusion not found')
    store=vector_store if vector_store is not None else get_vector_store()
    def scope():
        corpus,bindings,_=_load_scope(user_id,task.index_version_id,tuple(s.document_id for s in task.sources),store)
        if corpus.corpus_id!=task.corpus_id or bindings!=task.sources:
            raise ValueError('Owner review source snapshot changed')
        return corpus
    return tasks,task,scope


def read_claim_review(user_id,task_id,*,expected_revision=None,vector_store=None,task_store=None):
    from .agent import TaskConflict
    from .claim_reviews import build_review_view
    started=perf_counter()
    tasks,task,scope=_claim_review_snapshot(user_id,task_id,expected_revision=expected_revision,
        vector_store=vector_store,task_store=task_store)
    view=build_review_view(task,scope());scope()
    if tasks.load(user_id,task_id)!=task:raise TaskConflict('Task changed while reading owner review')
    logger.info('research_claim_review_read view_id=%s elapsed_ms=%d',view.view_id,round((perf_counter()-started)*1000))
    return view


def record_claim_review(user_id,task_id,claim_id,*,expected_revision,source_artifact_id,decision,reason,vector_store=None,task_store=None):
    from .claim_reviews import append_claim_review,build_review_view
    started=perf_counter()
    tasks,task,scope=_claim_review_snapshot(user_id,task_id,expected_revision=expected_revision,
        source_artifact_id=source_artifact_id,claim_id=claim_id,vector_store=vector_store,task_store=task_store)
    corpus=scope();build_review_view(task,corpus)
    updated=append_claim_review(task,claim_id,decision,reason)
    view=build_review_view(updated,corpus);scope()
    tasks.save_checkpoint(updated,expected_revision=task.revision)
    logger.info('research_claim_review_write event_id=%s view_id=%s elapsed_ms=%d',
        updated.claim_reviews[-1].event_id,view.view_id,round((perf_counter()-started)*1000))
    return view


def read_partial_artifact(user_id, task_id, *, expected_revision=None, vector_store=None, task_store=None):
    """Owner/state checks precede adapters; sources and revision are rechecked.

    No runtime model configuration, provider calls, task writes or activation.
    A concurrent revision change yields conflict rather than an obsolete view.
    """
    from .agent import TaskConflict
    from .partial import build_partial_view
    started=perf_counter()
    tasks=task_store if task_store is not None else SQLResearchTaskStore()
    task=tasks.load(user_id,task_id)
    if (task.status!='failed' or task.verification is not None or task.artifact is not None
            or (expected_revision is not None and expected_revision!=task.revision)):
        raise TaskConflict('Partial artifact is unavailable for this task state/revision')
    store=vector_store if vector_store is not None else get_vector_store()
    documents=tuple(s.document_id for s in task.sources)
    def scope():
        corpus,bindings,_=_load_scope(user_id,task.index_version_id,documents,store)
        if corpus.corpus_id!=task.corpus_id or bindings!=task.sources:
            raise ValueError('Partial artifact source snapshot changed')
        return corpus
    view=build_partial_view(task,scope())
    scope()  # Detect observed source drift while rendering the view.
    if tasks.load(user_id,task_id)!=task:
        raise TaskConflict('Research checkpoint changed while reading partial artifact')
    logger.info('research_partial_view view_id=%s elapsed_ms=%d',view.view_id,round((perf_counter()-started)*1000))
    return view


def _source_binding(user_id, document_id, chunk_set_id):
    with session_scope() as db:
        owner = db.get(User, user_id)
        if owner is None or owner.status != STATUS_ENABLED:
            raise PermissionError("Research account is not enabled")
        doc = db.get(Document, document_id)
        if doc is None or doc.user_id != user_id or doc.status != "ready":
            raise LookupError("Research source not found")
        with open(doc.local_path, "rb") as stream:
            sha = file_digest(stream, "sha256").hexdigest()
        job = db.scalar(select(DocumentIndexJob).where(DocumentIndexJob.user_id == user_id,
            DocumentIndexJob.document_id == document_id, DocumentIndexJob.chunk_set_id == chunk_set_id,
            DocumentIndexJob.status == "succeeded", DocumentIndexJob.source_sha256 == sha).limit(1))
        if job is None:
            raise ValueError("Research source changed after chunk preparation")
        return SourceBinding(document_id=document_id, chunk_set_id=chunk_set_id, source_sha256=sha, title=doc.file_name)


def _retry_snapshot(user_id, task_id, *, expected_revision=None, vector_store=None, task_store=None):
    """No credentials/models. Reject state/history before initializing storage."""
    from .agent import TaskConflict
    from .recovery import retry_decision
    tasks = task_store if task_store is not None else SQLResearchTaskStore()
    task = tasks.load(user_id, task_id)
    if expected_revision is not None and task.revision != expected_revision:
        raise TaskConflict('Retry checkpoint changed')
    decision = retry_decision(task)
    if decision.eligible:
        store = vector_store if vector_store is not None else get_vector_store()
        for _ in range(2):
            corpus, bindings, _ = _load_scope(user_id, task.index_version_id, tuple(s.document_id for s in task.sources), store)
            if corpus.corpus_id != task.corpus_id or bindings != task.sources:
                raise ValueError('Retry sources changed')
        decision = decision.model_copy(update={'sources_validated': True})
    if tasks.load(user_id, task_id) != task:
        raise TaskConflict('Retry checkpoint changed during source validation')
    return tasks, task, decision


def read_retry(user_id, task_id, **kwargs):
    return _retry_snapshot(user_id, task_id, **kwargs)[2]


def retry_failed(user_id, task_id, *, expected_revision, **kwargs):
    from .agent import TaskConflict
    from .recovery import retry_candidate
    tasks, task, decision = _retry_snapshot(user_id, task_id, expected_revision=expected_revision, **kwargs)
    if not decision.eligible or not decision.sources_validated:
        raise TaskConflict('Retry is unavailable; retain this checkpoint')
    saved = tasks.save_checkpoint(retry_candidate(task), expected_revision=task.revision)
    logger.info('research_retry task_id=%s failed_revision=%d revision=%d', task.id, task.revision, saved.revision)
    return saved


def _load_scope(user_id, version_id, document_ids, store):
    manifest = load_version_snapshot(user_id, version_id, store=store)
    members = {m["document_id"]: m for m in manifest["members"]}
    if len(document_ids) != len(set(document_ids)) or any(d not in members for d in document_ids):
        raise ValueError("Invalid research document scope")
    bindings = tuple(_source_binding(user_id, d, members[d]["chunk_set_id"]) for d in document_ids)
    corpus = EvidenceCorpus(user_id, tuple(load_chunk_set(user_id, b.chunk_set_id) for b in bindings))
    return corpus, bindings, manifest


def prepare_task(user_id, version_id, document_ids, goal, *, completion, budget=None, vector_store=None,
                plan_version="research-comparison-v1", context_policy="parent-floor-v2", candidate_policy="vector-v1"):
    if not 3 <= len(document_ids) <= 5 or not goal.strip():
        raise ValueError("Select 3–5 documents and a research goal")
    corpus, sources, _ = _load_scope(user_id, version_id, tuple(document_ids), vector_store or get_vector_store())
    if budget is None:
        budget = TaskBudget(max_steps=max(12, 3 * len(sources) + 4), max_model_calls=max(8, 2 * len(sources) + 2)) if plan_version == "research-comparison-v2" else TaskBudget()
    task = ResearchTask(id=generate_id("research"), user_id=user_id, goal=goal, schema_version=plan_version,
        index_version_id=version_id, corpus_id=corpus.corpus_id, sources=sources,
        completion=completion, budget=budget, context_policy=context_policy, candidate_policy=candidate_policy,
        steps=comparison_plan(sources, goal, version=plan_version))
    from .agent import validate_task_plan
    validate_task_plan(task)
    return task


def task_preview(task):
    """Deterministic seal binds the complete validated draft except its random ID.

    Does not persist a task, activate an index, or invoke a model. It is a
    consistency token, not an authorization token or an idempotency key.
    """
    import json
    payload = task.model_dump(mode='json', exclude={'id'})
    seal = digest(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
    return {'preview_id': seal, 'goal': task.goal, 'index_version_id': task.index_version_id,
            'sources': [{'document_id': s.document_id, 'title': s.title} for s in task.sources],
            'steps': [s.model_dump(mode='json') for s in task.steps],
            'budget': task.budget.model_dump(mode='json'), 'plan_version': task.schema_version,
            'model_id': task.completion.model_id, 'status': 'preview',
            'task_created': False, 'model_calls': 0}


def create_task(user_id, version_id, document_ids, goal, *, completion, budget=None, vector_store=None, task_store=None,
                plan_version="research-comparison-v1", context_policy="parent-floor-v2", candidate_policy="vector-v1",
                expected_preview_id=None):
    task = prepare_task(user_id, version_id, document_ids, goal, completion=completion, budget=budget,
        vector_store=vector_store, plan_version=plan_version, context_policy=context_policy, candidate_policy=candidate_policy)
    if expected_preview_id is not None and task_preview(task)['preview_id'] != expected_preview_id:
        from .agent import TaskConflict
        raise TaskConflict('Research preview changed; review a fresh plan before creating')
    return (task_store or SQLResearchTaskStore()).create(task)


class FrozenVersionRetriever:
    def __init__(self, task, corpus, manifest, config, store, *, model=None, research_facets=False):
        self.task, self.corpus, self.manifest, self.config, self.store = task, corpus, manifest, config, store
        self.model = model
        self.research_facets = research_facets

    def search(self, user_id, query, document_ids, top_k):
        self.corpus.require_scope(user_id, document_ids)
        spec = EmbeddingSpec.model_validate(self.manifest["embedding"])
        if spec.endpoint != build_endpoint(self.config.embedding_base_url, "embeddings"):
            raise ValueError("Frozen embedding endpoint differs from credential binding")
        model = self.model or RemoteEmbeddingAdapter(endpoint=spec.endpoint, api_key=self.config.embedding_api_key,
            model_id=spec.model_id, version=spec.version, timeout=spec.timeout_seconds, max_retries=1)
        queries = [query]
        if self.research_facets:
            queries = [f"{facet}. Research goal: {self.task.goal[:600]}" for facet in (
                "Model architecture method encoder retriever training",
                "Evaluation datasets benchmarks question answering",
                "Experimental results exact match accuracy scores",
                "Limitations failure analysis computational cost future work")]
        vectors = model.embed_documents(queries) if self.research_facets else [model.embed_query(query)]
        if len(vectors) != len(queries) or not all(_valid_vector(vector, spec.dimension) for vector in vectors):
            raise ValueError("Invalid research query embedding")
        members = {m["document_id"]: m for m in self.manifest["members"]}
        ranked_groups = []
        for vector in vectors:
            results = []
            for d in document_ids:
                chunks = self.corpus.chunk_sets[d].child_chunks
                for hit in self.store.search(user_id, vector, top_k, index_version=members[d]["namespace"]):
                    if (hit.doc_id != d or not 0 <= hit.chunk_index < len(chunks)
                            or chunks[hit.chunk_index].text != hit.text):
                        raise ValueError("Research hit provenance changed")
                    results.append(VectorHit(chunk_id=chunks[hit.chunk_index].chunk_id, score=hit.score))
            ranked_groups.append(sorted(results, key=lambda h: (-h.score, h.chunk_id)))
        # Interleave facet-specific rankings instead of letting architecture
        # terms dominate result/limitation context. No scores across facets are
        # interpreted as probabilities. All candidates remain source checked.
        combined, seen = [], set()
        for rank in range(max((len(g) for g in ranked_groups), default=0)):
            for group in ranked_groups:
                if rank < len(group) and group[rank].chunk_id not in seen:
                    combined.append(group[rank])
                    seen.add(group[rank].chunk_id)
        return combined


def configured_agent(*, vector_store=None, task_store=None):
    tasks = task_store or SQLResearchTaskStore()

    def context_factory(task):
        store = vector_store if vector_store is not None else get_vector_store()
        document_ids = tuple(s.document_id for s in task.sources)
        def frozen_corpus():
            corpus, bindings, manifest = _load_scope(task.user_id, task.index_version_id, document_ids, store)
            if corpus.corpus_id != task.corpus_id or bindings != task.sources:
                raise ValueError("Research sources changed")
            return corpus, manifest
        corpus, manifest = frozen_corpus()
        with session_scope() as db:
            config = config_service.load_runtime_config(db)
        if (task.completion.endpoint != build_endpoint(config.llm_base_url, "chat/completions")
                or task.completion.model_id != config.llm_model):
            raise ValueError("Frozen completion model differs from credential binding")
        graph = MemoryGraphStore()
        for source in task.sources:
            graph.replace_document(task.user_id, source.document_id,
                tuple(r for r in task.relations if r.document_id == source.document_id), corpus)
        retriever = FrozenVersionRetriever(task, corpus, manifest, config, store, research_facets=True)
        if task.candidate_policy in {"lexical-fusion-v2", "source-role-v3"}:
            retriever = LexicalEvidenceRetriever(corpus, retriever,
                source_role=task.candidate_policy == "source-role-v3")
        model = JsonResearchModel(task.completion, api_key=config.llm_api_key, max_calls=1)
        return ToolContext(task, corpus, HybridEvidenceEngine(corpus, retriever, graph), model, frozen_corpus)

    return ResearchAgent(tasks, context_factory)
