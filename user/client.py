from typing import Optional, Dict, Any
from user.internals import database, jwt_service
from user.models import User
from uuid import uuid4, UUID
from datetime import datetime, timezone

class AnonymousLoginResponse(User):
    access_token: str
    token_type: str = "bearer"

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


def create_anonymous_user_and_get_token() -> AnonymousLoginResponse:
    """
    Orchestrates the entire anonymous user creation process.
    1. Creates a user in Auth0.
    2. Requests a real access token for that user from Auth0.
    3. Creates a corresponding user in the local database.
    4. Returns the user object and the real Auth0 token.
    """
    from user.internals import auth0_service

    # 1. Create the user in Auth0 first.
    auth0_user = auth0_service.create_auth0_anonymous_user()
    auth0_sub = auth0_user.get("user_id")
    email = auth0_user.get("email")

    if not auth0_sub:
        raise ValueError("Auth0 user creation did not return a user_id.")

    # 2. Get a real access token for our new anonymous user
    token_response = auth0_service.get_token_for_user(auth0_sub)
    access_token = token_response.get("access_token")

    if not access_token:
        raise ValueError("Failed to get an access token for the anonymous user.")

    # 3. Create a corresponding user record in our local database.
    new_user = find_or_create_user_by_auth0_sub(
        auth0_sub=auth0_sub, 
        email=email
    )

    return AnonymousLoginResponse(
        **new_user.model_dump(),
        access_token=access_token
    ) 