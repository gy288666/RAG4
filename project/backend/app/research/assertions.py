"""Explicit statement coverage, one bounded judgment, and publication restriction.

Ranges are Python Unicode offsets, end exclusive. Callers supply a reviewed
partition; this module does not infer semantic boundaries or rewrite statements.
Coverage and literal source identity do not prove semantic entailment.
"""
from typing import Literal
from pydantic import Field, model_validator
from app.chunking.models import Identifier, Snapshot, content_id
from .artifacts import (ClaimAssessment, HandleCheck, SourceCheck, Verdict,
    VerificationReport, ComparisonArtifact, ArtifactComposer, verification_sources)
from .protocol import ResponseSchemaError, validate_response
from .verification_context import VerificationContext, build_context
from .verification_policy import requirements_for

VERSION = 'statement-ranges-v1'


class StatementAssertion(Snapshot):
    assertion_id: Identifier
    char_start: int = Field(strict=True,ge=0)
    char_end: int = Field(strict=True,gt=0)
    text: str = Field(min_length=1,max_length=1000)


class AssertionPlan(Snapshot):
    plan_id: Identifier
    version: Literal['statement-ranges-v1'] = VERSION
    corpus_id: Identifier
    claim_id: Identifier
    statement: str = Field(min_length=1,max_length=1000)
    assertions: tuple[StatementAssertion,...] = Field(min_length=1,max_length=8)

    @model_validator(mode='after')
    def coverage(self):
        position=0
        for assertion in self.assertions:
            if (assertion.char_start!=position or assertion.char_end<=position
                    or assertion.char_end>len(self.statement) or not assertion.text.strip()
                    or assertion.text!=self.statement[position:assertion.char_end]):
                raise ValueError('Assertion ranges must partition the complete original statement')
            position=assertion.char_end
        if position!=len(self.statement):raise ValueError('Incomplete assertion coverage')
        return self

    def expected_id(self):
        return content_id('assertion_plan_',self.model_dump(mode='json',exclude={'plan_id'}))

    def validate_source(self,corpus,claim):
        expected=build_assertion_plan(corpus,claim,tuple(a.char_end for a in self.assertions))
        if self!=expected:raise ValueError('Assertion plan differs from frozen claim')


def build_assertion_plan(corpus,claim,ends: tuple[int,...]) -> AssertionPlan:
    """Create a complete explicit partition; never silently trim punctuation."""
    corpus.require_scope(corpus.user_id,(claim.document_id,))
    claim.citation.validate_source(corpus,claim.document_id)
    if claim.claim_id!=claim.expected_id(corpus.corpus_id):raise ValueError('Claim identity mismatch')
    if not 1<=len(ends)<=8 or any(type(end) is not int for end in ends):
        raise ValueError('One to eight strict integer boundaries required')
    position=0;assertions=[]
    for end in ends:
        if not position<end<=len(claim.statement):raise ValueError('Invalid assertion boundary')
        data={'char_start':position,'char_end':end,'text':claim.statement[position:end]}
        identity=content_id('assertion_',{'version':VERSION,'corpus_id':corpus.corpus_id,
            'claim_id':claim.claim_id,**data})
        assertions.append(StatementAssertion(assertion_id=identity,**data));position=end
    result=AssertionPlan(plan_id='pending',corpus_id=corpus.corpus_id,claim_id=claim.claim_id,
        statement=claim.statement,assertions=tuple(assertions))
    return result.model_copy(update={'plan_id':result.expected_id()})


class AssertionAssessment(Snapshot):
    assertion_id: Identifier
    attribution: SourceCheck
    conditions: SourceCheck
    entailment: SourceCheck

    def verdict(self,claim):
        if any(not getattr(self,name).support_ids for name in ('attribution','conditions','entailment')):
            # Empty IDs cannot be upgraded by attaching an unaddressed excerpt.
            if all(getattr(self,name).status=='supported' for name in ('attribution','conditions','entailment')):
                return Verdict(claim_id=claim.claim_id,status='insufficient',reason='assertion_support_handle_missing')
        return ClaimAssessment(claim_id=claim.claim_id,**{
            name:getattr(self,name) for name in ('attribution','conditions','entailment')}).verdict(claim)


class AssertionReview(Snapshot):
    review_id: Identifier
    version: Literal['statement-ranges-v1'] = VERSION
    plan: AssertionPlan
    context: VerificationContext
    assessments: tuple[AssertionAssessment,...] = Field(max_length=8)
    annotation_status: Literal['machine_review_only'] = 'machine_review_only'

    def expected_id(self):
        return content_id('assertion_review_',self.model_dump(mode='json',exclude={'review_id'}))

    def verdict(self,claim) -> Verdict:
        expected={a.assertion_id for a in self.plan.assertions}
        received={a.assertion_id:a for a in self.assessments}
        if (claim.claim_id!=self.plan.claim_id or claim.statement!=self.plan.statement
                or len(received)!=len(self.assessments) or not received.keys()<=expected):
            raise ValueError('Assertion review scope mismatch')
        judgments=[a.verdict(claim) for a in self.assessments]
        status=('contradicted' if any(v.status=='contradicted' for v in judgments) else
                'insufficient' if received.keys()!=expected or any(v.status!='supported' for v in judgments)
                else 'supported')
        return Verdict(claim_id=claim.claim_id,status=status,reason='assertion_coverage_'+status)

    def validate_source(self,corpus,claim):
        self.plan.validate_source(corpus,claim)
        self.context.validate_source(corpus,claim)
        self.verdict(claim)
        if self.review_id!=self.expected_id():raise ValueError('Assertion review identity mismatch')


class _HandleAssertion(Snapshot):
    assertion_id: Identifier
    attribution: HandleCheck
    conditions: HandleCheck
    entailment: HandleCheck

    def resolve(self,claim):
        return AssertionAssessment(assertion_id=self.assertion_id,**{
            name:getattr(self,name).resolve(claim) for name in ('attribution','conditions','entailment')})


class _AssertionJudgment(Snapshot):
    assessments: tuple[_HandleAssertion,...] = Field(max_length=20)


class AssertionCoverageVerifier:
    """One generate call for the entire supplied scope, never per assertion.

    Not wired into ResearchTask/HTTP. Its caller must reserve that single call;
    no extraction, hidden retry, automatic partitioning or baseline re-run.
    """
    def __init__(self,model):self.model=model

    def verify(self,corpus,claims,plans) -> tuple[AssertionReview,...]:
        claim_map={c.claim_id:c for c in claims};plan_map={p.claim_id:p for p in plans}
        if (not 1<=len(claims)<=20 or len(claim_map)!=len(claims) or len(plan_map)!=len(plans)
                or claim_map.keys()!=plan_map.keys() or sum(len(p.assertions) for p in plans)>20):
            raise ValueError('Invalid assertion verification scope')
        policy=getattr(self.model,'verification_context_policy',None)
        if getattr(self.model,'verification_protocol',None)!='facet-handles-v5' or policy not in {'preceding-children-v1','cited-support-v2'}:
            raise ValueError('Assertion verifier requires explicit source-addressed facet configuration')
        contexts={};payload=[];owners={}
        for claim in claims:
            plan=plan_map[claim.claim_id];plan.validate_source(corpus,claim)
            contexts[claim.claim_id]=build_context(corpus,claim,policy=policy)
            for assertion in plan.assertions:
                if assertion.assertion_id in owners:raise ValueError('Duplicate assertion identity')
                owners[assertion.assertion_id]=claim
            payload.append({'claim_id':claim.claim_id,'document_id':claim.document_id,'facet':claim.facet,
                'statement':claim.statement,'plan_id':plan.plan_id,
                'assertions':[a.model_dump(mode='json') for a in plan.assertions],
                'requirements':requirements_for(claim.facet).model_dump(mode='json'),
                'sources':verification_sources(claim),'context':contexts[claim.claim_id].text,
                'context_sources':[p.model_dump(mode='json') for p in contexts[claim.claim_id].parts]})
        result=validate_response(_AssertionJudgment,self.model.generate('verify_assertions',
            {'protocol':VERSION,'context_policy':policy,'claims':payload}),'verify_assertions')
        ids=[a.assertion_id for a in result.assessments]
        if len(ids)!=len(set(ids)) or not set(ids)<=owners.keys():
            raise ResponseSchemaError(('response_contract_invalid:verify_assertions:assertion_identity',))
        resolved={a.assertion_id:a.resolve(owners[a.assertion_id]) for a in result.assessments}
        reviews=[]
        for claim in claims:
            plan=plan_map[claim.claim_id]
            review=AssertionReview(review_id='pending',plan=plan,context=contexts[claim.claim_id],
                assessments=tuple(resolved[a.assertion_id] for a in plan.assertions if a.assertion_id in resolved))
            review=review.model_copy(update={'review_id':review.expected_id()})
            review.validate_source(corpus,claim);reviews.append(review)
        return tuple(reviews)


class AssertionPublication(Snapshot):
    """Keep baseline, individual reviews and restricted artifact together."""
    publication_id: Identifier
    version: Literal['statement-ranges-v1'] = VERSION
    baseline: VerificationReport
    reviews: tuple[AssertionReview,...] = Field(min_length=1,max_length=20)
    artifact: ComparisonArtifact

    def expected_id(self):
        return content_id('assertion_publication_',self.model_dump(mode='json',exclude={'publication_id'}))

    def validate_source(self,corpus,claims):
        rows=self.artifact.rows
        expected=compose_assertion_review(corpus,self.artifact.goal,tuple(r.document_id for r in rows),
            {r.document_id:r.title for r in rows},claims,self.baseline,self.reviews)
        if self!=expected:raise ValueError('Assertion publication differs from source-bound aggregation')


def compose_assertion_review(corpus,goal,document_ids,titles,claims,baseline,reviews) -> AssertionPublication:
    """Only restrict a baseline; a new review alone cannot promote a claim."""
    composer=ArtifactComposer()
    composer.compose(corpus,goal,document_ids,titles,claims,baseline)
    review_map={r.plan.claim_id:r for r in reviews}
    if not claims or len(review_map)!=len(reviews) or review_map.keys()!={c.claim_id for c in claims}:
        raise ValueError('Publication requires complete assertion reviews')
    verdicts={v.claim_id:v for v in baseline.verdicts};restricted=[]
    for claim in claims:
        review=review_map[claim.claim_id];review.validate_source(corpus,claim)
        verdicts_for_assertions=review.verdict(claim)
        restricted.append(verdicts_for_assertions if verdicts[claim.claim_id].status=='supported' else verdicts[claim.claim_id])
    report=baseline.model_copy(update={'verdicts':tuple(restricted),
        'supported':sum(v.status=='supported' for v in restricted),
        'warnings':(*baseline.warnings,'assertion_coverage_checked:'+VERSION)})
    artifact=composer.compose(corpus,goal,document_ids,titles,claims,report)
    publication=AssertionPublication(publication_id='pending',baseline=baseline,reviews=tuple(reviews),artifact=artifact)
    return publication.model_copy(update={'publication_id':publication.expected_id()})
