"""Optional hints cannot destroy valid claims; required claim schema stays strict."""
import pytest
from app.research.artifacts import extract_claims
from app.research.evidence import HybridEvidenceEngine, RetrievalOptions
from app.research.protocol import ResponseSchemaError
from test_research_evidence import corpus_for, Hits


@pytest.mark.parametrize('bad',[{'predicate':'unknown'}, {'subject':None}, {'extra':'untrusted-secret'}])
def test_invalid_optional_relation_is_dropped_without_losing_required_claim(bad):
    corpus=corpus_for('DPR uses BERT.',parent_size=180,child_size=100)
    bundle=HybridEvidenceEngine(corpus,Hits(corpus)).search(1,'method',RetrievalOptions(document_ids=('d0',)))
    class Model:
        extraction_protocol='source-handles-v2'
        calls=0
        def generate(self,operation,payload):
            self.calls+=1
            cid=payload['citations'][0]['citation_id']
            valid={'citation_id':cid,'subject':'DPR','predicate':'uses','object':'BERT'}
            return {'claims':[{'facet':'method','statement':'DPR uses BERT.','citation_id':cid}],
                    'relations':[valid,{**valid,**bad}]}
    model=Model()
    claims,relations,warnings=extract_claims(model,corpus,'d0',bundle,'compare')
    assert len(claims)==1 and len(relations)==1 and model.calls==1
    claims[0].citation.validate_source(corpus,'d0')
    assert any(w.startswith('draft_relation_rejected:response_schema_invalid:extract_relation:') for w in warnings)
    assert 'untrusted-secret' not in str(warnings)


@pytest.mark.parametrize('mutation',['invalid_claim','too_many_relations','invalid_container'])
def test_optional_hint_handling_does_not_relax_critical_envelope(mutation):
    corpus=corpus_for('DPR uses BERT.',parent_size=180,child_size=100)
    bundle=HybridEvidenceEngine(corpus,Hits(corpus)).search(1,'method',RetrievalOptions(document_ids=('d0',)))
    class Model:
        extraction_protocol='source-handles-v2'
        def generate(self,operation,payload):
            cid=payload['citations'][0]['citation_id']
            claim={'facet':'method','statement':'DPR uses BERT.','citation_id':cid}
            result={'claims':[claim],'relations':[]}
            if mutation=='invalid_claim':del claim['citation_id']
            elif mutation=='too_many_relations':result['relations']=[{}]*3
            else:result['relations']=None
            return result
    with pytest.raises(ResponseSchemaError):extract_claims(Model(),corpus,'d0',bundle,'compare')
