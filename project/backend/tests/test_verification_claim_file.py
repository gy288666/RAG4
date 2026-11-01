"""External diagnostic claims cannot escape the frozen source contract."""
import pytest
from scripts.reverify_research_claims import load_claim_file
from test_research_verification_checks import example


def save(path,claim):
    path.write_bytes(claim.model_dump_json().encode('utf-8'))
    return path


def test_valid_claim_file_preserves_exact_claim_and_scope(tmp_path):
    corpus,claim=example()
    assert load_claim_file(save(tmp_path/'claim.json',claim),corpus,('d0',))==claim


@pytest.mark.parametrize('mutation',['quote','id','scope'])
def test_claim_file_rejects_fabricated_quote_identity_and_foreign_scope(tmp_path,mutation):
    corpus,claim=example()
    if mutation=='quote':claim=claim.model_copy(update={'citation':claim.citation.model_copy(update={'quote':'fabricated'})})
    if mutation=='id':claim=claim.model_copy(update={'claim_id':'foreign'})
    scope=('other',) if mutation=='scope' else ('d0',)
    with pytest.raises(ValueError):load_claim_file(save(tmp_path/'claim.json',claim),corpus,scope)
