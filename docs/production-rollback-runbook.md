# StatFlow v1 Production Rollback Runbook

## Rollback Principles

Use immutable release identities. Never overwrite an image or static artifact in place, and never use `latest` as the rollback reference. Preserve logs, metrics, approvals, and the failed release record before changing traffic.

Database rollback is not equivalent to application rollback. Do not blindly run an Alembic downgrade.

## Backend Rollback

1. Declare the failed release and record the current revision, image digest, symptoms, and time window.
2. Preserve deployment logs, readiness results, Sentry events, metrics, and smoke-test output.
3. Identify the previous known-good immutable backend revision and image digest.
4. Shift traffic to the previous revision.
5. Verify `/api/v1/health` and `/api/v1/ready`.
6. Run the safe authenticated or DB-backed smoke test.
7. Monitor 5xx rate, readiness, logs, metrics, and Sentry.
8. Keep the failed revision available for investigation; do not delete it until the incident record is complete.

If the migration changed the database incompatibly, application rollback may not be safe. Stop and use the migration/database procedure below.

## Frontend Rollback

1. Preserve the failed artifact identifier, deployment logs, browser errors, and smoke-test results.
2. Promote the previous known-good immutable static artifact.
3. Revalidate or invalidate `index.html` so browsers receive the prior entrypoint promptly.
4. Verify `/` and a BrowserRouter deep link.
5. Verify same-origin `/api/` routing and a basic user workflow.
6. Monitor frontend availability and Sentry errors.

Hashed assets may remain cached; the restored `index.html` must reference the intended artifact set.

## Database Rollback

1. Stop application traffic changes and assess whether the database state is corrupt, incompatible, or merely ahead of the application.
2. Inspect the deployed and database Alembic revisions.
3. Identify the relevant backup or managed snapshot and verify its timestamp and integrity.
4. Prefer an isolated restore to a separate database first.
5. Validate schema, row counts, constraints, and application compatibility in isolation.
6. Obtain explicit operational approval for production cutover.
7. Restore or promote the selected database deliberately.
8. Verify `/api/v1/ready` and perform basic API/data checks before restoring traffic.

Do not restore a backup solely because an application deployment failed. Use the least destructive corrective action that restores compatibility.

## Migration Failure

1. Stop the release immediately.
2. Do not promote backend traffic.
3. Preserve migration logs, job ID, database revision, error output, and release metadata.
4. Determine whether the migration transaction rolled back cleanly.
5. Inspect database state before any corrective action.
6. Use a forward migration fix where safe and reviewed.
7. Restore from backup/snapshot only when necessary and after isolated validation.
8. Do not automatically run `alembic downgrade`.

## Verification After Any Rollback

Record and verify:

- Previous backend revision is serving traffic.
- Previous frontend artifact is promoted.
- `/api/v1/health` is healthy.
- `/api/v1/ready` is ready.
- Safe authenticated or DB-backed smoke test succeeds.
- 5xx rate returns to baseline.
- Sentry and structured logs show no continuing release-specific error spike.
- Prometheus request, duration, and readiness metrics are normal.

## Required Records

Keep the failed and restored release SHAs, image digests, frontend artifact IDs, traffic changes, migration revision, backup/snapshot IDs, operators, approvals, timestamps, smoke results, and final incident decision.
