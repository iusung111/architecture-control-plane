from pathlib import Path

from app.services.cycles import CycleQueryService, CycleStreamService, CycleWriteService


def test_cycle_services_public_exports_are_available() -> None:
    assert CycleWriteService is not None
    assert CycleQueryService is not None
    assert CycleStreamService is not None


def test_cycle_service_files_respect_line_budget() -> None:
    targets = [
        Path("app/services/cycles.py"),
        *sorted(Path("app/services/cycle_service").glob("*.py")),
    ]
    violations = []
    for path in targets:
        line_count = sum(1 for _ in path.open())
        if line_count > 300:
            violations.append((str(path), line_count))
    assert violations == []
