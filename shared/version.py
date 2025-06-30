from pathlib import Path
import httpx
import logging
import json
import time

# Set up logging
logger = logging.getLogger(__name__)

# The Dockerfile places the VERSION file in the /app directory.
# Using an absolute path is more robust inside the container.
VERSION_FILE_PATH = Path("/app/VERSION")
LATEST_RELEASE_API_URL = "https://api.github.com/repos/Itempass/mini-interns/releases/latest"

_latest_version_cache = {
    "version": None,
    "timestamp": 0,
}
CACHE_DURATION_SECONDS = 3600  # 1 hour

def get_version() -> str:
    """Reads the version from the VERSION file."""
    try:
        return VERSION_FILE_PATH.read_text().strip()
    except FileNotFoundError:
        return "0.0.0-dev"

__version__ = get_version()

async def get_latest_version() -> str | None:
    """
    Fetches the latest official release version from the GitHub API.
    The result is cached for 1 hour to avoid excessive API calls.
    """
    # Check if a valid, non-expired version is in the cache
    now = time.time()
    if _latest_version_cache["version"] and (now - _latest_version_cache["timestamp"] < CACHE_DURATION_SECONDS):
        logger.info("Returning cached version.")
        return _latest_version_cache["version"]

    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"Fetching latest release from {LATEST_RELEASE_API_URL}")
            # The GitHub API requires a User-Agent header.
            headers = {'User-Agent': 'Mini-Interns-Version-Checker'}
            response = await client.get(LATEST_RELEASE_API_URL, headers=headers, follow_redirects=True)
            response.raise_for_status()

            data = response.json()
            tag_name = data.get('tag_name', '').strip()

            # The tag name might be something like "v0.0.1", so we strip the "v".
            if tag_name.startswith('v'):
                latest_version = tag_name[1:]
            else:
                latest_version = tag_name

            if latest_version:
                logger.info(f"Successfully fetched latest release version: {latest_version}")
                # Update cache
                _latest_version_cache["version"] = latest_version
                _latest_version_cache["timestamp"] = now
                return latest_version
            else:
                logger.warning("Latest release not found or tag_name is empty.")
                return None

        except httpx.RequestError as e:
            logger.error(f"Error fetching latest version from GitHub API: {e}")
            return None
        except (httpx.HTTPStatusError, json.JSONDecodeError) as e:
            logger.error(f"Error processing GitHub API response: {e}")
            return None 