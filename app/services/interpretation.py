import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app.services.llm_access import LLMRawResult


class InterpretationService:
    def __init__(self, schema_path: str | Path):
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        self._validator = Draft202012Validator(schema)

    def validate(self, result: LLMRawResult) -> dict:
        if result.parsed_payload is None:
            raise ValueError("llm output is not valid json")
        errors = list(self._validator.iter_errors(result.parsed_payload))
        if errors:
            raise ValueError("; ".join(error.message for error in errors))
        payload = result.parsed_payload
        if payload["confidence"] < 0.85:
            payload["escalation_recommendation"] = "human_review"
        return payload
