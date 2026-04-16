from __future__ import annotations

from pathlib import Path

from app.ops.postgres_backup_restore import run_backup_restore_drill

from .management_config_support.common import BackupDrillExecutionPlan, ManagementConfigResponse, ManagementConfigBase
from .management_config_support.config_service import ConfigServiceMixin
from .management_config_support.drill_service import DrillServiceMixin


class ManagementConfigService(
    ConfigServiceMixin,
    DrillServiceMixin,
    ManagementConfigBase,
):
    BackupDrillExecutionPlanClass = BackupDrillExecutionPlan
    PathClass = Path


__all__ = ["BackupDrillExecutionPlan", "ManagementConfigResponse", "ManagementConfigService", "run_backup_restore_drill"]
