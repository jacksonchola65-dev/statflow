# StatFlow v1 Production Release Runbook

## Preconditions

1. Confirm the release commit is merged to the protected production branch and identify the full Git commit SHA.
2. Create or identify the release tag. The tag and SHA must resolve to the same commit.
3. Confirm the protected `production` GitHub Environment and required approval are available.
4. Confirm all required checks are green:
   - Backend validation
   - Frontend validation
   - CodeQL Analysis (python)
   - CodeQL Analysis (javascript)
   - `pip-audit`
   - `npm audit`
5. Confirm the backend image and frontend artifact were built from the release SHA.
6. Decide whether a database backup or snapshot is required before migration. Treat destructive, irreversible, data-rewriting, enum-removal, column-removal, and high-risk index changes as backup-required.
7. Confirm no production secrets are in the repository, image, or frontend artifact.

## Security Gate Verification

The deployment job must depend on successful completion of the main CI and security workflows. A failed required check stops the release. Branch protection prevents merging without the required status checks and review approval; the protected production environment adds deployment-time approval.

Do not bypass a failed audit, CodeQL result, or required check without a documented security exception and explicit owner approval.

## Release Identity

Record these values before promotion:

- Actor and approving reviewers
- GitHub workflow run ID and URL
- Full commit SHA
- Release tag, if used
- Backend image tag and immutable registry digest
- Frontend artifact identifier and content/version identifier
- Target environment and deployment timestamp

Never deploy by `latest` alone.

## Migration Decision and Gate

Review the migration diff and classify it as additive, compatible, data-changing, destructive, or uncertain. Require a PostgreSQL backup/snapshot before destructive, data-changing, or uncertain migrations. Record the backup identifier.

Run the dedicated migration job using the exact backend image digest:

1. Verify PostgreSQL is reachable.
2. Verify the intended database and environment.
3. Run `alembic upgrade head`.
4. Wait for a successful job completion.
5. Preserve migration logs and the final Alembic revision.
6. Stop the release on any migration error, timeout, or unexpected revision.

Do not automatically run `alembic downgrade`. Use a forward fix or deliberate restore procedure after review.

## Backend Rollout

1. Deploy a new immutable backend revision using the image digest.
2. Inject runtime values from Secret Manager and deployment configuration.
3. Keep the revision out of production traffic initially.
4. Check `/api/v1/health` for liveness.
5. Check `/api/v1/ready` for database readiness.
6. Run one safe authenticated or DB-backed smoke test.
7. Confirm structured logs, request IDs, Prometheus metrics, and Sentry error capture are operating without sensitive data.
8. Promote traffic to the new revision.
9. Monitor readiness, 5xx rate, logs, metrics, and Sentry during the observation window.

## Frontend Rollout

1. Promote the immutable static artifact built from the same release SHA.
2. Verify `/` returns the new release.
3. Revalidate or invalidate `index.html`; hashed assets remain long-lived and immutable.
4. Load a BrowserRouter deep link directly and confirm the SPA fallback works.
5. Verify same-origin `/api/` routing reaches the backend.
6. Confirm no public source maps or build secrets are present.
7. Record the promoted artifact identifier.

## Post-Release Verification

Run and record:

- Frontend root and SPA deep-link smoke tests
- Same-origin API smoke test
- `/api/v1/health`
- `/api/v1/ready`
- One safe authenticated or DB-backed endpoint
- Prometheus request, latency, and readiness metrics
- Structured logs with request ID and duration
- Sentry event delivery and PII scrubbing, if enabled
- Backend and frontend release identifiers

Stop and roll back if readiness fails, 5xx errors increase materially, the frontend is unavailable, or smoke tests fail.

## Release Record

Attach the following to the release record:

- Actor, approvers, workflow run ID, and URL
- Commit SHA and release tag
- Backend image tag and digest
- Frontend artifact identifier
- Backup/snapshot identifier or the documented no-backup decision
- Migration job ID, final revision, logs, and result
- Backend revision and traffic result
- Frontend promotion result
- Smoke-test results
- Sentry/metrics/log verification
- Any rollback or exception decision
