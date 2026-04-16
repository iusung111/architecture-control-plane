from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import NotificationOutbox
from app.domain.enums import OutboxDeliveryState


class OutboxRepository:
    def __init__(self, db: Session):
        self._db = db

    def add(self, cycle_id: str | None, event_type: str, payload: dict, *, max_attempts: int = 5) -> NotificationOutbox:
        item = NotificationOutbox(
            outbox_id=str(uuid4()),
            cycle_id=cycle_id,
            event_type=event_type,
            payload=payload,
            next_attempt_at=datetime.now(timezone.utc),
            max_attempts=max_attempts,
        )
        self._db.add(item)
        return item

    def claim_pending(self, limit: int = 10) -> list[NotificationOutbox]:
        if self._supports_skip_locked():
            return self._claim_pending_with_skip_locked(limit=limit)
        return self._claim_pending_with_conditional_update(limit=limit)

    def _claim_pending_with_skip_locked(self, limit: int) -> list[NotificationOutbox]:
        now = datetime.now(timezone.utc)
        eligible_states = (OutboxDeliveryState.PENDING, OutboxDeliveryState.FAILED)
        items = list(
            self._db.execute(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.delivery_state.in_(eligible_states),
                    NotificationOutbox.next_attempt_at <= now,
                )
                .order_by(NotificationOutbox.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        for item in items:
            item.delivery_state = OutboxDeliveryState.CLAIMED
            item.updated_at = now
        if items:
            self._db.flush()
        return items

    def _claim_pending_with_conditional_update(self, limit: int) -> list[NotificationOutbox]:
        now = datetime.now(timezone.utc)
        eligible_states = (OutboxDeliveryState.PENDING, OutboxDeliveryState.FAILED)
        candidate_ids = list(
            self._db.execute(
                select(NotificationOutbox.outbox_id)
                .where(
                    NotificationOutbox.delivery_state.in_(eligible_states),
                    NotificationOutbox.next_attempt_at <= now,
                )
                .order_by(NotificationOutbox.created_at.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

        claimed_ids: list[str] = []
        for outbox_id in candidate_ids:
            result = self._db.execute(
                update(NotificationOutbox)
                .where(
                    NotificationOutbox.outbox_id == outbox_id,
                    NotificationOutbox.delivery_state.in_(eligible_states),
                )
                .values(
                    delivery_state=OutboxDeliveryState.CLAIMED,
                    updated_at=now,
                )
            )
            if result.rowcount == 1:
                claimed_ids.append(outbox_id)

        if not claimed_ids:
            return []

        return list(
            self._db.execute(
                select(NotificationOutbox)
                .where(NotificationOutbox.outbox_id.in_(claimed_ids))
                .order_by(NotificationOutbox.created_at.asc())
            )
            .scalars()
            .all()
        )

    def mark_delivered(self, item: NotificationOutbox) -> None:
        now = datetime.now(timezone.utc)
        item.delivery_state = OutboxDeliveryState.DELIVERED
        item.delivered_at = now
        item.last_error = None
        item.updated_at = now

    def mark_failed(self, item: NotificationOutbox, error: str, retryable: bool = True) -> None:
        now = datetime.now(timezone.utc)
        item.retry_count += 1
        item.last_error = error
        item.updated_at = now
        if retryable and item.retry_count < item.max_attempts:
            item.delivery_state = OutboxDeliveryState.FAILED
            item.next_attempt_at = now + self._backoff_for_attempt(item.retry_count)
        else:
            item.delivery_state = OutboxDeliveryState.DEAD_LETTERED
            item.dead_lettered_at = now

    def _supports_skip_locked(self) -> bool:
        bind = self._db.get_bind()
        return bind is not None and bind.dialect.name == 'postgresql'

    @staticmethod
    def _backoff_for_attempt(retry_count: int) -> timedelta:
        if retry_count <= 1:
            return timedelta(seconds=30)
        if retry_count == 2:
            return timedelta(minutes=2)
        return timedelta(minutes=10)
