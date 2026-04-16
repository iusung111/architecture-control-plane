from __future__ import annotations

import json

from .llm_management_support.common import ProviderStatus, RoutingDecision, ScopeOverrideStatus, LLMRoutingBase
from .llm_management_support.policy_service import PolicyServiceMixin
from .llm_management_support.selection_service import SelectionServiceMixin


class LLMRoutingService(
    PolicyServiceMixin,
    SelectionServiceMixin,
    LLMRoutingBase,
):
    pass


def parse_json_mapping(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


__all__ = ["LLMRoutingService", "ProviderStatus", "RoutingDecision", "ScopeOverrideStatus", "parse_json_mapping"]
