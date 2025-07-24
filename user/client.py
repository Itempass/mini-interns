from typing import Optional, Dict, Any
from user.internals.database import (
    get_default_user as get_default_user_from_db,
    create_user as create_user_in_db,
    get_user_by_uuid as get_user_by_uuid_from_db,
    find_or_create_user_by_auth0_sub as find_or_create_user_by_auth0_sub_in_db,
    set_user_balance as set_user_balance_in_db,
    deduct_from_balance as deduct_from_balance_in_db,
    get_all_users as get_all_users_from_db,
)
from user.models import User
from user.exceptions import InsufficientBalanceError
from uuid import uuid4, UUID
from datetime import datetime, timezone

def get_default_system_user() -> Optional[User]:
    """
    Retrieves the single, shared user record for password-based authentication mode.
    This is a passthrough to the internal database function.
    """
    return get_default_user_from_db()

def get_user_by_uuid(user_uuid: UUID) -> Optional[User]:
    """Retrieves a user from the database by their UUID."""
    return get_user_by_uuid_from_db(user_uuid)

def find_or_create_user_by_auth0_sub(auth0_sub: str, email: Optional[str] = None) -> User:
    """Finds a user by their Auth0 sub, creating one if they don't exist."""
    return find_or_create_user_by_auth0_sub_in_db(auth0_sub=auth0_sub, email=email)

def check_user_balance(user_id: UUID):
    """
    Checks a user's balance. Raises an exception if the balance is depleted.
    """
    user = get_user_by_uuid_from_db(user_id)
    if not user:
        # Or handle as a different error, but for now, this is a safe default
        raise ValueError("User not found")
    if user.balance <= 0:
        raise InsufficientBalanceError()

def set_user_balance(user_uuid: UUID, new_balance: float) -> Optional[User]:
    """Updates the balance for a specific user."""
    return set_user_balance_in_db(user_uuid, new_balance)

def deduct_from_balance(user_uuid: UUID, cost: float) -> Optional[User]:
    """Deducts a cost from a user's balance."""
    return deduct_from_balance_in_db(user_uuid, cost)

def get_all_users() -> list[User]:
    """Retrieves all users."""
    return get_all_users_from_db() 