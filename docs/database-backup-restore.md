# StatFlow Database Backup and Restore

## 1. Architecture

- Provider-managed PostgreSQL backups are the primary protection mechanism for production.
- Point-in-time recovery (PITR) should be enabled wherever the managed database provider supports it.
- Logical PostgreSQL backups created with `pg_dump -Fc` are the secondary, portable recovery mechanism.
- Local Docker Compose instances are for development and experimentation and are not a substitute for a production-grade backup plan.

## 2. Recommended policy

- Managed database backups: daily
- Managed backup retention: minimum 30 days
- Logical dumps: daily where practical
- Logical dump retention: 7 to 14 days
- Restore drill: at least monthly
- RPO baseline: 24 hours; tighter when PITR is available
- RTO initial target: 4 to 12 hours

## 3. Backup procedure

1. Export the target `DATABASE_URL` from the environment or a secret manager.
2. Run the logical backup command against the target database using `pg_dump -Fc`.
3. Save dumps to an encrypted object store or another protected destination.
4. Keep the backup filename deterministic and timestamped.
5. Ensure the backup file is not committed to the repository and is not exposed in logs.

## 4. Restore procedure

1. Restore into a new or isolated database first.
2. Confirm the target host, port, and database before proceeding.
3. Use `pg_restore` against the selected dump file.
4. Investigate the restored database state before any production cutover.
5. Only move traffic after the database has been validated.

## 5. Production restore safeguards

- Restore to a production database is rejected by default.
- `ENVIRONMENT=production` requires `--allow-production`.
- `--yes` alone must not bypass the production guard.
- Production restore requires both `--allow-production` and confirmation or `--yes`.

## 6. Pre-migration backup requirement

- Before any production migration, take a managed snapshot or logical backup.
- This is especially important for destructive or non-reversible schema changes.
- If a migration is risky or data-changing, validate the backup in a separate target before production use.

## 7. Alembic interaction

- After a restore, inspect the restored database revision first.
- Run `alembic upgrade head` only when the restored schema is known to be behind the current application revision.
- Never blindly apply Alembic migrations to an unknown restored database.
- Use the restored schema version to confirm whether the app and database are in sync.

## 8. Security

- Never commit database dumps to git.
- Use encrypted storage or a provider-managed snapshot system.
- Never print `DATABASE_URL`, passwords, JWT secrets, or other application secrets in logs or command output.
- Source database credentials from the environment or a secret manager.

## 9. Restore verification checklist

- Restore into an isolated target database
- Confirm `pg_restore` succeeded
- Inspect the Alembic revision
- Validate application connectivity to PostgreSQL
- Call `/api/v1/ready`
- Run a small DB-backed API request
- Validate data sanity and expected row counts
- Only then consider production cutover

## 10. Operational notes

- The repository is not a backup system by itself.
- Managed backups are the primary protection mechanism for production.
- Logical dumps are the secondary, portable recovery layer.
- The goal for v1 is a simple, testable, and provider-neutral backup strategy, not a broad enterprise backup platform.
