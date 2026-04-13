---
description: Momentum project session start — load mempalace context before any work
---

## Momentum Session Start Protocol

Always run this at the start of every session involving the momentum project.

### Step 1: Load palace overview
Call `mempalace_status` to get current wing/room inventory.

### Step 2: Read diary
Call `mempalace_diary_read(agent_name="cascade", last_n=5)` to recall recent sessions.

### Step 3: Query project state
Call `mempalace_kg_query(entity="momentum project")` to verify current config facts.

### Step 4: Before answering any question
Call `mempalace_search(query=<topic>, wing="momentum")` or `mempalace_kg_query(entity=<entity>)` FIRST. Never guess.

### Step 5: After session ends
Call `mempalace_diary_write(agent_name="cascade", entry=<AAAK summary>)`.

### Step 6: When facts change (e.g. TOP_N, circuit breaker, capital)
Call `mempalace_kg_invalidate(...)` on old fact, then `mempalace_kg_add(...)` for new value.
