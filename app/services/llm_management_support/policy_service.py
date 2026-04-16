from __future__ import annotations


from .common import (
    LLMProvider,
    LLMScopeType,
    ProviderStatus,
    ScopeOverrideStatus,
    _ALLOWED_PROVIDERS,
    fetch_provider_quota_snapshot,
)


class PolicyServiceMixin:
    def list_provider_statuses(
        self,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> list[ProviderStatus]:
        self._ensure_policy_rows()
        statuses = [self._provider_status(provider, tenant_id=tenant_id, project_id=project_id) for provider in _ALLOWED_PROVIDERS]
        return sorted(statuses, key=lambda item: (not item.enabled, -item.priority, item.provider))

    def list_scope_overrides(self, scope_type: LLMScopeType, scope_id: str) -> list[ScopeOverrideStatus]:
        return [
            ScopeOverrideStatus(
                scope_type=item.scope_type,
                scope_id=item.scope_id,
                provider=item.provider_name,
                enabled_override=item.enabled_override,
                allow_work_override=item.allow_work_override,
                allow_review_override=item.allow_review_override,
                usage_mode_override=item.usage_mode_override,
                priority_offset=item.priority_offset,
                daily_request_limit_override=item.daily_request_limit_override,
            )
            for item in self._overrides.list_for_scope(scope_type, scope_id)
        ]

    def update_policy(
        self,
        provider: LLMProvider,
        *,
        enabled: bool | None = None,
        allow_work: bool | None = None,
        allow_review: bool | None = None,
        usage_mode: str | None = None,
        priority: int | None = None,
        daily_request_limit_override: int | None = None,
    ) -> ProviderStatus:
        if provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"unsupported provider '{provider}'")
        self._ensure_policy_rows()
        existing = self._policies.get(provider)
        assert existing is not None
        self._policies.upsert(
            provider_name=provider,
            enabled=existing.enabled if enabled is None else enabled,
            allow_work=existing.allow_work if allow_work is None else allow_work,
            allow_review=existing.allow_review if allow_review is None else allow_review,
            usage_mode=existing.usage_mode if usage_mode is None else usage_mode,
            priority=existing.priority if priority is None else priority,
            daily_request_limit_override=(
                existing.daily_request_limit_override if daily_request_limit_override is None else daily_request_limit_override
            ),
        )
        self._db.flush()
        return self._provider_status(provider)

    def upsert_scope_override(
        self,
        *,
        scope_type: LLMScopeType,
        scope_id: str,
        provider: LLMProvider,
        enabled_override: bool | None = None,
        allow_work_override: bool | None = None,
        allow_review_override: bool | None = None,
        usage_mode_override: str | None = None,
        priority_offset: int | None = None,
        daily_request_limit_override: int | None = None,
    ) -> ScopeOverrideStatus:
        if provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"unsupported provider '{provider}'")
        override = self._overrides.upsert(
            scope_type=scope_type,
            scope_id=scope_id,
            provider_name=provider,
            enabled_override=enabled_override,
            allow_work_override=allow_work_override,
            allow_review_override=allow_review_override,
            usage_mode_override=usage_mode_override,
            priority_offset=0 if priority_offset is None else priority_offset,
            daily_request_limit_override=daily_request_limit_override,
        )
        self._db.flush()
        return ScopeOverrideStatus(
            scope_type=override.scope_type,
            scope_id=override.scope_id,
            provider=override.provider_name,
            enabled_override=override.enabled_override,
            allow_work_override=override.allow_work_override,
            allow_review_override=override.allow_review_override,
            usage_mode_override=override.usage_mode_override,
            priority_offset=override.priority_offset,
            daily_request_limit_override=override.daily_request_limit_override,
        )

    def refresh_provider_quota(self, provider: LLMProvider) -> ProviderStatus:
        if provider not in _ALLOWED_PROVIDERS:
            raise ValueError(f"unsupported provider '{provider}'")
        self._ensure_policy_rows()
        snapshot_payload = fetch_provider_quota_snapshot(self._settings, provider)
        if snapshot_payload is not None:
            self._quota.upsert(
                provider_name=provider,
                source=snapshot_payload.source,
                requests_limit=snapshot_payload.requests_limit,
                requests_remaining=snapshot_payload.requests_remaining,
                requests_reset_at=snapshot_payload.requests_reset_at,
                tokens_limit=snapshot_payload.tokens_limit,
                tokens_remaining=snapshot_payload.tokens_remaining,
                tokens_reset_at=snapshot_payload.tokens_reset_at,
                daily_request_limit=snapshot_payload.daily_request_limit,
                daily_requests_used=snapshot_payload.daily_requests_used,
                daily_requests_remaining=snapshot_payload.daily_requests_remaining,
                spend_limit_usd=snapshot_payload.spend_limit_usd,
                spend_used_usd=snapshot_payload.spend_used_usd,
                spend_remaining_usd=snapshot_payload.spend_remaining_usd,
                usage_tokens_input=snapshot_payload.usage_tokens_input,
                usage_tokens_output=snapshot_payload.usage_tokens_output,
                raw_payload=snapshot_payload.raw_payload or {},
            )
        else:
            self._ensure_documented_quota_snapshot(provider)
        self._db.flush()
        return self._provider_status(provider)
