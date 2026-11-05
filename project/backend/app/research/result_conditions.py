"""Conservative literal row-condition auditing, independent of model judgment.

Only vertical rows (label, then numeric lines) with complete parenthesized
symbol=named-value assignments are recognized. Other layouts stay unknown.
This does not certify dataset/metric alignment, units or semantic entailment.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import re
import unicodedata
from typing import Literal, TYPE_CHECKING

from pydantic import Field
from app.chunking.models import Identifier, Snapshot, content_id
from .graph import Citation

if TYPE_CHECKING:
    from .artifacts import Claim
    from .evidence import EvidenceCorpus

ResultConditionPolicy = Literal['model-only-v1', 'explicit-row-v1']
_NUMBER = r'[+-]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][+-]?\d+)?'
_CELL = re.compile(_NUMBER+r'%?\Z')
_MEASURE = re.compile(r'(?<![A-Za-z0-9_.@])'+_NUMBER+r'(?![A-Za-z0-9_]|\.\d)')
_ASSIGN = re.compile(r'\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*([A-Za-z][A-Za-z0-9_.-]*(?: [A-Za-z0-9_.-]+)*)\s*\Z')


class ConditionAssignment(Snapshot):
    """A literal named row condition; no model-inferred alias or default."""
    symbol: str = Field(min_length=1, max_length=64)
    value: Citation


class ExperimentRow(Snapshot):
    row_id: Identifier
    selector_version: Literal['vertical-assignment-row-v1'] = 'vertical-assignment-row-v1'
    corpus_id: Identifier
    document_id: Identifier
    source: Citation
    label: Citation
    values: tuple[Citation, ...] = Field(min_length=1, max_length=32)
    conditions: tuple[ConditionAssignment, ...] = Field(default=(), max_length=16)
    qualifiers_complete: bool

    def expected_id(self):
        return content_id('resultrow_', self.model_dump(mode='json', exclude={'row_id'}))


class ResultConditionAudit(Snapshot):
    audit_id: Identifier
    policy: Literal['explicit-row-v1'] = 'explicit-row-v1'
    corpus_id: Identifier
    claim_id: Identifier
    status: Literal['passed', 'missing', 'unknown', 'not_applicable']
    reason: str
    row: ExperimentRow | None = None
    missing_conditions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ('literal_row_assignments_only_not_semantic_proof',)

    def expected_id(self):
        return content_id('conditionaudit_', self.model_dump(mode='json', exclude={'audit_id'}))

    def validate_source(self, corpus: EvidenceCorpus, claim: Claim):
        if self != audit_result_conditions(corpus, claim):
            raise ValueError('Result condition audit differs from frozen source or claim')


def _decimal(text):
    return Decimal(text.rstrip('%').replace(',', ''))


def _cite(claim, start, end):
    return Citation(chunk_id=claim.citation.chunk_id,
                    char_start=claim.citation.char_start+start, char_end=claim.citation.char_start+end,
                    quote=claim.citation.quote[start:end])


def _rows(corpus, claim):
    lines, position = [], 0
    for raw in claim.citation.quote.splitlines(keepends=True):
        text = raw.strip()
        start = position+len(raw)-len(raw.lstrip())
        lines.append((text, start, start+len(text)))
        position += len(raw)
    rows = []
    for i, (label, left, right) in enumerate(lines):
        if not label or _CELL.fullmatch(label):
            continue
        values, j = [], i+1
        while j < len(lines) and _CELL.fullmatch(lines[j][0]):
            values.append(_cite(claim, lines[j][1], lines[j][2])); j += 1
        if not values or len(values) > 32:
            continue
        conditions, complete = [], True
        for group in re.finditer(r'\(([^()\n]*)\)', label):
            if '=' not in group[1]:
                continue
            cursor = group.start(1)
            for piece in group[1].split(','):
                assignment = _ASSIGN.fullmatch(piece)
                if assignment is None:
                    complete = False
                else:
                    start, end = assignment.span(2)
                    conditions.append(ConditionAssignment(symbol=assignment[1], value=_cite(claim, left+cursor+start, left+cursor+end)))
                cursor += len(piece)+1
        # Every explicit assignment must be parsed; never retain only a subset.
        if '=' in label and (not conditions or len(conditions) != label.count('=')):
            complete = False
        if len(conditions)>16:
            continue
        row = ExperimentRow(row_id='pending', corpus_id=corpus.corpus_id, document_id=claim.document_id,
                            source=_cite(claim,left,values[-1].char_end-claim.citation.char_start),
                            label=_cite(claim,left,right), values=tuple(values), conditions=tuple(conditions),
                            qualifiers_complete=complete)
        rows.append(row.model_copy(update={'row_id':row.expected_id()}))
    return rows


def _occurrence(statement, value):
    statement = unicodedata.normalize('NFKC', statement).casefold()
    value = unicodedata.normalize('NFKC', value).casefold()
    matches = list(re.finditer(r'(?<![a-z0-9_.-])'+re.escape(value)+r'(?![a-z0-9_-]|\.[a-z0-9])',statement))
    if not matches:
        return 'missing'
    for match in matches:
        before, after = statement[max(0,match.start()-24):match.start()], statement[match.end():match.end()+8]
        if (re.search(r'(?:\b(?:not|no|without|except|excluding)\b|不|未|非|没有|排除)[^,，。;；]{0,16}$',before)
                or re.match(r'\s*(?:并非|不是|除外|不适用)',after)):
            return 'uncertain'
    return 'present'


def audit_result_conditions(corpus: EvidenceCorpus, claim: Claim) -> ResultConditionAudit:
    """Deterministic, side-effect-free, bounded to one exact <=4000-char quote.

    One uniquely matching numeric row and all its explicit assignment values
    are required. Passing this gate does not replace the semantic verifier.
    Invalid provenance raises; unsupported layouts/ambiguous rows stay unknown.
    """
    claim.citation.validate_source(corpus, claim.document_id)
    if claim.claim_id != claim.expected_id(corpus.corpus_id):
        raise ValueError('Condition audit claim identity mismatch')
    def result(status, reason, row=None, missing=()):
        audit = ResultConditionAudit(audit_id='pending',corpus_id=corpus.corpus_id,claim_id=claim.claim_id,
                                     status=status,reason=reason,row=row,missing_conditions=missing)
        return audit.model_copy(update={'audit_id':audit.expected_id()})
    numbers = Counter(_decimal(m[0]) for m in _MEASURE.finditer(unicodedata.normalize('NFKC',claim.statement)))
    if claim.facet=='result' and not numbers and re.search(r'(?<![A-Za-z0-9_@])\d',unicodedata.normalize('NFKC',claim.statement)):
        return result('unknown','numeric_notation_unsupported')
    if claim.facet!='result' or not numbers:
        return result('not_applicable','not_a_numeric_result')
    candidates = [row for row in _rows(corpus,claim) if numbers<=Counter(_decimal(v.quote) for v in row.values)]
    if len(candidates)!=1:
        return result('unknown','ambiguous_numeric_rows' if candidates else 'numeric_row_not_located')
    row = candidates[0]
    if not row.qualifiers_complete or not row.conditions:
        return result('unknown','explicit_assignments_unavailable',row)
    occurrences = [(c.value.quote,_occurrence(claim.statement,c.value.quote)) for c in row.conditions]
    missing = tuple(dict.fromkeys(value for value,state in occurrences if state=='missing'))
    if missing:
        return result('missing','explicit_row_condition_omitted',row,missing)
    if any(state=='uncertain' for _,state in occurrences):
        return result('unknown','condition_occurrence_not_affirmed',row)
    normalized=unicodedata.normalize('NFKC',claim.statement).casefold()
    for condition in row.conditions:
        stated=re.search(r'\b'+re.escape(condition.symbol.casefold())+r'\s*=\s*([a-z][a-z0-9_.-]*)',normalized)
        if stated and stated[1]!=condition.value.quote.casefold():
            return result('unknown','explicit_condition_assignment_differs',row)
    return result('passed','all_explicit_row_assignments_retained',row)
