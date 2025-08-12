import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.endpoints.auth import get_current_user
from user.models import User
from user import client as user_client

logger = logging.getLogger(__name__)
router = APIRouter()

class BalanceUpdate(BaseModel):
    balance: float

def is_admin(current_user: User = Depends(get_current_user)) -> bool:
    """Dependency to check if the current user is an admin."""
    if not user_client.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    return True

@router.get("/users/me", response_model=User)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns the details of the currently authenticated user.
    """
    return user_client.add_admin_flag(current_user)

@router.post("/users/{user_uuid}/balance", response_model=User)
def set_balance(user_uuid: UUID, balance_update: BalanceUpdate, is_admin: bool = Depends(is_admin)):
    """
    Sets the balance for a specific user. This endpoint is restricted to admins.
    """
    logger.info(f"Admin request to set balance for user {user_uuid} to {balance_update.balance}")
    updated_user = user_client.set_user_balance(user_uuid, balance_update.balance)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return updated_user

@router.get("/users", response_model=list[User])
def get_users(is_admin: bool = Depends(is_admin)):
    """
    Returns a list of all users. This endpoint is restricted to admins.
    """
    return user_client.get_all_users() 