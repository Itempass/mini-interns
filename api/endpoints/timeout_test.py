
from fastapi import APIRouter
import asyncio

router = APIRouter()

@router.get("/timeout-test")
async def timeout_test(delay: int = 60):
    """
    An endpoint to test timeouts. It waits for a specified delay before responding.
    """
    print(f"Starting timeout test with a delay of {delay} seconds.")
    await asyncio.sleep(delay)
    print(f"Finished timeout test after {delay} seconds.")
    return {"status": "success", "delay": delay} 