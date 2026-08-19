#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups"


def sanitize_text(value: str | None) -> str:
    if not value:
        return ""

    sanitized = value
    patterns = [
        (r"(?i)(postgres(?:ql)?://)([^:@/\s]+):([^@/\s]+)@", r"\1\2:***REDACTED***@"),
        (r"(?i)(password=|pass=|passwd=|pwd=)([^&\s]+)", r"\1***REDACTED***"),
        (r"(?i)(DATABASE_URL=)([^\s]+)", r"\1***REDACTED***"),
    ]
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized


def parse_database_url(raw_url: str) -> str:
    if not raw_url:
        raise ValueError("DATABASE_URL is not set.")

    normalized = raw_url.strip()
    normalized = normalized.replace("postgresql+asyncpg://", "postgresql://")
    normalized = normalized.replace("postgresql+psycopg2://", "postgresql://")
    normalized = normalized.replace("postgresql+psycopg://", "postgresql://")

    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must be a PostgreSQL connection URL.")
    return normalized


def build_default_backup_path(environment: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    env_name = (environment or "development").strip() or "development"
    filename = f"statflow-{env_name}-{ts}.dump"
    return DEFAULT_BACKUP_DIR / filename


def ensure_output_path(output_arg: str | None) -> Path:
    if output_arg:
        path = Path(output_arg).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path

    return build_default_backup_path(os.getenv("ENVIRONMENT", "development"))


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def confirm_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing backup: {path}")


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_pg_dump(conn_url: str, output_path: Path) -> int:
    cmd = ["pg_dump", "-Fc", "-d", conn_url, "-f", str(output_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(sanitize_text(result.stdout.strip()))
    if result.stderr:
        print(sanitize_text(result.stderr.strip()), file=sys.stderr)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a PostgreSQL logical backup using pg_dump."
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="Optional explicit output path for the backup file.",
    )
    args = parser.parse_args()

    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        print("DATABASE_URL is required in the environment.", file=sys.stderr)
        return 2

    try:
        pg_url = parse_database_url(raw_url)
    except ValueError as exc:
        print(f"Invalid DATABASE_URL: {sanitize_text(str(exc))}", file=sys.stderr)
        return 2

    if not command_exists("pg_dump"):
        print("PostgreSQL client tools unavailable: pg_dump not found in PATH.", file=sys.stderr)
        return 127

    try:
        output_path = ensure_output_path(args.output)
        ensure_parent_dir(output_path)
        confirm_overwrite(output_path)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Unable to prepare backup directory: {sanitize_text(str(exc))}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exit_code = run_pg_dump(pg_url, output_path)
    if exit_code != 0:
        return exit_code

    if output_path.exists():
        size_bytes = output_path.stat().st_size
        print(f"backup path: {output_path}")
        print(f"backup size: {size_bytes} bytes")
        print(f"timestamp: {timestamp}")
        return 0

    print("Backup creation completed but the output file is missing.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
