from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.management_config import ManagementConfigRepository

ABUSE_ALLOWED_KEYS = {
    "global_requests_per_minute", "management_requests_per_minute", "cycle_create_limit_per_minute",
    "cycle_retry_limit_per_minute", "cycle_replan_limit_per_minute", "approval_confirm_limit_per_minute",
    "rate_limit_algorithm", "rate_limit_burst_multiplier", "failure_mode_api", "failure_mode_management",
    "tenant_plan_default", "tenant_plan_assignments_json", "tenant_plan_limits_json",
    "metrics_include_tenant_labels", "metrics_tenant_label_mode",
}
BACKUP_ALLOWED_KEYS = {
    "output_dir", "retention_keep_last", "retention_max_age_days", "object_store_verify_restore",
    "require_encryption", "default_label_prefix", "compose_service", "target_database_url",
    "target_database_urls_json", "command_timeout_seconds",
}
OBSERVABILITY_ALLOWED_KEYS = {
    "api_availability_slo_target", "api_latency_slo_target", "api_latency_slo_seconds",
    "metrics_enabled", "worker_metrics_enabled", "otel_enabled",
}


@dataclass(slots=True)
class BackupDrillExecutionPlan:
    target_name: str
    source_url: str
    target_url: str
    output_dir: Path
    label: str
    compose_service: str | None
    encryption_passphrase: str | None
    prune_keep_last: int
    prune_max_age_days: int
    object_store: dict[str, Any] | None
    restore_from_object_store: bool
    command_timeout_seconds: int


@dataclass(slots=True)
class ManagementConfigResponse:
    namespace: str
    effective: dict[str, Any]
    overrides: dict[str, Any]
    applies_immediately: bool
    applies_on_restart: bool


class ManagementConfigBase:
    def __init__(self, db: Session):
        self._db = db
        self._repo = ManagementConfigRepository(db)


def _sanitize(payload: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
    return {str(key): value for key, value in payload.items() if str(key) in allowed_keys}


def _validate_abuse_payload(payload: dict[str, Any]) -> None:
    for key in ["global_requests_per_minute", "management_requests_per_minute", "cycle_create_limit_per_minute", "cycle_retry_limit_per_minute", "cycle_replan_limit_per_minute", "approval_confirm_limit_per_minute"]:
        if key in payload and int(payload[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    if "rate_limit_algorithm" in payload and payload["rate_limit_algorithm"] not in {"fixed_window", "token_bucket"}:
        raise ValueError("rate_limit_algorithm must be fixed_window or token_bucket")
    if "rate_limit_burst_multiplier" in payload and float(payload["rate_limit_burst_multiplier"]) < 1.0:
        raise ValueError("rate_limit_burst_multiplier must be >= 1.0")
    for key in ["failure_mode_api", "failure_mode_management"]:
        if key in payload and payload[key] not in {"open", "closed"}:
            raise ValueError(f"{key} must be open or closed")


def _parse_named_backup_targets(payload: dict[str, Any]) -> dict[str, str]:
    value = payload.get("target_database_urls_json") or {}
    if not isinstance(value, dict):
        raise ValueError("target_database_urls_json must be a mapping")

    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str) or not item:
            raise ValueError("backup target values must be non-empty strings")
        result[str(key)] = item

    return result


def _resolve_backup_targets(*, overrides: dict[str, Any], settings) -> dict[str, str]:
    if "target_database_urls_json" in overrides:
        return _parse_named_backup_targets(overrides)

    if settings.backup_drill_target_database_urls_json:
        try:
            return _parse_named_backup_targets(
                {"target_database_urls_json": settings.backup_drill_target_database_urls_json}
            )
        except ValueError:
            pass

    default_url = overrides.get("target_database_url") or settings.backup_drill_target_database_url
    if default_url:
        return {"default": str(default_url)}

    return {"default": str(settings.database_url)}


def _validate_backup_payload(payload: dict[str, Any]) -> None:
    if "retention_keep_last" in payload and int(payload["retention_keep_last"]) <= 0:
        raise ValueError("retention_keep_last must be positive")
    if "retention_max_age_days" in payload and int(payload["retention_max_age_days"]) <= 0:
        raise ValueError("retention_max_age_days must be positive")
    if "command_timeout_seconds" in payload and int(payload["command_timeout_seconds"]) <= 0:
        raise ValueError("command_timeout_seconds must be positive")

    for key in ("object_store_verify_restore", "require_encryption"):
        if key in payload and not isinstance(payload[key], bool):
            raise ValueError(f"{key} must be a boolean")

    if "target_database_url" in payload and payload["target_database_url"] not in (None, "") and not isinstance(payload["target_database_url"], str):
        raise ValueError("target_database_url must be a string")

    if "default_label_prefix" in payload and payload["default_label_prefix"] not in (None, "") and not isinstance(payload["default_label_prefix"], str):
        raise ValueError("default_label_prefix must be a string")

    if "compose_service" in payload and payload["compose_service"] not in (None, "") and not isinstance(payload["compose_service"], str):
        raise ValueError("compose_service must be a string")

    if "target_database_urls_json" in payload:
        _parse_named_backup_targets(payload)


def _validate_observability_payload(payload: dict[str, Any]) -> None:
    for key in ["api_availability_slo_target", "api_latency_slo_target"]:
        if key in payload and not 0 < float(payload[key]) <= 1:
            raise ValueError(f"{key} must be between 0 and 1")
    if "api_latency_slo_seconds" in payload and float(payload["api_latency_slo_seconds"]) <= 0:
        raise ValueError("api_latency_slo_seconds must be positive")
