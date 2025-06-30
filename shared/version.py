from pathlib import Path

# The Dockerfile places the VERSION file in the /app directory.
# Using an absolute path is more robust inside the container.
VERSION_FILE_PATH = Path("/app/VERSION")

def get_version() -> str:
    """Reads the version from the VERSION file."""
    try:
        return VERSION_FILE_PATH.read_text().strip()
    except FileNotFoundError:
        return "0.0.0-dev"

__version__ = get_version() 