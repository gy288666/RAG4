"""Safe response diagnostics; never retain model text, keys or error messages."""
from pydantic import ValidationError


class ResponseSchemaError(ValueError):
    def __init__(self, diagnostics):
        super().__init__("research_response_schema_invalid")
        self.diagnostics = diagnostics


class ResponseContractError(ResponseSchemaError):
    """Server-owned codes/counts only; never echo returned IDs or error text."""
    def __init__(self, code, operation, collection, counts=None):
        codes={'duplicate_claim_ids','unknown_claim_ids','duplicate_and_unknown_claim_ids',
               'batch_scope','batch_verdict_coverage','batch_counters','batch_protocol','batch_policy',
               'batch_condition_scope','batch_condition_coverage','unclassified_document_validation'}
        if (code not in codes or operation not in {'verify','verify_checked','verify_handles','verify_facets','verify_document'}
                or collection not in {'assessments','verdicts','batch'}):
            raise ValueError('Unsupported response diagnostic route')
        counts=dict(counts or {})
        if any(k not in {'expected','received','unique','unknown','missing'} or type(v) is not int or not 0<=v<=1000000
               for k,v in counts.items()):
            raise ValueError('Invalid response diagnostic counts')
        diagnostics=[f'response_contract_invalid:{operation}:{collection}:{code}']
        if counts:
            diagnostics.append('response_contract_counts:'+operation+':'+','.join(f'{k}={counts[k]}' for k in sorted(counts)))
        super().__init__(tuple(diagnostics))
        self.code,self.counts=code,counts
        self.args=(('Verification batch scope or protocol mismatch:' if code.startswith('batch_')
                    else 'research_response_contract_invalid:')+code,)


def check_response_ids(expected, received, operation, collection):
    """Missing judgments retain existing insufficient behavior; bad IDs fail."""
    expected=set(expected);received=tuple(received);unique=set(received)
    duplicate=len(received)!=len(unique);unknown=bool(unique-expected)
    if duplicate or unknown:
        code='duplicate_and_unknown_claim_ids' if duplicate and unknown else 'duplicate_claim_ids' if duplicate else 'unknown_claim_ids'
        raise ResponseContractError(code,operation,collection,
            {'expected':len(expected),'received':len(received),'unique':len(unique),
             'unknown':len(unique-expected),'missing':len(expected-unique)})


def validate_response(schema, payload, operation):
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        fields = {"claims", "relations", "verdicts", "facet", "statement", "citation_id", "evidence_id",
            "quote", "subject", "predicate", "object", "claim_id", "status", "reason",
            "assessments", "attribution", "conditions", "entailment", "support_quote", "support_ids"}
        codes = {"missing", "extra_forbidden", "too_long", "tuple_type", "string_type", "string_too_long",
            "string_too_short", "literal_error", "model_type", "dict_type"}
        diagnostics = []
        for issue in error.errors(include_input=False, include_context=False, include_url=False)[:6]:
            path = ".".join(str(p) if type(p) is int and 0 <= p <= 100 else p if p in fields else "unrecognized"
                for p in issue["loc"])
            code = issue["type"] if issue["type"] in codes else "invalid_value"
            diagnostics.append(f"response_schema_invalid:{operation}:{path}:{code}")
        raise ResponseSchemaError(tuple(diagnostics)) from error
