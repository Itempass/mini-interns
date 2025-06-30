from pathlib import Path
import httpx

# The Dockerfile places the VERSION file in the /app directory.
# Using an absolute path is more robust inside the container.
VERSION_FILE_PATH = Path("/app/VERSION")
REMOTE_VERSION_URL = "https://github.com/Itempass/mini-interns/blob/main/VERSION" 

def get_version() -> str:
    """Reads the version from the VERSION file."""
    try:
        return VERSION_FILE_PATH.read_text().strip()
    except FileNotFoundError:
        return "0.0.0-dev"

__version__ = get_version()

async def get_latest_version() -> str | None:
    """Fetches the latest version from the remote repository."""
    if "your-username" in REMOTE_VERSION_URL:
        # Don't try to fetch if the URL is still a placeholder
        return None
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(REMOTE_VERSION_URL)
            response.raise_for_status()  # Raise an exception for bad status codes
            return response.text.strip()
        except httpx.RequestError as e:
            # Handle request errors (e.g., network issues)
            print(f"Error fetching latest version: {e}")
            return None
        except httpx.HTTPStatusError as e:
            # Handle non-2xx responses
            print(f"Error response {e.response.status_code} while fetching latest version.")
            return None 