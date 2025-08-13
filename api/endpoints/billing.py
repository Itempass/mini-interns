import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from api.endpoints.auth import get_current_user
from user.models import User
from user import client as user_client
from payments import client as payments_client


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


class CreateCheckoutSessionRequest(BaseModel):
    amount_usd: float = Field(..., description="Top-up amount in USD. Allowed presets; fractional supported for testing where permitted by Stripe.")


@router.post("/checkout-session")
async def create_checkout_session(request: Request, body: CreateCheckoutSessionRequest, current_user: User = Depends(get_current_user)):
    # Enforce Auth0 mode only
    if user_client.get_auth_mode() != "auth0":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Top-up is only available in Auth0 mode.")

    origin = request.headers.get("origin")
    if not origin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Origin header")

    try:
        url = payments_client.create_checkout_session(
            user_uuid=current_user.uuid,
            amount_usd=body.amount_usd,
            origin=origin,
        )
        return {"url": url}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    # No user auth here; verify Stripe signature only
    signature = request.headers.get("stripe-signature", "")
    try:
        payload = await request.body()
        payments_client.process_webhook_event(raw_body=payload, signature_header=signature)
        return {"status": "ok"}
    except Exception as e:
        # On validation/signature failures, return 400 to prompt Stripe retries when appropriate
        logger.warning(f"Stripe webhook processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook processing failed")


