#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


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


def parse_database_url(raw_url: str) -> tuple[str, str, str, str]:
    if not raw_url:
        raise ValueError("DATABASE_URL is required.")

    normalized = raw_url.strip()
    normalized = normalized.replace("postgresql+asyncpg://", "postgresql://")
    normalized = normalized.replace("postgresql+psycopg2://", "postgresql://")
    normalized = normalized.replace("postgresql+psycopg://", "postgresql://")

    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must be a PostgreSQL connection URL.")

    host = parsed.hostname or "<unknown-host>"
    port = str(parsed.port or "5432")
    database = parsed.path.lstrip("/") or "<unknown-database>"
    return normalized, host, port, database


def prompt_for_confirmation(host: str, port: str, database: str, environment: str) -> bool:
    print(f"Target host: {host}")
    print(f"Target port: {port}")
    print(f"Target database: {database}")
    print(f"Environment: {environment}")
    answer = input("Type 'yes' to confirm restore to this database: ").strip().lower()
    return answer == "yes"


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_pg_restore(conn_url: str, backup_path: Path) -> int:
    cmd = ["pg_restore", "-d", conn_url, "-v", str(backup_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(sanitize_text(result.stdout.strip()))
    if result.stderr:
        print(sanitize_text(result.stderr.strip()), file=sys.stderr)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore a PostgreSQL custom-format dump using pg_restore."
    )
    parser.add_argument(
        "backup_file",
        help="Path to the custom-format PostgreSQL dump to restore.",
    )
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation.")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow restore to a production environment. Required when ENVIRONMENT=production.",
    )
    args = parser.parse_args()

    raw_url = os.getenv("DATABASE_URL")
    if not raw_url:
        print("DATABASE_URL is required in the environment.", file=sys.stderr)
        return 2

    try:
        conn_url, host, port, database = parse_database_url(raw_url)
    except ValueError as exc:
        print(f"Invalid DATABASE_URL: {sanitize_text(str(exc))}", file=sys.stderr)
        return 2

    environment = (os.getenv("ENVIRONMENT") or "development").strip().lower()
    if environment == "production" and not args.allow_production:
        print("Production restore is blocked. Re-run with --allow-production.", file=sys.stderr)
        return 2

    backup_path = Path(args.backup_file).expanduser()
    if not backup_path.exists():
        print(f"Backup file not found: {backup_path}", file=sys.stderr)
        return 2

    if not backup_path.is_file():
        print(f"Backup path is not a file: {backup_path}", file=sys.stderr)
        return 2

    if not command_exists("pg_restore"):
        print("PostgreSQL client tools unavailable: pg_restore not found in PATH.", file=sys.stderr)
        return 127

    if not args.yes:
        confirmed = prompt_for_confirmation(host, port, database, environment)
        if not confirmed:
            print("Restore cancelled by user.")
            return 1

    if environment == "production" and not args.allow_production:
        print("Production restore requires --allow-production and confirmation.", file=sys.stderr)
        return 2

    exit_code = run_pg_restore(conn_url, backup_path)
    if exit_code != 0:
        return exit_code

    print(f"Restore completed for target database '{database}' on host '{host}:{port}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
