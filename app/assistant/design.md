# Assistant: design

An AI assistant that lets employees ask the back office questions in plain language, starting with the one they ask every morning: **"what should I restock today?"**

This is a design doc. Part of it is already built (see [Status](#status)); the rest is the plan.

## The problem

The system already tells you when something **is** low: each stock row has a `reorder_point`, and crossing it sends an email. What it can't answer is what an employee actually wants to know:

- "What do I need to restock today, and how much?"
- "What will run out this week at the current sales pace?"
- "Why did product X drop so much at location Y?"

The data to answer these is already in the database: `out` movements (consumption history), `reserved_quantity` (committed demand), `reorder_point`, and locations. What's missing is combining it and explaining it.

## Principles

1. **The math is deterministic, the LLM explains it.** The model never computes how much to restock. A plain, tested Python function does, and the model calls it as a tool and writes the answer. Knowing where *not* to use an LLM is part of the design.
2. **The agent is just another interface over the service layer**, like the REST API. Tools call services, never repositories, so they inherit the validation and locking that's already there.
3. **Permissions are the same permissions.** A tool declares the permission it needs, exactly like a route does with `require_permission(...)`. A user only gets the tools their role allows.
4. **Read-only first.** Writes (receiving stock, creating orders) come later and always go through human confirmation.
5. **Dependencies point one way.** `assistant` depends on `inventory` and `orders`, never the other way around. Inventory doesn't know an LLM exists.

## Overview

```
 employee ──▶ POST /assistant/chat
                   │
                   ▼
           ┌───────────────┐   tools allowed for this user
           │ AssistantSvc  │◀──────────────────────────── registry (filters by permission)
           │  (agent loop) │
           └──┬─────────┬──┘
              │         │ tool calls
              ▼         ▼
          LLM API   InventoryService / OrderService
                        │
                        ▼
                  replenishment.py  (pure math)
```

## Module layout

```
app/
├── inventory/
│   ├── replenishment.py        # pure restock math, no DB          [built]
│   └── service.py              # get_replenishment_suggestions()   [built]
│
├── assistant/
│   ├── design.md               # this file
│   ├── router.py               # POST /assistant/chat
│   ├── service.py              # agent loop: message → LLM → tools → answer
│   ├── schemas.py              # ChatRequest, ChatResponse
│   ├── prompts.py              # system prompt
│   └── tools/
│       ├── base.py             # Tool, ToolContext (split out to avoid an import cycle)  [built]
│       ├── registry.py         # permission filtering + run_tool()                        [built]
│       ├── inventory_tools.py  # thin adapters over InventoryService                      [built]
│       └── order_tools.py      # thin adapters over OrderService
│
└── infra/
    └── llm/
        └── client.py           # LLM client wrapper, same idea as mailer.py
```

Why two places? The restock calculation is **inventory domain logic**: a REST endpoint or the worker can use it too, not only the agent. The tools are **adapters**: they turn the JSON the model sends into a service call and return the result. They're closer to routers than to services.

## Replenishment math

Lives in [replenishment.py](../inventory/replenishment.py). It's a set of pure functions: numbers in, a result out. The service fetches the data and calls it.

### Inputs

- **`StockSnapshot`**: `quantity`, `reserved_quantity` and `reorder_point` of one stock row, plus `available = quantity - reserved_quantity`. It's called a snapshot because it's a frozen copy of the row at the moment the service read it: immutable, detached from the SQLAlchemy session, and testable without Postgres.
- **`consumed`**: total units that left that stock row during the window. The function doesn't care where the number comes from.
- **`ReplenishmentPolicy`**:

| Field | Default | Meaning |
|---|---|---|
| `window_days` | 30 | history used to estimate consumption |
| `horizon_days` | 7 | restock if stock runs out within this many days |
| `target_days` | 30 | after restocking, cover this many days |

### Formulas

```
daily_consumption = consumed / window_days
days_of_coverage  = available / daily_consumption      (None if no consumption)

needs_restock = available <= reorder_point             (when reorder_point > 0)
             or days_of_coverage <= horizon_days

target_level       = max(ceil(daily_consumption * target_days), reorder_point + 1)
suggested_quantity = max(target_level - available, 0)  (0 when no restock needed)
```

The `reorder_point` rule is the same one the low stock alerts use, so the assistant and the emails never disagree. The `+ 1` makes sure a restock always leaves the row above the alert threshold.

### Examples

| Situation | Result |
|---|---|
| 15 available, 3/day | 5 days of coverage, restock 75 |
| 100 available, 1/day | no restock |
| no history, 4 available, reorder point 5 | restock 2 (ends at 6) |
| over-reserved (-3 available), 2/day | restock 63 |

### Where consumption comes from

Consumption is the sum of `out` movements in the window. For that to be true, **every unit that leaves has to produce an `out` movement**. Manual `remove_stock` always did. Completing an order didn't: `fulfill_for_item` lowered `quantity` without recording anything, so sales were invisible in the history.

That's fixed: `fulfill_for_item` now records an `OUT` movement with `created_by` set to the user who completed the order. The movement is staged with `stock_repo.add_movement` (no commit) so it lands in the same single commit as the rest of `complete_order`. Using `create_movement` there would have committed per item, dropping the `FOR UPDATE` locks and leaving half-completed orders on failure.

## Tools

### The registry

Each tool declares its input schema and the permission it needs:

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: type[BaseModel]
    permission: str
    handler: Callable[..., Awaitable[BaseModel]]

def tools_for(user_permissions: set[str]) -> list[Tool]:
    return [t for t in ALL_TOOLS if t.permission in user_permissions]
```

A tool stays tiny:

```python
async def get_replenishment(args: ReplenishmentArgs, ctx: ToolContext):
    return await ctx.inventory_service.get_replenishment_suggestions(
        location_id=args.location_id, horizon_days=args.horizon_days
    )

TOOL = Tool(
    name="get_replenishment_suggestions",
    description="Products that should be restocked, with days of coverage and suggested qty",
    input_schema=ReplenishmentArgs,
    permission="stock:view",
    handler=get_replenishment,
)
```

### First set (read-only)

| Tool | Calls | Permission |
|---|---|---|
| `get_replenishment_suggestions` | `InventoryService.get_replenishment_suggestions` | `stock:view` |
| `get_stock_levels` | `InventoryService.get_stock_levels` | `stock:view` |
| `list_stock_movements` | `InventoryService.list_stock_movements` | `stock:view` |
| `list_locations` | `InventoryService.get_location_list` | `location:list` |
| `get_product` | `InventoryService.get_product` | `product:view` |

There's no `order:view` permission yet, so order tools wait until one exists.

### Rules

1. Tools call services, never repositories.
2. No logic in tools. If a tool starts computing, that code belongs in a service.
3. Permissions are checked twice: when building the list the model sees, and again when executing. The model can hallucinate the name of a tool it wasn't given.
4. Tool inputs are validated with the Pydantic schema before the handler runs. Invalid input goes back to the model as a tool error, not as a 500.

## The agent loop

`AssistantService.chat(user, messages)`:

1. Resolve the user's permissions and build the tool list with `tools_for(...)`.
2. Send the system prompt, conversation and tool definitions to the model.
3. If the model asks for tools: validate input, re-check permission, run the handler, append the results, go back to 2.
4. If the model answers with text: return it, along with the list of tools that were called.
5. Stop after a fixed number of iterations (e.g. 5) and return a fallback message, so a confused model can't loop forever.

The system prompt tells the model to use tools for every number it mentions, never to invent quantities, and to say so when the data isn't there.

**Conversation state:** stateless to start. The client sends the history with each request. Storing conversations server-side can come later if needed.

**Model:** configurable through `settings` (e.g. `LLM_MODEL`), API key in Secrets Manager like the other secrets.

## Writes, later

The agent never writes directly. When a write tool is added (e.g. "receive 40 units of X"), it returns a **pending action** instead of executing it. The employee confirms it through a separate endpoint, which calls the normal service with the normal permission check. Human in the loop, and the audit trail still shows the real user.

## Production concerns

- **Rate limiting:** a dedicated `assistant` policy in the Redis token bucket, per user. Every request costs money, so it should be much tighter than `default`.
- **Logging:** each request logs the user, the tools called, the iterations and token usage, tied to the existing request id.
- **Errors:** LLM failures map to an `AppError` subclass, so clients get the usual `{error_code, detail}`.

## Async use: smarter low stock emails

The same `get_replenishment_suggestions` can enrich the `low_stock_alert` worker task. Instead of "Product X is low", the email says "Product X has 2 days of coverage at the current pace, suggest ordering 40 units; 3 confirmed orders are holding it". That doesn't need the LLM at all, but the email can optionally get a short generated summary.

## Testing

- **`replenishment.py`:** plain unit tests with hand-picked numbers, no database.
- **Service method:** integration tests against Postgres, like the rest of the suite.
- **Agent loop:** the LLM client is mocked to return scripted tool calls, checking that tools run, permissions are enforced, and the loop stops.
- **Evals:** a small set of known questions ("what should I restock at location A?") run against the real model, checking which tools were called and that the numbers in the answer match the tool output.

## Status

- [x] `inventory/replenishment.py`: restock math
- [x] Order completion records `OUT` movements
- [x] Unit tests for `replenishment.py`
- [x] `InventoryService.get_replenishment_suggestions` (+ consumption query)
- [ ] `infra/llm/client.py`
- [x] Tool registry and read-only tools
- [ ] `POST /assistant/chat` with the agent loop
- [ ] Rate limit policy and logging
- [ ] Enriched low stock emails
- [ ] Write tools with confirmation
