from __future__ import annotations

from app.core.telemetry_support import tracing as tracing_support
from app.core.telemetry_support import common as telemetry_common

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bootstrap.lifespan import lifespan
from app.core.auth_support.bearer import (
    authenticate_bearer_token,
    claims_to_auth_context,
    coerce_audience,
    coerce_role,
)
from app.core.auth_support.models import AuthContext, AuthError
from app.core.config import Settings
from app.ops.postgres_backup_restore_support import cli as backup_cli


class _FakeParser:
    def __init__(self, args):
        self._args = args

    def parse_args(self, argv=None):
        return self._args

    def error(self, message: str):
        raise RuntimeError(message)


@dataclass(frozen=True)
class _Artifact:
    metadata: dict[str, object]


def _settings(**overrides) -> Settings:
    data = {
        "auth_jwt_secret": "secret",
        "auth_jwt_issuer": "issuer",
        "auth_jwt_audience": "aud",
        "auth_required_role_claim": "role",
        "auth_jwt_allowed_algorithms": "HS256,RS256",
    }
    data.update(overrides)
    return Settings(**data)


def test_coerce_audience_handles_common_shapes() -> None:
    assert coerce_audience(None) == set()
    assert coerce_audience("api") == {"api"}
    assert coerce_audience(["api", 2]) == {"api", "2"}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"role": "admin"}, "admin"),
        ({"roles": ["editor", "viewer"]}, "editor"),
        ({"realm_access": {"roles": ["auditor"]}}, "auditor"),
    ],
)
def test_coerce_role_uses_supported_claim_shapes(payload: dict[str, object], expected: str) -> None:
    assert coerce_role(payload, _settings()) == expected


def test_claims_to_auth_context_validates_subject_and_tenant() -> None:
    settings = _settings()
    context = claims_to_auth_context({"sub": "user-1", "role": "admin", "tenant_id": "tenant-a"}, settings)

    assert context == AuthContext(user_id="user-1", role="admin", tenant_id="tenant-a")

    with pytest.raises(AuthError, match="missing sub claim"):
        claims_to_auth_context({"role": "admin"}, settings)

    with pytest.raises(AuthError, match="invalid tenant claim"):
        claims_to_auth_context({"sub": "user-1", "role": "admin", "tenant_id": 123}, settings)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"other": "value"}, "missing role claim"),
        (None, "invalid aud claim"),
    ],
)
def test_auth_helpers_raise_expected_errors(payload, message: str) -> None:
    if payload is None:
        with pytest.raises(AuthError, match=message):
            coerce_audience(3.14)
        return

    with pytest.raises(AuthError, match=message):
        coerce_role(payload, _settings())


def test_authenticate_bearer_token_rejects_missing_secret() -> None:
    with pytest.raises(AuthError, match="server auth configuration is incomplete"):
        authenticate_bearer_token("token", _settings(auth_jwt_secret=None))


def test_authenticate_bearer_token_rejects_unsupported_header_algorithm(monkeypatch) -> None:
    monkeypatch.setattr(backup_cli.importlib, "import_module", backup_cli.importlib.import_module)
    settings = _settings(auth_jwt_allowed_algorithms="HS256")
    monkeypatch.setattr("app.core.auth_support.bearer.jwt.get_unverified_header", lambda token: {"alg": "HS512"})

    with pytest.raises(AuthError, match="unsupported bearer token algorithm"):
        authenticate_bearer_token("token", settings)


def test_authenticate_bearer_token_wraps_decode_errors(monkeypatch) -> None:
    settings = _settings()
    monkeypatch.setattr("app.core.auth_support.bearer.jwt.get_unverified_header", lambda token: {"alg": "HS256"})
    monkeypatch.setattr("app.core.auth_support.bearer.jwt.decode", lambda *a, **k: "not-a-dict")

    with pytest.raises(AuthError, match="invalid token claims"):
        authenticate_bearer_token("token", settings)


@pytest.mark.asyncio
async def test_lifespan_initializes_and_shuts_down_in_order(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    settings = object()

    monkeypatch.setattr("app.bootstrap.lifespan.get_settings", lambda: settings)
    monkeypatch.setattr("app.bootstrap.lifespan.ensure_runtime_settings_valid", lambda value: calls.append(("validate", value)))
    monkeypatch.setattr("app.bootstrap.lifespan.initialize_tracing", lambda: calls.append(("tracing", None)))
    monkeypatch.setattr("app.bootstrap.lifespan.initialize_rate_limit_backend", lambda value: calls.append(("rate_limit", value)))
    monkeypatch.setattr("app.bootstrap.lifespan.shutdown_tracing", lambda: calls.append(("shutdown_tracing", None)))
    monkeypatch.setattr("app.bootstrap.lifespan.reset_rate_limits", lambda: calls.append(("reset_rate_limits", None)))
    monkeypatch.setattr("app.bootstrap.lifespan.dispose_db_resources", lambda: calls.append(("dispose_db_resources", None)))

    async with lifespan(SimpleNamespace()):
        calls.append(("inside", None))

    assert calls == [
        ("validate", settings),
        ("tracing", None),
        ("rate_limit", settings),
        ("inside", None),
        ("shutdown_tracing", None),
        ("reset_rate_limits", None),
        ("dispose_db_resources", None),
    ]


def test_backup_cli_resolve_database_url_from_argument_and_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://from-env")

    assert backup_cli._resolve_database_url("postgres://from-arg", "DATABASE_URL") == "postgres://from-arg"
    assert backup_cli._resolve_database_url(None, "DATABASE_URL") == "postgres://from-env"

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="Missing database url"):
        backup_cli._resolve_database_url(None, "DATABASE_URL")


def test_backup_cli_build_parser_reads_environment_defaults(monkeypatch) -> None:
    monkeypatch.setenv("BACKUP_OUTPUT_DIR", "/tmp/backups")
    monkeypatch.setenv("BACKUP_RETENTION_KEEP_LAST", "4")
    monkeypatch.setenv("BACKUP_RETENTION_MAX_AGE_DAYS", "14")

    parser = backup_cli.build_parser()
    args = parser.parse_args(["backup", "--database-url", "postgres://db"])

    assert args.output_dir == "/tmp/backups"
    assert args.prune_keep_last == 4
    assert args.prune_max_age_days == 14


@pytest.mark.parametrize(
    ("args", "module_result", "expected_substring"),
    [
        (
            SimpleNamespace(
                command="backup",
                database_url="postgres://db",
                output_dir="/tmp/out",
                label="nightly",
                docker_compose_service=None,
                encryption_passphrase=None,
                prune_keep_last=2,
                prune_max_age_days=5,
                object_store_bucket=None,
                object_store_prefix=None,
                object_store_endpoint_url=None,
                object_store_region=None,
                object_store_access_key_id=None,
                object_store_secret_access_key=None,
                object_store_session_token=None,
                object_store_force_path_style=False,
                command_timeout_seconds=90,
            ),
            _Artifact({"artifact": "backup"}),
            '"artifact": "backup"',
        ),
        (
            SimpleNamespace(
                command="restore",
                database_url="postgres://target",
                backup_file="backup.dump",
                docker_compose_service=None,
                recreate_target_database=True,
                encryption_passphrase="pw",
                object_store_bucket=None,
                object_store_prefix=None,
                object_store_endpoint_url=None,
                object_store_region=None,
                object_store_access_key_id=None,
                object_store_secret_access_key=None,
                object_store_session_token=None,
                object_store_force_path_style=False,
                command_timeout_seconds=90,
            ),
            {"status": "restored"},
            '"status": "restored"',
        ),
        (
            SimpleNamespace(
                command="drill",
                source_database_url="postgres://source",
                target_database_url="postgres://target",
                output_dir="/tmp/out",
                label="drill",
                docker_compose_service=None,
                report_file="/tmp/report.json",
                encryption_passphrase=None,
                prune_keep_last=1,
                prune_max_age_days=None,
                object_store_bucket=None,
                object_store_prefix=None,
                object_store_endpoint_url=None,
                object_store_region=None,
                object_store_access_key_id=None,
                object_store_secret_access_key=None,
                object_store_session_token=None,
                object_store_force_path_style=False,
                restore_from_object_store=True,
                command_timeout_seconds=90,
            ),
            {"status": "drilled"},
            '"status": "drilled"',
        ),
        (
            SimpleNamespace(
                command="prune",
                output_dir="/tmp/out",
                keep_last=3,
                max_age_days=7,
                object_store_bucket=None,
                object_store_prefix=None,
                object_store_endpoint_url=None,
                object_store_region=None,
                object_store_access_key_id=None,
                object_store_secret_access_key=None,
                object_store_session_token=None,
                object_store_force_path_style=False,
            ),
            SimpleNamespace(deleted_files=["a.dump"], kept_sets=["keep"], pruned_sets=["old"]),
            '"deleted_files": [',
        ),
    ],
)
def test_backup_cli_main_dispatches_core_commands(monkeypatch, capsys, args, module_result, expected_substring: str) -> None:
    calls: list[tuple[str, tuple, dict]] = []

    class FakeModule:
        @staticmethod
        def resolve_object_store_config(**kwargs):
            calls.append(("resolve_object_store_config", (), kwargs))
            return {"bucket": kwargs.get("bucket")}

        @staticmethod
        def backup_database(*call_args, **call_kwargs):
            calls.append(("backup_database", call_args, call_kwargs))
            return module_result

        @staticmethod
        def restore_database(*call_args, **call_kwargs):
            calls.append(("restore_database", call_args, call_kwargs))
            return module_result

        @staticmethod
        def run_backup_restore_drill(*call_args, **call_kwargs):
            calls.append(("run_backup_restore_drill", call_args, call_kwargs))
            return module_result

        @staticmethod
        def prune_backup_artifacts(*call_args, **call_kwargs):
            calls.append(("prune_backup_artifacts", call_args, call_kwargs))
            return module_result

    monkeypatch.setattr(backup_cli, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(backup_cli, "_module", lambda: FakeModule)

    assert backup_cli.main([]) == 0
    stdout = capsys.readouterr().out
    assert expected_substring in stdout
    assert calls[0][0] == "resolve_object_store_config"


def test_backup_cli_main_rotate_passphrase_validates_required_values(monkeypatch) -> None:
    args = SimpleNamespace(
        command="rotate-passphrase",
        backup_file="backup.dump",
        current_passphrase=None,
        new_passphrase=None,
        output_dir=None,
        reupload_object_store=False,
        object_store_bucket=None,
        object_store_prefix=None,
        object_store_endpoint_url=None,
        object_store_region=None,
        object_store_access_key_id=None,
        object_store_secret_access_key=None,
        object_store_session_token=None,
        object_store_force_path_style=False,
    )

    class FakeModule:
        @staticmethod
        def resolve_object_store_config(**kwargs):
            return None

    monkeypatch.setattr(backup_cli, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(backup_cli, "_module", lambda: FakeModule)

    with pytest.raises(SystemExit, match="Missing current passphrase"):
        backup_cli.main([])

    args.current_passphrase = "old"
    with pytest.raises(SystemExit, match="Missing new passphrase"):
        backup_cli.main([])


def test_backup_cli_main_rotate_passphrase_dispatches(monkeypatch, capsys) -> None:
    args = SimpleNamespace(
        command="rotate-passphrase",
        backup_file="backup.dump",
        current_passphrase="old",
        new_passphrase="new",
        output_dir="/tmp/out",
        reupload_object_store=True,
        object_store_bucket=None,
        object_store_prefix=None,
        object_store_endpoint_url=None,
        object_store_region=None,
        object_store_access_key_id=None,
        object_store_secret_access_key=None,
        object_store_session_token=None,
        object_store_force_path_style=False,
    )
    called: dict[str, object] = {}

    class FakeModule:
        @staticmethod
        def resolve_object_store_config(**kwargs):
            return {"ok": True}

        @staticmethod
        def rotate_backup_encryption_passphrase(*call_args, **call_kwargs):
            called["args"] = call_args
            called["kwargs"] = call_kwargs
            return _Artifact({"rotated": True})

    monkeypatch.setattr(backup_cli, "build_parser", lambda: _FakeParser(args))
    monkeypatch.setattr(backup_cli, "_module", lambda: FakeModule)

    assert backup_cli.main([]) == 0
    assert '"rotated": true' in capsys.readouterr().out.lower()
    assert called["args"] == ("backup.dump",)
    assert called["kwargs"]["reupload_object_store"] is True
    assert called["kwargs"]["output_dir"] == Path("/tmp/out")


def test_tracing_helpers_parse_and_format_trace_context() -> None:
    traceparent = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"

    assert tracing_support._parse_traceparent(traceparent) == ("a" * 32, "b" * 16, "01")
    assert tracing_support._parse_traceparent("00-" + "0" * 32 + "-" + "b" * 16 + "-01") is None
    assert tracing_support._parse_traceparent("malformed") is None
    assert tracing_support._parse_otel_headers("k=v, x = y , bad") == {"k": "v", "x": "y"}

    formatted, tokens = tracing_support.start_request_trace(traceparent)
    assert formatted.startswith("00-" + "a" * 32 + "-")
    assert tracing_support.get_current_traceparent() == formatted
    tracing_support.reset_trace_context(tokens)
    assert tracing_support.get_current_traceparent() is None


def test_tracing_start_child_trace_reuses_current_trace_id() -> None:
    parent, tokens = tracing_support.start_request_trace(None)
    try:
        child, child_tokens = tracing_support.start_child_trace(None)
        try:
            assert child.split("-")[1] == parent.split("-")[1]
            assert child != parent
        finally:
            tracing_support.reset_trace_context(child_tokens)
    finally:
        tracing_support.reset_trace_context(tokens)


class _FakeSpan:
    def __init__(self):
        self.attributes = {}
        self.statuses = []
        self.recorded = []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def set_status(self, status):
        self.statuses.append(status)

    def record_exception(self, exc):
        self.recorded.append(str(exc))


class _FakeSpanContextManager:
    def __init__(self, span):
        self.span = span
        self.exited = False

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc, tb):
        self.exited = True
        return False


def test_timed_span_falls_back_to_child_trace_when_otel_traceparent_missing(monkeypatch) -> None:
    span = _FakeSpan()
    cm = _FakeSpanContextManager(span)
    started = []

    monkeypatch.setattr(tracing_support, "_start_otel_span", lambda *a, **k: cm)
    monkeypatch.setattr(tracing_support, "get_current_otel_traceparent", lambda: None)

    with tracing_support.timed_span(name="unit.test") as (traceparent, started_at):
        started.append((traceparent, started_at))
        assert traceparent.startswith("00-")

    assert started
    assert cm.exited is True
    assert tracing_support.get_current_traceparent() is None


def test_set_span_helpers_handle_success_and_error(monkeypatch) -> None:
    span = _FakeSpan()

    tracing_support.set_span_attribute(span, "http.method", "POST")
    assert span.attributes["http.method"] == "POST"

    tracing_support.set_span_http_status(span, 200)
    tracing_support.set_span_http_status(span, 503)
    assert len(span.statuses) >= 2

    exc = RuntimeError("boom")
    tracing_support.set_span_error(span, exc)
    assert span.recorded == ["boom"]


def test_initialize_tracing_returns_false_when_otel_disabled(monkeypatch) -> None:
    telemetry_common._tracing_initialized = False
    telemetry_common._tracing_enabled = True
    monkeypatch.setattr(tracing_support, "get_settings", lambda: Settings(otel_enabled=False, otel_exporter_otlp_endpoint=None))

    assert tracing_support.initialize_tracing() is False
    assert telemetry_common._tracing_initialized is True
    assert telemetry_common._tracing_enabled is False
