from __future__ import annotations

import json
import os
from pathlib import Path


def build_policy(*, expiration_days: int, prefix: str | None = None) -> dict:
    rule = {
        "ID": "acp-backup-expiration",
        "Status": "Enabled",
        "Filter": {"Prefix": (prefix or "").strip("/") + ("/" if prefix and not prefix.endswith("/") else "")},
        "Expiration": {"Days": expiration_days},
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
        "NoncurrentVersionExpiration": {"NoncurrentDays": expiration_days},
    }
    return {"Rules": [rule]}


def main() -> int:
    expiration_days = int(
        os.getenv("BACKUP_S3_LIFECYCLE_EXPIRATION_DAYS")
        or os.getenv("BACKUP_RETENTION_MAX_AGE_DAYS")
        or "30"
    )
    prefix = os.getenv("BACKUP_S3_PREFIX", "")
    output_path = Path(os.getenv("BACKUP_S3_LIFECYCLE_POLICY_PATH", "deploy/object_storage/s3-lifecycle-policy.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    policy = build_policy(expiration_days=expiration_days, prefix=prefix)
    output_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(policy, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
