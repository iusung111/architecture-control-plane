from __future__ import annotations

from uuid import uuid4

from .common import (
    LLMComplexity,
    LLMProvider,
    LLMSessionMode,
    LLMStage,
    ProviderStatus,
    RoutingDecision,
    _ALLOWED_PROVIDERS,
    _STAGE_COMPLEXITY_RANKS,
    UTC,
    datetime,
    provider_default_model,
    provider_documented_daily_limit,
    provider_free_limit,
    provider_is_configured,
)


class SelectionRoutingMixin:
    def _ensure_policy_rows(self) -> None:
        changed = False
        quota_changed = False
        for provider in _ALLOWED_PROVIDERS:
            if self._policies.get(provider) is not None:
                continue
            configured = provider_is_configured(self._settings, provider)
            self._policies.upsert(
                provider_name=provider,
                enabled=configured,
                allow_work=configured,
                allow_review=configured and provider != "cloudflare_workers_ai",
                usage_mode=self._settings.llm_usage_mode,
                priority=self._default_priority(provider),
                daily_request_limit_override=None,
            )
            changed = True
        if changed:
            self._db.flush()
        for provider in _ALLOWED_PROVIDERS:
            before = self._quota.get(provider)
            self._ensure_documented_quota_snapshot(provider)
            after = self._quota.get(provider)
            if before is None and after is not None:
                quota_changed = True
        if changed or quota_changed:
            self._db.flush()

    def _ensure_documented_quota_snapshot(self, provider: LLMProvider) -> None:
        if self._quota.get(provider) is not None:
            return
        daily_limit = provider_documented_daily_limit(self._settings, provider)
        if daily_limit is None:
            return
        self._quota.upsert(
            provider_name=provider,
            source="documented_defaults",
            requests_limit=None,
            requests_remaining=None,
            requests_reset_at=None,
            tokens_limit=None,
            tokens_remaining=None,
            tokens_reset_at=None,
            daily_request_limit=daily_limit,
            daily_requests_used=0,
            daily_requests_remaining=daily_limit,
            spend_limit_usd=None,
            spend_used_usd=None,
            spend_remaining_usd=None,
            usage_tokens_input=None,
            usage_tokens_output=None,
            raw_payload={"documented_daily_limit": daily_limit},
        )

    def _provider_status(
        self,
        provider: LLMProvider,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> ProviderStatus:
        policy = self._policies.get(provider)
        if policy is None:
            raise RuntimeError(f"missing policy for provider '{provider}'")
        configured = provider_is_configured(self._settings, provider)
        usage = self._usage.get_for_date(provider, datetime.now(UTC).date().isoformat())
        used_today = usage.total_requests if usage else 0
        override_project = self._overrides.get("project", project_id, provider) if project_id else None
        override_tenant = self._overrides.get("tenant", tenant_id, provider) if tenant_id else None
        effective = {
            "enabled": policy.enabled,
            "allow_work": policy.allow_work,
            "allow_review": policy.allow_review,
            "usage_mode": policy.usage_mode,
            "priority": policy.priority,
            "daily_request_limit_override": policy.daily_request_limit_override,
            "effective_scope": "global",
        }
        for scope_name, override in (("tenant", override_tenant), ("project", override_project)):
            if override is None:
                continue
            if override.enabled_override is not None:
                effective["enabled"] = override.enabled_override
            if override.allow_work_override is not None:
                effective["allow_work"] = override.allow_work_override
            if override.allow_review_override is not None:
                effective["allow_review"] = override.allow_review_override
            if override.usage_mode_override is not None:
                effective["usage_mode"] = override.usage_mode_override
            effective["priority"] = int(effective["priority"]) + override.priority_offset
            if override.daily_request_limit_override is not None:
                effective["daily_request_limit_override"] = override.daily_request_limit_override
            effective["effective_scope"] = scope_name
        daily_limit = effective["daily_request_limit_override"]
        if daily_limit is None:
            daily_limit = provider_free_limit(self._settings, provider) if effective["usage_mode"] == "free_only" else None
        remaining = None if daily_limit is None else max(int(daily_limit) - used_today, 0)
        snapshot = self._quota.get(provider)
        return ProviderStatus(
            provider=provider,
            configured=configured,
            enabled=bool(effective["enabled"]) and configured,
            allow_work=bool(effective["allow_work"]),
            allow_review=bool(effective["allow_review"]),
            usage_mode=str(effective["usage_mode"]),
            priority=int(effective["priority"]),
            daily_limit=daily_limit,
            used_today=used_today,
            remaining_today=remaining,
            model=provider_default_model(self._settings, provider),
            external_quota_source=snapshot.source if snapshot else None,
            external_requests_limit=snapshot.requests_limit if snapshot else None,
            external_requests_remaining=snapshot.requests_remaining if snapshot else None,
            external_tokens_limit=snapshot.tokens_limit if snapshot else None,
            external_tokens_remaining=snapshot.tokens_remaining if snapshot else None,
            external_daily_limit=snapshot.daily_request_limit if snapshot else None,
            external_daily_used=snapshot.daily_requests_used if snapshot else None,
            external_daily_remaining=snapshot.daily_requests_remaining if snapshot else None,
            external_spend_limit_usd=snapshot.spend_limit_usd if snapshot else None,
            external_spend_used_usd=snapshot.spend_used_usd if snapshot else None,
            external_spend_remaining_usd=snapshot.spend_remaining_usd if snapshot else None,
            external_usage_tokens_input=snapshot.usage_tokens_input if snapshot else None,
            external_usage_tokens_output=snapshot.usage_tokens_output if snapshot else None,
            external_observed_at=snapshot.observed_at.isoformat() if snapshot and snapshot.observed_at else None,
            effective_scope=str(effective["effective_scope"]),
        )

    def _select_provider(
        self,
        *,
        stage: LLMStage,
        complexity: LLMComplexity,
        exclude_provider: str | None,
        source_session_id: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> RoutingDecision | None:
        statuses = self.list_provider_statuses(tenant_id=tenant_id, project_id=project_id)
        preferred_order = _STAGE_COMPLEXITY_RANKS[stage][complexity]
        alternatives = [s for s in statuses if self._eligible_for_stage(s, stage)]
        if exclude_provider is not None:
            alternatives_without_excluded = [s for s in alternatives if s.provider != exclude_provider]
            if alternatives_without_excluded:
                alternatives = alternatives_without_excluded
            else:
                return None
        scored: list[tuple[float, ProviderStatus]] = []
        for status in alternatives:
            if status.provider not in preferred_order:
                continue
            rank_index = preferred_order.index(status.provider)
            score = (len(preferred_order) - rank_index) * 100 + status.priority
            if status.remaining_today is None:
                score += 50
            elif status.daily_limit and status.daily_limit > 0:
                score += (status.remaining_today / status.daily_limit) * 25
            if status.external_daily_remaining is not None and status.external_daily_limit:
                score += (status.external_daily_remaining / status.external_daily_limit) * 20
            if status.external_requests_remaining is not None:
                score += min(status.external_requests_remaining, 100) / 10
            scored.append((score, status))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        _, winner = scored[0]
        session_id = uuid4().hex
        session_mode: LLMSessionMode = "job_session" if stage == "work" else "fresh_review_session"
        requires_fresh_session = stage == "review"
        rationale: dict[str, object] = {
            "selected_by": "llm_routing_service",
            "stage": stage,
            "complexity": complexity,
            "used_today": winner.used_today,
            "daily_limit": winner.daily_limit,
            "remaining_today": winner.remaining_today,
            "priority": winner.priority,
            "exclude_provider": exclude_provider,
            "effective_scope": winner.effective_scope,
            "external_quota_source": winner.external_quota_source,
            "external_daily_remaining": winner.external_daily_remaining,
            "external_requests_remaining": winner.external_requests_remaining,
            "session_policy": session_mode,
            "session_state_transfer": "none" if requires_fresh_session else "new_job_session",
            "session_isolation_reason": (
                "review must run in a fresh session to avoid self-confirming hallucination from retained work context"
                if requires_fresh_session
                else "work starts in a dedicated job session"
            ),
        }
        return RoutingDecision(
            stage=stage,
            complexity=complexity,
            provider=winner.provider,
            model=winner.model,
            usage_mode=winner.usage_mode,
            session_id=session_id,
            session_mode=session_mode,
            source_session_id=source_session_id if requires_fresh_session else None,
            requires_fresh_session=requires_fresh_session,
            remaining_requests=winner.remaining_today,
            rationale=rationale,
        )
