"""Real failure regression and exact-source condition checks, no model calls."""
import json
from pathlib import Path

import pytest

from app.research.artifacts import Claim
from app.research.graph import Citation
from app.research.result_conditions import audit_result_conditions
from test_research_evidence import corpus_for


def example(statement=None, text=None):
    if text is None:
        record=json.loads((Path(__file__).resolve().parents[1]/'evaluation/results/research_context_e2e_20261101.json').read_text(encoding='utf-8'))
        original=next(c for c in record['claims'] if c['document_id']=='realm' and c['facet']=='result')
        text=original['citation']['quote']
        if statement is None:statement=original['statement']
    corpus=corpus_for(text,parent_size=2000,child_size=1800)
    chunk=corpus.chunk_sets['d0'].child_chunks[0]
    assert chunk.text==text
    claim=Claim(claim_id='pending',document_id='d0',facet='result',statement=statement,
                citation=Citation(chunk_id=chunk.chunk_id,char_start=0,char_end=len(text),quote=text))
    return corpus,claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})


def test_actual_r33_table_requires_cc_news_despite_matching_numbers():
    corpus,claim=example()
    audit=audit_result_conditions(corpus,claim)
    assert audit.status=='missing' and audit.missing_conditions==('CC-News',)
    assert audit.row.label.quote=='REALM (X = CC-News)'
    assert [v.quote for v in audit.row.values]==['38.5','52.0']


def test_complete_condition_is_only_a_condition_pass_and_is_source_bound():
    corpus,claim=example('在NQ开发集，使用CC-News预训练的REALM达到EM 38.5与Recall@5 52.0。')
    audit=audit_result_conditions(corpus,claim)
    assert audit.status=='passed'
    audit.validate_source(corpus,claim)
    assert audit.audit_id==audit.expected_id()
    for citation in (audit.row.source,audit.row.label,*audit.row.values,*(c.value for c in audit.row.conditions)):
        citation.validate_source(corpus,'d0')


@pytest.mark.parametrize('statement',[
    'REALM没有使用CC-News，EM 38.5，Recall@5 52.0。',
    'REALM without CC-News achieves 38.5 and 52.0.',
    'REALM uses CC-NewsExtra and achieves 38.5 and 52.0.',
])
def test_negation_or_substring_cannot_satisfy_a_condition(statement):
    corpus,claim=example(statement)
    assert audit_result_conditions(corpus,claim).status!='passed'


def test_duplicate_rows_are_unknown_instead_of_selecting_first():
    text='Model (X = CorpusA)\n38.5\n52.0\nModel (X = CorpusB)\n38.5\n52.0'
    corpus,claim=example('CorpusA yields 38.5 and 52.0.',text)
    audit=audit_result_conditions(corpus,claim)
    assert audit.status=='unknown' and audit.reason=='ambiguous_numeric_rows'


@pytest.mark.parametrize('text',[
    'Model (X = CorpusA, unspecified qualifier)\n38.5\n52.0',
    'Model\n38.5\n52.0',
    'Model achieves 38.5 and 52.0 in prose.',
])
def test_unparsed_or_absent_conditions_are_unknown(text):
    corpus,claim=example('Model using CorpusA achieves 38.5 and 52.0.',text)
    assert audit_result_conditions(corpus,claim).status=='unknown'


def test_non_numeric_result_does_not_require_a_numeric_row():
    corpus,claim=example('The paper reports state of the art.','The paper reports state of the art.')
    assert audit_result_conditions(corpus,claim).status=='not_applicable'


def test_forged_source_offsets_and_stale_statement_are_rejected():
    corpus,claim=example('CC-News: 38.5 and 52.0.')
    audit=audit_result_conditions(corpus,claim)
    bad=audit.model_copy(update={'audit_id':'forged'})
    with pytest.raises(ValueError):bad.validate_source(corpus,claim)
    with pytest.raises(ValueError):audit.validate_source(corpus,claim.model_copy(update={'statement':'changed'}))


def test_all_explicit_assignments_required_not_just_pretraining_source():
    text='Model (X = CorpusA, Z = CorpusB)\n38.5\n52.0'
    corpus,claim=example('CorpusA yields 38.5 and 52.0.',text)
    assert audit_result_conditions(corpus,claim).missing_conditions==('CorpusB',)


def test_swapped_explicit_assignments_are_not_passed_by_value_presence():
    text='Model (X = CorpusA, Z = CorpusB)\n38.5\n52.0'
    corpus,claim=example('X = CorpusB, Z = CorpusA yield 38.5 and 52.0.',text)
    assert audit_result_conditions(corpus,claim).status=='unknown'


def test_offsets_remain_exact_with_leading_whitespace_and_crlf():
    text='Table results\r\n  Model (X = CorpusA)\r\n 38.5\r\n 52.0'
    corpus,claim=example('CorpusA yields 38.5 and 52.0.',text)
    audit=audit_result_conditions(corpus,claim)
    assert audit.status=='passed'
    audit.validate_source(corpus,claim)
    assert audit.row.source.quote=='Model (X = CorpusA)\r\n 38.5\r\n 52.0'


def test_scientific_notation_is_decimal_equivalence_not_unit_conversion():
    corpus,claim=example('CorpusA yields 38.5 and 52.0.','Model (X = CorpusA)\n3.85e1\n5.2E1')
    assert audit_result_conditions(corpus,claim).status=='passed'


def test_unsupported_numeric_unit_is_unknown_instead_of_non_numeric():
    corpus,claim=example('CorpusA has 38m.','Model (X = CorpusA)\n38')
    assert audit_result_conditions(corpus,claim).status=='unknown'


def test_condition_at_english_sentence_end_is_preserved_but_name_extension_is_not():
    corpus,claim=example('REALM yields 38.5 and 52.0 using CC-News.')
    assert audit_result_conditions(corpus,claim).status=='passed'
    extended=claim.model_copy(update={'statement':claim.statement.replace('CC-News.','CC-News.Extra.')})
    extended=extended.model_copy(update={'claim_id':extended.expected_id(corpus.corpus_id)})
    assert audit_result_conditions(corpus,extended).status=='missing'
