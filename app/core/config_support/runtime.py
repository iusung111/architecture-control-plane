from functools import lru_cache

from .model import Settings
from .secrets import resolve_secret_file_overrides
from .validation import validate_runtime_settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    overrides = resolve_secret_file_overrides(settings)
    if overrides:
        settings = settings.model_copy(update=overrides)
    return settings


def ensure_runtime_settings_valid(settings: Settings) -> None:
    errors = validate_runtime_settings(settings)
    if errors:
        raise RuntimeError("invalid runtime configuration: " + "; ".join(errors))
