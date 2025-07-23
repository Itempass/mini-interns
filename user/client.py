from typing import Optional, Dict, Any
from user.internals import database, jwt_service
from user.models import User
from uuid import uuid4, UUID
from datetime import datetime, timezone

def get_default_system_user() -> Optional[User]:
    """
    Retrieves the single, shared user record for password-based authentication mode.
    This is a passthrough to the internal database function.
    """
    return database.get_default_user()

def get_user_by_uuid(user_uuid: UUID) -> Optional[User]:
    """Retrieves a user from the database by their UUID."""
    return database.get_user_by_uuid(user_uuid)

def find_or_create_user_by_auth0_sub(auth0_sub: str, email: Optional[str] = None) -> User:
    """Finds a user by their Auth0 sub, creating one if they don't exist."""
    return database.find_or_create_user_by_auth0_sub(auth0_sub=auth0_sub, email=email) 