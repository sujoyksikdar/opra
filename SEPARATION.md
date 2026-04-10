# Allocation–Polls Separation

This document describes the full effort to make the `allocation` Django app functionally independent from the `polls` app. The work was done on the `complete-separation-allocation-polls` branch across 5 commits.

---

## Background

The `allocation` app was originally embedded inside `polls`. All allocation logic — models (`AllocationVoter`, `AllocationCache`), views (`AllocateResultsView`, `RegularAllocationView`, etc.), URLs, and templates — lived inside the polls app. This made it impossible to maintain, extend, or deploy allocation independently.

---

## Phase 1: Create the Allocation App (`8b3ea4d`)

**Goal:** Extract allocation out of polls into its own Django app with no Python-level imports from polls.

### Models
- Removed `AllocationVoter` and `AllocationCache` from `polls/models.py`
- Re-registered them in `allocation/models.py` using `SeparateDatabaseAndState` migrations — no database changes, just ORM ownership transfer
- The underlying tables (`polls_allocationvoter`, `polls_allocationcache`) were preserved as-is

### Views
- Moved all allocation-specific views out of `polls/views.py` into `allocation/views.py`:
  - `AllocateResultsView`, `RegularAllocationView`, `CodeAllocationView`
  - `AllocationOrder`, `setAllocationOrder`, `stopAllocation`
- `polls/views.py` was reduced by ~950 lines

### URLs
- Created `allocation/urls.py` with the `allocation:` namespace
- Mounted it under `/polls/` prefix in `compsocsite/urls.py` to keep existing HTTP paths unchanged
- Updated all URL reversals from `polls:` to `allocation:` namespace throughout templates

### Utilities
- Created `polls/utils.py` for shared helpers: `categorizeResponses`, `getPrefOrder`, `buildResponseDict`, `interpretResponseDict`, `block_code_users`
- Created `allocation/utils.py` for allocation-specific helpers: `getFinalAllocation`, `getAllocMethods`, envy metrics, voter ordering

---

## Phase 2: Full Feature Parity (`15193c6`)

**Goal:** Make allocation match all polls features that had been missing.

### New Models (with migrations)
- `AllocationQuestion` — full standalone question model with all settings fields
- `AllocationItem`, `AllocationResponse`, `AllocationDictionary`, `AllocationKeyValuePair`
- `AllocationLoginCode` — login codes for access-controlled allocations
- `AllocationEmail` — per-question email configuration
- `AllocationSignUpRequest` — self sign-up workflow

### New Modules
- `allocation/email.py` — background email sending thread, matching polls email features (invite CSV, start/stop notifications, custom email)
- `allocation/record.py` — `AllocationRecordView` and `downloadAllocationLatestVotes` for the User Records page

### New Templates
- `pollinfo.html` — full allocation info/settings sidebar with all tabs: Preference Management, Deleted Preferences, User Records, Settings, Access, Email
- `add_step1.html` through `add_step4.html` — creation wizard
- `_view_history.html` — preference management with all visibility modes including the missing `creator_pref == 2` section
- `_invite_voters_new_ui.html` — voter management with search autocomplete and CSV upload
- `_add_choice.html` — item management with Delete Selected, Delete All, CSV upload, bulk/single image upload
- `record.html` — user records page with per-record JSON download
- `confirmation.html`, `self_register.html`, `_display_vote.html`, `_view_deleted_votes.html`, `_visibility.html`, `_approve_request.html`

### Bug Fixes
- **`getPrefOrder` rewrite:** Score-based UIs (budget, slider, star, twoCol) submit preferences as JSON dicts `{"name": "itemText", "score": N}` rather than strings. The original parser only handled the string format, causing item names to silently drop — resulting in numbers (e.g. 50, 33, 17) appearing instead of item names in the Preference Management tab. Fixed to parse both formats.
- **Broken cached `AllocationDictionary` auto-heal:** Entries where all ranks were 1000 (sentinel for unranked) were detected on read and rebuilt from scratch.

---

## Phase 3: Creation Wizard Parity (`2599829`)

**Goal:** Make the allocation creation wizard (add_step1–4) match the polls wizard.

### add_step1
- Added **Allow Ties** Yes/No option (was missing from allocation)
- Removed the Poll/Allocation toggle button (redundant — the header already has dedicated links for each)
- Fixed `polls/views.py` `add_step1` handler: changed `request.POST['questiontype']` to `request.POST.get('questiontype', '1')` to fix a `MultiValueDictKeyError` caused by removing the toggle

### add_step2
- Replaced minimal inline item form with `{% include 'allocation/_add_choice.html' %}` — bringing in Delete Selected, Delete All, CSV upload, bulk image upload, per-item image upload

### add_step3
- Replaced basic `<select multiple>` voter picker with `{% include 'allocation/_invite_voters_new_ui.html' %}` — search autocomplete, group management, CSV upload, email invites

### add_step4
- Added **Accessibility** panel: Anonymous / Invited / Users-Only, Allow Self Sign Up
- Added **Creator preferences** dropdown to Visibility panel
- Added **Results visible after** datetime input
- Extended **Allocation Results** options: Equitability, Fractional Share, Welfare, Pareto Optimality, First-choices
- Added algorithm-locking JS (selected algorithm checkbox auto-checks and disables)

---

## Phase 4: Remove `poll_extra` Template Tag Dependency (`599ebde`)

**Before:** All allocation templates used `{% load poll_extra %}` from the polls app.

**After:** Created `allocation/templatetags/allocation_extra.py` with all 8 filters:
`can_show_results`, `largest`, `smallest`, `index`, `bitwise_and`, `modulus`, `random_utility`, `get_item`

Updated 7 allocation templates to use `{% load allocation_extra %}`.

Also in this commit:
- Replaced `{% extends 'polls/detail.html' %}` with a fully standalone `allocation/detail.html` that extends `polls/base.html` directly, removing polls-specific branches (Poll Winners button, `question_type == 1` checks)
- Added `writeAllocationUserAction` endpoint in `allocation/record.py` to handle AJAX behavior tracking calls from `voting.js` without depending on the polls record handler
- Registered `allocation:record` URL

---

## Phase 5: Remove `polls/voteOptions` Include Dependency (`85d154c`)

**Before:** `allocation/detail.html` included voting UI templates directly from `polls/voteOptions/`. Each template hardcoded `polls:vote` as the form submission URL. A JavaScript hack in `allocation/detail.html` overwrote the form action at runtime to redirect to `allocation:vote`.

**After:**
- Duplicated all 9 voting UI templates into `allocation/voteOptions/`: twoCol, oneCol, slider, stars, yesNo, budgetUI, listUI, infiniteBudget, _comment_section
- Updated form actions in each to use `allocation:vote` directly
- Simplified form action to always use `allocation:vote` (removed the logged-in vs anonymous branch, since allocation handles both through the same endpoint)
- Updated `allocation/detail.html` includes to point to `allocation/voteOptions/`
- Removed the JS form action override hack

---

## What Was Not Changed

### `polls/base.html`

All allocation templates still extend `polls/base.html`. This template contains shared infrastructure used across the entire application — navigation header, login modal, jQuery/Bootstrap loading, static asset references — and is not polls-specific in any meaningful way.

Separating it would require either:
- Adding `DIRS` to `TEMPLATES` in `settings.py` and placing `base.html` at the project level, updating all extends tags across every app, or
- Duplicating it into `allocation/base.html`, creating a maintenance burden whenever the nav changes

Given the effort and the low benefit, this dependency was intentionally left in place. `polls/base.html` functions as the application-wide shared base template.

### Migration FK to polls

`allocation/migrations/0001_initial.py` declares a dependency on a polls migration. This is a historical artifact from when `AllocationVoter` and `AllocationCache` lived in polls and needed the polls tables to exist first. The current `allocation/models.py` has no FK references to polls models — all models are self-contained. There is no runtime impact.

---

## Summary

| Dependency | Before | After |
|---|---|---|
| Allocation views | Inside `polls/views.py` | `allocation/views.py` |
| Allocation models | Inside `polls/models.py` | `allocation/models.py` |
| Template tag | `{% load poll_extra %}` | `{% load allocation_extra %}` |
| Detail page | Extends `polls/detail.html` | Extends `polls/base.html` directly |
| Voting UIs | Included from `polls/voteOptions/` | Included from `allocation/voteOptions/` |
| Vote submission URL | JS hack rewrote `polls:vote` → `allocation:vote` | `allocation:vote` set directly in templates |
| `polls/base.html` | Extended by all templates | Still extended — kept intentionally |
| Migration FK | Historical artifact | No runtime impact, left as-is |
