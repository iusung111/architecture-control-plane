#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class CommandResult:
    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class ReleaseReadinessSummary:
    runtime_validation: str
    checks: list[CommandResult]

    @property
    def ok(self) -> bool:
        runtime_ok = self.runtime_validation in {"passed", "skipped"}
        return runtime_ok and all(item.ok for item in self.checks)


def _run(name: str, command: list[str]) -> CommandResult:
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _validate_runtime(require_production: bool) -> str:
    from app.core.config import get_settings
    from app.core.config_support.runtime import ensure_runtime_settings_valid

    get_settings.cache_clear()
    settings = get_settings()
    if require_production and settings.environment.lower() not in {"production", "prod"}:
        raise RuntimeError(
            "release readiness runtime validation requires ENVIRONMENT=production or --allow-non-production-runtime"
        )
    ensure_runtime_settings_valid(settings)
    return "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run release readiness checks for the current revision.")
    parser.add_argument("--postgres-integration", action="store_true", help="Run PostgreSQL integration tests.")
    parser.add_argument(
        "--pytest-target",
        action="append",
        default=None,
        help="Optional pytest target override. May be passed multiple times.",
    )
    parser.add_argument("--compose-smoke", action="store_true", help="Run docker compose smoke test.")
    parser.add_argument("--k8s-smoke", action="store_true", help="Run Kubernetes/Helm static smoke test.")
    parser.add_argument(
        "--skip-runtime-validation",
        action="store_true",
        help="Skip runtime configuration validation using the current environment.",
    )
    parser.add_argument(
        "--allow-non-production-runtime",
        action="store_true",
        help="Allow runtime validation even when ENVIRONMENT is not production.",
    )
    args = parser.parse_args()

    run_postgres_integration = args.postgres_integration or _env_flag("ACP_RELEASE_RUN_POSTGRES_INTEGRATION")
    pytest_targets = list(args.pytest_target or [])
    raw_pytest_targets = os.getenv("ACP_RELEASE_PYTEST_TARGETS")
    if raw_pytest_targets:
        pytest_targets.extend([item for item in raw_pytest_targets.split() if item])
    run_compose_smoke = args.compose_smoke or _env_flag("ACP_RELEASE_RUN_COMPOSE_SMOKE")
    run_k8s_smoke = args.k8s_smoke or _env_flag("ACP_RELEASE_RUN_K8S_SMOKE", default=True)
    skip_runtime_validation = args.skip_runtime_validation or _env_flag("ACP_RELEASE_SKIP_RUNTIME_VALIDATION")

    runtime_validation = "skipped"
    if not skip_runtime_validation:
        try:
            runtime_validation = _validate_runtime(require_production=not args.allow_non_production_runtime)
        except Exception as exc:  # pragma: no cover - exercised via process result in practice
            summary = ReleaseReadinessSummary(runtime_validation=f"failed: {exc}", checks=[])
            print(json.dumps({
                "ok": summary.ok,
                "runtime_validation": summary.runtime_validation,
                "checks": [],
            }, indent=2))
            return 1

    pytest_command = [sys.executable, "-m", "pytest", "-q", *pytest_targets]
    commands: list[tuple[str, list[str]]] = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
        ("pytest", pytest_command),
    ]
    if run_postgres_integration:
        commands.append(
            (
                "pytest-postgres-integration",
                [sys.executable, "-m", "pytest", "-q", "tests/test_postgres_integration.py"],
            )
        )
    if run_k8s_smoke:
        commands.append(("k8s-runtime-smoke", ["bash", "scripts/k8s_runtime_smoke.sh"]))
    if run_compose_smoke:
        commands.append(("docker-compose-smoke", ["bash", "scripts/docker_compose_smoke.sh"]))

    results: list[CommandResult] = []
    for name, command in commands:
        result = _run(name, command)
        results.append(result)
        if not result.ok:
            break

    summary = ReleaseReadinessSummary(runtime_validation=runtime_validation, checks=results)
    print(json.dumps({
        "ok": summary.ok,
        "runtime_validation": summary.runtime_validation,
        "checks": [asdict(item) | {"ok": item.ok} for item in summary.checks],
    }, indent=2))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
