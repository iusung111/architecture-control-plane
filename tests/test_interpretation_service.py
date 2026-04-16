from __future__ import annotations

import json

import pytest

from app.services.interpretation import InterpretationService
from app.services.llm_access import LLMRawResult



def test_interpretation_service_rejects_non_json_output(tmp_path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({"type": "object", "required": ["confidence"]}), encoding="utf-8")
    service = InterpretationService(schema_path)

    with pytest.raises(ValueError, match="llm output is not valid json"):
        service.validate(
            LLMRawResult(
                backend_name="test",
                model="demo",
                raw_text="not-json",
                parsed_payload=None,
                validation_errors=["invalid json"],
            )
        )



def test_interpretation_service_validates_schema_and_marks_low_confidence_for_review(tmp_path):
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["confidence", "summary"],
                "properties": {
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "summary": {"type": "string"},
                },
            }
        ),
        encoding="utf-8",
    )
    service = InterpretationService(schema_path)

    with pytest.raises(ValueError, match="'summary' is a required property"):
        service.validate(
            LLMRawResult(
                backend_name="test",
                model="demo",
                raw_text='{"confidence": 0.5}',
                parsed_payload={"confidence": 0.5},
                validation_errors=[],
            )
        )

    low_confidence = service.validate(
        LLMRawResult(
            backend_name="test",
            model="demo",
            raw_text='{"confidence": 0.84, "summary": "needs review"}',
            parsed_payload={"confidence": 0.84, "summary": "needs review"},
            validation_errors=[],
        )
    )
    assert low_confidence["escalation_recommendation"] == "human_review"

    high_confidence = service.validate(
        LLMRawResult(
            backend_name="test",
            model="demo",
            raw_text='{"confidence": 0.92, "summary": "ok"}',
            parsed_payload={"confidence": 0.92, "summary": "ok"},
            validation_errors=[],
        )
    )
    assert "escalation_recommendation" not in high_confidence
