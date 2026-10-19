"""Safe response diagnostics; never retain model text, keys or error messages."""
from pydantic import ValidationError


class ResponseSchemaError(ValueError):
    def __init__(self, diagnostics):
        super().__init__("research_response_schema_invalid")
        self.diagnostics = diagnostics


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
