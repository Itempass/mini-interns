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

def create_anonymous_user_and_get_token() -> AnonymousLoginResponse:
    """
    Orchestrates the entire anonymous user creation process.
    1. Creates a user in Auth0.
    2. Creates a corresponding user in the local database.
    3. Creates and returns a JWT for the new user.
    """
    from user.internals import auth0_service

    # 1. Create the user in Auth0 first.
    auth0_user = auth0_service.create_auth0_anonymous_user()
    auth0_sub = auth0_user.get("user_id")
    email = auth0_user.get("email")

    if not auth0_sub:
        raise ValueError("Auth0 user creation did not return a user_id.")

    # 2. Create a corresponding user record in our local database.
    new_user = User(
        uuid=uuid4(),
        auth0_sub=auth0_sub,
        email=email,
        is_anonymous=True,
        created_at=datetime.now(timezone.utc)
    )
    
    created_user = database.create_user(new_user)

    # 3. Create a JWT for the new user.
    token_data = {"sub": str(created_user.uuid), "auth0_sub": created_user.auth0_sub}
    access_token = jwt_service.create_access_token(data=token_data)

    return AnonymousLoginResponse(
        **created_user.model_dump(),
        access_token=access_token
    ) 