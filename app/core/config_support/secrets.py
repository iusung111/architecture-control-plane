import os
from pathlib import Path

from .constants import SECRET_FILE_ENV_FIELD_MAP
from .model import Settings


def _read_secret_value(secret_path: str, *, env_name: str) -> str:
    path = Path(secret_path)
    if not path.exists():
        raise RuntimeError(f"invalid runtime configuration: {env_name}_FILE path does not exist: {path}")
    if not path.is_file():
        raise RuntimeError(f"invalid runtime configuration: {env_name}_FILE path is not a file: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"invalid runtime configuration: {env_name}_FILE path is empty: {path}")
    return value


def _secret_dir_candidates(base: Path, env_name: str, field_name: str):
    return (
        base / env_name,
        base / field_name,
        base / f"{env_name}.txt",
        base / f"{field_name}.txt",
    )


def resolve_secret_file_overrides(settings: Settings) -> dict[str, str]:
    if not settings.secrets_file_env_enabled:
        return {}

    overrides: dict[str, str] = {}
    for env_name, field_name in SECRET_FILE_ENV_FIELD_MAP.items():
        secret_path = os.getenv(f"{env_name}_FILE")
        if secret_path:
            overrides[field_name] = _read_secret_value(secret_path, env_name=env_name)

    secrets_dir = settings.secrets_dir or os.getenv("SECRETS_DIR")
    if not secrets_dir:
        return overrides

    base = Path(secrets_dir)
    if not base.exists():
        raise RuntimeError(f"invalid runtime configuration: SECRETS_DIR path does not exist: {base}")
    if not base.is_dir():
        raise RuntimeError(f"invalid runtime configuration: SECRETS_DIR path is not a directory: {base}")

    for env_name, field_name in SECRET_FILE_ENV_FIELD_MAP.items():
        if field_name in overrides:
            continue
        for candidate in _secret_dir_candidates(base, env_name, field_name):
            if candidate.exists():
                overrides[field_name] = _read_secret_value(str(candidate), env_name=env_name)
                break
    return overrides
