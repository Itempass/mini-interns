### Stripe integration guide

This folder contains the Stripe integration logic. API endpoints should remain thin wrappers and call functions from `payments/client.py`.

### Environment variables

Add these to your `.env` (use test-mode for dev; live for prod):

```bash
STRIPE_SECRET_KEY=sk_live_or_restricted_key
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_CURRENCY=usd
```

Notes:
- Use a Restricted key with minimal permissions (Checkout Sessions: write; Payment Intents: write if needed). Create it in Dashboard → Developers → API keys → Create restricted key.
- `STRIPE_WEBHOOK_SECRET` comes from either the Stripe CLI (for local testing) or from the Dashboard endpoint’s signing secret (for production).

### Local testing (Docker + Stripe CLI)

Prereq: `docker-compose.override.yaml` exposes the API, e.g. `http://localhost:8000`.

1) Verify API is reachable
- Open `http://localhost:8000/version` in your browser.

2) Login to Stripe CLI (one time)
```bash
stripe login
```

3) Start the listener and forward webhooks to the API
- Test mode:
```bash
stripe listen --forward-to http://localhost:8000/billing/webhook --events checkout.session.completed
```
- Live mode:
```bash
stripe listen --live --forward-to http://localhost:8000/billing/webhook --events checkout.session.completed
# If you use a restricted live key in the backend, ensure the CLI listens on the same account:
# stripe listen --live --api-key sk_live_xxx --forward-to http://localhost:8000/billing/webhook --events checkout.session.completed
```
- Copy the printed Signing secret (starts with `whsec_`) and set `STRIPE_WEBHOOK_SECRET` in `.env`.

4) Run the flow
- From the UI, start a top-up; you will be redirected to Stripe Checkout and back to the app.
- The CLI will forward the webhook to `/billing/webhook`.

5) Validate behavior
- Balance increases by the paid amount (cents → dollars, rounded to 2 decimals).
- Retrying the webhook in CLI does not double-credit (idempotent).
 - Minimum charge in USD is $0.50; presets: $0.50, $5, $10, $20, $50, $100.

Important:
- Point the CLI to the FastAPI backend URL (`/billing/webhook`), not the Next.js proxy.
- The backend derives success/cancel URLs from the request `Origin`, validated against `shared/config.ALLOWED_FRONTEND_ORIGINS`.

### Production setup

1) Create a Restricted API key (live)
- Dashboard → Developers → API keys → Create restricted key.
- Permissions: Checkout Sessions: write; Payment Intents: write if used by Checkout.
- Set `STRIPE_SECRET_KEY` in the server environment.

2) Configure webhook endpoint
- Create a webhook endpoint pointing to `https://<your-api-domain>/billing/webhook` and subscribe to `checkout.session.completed`.
- Copy the endpoint’s signing secret and set `STRIPE_WEBHOOK_SECRET` in the server environment.

3) Frontend origins
- Add your production frontend origin(s) to `shared/config.ALLOWED_FRONTEND_ORIGINS`.

### Code layout and endpoint wrappers

- `api/endpoints/billing.py` should:
  - For `POST /billing/checkout-session`: authenticate user, validate amount, derive and validate `Origin`, then call `stripe.client.create_checkout_session(...)` and return the URL.
  - For `POST /billing/webhook`: read raw body + `Stripe-Signature` header, then call `stripe.client.process_webhook_event(...)`.

- `payments/client.py` should encapsulate:
  - Creating Checkout Sessions (USD only) using the configured key
  - Validating and processing webhook events transactionally and idempotently
  - Persisting `stripe_payments` and crediting user balance via `user.client.add_to_balance`

### Troubleshooting

- Signature verification fails (400): ensure the webhook is sent directly to FastAPI (not via Next.js), and `STRIPE_WEBHOOK_SECRET` matches the CLI/dashboard secret.
- 403 when creating sessions: your Restricted key may lack required permissions; add only the missing ones.
- Amount mismatches: only trust Stripe’s `amount_total` (cents); convert to dollars with rounding.

