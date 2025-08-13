import stripe as stripe_sdk
import logging
from typing import Optional
from uuid import UUID

from shared.config import settings, ALLOWED_FRONTEND_ORIGINS
from user import client as user_client
import mysql.connector


def _get_db_connection():
    return mysql.connector.connect(
        host='db',
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        port=3306,
    )


def initialize_stripe_client():
    stripe_sdk.api_key = settings.STRIPE_SECRET_KEY or ''
    logging.getLogger(__name__).info("Stripe client initialized (key configured: %s)", bool(settings.STRIPE_SECRET_KEY))


def is_origin_allowed(origin: str) -> bool:
    return origin in ALLOWED_FRONTEND_ORIGINS


def create_checkout_session(user_uuid: UUID, amount_usd: float, origin: str) -> str:
    """
    Creates a Stripe Checkout Session and stores a pending record.
    Returns the session URL for redirect.
    """
    if not is_origin_allowed(origin):
        raise ValueError("Unrecognized frontend origin")

    initialize_stripe_client()

    # Validate against allowed presets (in cents). Note: Stripe minimum for USD is 50 cents.
    amount_cents = int(round(amount_usd * 100))
    allowed_cents = {500, 1000, 2000, 5000, 10000}
    if settings.ENABLE_TEST_PAYMENT_AMOUNT:
        allowed_cents.add(50)
    if amount_cents not in allowed_cents:
        raise ValueError("Invalid amount")
    success_url = f"{origin}/settings?tab=balance&topup=success"
    cancel_url = f"{origin}/settings?tab=balance&topup=cancel"

    session = stripe_sdk.checkout.Session.create(
        mode="payment",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_uuid": str(user_uuid)},
        line_items=[{
            "price_data": {
                "currency": settings.STRIPE_CURRENCY,
                "unit_amount": amount_cents,
                "product_data": {"name": "Balance top-up"},
            },
            "quantity": 1,
        }],
    )

    # Store pending record
    conn = _get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO stripe_payments (payment_intent_id, checkout_session_id, user_uuid, amount_cents, currency, status)
            VALUES (%s, %s, UUID_TO_BIN(%s), %s, %s, 'pending')
            ON DUPLICATE KEY UPDATE user_uuid = VALUES(user_uuid), amount_cents = VALUES(amount_cents), currency = VALUES(currency)
            """,
            (
                None,
                session.id,
                str(user_uuid),
                amount_cents,
                settings.STRIPE_CURRENCY,
            ),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    logging.getLogger(__name__).info("Created checkout session %s for user %s amount_cents=%s", session.id, user_uuid, amount_cents)
    return session.url


def process_webhook_event(raw_body: bytes, signature_header: str) -> None:
    """
    Verifies the event signature, processes checkout.session.completed idempotently,
    and credits the user's balance.
    """
    initialize_stripe_client()
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET or ''
    logger = logging.getLogger(__name__)
    event = stripe_sdk.Webhook.construct_event(
        payload=raw_body,
        sig_header=signature_header,
        secret=webhook_secret,
    )

    if event['type'] != 'checkout.session.completed':
        return

    obj = event['data']['object']
    if obj.get('payment_status') != 'paid':
        return

    checkout_session_id = obj['id']
    payment_intent_id = obj.get('payment_intent')
    amount_total = obj.get('amount_total')
    currency = obj.get('currency')
    user_uuid_str = (obj.get('metadata') or {}).get('user_uuid')

    if not (amount_total and amount_total > 0 and currency == 'usd' and user_uuid_str):
        raise ValueError('Invalid event payload')

    # Transactional idempotent processing
    conn = _get_db_connection()
    cur = conn.cursor()
    try:
        conn.start_transaction()

        # Fetch or upsert payment row
        # Try to mark as succeeded only if not already succeeded
        cur.execute(
            "SELECT status FROM stripe_payments WHERE payment_intent_id = %s OR checkout_session_id = %s FOR UPDATE",
            (payment_intent_id, checkout_session_id),
        )
        row = cur.fetchone()
        if row and row[0] == 'succeeded':
            logger.info("Idempotent duplicate webhook for session %s/payment_intent %s", checkout_session_id, payment_intent_id)
            conn.commit()
            return

        # Ensure a row exists and update identifiers/amount
        cur.execute(
            """
            INSERT INTO stripe_payments (payment_intent_id, checkout_session_id, user_uuid, amount_cents, currency, status)
            VALUES (%s, %s, UUID_TO_BIN(%s), %s, %s, 'pending')
            ON DUPLICATE KEY UPDATE payment_intent_id = VALUES(payment_intent_id), checkout_session_id = VALUES(checkout_session_id), amount_cents = VALUES(amount_cents), currency = VALUES(currency)
            """,
            (
                payment_intent_id,
                checkout_session_id,
                user_uuid_str,
                amount_total,
                currency,
            ),
        )

        # Credit balance
        amount_usd = round(amount_total / 100.0, 2)
        user_client.add_to_balance(UUID(user_uuid_str), amount_usd)
        logger.info("Credited user %s by $%.2f for session %s/payment_intent %s", user_uuid_str, amount_usd, checkout_session_id, payment_intent_id)

        # Mark succeeded
        cur.execute(
            "UPDATE stripe_payments SET status = 'succeeded' WHERE payment_intent_id = %s OR checkout_session_id = %s",
            (payment_intent_id, checkout_session_id),
        )

        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.exception("Error processing Stripe webhook: %s", e)
        raise
    finally:
        cur.close()
        conn.close()



def get_topups_for_user(user_uuid: UUID) -> list[dict]:
    """
    Returns a list of successful top-up payments for the given user from the stripe_payments table.
    Each entry contains: checkout_session_id, payment_intent_id, amount_cents, currency, status, created_at.
    """
    conn = _get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT checkout_session_id, payment_intent_id, amount_cents, currency, status, created_at
            FROM stripe_payments
            WHERE user_uuid = UUID_TO_BIN(%s) AND status = 'succeeded'
            ORDER BY created_at DESC
            """,
            (str(user_uuid),),
        )
        rows = cur.fetchall() or []
        return rows
    finally:
        cur.close()
        conn.close()
