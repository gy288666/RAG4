"""Bounded, source-addressed attribution context, separate from cited support.

Parts retain canonical chunk IDs and exact Unicode offsets. Source locations
are recovered through the frozen ChunkSet; context never gains support IDs.
"""
from typing import Literal,Protocol
from pydantic import Field,model_validator
from app.chunking.models import Identifier,Snapshot,content_id
from .graph import Citation

VerificationContextPolicy=Literal['cited-chunk-v1','preceding-children-v1']


class ContextClaim(Protocol):
    claim_id: str
    document_id: str
    citation: Citation


class ContextPart(Snapshot):
    role: Literal['preceding','cited']
    citation: Citation


class VerificationContext(Snapshot):
    context_id: Identifier
    policy: Literal['preceding-children-v1']='preceding-children-v1'
    corpus_id: Identifier
    claim_id: Identifier
    document_id: Identifier
    parts: tuple[ContextPart,...]=Field(min_length=1,max_length=3)
    context_chars: int=Field(strict=True,ge=1,le=6000)
    warnings: tuple[str,...]=()

    @property
    def text(self):
        return '\n\n'.join(p.citation.quote for p in self.parts)

    @model_validator(mode='after')
    def structure(self):
        if self.context_chars!=len(self.text) or [p.role for p in self.parts].count('cited')!=1 or self.parts[-1].role!='cited':
            raise ValueError('Invalid verification context structure')
        return self

    def expected_id(self):
        return content_id('verification_context_',self.model_dump(mode='json',exclude={'context_id'}))

    def validate_source(self,corpus,claim: ContextClaim):
        if self!=build_context(corpus,claim):
            raise ValueError('Verification context differs from frozen source selection')


def build_context(corpus,claim: ContextClaim) -> VerificationContext:
    """At most two immediate preceding children plus the cited source slice.

    Cross-parent adjacency is intentional. Never skip an oversized nearest
    predecessor to borrow an unrelated distant one. No corpus-wide retrieval.
    """
    corpus.require_scope(corpus.user_id,(claim.document_id,))
    claim.citation.validate_source(corpus,claim.document_id)
    chunk=corpus.chunks[claim.citation.chunk_id]
    cited=claim.citation if len(chunk.text)>4000 else Citation(
        chunk_id=chunk.chunk_id,char_start=0,char_end=len(chunk.text),quote=chunk.text)
    children=sorted(corpus.chunk_sets[claim.document_id].child_chunks,key=lambda c:(c.chunk_index,c.chunk_id))
    anchors=[i for i,c in enumerate(children) if c.chunk_id==chunk.chunk_id]
    if chunk.is_parent:
        for i,child in enumerate(children):
            if child.parent_chunk_id!=chunk.chunk_id:continue
            start=chunk.text.find(child.text)
            if start<0 or chunk.text.find(child.text,start+1)>=0:continue
            if start<cited.char_end and start+len(child.text)>cited.char_start:anchors.append(i)
    warnings=[];selected=[];used=len(cited.quote)
    if anchors:
        for previous in reversed(children[max(0,min(anchors)-2):min(anchors)]):
            if len(previous.text)>4000 or used+2+len(previous.text)>6000:
                warnings.append('preceding_context_omitted_budget');break
            selected.append(ContextPart(role='preceding',citation=Citation(chunk_id=previous.chunk_id,
                char_start=0,char_end=len(previous.text),quote=previous.text)))
            used+=2+len(previous.text)
    else:warnings.append('context_anchor_not_mapped')
    selected.reverse();selected.append(ContextPart(role='cited',citation=cited))
    result=VerificationContext(context_id='pending',corpus_id=corpus.corpus_id,claim_id=claim.claim_id,
        document_id=claim.document_id,parts=tuple(selected),context_chars=used,warnings=tuple(warnings))
    return result.model_copy(update={'context_id':result.expected_id()})
