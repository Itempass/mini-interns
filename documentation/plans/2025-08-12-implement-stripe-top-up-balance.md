### Title: Implement Stripe-powered User Balance Top-up (Checkout + Webhook)

**Date:** 2025-08-12

**Status:** Draft

---

### 1. Summary

Enable end users (in Auth0 mode) to add funds to their account balance via Stripe. We will use Stripe Checkout (hosted payment page) to keep PCI scope low and rely on webhooks to credit the payment amount to `users.balance` after successful payment. The top-up will be visible and accessible in the existing Settings → Balance tab.

Key properties:
- Hosted Stripe Checkout Session created by our backend
- Stripe webhook with signature verification
- Idempotent crediting using a payment tracking table
- Simple preset amounts (e.g., $5, $10, $20) to reduce validation complexity

Non-goals:
- No subscriptions or recurring billing
- No invoices/receipts management beyond Stripe default
- No refund handling (can be added later)

---

### 2. Prerequisite Reading

- Balance system overview: `documentation/plans/2025-07-24-implement-user-balance-and-credit-system.md`
- Atomicity follow-ups: `documentation/plans/2025-08-12-strengthen-user-module-separation-and-balance-atomicity.md`
- Existing balance code:
  - Backend user client: `user/client.py`
  - Backend DB ops: `user/internals/database.py`
  - User model: `user/models.py`
  - Admin/user endpoints: `api/endpoints/user.py`
  - Balance UI: `frontend/components/settings/BalanceSettings.tsx`
  - Frontend API: `frontend/services/api.ts`
  - Cost history endpoints: `api/endpoints/agentlogger.py`
  - Config: `shared/config.py`
  - DB init/migrations: `scripts/init_workflow_db.py`

---

### 3. High-level Flow

1) User selects a top-up amount in the UI (Balance tab) and clicks “Top up”.
2) Backend creates a Stripe Checkout Session (server-only, using secret key) with metadata `user_uuid` and our preset line item/amount.
3) Frontend redirects to the Checkout Session URL.
4) User completes payment on Stripe; Stripe sends a signed webhook to our public `/billing/webhook`.
5) Our webhook verifies the signature, validates event details, and idempotently credits `users.balance` by the paid amount.
6) Frontend returns to success URL, reloads balance, and shows confirmation.

---

### 4. Data Shapes (no code)

- Create Checkout Session request (frontend → backend):
  - Path: `/billing/checkout-session`
  - Body (example):
    ```json
    { "amount_usd": 10 }
    ```
    or
    ```json
    { "amount_cents": 1000 }
    ```
  - Constraints: allowed set [5, 10, 20, 50, 100] USD or a bounded range (1–500 USD).

- Create Checkout Session response (backend → frontend):
  - Body:
    ```json
    { "url": "https://checkout.stripe.com/c/session_..." }
    ```

- Webhook event (Stripe → backend):
  - Event types handled: `checkout.session.completed` (and optionally `payment_intent.succeeded`)
  - Relevant payload fields (from event.data.object):
    - `id` (Checkout Session ID)
    - `payment_intent` (PaymentIntent ID)
    - `amount_total` (integer, cents)
    - `currency` (e.g., "usd")
    - `payment_status` (expect "paid")
    - `metadata.user_uuid` (UUID string we set when creating the session)

- Payment tracking record (our DB):
  - `payment_intent_id` (string, unique)
  - `checkout_session_id` (string, unique, optional but recommended)
  - `user_uuid` (BINARY(16))
  - `amount_cents` (integer)
  - `currency` (string, e.g., "usd")
  - `status` (string enum: "pending", "succeeded", "refunded", etc.)
  - `created_at` (timestamp)

---

### 5. Backend Tasks

5.1 New configuration
- Add to `shared/config.py` and environment:
  - `STRIPE_SECRET_KEY`
  - `STRIPE_WEBHOOK_SECRET`
  - `STRIPE_CURRENCY` (default `usd`)
  - `FRONTEND_BASE_URL` (for success/cancel redirects)

5.2 Dependencies
- Add Python package: `stripe`

5.3 New endpoints (`api/endpoints/billing.py`)
- POST `/billing/checkout-session` (auth required)
  - Validates amount against allowed presets/range
  - Creates Stripe Checkout Session with:
    - `mode = "payment"`
    - `success_url = {FRONTEND_BASE_URL}/settings?tab=balance&topup=success`
    - `cancel_url = {FRONTEND_BASE_URL}/settings?tab=balance&topup=cancel`
    - `metadata = { "user_uuid": str(current_user.uuid) }`
    - Line item with price_data (currency, name "Balance top-up", unit_amount in cents)
  - Stores a pending record (see 5.5) with `checkout_session_id`, `user_uuid`, `amount_cents`, `currency`, `status='pending'`
  - Returns `{ url }`

- POST `/billing/webhook` (no auth; Stripe-signed)
  - Verifies signature using `STRIPE_WEBHOOK_SECRET`
  - Accept only event(s): `checkout.session.completed` (and optionally require `payment_status == 'paid'`)
  - Extracts: `checkout_session_id`, `payment_intent_id`, `amount_total`, `currency`, `metadata.user_uuid`
  - Finds matching pending record; if not found, ignore or log (defense-in-depth)
  - Idempotency: if `payment_intent_id` or `checkout_session_id` already marked processed → do nothing
  - Validations:
    - `amount_total` > 0
    - `currency` equals `STRIPE_CURRENCY`
    - `metadata.user_uuid` matches the pending record
  - Crediting: convert cents to dollars and call `user_client.add_to_balance(user_uuid, amount_usd)`
  - Mark payment record as `succeeded` and store the credited amount

5.4 Include router
- In `api/main.py`, include the new `billing` router

5.5 Database changes
- Add new table for payment idempotency/tracking, e.g., `stripe_payments`:
  - Fields listed in section 4
  - Unique index on `payment_intent_id` (and/or `checkout_session_id`)
- Optionally add `pending_topups` table; or reuse `stripe_payments` with `status='pending'` when session is created
- Implement migration in `scripts/init_workflow_db.py` (guarded by existence checks)

5.6 User module additions (atomic increment)
- `user/internals/database.py`: add `add_to_balance(user_uuid: UUID, amount: float)` → `UPDATE users SET balance = balance + :amount WHERE uuid = ...`
- `user/client.py`: expose `add_to_balance(...)`
- Confirm alignment with `2025-08-12-strengthen-user-module-separation-and-balance-atomicity.md` (keep operations atomic and race-safe)

5.7 Access control
- Only show and enable top-up in Auth0 mode (aligns with current enforcement that only Auth0 users are billed)

---

### 6. Frontend Tasks

6.1 UI changes (Settings → Balance)
- File: `frontend/components/settings/BalanceSettings.tsx`
  - Add a “Top up balance” card with preset buttons ($5, $10, $20, $50, $100)
  - Add a confirm button to initiate top-up
  - On click: call backend `POST /billing/checkout-session` with the selected amount; redirect browser to returned URL
  - On return to success URL: refresh balance via `getMe()` and display a success message
  - Hide/disable this section unless backend says mode is Auth0 (via existing `GET /auth/mode`)

6.2 Frontend API
- File: `frontend/services/api.ts`
  - Add `createCheckoutSession(amountUsd: number)` that POSTs to backend and returns `{ url }`

6.3 Optional enhancements
- Remember last amount
- Add a small “Top up” shortcut button in top bar that deep-links to Settings → Balance

---

### 7. Security & Integrity

- Webhook signature verification: required, using `Stripe-Signature` + `STRIPE_WEBHOOK_SECRET`
- Process only expected event types and require `payment_status == 'paid'`
- Idempotency: persist and check `payment_intent_id` or `checkout_session_id` to avoid double-credit
- Trust Stripe amounts only (ignore client-sent numbers in webhook)
- Validate that the webhook’s session matches a server-created pending record (amount, currency, user)
- Restrict to preset amounts (or strict min/max bounds) to avoid abuse
- Do not expose secret keys in frontend; only backend creates sessions

---

### 8. Testing & Verification

- Local webhook relay: Stripe CLI → `stripe listen --forward-to http://localhost:<API_PORT>/billing/webhook`
- Manual tests:
  - Create session for $5 top-up; complete with test card; confirm DB shows credited amount and UI updates
  - Retry delivery of webhook to verify idempotency
  - Mismatched currency/amount test: ensure webhook is rejected
  - Unknown session test: ensure webhook is ignored/logged
- Unit tests:
  - `user` module: `add_to_balance` correctly increments and returns updated user
  - Payment tracking repository: upsert, idempotency, status transitions
- Integration tests (if feasible): mock Stripe signature verification and simulate event payloads

---

### 9. Rollout Checklist

- [ ] Add `stripe` to backend dependencies (`requirements.txt`)
- [ ] Configure environment variables in deployment: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `FRONTEND_BASE_URL`, `STRIPE_CURRENCY`
- [ ] Database migration: create `stripe_payments` table
- [ ] Implement backend endpoints and include router
- [ ] Implement `add_to_balance` in user module
- [ ] Add frontend UI in Balance page and API function
- [ ] Test end-to-end with Stripe CLI
- [ ] Document operational steps (how to rotate webhook secret, verify logs)

---

### 10. Open Questions

1) Accepted currencies: stick with `usd` or make it configurable per deployment?
2) Maximum single top-up amount we want to allow?
3) Do we need admin visibility of payment history in Management page now, or later?
4) Should we add refund handling that decrements balance when Stripe issues refunds (future work)?
5) Should we support Payment Links as a fallback for static deployments (future alternative)?

---

### 11. File References & Edits

- New: `api/endpoints/billing.py`
- Edit: `api/main.py` (include router)
- Edit: `user/internals/database.py` (add `add_to_balance`, payment tracking persistence functions)
- Edit: `user/client.py` (expose `add_to_balance`)
- Edit: `scripts/init_workflow_db.py` (create `stripe_payments` table; guarded)
- Edit: `shared/config.py` (new settings)
- Edit: `requirements.txt` (add `stripe`)
- Edit: `frontend/services/api.ts` (add `createCheckoutSession`)
- Edit: `frontend/components/settings/BalanceSettings.tsx` (add top-up UI)


