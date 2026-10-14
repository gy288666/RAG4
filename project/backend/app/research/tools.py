"""Allowlisted read-only tools. No shell, network browsing or model tool calls."""
from dataclasses import dataclass
from time import perf_counter

from pydantic import Field

from app.chunking.models import Identifier, Snapshot
from .artifacts import ArtifactComposer, EvidenceVerifier, extract_claims
from .evidence import EvidenceCorpus, HybridEvidenceEngine, RetrievalOptions
from .graph import Citation, GraphRelation, MemoryGraphStore
from .tasks import BundleRef, ResearchTask, ToolResult
from .protocol import ResponseSchemaError


class SearchArgs(Snapshot):
    document_id: Identifier
    query: str = Field(min_length=1, max_length=4000)


class DocumentArgs(Snapshot):
    document_id: Identifier


class EmptyArgs(Snapshot):
    pass


class RelationDraft(Snapshot):
    evidence_id: Identifier
    quote: str = Field(min_length=1, max_length=1600)
    subject: Identifier
    predicate: str
    object: Identifier


@dataclass(frozen=True)
class ToolContext:
    task: ResearchTask
    corpus: EvidenceCorpus
    engine: HybridEvidenceEngine
    model: object
    assert_fresh: object = None


class ResearchToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name, schema, execute):
        if name in self._tools:
            raise ValueError("A research tool cannot be overwritten")
        self._tools[name] = schema, execute

    def execute(self, name, context, arguments):
        started = perf_counter()
        before = len(getattr(context.model, "calls", []))
        try:
            if name not in self._tools:
                raise ValueError("Unregistered tool")
            schema, execute = self._tools[name]
            result = execute(context, schema.model_validate(arguments))
            return result.model_copy(update={"elapsed_ms": round((perf_counter() - started) * 1000),
                "model_calls": tuple(getattr(context.model, "calls", [])[before:])})
        except Exception as error:
            # Never persist exception messages: providers can include private
            # endpoints, headers or snippets in them. The tool name is recorded.
            return ToolResult(status="failed", error_code="research_tool_failed",
                warnings=error.diagnostics if isinstance(error, ResponseSchemaError) else (),
                error_type=type(error.__cause__ or error).__name__,
                elapsed_ms=round((perf_counter() - started) * 1000),
                model_calls=tuple(getattr(context.model, "calls", [])[before:]))


def _search(context, args):
    context.corpus.require_scope(context.task.user_id, (args.document_id,))
    bundle = context.engine.search(context.task.user_id, args.query, RetrievalOptions(
        document_ids=(args.document_id,), max_context_chars=context.task.budget.max_context_chars))
    return ToolResult(status="succeeded", elapsed_ms=0, data={"bundle": BundleRef.capture(bundle).model_dump(mode="json")},
        evidence_ids=tuple(i.evidence_id for i in bundle.items), warnings=bundle.warnings)


def _analyse(context, args):
    context.corpus.require_scope(context.task.user_id, (args.document_id,))
    ref = next(b for b in context.task.bundles if b.options.document_ids == (args.document_id,))
    bundle = ref.hydrate(context.corpus)
    claims, drafts, warnings = extract_claims(context.model, context.corpus, args.document_id, bundle, context.task.goal)
    items, relations = {i.evidence_id: i for i in bundle.items}, []
    for raw in drafts:
        try:
            draft = RelationDraft.model_validate(raw)
            item = items[draft.evidence_id]
            if item.chunk.text.count(draft.quote) != 1:
                raise ValueError("Ambiguous relation quote")
            start = item.chunk.text.index(draft.quote)
            relation = GraphRelation(relation_id="pending", document_id=args.document_id,
                subject=draft.subject, predicate=draft.predicate, object=draft.object,
                citation=Citation(chunk_id=item.chunk.chunk_id, char_start=start, char_end=start + len(draft.quote), quote=draft.quote))
            relation = relation.model_copy(update={"relation_id": relation.expected_id(context.corpus.corpus_id)})
            MemoryGraphStore().replace_document(context.task.user_id, args.document_id, (relation,), context.corpus)
            if relation.relation_id not in {r.relation_id for r in relations}:
                relations.append(relation)
        except (ValueError, KeyError):
            warnings += ("draft_relation_rejected",)
    return ToolResult(status="succeeded", elapsed_ms=0,
        data={"claims": [c.model_dump(mode="json") for c in claims], "relations": [r.model_dump(mode="json") for r in relations]},
        evidence_ids=tuple(i.evidence_id for i in bundle.items), warnings=warnings + ("graph_relations_are_source_backed_hypotheses",))


def _verify(context, args):
    report = EvidenceVerifier(context.model).verify(context.corpus, context.task.claims)
    return ToolResult(status="succeeded", elapsed_ms=0, data={"verification": report.model_dump(mode="json")}, warnings=report.warnings)


def _compose(context, args):
    if context.task.verification is None:
        raise ValueError("Verification required before composition")
    artifact = ArtifactComposer().compose(context.corpus, context.task.goal,
        tuple(s.document_id for s in context.task.sources), {s.document_id: s.title for s in context.task.sources},
        context.task.claims, context.task.verification)
    return ToolResult(status="succeeded", elapsed_ms=0, data={"artifact": artifact.model_dump(mode="json")}, warnings=artifact.warnings)


def comparison_tools():
    registry = ResearchToolRegistry()
    for name, schema, execute in (("search_evidence", SearchArgs, _search), ("compare_evidence", DocumentArgs, _analyse),
        ("verify_evidence", EmptyArgs, _verify), ("compose_artifact", EmptyArgs, _compose)):
        registry.register(name, schema, execute)
    return registry
