from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from .common import RoutingDecision


class SelectionAssignmentMixin:
    def preview_assignment(
        self,
        *,
        prompt_type: str,
        complexity: str,
        review_required: bool,
        cycle_id: str | None = None,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, object]:
        complexity_key = self._normalize_complexity(complexity)
        assignment_group_id = uuid4().hex
        work = self._select_provider(
            stage="work",
            complexity=complexity_key,
            exclude_provider=None,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        review: RoutingDecision | None = None
        if review_required:
            review = self._select_provider(
                stage="review",
                complexity=complexity_key,
                exclude_provider=work.provider if work else None,
                source_session_id=work.session_id if work else None,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if review is None and work is not None:
                review = self._select_provider(
                    stage="review",
                    complexity=complexity_key,
                    exclude_provider=None,
                    source_session_id=work.session_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
                if review is not None:
                    review.rationale["same_provider_fallback"] = True
        return {
            "cycle_id": cycle_id,
            "prompt_type": prompt_type,
            "complexity": complexity_key,
            "assignment_group_id": assignment_group_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "work": asdict(work) if work else None,
            "review": asdict(review) if review else None,
        }

    def assign_for_job(
        self,
        *,
        cycle_id: str,
        prompt_type: str,
        complexity: str,
        review_required: bool,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, object]:
        preview = self.preview_assignment(
            prompt_type=prompt_type,
            complexity=complexity,
            review_required=review_required,
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        work = preview["work"]
        review = preview["review"]
        assignment_group_id = preview["assignment_group_id"]
        if work:
            self._usage.record(work["provider"], "work")
            self._decisions.add(
                cycle_id=cycle_id,
                assignment_group_id=assignment_group_id,
                prompt_type=prompt_type,
                stage="work",
                complexity=preview["complexity"],
                selected_provider=work["provider"],
                selected_model=work["model"],
                selected_usage_mode=work["usage_mode"],
                session_id=work["session_id"],
                source_session_id=work["source_session_id"],
                requires_fresh_session=work["requires_fresh_session"],
                remaining_requests=work["remaining_requests"],
                paired_provider=review["provider"] if review else None,
                rationale=work["rationale"],
            )
        if review:
            self._usage.record(review["provider"], "review")
            self._decisions.add(
                cycle_id=cycle_id,
                assignment_group_id=assignment_group_id,
                prompt_type=prompt_type,
                stage="review",
                complexity=preview["complexity"],
                selected_provider=review["provider"],
                selected_model=review["model"],
                selected_usage_mode=review["usage_mode"],
                session_id=review["session_id"],
                source_session_id=review["source_session_id"],
                requires_fresh_session=review["requires_fresh_session"],
                remaining_requests=review["remaining_requests"],
                paired_provider=work["provider"] if work else None,
                rationale=review["rationale"],
            )
        self._db.flush()
        return preview
