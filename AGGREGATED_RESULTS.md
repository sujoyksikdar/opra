# Aggregated Results Feature

## Overview

The Aggregated Results page provides a statewide view of mock election outcomes across multiple polls. When multiple mock elections are created for different congressional districts within the same state and year, the aggregated results page combines all their votes and displays a unified interactive map showing which candidate leads in each district — along with charts, algorithm comparisons, and a district-by-district breakdown.

---

## How It Works

### Individual Poll Setup

Each mock election is created with a **State**, **District**, and **Year** (e.g., Texas → District 5 → 2026). This ties the poll to a specific congressional district and election year. Voters participate in their district's poll and rank candidates in order of preference.

A single district can have multiple polls (e.g., two separate polls for District 5 in Texas in 2026). All of their votes are combined during aggregation.

Candidates do **not** need to be identical across all polls. If a poll introduces a new candidate not present in other polls, that candidate is included in the aggregation automatically (see `buildUnifiedCandMap` below).

### Accessing Aggregated Results

On the **Poll Settings page** (`pollinfo`), poll owners who have started or ended a poll will see an **"Aggregated Results"** button next to the "Recalculate Result" button. The button is only shown if the poll has both `state` and `year` set. Clicking it navigates to:

```
/mock_election/aggregated/<State>/<Year>/
```

For example: `/mock_election/aggregated/Texas/2026/`

**Access control:** Only users who own at least one poll in that state and year can view the page. Other users get a 404.

---

## What the Page Shows

### 1. District Map (with Algorithm Dropdown)

A Leaflet.js interactive map of the selected state showing all congressional district boundaries. Each district polygon is **colored by the winning candidate** in that district.

- **Algorithm dropdown** (top right of map card): Select from all 16 voting algorithms. Algorithms 8–15 (STV, Baldwin, Coombs, etc.) are labeled "(may be slow)". Changing the algorithm fires an AJAX request — the map recolors without a page reload.
- **Loading spinner**: Shown over the map while the AJAX request is in progress.
- **Sidebar (left)**: Lists all districts with checkboxes. Unchecking a district removes it from the map.
- **Hover tooltip**: Shows the district winner and score/vote percentages per candidate.
- **District coloring**: Grey means no votes have been cast in that district.

### 2. Right Panel (Score-based vs Winner-only)

The right panel changes depending on the selected algorithm:

| Algorithm type | Panel shown |
|---|---|
| Score-based (Plurality, Borda, Veto, K-Approval, Bucklin, Copeland, Maximin) | **Pie chart** with score proportions + candidate breakdown with scores and percentages |
| Winner-only (STV, Baldwin, Coombs, Black, Ranked Pairs, Plurality Runoff, Borda Mean, Simulated Approval) | **Winner Podium** card — trophy icon for winner(s), numbered runners-up listed below |

### 3. Statewide Algorithm Comparison Table

A static table showing scores or win/loss (1/0) for every candidate under all 16 algorithms, computed from the combined votes across all polls in the state and year. Rendered on page load; does not change when the dropdown changes.

### 4. District Winners Table (bottom)

A dynamic table listing each district, its winning candidate (with colored dot), and the first-choice vote breakdown per candidate. The table title updates to show the currently selected algorithm name. Updates on each algorithm change via AJAX.

---

## Algorithm Classification

| Index | Algorithm | Type |
|---|---|---|
| 0 | Plurality | Score-based |
| 1 | Borda | Score-based |
| 2 | Veto | Score-based |
| 3 | K-Approval (k=3) | Score-based |
| 4 | Simplified Bucklin | Score-based |
| 5 | Copeland | Score-based |
| 6 | Maximin | Score-based |
| 7 | MaxiMin-Duplicate | Score-based |
| 8 | STV | Winner-only (slow) |
| 9 | Baldwin | Winner-only (slow) |
| 10 | Coombs | Winner-only (slow) |
| 11 | Black | Winner-only (slow) |
| 12 | Ranked Pairs | Winner-only (slow) |
| 13 | Plurality With Runoff | Winner-only (slow) |
| 14 | Borda Mean | Winner-only (slow) |
| 15 | Simulated Approval | Winner-only (slow) |

Score-based algorithms return a numeric score per candidate. Winner-only algorithms return 1 (winner) or 0 (not winner) per candidate.

---

## URL Structure

| URL | View | Purpose |
|---|---|---|
| `/mock_election/aggregated/<state>/<year>/` | `AggregatedResultsView` | Main aggregated results page |
| `/mock_election/aggregated/<state>/<year>/district_winners/?alg=<index>` | `DistrictWinnersAPIView` | AJAX endpoint — returns district winners and statewide scores for a given algorithm |

---

## Technical Implementation

### Files Changed

| File | Change |
|---|---|
| `mock_election/models.py` | Added `year = IntegerField(null=True, blank=True)` to `MockElectionQuestion` |
| `mock_election/migrations/0007_mockelectionquestion_year.py` | Migration for the `year` field |
| `mock_election/views.py` | Added `AggregatedResultsView`, `DistrictWinnersAPIView`, `runSingleAlgorithm()`, `buildUnifiedProfile()`, `buildUnifiedCandMap()` |
| `mock_election/urls.py` | Added URL patterns for aggregated results page and AJAX API |
| `mock_election/templates/mock_election/aggregated_results.html` | New template — map, pie chart, podium, algorithm table, district table |
| `mock_election/templates/mock_election/pollinfo.html` | Added "Aggregated Results" button; shows year in location row |
| `mock_election/templates/mock_election/add_step1.html` | Added State, District, and Year fields on poll creation |
| `mock_election/templates/mock_election/regular_polls.html` | Shows year on poll cards; adds Year and State filter dropdowns; adds Sort by Year |

---

## Key Functions Reference

### `buildUnifiedCandMap(all_polls)`
**Location:** `mock_election/views.py`

Builds a candidate map by collecting every unique candidate name across **all** polls, not just the first one. This is critical — if only the first poll's candidates were used, any candidate introduced in a later poll would be silently ignored in algorithm calculations, receive no color on the map, and cause incorrect vote totals.

**How it works:**
1. Iterates through every poll in `all_polls`
2. For each poll, iterates through its `MockElectionItem` objects
3. Adds any candidate name not yet seen to a `seen` dict (preserving insertion order)
4. Returns `{0: item, 1: item, ...}` — candidates from the first poll come first, then any extras appended in the order they were found

```python
def buildUnifiedCandMap(all_polls):
    seen = {}   # candidate name -> item object
    for poll in all_polls:
        for item in poll.mockelectionitem_set.all():
            if item.item_text not in seen:
                seen[item.item_text] = item
    return {idx: item for idx, item in enumerate(seen.values())}
```

**Why candidate order is stable:** Candidates from the first poll always get the lowest indices (0, 1, 2...). Extra candidates from later polls are appended at the end. This means colors don't reshuffle when a new poll with an extra candidate is added.

---

### `buildUnifiedProfile(all_polls, unified_cand_map)`
**Location:** `mock_election/views.py`

Builds a prefpy `Profile` object by combining voter responses from multiple polls into a single election profile. This is the core aggregation function — it makes it possible to run voting algorithms across polls that may have been created independently with different item IDs.

**The problem it solves:** Each poll has its own `MockElectionItem` objects with their own database IDs. A voter in Poll A who ranked "Alice" (item ID 42) and a voter in Poll B who ranked "Alice" (item ID 107) cannot be directly compared by ID. This function matches candidates by **name** instead of ID.

**How it works (step by step):**

1. For each response in each poll, call `getPrefOrder()` to get the ranked preference list
2. Parse the response into a `name_rank` dict: `{"Alice": 1, "Bob": 2, "Charlie": 3}`
   - Handles both `resp_str` formats (dict format with `"name": "itemAlice"` and raw ID format)
   - Strips the `"item"` prefix from dict-format names
3. Fill in any candidates from `unified_cand_map` that the voter didn't rank — assign them `max_rank + 1` (last place)
4. Build a pairwise preference graph using unified integer indices (not item IDs)
   - `pref_graph[i][j] = 1` means candidate i is preferred over j
   - `pref_graph[i][j] = -1` means j is preferred over i
   - `pref_graph[i][j] = 0` means tied
5. Wrap in a prefpy `Preference` object and collect all into a `Profile`

**Returns:** A prefpy `Profile` object, or `None` if no valid responses exist.

**Important:** Always call `buildUnifiedCandMap(all_polls)` first and pass the result as `unified_cand_map`. Never pass a single poll's candidate map — that would exclude extra candidates from other polls.

---

### `runSingleAlgorithm(profile, cand_map, alg_index)`
**Location:** `mock_election/views.py`

Runs one of the 16 voting algorithms on a prefpy `Profile` and returns the result in a consistent format.

**Parameters:**
- `profile` — a prefpy `Profile` object (from `buildUnifiedProfile`)
- `cand_map` — the unified candidate map `{0: item, 1: item, ...}`
- `alg_index` — integer 0–15 (see Algorithm Classification table above)

**Returns:** `(is_score_based: bool, scores: dict)`
- `scores` keys are **candidate indices** (integers), not names
- For score-based algorithms: values are numeric scores (higher = better)
- For winner-only algorithms: values are `1` (winner) or `0` (not winner)

To convert to candidate names: `{cand_map[k].item_text: v for k, v in scores.items()}`

**Usage pattern:**
```python
is_score_based, raw_scores = runSingleAlgorithm(profile, cand_map, alg_index)
named_scores = {cand_map[k].item_text: v for k, v in raw_scores.items()}
winner = max(named_scores, key=named_scores.get)
```

---

### `getCandidateMapFromList(items)`
**Location:** `mock_election/views.py`

Builds `{0: item, 1: item, ...}` from a list of `MockElectionItem` objects. Used internally by prefpy to identify candidates by integer index.

> **Note:** For aggregation, always use `buildUnifiedCandMap(all_polls)` instead of this function. `getCandidateMapFromList` only works on a single poll's item list and will miss candidates from other polls.

---

### `getPrefOrder(resp_str, question)`
**Location:** `mock_election/views.py`

Parses a voter's `resp_str` string (stored on `MockElectionResponse`) into a ranked preference list. Returns a list of tiers, where each tier is a list of entries the voter ranked equally.

**resp_str comes in two formats:**

**Format 1 — Dict format** (most common, used by the drag-and-drop UI):
```json
[{"name": "itemAlice", "tier": 1}, {"name": "itemBob", "tier": 2}]
```
Strip `"item"` prefix from the `name` field to get the candidate name.

**Format 2 — ID format** (older UI):
```
[[42], [107], [88]]
```
Each inner list contains a `MockElectionItem` ID. Look up the candidate name via `poll.mockelectionitem_set`.

`buildUnifiedProfile` handles both formats using an `isinstance(entry, dict)` check.

---

### `translateWinnerList(winners, cand_map)`
**Location:** `mock_election/views.py`

Converts a list of winning candidate indices (returned by STV, Baldwin, Coombs, Black, Ranked Pairs, Plurality Runoff) into a `{cand_index: 1/0}` dict compatible with `runSingleAlgorithm`'s return format.

```python
# winners = [0, 2]  (indices of winning candidates)
# Returns: {0: 1, 1: 0, 2: 1, 3: 0}
```

---

### `translateBinaryWinnerList(winners, cand_map)`
**Location:** `mock_election/views.py`

Same purpose as `translateWinnerList` but for Borda Mean and Simulated Approval, which return a binary dict `{cand_index: 1/0}` directly rather than a list of indices. Validates that the length matches before converting.

---

### `getListPollAlgorithms()`
**Location:** `mock_election/views.py`

Returns the ordered list of 16 algorithm names as strings. The index in this list corresponds directly to the `alg_index` used in `runSingleAlgorithm` and the AJAX API `?alg=` parameter.

---

### `getListAlgorithmLinks()`
**Location:** `mock_election/views.py`

Returns a list of Wikipedia URLs for each algorithm (in the same order as `getListPollAlgorithms`). Empty string where no link is available. Used to make algorithm names in the Statewide Algorithm Comparison table clickable.

---

## Data Flow — Page Load

```
User clicks "Aggregated Results" on pollinfo page
        ↓
AggregatedResultsView.get()
  — checks user owns at least one poll in state + year
  — raises 404 if not
        ↓
AggregatedResultsView.get_context_data()
        ↓
buildUnifiedCandMap(all_polls)
  — collects all unique candidates across ALL polls
  — returns stable {0: item, 1: item, ...} map
        ↓
Per-district first-choice vote counts
  — iterates all polls, groups by district
  — counts first-choice votes per candidate per district
  — used for initial map coloring (Plurality default)
        ↓
buildUnifiedProfile(all_polls, cand_map)
  — combines all responses into one prefpy Profile
  — matches candidates by name across polls
        ↓
Runs all 16 algorithms on unified profile
  — produces statewide_vote_results for the comparison table
        ↓
Passes JSON data to template:
  district_winners, district_vote_counts, candidate_colors,
  candidates_json, statewide_first_choice_json, statewide_vote_results
        ↓
aggregated_results.html renders map + pie chart + table on page load
```

---

## Data Flow — Algorithm Change (AJAX)

```
User selects algorithm from dropdown
        ↓
JS fires fetch() to:
  /mock_election/aggregated/<state>/<year>/district_winners/?alg=<index>
        ↓
DistrictWinnersAPIView.get(request, state, year)
        ↓
buildUnifiedCandMap(polls) — same unified map as page load
        ↓
Groups polls by district
  — a district may have multiple polls; all are combined
        ↓
For each district:
  buildUnifiedProfile([district_polls], cand_map)
  runSingleAlgorithm(dist_profile, cand_map, alg_index)
  → district_winners[district] = max scoring/winning candidate
        ↓
buildUnifiedProfile(all_polls, cand_map) — statewide
runSingleAlgorithm(unified_profile, cand_map, alg_index)
  → statewide_scores, is_score_based
        ↓
Returns JSON:
  { district_winners, district_scores, district_vote_counts,
    statewide_scores, is_score_based, candidate_names }
        ↓
JS recolors map polygons, updates tooltips, updates sidebar labels
        ↓
If score-based → updates pie chart + candidate breakdown
If winner-only → hides pie chart, renders Winner Podium card
        ↓
Updates District Winners table title and rows
```

---

## Candidate Colors

Candidates are assigned colors deterministically based on their position in the unified candidate map:

```python
COLORS = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
          '#1abc9c', '#e67e22', '#34495e', '#e91e63', '#00bcd4']
candidate_colors = {name: COLORS[i % len(COLORS)] for i, name in enumerate(candidate_names)}
```

Because `buildUnifiedCandMap` preserves insertion order (first poll's candidates first), colors are stable — adding a new poll with an extra candidate won't change the colors of existing candidates.

The same colors are used across: map polygons, pie chart, tooltips, podium card, sidebar labels, and the district winners table.

---

## Error Handling and Fallbacks

- If the algorithm throws an exception for a district (e.g., not enough candidates or malformed responses), that district falls back to first-choice plurality for coloring.
- If no valid prefpy Profile can be built for the statewide data (e.g., no votes at all), the page shows a "No results yet" empty state card.
- If a poll has no `year` set (polls created before the year field was added), the "Aggregated Results" button is hidden on the `pollinfo` page.
- If the AJAX request fails, the map stays in its last known state (no crash).

---

## Polls List — Year and State Filters

The polls list page (`regular_polls.html`) has Year and State filter dropdowns in the toolbar. These are purely client-side (JS) — they use `data-year` and `data-state` attributes on each poll card and show/hide cards without a server round-trip.

- **Year filter:** Shows only polls matching the selected year. Dropdown is hidden if no polls have a year set.
- **State filter:** Shows only polls matching the selected state. Dropdown is hidden if no polls have a state set.
- Both filters work together with the search box, status pills, and sort dropdown simultaneously.
- The unique years and states in the dropdowns are computed server-side in `RegularPollsView.get_context_data()` from the user's created and participated polls, and passed to the template as `filter_years` and `filter_states`.

---

## Static Files Used

- `static/js/leaflet.js` + `static/css/leaflet.css` — Leaflet map rendering (local, no CDN)
- `static/js/chart.umd.min.js` — Chart.js for pie chart
- `static/js/districts/<StateName>.json` — GeoJSON boundary files for all 50 states. File name uses underscores for spaces, e.g., `New_Jersey.json`.
- `static/js/congressional_districts_by_state.json` — Maps each state name to its list of district names; used to populate the State and District dropdowns on poll creation.

After any change to static files, run `collectstatic` on the server:
```bash
docker compose exec web python3 manage.py collectstatic --noinput
```

---

## Updating District Boundaries

Congressional district boundaries change after each decennial census redistricting cycle (most recently in 2022 for the 118th Congress, and in 2025 for the 119th Congress). We should run the update script to pull the latest boundary files from the US Census Bureau.

### Script location

```
compsocsite/scripts/update_district_boundaries.py
```

### How to run

Run from the `compsocsite/` directory:

```bash
# Auto-detect the latest available Census release (recommended)
python3 scripts/update_district_boundaries.py

# Specify a Congress and Census release year explicitly
python3 scripts/update_district_boundaries.py --congress 119 --year 2024

# Preview what would change without writing any files
python3 scripts/update_district_boundaries.py --dry-run
```

### What the script does

1. Downloads the national congressional district boundary file from the [US Census Bureau Cartographic Boundary Files](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html).
2. Splits the features by state into 50 individual GeoJSON files.
3. Normalizes the district field name (e.g. `CD119FP` → `CD116FP`) so the map JavaScript works without any code changes.
4. Overwrites the existing files in `static/js/districts/`.

No dependencies beyond the Python standard library are required (`urllib`, `json`, `os`).

### After running the script

**Development:** The map will use the new boundaries immediately on the next page load — no restart needed.

**Production (Docker):** Run collectstatic to push the updated files to WhiteNoise:

```bash
docker compose exec web python3 manage.py collectstatic --noinput
```

### When to run it

Run this script when:
- A redistricting cycle has taken effect (e.g., after the 2030 census).
- The Census Bureau publishes updated boundaries for the current Congress.
- Districts visible on the map look wrong or are missing.

### Command-line options

| Flag | Description |
|---|---|
| `--congress N` | Congressional session number (e.g. `119`). Auto-detected if omitted. |
| `--year YYYY` | Census release year (e.g. `2024`). Auto-detected if omitted. |
| `--output-dir PATH` | Override the output directory. Defaults to `static/js/districts/`. |
| `--dry-run` | Print what would be updated without writing any files. |

### Troubleshooting

- **"Could not auto-detect a Census release"** — The Census Bureau may not have published the latest Congress yet, or your internet connection is blocked. Run with explicit `--congress` and `--year` flags.
- **Missing states** — The Census file may not include territories (Puerto Rico, Guam, etc.) — this is expected. All 50 states should always be present.
- **Map still shows old boundaries after update** — Make sure you ran `collectstatic` in production. In development, try a hard refresh (`Cmd+Shift+R` / `Ctrl+Shift+R`) to bypass the browser cache.

---

## Testing the Feature

1. Create at least 2 mock election polls with the same state and year but different districts
2. Optionally add a candidate to one poll that is not in the other (to test `buildUnifiedCandMap`)
3. Add voters and cast votes in both polls
4. Go to Poll Settings → click "Aggregated Results"
5. Verify the map colors each district by plurality winner (default)
6. Change the algorithm dropdown → verify map recolors, right panel updates, district table title changes
7. Select a winner-only algorithm (e.g., STV) → verify Podium card appears instead of pie chart
8. If you added an extra candidate in step 2, verify they appear in the pie chart, table, and on the map

**Inspecting the AJAX response:** Open browser DevTools → Network tab → change the algorithm dropdown → look for the `district_winners/?alg=X` request and inspect its JSON payload.

**Filter test:** On the polls list page, verify the Year and State dropdowns appear and correctly hide polls that don't match.

---

## Known Limitations

- All polls in the same state and year are assumed to have candidates with the same names. Spelling differences (e.g., "Alice Smith" vs "Alice") will cause them to be treated as separate candidates.
- Polls in **any status** (draft, active, ended, paused) are included in aggregation. There is no way to filter by status on the aggregated results page yet.
- Only responses marked as `active=1` are counted.

---

## Future Enhancements

- **Filter by poll status:** Option to include only ended polls in aggregation.
- **Export:** Download aggregated results as CSV.
- **WebSocket live updates:** Real-time map updates as votes are cast.
- **District-level voter input:** Allow voters to select their own district when voting, enabling a single statewide poll instead of one poll per district.
- **Year filter on polls list:** Currently implemented as a client-side dropdown. A future version could make this a server-side filter for better performance with large numbers of polls.
- **Candidate name normalization:** Fuzzy matching or a canonical name list to handle spelling differences across polls.
