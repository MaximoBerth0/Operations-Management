# Assistant Module

Source: [app/assistant/](../../app/assistant/) · LLM client: [app/infra/llm/client.py](../../app/infra/llm/client.py) · Design: [design.md](../../app/assistant/design.md)

## Purpose

Lets employees ask the back office questions in plain language ("what should I restock today?") and get answers built from real data. The model never computes numbers: it calls read-only tools that wrap existing services, and writes the answer from their output. The restock math itself lives in [inventory](inventory.md) (`replenishment.py`), not here.

## Architecture

```
 employee ──▶ POST /assistant/chat   (auth, X-Location-Id, rate limit "assistant")
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
| `exceptions.py` | `AssistantError`, `AssistantUnavailable` |
| `tools/base.py` | `Tool`, `ToolContext` |
| `tools/registry.py` | `tools_for()` permission filter, `run_tool()` |
| `tools/inventory_tools.py` | thin adapters over `InventoryService` |
| `infra/llm/client.py` | `LLMClient`: the only place that imports the Anthropic SDK |

Dependencies point one way: `assistant` depends on `inventory` and `rbac`; neither knows the assistant exists.

## Flow

`AssistantService.chat(user_id, location_id, messages)`:

1. Load the user's permission codes (`RBACService.get_user_permissions`) and keep only the tools they allow.
2. Send the system prompt, the conversation and the tool definitions to the model.
3. If the model asks for tools, each call goes through `run_tool`: the permission is checked **again** (the model can name a tool it was never given), the input is validated with the tool's Pydantic schema, and the handler runs. Errors (unknown tool, invalid input, any `AppError` from the service) go back to the model as `is_error` tool results, never as a 500. All results of one turn go back in a single user message, then the loop repeats.
4. If the model answers with text, return it with the list of tools called.
5. After `ASSISTANT_MAX_ITERATIONS` (default 5) model calls without a final answer, return a fixed fallback message.

Details:

- **Tools run sequentially**, even when the model asks for several at once: they share the request's `AsyncSession`, which can't run concurrent queries.
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
| `POST /assistant/chat` | logged-in user + `X-Location-Id` header; tools filtered by the user's permissions |

There's no dedicated permission for the endpoint itself: a user without any of the tool permissions can still chat, but the model gets no tools and can only say it has no data.

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
| `LLM_MAX_TOKENS` | `16000` | output cap per model call |
| `LLM_EFFORT` | `medium` | `output_config.effort`: `low` / `medium` / `high` / `xhigh` / `max` |
| `LLM_TIMEOUT_SECONDS` | `60` | per-request timeout (the SDK retries twice on 429/5xx/network errors) |
| `ASSISTANT_MAX_ITERATIONS` | `5` | model calls per chat request before the fallback answer |

The client is built on first use, so the app starts without a key. Without one, the endpoint returns `503 ASSISTANT_UNAVAILABLE`.

## Rate limiting and logging

- **Rate limit:** policy `assistant` in the Redis token bucket, per user: burst of 10, then one request every 30 seconds. Tunable in prod through `RATE_LIMIT_OVERRIDES` like any other policy.
- **Logging:** each chat logs `assistant chat finished` with `user_id`, `location_id`, `tools_called`, `iterations`, `stop_reason`, `input_tokens` and `output_tokens`, tagged with the request id. Hitting the iteration limit logs a warning. LLM failures log the HTTP status and the Anthropic request id.

## Error cases

| Exception | HTTP | Code | When |
|---|---|---|---|
| `AssistantUnavailable` | 503 | `ASSISTANT_UNAVAILABLE` | LLM API error, timeout, network failure, or no API key configured |
| (validation) | 422 | | bad `messages` (empty, too long, not starting and ending with `user`) |
| (location) | 400 / 404 | | missing `X-Location-Id` / unknown location |
| (rate limit) | 429 | `RATE_LIMITED` | `assistant` bucket empty |

Tool failures are not HTTP errors: they go back to the model as tool results with `error_code` (`TOOL_NOT_AVAILABLE`, `INVALID_TOOL_INPUT`, or the service's own code such as `PRODUCT_NOT_FOUND`), and the model explains them.
