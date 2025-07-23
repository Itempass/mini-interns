import httpx
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError
from typing import Dict, Any, Optional

from shared.config import settings

# A simple in-memory cache for the JWKS
_jwks: Optional[Dict[str, Any]] = None

async def get_jwks() -> Dict[str, Any]:
    """
    Fetches and caches the JSON Web Key Set (JWKS) from the Auth0 domain.
    The JWKS contains the public keys used to verify JWTs.
    """
    global _jwks
    if _jwks is None:
        jwks_url = f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            _jwks = response.json()
    return _jwks

async def validate_auth0_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validates a JWT access token from Auth0.
    
    - Fetches the JWKS from Auth0.
    - Verifies the token's signature using the correct public key.
    - Validates the audience and issuer claims.
    
    Returns the decoded payload if valid, otherwise None.
    """
    try:
        jwks = await get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
        
        if rsa_key:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=settings.AUTH0_API_AUDIENCE,
                issuer=f"https://{settings.AUTH0_DOMAIN}/",
            )
            return payload

    except ExpiredSignatureError:
        print("[AUTH_VALIDATOR] Token has expired.")
        return None
    except JWTClaimsError as e:
        print(f"[AUTH_VALIDATOR] Token claims are invalid: {e}")
        return None
    except JWTError as e:
        print(f"[AUTH_VALIDATOR] Signature validation failed: {e}")
        return None
    except Exception as e:
        print(f"[AUTH_VALIDATOR] An unexpected error occurred during token validation: {e}")
        return None
        
    print("[AUTH_VALIDATOR] Could not find a matching key in JWKS.")
    return None 