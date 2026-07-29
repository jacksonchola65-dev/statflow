# Requirements: Authentication and Authorization Foundation

## Overview

Add secure email/password authentication and role-based access control to StatFlow. Users are created by an administrator — there is no public self-registration in this MVP. All protected pages and API endpoints require a valid JWT access token. No existing APIs, dashboard behaviour, or test suites are changed.

---

## Glossary

| Term | Definition |
|---|---|
| **Access token** | A short-lived signed JWT that identifies the authenticated user and their role |
| **Principal** | The currently authenticated user derived from a valid access token |
| **Protected route** | A frontend page that redirects to `/login` if no valid token exists |
| **Permission** | A boolean check — does the principal's role allow a given action? |
| **Inactive user** | A user whose `is_active` flag is `false`; they cannot authenticate |

---

## Requirements

### REQ-1: User Model

- **REQ-1.1** A `users` table stores all StatFlow operator accounts. It contains: `id` (UUID, PK), `email` (unique, not null), `hashed_password` (not null), `full_name` (nullable), `role` (enum, not null), `is_active` (boolean, default true), `created_at`, `updated_at`.
- **REQ-1.2** Email addresses are stored lower-cased and trimmed. Duplicate emails are rejected at the database level with a unique constraint.
- **REQ-1.3** Plaintext passwords are NEVER stored. Only bcrypt hashes are persisted. Password hashes are never returned in any API response.
- **REQ-1.4** `updated_at` is automatically refreshed on every record update.
- **REQ-1.5** There is no public user registration endpoint. User accounts are created by an ADMIN via a dedicated user-management endpoint or via the admin seed script.

---

### REQ-2: Roles

Four roles exist in a fixed enum. Each user has exactly one role.

| Role | Code | Description |
|---|---|---|
| Administrator | `ADMIN` | Full system access; creates and manages user accounts |
| Data Manager | `DATA_MANAGER` | Imports data and manages datasets |
| Analyst | `ANALYST` | Views analytics, datasets, and indicators |
| Viewer | `VIEWER` | Read-only dashboard access |

- **REQ-2.1** The role is stored as a PostgreSQL `enum` type via SQLAlchemy.
- **REQ-2.2** An unknown or missing role value is rejected at the application layer before database insertion.

---

### REQ-3: Permission Matrix

| Endpoint / Action | ADMIN | DATA_MANAGER | ANALYST | VIEWER |
|---|---|---|---|---|
| Login (`POST /auth/login`) | ✅ | ✅ | ✅ | ✅ |
| Current user (`GET /auth/me`) | ✅ | ✅ | ✅ | ✅ |
| Create user (`POST /users`) | ✅ | ❌ | ❌ | ❌ |
| List users (`GET /users`) | ✅ | ❌ | ❌ | ❌ |
| Update user (`PATCH /users/{id}`) | ✅ | ❌ | ❌ | ❌ |
| Deactivate user (`DELETE /users/{id}`) | ✅ | ❌ | ❌ | ❌ |
| CSV import preview/confirm | ✅ | ✅ | ❌ | ❌ |
| View analytics / indicators | ✅ | ✅ | ✅ | ✅ |
| View datasets | ✅ | ✅ | ✅ | ✅ |
| Manage datasets | ✅ | ✅ | ❌ | ❌ |

- **REQ-3.1** A request from an unauthenticated caller to any protected endpoint returns HTTP 401.
- **REQ-3.2** A request from an authenticated caller with insufficient role returns HTTP 403.

---

### REQ-4: Authentication Flow

- **REQ-4.1** The login endpoint accepts `{ email, password }` and, on success, returns an access token JSON object: `{ access_token, token_type: "bearer" }`.
- **REQ-4.2** On failure (wrong email, wrong password, or inactive account) the response is HTTP 401 with the generic message `"Invalid credentials."`. No specific reason is given.
- **REQ-4.3** The token payload (claims) contains: `sub` (user UUID as string), `email`, `role`, `iat` (issued-at), `exp` (expiry).
- **REQ-4.4** Token expiry defaults to **60 minutes** for the MVP. The value is configurable via the `ACCESS_TOKEN_EXPIRE_MINUTES` environment variable.
- **REQ-4.5** Logout is handled client-side by discarding the stored token. There is no server-side token revocation in this MVP.
- **REQ-4.6** The current-user endpoint (`GET /auth/me`) validates the token and returns the authenticated user's id, email, full_name, role, and is_active. It never returns the hashed password.

---

### REQ-5: JWT Security

- **REQ-5.1** Tokens are signed with HMAC-SHA256 (HS256) using a secret key loaded from the `JWT_SECRET_KEY` environment variable.
- **REQ-5.2** In the development `.env`, a placeholder value is documented. In production, a cryptographically random key of at least 32 bytes must be used and must not be committed to version control.
- **REQ-5.3** The API validates the JWT signature on every protected request. An invalid signature returns HTTP 401.
- **REQ-5.4** An expired token returns HTTP 401.
- **REQ-5.5** The token is transmitted in the `Authorization: Bearer <token>` header. It is NOT passed in query parameters or cookies in this MVP.

---

### REQ-6: Token Storage (Frontend)

- **REQ-6.1** The frontend stores the access token in `localStorage` for MVP simplicity.
- **REQ-6.2** The token is removed from `localStorage` on logout or on receipt of an HTTP 401 from any API call.
- **REQ-6.3** On application load (or page refresh), the app reads the token from `localStorage` and attempts to validate it by calling `GET /auth/me`. If the call succeeds the user is considered authenticated; otherwise the token is discarded and the user is redirected to `/login`.

> **Security note**: `localStorage` is susceptible to XSS. This is an accepted trade-off for MVP simplicity. The spec documents this and flags it as an open question for the CTO (see Risks section).

---

### REQ-7: Protected Routes (Frontend)

- **REQ-7.1** All routes except `/login` are protected — they redirect unauthenticated users to `/login`.
- **REQ-7.2** After successful login the user is redirected to the page they originally tried to access, or `/dashboard` if no prior target exists.
- **REQ-7.3** Role-aware navigation hides menu items the user's role cannot access (e.g., "Import Data" is hidden for VIEWER and ANALYST).
- **REQ-7.4** Hiding navigation items does not replace server-side enforcement. A VIEWER who navigates directly to `/import` receives a 403 from the API.

---

### REQ-8: User Management Endpoints (ADMIN only)

- **REQ-8.1** `POST /api/v1/users` — create a user. Body: `{ email, password, full_name, role }`. Returns the created user (no password hash).
- **REQ-8.2** `GET /api/v1/users` — list all users with pagination. Returns array of user objects (no password hashes).
- **REQ-8.3** `GET /api/v1/users/{id}` — get a single user.
- **REQ-8.4** `PATCH /api/v1/users/{id}` — update full_name, role, or is_active. Changing password requires a separate field and is hashed before storage.
- **REQ-8.5** `DELETE /api/v1/users/{id}` — soft-deactivate (sets `is_active = false`). Hard deletion is not provided in this MVP.

---

### REQ-9: Initial Admin Bootstrap

- **REQ-9.1** A CLI seed script (`backend/app/db/seeders/users.py`) creates the initial ADMIN user when run for the first time.
- **REQ-9.2** Admin credentials for seeding are provided via environment variables `ADMIN_EMAIL` and `ADMIN_PASSWORD`. Neither is hard-coded in source.
- **REQ-9.3** If an admin user with that email already exists, the seed script is idempotent (it does not duplicate or overwrite).

---

### REQ-10: Alembic Migration

- **REQ-10.1** A new Alembic migration creates the `user_role` enum type and alters the `users` table to add the `role` column with a `NOT NULL` constraint and default `VIEWER`.
- **REQ-10.2** The migration is reversible (down migration drops the column and enum).
- **REQ-10.3** The `is_superuser` column on the existing `User` model is retired and replaced by the `role` enum. The migration drops `is_superuser` and adds `role`.

---

### REQ-11: Backward Compatibility

- **REQ-11.1** Existing API endpoints (analytics, provinces, indicators, datasets, data-points, CSV import) must continue to work exactly as they do today after the `get_db` session dependency is preserved.
- **REQ-11.2** After auth is introduced, all existing endpoints will require authentication. A phased rollout strategy (where endpoints are individually wrapped) is described in the design.
- **REQ-11.3** All existing backend and frontend test suites must continue to pass. Test fixtures will inject a mock authenticated principal where needed.

---

### REQ-12: New Dependencies

- **REQ-12.1** Backend: `passlib[bcrypt]` for password hashing, `python-jose[cryptography]` for JWT (or `PyJWT`).
- **REQ-12.2** Frontend: no new npm packages — the existing axios interceptor pattern in `api.js` is extended to attach the `Authorization` header.
- **REQ-12.3** Exact pinned versions are decided at implementation time. Package choices are flagged as an open question for the CTO.

---

### REQ-13: Testing

- **REQ-13.1** Password hashing: `verify_password` returns True for correct password, False for wrong password; plaintext is never equal to hash.
- **REQ-13.2** Token creation/validation: valid token round-trip; expired token raises; tampered token raises.
- **REQ-13.3** Login endpoint: correct credentials return 200 + token; wrong password returns 401; unknown email returns 401; inactive user returns 401.
- **REQ-13.4** Protected endpoint: valid token returns 200; missing token returns 401; invalid token returns 401; expired token returns 401.
- **REQ-13.5** Role enforcement: ADMIN can call user management endpoints; DATA_MANAGER returns 403 on user management; VIEWER returns 403 on import.
- **REQ-13.6** Frontend: login form submits credentials; successful login stores token and redirects; failed login shows error; logout clears token; protected route redirects unauthenticated user; session is restored on refresh.
