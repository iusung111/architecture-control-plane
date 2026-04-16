
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ManagementConfigDocument


class ManagementConfigRepository:
    def __init__(self, db: Session):
        self._db = db

    def get(self, namespace: str) -> ManagementConfigDocument | None:
        return self._db.get(ManagementConfigDocument, namespace)

    def get_payload(self, namespace: str) -> dict:
        record = self.get(namespace)
        return dict(record.payload or {}) if record else {}

    def upsert_payload(self, namespace: str, payload: dict) -> ManagementConfigDocument:
        record = self.get(namespace)
        if record is None:
            record = ManagementConfigDocument(namespace=namespace, payload=payload)
            self._db.add(record)
        else:
            record.payload = payload
        self._db.flush()
        return record
