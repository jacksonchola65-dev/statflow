# Design: Authentication and Authorization Foundation

## Overview

A new auth vertical slice is added to StatFlow. The backend gains a `User` model upgrade (adding `role`), password and JWT utilities, an auth service and repository, a login endpoint, a current-user endpoint, user-management endpoints, and two reusable FastAPI dependencies (`get_current_user`, `require_roles`). The frontend gains a `LoginPage`, an `AuthContext`, an axios interceptor, and a `ProtectedRoute` wrapper. No existing endpoints, models, or test files are deleted.

---

## New File Map

### Backend

```
backend/app/
├── core/
│   ├── config.py                    UPDATED — add JWT_SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES, ADMIN_EMAIL, ADMIN_PASSWORD
│   ├── security.py                  NEW — password hashing + JWT creation/validation
│   └── dependencies.py              NEW — get_current_user, require_roles FastAPI deps
├── models/
│   └── user.py                      UPDATED — add role column; retire is_superuser
├── schemas/
│   └── auth.py                      NEW — LoginRequest, TokenResponse, UserResponse, UserCreate, UserUpdate
├── repositories/
│   └── user_repository.py           NEW — get_by_email, get_by_id, create_user, list_users, update_user, deactivate_user
├── services/
│   └── auth_service.py              NEW — login(), get_current_user_from_token()
├── api/v1/endpoints/
│   ├── auth.py                      NEW — POST /auth/login, GET /auth/me
│   └── users.py                     NEW — CRUD for user management (ADMIN only)
├── api/v1/api.py                    UPDATED — register auth.router, users.router
├── db/seeders/
│   └── users.py                     NEW — idempotent admin seed script
└── alembic/versions/
    └── <timestamp>_add_role_to_users.py  NEW — migration: add role enum + column, drop is_superuser
```

### Frontend

```
frontend/src/
├── contexts/
│   └── AuthContext.jsx              NEW — AuthProvider, useAuth hook
├── pages/
│   └── LoginPage.jsx               NEW — login form, error state, redirect-after-login
├── components/
│   └── auth/
│       └── ProtectedRoute.jsx      NEW — redirects unauthenticated users
├── app/
│   └── router.jsx                  UPDATED — wrap routes in ProtectedRoute; add /login route
├── services/
│   └── api.js                      UPDATED — axios request interceptor adds Authorization header; axios response interceptor handles 401
└── components/layout/
    └── Topbar.jsx                  UPDATED — show/hide Import Data based on role; show user name + logout button
```

---

## Backend Architecture

### `core/security.py`

```python
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt   # or PyJWT

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plaintext: str) -> str: ...
def verify_password(plaintext: str, hashed: str) -> bool: ...
def create_access_token(subject: str, role: str, email: str) -> str:
    # payload: sub=user_id, email, role, iat, exp
    ...
def decode_access_token(token: str) -> dict:
    # raises JWTError on invalid/expired token
    ...
```

### `core/dependencies.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

http_bearer = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate JWT; return the authenticated User. Raises 401 on any failure."""
    ...

def require_roles(*roles: UserRole):
    """Returns a FastAPI dependency that checks the principal's role."""
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        return current_user
    return dependency
```

Usage example:
```python
# Any authenticated user:
@router.get("/me")
async def me(user: User = Depends(get_current_user)): ...

# ADMIN only:
@router.post("/users")
async def create_user(user: User = Depends(require_roles(UserRole.ADMIN))): ...

# DATA_MANAGER or ADMIN:
@router.post("/imports/csv/preview")
async def preview(user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DATA_MANAGER))): ...
```

### Updated `User` model

```python
class UserRole(str, Enum):
    ADMIN        = "ADMIN"
    DATA_MANAGER = "DATA_MANAGER"
    ANALYST      = "ANALYST"
    VIEWER       = "VIEWER"

class User(Base):
    # ... existing columns (id, email, hashed_password, full_name, is_active, created_at, updated_at)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.VIEWER,
        server_default=UserRole.VIEWER.value,
    )
    # is_superuser: REMOVED (replaced by role)
```

### Token Payload

```json
{
  "sub":   "550e8400-e29b-41d4-a716-446655440000",
  "email": "admin@statflow.zm",
  "role":  "ADMIN",
  "iat":   1720000000,
  "exp":   1720003600
}
```

- `sub` is the user's UUID string (not email) per JWT convention.
- `role` is embedded to avoid a DB round-trip on every request. The trade-off: a role change takes effect only after the current token expires (max 60 min).

### `repositories/user_repository.py`

```python
class UserRepository:
    def __init__(self, session: AsyncSession) -> None: ...
    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: UUID) -> User | None: ...
    async def create_user(self, email, hashed_password, full_name, role) -> User: ...
    async def list_users(self, skip, limit) -> list[User]: ...
    async def update_user(self, user_id, **fields) -> User: ...
    async def deactivate_user(self, user_id) -> User: ...
```

No `commit()` or `rollback()` — follows existing repository pattern.

### `services/auth_service.py`

```python
class AuthService:
    def __init__(self, session: AsyncSession) -> None: ...

    async def login(self, email: str, password: str) -> str:
        """Validate credentials → create token. Returns access_token string."""
        # 1. Fetch user by email (case-insensitive)
        # 2. If not found → raise 401 "Invalid credentials."
        # 3. If not active → raise 401 "Invalid credentials."
        # 4. verify_password → if wrong → raise 401 "Invalid credentials."
        # 5. create_access_token(sub=str(user.id), role=user.role, email=user.email)
        # 6. return token

    async def get_user_for_token(self, payload: dict) -> User:
        """Look up the user whose UUID is in the token sub claim."""
        ...
```

### Auth Endpoints

```
POST /api/v1/auth/login
  Body: { "email": "...", "password": "..." }
  200: { "access_token": "...", "token_type": "bearer" }
  401: { "detail": "Invalid credentials." }

GET /api/v1/auth/me
  Header: Authorization: Bearer <token>
  200: { "id", "email", "full_name", "role", "is_active", "created_at", "updated_at" }
  401: missing / invalid / expired token
```

### Alembic Migration Strategy

The migration performs these steps in order:
1. Create the `user_role` PostgreSQL enum: `ADMIN`, `DATA_MANAGER`, `ANALYST`, `VIEWER`.
2. Add column `role user_role NOT NULL DEFAULT 'VIEWER'` to `users`.
3. Assign `role = 'ADMIN'` to any rows where `is_superuser = true`.
4. Drop `is_superuser` column.

Down migration reverses: re-adds `is_superuser`, sets it from `role = 'ADMIN'`, drops `role`, drops the enum.

### Admin Seed Script

```python
# backend/app/db/seeders/users.py
async def seed_admin(session: AsyncSession) -> None:
    email = settings.ADMIN_EMAIL.strip().lower()
    existing = await repo.get_by_email(email)
    if existing:
        return   # idempotent
    hashed = hash_password(settings.ADMIN_PASSWORD)
    await repo.create_user(email=email, hashed_password=hashed,
                           full_name="System Administrator", role=UserRole.ADMIN)
    await session.commit()
```

Invoked manually: `python -m app.db.seeders.users` or via the app lifespan if `SEED_ADMIN=true` env var is set.

---

## Frontend Architecture

### `AuthContext.jsx`

```jsx
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)   // null = not loaded yet
  const [loading, setLoading] = useState(true)   // true during initial token check

  // On mount: read token from localStorage → call GET /auth/me → setUser
  useEffect(() => { restoreSession() }, [])

  async function login(email, password) {
    const { access_token } = await apiLogin(email, password)
    localStorage.setItem('statflow_token', access_token)
    const me = await fetchMe()
    setUser(me)
  }

  function logout() {
    localStorage.removeItem('statflow_token')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
```

### `api.js` Axios Interceptors

```js
// Request interceptor — attach token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('statflow_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Response interceptor — handle 401 globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem('statflow_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
```

### `ProtectedRoute.jsx`

```jsx
export default function ProtectedRoute({ children, requiredRoles }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <LoadingSpinner />
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (requiredRoles && !requiredRoles.includes(user.role)) return <UnauthorizedPage />
  return children
}
```

### Updated Router

```jsx
<Routes>
  <Route path="/login" element={<LoginPage />} />
  <Route path="/" element={<Navigate to="/dashboard" replace />} />
  <Route path="/dashboard" element={
    <ProtectedRoute><DashboardPage /></ProtectedRoute>
  } />
  <Route path="/import" element={
    <ProtectedRoute requiredRoles={['ADMIN', 'DATA_MANAGER']}>
      <ImportPage />
    </ProtectedRoute>
  } />
  <Route path="/users" element={
    <ProtectedRoute requiredRoles={['ADMIN']}>
      <UserManagementPage />
    </ProtectedRoute>
  } />
  <Route path="*" element={<NotFoundPage />} />
</Routes>
```

### Frontend State Transitions

```
App loads
  └── AuthProvider mounts
        └── token in localStorage?
              ├── YES → GET /auth/me
              │         ├── 200 → user = { id, email, role, ... } → show app
              │         └── 401 → clear token → user = null → /login
              └── NO  → user = null → show /login

User submits login form
  └── POST /auth/login
        ├── 200 → store token → GET /auth/me → user populated → redirect
        └── 401 → show "Invalid email or password."

User clicks Logout
  └── clear localStorage → user = null → redirect /login

Any API call returns 401
  └── axios interceptor → clear localStorage → redirect /login
```

### Role-Aware Navigation

| Navigation item | ADMIN | DATA_MANAGER | ANALYST | VIEWER |
|---|---|---|---|---|
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| Import Data | ✅ | ✅ | ❌ | ❌ |
| User Management | ✅ | ❌ | ❌ | ❌ |
| Logout | ✅ | ✅ | ✅ | ✅ |

---

## Phased Rollout of Auth on Existing Endpoints

To avoid a big-bang change that breaks every existing test, existing endpoints are wrapped with `get_current_user` in a dedicated implementation task (Task 9 in tasks.md). Until that task runs, existing endpoints remain unprotected — identical to current behaviour.

---

## Settings Changes (`core/config.py`)

```python
# New fields added to Settings:
JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_openssl_rand_-hex_32"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
ADMIN_EMAIL: str = ""      # Required for seed; empty default is safe
ADMIN_PASSWORD: str = ""   # Required for seed; empty default is safe
```

**Local development**: add `JWT_SECRET_KEY=dev-only-secret` to `.env` (already in `.gitignore`).
**Production**: generate with `openssl rand -hex 32` and inject via environment variable or secrets manager. Never commit.

---

## Correctness Properties

1. **No plaintext stored**: `hash_password` always runs through bcrypt; the raw string never touches the database.
2. **No info leakage on login failure**: all failure paths (wrong email, wrong password, inactive) return the identical 401 response.
3. **Role in token is advisory only**: `get_current_user` re-loads the user from the DB on every protected request. The role embedded in the token is NOT used for authorization decisions — the live DB role is used. This avoids stale-role attacks.
4. **Token expiry is enforced server-side**: `decode_access_token` checks `exp` claim; expired tokens are rejected before the user object is returned.
5. **Idempotent seed**: the admin seed is safe to run multiple times.

---

## Risks and Open Questions

See `tasks.md` — Risks section.
