"""Fixed, bounded literature-comparison plan; no model-controlled tool execution."""
from typing import Literal

from pydantic import Field, model_validator

from app.chunking.models import Identifier, Snapshot
from .artifacts import Claim, ComparisonArtifact, VerificationReport
from .evidence import EvidenceBundle, EvidenceCorpus, EvidenceItem, RetrievalOptions
from .graph import GraphRelation
from .model import CompletionSpec


class TaskBudget(Snapshot):
    max_steps: int = Field(default=12, strict=True, ge=1, le=24)
    max_model_calls: int = Field(default=8, strict=True, ge=1, le=20)
    max_context_chars: int = Field(default=6000, strict=True, ge=600, le=12000)


class SourceBinding(Snapshot):
    document_id: Identifier
    chunk_set_id: Identifier
    source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    title: str


class EvidenceRef(Snapshot):
    evidence_id: str
    chunk_id: str
    chunk_set_id: str
    matched_child_ids: tuple[str, ...]
    channels: tuple[str, ...]


class BundleRef(Snapshot):
    """Persistent evidence handles. Never copies the full document into logs."""
    bundle_id: str
    corpus_id: str
    user_id: int
    selector_version: str | None = None
    query: str
    options: RetrievalOptions
    items: tuple[EvidenceRef, ...]
    relation_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    context_chars: int
    elapsed_ms: int

    @classmethod
    def capture(cls, bundle: EvidenceBundle):
        return cls(**bundle.model_dump(exclude={"items"}), items=tuple(EvidenceRef(
            chunk_id=i.chunk.chunk_id, **i.model_dump(exclude={"chunk"})) for i in bundle.items))

    def hydrate(self, corpus: EvidenceCorpus):
        if self.selector_version is None:
            raise ValueError("Unversioned experimental evidence must be regenerated")
        if self.corpus_id != corpus.corpus_id or self.user_id != corpus.user_id:
            raise ValueError("Persisted evidence corpus mismatch")
        items = tuple(EvidenceItem(chunk=corpus.chunks[i.chunk_id], **i.model_dump(exclude={"chunk_id"})) for i in self.items)
        bundle = EvidenceBundle(**self.model_dump(exclude={"items"}), items=items)
        if bundle.bundle_id != bundle.expected_id() or bundle.context_chars != sum(len(i.chunk.text) for i in items):
            raise ValueError("Persisted evidence identity mismatch")
        for item in items:
            corpus.validate_item(item)
        return bundle


class ToolResult(Snapshot):
    status: Literal["succeeded", "failed"]
    data: dict = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    elapsed_ms: int = Field(ge=0)
    error_code: str | None = None
    error_type: str | None = None
    model_calls: tuple[dict, ...] = ()


class ResearchStep(Snapshot):
    id: Identifier
    objective: str
    tool_name: str
    arguments: dict
    dependencies: tuple[str, ...] = ()
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"] = "pending"
    result: ToolResult | None = None
    started_at: str | None = None
    finished_at: str | None = None


class ResearchTask(Snapshot):
    schema_version: Literal["research-comparison-v1"] = "research-comparison-v1"
    id: Identifier
    user_id: int = Field(strict=True, gt=0)
    goal: str = Field(min_length=1, max_length=2000)
    index_version_id: Identifier
    corpus_id: Identifier
    sources: tuple[SourceBinding, ...] = Field(min_length=3, max_length=5)
    completion: CompletionSpec
    budget: TaskBudget
    status: Literal["pending", "running", "paused", "completed", "failed", "cancelled"] = "pending"
    revision: int = Field(default=0, strict=True, ge=0)
    steps: tuple[ResearchStep, ...]
    model_calls_used: int = Field(default=0, strict=True, ge=0)
    tool_calls_used: int = Field(default=0, strict=True, ge=0)
    bundles: tuple[BundleRef, ...] = ()
    claims: tuple[Claim, ...] = ()
    relations: tuple[GraphRelation, ...] = ()
    verification: VerificationReport | None = None
    artifact: ComparisonArtifact | None = None
    error_code: str | None = None

    @model_validator(mode="after")
    def consistent_scope(self):
        if len({s.document_id for s in self.sources}) != len(self.sources) or len({s.id for s in self.steps}) != len(self.steps):
            raise ValueError("Duplicate source or step")
        if self.model_calls_used > self.budget.max_model_calls or self.tool_calls_used > self.budget.max_steps:
            raise ValueError("Consumed task budget exceeds its frozen limit")
        return self


def comparison_plan(sources: tuple[SourceBinding, ...], goal: str) -> tuple[ResearchStep, ...]:
    searches, analyses = [], []
    for n, source in enumerate(sources):
        search_id = f"search-{n}"
        searches.append(ResearchStep(id=search_id, objective="定位该论文的方法、数据集、结果与局限",
            tool_name="search_evidence", arguments={"document_id": source.document_id,
                "query": "method model encoder training datasets results evaluation limitations " + goal[:600]}))
        analyses.append(ResearchStep(id=f"analyse-{n}", objective="从原文提取四类候选陈述及有来源的关系",
            tool_name="compare_evidence", arguments={"document_id": source.document_id}, dependencies=(search_id,)))
    verify = ResearchStep(id="verify", objective="逐项检查原文定位与语义支持，标记不足和冲突",
        tool_name="verify_evidence", arguments={}, dependencies=tuple(s.id for s in analyses))
    compose = ResearchStep(id="compose", objective="交付含可核对引用和知识缺口的比较表",
        tool_name="compose_artifact", arguments={}, dependencies=("verify",))
    return tuple(searches + analyses + [verify, compose])
