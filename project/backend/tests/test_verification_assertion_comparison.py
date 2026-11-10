"""Frozen statement controls are diagnostics, never automatic semantic labels."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.research.artifacts import Claim
from app.research.graph import Citation
from scripts.compare_verification_scope import assertion_cases, experiment_cases, diagnostic_exit_code
from test_research_evidence import corpus_for


@pytest.fixture
def assertion_fixture(tmp_path):
    results = Path(__file__).resolve().parents[1] / 'evaluation/results'
    filenames = [f'research_recovery_method_{kind}_20261108.json' for kind in ('negative','positive')]
    inputs = [Claim.model_validate_json((results/name).read_bytes()) for name in filenames]
    corpus = corpus_for('\n\n'.join(c.citation.quote for c in inputs), parent_size=8000, child_size=4000)
    chunk = corpus.chunk_sets['d0'].child_chunks[0]
    for name, original in zip(filenames, inputs):
        quote = original.citation.quote
        start = chunk.text.index(quote)
        claim = original.model_copy(update={'document_id':'d0', 'citation':Citation(
            chunk_id=chunk.chunk_id,char_start=start,char_end=start+len(quote),quote=quote)})
        claim = claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})
        (tmp_path/name).write_text(claim.model_dump_json(),encoding='utf-8')
    task = SimpleNamespace(sources=(SimpleNamespace(document_id='d0'),))
    return task, corpus, tmp_path


def test_atomic_controls_keep_exact_source_and_new_statement_identity(assertion_fixture):
    task, corpus, results = assertion_fixture
    cases = assertion_cases(task,corpus,results)
    assert len(cases)==4 and cases==assertion_cases(task,corpus,results)
    assert [expected for _,_,expected in cases]==['insufficient','supported','insufficient','supported']
    assert len({c.claim_id for _,c,_ in cases})==4
    assert cases[0][1].citation==cases[1][1].citation==cases[2][1].citation
    assert cases[2][1].statement==cases[3][1].statement
    assert cases[2][1].citation!=cases[3][1].citation
    for _,claim,_ in cases:
        claim.citation.validate_source(corpus,claim.document_id)
        assert claim.claim_id==claim.expected_id(corpus.corpus_id)


def test_assertion_experiment_has_four_requests_and_retains_attribution_context(assertion_fixture):
    cases,policies=experiment_cases(*assertion_fixture,experiment='assertions-v1')
    assert policies==('preceding-children-v1',) and len(cases)*len(policies)==4
    with pytest.raises(ValueError):experiment_cases(*assertion_fixture,experiment='unknown')


def test_changed_frozen_statement_cannot_silently_reuse_the_atomic_controls(assertion_fixture):
    task,corpus,results=assertion_fixture
    path=results/'research_recovery_method_negative_20261108.json'
    claim=Claim.model_validate_json(path.read_bytes()).model_copy(update={'statement':'Different compound assertion.'})
    claim=claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})
    path.write_text(claim.model_dump_json(),encoding='utf-8')
    with pytest.raises(ValueError,match='statement'):assertion_cases(task,corpus,results)


@pytest.mark.parametrize('change',['id','quote','scope'])
def test_atomic_controls_require_valid_owned_frozen_inputs(assertion_fixture,change):
    task,corpus,results=assertion_fixture
    path=results/'research_recovery_method_negative_20261108.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    if change=='id':data['claim_id']='foreign'
    if change=='quote':data['citation']['quote']='invented'
    if change=='scope':task=SimpleNamespace(sources=(SimpleNamespace(document_id='other'),))
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError):assertion_cases(task,corpus,results)


def test_http_success_is_not_a_passing_development_expectation():
    record={'status':'completed','max_requests':1,'rows':[
        {'expected_status':'insufficient','verdict':{'status':'supported'}}]}
    assert diagnostic_exit_code(record)==3
    record['rows'][0]['verdict']['status']='insufficient'
    assert diagnostic_exit_code(record)==0


@pytest.mark.parametrize('record',[
    {'status':'stopped','max_requests':1,'rows':[]},
    {'status':'completed','max_requests':1,'rows':[]},
    {'status':'completed','max_requests':1,'rows':[{'expected_status':'insufficient','error_type':'TimeoutError'}]},
    {'status':'completed','max_requests':0,'rows':[]},
])
def test_incomplete_diagnostics_cannot_pass_by_omitting_judgments(record):
    assert diagnostic_exit_code(record)==2


def test_duplicate_rows_do_not_stand_in_for_missing_controls():
    row={'case':'training_original_quote','policy':'preceding-children-v1',
         'expected_status':'insufficient','verdict':{'status':'insufficient'}}
    assert diagnostic_exit_code({'status':'completed','max_requests':2,'rows':[row,row]})==2
