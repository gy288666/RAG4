"""Deterministic scoped BM25 supplement; no model calls or index mutations."""
from collections import Counter
import math
import re
import unicodedata

from .evidence import VectorHit


CONCEPTS = {
    "索引": "index", "更新": "update refresh", "预训练": "pretraining pre training",
    "微调": "finetuning fine tuning", "编码": "encoder encoding", "拼接": "concatenate concatenated",
    "数据集": "dataset benchmark", "局限": "limitation failure", "训练": "training",
}


def words(text):
    text = re.sub(r"([A-Za-z])-\s*\n\s*([A-Za-z])", r"\1\2", unicodedata.normalize("NFKC", text))
    return re.findall(r"[a-z0-9]+", text.casefold())


class LexicalEvidenceRetriever:
    """Repair a document's missing index context without displacing other docs.

    Small explicit Chinese/English concept mappings describe query intent;
    neither answer labels nor paper-specific expected terms enter ranking.
    Scores are BM25 relevance scores, never probabilities or semantic proof.
    Optional source_role prioritizes first-person procedures over cited work;
    it cannot establish authorship and never replaces existing index hits.
    """
    def __init__(self, corpus, primary, *, source_role=False):
        self.corpus, self.primary = corpus, primary
        self.source_role = source_role

    def search(self, user_id, query, document_ids, top_k):
        self.corpus.require_scope(user_id, document_ids)
        if type(top_k) is not int or not 1 <= top_k <= 20:
            raise ValueError("Invalid candidate limit")
        dense = self.primary.search(user_id, query, document_ids, top_k)
        for hit in dense:
            chunk = self.corpus.chunks.get(hit.chunk_id)
            if chunk is None or chunk.is_parent or chunk.document_id not in document_ids or not math.isfinite(hit.score):
                raise ValueError("Out-of-scope primary candidate")
        # Sparse supplementation is opt-in AND intent gated. Generic comparison
        # terms matched unrelated papers in the first development ablation.
        if '索引' not in query and not re.search(r'\bindex(?:es|ing)?\b', query, re.IGNORECASE):
            return dense[:top_k]
        terms = set(words(query + ' ' + ' '.join(v for k, v in CONCEPTS.items() if k in query)))
        # Sort before truncation, so hash randomization cannot change a long query.
        terms = sorted(terms)[:64]
        if not terms:
            return dense[:top_k]
        chunks = [c for d in document_ids for c in self.corpus.chunk_sets[d].child_chunks]
        counters = [Counter(words(c.text)) for c in chunks]
        average = sum(sum(c.values()) for c in counters) / max(1, len(chunks)) or 1
        frequency = {t: sum(t in c for c in counters) for t in terms}
        sparse = []
        for chunk, counter in zip(chunks, counters):
            length = sum(counter.values())
            score = sum(math.log(1 + (len(chunks) - frequency[t] + .5) / (frequency[t] + .5))
                * counter[t] * 2.2 / (counter[t] + 1.2 * (.25 + .75 * length / average))
                for t in terms if counter[t])
            if score > 0:
                sparse.append(VectorHit(chunk_id=chunk.chunk_id, score=score, channel='lexical'))
        sparse.sort(key=lambda h: (-h.score, h.chunk_id))
        # An attribution hint for procedure questions, not a semantic verdict.
        # Keep BM25 order for benchmark/speed questions and the legacy policy.
        if self.source_role and not re.search(r'速度|延迟|性能|\b(?:speed|latency|performance)\b', query, re.IGNORECASE):
            def role(hit):
                tokens = set(words(self.corpus.chunks[hit.chunk_id].text))
                own = bool(tokens & {'we', 'our'})
                procedure = bool(tokens & {'apply', 'encode', 'build', 'refresh', 'update', 'offline', 'inference'})
                cited = {'et', 'al'}.issubset(tokens) and bool(tokens & {'their', 'they'})
                return 2 if own and procedure else 0 if cited and not own else 1
            sparse.sort(key=lambda h: (-role(h), -h.score, h.chunk_id))
        selected, seen = [], set()
        for hit in dense:
            if hit.chunk_id not in seen:
                selected.append(hit)
                seen.add(hit.chunk_id)
                if len(selected) >= top_k:
                    break
        index_terms = {'index','indexes','indices','indexing'}
        for document_id in document_ids:
            positions = [n for n,h in enumerate(selected) if self.corpus.chunks[h.chunk_id].document_id==document_id]
            if not positions or any(index_terms.intersection(words(self.corpus.chunks[selected[n].chunk_id].text)) for n in positions):
                continue
            candidate = next((h for h in sparse if self.corpus.chunks[h.chunk_id].document_id==document_id
                and h.chunk_id not in seen and index_terms.intersection(words(self.corpus.chunks[h.chunk_id].text))),None)
            if candidate is None:
                continue
            if len(selected)<top_k:
                selected.append(candidate)
            else:
                # Replace only the last off-topic hit of this same document.
                # Other documents' exact-match evidence remains available.
                seen.remove(selected[positions[-1]].chunk_id)
                selected[positions[-1]] = candidate
            seen.add(candidate.chunk_id)
        return selected
