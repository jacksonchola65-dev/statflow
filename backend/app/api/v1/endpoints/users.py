"""
api/v1/endpoints/users.py
=========================
User management endpoints (ADMIN only).

All endpoints require an active ADMIN session (require_admin dependency).
Transaction management is handled by get_db (auto-commit after yield).

Routes:
    GET    /users               — list all users
    GET    /users/{user_id}     — get single user
    POST   /users               — create user (201)
    PATCH  /users/{user_id}     — partial update user
    DELETE /users/{user_id}     — soft-delete user (204)
"""

from __future__ import annotations

import uuid

from app.core.dependencies import require_admin, validate_csrf
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.users import UserCreateRequest, UserListResponse, UserUpdateRequest
from app.services.auth_service import (
    EmailAlreadyExistsError,
    PasswordPolicyError,
    UserNotFoundError,
)
from app.services.user_service import LastActiveAdminError, SelfDeletionError, UserService
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------


@router.get("", response_model=UserListResponse)
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserListResponse:
    """Return all users. Requires ADMIN role."""
    svc = UserService(db)
    users = await svc.list_users()
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


# ---------------------------------------------------------------------------
# GET /users/{user_id}
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> UserResponse:
    """Return a single user by ID. Requires ADMIN role."""
    svc = UserService(db)
    try:
        user = await svc.get_user(user_id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    __: None = Depends(validate_csrf),
) -> UserResponse:
    """Create a new user account. Requires ADMIN role.

    Transaction is managed by get_db (auto-commit after yield).
    """
    svc = UserService(db)
    try:
        user = await svc.create_user(
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            role=body.role,
            is_active=body.is_active,
        )
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="A user with that email already exists.",
        )
    except PasswordPolicyError:
        raise HTTPException(status_code=400, detail="Password does not meet the required policy.")
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# PATCH /users/{user_id}
# ---------------------------------------------------------------------------


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    __: None = Depends(validate_csrf),
) -> UserResponse:
    """Partially update a user. Only provided fields are changed. Requires ADMIN role."""
    svc = UserService(db)
    try:
        user = await svc.update_user(
            user_id,
            email=body.email,
            full_name=body.full_name,
            role=body.role,
            is_active=body.is_active,
            password=body.password,
        )
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found.")
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="A user with that email already exists.",
        )
    except LastActiveAdminError:
        raise HTTPException(
            status_code=409, detail="This is the last active admin and cannot be changed."
        )
    except PasswordPolicyError:
        raise HTTPException(status_code=400, detail="Password does not meet the required policy.")
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# DELETE /users/{user_id}
# ---------------------------------------------------------------------------


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    __: None = Depends(validate_csrf),
) -> None:
    """Soft-delete a user (marks is_active=False). Requires ADMIN role.

    The user row is never physically removed from the database.
    """
    svc = UserService(db)
    try:
        await svc.delete_user(user_id, acting_user_id=current_user.id)
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found.")
    except SelfDeletionError:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    except LastActiveAdminError:
        raise HTTPException(
            status_code=409, detail="This is the last active admin and cannot be deleted."
        )
