from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from .models import CommandSpec, DEFAULT_COMMAND_TIMEOUT_SECONDS, DEFAULT_VERIFY_TABLES


def _module():
    return importlib.import_module("app.ops.postgres_backup_restore")

def sanitize_database_url(database_url: str) -> str:
    url = make_url(database_url)
    rendered = url.render_as_string(hide_password=False)
    if url.password is None:
        return rendered
    encoded_password = quote(str(url.password), safe="")
    return rendered.replace(f":{encoded_password}@", ":***@", 1)

def _database_slug(database_url: str) -> str:
    database = make_url(database_url).database or "database"
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-" for character in database
    )

def _tool_env(database_url: str) -> dict[str, str]:
    url = make_url(database_url)
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    return env


def _tool_database_url(database_url: str) -> str:
    url = make_url(database_url)
    rendered = url.set(drivername=url.get_backend_name()).render_as_string(hide_password=True)
    return rendered.replace(":***@", "@", 1)


def _compose_exec_prefix(service: str, env: dict[str, str]) -> list[str]:
    prefix = ["docker", "compose", "exec", "-T"]
    for key in ("PGPASSWORD",):
        value = env.get(key)
        if value:
            prefix.extend(["-e", f"{key}={value}"])
    prefix.append(service)
    return prefix

def build_backup_command(database_url: str, *, docker_compose_service: str | None = None) -> CommandSpec:
    env = _tool_env(database_url)
    tool_database_url = _tool_database_url(database_url)
    argv = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--dbname",
        tool_database_url,
    ]
    source = "direct"
    if docker_compose_service:
        argv = _compose_exec_prefix(docker_compose_service, env) + argv
        source = f"docker-compose:{docker_compose_service}"
    return CommandSpec(argv=argv, env=env, source=source)


def build_restore_command(
    database_url: str,
    *,
    docker_compose_service: str | None = None,
) -> CommandSpec:
    env = _tool_env(database_url)
    tool_database_url = _tool_database_url(database_url)
    argv = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--dbname",
        tool_database_url,
    ]
    source = "direct"
    if docker_compose_service:
        argv = _compose_exec_prefix(docker_compose_service, env) + argv
        source = f"docker-compose:{docker_compose_service}"
    return CommandSpec(argv=argv, env=env, source=source)

def run_command_to_file(spec: CommandSpec, output_path: Path, *, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> None:
    with output_path.open("wb") as output_handle:
        _module().subprocess.run(spec.argv, check=True, env=spec.env, stdout=output_handle, timeout=timeout_seconds)


def run_command_from_file(spec: CommandSpec, input_path: Path, *, timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS) -> None:
    with input_path.open("rb") as input_handle:
        _module().subprocess.run(spec.argv, check=True, env=spec.env, stdin=input_handle, timeout=timeout_seconds)


def admin_database_url(database_url: str) -> str:
    url = make_url(database_url)
    admin_db = "postgres"
    return url.set(database=admin_db).render_as_string(hide_password=False)


def recreate_database(database_url: str) -> None:
    target = make_url(database_url)
    admin_url = admin_database_url(database_url)
    database_name = target.database
    if not database_name:
        raise ValueError("Target database URL must include a database name")

    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                (database_name,),
            )
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name)))
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))


def verify_restored_database(
    database_url: str,
    *,
    required_tables: tuple[str, ...] = DEFAULT_VERIFY_TABLES,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    present_tables: list[str] = []
    missing_tables: list[str] = []
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for table in required_tables:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                result = cursor.fetchone()
                if result and result[0]:
                    present_tables.append(table)
                    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
                    counts[table] = int(cursor.fetchone()[0])
                else:
                    missing_tables.append(table)
    return {
        "required_tables": list(required_tables),
        "present_tables": present_tables,
        "missing_tables": missing_tables,
        "row_counts": counts,
    }

