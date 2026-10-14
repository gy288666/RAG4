"""Phase 2 snapshot adapter for research; never activates or rebuilds indexes."""
from hashlib import file_digest

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
from .model import CompletionSpec, JsonResearchModel
from .store import SQLResearchTaskStore
from .tasks import ResearchTask, SourceBinding, TaskBudget, comparison_plan
from .tools import ToolContext


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


def _load_scope(user_id, version_id, document_ids, store):
    manifest = load_version_snapshot(user_id, version_id, store=store)
    members = {m["document_id"]: m for m in manifest["members"]}
    if len(document_ids) != len(set(document_ids)) or any(d not in members for d in document_ids):
        raise ValueError("Invalid research document scope")
    bindings = tuple(_source_binding(user_id, d, members[d]["chunk_set_id"]) for d in document_ids)
    corpus = EvidenceCorpus(user_id, tuple(load_chunk_set(user_id, b.chunk_set_id) for b in bindings))
    return corpus, bindings, manifest


def create_task(user_id, version_id, document_ids, goal, *, completion, budget=None, vector_store=None, task_store=None):
    if not 3 <= len(document_ids) <= 5 or not goal.strip():
        raise ValueError("Select 3–5 documents and a research goal")
    corpus, sources, _ = _load_scope(user_id, version_id, tuple(document_ids), vector_store or get_vector_store())
    task = ResearchTask(id=generate_id("research"), user_id=user_id, goal=goal,
        index_version_id=version_id, corpus_id=corpus.corpus_id, sources=sources,
        completion=completion, budget=budget or TaskBudget(), steps=comparison_plan(sources, goal))
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
        model = JsonResearchModel(task.completion, api_key=config.llm_api_key, max_calls=1)
        return ToolContext(task, corpus, HybridEvidenceEngine(corpus, retriever, graph), model, frozen_corpus)

    return ResearchAgent(tasks, context_factory)
