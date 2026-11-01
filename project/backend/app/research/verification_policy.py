"""Server-owned audit targets; these are rules, never scientific evidence."""
from typing import Literal
from app.chunking.models import Snapshot


class FacetRequirements(Snapshot):
    version: Literal['facet-scope-v1'] = 'facet-scope-v1'
    condition_rule: Literal['method_scope','dataset_scope','experiment_conditions','explicit_limitation_scope']
    scope_target: str


_RULES = {
    'method': ('method_scope', 'Match the stated mechanism, training/inference stage and scope. '
        'Do not demand dataset, model size or result variants absent from this method claim.'),
    'dataset': ('dataset_scope', 'Match every named dataset and its stated purpose/split. '
        'A result table without dataset headers cannot establish dataset names.'),
    'result': ('experiment_conditions', 'Match the exact row, dataset, metric, split, units, model variant '
        'and pretraining corpus. Reject a materially omitted qualifier; matching numbers alone is insufficient.'),
    'limitation': ('explicit_limitation_scope', 'Require explicit evidence for the stated limitation and scope. '
        'Do not demand unrelated result labels; a completed investigation is not evidence for future work.'),
}


def requirements_for(facet: str) -> FacetRequirements:
    """Choose by validated claim facet, independently of model output or labels."""
    if facet not in _RULES:
        raise ValueError('Unknown verification facet')
    rule,target = _RULES[facet]
    return FacetRequirements(condition_rule=rule,scope_target=target)
