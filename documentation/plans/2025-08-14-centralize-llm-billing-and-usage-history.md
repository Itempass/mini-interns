### Plan: Centralize OpenRouter Calls, Add Usage History, and Consolidate Billing

#### Goals
- Centralize all OpenRouter calls behind a single service.
- Introduce a dedicated `usage_history` table for cost/usage reporting (separate from agentlogger).
- Add an optional centralized billing flow (balance check, cost retrieval, deduction, and usage logging) with a controlled rollout.
- Keep the frontend cost overview working during transition; switch to new endpoints once validated.

#### Non-Goals (for now)
- Replace or remove agentlogger immediately.
- Backfill historical data (optional later).

---

### Phase 1: Centralize OpenRouter calls with in-function billing and standardize return type
0) Create `shared/services/openrouterservice/` package:
   - Files:
     - `shared/services/openrouterservice/models.py` → defines `LLMCallResult`
     - `shared/services/openrouterservice/client.py` → implements centralized OpenRouter client
     - `shared/services/openrouterservice/__init__.py` → exports public API
   - Leave `shared/services/openrouter_service.py` as a thin compatibility shim (optional) or plan to remove later.
1) Add a single entry point in `shared/services/openrouterservice/client.py`:
   - `chat(*, call_uuid: UUID, messages, model, user_id: UUID, temperature=None, max_tokens=None, tools=None, tool_choice=None, response_format_json: bool = False, step_name=None, workflow_uuid=None, workflow_instance_uuid=None) -> LLMCallResult`
   - Billing occurs inside `chat`: balance check before the call; after receiving a `generation_id`, retrieve cost from OpenRouter and deduct user balance.
   - Introduce a unified `LLMCallResult` model returned by all LLM calls that includes:
     - identity/context: `uuid` (new per-call unique ID), `user_id`, `model`, `provider`, `generation_id`, `step_name`, `workflow_uuid`, `workflow_instance_uuid`
     - timestamps: `start_time`, `end_time`
     - metering: `prompt_tokens`, `completion_tokens`, `total_tokens`
     - costs: `total_cost` (optional in Phase 1), `currency`
     - payloads: `response_text`, `response_message`, `raw_response`
   - Downstream systems (agentlogger, future usage history) will consume this object directly.
2) Migrate call sites to use the centralized `chat` (from `shared/services/openrouterservice/client.py`):
   - `workflow/internals/llm_runner.py`
   - `workflow/internals/agent_runner.py`
   - `workflow_agent/client/internals/agent_runner.py`
   - `prompt_optimizer/llm_client.py`
   - `workflow_agent/mcp/tools.py`
3) Remove/replace the duplicate service in `mcp_servers/tone_of_voice_mcpserver/src/services/openrouter_service.py`.

Acceptance:
- All OpenRouter calls flow through the centralized `chat` and return `LLMCallResult`.
- Billing is enforced inside `chat` (balance check and deduction). `total_cost` is included when available. No `usage_history` persistence yet.

---

### Phase 2: Introduce `usage_history` (separate from agentlogger)
1) Schema (MySQL, same DB as `users`), created idempotently in `scripts/init_workflow_db.py`:
```sql
CREATE TABLE IF NOT EXISTS usage_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BINARY(16) NOT NULL,
  generation_id VARCHAR(255) NOT NULL,
  UNIQUE KEY uniq_generation_id (generation_id),
  operation ENUM('chat_completion','embedding','rerank','other') NOT NULL DEFAULT 'chat_completion',
  model VARCHAR(255) NOT NULL,
  provider VARCHAR(50) NOT NULL DEFAULT 'openrouter',
  step_name VARCHAR(255) NULL,
  workflow_uuid BINARY(16) NULL,
  workflow_instance_uuid BINARY(16) NULL,
  prompt_tokens INT NULL,
  completion_tokens INT NULL,
  total_tokens INT NULL,
  total_cost DECIMAL(10,6) NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'USD',
  start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  end_time TIMESTAMP NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata JSON NULL,
  INDEX idx_user_time (user_id, start_time),
  INDEX idx_user_model_time (user_id, model, start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```
2) Minimal DAO/helpers:
   - `insert_usage_history_entry(...)` (idempotent by `generation_id`).
   - `get_usage_history(user_id, from, to, limit, offset)` and `get_usage_summary(user_id, from, to)`.
3) Backend APIs (read-only):
   - `GET /usage/history?limit&offset&from&to` → returns list and aggregated total.
   - `GET /usage/summary?from&to` → totals by model/operation.
   - Admin mirrors under `/management/users/{user_uuid}/usage/...`.

Acceptance:
- Table is created on startup when missing.
- APIs return usage entries and totals for the authenticated user.

---

### Phase 3: (Removed)
Billing is implemented directly inside the centralized `chat` in Phase 1. No separate wrapper or feature flag rollout is needed.

---

### Phase 3: Frontend wiring
1) Add client methods to call `/usage/history` and `/usage/summary`.
2) Create/adjust the “Usage History” view to use new endpoints; leave agentlogger costs as fallback until validated.

Acceptance:
- Usage History can be switched to use the new endpoints and shows accurate totals.

---

### Phase 4: Cleanup and safeguards
1) Remove remaining direct POSTs to `openrouter.ai` and direct `OpenAI(base_url=...)` usage.
2) Adopt conditional deduction in DB (race-safe) and raise on affected-rows=0.
3) Ensure `generation_id`-based idempotency for retries.

Acceptance:
- All LLM paths go through the centralized service; deduction is atomic and idempotent.

---

### Phase 5: Backfill and deprecation (optional)
1) Optional backfill: project agentlogger cost-bearing logs into `usage_history` to avoid a visual reset of totals.
2) Optionally re-implement `/agentlogger/logs/costs` to read from `usage_history`, or deprecate after a transition period.

Acceptance:
- Historical totals remain coherent if backfilled; agentlogger coupling reduced.

---

### Phase 6: Tests and observability
1) Unit tests:
   - DAO idempotency and range queries.
   - Billing success, retry, insufficient funds.
   - Conditional deduction (race-safe behavior).
2) Logs/metrics for: balance check, cost retrieval, deduction success/failure, usage insert success/failure.

Acceptance:
- CI covers core billing and usage flows; logs are actionable.

---

### Phase 7: Rollout plan
1) Canary enable on one runner; validate rows/balances.
2) Gradually enable across all LLM call sites; monitor error rates and totals.

Acceptance:
- Smooth rollout; no regressions in user experience.


