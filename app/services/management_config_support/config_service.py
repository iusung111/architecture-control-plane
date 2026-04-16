from __future__ import annotations

from app.core.config import get_settings
from app.ops.postgres_backup_restore import resolve_object_store_config, sanitize_database_url
from app.core.rate_limit import invalidate_abuse_override_cache, set_inprocess_abuse_override_payload

from .common import (
    ABUSE_ALLOWED_KEYS,
    BACKUP_ALLOWED_KEYS,
    OBSERVABILITY_ALLOWED_KEYS,
    ManagementConfigResponse,
    _resolve_backup_targets,
    _sanitize,
    _validate_abuse_payload,
    _validate_backup_payload,
    _validate_observability_payload,
)


class ConfigServiceMixin:
    def get_abuse_config(self) -> ManagementConfigResponse:
        settings = get_settings()
        overrides = self._repo.get_payload("abuse")
        effective = {
            "global_requests_per_minute": overrides.get("global_requests_per_minute", settings.abuse_global_requests_per_minute),
            "management_requests_per_minute": overrides.get("management_requests_per_minute", settings.abuse_management_requests_per_minute),
            "cycle_create_limit_per_minute": overrides.get("cycle_create_limit_per_minute", settings.abuse_cycle_create_limit_per_minute),
            "cycle_retry_limit_per_minute": overrides.get("cycle_retry_limit_per_minute", settings.abuse_cycle_retry_limit_per_minute),
            "cycle_replan_limit_per_minute": overrides.get("cycle_replan_limit_per_minute", settings.abuse_cycle_replan_limit_per_minute),
            "approval_confirm_limit_per_minute": overrides.get("approval_confirm_limit_per_minute", settings.abuse_approval_confirm_limit_per_minute),
            "rate_limit_algorithm": overrides.get("rate_limit_algorithm", settings.abuse_rate_limit_algorithm),
            "rate_limit_burst_multiplier": overrides.get("rate_limit_burst_multiplier", settings.abuse_rate_limit_burst_multiplier),
            "failure_mode_api": overrides.get("failure_mode_api", settings.abuse_rate_limit_backend_failure_mode_api or settings.abuse_rate_limit_backend_failure_mode),
            "failure_mode_management": overrides.get("failure_mode_management", settings.abuse_rate_limit_backend_failure_mode_management or settings.abuse_rate_limit_backend_failure_mode),
            "tenant_plan_default": overrides.get("tenant_plan_default", settings.abuse_tenant_plan_default),
            "tenant_plan_assignments_json": overrides.get("tenant_plan_assignments_json", settings.abuse_tenant_plan_assignments_json),
            "tenant_plan_limits_json": overrides.get("tenant_plan_limits_json", settings.abuse_tenant_plan_limits_json),
            "metrics_include_tenant_labels": overrides.get("metrics_include_tenant_labels", settings.abuse_metrics_include_tenant_labels),
            "metrics_tenant_label_mode": overrides.get("metrics_tenant_label_mode", settings.abuse_metrics_tenant_label_mode),
        }
        return ManagementConfigResponse("abuse", effective, overrides, applies_immediately=True, applies_on_restart=False)

    def update_abuse_config(self, payload: dict[str, object]) -> ManagementConfigResponse:
        sanitized = _sanitize(payload, ABUSE_ALLOWED_KEYS)
        _validate_abuse_payload(sanitized)
        self._repo.upsert_payload("abuse", sanitized)
        invalidate_abuse_override_cache()
        set_inprocess_abuse_override_payload(sanitized)
        return self.get_abuse_config()

    def get_backup_config(self) -> ManagementConfigResponse:
        settings = get_settings()
        overrides = self._repo.get_payload("backup")
        targets = _resolve_backup_targets(overrides=overrides, settings=settings)
        default_target_name = "default" if "default" in targets else (sorted(targets)[0] if targets else None)
        effective = {
            "output_dir": overrides.get("output_dir", settings.backup_output_dir),
            "retention_keep_last": overrides.get("retention_keep_last", settings.backup_retention_keep_last),
            "retention_max_age_days": overrides.get("retention_max_age_days", settings.backup_retention_max_age_days),
            "object_store_verify_restore": overrides.get("object_store_verify_restore", settings.backup_object_store_verify_restore),
            "require_encryption": overrides.get("require_encryption", bool(settings.backup_encryption_passphrase)),
            "default_label_prefix": overrides.get("default_label_prefix", settings.backup_default_label_prefix or settings.environment),
            "compose_service": overrides.get("compose_service", settings.backup_compose_service),
            "command_timeout_seconds": overrides.get("command_timeout_seconds", settings.backup_command_timeout_seconds),
            "target_database_url": sanitize_database_url(targets["default"]) if "default" in targets else None,
            "default_target_name": default_target_name,
            "target_names": sorted(targets),
            "configured_target_count": len(targets),
        }
        return ManagementConfigResponse("backup", effective, overrides, applies_immediately=False, applies_on_restart=False)

    def update_backup_config(self, payload: dict[str, object]) -> ManagementConfigResponse:
        sanitized = _sanitize(payload, BACKUP_ALLOWED_KEYS)
        _validate_backup_payload(sanitized)
        self._repo.upsert_payload("backup", sanitized)
        return self.get_backup_config()

    def get_observability_config(self) -> ManagementConfigResponse:
        settings = get_settings()
        overrides = self._repo.get_payload("observability")
        effective = {
            "api_availability_slo_target": overrides.get("api_availability_slo_target", settings.api_availability_slo_target),
            "api_latency_slo_target": overrides.get("api_latency_slo_target", settings.api_latency_slo_target),
            "api_latency_slo_seconds": overrides.get("api_latency_slo_seconds", settings.api_latency_slo_seconds),
            "metrics_enabled": overrides.get("metrics_enabled", settings.metrics_enabled),
            "worker_metrics_enabled": overrides.get("worker_metrics_enabled", settings.worker_metrics_enabled),
            "otel_enabled": overrides.get("otel_enabled", settings.otel_enabled),
        }
        return ManagementConfigResponse("observability", effective, overrides, applies_immediately=True, applies_on_restart=False)

    def update_observability_config(self, payload: dict[str, object]) -> ManagementConfigResponse:
        sanitized = _sanitize(payload, OBSERVABILITY_ALLOWED_KEYS)
        _validate_observability_payload(sanitized)
        self._repo.upsert_payload("observability", sanitized)
        return self.get_observability_config()

    def build_backup_drill_preview(self) -> dict[str, object]:
        config = self.get_backup_config().effective
        command = [
            "python",
            "scripts/postgres_backup_restore.py",
            "drill",
            "--output-dir",
            str(config["output_dir"]),
            "--label",
            str(config["default_label_prefix"]),
        ]
        if config.get("compose_service"):
            command.extend(["--docker-compose-service", str(config["compose_service"])])
        command.extend(["--command-timeout-seconds", str(config["command_timeout_seconds"])])
        return {
            "command": command,
            "effective_backup_config": config,
        }

    def build_backup_drill_execution_plan(
        self,
        *,
        target_name: str | None = None,
        label: str | None = None,
        restore_from_object_store: bool | None = None,
    ):
        settings = get_settings()
        overrides = self._repo.get_payload("backup")
        config = self.get_backup_config().effective
        targets = _resolve_backup_targets(overrides=overrides, settings=settings)
        resolved_target_name = (target_name or config.get("default_target_name") or "default").strip()
        if not resolved_target_name:
            raise ValueError("target_name must be a non-empty string")

        target_url = targets.get(resolved_target_name)
        if not target_url:
            if not targets:
                raise ValueError("backup drill target is not configured")
            available_targets = ", ".join(sorted(targets))
            raise ValueError(f"unknown target_name: {resolved_target_name}. Available targets: {available_targets}")

        resolved_compose_service = config.get("compose_service")
        if resolved_compose_service == "":
            resolved_compose_service = None

        resolved_encryption = settings.backup_encryption_passphrase if config.get("require_encryption") else None
        if config.get("require_encryption") and not resolved_encryption:
            raise ValueError("backup encryption is required but no passphrase is configured")

        resolved_restore_from_object_store = (
            bool(config.get("object_store_verify_restore"))
            if restore_from_object_store is None
            else bool(restore_from_object_store)
        )
        object_store = resolve_object_store_config()
        return self.BackupDrillExecutionPlanClass(
            target_name=resolved_target_name,
            source_url=settings.database_url,
            target_url=target_url,
            output_dir=self.PathClass(str(config["output_dir"])),
            label=label or str(config["default_label_prefix"]),
            compose_service=resolved_compose_service,
            encryption_passphrase=resolved_encryption,
            prune_keep_last=int(config["retention_keep_last"]),
            prune_max_age_days=int(config["retention_max_age_days"]),
            object_store=object_store,
            restore_from_object_store=resolved_restore_from_object_store,
            command_timeout_seconds=int(config["command_timeout_seconds"]),
        )
