from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_release_readiness_script_runs_repo_quality_gates_and_optional_smokes() -> None:
    script = Path("scripts/release_readiness.py").read_text()

    assert '"-m", "ruff", "check", "."' in script
    assert '"-m", "pytest", "-q"' in script
    assert 'tests/test_postgres_integration.py' in script
    assert 'scripts/docker_compose_smoke.sh' in script
    assert 'scripts/k8s_runtime_smoke.sh' in script
    assert 'ACP_RELEASE_RUN_POSTGRES_INTEGRATION' in script
    assert 'ACP_RELEASE_RUN_COMPOSE_SMOKE' in script
    assert 'ACP_RELEASE_RUN_K8S_SMOKE' in script
    assert 'ACP_RELEASE_SKIP_RUNTIME_VALIDATION' in script
    assert 'ACP_RELEASE_PYTEST_TARGETS' in script
    assert '--pytest-target' in script


def test_release_readiness_make_target_exists() -> None:
    makefile = Path("Makefile").read_text()

    assert "release-readiness:" in makefile
    assert "python scripts/release_readiness.py" in makefile


def test_release_readiness_supports_non_production_runtime_bypass() -> None:
    env = os.environ.copy()
    env["ACP_RELEASE_SKIP_RUNTIME_VALIDATION"] = "true"
    env["ACP_RELEASE_PYTEST_TARGETS"] = "tests/test_health.py"
    env["MANAGEMENT_ENDPOINTS_REQUIRE_API_KEY"] = "true"
    env["MANAGEMENT_API_KEY"] = "ops-secret"
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/release_readiness.py"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["runtime_validation"] == "skipped"
    assert [item["name"] for item in payload["checks"]] == ["ruff", "pytest", "k8s-runtime-smoke"]
