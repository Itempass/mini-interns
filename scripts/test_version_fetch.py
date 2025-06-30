import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path to allow for imports from shared
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from shared.version import get_latest_version

async def main():
    """Runs the test and prints the result."""
    print("Testing get_latest_version()...")
    latest_version = await get_latest_version()
    if latest_version:
        print(f"Success! Fetched version: {latest_version}")
    else:
        print("Failed to fetch version. Result was None.")
        print("This is expected if no releases have been published on GitHub.")

if __name__ == "__main__":
    asyncio.run(main()) 