# Assistant Module

Source: [app/assistant/](../../app/assistant/) · LLM client: [app/infra/llm/client.py](../../app/infra/llm/client.py) · Design: [design.md](../../app/assistant/design.md)

## Purpose

Lets employees ask the back office questions in plain language ("what should I restock today?") and get answers built from real data. The model never computes numbers: it calls read-only tools that wrap existing services, and writes the answer from their output. The restock math itself lives in [inventory](inventory.md) (`replenishment.py`), not here.

## Architecture

```
 employee ──▶ POST /assistant/chat   (assistant:use, X-Location-Id, rate limit "assistant")
                   │
                   ▼
           ┌────────────────┐  tools_for(permissions)  ┌──────────────┐
           │AssistantService│◀─────────────────────────│ tool registry│
           │  (agent loop)  │──── run_tool(...) ──────▶│  (adapters)  │
           └───────┬────────┘                          └──────┬───────┘
                   │                                          │
                   ▼                                          ▼
              LLMClient                               InventoryService
        (infra/llm, Anthropic SDK)                     replenishment.py
```

| File | Role |
|---|---|
| `router.py` | `POST /assistant/chat` |
| `service.py` | `AssistantService.chat`: the agent loop |
| `dependencies.py` | builds the service; maps a missing LLM config to `AssistantUnavailable` |
| `schemas.py` | `ChatRequest`, `ChatMessage`, `ChatResponse` |
| `prompts.py` | system prompt and fixed fallback answers |
| `exceptions.py` | `AssistantError`, `AssistantUnavailable`, `AssistantTimeout`, `AssistantQuotaExceeded` |
| `usage.py` | `UsageMeter` (cost of a chat) and the per-user daily quota in Redis |
| `tools/base.py` | `Tool`, `ToolContext` |
| `tools/registry.py` | `tools_for()` permission filter, `run_tool()` |
| `tools/inventory_tools.py` | thin adapters over `InventoryService` |
| `infra/llm/client.py` | `LLMClient`: the only place that imports the Anthropic SDK |

Dependencies point one way: `assistant` depends on `inventory` and `rbac`; neither knows the assistant exists.

## Flow

`AssistantService.chat(user_id, location_id, messages)`:

0. Check the user's daily quota in Redis; if it's used up, `429 ASSISTANT_QUOTA_EXCEEDED` before any LLM call.
1. Load the user's permission codes (`RBACService.get_user_permissions`) and keep only the tools they allow.
2. Send the system prompt, the conversation and the tool definitions to the model.
3. If the model asks for tools, each call goes through `run_tool`: the permission is checked **again** (the model can name a tool it was never given), the input is validated with the tool's Pydantic schema, and the handler runs. Errors (unknown tool, invalid input, any `AppError` from the service) go back to the model as `is_error` tool results, never as a 500. All results of one turn go back in a single user message, then the loop repeats.
4. If the model answers with text, return it with the list of tools called. Other stop reasons: `refusal` and `max_tokens` return a fixed answer (a response cut by `max_tokens` never runs its tool calls, since their input may be incomplete), `pause_turn` sends the turn back and continues.
5. After `ASSISTANT_MAX_ITERATIONS` (default 5) model calls without a final answer, return a fixed fallback message.
6. Before each model call after the first, if the request's cost is already at `ASSISTANT_MAX_COST_PER_REQUEST`, stop and return the fallback message.
7. Whatever happened (answer, timeout, LLM failure), the request's cost is added to the user's daily usage.
8. The whole request runs under `ASSISTANT_DEADLINE_SECONDS` (default 50, below the ALB's 60s idle timeout). Past it, the loop is cancelled and the client gets `504 ASSISTANT_TIMEOUT`.

Details:

- **Tools run sequentially**, even when the model asks for several at once: they share the request's `AsyncSession`, which can't run concurrent queries.
- **No connection held during LLM calls.** The service commits the session after loading permissions and after each round of tools. Everything is read-only, so the commit only ends the transaction and returns the connection to the pool; the next query takes a new one.
- **Prompt caching.** Two 5-minute breakpoints: one on the system prompt (tools render before it, so it caches both) and the top-level automatic one, which follows the growing conversation. The big saving is inside a request: each iteration reads everything the previous one sent from cache. Across requests only tools + system hit, because the client's text-only history diverges from the tool calls the server saw. Tools come from a fixed list filtered by permissions, so each role gets its own cache entry.
- **Cost units.** Usage is measured in units of one uncached input token, weighted by Claude Opus 5.5 prices: cache reads 0.05, cache writes 1.25, output 5. Raw token counts would make cached requests look as expensive as uncached ones. The weights live in `usage.py`; update them if `LLM_MODEL` changes.
- **Capped results.** `get_stock_levels` and `get_replenishment_suggestions` take a `limit` (default 50, max 200). `total` still counts every row, so the model can tell the list was cut.
- **Current location.** Tools default to the location from the `X-Location-Id` header (same as the stock endpoints). The model only passes a `location_id` when the employee asks about another branch.
- **Stateless.** The client sends the whole conversation on every request (max 20 messages, 4000 chars each, starting and ending with a user message). Only plain text is accepted from the client, so it can't forge tool results; tool calls and their results exist only inside one request.
- **Refusals.** Requests go out with `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`): if the model's safety classifiers decline, the API retries on Anthropic's recommended fallback model. If the whole chain still refuses, the user gets a fixed "can't help" answer.
- **Read-only.** There are no write tools. When they're added, they'll return a pending action that the employee confirms through a separate endpoint (see the design doc).

### Tools

| Tool | Calls | Permission |
|---|---|---|
| `get_replenishment_suggestions` | `InventoryService.get_replenishment_suggestions` | `stock:view` |
| `get_stock_levels` | `InventoryService.get_stock_levels` | `stock:view` |
| `list_stock_movements` | `InventoryService.list_stock_movements` | `stock:view` |
| `list_locations` | `InventoryService.get_location_list` | `location:list` |
| `get_product` | `InventoryService.get_product` | `product:view` |

Adding a tool: write the args schema, a handler that only calls a service, a `Tool(...)` with its permission, and add it to the module's tool list. If the handler starts computing, that code belongs in the service.

## Endpoints

| Endpoint | Auth |
|---|---|
| `POST /assistant/chat` | `assistant:use` + `X-Location-Id` header; tools filtered by the user's permissions |

Two layers of permissions: `assistant:use` decides who can reach the endpoint at all (`employee` and `admin`; `client` and users without a role get 403 before any LLM call, since every request costs tokens), and the tool permissions decide what the model can see once inside.

Request:

```json
{
  "messages": [
    {"role": "user", "content": "What should I restock today?"}
  ]
}
```

Response:

```json
{
  "answer": "Three products need restocking at Downtown: ...",
  "tools_called": ["get_replenishment_suggestions"],
  "iterations": 2
}
```

`iterations` is the number of model calls the request took.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | API key; in prod it comes from Secrets Manager like the other secrets |
| `LLM_MODEL` | `claude-opus-5-5` | model id |
| `LLM_MAX_TOKENS` | `8000` | output cap per model call (thinking included) |
| `LLM_EFFORT` | `medium` | `output_config.effort`: `low` / `medium` / `high` / `xhigh` / `max` |
| `LLM_TIMEOUT_SECONDS` | `25` | per-request timeout (the SDK retries twice on 429/5xx/network errors) |
| `ASSISTANT_MAX_ITERATIONS` | `5` | model calls per chat request before the fallback answer |
| `ASSISTANT_DEADLINE_SECONDS` | `50` | total time per chat request before `504 ASSISTANT_TIMEOUT` |
| `ASSISTANT_MAX_COST_PER_REQUEST` | `200000` | cost units per chat request (about $0.80) before the fallback answer |
| `ASSISTANT_DAILY_COST_PER_USER` | `2500000` | cost units per user per UTC day (about $10) before `429 ASSISTANT_QUOTA_EXCEEDED` |

The cost limits are starting points: tune them from the `cost_units` in the logs.

The client is built on first use, so the app starts without a key. Without one, the endpoint returns `503 ASSISTANT_UNAVAILABLE`.

## Rate limiting and logging

- **Rate limit:** policy `assistant` in the Redis token bucket, per user: burst of 10, then one request every 30 seconds. Tunable in prod through `RATE_LIMIT_OVERRIDES` like any other policy.
- **Daily quota:** key `assistant:usage:{user_id}:{YYYY-MM-DD}` (UTC), incremented by the request's cost units after each chat, expires after 48h. Checked before the call and charged after, so a user can go over by at most one request, which `ASSISTANT_MAX_COST_PER_REQUEST` bounds. Fails open like the rate limit: with Redis off or down, nothing is checked or charged.
- **Logging:** each chat logs `assistant chat finished` with `user_id`, `location_id`, `tools_called`, `iterations`, `stop_reason`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` and `cost_units`, tagged with the request id. Hitting the iteration limit, the request budget, `max_tokens`, the deadline or the daily quota logs a warning. LLM failures log the HTTP status and the Anthropic request id.

## Error cases

| Exception | HTTP | Code | When |
|---|---|---|---|
| `AssistantUnavailable` | 503 | `ASSISTANT_UNAVAILABLE` | LLM API error, timeout, network failure, or no API key configured |
| `AssistantTimeout` | 504 | `ASSISTANT_TIMEOUT` | the request went past `ASSISTANT_DEADLINE_SECONDS` |
| `AssistantQuotaExceeded` | 429 | `ASSISTANT_QUOTA_EXCEEDED` | the user's daily cost reached `ASSISTANT_DAILY_COST_PER_USER` |
| (permission) | 403 | | missing `assistant:use` |
| (validation) | 422 | | bad `messages` (empty, too long, not starting and ending with `user`) |
| (location) | 400 / 404 | | missing `X-Location-Id` / unknown location |
| (rate limit) | 429 | `RATE_LIMITED` | `assistant` bucket empty |

Tool failures are not HTTP errors: they go back to the model as tool results with `error_code` (`TOOL_NOT_AVAILABLE`, `INVALID_TOOL_INPUT`, or the service's own code such as `PRODUCT_NOT_FOUND`), and the model explains them.
