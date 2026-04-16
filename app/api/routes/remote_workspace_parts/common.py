from __future__ import annotations




def _normalize_snapshot(data: dict) -> dict:
    return {
        **data,
        "patch_present": bool(data.get("patch") or data.get("patch_stack")),
        "artifact_count": len(data.get("artifacts", [])),
        "artifact_history": data.get("artifact_history") or data.get("artifacts") or [],
    }
