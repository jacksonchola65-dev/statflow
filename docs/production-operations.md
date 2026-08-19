# StatFlow v1 Production Operations

## Incident Decision Matrix

| Signal | Immediate action | Rollback required? | Evidence to preserve |
| --- | --- | --- | --- |
| Migration failure | Stop release and traffic promotion; inspect job and database revision | Not automatically; restore only if necessary | Migration logs, job ID, revision, backup ID, release SHA |
| Readiness failure | Keep new backend revision out of traffic; inspect database connectivity and Secret Manager bindings | Yes if the prior revision is healthy and failure persists | Readiness responses, logs, metrics, revision events |
| Increased 5xx rate | Freeze promotion, compare with prior revision, inspect structured logs and Sentry | Usually yes when release-specific and persistent | Error samples, request IDs, metrics, Sentry event IDs, image digest |
| Sentry error spike | Triage grouped exceptions and release correlation; stop further promotion | Yes when unexpected errors affect users or trend upward | Sentry release, event IDs, stack metadata, logs, deployment record |
| Frontend outage | Check static artifact, CDN/edge status, `index.html`, and API proxy | Promote previous static artifact if release-specific | Browser smoke output, CDN logs, artifact IDs, Sentry events |
| Database outage | Keep or shift backend away from failing revision; verify Cloud SQL and network state | Application rollback only if it reduces incompatibility; database restore requires separate approval | Database alerts, readiness results, connection logs, snapshot/backup IDs |

## Monthly Restore Drill

1. Select a recent logical or managed PostgreSQL backup without touching production.
2. Restore it to an isolated database with isolated credentials and network access.
3. Inspect the restored Alembic revision and compare it with the expected release revision.
4. Run migrations only if the drill explicitly tests migration-forward behavior and the target is isolated.
5. Verify schema objects, constraints, representative row counts, and basic data integrity.
6. Point an isolated application instance at the restored database.
7. Verify `/api/v1/health` and `/api/v1/ready`.
8. Run a basic read API check and one representative authenticated/DB-backed check.
9. Record restore duration, backup age, revision, validation results, and any discrepancy.
10. Destroy isolated drill resources according to the approved retention policy.

Never perform a restore drill against the production database or production traffic path.

## Security Operating Rules

- Production secrets remain in Google Secret Manager.
- GitHub Actions authenticates with GitHub OIDC and Workload Identity Federation.
- Do not use long-lived service-account JSON keys.
- Do not create or commit production `.env` files.
- Do not commit database backups, dumps, credentials, Sentry auth tokens, or service-account keys.
- Runtime secrets are not duplicated into GitHub unless a narrowly approved deployment operation requires it.
- Sentry source maps, if enabled later, are uploaded privately and are never served publicly.
- Do not use request IDs, user IDs, emails, hostnames, or database identifiers as release/environment identifiers or high-cardinality metric labels.
- Do not perform destructive automatic rollback or automatic Alembic downgrade.

## Operational Checks

During normal operation, monitor:

- Backend `/api/v1/health` liveness
- Backend `/api/v1/ready` database readiness
- Prometheus request count, latency, status codes, and readiness gauge
- Structured JSON logs, request IDs, and duration fields
- Sentry grouped errors by release and environment
- Backend 5xx rate and frontend availability
- Database health, capacity, backups, and migration state

The `/metrics` endpoint must not be treated as a database probe. Successful health/readiness checks and metrics scrapes should not create Sentry error events.

## Deployment Evidence Checklist

Every release or incident record should include:

- Commit SHA and optional release tag
- GitHub actor, approval, workflow run ID, and URL
- Backend image tag and digest
- Frontend artifact identifier
- Migration job result and final Alembic revision
- Backup/snapshot decision and identifier
- Backend revision and traffic assignment
- Frontend promotion and cache revalidation result
- Health, readiness, smoke-test, metrics, log, and Sentry results
- Rollback decision, operator, timestamp, and final state

## Cost and Safety

Do not provision chargeable resources as part of an operational response without the appropriate approval. Prefer bounded diagnostics, existing logs/metrics, isolated restore targets, and immutable release artifacts. Avoid broad tracing or high-cardinality telemetry until a separate capacity and cost review is complete.
