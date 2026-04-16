from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    LLMDailyUsage,
    LLMProviderPolicy,
    LLMProviderQuotaSnapshot,
    LLMRoutingDecision,
    LLMScopeOverride,
)


class LLMProviderPolicyRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_all(self) -> list[LLMProviderPolicy]:
        return list(self._db.scalars(select(LLMProviderPolicy).order_by(LLMProviderPolicy.provider_name)))

    def get(self, provider_name: str) -> LLMProviderPolicy | None:
        return self._db.get(LLMProviderPolicy, provider_name)

    def upsert(
        self,
        *,
        provider_name: str,
        enabled: bool,
        allow_work: bool,
        allow_review: bool,
        usage_mode: str,
        priority: int,
        daily_request_limit_override: int | None,
    ) -> LLMProviderPolicy:
        policy = self.get(provider_name)
        if policy is None:
            policy = LLMProviderPolicy(provider_name=provider_name)
            self._db.add(policy)
        policy.enabled = enabled
        policy.allow_work = allow_work
        policy.allow_review = allow_review
        policy.usage_mode = usage_mode
        policy.priority = priority
        policy.daily_request_limit_override = daily_request_limit_override
        return policy


class LLMScopeOverrideRepository:
    def __init__(self, db: Session):
        self._db = db

    def list_for_scope(self, scope_type: str, scope_id: str) -> list[LLMScopeOverride]:
        stmt = (
            select(LLMScopeOverride)
            .where(LLMScopeOverride.scope_type == scope_type, LLMScopeOverride.scope_id == scope_id)
            .order_by(LLMScopeOverride.provider_name)
        )
        return list(self._db.scalars(stmt))

    def get(self, scope_type: str, scope_id: str, provider_name: str) -> LLMScopeOverride | None:
        stmt = select(LLMScopeOverride).where(
            LLMScopeOverride.scope_type == scope_type,
            LLMScopeOverride.scope_id == scope_id,
            LLMScopeOverride.provider_name == provider_name,
        )
        return self._db.scalar(stmt)

    def upsert(
        self,
        *,
        scope_type: str,
        scope_id: str,
        provider_name: str,
        enabled_override: bool | None,
        allow_work_override: bool | None,
        allow_review_override: bool | None,
        usage_mode_override: str | None,
        priority_offset: int,
        daily_request_limit_override: int | None,
    ) -> LLMScopeOverride:
        override = self.get(scope_type, scope_id, provider_name)
        if override is None:
            override = LLMScopeOverride(
                override_id=uuid4().hex,
                scope_type=scope_type,
                scope_id=scope_id,
                provider_name=provider_name,
            )
            self._db.add(override)
        override.enabled_override = enabled_override
        override.allow_work_override = allow_work_override
        override.allow_review_override = allow_review_override
        override.usage_mode_override = usage_mode_override
        override.priority_offset = priority_offset
        override.daily_request_limit_override = daily_request_limit_override
        return override


class LLMProviderQuotaSnapshotRepository:
    def __init__(self, db: Session):
        self._db = db

    def get(self, provider_name: str) -> LLMProviderQuotaSnapshot | None:
        return self._db.get(LLMProviderQuotaSnapshot, provider_name)

    def list_all(self) -> list[LLMProviderQuotaSnapshot]:
        return list(self._db.scalars(select(LLMProviderQuotaSnapshot).order_by(LLMProviderQuotaSnapshot.provider_name)))

    def upsert(
        self,
        *,
        provider_name: str,
        source: str,
        requests_limit: int | None,
        requests_remaining: int | None,
        requests_reset_at,
        tokens_limit: int | None,
        tokens_remaining: int | None,
        tokens_reset_at,
        daily_request_limit: int | None,
        daily_requests_used: int | None,
        daily_requests_remaining: int | None,
        spend_limit_usd: float | None,
        spend_used_usd: float | None,
        spend_remaining_usd: float | None,
        usage_tokens_input: int | None,
        usage_tokens_output: int | None,
        raw_payload: dict,
    ) -> LLMProviderQuotaSnapshot:
        snapshot = self.get(provider_name)
        if snapshot is None:
            snapshot = LLMProviderQuotaSnapshot(provider_name=provider_name)
            self._db.add(snapshot)
        snapshot.source = source
        snapshot.observed_at = datetime.now(UTC)
        snapshot.requests_limit = requests_limit
        snapshot.requests_remaining = requests_remaining
        snapshot.requests_reset_at = requests_reset_at
        snapshot.tokens_limit = tokens_limit
        snapshot.tokens_remaining = tokens_remaining
        snapshot.tokens_reset_at = tokens_reset_at
        snapshot.daily_request_limit = daily_request_limit
        snapshot.daily_requests_used = daily_requests_used
        snapshot.daily_requests_remaining = daily_requests_remaining
        snapshot.spend_limit_usd = spend_limit_usd
        snapshot.spend_used_usd = spend_used_usd
        snapshot.spend_remaining_usd = spend_remaining_usd
        snapshot.usage_tokens_input = usage_tokens_input
        snapshot.usage_tokens_output = usage_tokens_output
        snapshot.raw_payload = raw_payload
        return snapshot


class LLMDailyUsageRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_for_date(self, provider_name: str, usage_date: str) -> LLMDailyUsage | None:
        stmt = select(LLMDailyUsage).where(
            LLMDailyUsage.provider_name == provider_name,
            LLMDailyUsage.usage_date == usage_date,
        )
        return self._db.scalar(stmt)

    def get_or_create(self, provider_name: str, usage_date: str) -> LLMDailyUsage:
        for pending in self._db.new:
            if isinstance(pending, LLMDailyUsage) and pending.provider_name == provider_name and pending.usage_date == usage_date:
                return pending
        existing = self.get_for_date(provider_name, usage_date)
        if existing is not None:
            return existing
        usage = LLMDailyUsage(
            usage_id=uuid4().hex,
            provider_name=provider_name,
            usage_date=usage_date,
            work_requests=0,
            review_requests=0,
            total_requests=0,
        )
        self._db.add(usage)
        return usage

    def record(self, provider_name: str, stage: str, count: int = 1) -> LLMDailyUsage:
        usage_date = datetime.now(UTC).date().isoformat()
        usage = self.get_or_create(provider_name, usage_date)
        usage.total_requests += count
        if stage == "review":
            usage.review_requests += count
        else:
            usage.work_requests += count
        return usage


class LLMRoutingDecisionRepository:
    def __init__(self, db: Session):
        self._db = db

    def add(
        self,
        *,
        cycle_id: str | None,
        assignment_group_id: str,
        prompt_type: str,
        stage: str,
        complexity: str,
        selected_provider: str,
        selected_model: str,
        selected_usage_mode: str,
        session_id: str,
        source_session_id: str | None,
        requires_fresh_session: bool,
        remaining_requests: int | None,
        paired_provider: str | None,
        rationale: dict,
    ) -> LLMRoutingDecision:
        decision = LLMRoutingDecision(
            routing_decision_id=uuid4().hex,
            cycle_id=cycle_id,
            assignment_group_id=assignment_group_id,
            prompt_type=prompt_type,
            stage=stage,
            complexity=complexity,
            selected_provider=selected_provider,
            selected_model=selected_model,
            selected_usage_mode=selected_usage_mode,
            session_id=session_id,
            source_session_id=source_session_id,
            requires_fresh_session=requires_fresh_session,
            remaining_requests=remaining_requests,
            paired_provider=paired_provider,
            rationale=rationale,
        )
        self._db.add(decision)
        return decision
