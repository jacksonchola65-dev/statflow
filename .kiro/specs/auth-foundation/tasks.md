# Implementation Plan: Authentication and Authorization Foundation

## Overview

Add JWT-based email/password authentication and role-based access control to StatFlow without breaking any existing behaviour. Tasks are sequenced so that new infrastructure is built before it is wired into existing endpoints.

**Do not begin implementation until this spec has been reviewed and approved.**

---

## Tasks

- [x] 1. Upgrade `User` model and Alembic migration
  - Add `UserRole` enum (`ADMIN`, `DATA_MANAGER`, `ANALYST`, `VIEWER`) to `app/models/user.py`
  - Add `role` column to `User` with `NOT NULL DEFAULT 'VIEWER'`
  - Remove `is_superuser` column from `User`
  - Create Alembic migration: create enum type → add column → copy superuser → drop old column
  - Write reversible down-migration
  - Update `app/db/base.py` imports if needed
  - References: REQ-1, REQ-2, REQ-10
  - Acceptance: `alembic upgrade head` runs cleanly; `alembic downgrade -1` reverses it

- [x] 2. Add new dependencies to requirements.txt
  - Add `passlib[bcrypt]` (pinned) for password hashing
  - Add `python-jose[cryptography]` (pinned) for JWT (alternative: `PyJWT`)
  - Add `email-validator` (pinned) for Pydantic email validation
  - Update `backend/requirements.txt`
  - Install in the project venv
  - References: REQ-12
  - Acceptance: `python -c "from passlib.context import CryptContext; from jose import jwt"` exits 0

- [x] 3. Implement `core/security.py` — password and JWT utilities
  - Create `backend/app/core/security.py`
  - Implement `hash_password(plaintext: str) → str` using bcrypt
  - Implement `verify_password(plaintext: str, hashed: str) → bool`
  - Implement `create_access_token(sub, email, role) → str` (signs HS256 JWT, adds exp)
  - Implement `decode_access_token(token: str) → dict` (raises `jose.JWTError` on failure)
  - Add `JWT_SECRET_KEY` and `ACCESS_TOKEN_EXPIRE_MINUTES` to `core/config.py`
  - References: REQ-5, REQ-4.3
  - Acceptance: unit tests in Task 7 pass

- [x] 4. Implement `repositories/user_repository.py`
  - Create `backend/app/repositories/user_repository.py`
  - `get_by_email(email: str) → User | None` — case-insensitive lookup
  - `get_by_id(user_id: UUID) → User | None`
  - `create_user(email, hashed_password, full_name, role) → User`
  - `list_users(skip, limit) → list[User]`
  - `update_user(user_id, **fields) → User`
  - `deactivate_user(user_id) → User` (sets `is_active=False`)
  - Follow existing repository pattern: `__init__(self, session: AsyncSession)`, no commit/rollback
  - References: REQ-1, REQ-8
  - Acceptance: used successfully by auth service

- [x] 5. Implement `services/auth_service.py`
  - Create `backend/app/services/auth_service.py`
  - `AuthService.login(email, password) → str` — validates credentials, returns access token
  - All failure paths (wrong email, wrong password, inactive user) raise HTTP 401 `"Invalid credentials."`
  - `AuthService.get_user_for_token(payload: dict) → User`
  - References: REQ-4, REQ-5.2
  - Acceptance: login integration tests in Task 8 pass

- [x] 6. Implement `core/dependencies.py` — FastAPI auth dependencies
  - Create `backend/app/core/dependencies.py`
  - `get_current_user(credentials, db) → User` — parse Bearer token → decode → load user from DB; raises HTTP 401 on any failure
  - `require_roles(*roles) → Callable` — returns a dependency that calls `get_current_user` and checks role; raises HTTP 403 if insufficient
  - References: REQ-3, REQ-4.6, REQ-5.3, REQ-5.4
  - Acceptance: dependency correctly returns user on valid token; raises 401/403 as specified

- [x] 7. Add Pydantic schemas (`schemas/auth.py`) and auth endpoints (`endpoints/auth.py`)
  - Create `backend/app/schemas/auth.py`:
    - `LoginRequest(BaseModel)` — email, password
    - `TokenResponse(BaseModel)` — access_token, token_type
    - `UserResponse(BaseModel)` — id, email, full_name, role, is_active, created_at, updated_at (no password_hash)
    - `UserCreate(BaseModel)` — email, password, full_name, role
    - `UserUpdate(BaseModel)` — full_name?, role?, is_active?, password?
  - Create `backend/app/api/v1/endpoints/auth.py`:
    - `POST /auth/login` → `TokenResponse`
    - `GET /auth/me` → `UserResponse` (requires `get_current_user`)
  - Register `auth.router` in `api.py`
  - References: REQ-4, REQ-4.6
  - Acceptance: `POST /auth/login` returns token for valid credentials; `GET /auth/me` returns user

- [x] 8. Implement user management endpoints (`endpoints/users.py`)
  - Create `backend/app/api/v1/endpoints/users.py`
  - All endpoints require `require_roles(UserRole.ADMIN)`
  - `POST /users` — create user
  - `GET /users` — list users (skip/limit pagination)
  - `GET /users/{id}` — get single user
  - `PATCH /users/{id}` — update user
  - `DELETE /users/{id}` — deactivate user
  - Register `users.router` in `api.py`
  - References: REQ-8, REQ-3
  - Acceptance: ADMIN can CRUD; non-ADMIN gets 403

- [x] 9. Write backend tests
  - Create `backend/tests/test_security.py` — password hashing, token creation, token validation, expired token, tampered token
  - Create `backend/tests/test_auth.py` — login success, wrong password, unknown email, inactive user, `/auth/me` with valid/invalid/expired token
  - Create `backend/tests/test_users.py` — ADMIN CRUD success, non-ADMIN 403 on user endpoints
  - Update `backend/tests/conftest.py` to seed a test user (ADMIN) for auth tests
  - References: REQ-13.1–REQ-13.5
  - Acceptance: `pytest backend/tests/test_security.py backend/tests/test_auth.py backend/tests/test_users.py` passes

- [x] 10. Protect existing endpoints with `get_current_user`
  - Update each existing endpoint in `endpoints/` to add `current_user: User = Depends(get_current_user)` (or the role-specific variant)
  - Route-to-role mapping (see REQ-3 permission matrix):
    - Analytics, provinces, indicators, categories, datasets, data-points: any authenticated user
    - CSV import preview/confirm: ADMIN or DATA_MANAGER
  - Update existing endpoint tests to inject a mock authenticated user
  - References: REQ-3, REQ-11
  - Acceptance: all existing backend tests pass with auth headers added; unauthenticated requests return 401

- [x] 11. Implement admin seed script
  - Create `backend/app/db/seeders/users.py`
  - Add `ADMIN_EMAIL`, `ADMIN_PASSWORD` to `core/config.py`
  - Seed is idempotent (no-op if email already exists)
  - Document in README: how to run the seed command
  - References: REQ-9
  - Acceptance: running the seed twice produces exactly one admin user

- [x] 12. Frontend — `AuthContext` and axios interceptors
  - Create `frontend/src/contexts/AuthContext.jsx`:
    - `AuthProvider` wraps the app; provides `user`, `loading`, `login()`, `logout()`
    - `useAuth()` hook
    - `restoreSession()` reads token from `localStorage`, calls `GET /auth/me`
  - Update `frontend/src/services/api.js`:
    - Request interceptor: attach `Authorization: Bearer <token>` from localStorage
    - Response interceptor: on 401, clear token and redirect to `/login`
  - Add `apiLogin(email, password)` and `fetchMe()` to `api.js`
  - Wrap `<App>` in `<AuthProvider>` in `main.jsx`
  - References: REQ-6, REQ-7.3
  - Acceptance: token is attached on all API calls; 401 redirects to login

- [x] 13. Frontend — `LoginPage` and `ProtectedRoute`
  - Create `frontend/src/pages/LoginPage.jsx`:
    - Email + password form
    - Calls `useAuth().login()`
    - Shows generic error "Invalid email or password." on failure
    - Redirects to intended page (or `/dashboard`) on success
  - Create `frontend/src/components/auth/ProtectedRoute.jsx`:
    - Shows spinner while `loading === true`
    - Redirects to `/login` if `user === null`
    - Renders `<UnauthorizedPage>` (or redirects) if role not in `requiredRoles`
  - References: REQ-7
  - Acceptance: unauthenticated users see login page; authorized users pass through

- [x] 14. Update router and Topbar for auth
  - Update `frontend/src/app/router.jsx`:
    - Add `/login` route (unprotected)
    - Wrap `/dashboard`, `/import`, future `/users` routes in `ProtectedRoute`
    - Redirect `/` → `/dashboard` only if authenticated; else → `/login`
  - Update `frontend/src/components/layout/Topbar.jsx`:
    - Show/hide "Import Data" based on role (hidden for VIEWER/ANALYST)
    - Show/hide "User Management" based on role (ADMIN only)
    - Show logged-in user's full_name or email
    - Add Logout button
  - References: REQ-7.1, REQ-7.3
  - Acceptance: role-aware nav renders correctly; logout clears session

- [x] 15. Frontend tests
  - Create `frontend/src/test/LoginPage.test.jsx` — renders form; submit calls login; error message on failure; redirect on success
  - Create `frontend/src/test/ProtectedRoute.test.jsx` — unauthenticated redirects to /login; loading shows spinner; authorized user passes
  - Create `frontend/src/test/AuthContext.test.jsx` — session restored from localStorage; logout clears state
  - Update existing `DashboardPage.test.jsx` to provide a mock `AuthContext`
  - References: REQ-13.6
  - Acceptance: `vitest run` passes including all new auth tests

- [x] 16. Final quality gates
  - Run `pytest backend/tests/` — all tests pass
  - Run `vitest run` — all tests pass
  - Run `oxlint src` — exit 0
  - Verify `/login` loads and accepts credentials
  - Verify `/dashboard` redirects to `/login` when unauthenticated
  - Verify existing dashboard, analytics, and import flows work for an authenticated user
  - References: REQ-11, REQ-13
  - Acceptance: zero test failures; no regressions in existing functionality

---

## Task Dependency Graph

```
1 (model + migration)
    │
    ├──► 2 (deps) ──► 3 (security utils)
    │                       │
    │              4 (user repo) ──► 5 (auth service) ──► 6 (dependencies)
    │                                                              │
    │                                           7 (schemas + auth endpoints)
    │                                           8 (user management endpoints)
    │                                           9 (backend tests)
    │                                          10 (protect existing endpoints)
    │                                          11 (admin seed)
    │
    ├──► 12 (AuthContext + axios)
    │          │
    │     13 (LoginPage + ProtectedRoute)
    │          │
    │     14 (router + Topbar)
    │          │
    │     15 (frontend tests)
    │
    └──► 16 (quality gates)  ← after ALL of the above
```

Tasks 1, 2, and 12 can start in parallel once the spec is approved.

---

## Risks and Open Questions

### R1 — Token storage: `localStorage` vs `httpOnly` cookie
**Risk**: `localStorage` is vulnerable to XSS. A malicious script can steal the token.
**Current decision**: Use `localStorage` for MVP simplicity.
**CTO decision required**: Should this MVP use `httpOnly` cookies (eliminates XSS risk but requires CSRF protection and changes the API contract) or is `localStorage` acceptable for the initial internal deployment?

### R2 — JWT library choice: `python-jose` vs `PyJWT`
**Risk**: `python-jose` has had CVEs; `PyJWT` is more actively maintained as of 2024.
**Current decision**: `python-jose[cryptography]` is listed as the default (to match common FastAPI examples). `PyJWT` is a valid alternative.
**CTO decision required**: Confirm library preference before Task 2.

### R3 — Role change latency (token cache)
**Risk**: If an admin changes a user's role, the change does not take effect until the user's current token expires (up to 60 minutes).
**Current decision**: The design re-loads the user from the DB on every request (REQ-3, correctness property #3), so role changes take effect immediately. The role in the token is informational only.
**Status**: No CTO decision needed — design is already safe.

### R4 — Protecting existing endpoints breaks existing tests
**Risk**: Task 10 adds auth headers to every existing endpoint, which will break tests that don't inject a valid token.
**Mitigation**: Task 10 includes updating existing test fixtures to inject a mock authenticated user. All existing tests must still pass after Task 10.
**CTO decision required**: Should existing tests be updated as part of this spec, or should the auth dependency be added in a way that is opt-out for the test environment (e.g., an `DISABLE_AUTH=true` flag)?

### R5 — Admin password in environment variable
**Risk**: Developers may commit weak passwords in local `.env` files. The `.env` file is in `.gitignore` but history may leak it.
**Mitigation**: Document clearly in README. Add `.env` validation that rejects empty `ADMIN_PASSWORD` in non-development environments.
**Status**: Informational. No CTO decision required for MVP.

### R6 — No refresh token in this MVP
**Risk**: Users are logged out after 60 minutes and must re-authenticate.
**Current decision**: Accepted for MVP.
**CTO decision required**: Is the 60-minute expiry acceptable for the initial deployment, or should we implement a refresh-token flow?

### R7 — No password reset in this MVP
**Risk**: If an admin loses their password, only another admin can reset it (or the database must be updated directly).
**Current decision**: Out of scope for MVP. Admin can change passwords via the `PATCH /users/{id}` endpoint (requires another ADMIN account).
**Status**: Acknowledged. Log as a follow-up feature.

---

## Open Questions Requiring CTO Decision

| # | Question | Options | Impact |
|---|---|---|---|
| Q1 | Token storage mechanism | `localStorage` (XSS risk, simpler) vs `httpOnly` cookie (more secure, more complex) | Security posture, API contract |
| Q2 | JWT library | `python-jose[cryptography]` vs `PyJWT` | Dependency CVE risk |
| Q3 | Protecting existing tests | Update test fixtures vs `DISABLE_AUTH` flag | Implementation complexity |
| Q4 | Token expiry | 60 min (no refresh) vs shorter expiry + refresh token | UX vs security |
