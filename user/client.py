from typing import Optional, Dict, Any
from user.internals.database import (
    get_or_create_default_user as get_or_create_default_user_from_db,
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

def get_or_create_default_user() -> User:
    """
    Retrieves the single, shared user record, creating it if it doesn't exist.
    This is a passthrough to the internal database function.
    """
    return get_or_create_default_user_from_db()

def get_user_by_uuid(user_uuid: UUID) -> Optional[User]:
    """Retrieves a user from the database by their UUID."""
    return get_user_by_uuid_from_db(user_uuid)

def find_or_create_user_by_auth0_sub(auth0_sub: str, email: Optional[str] = None) -> User:
    """Finds a user by their Auth0 sub, creating one if they don't exist."""
    return find_or_create_user_by_auth0_sub_in_db(auth0_sub=auth0_sub, email=email)

def check_user_balance(user_id: UUID):
    """
    Checks a user's balance if they are an Auth0 user.
    Raises an exception if the balance is depleted.
    Non-Auth0 users will always pass this check.
    """
    user = get_user_by_uuid_from_db(user_id)
    if not user:
        raise ValueError("User not found")

    # Only check balance for Auth0 users
    if user.auth0_sub:
        if user.balance <= 0:
            raise InsufficientBalanceError()

def set_user_balance(user_uuid: UUID, new_balance: float) -> Optional[User]:
    """Updates the balance for a specific user."""
    return set_user_balance_in_db(user_uuid, new_balance)

def deduct_from_balance(user_uuid: UUID, cost: float) -> Optional[User]:
    """
    Deducts a cost from a user's balance if they are an Auth0 user.
    """
    user = get_user_by_uuid_from_db(user_uuid)
    if not user:
        # We don't raise an error here to avoid crashing a running process
        # if the user somehow gets deleted mid-operation.
        return None

    # Only deduct from balance for Auth0 users
    if user.auth0_sub:
        return deduct_from_balance_in_db(user_uuid, cost)
    
    return user # Return the original user object if no deduction was made

def get_all_users() -> list[User]:
    """Retrieves all users."""
    return get_all_users_from_db() 