"""Context can clarify attribution, but cannot enlarge publishable evidence."""
import pytest
from app.research.artifacts import Claim,EvidenceVerifier,ArtifactComposer
from app.research.graph import Citation
from app.research.verification_context import build_context
from test_research_evidence import corpus_for
from test_verification_facets import FacetModel


def context_example():
    paragraphs=('Roberts et al. describe a model that stores all information in its weights.',
        'Without external knowledge, this earlier model answers benchmark questions.',
        'However, it needs billions of parameters. Our model instead retrieves documents.')
    corpus=corpus_for('\n\n'.join(paragraphs),'FOREIGN DOCUMENT',parent_size=110,child_size=100)
    chunk=next(c for c in corpus.chunk_sets['d0'].child_chunks if c.text.startswith('However'))
    claim=Claim(claim_id='pending',document_id='d0',facet='limitation',statement='Our model needs billions of parameters.',
        citation=Citation(chunk_id=chunk.chunk_id,char_start=0,char_end=len(chunk.text),quote=chunk.text))
    return corpus,claim.model_copy(update={'claim_id':claim.expected_id(corpus.corpus_id)})


class ContextModel(FacetModel):
    verification_context_policy='preceding-children-v1'


def test_preceding_context_crosses_parent_boundary_with_exact_source_slices():
    corpus,claim=context_example()
    assert 'Roberts' not in corpus.chunks[corpus.chunks[claim.citation.chunk_id].parent_chunk_id].text
    context=build_context(corpus,claim)
    assert context==build_context(corpus,claim)
    assert 'Roberts' in context.text and 'FOREIGN' not in context.text
    assert len(context.parts)==3 and context.context_chars==len(context.text)<=6000
    assert context.parts[-1].role=='cited' and all(p.role=='preceding' for p in context.parts[:-1])
    context.validate_source(corpus,claim)
    for part in context.parts:part.citation.validate_source(corpus,'d0')


def test_context_is_persisted_but_not_added_to_the_support_catalog():
    from app.research.artifacts import VerificationReport,ComparisonArtifact
    corpus,claim=context_example();model=ContextModel()
    report=EvidenceVerifier(model).verify(corpus,(claim,))
    assert 'Roberts' in model.payload['claims'][0]['context']
    assert 'Roberts' not in ''.join(s['text'] for s in model.payload['claims'][0]['sources'])
    assert report.context_policy=='preceding-children-v1' and len(report.contexts)==1
    assert VerificationReport.model_validate_json(report.model_dump_json())==report
    artifact=ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'paper'},(claim,),report)
    assert artifact.citations[0].citation==claim.citation
    assert ComparisonArtifact.model_validate_json(artifact.model_dump_json()).expected_id()==artifact.artifact_id


def test_context_ids_cannot_be_returned_as_support_handles():
    corpus,claim=context_example();model=ContextModel();generate=model.generate
    def altered(operation,payload):
        result=generate(operation,payload)
        result['assessments'][0]['attribution']['support_ids']=[payload['claims'][0]['context_sources'][0]['citation']['chunk_id']]
        return result
    model.generate=altered
    assert EvidenceVerifier(model).verify(corpus,(claim,)).supported==0


def test_composer_rejects_tampered_context_identity():
    corpus,claim=context_example()
    report=EvidenceVerifier(ContextModel()).verify(corpus,(claim,))
    altered=report.contexts[0].model_copy(update={'context_id':'forged'})
    with pytest.raises(ValueError,match='context'):
        ArtifactComposer().compose(corpus,'compare',('d0',),{'d0':'paper'},(claim,),
            report.model_copy(update={'contexts':(altered,)}))


def test_context_budget_omits_distant_predecessor_without_losing_cited_quote():
    corpus=corpus_for('A'*3000+'\n\n'+'B'*3000+'\n\n'+'C'*3000,parent_size=4000,child_size=4000)
    chunk=corpus.chunk_sets['d0'].child_chunks[-1]
    claim=Claim(claim_id='p',document_id='d0',facet='method',statement='statement',
        citation=Citation(chunk_id=chunk.chunk_id,char_start=0,char_end=len(chunk.text),quote=chunk.text))
    context=build_context(corpus,claim)
    assert context.context_chars<=6000 and chunk.text in context.text
    assert 'preceding_context_omitted_budget' in context.warnings


def test_old_context_default_and_wire_identity_are_preserved():
    from app.research.model import CompletionSpec
    corpus,claim=context_example();model=FacetModel()
    report=EvidenceVerifier(model).verify(corpus,(claim,))
    assert model.payload['claims'][0]['context']==corpus.chunks[claim.citation.chunk_id].text
    assert 'contexts' not in report.model_dump() and 'context_policy' not in report.model_dump()
    spec=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test')
    assert 'verification_context_policy' not in spec.model_dump()


def test_parent_citation_uses_children_for_preceding_context_anchor():
    corpus,claim=context_example()
    parent=corpus.chunks[corpus.chunks[claim.citation.chunk_id].parent_chunk_id]
    claim=claim.model_copy(update={'citation':Citation(chunk_id=parent.chunk_id,char_start=0,
        char_end=len(parent.text),quote=parent.text)})
    context=build_context(corpus,claim)
    assert 'Roberts' in context.text
    assert context.parts[-1].citation.chunk_id==parent.chunk_id
    assert all(p.citation.chunk_id!=parent.chunk_id for p in context.parts[:-1])


def test_long_cited_chunk_uses_exact_quote_without_exceeding_budget():
    corpus=corpus_for('A'*7000,parent_size=8000,child_size=8000)
    chunk=corpus.chunk_sets['d0'].child_chunks[0]
    quote=chunk.text[6500:6600]
    claim=Claim(claim_id='p',document_id='d0',facet='method',statement='statement',
        citation=Citation(chunk_id=chunk.chunk_id,char_start=6500,char_end=6600,quote=quote))
    context=build_context(corpus,claim)
    assert context.parts[-1].citation==claim.citation and context.context_chars==100


def test_foreign_document_citation_cannot_supply_context():
    corpus,claim=context_example()
    foreign=corpus.chunk_sets['d1'].child_chunks[0]
    altered=claim.model_copy(update={'citation':Citation(chunk_id=foreign.chunk_id,char_start=0,
        char_end=len(foreign.text),quote=foreign.text)})
    with pytest.raises(ValueError,match='source'):build_context(corpus,altered)


def test_context_policy_is_explicit_and_only_allowed_for_v5():
    from app.research.model import CompletionSpec
    from pydantic import ValidationError
    with pytest.raises(ValidationError):CompletionSpec(endpoint='https://example.test/v1/chat/completions',
        model_id='test',verification_context_policy='preceding-children-v1')
    spec=CompletionSpec(endpoint='https://example.test/v1/chat/completions',model_id='test',
        verification_protocol='facet-handles-v5',verification_context_policy='preceding-children-v1')
    assert CompletionSpec.model_validate_json(spec.model_dump_json())==spec


def test_ambiguous_repeated_parent_text_does_not_guess_a_preceding_anchor():
    corpus=corpus_for('A'*7000,parent_size=8000,child_size=4000)
    parent=corpus.chunk_sets['d0'].parent_chunks[0]
    claim=Claim(claim_id='p',document_id='d0',facet='method',statement='statement',
        citation=Citation(chunk_id=parent.chunk_id,char_start=6500,char_end=6600,quote=parent.text[6500:6600]))
    context=build_context(corpus,claim)
    assert len(context.parts)==1 and 'context_anchor_not_mapped' in context.warnings
