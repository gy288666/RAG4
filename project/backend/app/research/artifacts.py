"""Exact-source gates, explicit machine judgments and conservative comparison.

Literal citation validation does not prove semantic entailment. A separate model
judge is mandatory, uncertainty fails closed, and human support is never claimed.
"""
from __future__ import annotations

import html
import re
import unicodedata
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import Field, model_serializer

from app.chunking.models import Identifier, Snapshot, SourceLocator, SourceSpan, content_id
from .evidence import EvidenceBundle, EvidenceCorpus
from .graph import Citation
from .protocol import validate_response

Facet = Literal["method", "dataset", "result", "limitation"]
FACETS = ("method", "dataset", "result", "limitation")
FACET_LABELS = {"method": "方法", "dataset": "数据集", "result": "结果", "limitation": "局限"}


class ResearchModel(Protocol):
    def generate(self, operation: str, payload: dict) -> dict: ...


class Claim(Snapshot):
    claim_id: Identifier
    document_id: Identifier
    facet: Facet
    statement: str = Field(min_length=1, max_length=1000)
    citation: Citation

    def expected_id(self, corpus_id):
        return content_id("claim_", {"corpus_id": corpus_id, **self.model_dump(mode="json", exclude={"claim_id"})})


class QuotedClaim(Snapshot):
    facet: Facet
    statement: str = Field(min_length=1, max_length=1000)
    evidence_id: Identifier
    quote: str = Field(min_length=1, max_length=1600)


class AnalysisDraft(Snapshot):
    claims: tuple[QuotedClaim, ...] = Field(default=(), max_length=4)
    # Draft relations require exact mentions in an available quote. They are
    # graph retrieval hints, not verified statements in the final artifact.
    relations: tuple[dict, ...] = Field(default=(), max_length=8)


class CitedClaim(Snapshot):
    facet: Facet
    statement: str = Field(min_length=1, max_length=1000)
    citation_id: Identifier


class CitedRelation(Snapshot):
    citation_id: Identifier
    subject: Identifier
    predicate: Literal["uses", "evaluates_on", "reports", "contrasts", "limits"]
    object: Identifier


class CitedAnalysisDraft(Snapshot):
    # Bound wire candidates separately from the four-facet domain output.
    # A duplicated facet must not discard valid candidates for other facets.
    claims: tuple[CitedClaim, ...] = Field(default=(), max_length=8)
    relations: tuple[CitedRelation, ...] = Field(default=(), max_length=2)


class Verdict(Snapshot):
    claim_id: Identifier
    status: Literal["supported", "contradicted", "insufficient"]
    reason: str = Field(min_length=1, max_length=400)


class Judgment(Snapshot):
    verdicts: tuple[Verdict, ...] = Field(max_length=20)


class SourceCheck(Snapshot):
    """A model judgment with an independently checked literal support excerpt."""
    status: Literal["supported", "contradicted", "insufficient"]
    reason: str = Field(min_length=1, max_length=200)
    support_quote: str = Field(max_length=1600)
    support_ids: tuple[Identifier, ...] = Field(default=(), max_length=4)

    @model_serializer(mode="wrap")
    def preserve_quote_protocol(self, handler):
        payload = handler(self)
        if not self.support_ids:
            payload.pop("support_ids", None)
        return payload


class ClaimAssessment(Snapshot):
    claim_id: Identifier
    attribution: SourceCheck
    conditions: SourceCheck
    entailment: SourceCheck

    def verdict(self, claim):
        failures = []
        contradicted = False
        for name in ("attribution", "conditions", "entailment"):
            check = getattr(self, name)
            grounded = bool(check.support_quote.strip()) and check.support_quote in claim.citation.quote
            if check.support_ids:
                grounded = grounded and resolve_support(claim, check.support_ids) == check.support_quote
            if check.status != "supported" or not grounded:
                failures.append(name + ":" + (check.reason if grounded or check.status == "insufficient" else "support_excerpt_not_in_quote"))
                contradicted |= grounded and check.status == "contradicted"
        return Verdict(claim_id=self.claim_id,
            status=("contradicted" if contradicted else "insufficient") if failures else "supported",
            reason="; ".join(failures)[:400] if failures else "all_source_checks_supported")


class CheckedJudgment(Snapshot):
    assessments: tuple[ClaimAssessment, ...] = Field(max_length=20)


def verification_sources(claim):
    """Disjoint exact quote windows; IDs bind claim, citation and local offsets.

    No additional retrieval or normalized text. Keep table line groups intact
    where possible, preferring paragraph boundaries over arbitrary character cuts.
    """
    sources, start, text = [], 0, claim.citation.quote
    while start < len(text):
        end = min(start + 800, len(text))
        if end < len(text):
            breaks = [m.end() for m in re.finditer(r"\n\s*\n|[.!?。！？](?:\s+|$)", text[start:end])]
            if breaks and breaks[-1] >= 400:
                end = start + breaks[-1]
        identity = content_id("support_", {"protocol": "source-handles-v4", "claim_id": claim.claim_id,
            "citation": claim.citation.model_dump(mode="json"), "start": start, "end": end})
        sources.append({"source_id": identity, "start": start, "end": end, "text": text[start:end]})
        start = end
    return tuple(sources)


def resolve_support(claim, support_ids):
    """Resolve an enclosing original interval; never concatenate distant quotes."""
    catalog = {s["source_id"]: s for s in verification_sources(claim)}
    if not support_ids or len(set(support_ids)) != len(support_ids) or any(i not in catalog for i in support_ids):
        return None
    start = min(catalog[i]["start"] for i in support_ids)
    end = max(catalog[i]["end"] for i in support_ids)
    return claim.citation.quote[start:end] if end - start <= 1600 else None


class HandleCheck(Snapshot):
    status: Literal["supported", "contradicted", "insufficient"]
    reason: str = Field(min_length=1, max_length=200)
    support_ids: tuple[Identifier, ...] = Field(max_length=4)

    def resolve(self, claim):
        text = resolve_support(claim, self.support_ids)
        if text is None:
            reason = "no_support_selected" if not self.support_ids else "unknown_support_id_or_invalid_span"
            return SourceCheck(status="insufficient", reason=(reason + ": " + self.reason)[:200],
                support_quote="", support_ids=self.support_ids)
        return SourceCheck(status=self.status, reason=self.reason, support_quote=text, support_ids=self.support_ids)


class HandleAssessment(Snapshot):
    claim_id: Identifier
    attribution: HandleCheck
    conditions: HandleCheck
    entailment: HandleCheck

    def resolve(self, claim):
        return ClaimAssessment(claim_id=self.claim_id, **{name: getattr(self, name).resolve(claim)
            for name in ("attribution", "conditions", "entailment")})


class HandleJudgment(Snapshot):
    assessments: tuple[HandleAssessment, ...] = Field(max_length=20)


class VerificationReport(Snapshot):
    verifier_version: Literal["exact-source-and-model-v1", "exact-source-numeric-and-model-v2", "exact-source-checks-v3", "exact-source-handles-v4"] = "exact-source-numeric-and-model-v2"
    annotation_status: Literal["machine_review_only"] = "machine_review_only"
    verdicts: tuple[Verdict, ...]
    supported: int
    total: int
    warnings: tuple[str, ...] = ()
    assessments: tuple[ClaimAssessment, ...] = ()

    @model_serializer(mode="wrap")
    def preserve_historical_wire_format(self, handler):
        payload = handler(self)
        if self.verifier_version not in {"exact-source-checks-v3", "exact-source-handles-v4"}:
            payload.pop("assessments", None)
        return payload


def _quote_matches(text: str, quote: str):
    """Match only Unicode typography and whitespace equivalence, uniquely.

    Does not change words, case, punctuation or hyphenation. Returns original
    character offsets, so persisted citations contain exact original text.
    """
    chars, offsets = [], []
    for n, char in enumerate(text):
        normalized = unicodedata.normalize("NFKC", char)
        chars.append(normalized)
        offsets.extend([n] * len(normalized))
    words = unicodedata.normalize("NFKC", quote).split()
    if not words:
        return ()
    matches = list(re.finditer(r"\s+".join(re.escape(w) for w in words), "".join(chars)))
    return tuple((offsets[m.start()], offsets[m.end() - 1] + 1) for m in matches)


def locate_quote(text: str, quote: str):
    matches = _quote_matches(text, quote)
    return matches[0] if len(matches) == 1 else None


def citation_catalog(bundle: EvidenceBundle):
    """Contiguous, disjoint source excerpts. No new retrieval or extra context.

    Up to 1600 characters per excerpt; prefer paragraph/sentence boundaries.
    Offsets, rather than model-copied text, determine the persisted citation.
    """
    result = {}
    for item in bundle.items:
        text, start = item.chunk.text, 0
        while start < len(text):
            end = min(start + 1600, len(text))
            if end < len(text):
                boundaries = [m.end() for m in re.finditer(r"\n\s*\n|[.!?。！？](?:\s+|$)", text[start:end])]
                if boundaries and boundaries[-1] >= 800:
                    end = start + boundaries[-1]
            citation_id = content_id("cite_", {"protocol": "source-handles-v2", "corpus_id": bundle.corpus_id,
                "chunk_set_id": item.chunk_set_id, "chunk_id": item.chunk.chunk_id, "start": start, "end": end})
            result[citation_id] = (item, start, end)
            start = end
    return result


def _numbers(text):
    # Numeric components of model names (T5, BERT-base) are not experimental
    # values. Decimal normalization treats 52 and 52.0 as equivalent; no unit
    # conversion, rounding or inferred arithmetic is accepted.
    normalized = unicodedata.normalize("NFKC", text)
    values = re.findall(r"(?<![A-Za-z0-9_.])[+-]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][+-]?\d+)?(?![A-Za-z0-9_.])", normalized)
    return {Decimal(value.replace(",", "")) for value in values}


def extract_claims(model: ResearchModel, corpus: EvidenceCorpus, document_id: str, bundle: EvidenceBundle, goal: str):
    if (bundle.corpus_id != corpus.corpus_id or bundle.user_id != corpus.user_id
            or bundle.bundle_id != bundle.expected_id()):
        raise ValueError("Bundle snapshot mismatch")
    for item in bundle.items:
        corpus.validate_item(item)
        if item.chunk.document_id != document_id:
            raise ValueError("Analysis evidence is outside the selected document")
    if getattr(model, "extraction_protocol", "literal-quote-v1") == "source-handles-v2":
        return _extract_cited(model, corpus, document_id, bundle, goal)
    draft = validate_response(AnalysisDraft, model.generate("extract", {
        "goal": goal, "document_id": document_id, "facets": list(FACETS),
        "evidence": [{"evidence_id": i.evidence_id, "text": i.chunk.text} for i in bundle.items]}), "extract")
    items = {i.evidence_id: i for i in bundle.items}
    claims, warnings = [], []
    seen = set()
    for candidate in draft.claims:
        item = items.get(candidate.evidence_id)
        matches = _quote_matches(item.chunk.text, candidate.quote) if item is not None else ()
        location = matches[0] if len(matches) == 1 else None
        if location is None or candidate.facet in seen:
            warnings.append("draft_claim_rejected:" + candidate.facet)
            reason = "unknown_evidence" if item is None else "duplicate_facet" if candidate.facet in seen else "ambiguous_quote" if len(matches) > 1 else "quote_not_found"
            warnings.append("draft_claim_rejected:" + candidate.facet + ":" + reason)
            continue
        start, end = location
        claim = Claim(claim_id="pending", document_id=document_id, facet=candidate.facet,
            statement=candidate.statement, citation=Citation(chunk_id=item.chunk.chunk_id,
                char_start=start, char_end=end, quote=item.chunk.text[start:end]))
        claims.append(claim.model_copy(update={"claim_id": claim.expected_id(corpus.corpus_id)}))
        seen.add(candidate.facet)
    return tuple(claims), draft.relations, tuple(warnings)


def _extract_cited(model, corpus, document_id, bundle, goal):
    catalog = citation_catalog(bundle)
    draft = validate_response(CitedAnalysisDraft, model.generate("extract_cited", {
        "goal": goal, "document_id": document_id, "facets": list(FACETS),
        "citations": [{"citation_id": key, "text": item.chunk.text[start:end]}
            for key, (item, start, end) in catalog.items()]}), "extract_cited")
    claims, relations, warnings, seen = [], [], [], set()
    if len(draft.claims) > 4:
        warnings.append(f"candidate_claim_count:{len(draft.claims)}")
    for candidate in draft.claims:
        if candidate.citation_id not in catalog or candidate.facet in seen:
            reason = "unknown_citation" if candidate.citation_id not in catalog else "duplicate_facet"
            warnings.append(f"draft_claim_rejected:{candidate.facet}:{reason}")
            continue
        item, start, end = catalog[candidate.citation_id]
        claim = Claim(claim_id="pending", document_id=document_id, facet=candidate.facet, statement=candidate.statement,
            citation=Citation(chunk_id=item.chunk.chunk_id, char_start=start, char_end=end, quote=item.chunk.text[start:end]))
        claims.append(claim.model_copy(update={"claim_id": claim.expected_id(corpus.corpus_id)}))
        seen.add(candidate.facet)
    for relation in draft.relations:
        if relation.citation_id not in catalog:
            warnings.append("draft_relation_rejected:unknown_citation")
            continue
        item, start, end = catalog[relation.citation_id]
        relations.append({"evidence_id": item.evidence_id, "quote": item.chunk.text[start:end],
            **relation.model_dump(exclude={"citation_id"})})
    return tuple(claims), tuple(relations), tuple(warnings)


class EvidenceVerifier:
    def __init__(self, model: ResearchModel):
        self.model = model

    def verify(self, corpus: EvidenceCorpus, claims: tuple[Claim, ...]) -> VerificationReport:
        if len(claims) > 20 or len({c.claim_id for c in claims}) != len(claims):
            raise ValueError("Invalid verification scope")
        protocol = getattr(self.model, "verification_protocol", "numeric-model-v2")
        if protocol not in {"numeric-model-v2", "source-checks-v3", "source-handles-v4"}:
            raise ValueError("Unknown verification protocol")
        handles = protocol == "source-handles-v4"
        checked = protocol in {"source-checks-v3", "source-handles-v4"}
        valid, invalid, assessments = [], [], ()
        for claim in claims:
            try:
                claim.citation.validate_source(corpus, claim.document_id)
                if claim.claim_id != claim.expected_id(corpus.corpus_id):
                    raise ValueError("Claim identity mismatch")
                if not _numbers(claim.statement) <= _numbers(claim.citation.quote):
                    invalid.append(Verdict(claim_id=claim.claim_id, status="insufficient", reason="numeric_value_not_in_quote"))
                    continue
                valid.append(claim)
            except ValueError:
                invalid.append(Verdict(claim_id=claim.claim_id, status="insufficient", reason="source_integrity_failed"))
        if valid:
            payload = {"claims": [
                {"claim_id": c.claim_id, "statement": c.statement, "quote": c.citation.quote,
                 "document_id": c.document_id, "facet": c.facet,
                 "source_uri": corpus.chunks[c.citation.chunk_id].source_locator.source.uri,
                 "section_path": corpus.chunks[c.citation.chunk_id].section_path,
                 "context": corpus.chunks[c.citation.chunk_id].text} for c in valid]}
            if checked:
                claims_by_id = {c.claim_id: c for c in valid}
                operation = "verify_handles" if handles else "verify_checked"
                if handles:
                    for item in payload["claims"]:
                        item["sources"] = verification_sources(claims_by_id[item["claim_id"]])
                        del item["quote"]  # One authoritative source catalog, no copied quote required.
                assessments = validate_response(HandleJudgment if handles else CheckedJudgment,
                    self.model.generate(operation, payload), operation).assessments
                if len({a.claim_id for a in assessments}) != len(assessments) or any(a.claim_id not in claims_by_id for a in assessments):
                    raise ValueError("Judge returned duplicate or unknown claim IDs")
                if handles:
                    assessments = tuple(a.resolve(claims_by_id[a.claim_id]) for a in assessments)
                judged = Judgment(verdicts=tuple(a.verdict(claims_by_id[a.claim_id]) for a in assessments))
            else:
                judged = validate_response(Judgment, self.model.generate("verify", payload), "verify")
            ids = {c.claim_id for c in valid}
            if len({v.claim_id for v in judged.verdicts}) != len(judged.verdicts) or any(v.claim_id not in ids for v in judged.verdicts):
                raise ValueError("Judge returned duplicate or unknown claim IDs")
            mapping = {v.claim_id: v for v in judged.verdicts}
            verdicts = invalid + [mapping.get(c.claim_id, Verdict(claim_id=c.claim_id,
                status="insufficient", reason="judge_did_not_verify_claim")) for c in valid]
        else:
            verdicts = invalid
        return VerificationReport(verifier_version="exact-source-handles-v4" if handles else "exact-source-checks-v3" if checked else "exact-source-numeric-and-model-v2",
            assessments=assessments, verdicts=tuple(verdicts), supported=sum(v.status == "supported" for v in verdicts),
            total=len(claims), warnings=("literal_numeric_values_checked_no_unit_conversion",
                "semantic_support_is_machine_judgment_requires_human_review"))


class ComparisonCell(Snapshot):
    facet: Facet
    status: Literal["supported", "missing", "uncertain", "conflict"]
    statement: str | None = None
    claim_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


class ComparisonRow(Snapshot):
    document_id: Identifier
    title: str
    cells: tuple[ComparisonCell, ...]


class ArtifactSource(Snapshot):
    claim_id: Identifier
    chunk_set_id: Identifier
    source_locator: SourceLocator
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None


def _quote_source(corpus, claim):
    """Map a quote's chunk offsets to original block offsets, excluding joins."""
    chunk = corpus.chunks[claim.citation.chunk_id]
    spans = chunk.source_locator.spans
    if len(chunk.text) != sum(s.char_end - s.char_start for s in spans) + 2 * (len(spans) - 1):
        raise ValueError("Source span layout cannot be mapped exactly")
    position, clipped = 0, []
    for span in spans:
        width = span.char_end - span.char_start
        left, right = max(position, claim.citation.char_start), min(position + width, claim.citation.char_end)
        if left < right:
            clipped.append(SourceSpan(block_id=span.block_id, char_start=span.char_start + left - position,
                char_end=span.char_start + right - position, page_start=span.page_start, page_end=span.page_end))
        position += width + 2
    if not clipped:
        raise ValueError("Quote must contain source text rather than only block separators")
    pages_start = [s.page_start for s in clipped if s.page_start is not None]
    pages_end = [s.page_end for s in clipped if s.page_end is not None]
    return ArtifactSource(claim_id=claim.claim_id, chunk_set_id=corpus.set_ids[chunk.chunk_id],
        source_locator=SourceLocator(source=chunk.source_locator.source, spans=tuple(clipped)), section_path=chunk.section_path,
        page_start=min(pages_start) if pages_start else None, page_end=max(pages_end) if pages_end else None)


class ComparisonArtifact(Snapshot):
    artifact_id: Identifier
    composer_version: Literal["comparison-table-v1", "comparison-table-v2"] = "comparison-table-v2"
    completion_status: Literal["partial", "ready_for_review"] = "partial"
    corpus_id: Identifier
    goal: str
    rows: tuple[ComparisonRow, ...]
    citations: tuple[Claim, ...]
    citation_sources: tuple[ArtifactSource, ...] = ()
    verification: VerificationReport
    knowledge_gaps: tuple[str, ...]
    warnings: tuple[str, ...]
    markdown: str

    def expected_id(self):
        excluded = {"artifact_id"}
        if self.composer_version == "comparison-table-v1":
            excluded.add("completion_status")
            excluded.add("citation_sources")
        payload = self.model_dump(mode="json", exclude=excluded)
        if self.verification.verifier_version not in {"exact-source-checks-v3", "exact-source-handles-v4"}:
            payload["verification"].pop("assessments", None)
        return content_id("artifact_", payload)


def _escape(text):
    return html.escape(text, quote=False).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


class ArtifactComposer:
    """Renders only verified claims, without an additional generative pass.

    No overall numerical ranking: comparable datasets, readers, hardware and
    evaluation conditions are not inferred from independent result statements.
    """
    def compose(self, corpus, goal, document_ids, titles, claims, verification):
        corpus.require_scope(corpus.user_id, document_ids)
        if verification.verifier_version not in {"exact-source-numeric-and-model-v2", "exact-source-checks-v3", "exact-source-handles-v4"}:
            raise ValueError("Historical verifier results must be reverified before composing a new artifact")
        verdicts = {v.claim_id: v for v in verification.verdicts}
        if len(verdicts) != len(verification.verdicts) or set(verdicts) != {c.claim_id for c in claims}:
            raise ValueError("Verification does not cover exactly the supplied claims")
        if verification.total != len(claims) or verification.supported != sum(v.status == "supported" for v in verdicts.values()):
            raise ValueError("Verification counters mismatch")
        if verification.verifier_version in {"exact-source-checks-v3", "exact-source-handles-v4"}:
            assessments = {a.claim_id: a for a in verification.assessments}
            if len(assessments) != len(verification.assessments) or not set(assessments) <= set(verdicts):
                raise ValueError("Invalid verification assessments")
            for claim in claims:
                assessment = assessments.get(claim.claim_id)
                if verdicts[claim.claim_id].status == "supported" and (assessment is None or assessment.verdict(claim).status != "supported"):
                    raise ValueError("Supported claim failed source checks")
                if verification.verifier_version == "exact-source-handles-v4" and verdicts[claim.claim_id].status == "supported":
                    if any(not getattr(assessment, name).support_ids for name in ("attribution", "conditions", "entailment")):
                        raise ValueError("Supported claim missing source handles")
        for c in claims:
            c.citation.validate_source(corpus, c.document_id)
            if c.document_id not in document_ids or c.claim_id != c.expected_id(corpus.corpus_id):
                raise ValueError("Artifact claim outside frozen scope")
            if verdicts[c.claim_id].status == "supported" and not _numbers(c.statement) <= _numbers(c.citation.quote):
                raise ValueError("Supported claim failed numerical source gate")
        rows, gaps, cited = [], [], []
        for d in document_ids:
            cells = []
            for facet in FACETS:
                candidates = [c for c in claims if c.document_id == d and c.facet == facet]
                supported = [c for c in candidates if verdicts[c.claim_id].status == "supported"]
                conflicting = any(verdicts[c.claim_id].status == "contradicted" for c in candidates) or len({c.statement for c in supported}) > 1
                if supported and not conflicting:
                    c = supported[0]
                    cell = ComparisonCell(facet=facet, status="supported", statement=c.statement, claim_ids=(c.claim_id,))
                    cited.append(c)
                else:
                    status = "conflict" if conflicting else "uncertain" if candidates else "missing"
                    reasons = tuple(verdicts[c.claim_id].reason for c in candidates) or ("retrieved_evidence_insufficient_not_proof_paper_omits_field",)
                    cell = ComparisonCell(facet=facet, status=status, reasons=reasons)
                    gaps.append(f"{d}:{facet}:{status}")
                cells.append(cell)
            rows.append(ComparisonRow(document_id=d, title=titles[d], cells=tuple(cells)))
        sources = tuple(_quote_source(corpus, c) for c in cited)
        source_by_claim = {s.claim_id: s for s in sources}
        references = {c.claim_id: n + 1 for n, c in enumerate(cited)}
        lines = ["# 文献比较", "", _escape(goal), "", "| 文献 | 方法 | 数据集 | 结果 | 局限 |", "| --- | --- | --- | --- | --- |"]
        labels = {"missing": "证据未检出", "uncertain": "待核验", "conflict": "证据冲突"}
        for row in rows:
            values = [_escape(row.title)] + [(_escape(c.statement) + f" [{references[c.claim_ids[0]]}]")
                if c.status == "supported" else labels[c.status] for c in row.cells]
            lines.append("| " + " | ".join(values) + " |")
        lines.extend(["", "引用由原文定位及模型核验；仍需人工复核。实验条件未统一，本表不作性能排名。", "", "引用："])
        for c in cited:
            chunk = corpus.chunks[c.citation.chunk_id]
            source = source_by_claim[c.claim_id]
            page = f"{source.page_start}–{source.page_end}" if source.page_start is not None else "未知"
            lines.append(f"[{references[c.claim_id]}] {_escape(titles[c.document_id])}，PDF 页 {page}，切片 {chunk.chunk_id}，字符 {c.citation.char_start}:{c.citation.char_end}：{_escape(c.citation.quote)}")
        lines.extend(["", "知识缺口："] + [_escape(g) for g in gaps])
        artifact = ComparisonArtifact(artifact_id="pending", corpus_id=corpus.corpus_id, goal=goal,
            completion_status="partial" if gaps else "ready_for_review",
            rows=tuple(rows), citations=tuple(cited), citation_sources=sources, verification=verification, knowledge_gaps=tuple(gaps),
            warnings=("machine_review_only", "cross_paper_results_not_directly_comparable"), markdown="\n".join(lines) + "\n")
        return artifact.model_copy(update={"artifact_id": artifact.expected_id()})
