import logging
from auth0.management import Auth0
from auth0.authentication import GetToken
from shared.config import settings
from uuid import uuid4
from typing import Dict, Any
import requests

logger = logging.getLogger(__name__)

def get_auth0_management_client() -> Auth0:
    """Initializes and returns the Auth0 Management API client."""
    if not settings.AUTH0_M2M_CLIENT_ID or not settings.AUTH0_M2M_CLIENT_SECRET:
        raise ValueError("Auth0 M2M credentials are not configured.")
    
    auth0_domain = settings.AUTH0_DOMAIN
    
    get_token = GetToken(auth0_domain, settings.AUTH0_M2M_CLIENT_ID, settings.AUTH0_M2M_CLIENT_SECRET)
    token = get_token.client_credentials(f"https://{auth0_domain}/api/v2/")
    return Auth0(auth0_domain, token['access_token'])


def get_token_for_user(user_id: str) -> Dict[str, Any]:
    """
    Given a user_id (the auth0_sub), this function uses the M2M client to
    retrieve an access token for the user via the Client Credentials Grant.
    
    Args:
        user_id: The user's Auth0 ID (subject).
        
    Returns:
        The token response dictionary from Auth0, containing the access_token.
    """
    url = f"https://{settings.AUTH0_DOMAIN}/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "audience": settings.AUTH0_API_AUDIENCE,
        "client_id": settings.AUTH0_M2M_CLIENT_ID,
        "client_secret": settings.AUTH0_M2M_CLIENT_SECRET,
        "auth0_sub": user_id,
        "scope": "openid profile email"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Failed to get token for user {user_id}: {e}")
        # In a real app, you might want a more specific exception.
        raise Exception("Could not retrieve user token from Auth0.") 