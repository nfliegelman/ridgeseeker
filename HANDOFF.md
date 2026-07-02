# RidgeSeeker (formerly EdgeFinder): AI Handoff / Technical Spec

**Purpose of this file:** you are an AI assistant helping the owner (a hobbyist sports bettor, not a professional developer) modify this program. This document tells you what the program is, how it is built, and which decisions are deliberate so you do not undo them while helping. Read it fully before proposing changes.

**Doc version:** 2026-07-02 (v9). Update the changelog at the bottom whenever you change the code.

---

## 0. THE ONE RULE THAT PREVENTS CONFUSION

Every time you change the code, hand the owner back BOTH the updated `ridgeseeker.py` AND an updated `HANDOFF.md` with a new changelog entry, and tell them to commit both together. This file is only accurate if it is kept in sync. The single most common failure is code changing while this doc goes stale, which leaves the next AI confused. Do not let that happen.

---

## 0b. File handback protocol (the owner uploads via the GitHub web UI)

The owner updates the repo by unzipping what you send and using GitHub's Add file -> Upload files at the repo ROOT. That upload overwrites same-named root files but CANNOT place files into `.github/workflows/`. Therefore: hand back only root-level files (`ridgeseeker.py`, `HANDOFF.md`, `FUTURE.md`, `README.md`). If the workflow must change, give the owner the full file contents to paste via the web editor at `.github/workflows/edgefinder.yml`, and say so explicitly. Never hand back `ridgeseeker_betlog.json` or `ridgeseeker_snapshots.json`: the bot owns those.

---

## 1. Prime directives (read first)

1. **Do not rebuild from scratch.** This code is the product of many careful iterations against live data. Prefer surgical edits. If you believe a rewrite is warranted, say so explicitly and explain the tradeoff before doing it.
2. **Honesty over polish is the core philosophy.** The point of this tool is to surface real edges and output "no edge / pass" when there is not one. Never add logic that manufactures signals, inflates grades, or fabricates data to look busier. "No plays today" is a correct, valuable output.
3. **Never use em dashes** anywhere: not in code, comments, UI text, or your chat replies to the owner. The owner forwards output to other people and em dashes read as AI-authored. Use commas, colons, or parentheses. There are currently zero em dashes in the file; keep it that way. Empty table cells use a plain hyphen "-".
4. **Real data only.** Every number shown must trace to an actual API response. If a source is unavailable, show "no data" honestly rather than estimating and presenting it as fact.
5. **Serve the underlying goal, not just the literal request.** If a smarter framing or a split solution better serves what the owner actually cares about, propose it. Ask clarifying questions when they improve the result. The owner explicitly values this.

---

## 2. What the program does

RidgeSeeker is a single Python script (`ridgeseeker.py`, ~1250 lines) that:
1. Fetches MLB odds (The Odds API) and sharp-money splits + live status + final scores (Action Network, free/no-auth).
2. Computes a "fair" probability anchored to DEVIGGED PINNACLE (fetched via the eu region of The Odds API; every play carries `anchor`: 'pinnacle' or 'consensus'). When Pinnacle skips a market or line, it falls back to the no-vig median of ~25 books. Compares fair to Bovada and flags **value** (EV >= 3%).
3. Grades **sharp money** S/A/B/C/D from the money%-minus-tickets% gap, with contrarian and steam confirmation.
4. Suggests a **unit size** (1u / 1.5u / 2u) per play, with a hard longshot cap.
5. Tracks results automatically: logs plays (stamped with `MODEL_VERSION`, stated `ev`, `fair`, `anchor`), refreshes each pending play's `close_price` every run while pregame, grades against final scores, computes units/ROI AND closing line value (CLV), reports level-up progress.
6. Snapshots every graded game each run for edge-over-time analysis.
7. Renders one mobile-first HTML dashboard with a **Board / Results pill toggle** (both views live in the same file, no page reload), plus CSV exports.

Runs on **GitHub Actions** (cloud) 3x/day and publishes to **GitHub Pages**. Also runs locally on Windows (opens a browser). One file, auto-detecting via the `CI` flag.

---

## 3. File structure (single file: edgefinder.py)

Top to bottom:

| Section | What it does |
|---|---|
| CONFIG | `ODDS_KEY` (env or fallback), `SPORTS` (MLB only), `GRADE_THRESHOLDS`, sanity gate, `UNIT_DOLLARS` |
| SSL fetch (`_ssl_tiers`, `gj`) | Layered SSL fallback. Do not simplify (see section 6). |
| Odds math | `am2prob`, `am2dec`, `prob2am`, `novig`, `novig3`, `gate` |
| Data fetch | `fetch_odds`, `fetch_sharp_and_status` (returns `(sharp, status, raw)`; `raw` reused for final scores), `soft_fair_map` |
| Engine (`analyze_game`) | Builds ML/spread/total plays, no-vig fair, EV, value gate, consensus-favorite guard |
| Grading (`grade_sharp`) | Sport-aware S/A/B/C/D (see section 4) |
| Sizing (`suggest_units`) | 1u/1.5u/2u with longshot cap (see section 5) |
| Recommendation (`build_recommendation`) | Picks which market to name; hybrid value-vs-sharp |
| Tracker | `load_log`, `log_plays`, `grade_pending`, `_grade_one`, `tracker_summary`, `collect_results` |
| Snapshots | `hours_until`, `log_snapshots` |
| Stats | `compute_stats` (aggregations by grade/units/market/signal/price/time-to-game) |
| Templates | `TEMPLATE_HEAD` (HTML shell + all CSS), `TEMPLATE_APP` (all JS, including the Board/Results toggle and `renderResults`) |
| `main()` | Orchestrates, writes outputs |

The frontend is two raw-string templates. Python injects `const ALL = {...}` (card data + `_top`, `_tracker`, `_stats`, `_unit_dollars`) between them. The JS reads `ALL` and builds the DOM. **There is exactly ONE stats system: the Results tab, rendered client-side by `renderResults()` from `ALL['_stats']`.** (An older standalone `build_stats_page` function was removed in v8; if you see references to `stats.html` anywhere, they are stale.)

---

## 4. Grading (DELIBERATE, do not loosen)

Sharp grade is driven by **gap = money% minus tickets%** on the sharp side. Thresholds are **percentile-anchored to the real MLB gap distribution** (median ~9, 75th ~15, 90th ~22), in `GRADE_THRESHOLDS`:

```
baseball: S:25, A:20, B:13, C:9, D:6
```

`grade_sharp` logic:
- **S** = gap >= 25 AND contrarian AND steam (all three).
- **A** = (gap >= 20 AND contrarian) OR gap >= 25.
- **B** = gap >= 13. **C** = gap >= 9. **D** = gap >= 6. Below 6 = None.
- **contrarian** = sharp side has <= 35% of tickets.
- **steam** = sharp side's Action-Network price implies prob > soft-book fair by > 1.5 pts. This is a snapshot proxy, NOT true reverse-line-movement (no opening-line history available). Label it "steam", never "RLM".
- **Non-contrarian penalty:** if not contrarian and tickets >= 55, force D.
- **Thin cap:** if num_bets < 1500, cap at B.

**Why:** an earlier version graded on raw gap and produced far too many A/S (a +15 gap graded A, a 75th-percentile event, way too common). The owner wants B to be the average and A/S rare "chase it" bets. If you are making A/S more common, you are going the wrong way. Other sports get their own thresholds once calibrated; they currently fall back to `_default` (= baseball).

---

## 5. Unit sizing (DELIBERATE, the longshot cap is the guardrail)

`suggest_units` returns (units, reason). The owner bets underdogs; the principle is **a long price is already its own reward, so do not double down on variance.**

- **2u** (rare): has_value AND EV >= 8% AND sharp A/S agrees with the value side AND price <= +200.
- **1.5u**: (has_value AND 4% <= EV < 8%, not longshot) OR (pure S with contrarian+steam, no value).
- **1u**: any single real signal, OR anything at +250 or longer regardless of grade.
- **skip** (None): C/D with no value.

**The +250 longshot cap is non-negotiable** unless the owner explicitly changes it.

Level-up gates (`LEVELS`): $10->$20 needs ~50 settled bets AND >= +5u AND ~$800 bankroll; $20->$50 needs ~175 bets AND >= +12u AND ~$2000. A "profit concentrated in one lucky hit" flag blocks leveling up on a fluke. These sample sizes are deliberate; do not shrink them.

---

## 6. SSL fetch (DELIBERATE, do not clean up)

`_ssl_tiers` + `gj` try, in order: normal verified context, certifi + widened ciphers (SECLEVEL=1), system store + widened ciphers, last-resort no-verify. It caches whichever works. Every tier fixed a real failure (corporate TLS inspection, cert-store issues, handshake failures). On GitHub runners tier 0 works instantly; the rest are for local/managed machines. **Do not reduce this to a plain `urlopen`.** The owner's work laptop firewall blocks the odds APIs entirely, which is WHY this runs on GitHub (fetch happens on GitHub's network). Keep it cloud-runnable.

---

## 7. Data sources and quirks

- **The Odds API** (`fetch_odds`): key via `ODDS_KEY` env (GitHub secret), hardcoded fallback for local. **Cost = markets x regions per call.** Currently `regions=us` (1) x `h2h,spreads,totals` (3) = **3 credits/run**. Free tier ~500/month. 3x/day = ~270/month. Adding a sport, region, or run frequency can blow the budget. Do the math before changing cadence.
- **Action Network** (`fetch_sharp_and_status`): free, no auth, needs a browser User-Agent. Provides ticket%/money% splits, live status with real inning, and final scores (`boxscore.stats.{away,home}.runs`). US team sports only. Source for grades, live badges, AND result grading. If down, value scanning still works but grades/results do not.
- **Pinnacle: the fair-value anchor (v9).** The old claim that Pinnacle is paywalled on free feeds was WRONG: The Odds API serves Pinnacle in the `eu` region on the free tier. `fetch_odds` now requests `regions=us,eu`, which DOUBLES the credit cost: 3 markets x 2 regions = **6 credits/run**. At 2 scheduled runs/day that is ~360/month of the ~500 free, leaving manual-run headroom. Do not add sports, regions, or scheduled runs without redoing this math.
- **CLV (closing line value), v9:** `update_closes` refreshes `close_price` on pending pregame plays each run; `grade_pending` computes `clv` = decimal(entry)/decimal(close) - 1 at settlement. The close is the LAST PREGAME PRICE THIS TOOL SAW, an approximation given 2 runs/day; the UI says so honestly. CLV is the primary validation metric: consistently positive CLV over 50+ bets is evidence of real edge long before W/L stabilizes. Do not remove it, and do not present the approximate close as a true close.
- **Doubleheaders:** `collect_results` marks a matchup AMBIG when one payload contains two different finals for the same teams, and grading skips it. An honest skip beats a coin-flip grade.

---

## 8. Outputs and persistence

Each run writes:
- `docs/index.html` (CI) or `ridgeseeker_latest.html` (local): the dashboard (contains both Board and Results tabs).
- `docs/bets.csv`, `docs/snapshots.csv`: raw data for manual sorting.
- `ridgeseeker_betlog.json`: recommended plays + graded results (auto-migrated from `edgefinder_betlog.json` on first run; never delete either without a backup).
- `ridgeseeker_snapshots.json`: per-run per-game readings for edge-over-time (auto-migrated). NOTE: the old workflow never committed the snapshots file, so CI snapshots were silently lost; the v9 workflow commits it.
- `ridgeseeker_history/`: timestamped HTML archives.

On GitHub the workflow commits these back so state persists across ephemeral runs and time off. Do not move persistence to anything needing a database or paid service; the commit-back pattern is deliberate and free.

---

## 9. Frontend conventions

- Mobile-first (~410px), dark theme, CSS variables at the top of `TEMPLATE_HEAD`.
- **Board / Results** views toggled by pills via `showView('board'|'results')`, matching the owner's weather tracker for consistency. Results builds lazily on first open from `ALL['_stats']` via `renderResults()`.
- Grade colors: S gold `#f5c451`, A green `#34d399`, B blue `#60a5fa`, C/D grey. Keep consistent.
- No em dashes in any string. Empty cells use "-".
- The parlay feature was removed on purpose. Multi-sport tab scaffolding (NFL/NBA/NHL "out of season") is intentional forward-support; leave it.

---

## 10. Validate before handing back

1. `python -c "import py_compile; py_compile.compile('ridgeseeker.py', doraise=True)"` passes.
2. `EDGEFINDER_CI=1 python ridgeseeker.py` runs and writes `docs/index.html` with no error.
3. The generated HTML's JS runs with no reference errors, and BOTH Board and Results views render (you can eval the two script blocks with a stubbed DOM and call `showView('results')`).
4. Zero em dashes introduced.
5. You did not loosen grades, remove the longshot cap, simplify the SSL tiers, or break commit-back persistence.
6. You updated this file's changelog and told the owner to commit both files.

---

## Changelog

- **v9 (2026-07-02), renamed RidgeSeeker:** (1) Fair value is now anchored to devigged Pinnacle, fetched via `regions=us,eu` (the old "Pinnacle is paywalled" premise was wrong); consensus median remains the fallback and every play records its `anchor`. (2) Added closing line value: pending plays get `close_price` refreshed while pregame and `clv` computed at grading; Results tab shows avg CLV and beat-the-close rate, plus a new "By stated EV" table. (3) Logged plays now carry `model_version`, `ev`, `fair`, `anchor`. (4) Doubleheader finals are detected as ambiguous and skipped rather than coin-flip graded. (5) Dashboard text no longer claims Kalshi/Polymarket sources that were never implemented (honesty fix). (6) File renames with auto-migration: `ridgeseeker.py`, `ridgeseeker_betlog.json`, `ridgeseeker_snapshots.json`, `ridgeseeker_history/`; old EdgeFinder files are adopted on first run, history preserved. (7) Workflow (paste-in): name RidgeSeeker, 2 scheduled runs/day (15:00 and 21:30 UTC), concurrency guard, pull-rebase before push, snapshots file now committed. Credit math: 6/run x 2/day = ~360 of ~500 free monthly.

- **v8 (2026-07-01):** Removed the dead standalone `build_stats_page` function and all `stats.html` writes. There is now exactly one stats system: the integrated Results tab inside `index.html`. Replaced the remaining em-dash placeholders in table cells with plain hyphens (file now has zero em dashes). No behavior change to grades, sizing, fetching, or tracking.
- **v7 (2026-07-01):** MLB-only focus; grades recalibrated to the MLB percentile distribution (B is the average, A/S rare); unit sizing with +250 longshot cap; automatic results tracker with level-up gates; per-run snapshot logging for edge-over-time; Results view folded into the main dashboard via a Board/Results pill toggle; CSV exports; parlay removed; 3x/day GitHub Actions schedule.
- (Earlier history predates this file; reconstruct from git log if needed.)

---

*When you finish a change: bump the doc version, add a changelog entry saying what changed and why, update any section above that no longer matches the code, and remind the owner to commit ridgeseeker.py, HANDOFF.md, and FUTURE.md together.*
