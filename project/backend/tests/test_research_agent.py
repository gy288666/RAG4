"""Durable comparison workflow, independent verification and control fences."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import httpx
import pytest

from app.core.database import SessionLocal
from app.models.research_task import ResearchTaskRecord
from app.models.user import User
from app.research.agent import ResearchAgent, TaskConflict
from app.research.artifacts import (ArtifactComposer, Claim, EvidenceVerifier, VerificationReport, Verdict,
    extract_claims)
from app.research.evidence import HybridEvidenceEngine, RetrievalOptions
from app.research.graph import Citation
from app.research.model import CompletionSpec, JsonResearchModel
from app.research.store import SQLResearchTaskStore
from app.research.tasks import ResearchTask, SourceBinding, TaskBudget, comparison_plan
from app.research.tools import ToolContext, comparison_tools
from test_research_evidence import Hits, corpus_for


class FakeModel:
    def __init__(self):
        self.calls = []

    def generate(self, operation, payload):
        self.calls.append({"operation": operation, "status": "succeeded", "usage": {"total_tokens": 1}})
        if operation == "verify":
            return {"verdicts": [{"claim_id": c["claim_id"], "status": "supported", "reason": "Supported by supplied source"}
                for c in payload["claims"]]}
        item = payload["evidence"][0]
        return {"claims": [{"facet": "method", "statement": item["text"], "evidence_id": item["evidence_id"], "quote": item["text"]}], "relations": []}


@pytest.fixture
def workflow():
    with SessionLocal() as db:
        owner = User(email="research@example.org", password_hash="unused", status=1)
        db.add(owner)
        db.commit()
        user_id = owner.id
    corpus = corpus_for("DPR uses BERT.", "FiD uses T5.", "REALM uses BERT.", owner=user_id)
    sources = tuple(SourceBinding(document_id=d, chunk_set_id=s.chunk_set_id, source_sha256="a" * 64, title=d)
        for d, s in corpus.chunk_sets.items())
    task = ResearchTask(id="research-test", user_id=user_id, goal="比较模型方法与实验条件", index_version_id="version-test",
        corpus_id=corpus.corpus_id, sources=sources, completion=CompletionSpec(endpoint="https://model.example/v1/chat/completions", model_id="fake"),
        budget=TaskBudget(), steps=comparison_plan(sources, "比较模型方法与实验条件"))
    store = SQLResearchTaskStore()
    store.create(task)
    model = FakeModel()
    engine = HybridEvidenceEngine(corpus, ScopedHits(corpus))
    context = lambda current: ToolContext(current, corpus, engine, model)
    return task, corpus, store, model, ResearchAgent(store, context), context


class ScopedHits(Hits):
    def __init__(self, corpus):
        super().__init__(corpus)
        self.corpus = corpus

    def search(self, user_id, query, document_ids, top_k):
        return [h for h in super().search(user_id, query, document_ids, top_k)
            if self.corpus.chunks[h.chunk_id].document_id in document_ids][:top_k]


def finish(agent, task):
    for _ in range(task.budget.max_steps):
        task = agent.step(task.user_id, task.id)
        if task.status in {"completed", "failed", "paused", "cancelled"}:
            return task
    pytest.fail("Comparison did not terminate")


def test_sql_restart_to_completed_comparison_with_missing_fields(workflow):
    task, corpus, store, model, agent, context = workflow
    first = agent.step(task.user_id, task.id)
    assert first.steps[0].status == "succeeded" and first.tool_calls_used == 1
    # Recreate the store and executor: progress is not a process-local counter.
    done = finish(ResearchAgent(SQLResearchTaskStore(), context), first)
    assert done.status == "completed" and done.tool_calls_used == 8 and done.model_calls_used == 4
    assert len(model.calls) == 4
    assert len(done.artifact.rows) == 3 and len(done.artifact.citations) == 3
    assert len(done.artifact.knowledge_gaps) == 9
    assert done.artifact.artifact_id == done.artifact.expected_id()
    assert done.artifact.verification.annotation_status == "machine_review_only"
    assert all(s.result and s.result.elapsed_ms >= 0 for s in done.steps)
    assert all("text" not in json.dumps(s.result.data) for s in done.steps)
    assert "论文没有报告" not in done.artifact.markdown
    assert "本表不作性能排名" in done.artifact.markdown
    assert agent.step(task.user_id, task.id) == done  # terminal execution is inert


def test_pause_resume_cancel_and_wrong_revision(workflow):
    task, _, store, _, agent, _ = workflow
    paused = agent.control(task.user_id, task.id, "pause", 0)
    assert agent.step(task.user_id, task.id) == paused
    with pytest.raises(TaskConflict):
        agent.control(task.user_id, task.id, "resume", 0)
    resumed = agent.control(task.user_id, task.id, "resume", paused.revision)
    assert resumed.status == "pending"
    running = agent.step(task.user_id, task.id)
    cancelled = agent.control(task.user_id, task.id, "cancel", running.revision)
    assert cancelled.status == "cancelled" and cancelled.artifact is None
    assert all(s.status in {"succeeded", "cancelled"} for s in cancelled.steps)
    with pytest.raises(LookupError):
        store.load(task.user_id + 1, task.id)


def test_cancel_during_tool_discards_late_result_and_second_runner_is_fenced(workflow):
    task, _, store, _, _, context = workflow
    entered, released = threading.Event(), threading.Event()
    def blocked(current):
        entered.set()
        assert released.wait(10)
        return context(current)
    agent = ResearchAgent(store, blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(agent.step, task.user_id, task.id)
        assert entered.wait(10)
        claimed = store.load(task.user_id, task.id)
        with pytest.raises(TaskConflict):
            agent.step(task.user_id, task.id)
        cancelled = agent.control(task.user_id, task.id, "cancel", claimed.revision)
        released.set()
        assert future.result(10) == cancelled
    assert cancelled.bundles == () and cancelled.artifact is None


def test_failure_is_safe_persistent_and_retry_spends_budget(workflow):
    task, _, store, _, _, context = workflow
    def broken(current):
        raise ConnectionError("private credential and endpoint")
    failed = ResearchAgent(store, broken).step(task.user_id, task.id)
    assert failed.status == "failed" and failed.error_code == "research_context_unavailable"
    assert "private" not in failed.model_dump_json()
    retrier = ResearchAgent(store, context)
    resumed = retrier.control(task.user_id, task.id, "resume", failed.revision)
    done = finish(retrier, resumed)
    assert done.status == "completed" and done.tool_calls_used == 9


def test_plan_and_budget_changes_are_rejected(workflow):
    task, _, store, _, _, _ = workflow
    malicious = task.model_copy(update={"steps": (task.steps[0].model_copy(update={"tool_name": "shell"}),) + task.steps[1:]})
    with pytest.raises(ValueError, match="plan"):
        store.save_checkpoint(malicious, expected_revision=0)
    with pytest.raises(ValueError, match="Budget"):
        store.save_checkpoint(task.model_copy(update={"budget": TaskBudget(max_steps=2)}), expected_revision=0)
    with SessionLocal() as db:
        row = db.get(ResearchTaskRecord, task.id)
        row.payload_json = row.payload_json.replace("research-test", "different")
        db.commit()
    with pytest.raises(ValueError, match="integrity"):
        store.load(task.user_id, task.id)


def test_unregistered_tools_and_invalid_arguments_never_execute(workflow):
    task, corpus, _, model, _, context = workflow
    registry = comparison_tools()
    bad = registry.execute("shell", context(task), {"command": "anything"})
    assert bad.status == "failed" and model.calls == []
    bad_args = registry.execute("search_evidence", context(task), {"document_id": "d0", "query": "models", "extra": "private"})
    assert bad_args.status == "failed"
    with pytest.raises(ValueError):
        registry.register("search_evidence", object, None)


def claim_for(corpus, statement="DPR uses BERT.", facet="method"):
    chunk = next(iter(corpus.chunks.values()))
    claim = Claim(claim_id="pending", document_id=chunk.document_id, facet=facet, statement=statement,
        citation=Citation(chunk_id=chunk.chunk_id, char_start=0, char_end=len(chunk.text), quote=chunk.text))
    return claim.model_copy(update={"claim_id": claim.expected_id(corpus.corpus_id)})


def test_exact_quote_does_not_bypass_semantic_verifier_or_missing_judgment():
    corpus = corpus_for("DPR uses BERT.")
    claim = claim_for(corpus, "DPR uses T5.", "result")
    class Reject:
        def generate(self, operation, payload):
            return {"verdicts": [{"claim_id": claim.claim_id, "status": "contradicted", "reason": "Source contains no result"}]}
    report = EvidenceVerifier(Reject()).verify(corpus, (claim,))
    artifact = ArtifactComposer().compose(corpus, "compare", ("d0",), {"d0": "DPR"}, (claim,), report)
    assert report.supported == 0 and "DPR uses T5" not in artifact.markdown
    assert artifact.rows[0].cells[2].status == "conflict" and not artifact.citations
    class Missing:
        def generate(self, *args):
            return {"verdicts": []}
    assert EvidenceVerifier(Missing()).verify(corpus, (claim,)).verdicts[0].status == "insufficient"


def test_invalid_source_never_reaches_judge_and_duplicate_verdict_fails_closed():
    corpus = corpus_for("DPR uses BERT.")
    claim = claim_for(corpus)
    model = FakeModel()
    tampered = claim.model_copy(update={"citation": claim.citation.model_copy(update={"quote": "DPR uses T5."})})
    report = EvidenceVerifier(model).verify(corpus, (tampered,))
    assert report.supported == 0 and model.calls == []
    class Duplicate:
        def generate(self, *args):
            v = {"claim_id": claim.claim_id, "status": "supported", "reason": "test"}
            return {"verdicts": [v, v]}
    with pytest.raises(ValueError):
        EvidenceVerifier(Duplicate()).verify(corpus, (claim,))


def test_conflicting_supported_claims_remain_visible_as_gap():
    corpus = corpus_for("DPR uses BERT.")
    one, two = claim_for(corpus), claim_for(corpus, "A different interpretation.")
    report = VerificationReport(verdicts=tuple(Verdict(claim_id=c.claim_id, status="supported", reason="machine judgment") for c in (one, two)), supported=2, total=2)
    artifact = ArtifactComposer().compose(corpus, "compare", ("d0",), {"d0": "DPR"}, (one, two), report)
    assert artifact.rows[0].cells[0].status == "conflict" and not artifact.citations


def test_unknown_or_ambiguous_quote_is_rejected_not_repaired():
    corpus = corpus_for("DPR uses BERT. DPR uses BERT.")
    bundle = HybridEvidenceEngine(corpus, Hits(corpus)).search(1, "model", RetrievalOptions(document_ids=("d0",)))
    class Ambiguous:
        def generate(self, *args):
            return {"claims": [{"facet": "method", "statement": "Claim", "evidence_id": bundle.items[0].evidence_id, "quote": "DPR uses BERT."}], "relations": []}
    claims, _, warnings = extract_claims(Ambiguous(), corpus, "d0", bundle, "models")
    assert claims == () and warnings == ("draft_claim_rejected:method", "draft_claim_rejected:method:ambiguous_quote")


def test_numeric_mismatch_cannot_be_approved_by_a_permissive_judge():
    corpus = corpus_for("REALM (X = CC-News)\n38.5\n52.0")
    claim = claim_for(corpus, "在 NQ 开发集上，精确匹配 38.2，召回率 52.0", "result")
    model = FakeModel()
    report = EvidenceVerifier(model).verify(corpus, (claim,))
    assert report.supported == 0 and model.calls == []
    assert report.verdicts[0].reason == "numeric_value_not_in_quote"
    artifact = ArtifactComposer().compose(corpus, "compare", ("d0",), {"d0": "REALM"}, (claim,), report)
    assert "38.2" not in artifact.markdown


def test_typographical_quote_match_retains_original_offsets_and_rejects_new_words():
    from app.research.artifacts import locate_quote
    text = "The model uses ﬁd and\nBERT."
    location = locate_quote(text, "ﬁd and BERT.")
    assert text[slice(*location)] == "ﬁd and\nBERT."
    location = locate_quote(text, "fid and BERT.")
    assert text[slice(*location)] == "ﬁd and\nBERT."
    assert locate_quote(text, "fid and T5.") is None
    assert locate_quote("DPR DPR", "DPR") is None


def test_model_timeout_output_truncation_and_call_budget_are_sanitized():
    spec = CompletionSpec(endpoint="https://model.example/v1/chat/completions", model_id="test")
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": '{}'}}]})
    model = JsonResearchModel(spec, api_key="private-secret", max_calls=1, transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="call_failed"):
        model.generate("extract", {})
    with pytest.raises(RuntimeError, match="budget"):
        model.generate("extract", {})
    assert len(requests) == 1 and "private-secret" not in json.dumps(model.calls)
    assert model.calls[0]["status"] == "failed"


def test_caller_owned_http_connection_is_reused_and_not_closed():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"claims": [], "relations": []}'}}], "usage": {"total_tokens": 2}})
    spec = CompletionSpec(endpoint="https://model.example/v1/chat/completions", model_id="test")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = JsonResearchModel(spec, api_key="private", client=client, max_calls=2)
        assert model.generate("extract", {}) == {"claims": [], "relations": []}
        assert model.generate("extract", {}) == {"claims": [], "relations": []}
        assert not client.is_closed and len(seen) == 2
        assert all(request.extensions["timeout"]["read"] == spec.timeout_seconds for request in seen)


def test_historical_verifier_requires_reverification_and_keeps_artifact_identity(workflow):
    task, _, _, _, agent, _ = workflow
    done = finish(agent, task)
    artifact = done.artifact
    old_verification = artifact.verification.model_copy(update={"verifier_version": "exact-source-and-model-v1"})
    with pytest.raises(ValueError, match="reverified"):
        ArtifactComposer().compose(workflow[1], task.goal, tuple(s.document_id for s in task.sources),
            {s.document_id: s.title for s in task.sources}, done.claims, old_verification)
    legacy = artifact.model_copy(update={"composer_version": "comparison-table-v1", "verification": old_verification})
    from app.chunking.models import content_id
    raw = legacy.model_dump(mode="json", exclude={"artifact_id", "completion_status", "citation_sources"})
    assert legacy.expected_id() == content_id("artifact_", raw)


def test_artifact_maps_quote_to_its_actual_pdf_page_not_whole_parent_range():
    from app.chunking import ChunkingConfig, ChunkingEngine
    from app.chunking.models import ParsedDocument, ParsedBlock, SourceInfo
    from app.research.evidence import EvidenceCorpus
    document = ParsedDocument(document_id="d0", file_name="paper.pdf", parser_version="test", page_count=2,
        source=SourceInfo(uri="document:d0"), blocks=(
            ParsedBlock(block_id="p1", text="Introduction text.", page_start=1, page_end=1),
            ParsedBlock(block_id="p2", text="NQ dev result is 38.5.", page_start=2, page_end=2)))
    corpus = EvidenceCorpus(1, (ChunkingEngine().split(document, ChunkingConfig(child_max_tokens=20, parent_max_tokens=100)),))
    parent = corpus.chunk_sets["d0"].parent_chunks[0]
    assert (parent.page_start, parent.page_end) == (1, 2)
    start = parent.text.index("38.5")
    claim = Claim(claim_id="pending", document_id="d0", facet="result", statement="NQ开发集38.5", citation=Citation(
        chunk_id=parent.chunk_id, char_start=start, char_end=start+4, quote="38.5"))
    claim = claim.model_copy(update={"claim_id": claim.expected_id(corpus.corpus_id)})
    report = EvidenceVerifier(FakeModel()).verify(corpus, (claim,))
    artifact = ArtifactComposer().compose(corpus, "compare", ("d0",), {"d0": "paper.pdf"}, (claim,), report)
    source = artifact.citation_sources[0]
    assert (source.page_start, source.page_end) == (2, 2)
    assert source.source_locator.spans[0].block_id == "p2"
    assert source.source_locator.spans[0].char_start == len("NQ dev result is ")
    assert "PDF 页 2–2" in artifact.markdown


def test_invalid_tool_result_becomes_failed_checkpoint_not_stuck_running(workflow):
    task, _, store, _, _, context = workflow
    from app.research.tasks import ToolResult
    class BrokenTool:
        def execute(self, *args):
            return ToolResult(status="succeeded", elapsed_ms=0, data={"unexpected": True})
    failed = ResearchAgent(store, context, BrokenTool()).step(task.user_id, task.id)
    assert failed.status == "failed" and failed.error_code == "research_tool_result_invalid"
    assert failed.steps[0].status == "failed" and not failed.bundles


def test_paused_task_does_not_open_vector_storage(workflow, monkeypatch):
    task, _, store, _, agent, _ = workflow
    paused = agent.control(task.user_id, task.id, "pause", 0)
    from app.research import runtime
    def unavailable():
        pytest.fail("Paused tasks must not open vector storage")
    monkeypatch.setattr(runtime, "get_vector_store", unavailable)
    assert runtime.configured_agent(task_store=store).step(task.user_id, task.id) == paused


def test_research_api_auth_scope_and_control_without_models(client, user_headers, workflow, monkeypatch):
    task, _, _, _, _, _ = workflow
    assert client.get("/api/v1/research-tasks").status_code == 401
    assert client.get(f"/api/v1/research-tasks/{task.id}", headers=user_headers).status_code == 404
    # Owner dependency is replaced for this specific owner; no admin bypass.
    from app.core.deps import get_current_user
    with SessionLocal() as db:
        owner = db.get(User, task.user_id)
        db.expunge(owner)
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: owner
    try:
        detail = client.get(f"/api/v1/research-tasks/{task.id}")
        assert detail.status_code == 200 and detail.json()["data"]["revision"] == 0
        paused = client.post(f"/api/v1/research-tasks/{task.id}/control", json={"action": "pause", "expected_revision": 0})
        assert paused.status_code == 200 and paused.json()["data"]["status"] == "paused"
        assert client.post(f"/api/v1/research-tasks/{task.id}/control", json={"action": "resume", "expected_revision": 0}).status_code == 409
        assert client.post("/api/v1/research-tasks", json={"document_ids": ["a"], "goal": "compare", "index_version_id": "v"}).status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)
