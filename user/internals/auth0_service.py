import logging
from auth0.management import Auth0
from auth0.authentication import GetToken
from shared.config import settings
from uuid import uuid4

logger = logging.getLogger(__name__)

def get_auth0_management_client() -> Auth0:
    """Initializes and returns the Auth0 Management API client."""
    if not all([settings.AUTH0_DOMAIN, settings.AUTH0_M2M_CLIENT_ID, settings.AUTH0_M2M_CLIENT_SECRET, settings.AUTH0_API_AUDIENCE]):
        raise ValueError("Auth0 Management API credentials are not fully configured.")
    
    # First, get a management API token using our M2M credentials
    get_token = GetToken(
        domain=settings.AUTH0_DOMAIN,
        client_id=settings.AUTH0_M2M_CLIENT_ID,
        client_secret=settings.AUTH0_M2M_CLIENT_SECRET
    )
    token_data = get_token.client_credentials(audience=settings.AUTH0_API_AUDIENCE)
    mgmt_api_token = token_data['access_token']

    # Then, use that token to initialize the management client
    auth0 = Auth0(
        domain=settings.AUTH0_DOMAIN,
        token=mgmt_api_token
    )
    return auth0

def create_auth0_anonymous_user() -> dict:
    """
    Creates a new, non-interactive user in Auth0 for the guest flow.
    
    Returns:
        The created user object from Auth0.
    """
    auth0 = get_auth0_management_client()
    
    # Generate a unique, random identifier for the anonymous user
    user_id = uuid4()
    
    user_data = {
        "connection": "Username-Password-Authentication", # This is the default database connection
        "email": f"anonymous_{user_id}@guest.brewdock.com",
        "password": f"p_{uuid4()}{uuid4()}", # A strong, random password is required but will not be used
        "email_verified": False,
        "verify_email": False,
        "app_metadata": {
            "is_anonymous": True
        }
    }
    
    try:
        logger.info(f"Creating anonymous user in Auth0 with email: {user_data['email']}")
        new_user = auth0.users.create(user_data)
        logger.info(f"Successfully created Auth0 user with sub: {new_user['user_id']}")
        return new_user
    except Exception as e:
        logger.error(f"Failed to create anonymous user in Auth0: {e}", exc_info=True)
        raise

def get_token_for_user(auth0_sub: str) -> dict:
    """
    Retrieves an access token for a specific user via the Client Credentials Grant.
    This is used to get a real, Auth0-vended token for our anonymous users.
    
    Args:
        auth0_sub: The user's Auth0 ID (subject).
        
    Returns:
        The token response dictionary from Auth0, containing the access_token.
    """
    get_token = GetToken(
        domain=settings.AUTH0_DOMAIN,
        client_id=settings.AUTH0_M2M_CLIENT_ID,
        client_secret=settings.AUTH0_M2M_CLIENT_SECRET,
    )
    
    token_data = get_token.client_credentials(
        audience=settings.AUTH0_API_AUDIENCE,
        body={
            "grant_type": "client_credentials",
            "auth0_sub": auth0_sub
        }
    )
    return token_data 