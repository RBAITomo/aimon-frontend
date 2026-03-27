# Code Review: Food Journal + Badge System

**Date:** 2026-03-08
**Reviewer:** code-reviewer agent
**Scope:** 12 new/modified files across frontend (Python/Pygame) and backend (Java/Quarkus)
**Focus:** Correctness, thread safety, edge cases, security, integration

---

## Overall Assessment

Solid feature implementation with clean separation of concerns. Food journal persistence is well-designed with atomic writes and thread-safe locking. Badge system integration follows existing patterns. Several medium-severity issues around thread safety of badge cache, missing input validation on pet_action endpoint, and an encapsulation violation accessing private `_badges_cache` via `getattr`.

---

## Critical Issues

### 1. No input validation on `pet_action` action string (Security)

**File:** `PetMessageHandler.java:472-493`

The `handlePetAction` method accepts any arbitrary `action` string from the WebSocket client with no validation or sanitization. A malicious client can:
- Fire `pet_action` with action=`"unique_food"` and amount=`100` to instantly earn all cookbook badges
- Inject arbitrary action types that pollute the `action_counters` table

```java
// Current: no validation
String action = message.has("action") ? message.get("action").asText("") : "";
int amount = message.has("amount") ? message.get("amount").asInt(1) : 1;
petActionEvent.fire(new PetActionEvent(userId, action, amount));
```

**Recommendation:** Whitelist allowed actions, cap amount to 1 for `unique_food`.

```java
private static final Set<String> ALLOWED_ACTIONS = Set.of("unique_food", "feed", "quest_complete");
private static final int MAX_AMOUNT = 1;

// Validate
if (!ALLOWED_ACTIONS.contains(action)) {
    return sendError(connection, "INVALID_ACTION", "Unknown action: " + action);
}
amount = Math.min(Math.max(amount, 1), MAX_AMOUNT);
```

### 2. BadgeResource has no authentication (Security)

**File:** `BadgeResource.java`

`GET /api/badges/{userId}` has no `@Authenticated` or `@RolesAllowed` annotation. Any caller can enumerate badge progress for any user by iterating userId values (IDOR vulnerability).

**Impact:** Low in current deployment (single-user pet device), but should be addressed before multi-user or public deployment.

**Recommendation:** Add `@Authenticated` or at minimum validate the caller matches the userId.

---

## High Priority

### 3. Thread-unsafe badge cache read/write (Race Condition)

**File:** `pet-event-handler.py:31, 111-114, 242`

`_badges_cache` is:
- Written from background thread in `fetch_badges` (line 242)
- Mutated from WS recv thread in `on_badge_earned` (lines 111-114)
- Read from main render thread via `getattr(self._pet_handler, '_badges_cache', None)` (state_machine.py:1034)

Python's GIL prevents data corruption but not logical races. If `on_badge_earned` iterates the list while `fetch_badges` replaces it with a new list, the mutation applies to the old discarded list. The earned badge disappears from UI until next fetch.

**Recommendation:** Use `_pet_lock` for badge cache access, or use an atomic replace pattern:

```python
def on_badge_earned(self, data):
    ...
    code = data.get("badge_code", "")
    with self._pet_lock:  # protect concurrent access
        if self._badges_cache and code:
            for b in self._badges_cache:
                if b.get("code") == code:
                    b["earned"] = True
                    break

def fetch_badges(self, user_id):
    def _fetch():
        ...
        result = json.loads(resp.read().decode("utf-8"))
        with self._pet_lock:
            self._badges_cache = result
```

### 4. Encapsulation violation accessing `_badges_cache` (Code Quality)

**File:** `state_machine.py:1034`

```python
badges_data=getattr(self._pet_handler, '_badges_cache', None),
```

Accessing a private attribute via `getattr` bypasses encapsulation and is fragile. If the attribute name changes, this silently returns `None` with no error.

**Recommendation:** Add a public property to `PetEventHandler`:

```python
@property
def badges_data(self):
    return self._badges_cache
```

Then: `badges_data=self._pet_handler.badges_data`

### 5. `unique_count()` not thread-safe (Race Condition)

**File:** `food-journal-manager.py:56-58`

```python
def unique_count(self) -> int:
    return len(self._journal)
```

This reads `self._journal` without acquiring `self._lock`. While dict length read is GIL-atomic in CPython, it's inconsistent with the locking discipline used by all other public methods. More critically, this value is used to compose a bubble message and compared against badge thresholds on the backend, so a stale read could cause a race.

**Recommendation:** Add lock:

```python
def unique_count(self) -> int:
    with self._lock:
        return len(self._journal)
```

---

## Medium Priority

### 6. Badge screen shows "Dang tai..." for genuinely empty badge catalogs

**File:** `badge-screen-renderer.py:60-63`

```python
badges = badges_data or []
if not badges:
    self._render_empty(surface)  # shows "Dang tai..."
```

If the REST API returns an empty list `[]` (no badges defined in DB), the UI shows "Dang tai..." (Loading...) indefinitely. There's no way to distinguish "still loading" from "no badges exist."

**Recommendation:** Differentiate `None` (loading) from `[]` (empty):

```python
if badges_data is None:
    self._render_empty(surface)  # "Loading..."
elif len(badges_data) == 0:
    self._render_no_badges(surface)  # "No badges yet"
else:
    # render grid
```

### 7. Selection index can go negative or exceed bounds between renders

**File:** `badge-screen-renderer.py:40-45`

```python
def next_selection(self):
    self._selected += 1

def prev_selection(self):
    self._selected -= 1
```

Selection is clamped in `render()` (line 68), but between button press and render, `_selected` can be negative or exceed `len(badges)`. If `render()` is called with empty `badges_data`, the clamp `max(0, min(self._selected, total - 1))` with `total=0` yields `max(0, min(-1, -1)) = 0`, which is fine. But if another thread reads `_selected` before clamp, it could be invalid.

**Recommendation:** Clamp in the setter methods too:

```python
def next_selection(self, total=None):
    self._selected += 1
    # Clamped on render, but guard here too
```

Not blocking since Pygame is single-threaded for events, but defensive coding is preferred.

### 8. Cookbook sprite cache grows unbounded across page visits

**File:** `cookbook-screen-renderer.py:33, 45, 50`

Cache is cleared on page change, but if user visits page 1, then page 2, then back to page 1, sprites are reloaded and cached again. The cache itself has no size limit. With 20 items per page and a typical 36x36 sprite, memory impact is minimal, so this is low risk.

### 9. `_save()` temp file cleanup on Windows failure

**File:** `food-journal-manager.py:104-109`

If `os.replace()` fails (e.g., antivirus lock on Windows), the temp file remains on disk. The `except` only logs.

**Recommendation:** Add cleanup in the except block:

```python
except OSError as e:
    log.error("Failed to save journal: %s", e)
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
```

### 10. Badge paging not wired (minor gap)

**File:** `badge-screen-renderer.py`

`_page` is managed internally but there's no `next_page()` / `prev_page()` method. If total badges exceed `_PER_PAGE` (10), user has no way to navigate to the next page. Currently the selection wraps via clamp, so items beyond page 0 are unreachable.

**Recommendation:** Add paging methods similar to CookbookScreenRenderer, or auto-advance page when selection moves beyond page bounds.

### 11. Migration V9 assumes `badges` table exists with specific columns

**File:** `V9__cookbook_badges.sql`

The INSERT assumes columns `(code, name, description, category, icon, condition_type, condition_config, xp_reward)` exist. These were likely created in an earlier migration. If the column set changes between V-whatever created `badges` and V9, this fails silently or with a migration error.

**Impact:** Low risk, but worth noting the tight coupling to the badge table schema.

---

## Low Priority

### 12. Menu item count hardcoded in MENU_ITEM_NAMES

**File:** `config.py:209`

`MENU_ITEM_NAMES` has 7 items matching `MenuItem` enum (0-6). If someone adds a menu item to the enum without updating the list, `_render_item_select` will crash with `IndexError`.

**Recommendation:** Assert lengths match at import time, or derive names from the enum.

### 13. Vietnamese text truncation in cookbook grid

**File:** `cookbook-screen-renderer.py:87`

```python
name = journal[key].get("name_vi", key)[:8]
```

Truncating Vietnamese strings at 8 characters can break multi-byte characters or diacritics mid-character. Python 3 handles this correctly at the Unicode level (won't split a codepoint), but 8 chars may cut meaningful Vietnamese words awkwardly.

---

## Positive Observations

- **Atomic file persistence**: `FoodJournalManager._save()` uses temp file + `os.replace()` -- proper crash-safe write pattern
- **Clean separation**: Journal manager, renderers, and event handler each own their domain
- **Lazy sprite loading**: Cookbook and badge screens only load visible page sprites -- important for Pi Zero 2 memory
- **Consistent WS protocol**: `pet_action` follows the same `type`-dispatched pattern as all other WS messages
- **Badge cache invalidation on earn**: `on_badge_earned` updates cache in-place so UI reflects immediately
- **Region map with wildcard matching**: `fruit_*` pattern matching is a nice touch for region resolution
- **Defensive fallback rendering**: Badge screen draws circle+letter when sprite missing

---

## Recommended Actions (Priority Order)

1. **Whitelist allowed actions in `handlePetAction`** -- prevents badge farming exploit
2. **Add locking around `_badges_cache` access** -- prevents lost-update race
3. **Expose `badges_data` as public property** -- fix encapsulation violation
4. **Add lock to `unique_count()`** -- consistency with rest of FoodJournalManager
5. **Differentiate loading vs empty badge state** -- better UX
6. **Add badge page navigation** -- needed when badge count exceeds 10
7. **Add temp file cleanup on save failure** -- Windows edge case
8. **Add auth to BadgeResource** -- before multi-user deployment

---

## Metrics

| Metric | Value |
|--------|-------|
| Files reviewed | 17 |
| New files | 6 |
| Modified files | 11 |
| Critical issues | 2 |
| High issues | 3 |
| Medium issues | 6 |
| Low issues | 2 |
| LOC (new) | ~520 |
| LOC (modified) | ~80 delta |

---

## Unresolved Questions

1. Is `pet_action` amount=1 always the correct increment for `unique_food`? The frontend sends `amount=1` (default), but the WS handler allows arbitrary amounts from any client.
2. Should badge cache be re-fetched periodically, or is the connect-once + in-place-update pattern sufficient for the single-device deployment model?
3. Are badge sprite assets (`assets/badges/cookbook_explorer.png`, etc.) included in the frontend asset bundle? Not verified.
