from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ExecutionSnapshot:
    project_id: str
    user_input: str
    tenant_id: str | None
    input_artifacts: list[dict[str, Any]]
    metadata: dict[str, Any]
    override_input: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "user_input": self.user_input,
            "tenant_id": self.tenant_id,
            "input_artifacts": self.input_artifacts,
            "metadata": self.metadata,
            "override_input": self.override_input,
        }
