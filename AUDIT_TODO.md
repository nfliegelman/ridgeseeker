# RidgeSeeker Model Audit: TODO Tracker

**Purpose:** short-term tracker for the full model audit (source: AUDIT_ORIGINAL.md in the repo root, AMENDED 2026-07-03: the old "do not add features" instruction is removed; features for accuracy and profitability are IN SCOPE). The original's per-item detail is embedded below, so it does not need uploading to chats. This file is the cross-chat memory for the audit. It is separate from HANDOFF.md, which remains the permanent technical spec. Update BOTH whenever code changes.

**How to use this file (instructions for the next AI chat):**
1. Read HANDOFF.md first (prime directives, no em dashes anywhere, surgical edits only, hand back root files only, never hand back the betlog/snapshots files).
2. Then read this file top to bottom. Work the next PENDING batch: ONE item per chat (two only where the batch plan explicitly pairs them). The owner kept running out of tokens at 3 items per chat. Finish the batch cleanly, hand files back, and STOP; only continue into the next batch if the owner explicitly asks in the same chat. Option B still applies: make fixes immediately, not just findings.
3. Findings go in the Findings Ledger below with an ID, so the final deliverables (ranked top-50 list, roadmap, tech debt assessment) can be assembled from the ledger at the end.
4. Sample-gated items must NOT be analyzed early with tiny N. Their job now is only to make sure the right data is being logged so the analysis is possible later.
5. Before starting item 18 (community ideas), tell the owner to turn ON advanced research mode for that chat. It is a pure web-research item and the one place deep research is the right tool.
6. Owner context: paper trading for now, several weeks of data gathering before real money. Optimize for long-term model quality, not quick wins on 4 bets.
7. Token discipline: each batch lists which files the owner should upload. Do not ask for ridgeseeker.py (100 KB, the biggest token cost) for analysis-only batches that do not need it.
8. OWNER DIRECTIVE (2026-07-03): features ARE in scope. Every batch should actively scout accuracy/profitability features and add candidates to the FUTURE.md roadmap with impact/difficulty/confidence/dependencies/validation. Tier-NOW roadmap items get implemented in code batches; decision-affecting features stay log-first and flip on only at their pre-registered N-gates with a MODEL_VERSION bump. Do NOT re-derive a "no features" stance from any older phrasing.

---

## Audit order (reorganized) and status

Original item numbers from RIDGESEEKER_AUDIT.md in parentheses.

### Phase A: Make what is running now trustworthy
| # | Item | Status |
|---|---|---|
| 0 | Repo and CI cleanup (new) | DONE batch 1 |
| 1 | Data quality, leakage, timestamps (orig 1) | DONE batch 1 |
| 2 | EV calculations and vig removal (orig 6) | DONE batch 1 |
| 3 | CLV methodology as primary metric (orig 5) | DONE batch 2 |
| 4 | Logging schema: capture-now-or-lose-forever fields (part of orig 16) | DONE batch 2 |
| 5 | Risk management: unit ladder vs Kelly, bet correlation, exposure (orig 11) | DONE batch 2 |

### Phase B: Strategy logic (auditable without sample size)
| # | Item | Status |
|---|---|---|
| 6 | Data sources worth adding within API budget (spun out of orig 1) | DONE batch 3 (analysis; F26/F27 implementation queued to batch 4 behind owner verification) |
| 7 | Feature engineering brainstorm + which to start logging now (orig 2) | DONE batch 4 |
| 8 | Market efficiency: where the edge plausibly lives (orig 3) | DONE batch 5 |
| 9 | Challenge every assumption (orig 17): running checklist, revisit each batch | OPEN (standing) |

### Phase C: Sample-gated analytics (logic can be built now, conclusions blocked until N)
| # | Item | Status | Gate |
|---|---|---|---|
| 10 | Probability calibration (orig 4: Brier, ECE, reliability) | BLOCKED | ~150 graded plays |
| 11 | Statistical testing (orig 7: bootstrap, MC, significance) | BLOCKED | ~100 graded plays |
| 12 | Backtesting audit (orig 8): forward-test hygiene review | DONE batch 6 |
| 13 | Monitoring dashboards (orig 13) | DONE batch 7 |

### Phase D: Expansion and synthesis
| # | Item | Status | Gate |
|---|---|---|---|
| 14 | ML models (orig 9) | BLOCKED | ~500+ graded plays or external historical data |
| 15 | Ensembles (orig 10) | BLOCKED | needs a second model to exist |
| 16 | Market microstructure (orig 12) | DONE batch 5 |
| 17 | Continuous learning / retraining (orig 14) | DONE batch 6 |
| 18 | Community ideas sweep (orig 15) | DONE batch 9 (regular search; zero Reddit threads reachable, disclosed in AUDIT_DELIVERABLES.md; optional research-mode pass 9b remains) |
| 19 | Final deliverables | DONE batch 10: AUDIT_DELIVERABLES.md (new root file, in every zip) |
| 20 | Architecture review (remainder of orig 16) | DONE batch 8 |

**Reordering rationale:** Phase A first because every play logged between now and real money is the evidence base; a leaky logger poisons everything downstream. Sample-gated items were originally scattered through the list; running calibration curves on 4 bets would be numerology, so they are explicitly gated. Item 17 (assumptions) is standing, not a one-shot. Community research goes near the end so it supplements a finished internal report, per the owner's stated plan to cross-pollinate it with forum knowledge.

---

## Findings Ledger

Severity: CRIT (was actively corrupting results), HIGH (would corrupt results soon), MED (bias or debt), LOW (hygiene).

### Batch 1 (2026-07-02, this chat): Items 0, 1, 2

| ID | Sev | Finding | Status |
|---|---|---|---|
| F1 | CRIT | Workflow `edgefinder.yml` runs `python edgefinder.py`, a file that no longer exists. Every scheduled CI run since the v9 rename has failed. Also ran 3x/day (old cadence), committed old filenames, never committed snapshots. | FIXED: new `ridgeseeker.yml` provided (paste via web editor, delete old file) |
| F2 | CRIT | Night-game grading hole. Action Network scoreboard rolls over each morning, so any game finishing after the day's last run never gets graded and stays pending forever. Confirmed live: the 6/30 Angels ML play sat pending for 2 days. Biases the tracked record toward day games. | FIXED: `fetch_scores_for_dates` backfills 3 days via the AN `?date=YYYYMMDD` param (verified working, free). Angels play graded loss, record now honest 2-2, -0.24u |
| F3 | CRIT | Hardcoded Odds API key in a public repo (Pages free tier means public). Key is in git history and in every zip shared with AI assistants. | FIXED in code (env var or gitignored odds_key.txt). OWNER ACTION REQUIRED: rotate the key at the-odds-api.com and update the ODDS_KEY GitHub secret. Until rotated, anyone can burn the 500 monthly credits |
| F4 | HIGH | Proportional (multiplicative) devig systematically overstates fair probability of the longer-priced side (favorite-longshot bias). Measured: +0.5 pts at +160, +1.2 pts at +250, which inflates stated EV by ~1.3 to ~4.3 points on exactly the underdog bets this tool prefers. A "+3% EV" longshot could be 0% or negative. | FIXED: power-method devig (`fair_pair`) now drives decisions everywhere (Pinnacle anchor and consensus fallback). Proportional value still logged as `fair_mult` on every play so the two methods can be compared on real results at ~100+ bets |
| F5 | HIGH | Pushes were never graded (returned None), so a pushed run line or integer total would sit pending forever. | FIXED: result can now be 'push', units_pl 0, CLV still computed. Record/ROI exclude pushes (standard convention); tracker and stats surface a pushes count |
| F6 | HIGH | CLV close-price contamination: pregame check trusted only the Action Network status feed. If AN is down, live games default to 'scheduled' and live in-play prices would overwrite `close_price`, corrupting the primary validation metric. | FIXED: `update_closes` now also requires commence_time to be in the future by clock, and matches cards by event id |
| F7 | HIGH | Duplicate-logging risk: dedupe key used the RUN date, so a game scheduled for tomorrow would be re-logged tomorrow under a new date (double-counted bet). Doubleheaders could also collide on matchup-name keys in closes/results. | FIXED: plays now carry Odds API `event_id` + `commence`; dedupe keys on event_id, close matching keys on event_id, result matching uses game start time (nearest within 6h), with a date fallback for legacy plays |
| F8 | MED | The old AMBIG doubleheader flag only worked within a single payload, and with backfill it would have wrongly flagged the same matchup on consecutive days as ambiguous, skipping both. | FIXED: results are now a list of finals per matchup, each with start_time; `_pick_result` matches the correct game or honestly skips |
| F9 | MED | Integer-total EV overstated: EV formula ignores push probability. True EV = (1-P(push)) x stated EV, roughly a 5-8% haircut on the EV magnitude at integer lines. Sign never flips, so gates still work. | OPEN: acceptable for now; revisit if integer-line totals become a meaningful share of plays (check at ~100 bets) |
| F10 | MED | Team-name join risk across the two APIs (Odds API names vs AN full_name). A mismatch (e.g. an "Athletics" style rename) silently kills sharp data AND grading for that team. No mismatch observed in the live 19-game test, but there is no alarm if it starts. | OPEN: add an unmatched-matchup counter + printout per run (small, do in batch 2 alongside monitoring-lite) |
| F11 | MED | The "close" is the last price seen up to ~3h before first pitch for night games (21:30 UTC run vs ~00:00 UTC starts). CLV vs a stale close is noisy and slightly biased. | OPEN: batch 2 (CLV methodology). Options: third late run in the evening (credit math!), or accept and label, or capture close from the AN odds already in the sharp payload at grading time |
| F12 | LOW | Stale references: docstring said edgefinder_history; HANDOFF section header said edgefinder.py. | FIXED in code; HANDOFF updated to v10 |
| F13 | LOW | `log_snapshots` rewrites the whole growing JSON every run. Fine for months at MLB scale; revisit under item 20 (architecture) before adding sports. | OPEN |
| F14 | LOW | `soft_fair_map` (steam detection input) still uses proportional devig, deliberately, because the 1.5pt steam threshold was tuned around it. Reconcile when grades are recalibrated with real data. | OPEN |


### Batch 2 (2026-07-03, this chat): Items 3, 4, 5

| ID | Sev | Finding | Status |
|---|---|---|---|
| F15 | HIGH | CLV coverage hole. A play only received a close if a LATER run happened while its game was still pregame (update_closes runs before log_plays). Day games logged at 15:00 (start before 21:30) never got one; EVERY play logged at the 21:30 run never got one (next run is next morning). Only morning-logged night games earned CLV, so the primary validation metric silently covered a biased minority of plays, and the 21:30 run is exactly where matured sharp money logs. | FIXED: closes seeded with entry values at log time (close_price, close_fair, close_anchor, close_ts, close_obs=0). update_closes bumps close_obs per pregame observation. Stats count only measured closes (close_obs>0, legacy plays with a clv grandfathered as measured) and report coverage%, instead of averaging seeded zeros in and hiding the problem |
| F16 | - | Decision, item 3 core question: CLV vs Pinnacle close is measured the correct way, in devigged probability space, via new clv_fair = (close_fair x dec(entry) - 1): the stated-EV formula re-run at the closing fair prob (Pinnacle-anchored when available, close_anchor records which). This is "EV at close", the market's final verdict, and the new headline metric. Price CLV stays same-book (Bovada entry vs Bovada close); never compare vigged prices across books. | SHIPPED |
| F17 | MED | F11 follow-through (stale close). Close-capture run mode: RS_MODE=close fetches h2h only (2 credits), refreshes closes + grades, never logs plays or rebuilds the dashboard. Workflow cron at 22:45 UTC. Note: FUTURE.md's earlier 23:30 UTC suggestion was wrong: 7:05pm ET starts are 23:05 UTC, so 23:30 would miss the entire East slate; 22:45 catches everything from 23:00 on. Day games and 22:40 UTC (6:40 ET) starts still close at an earlier observation or entry seed; coverage% makes the gap visible. Credit math: 6+6+2 = 14/day, ~420 of ~500/month, ~13 manual full runs of headroom. SPR/TOT closes freeze during close runs (h2h only), deliberate. | FIXED in code; workflow paste required (owner action) |
| F18 | MED | Rec-flip double exposure: build_recommendation names ONE market per game, but the rec can flip (ML at 15:00, total at 21:30) as prices move; the two would log under different dedupe keys: correlated double exposure on one game and a double-counted result. | FIXED: log_plays skips any play whose event_id already has a pending play (first logged wins) |
| F19 | MED | Sharp-only plays logged fair=None even though the entry fair was computed (capture-or-lose), and the sharp inputs were collapsed to gap + booleans (tickets/money/num_bets/steam margin lost). | FIXED: rec now carries fair/fair_mult/anchor/nb from its source play; grade_sharp returns steam_delta (raw pts, decision still uses the unrounded value) and num_bets; all logged |
| F20 | MED | Logging schema gaps (item 4 sweep): no run timestamp (only date), no raw Pinnacle prices (any future devig method could never be re-run on history), no book count, no close point/timestamp, line moves invisible. Bovada limits are NOT available via the API (accepted, unknowable). Sharp splits at close are reconstructable from snapshots, same staleness caveat as the close itself. | FIXED: plays now log run_ts, pin_price/pin_opp, nb, close_point/close_ts/close_obs, close_line_moved (Bovada moved off the entry line: same-line close freezes, movement recorded), units_reason, rec_type. bets.csv and snapshots.csv export the full set |
| F21 | - | Item 5 verdicts. (a) Ladder vs Kelly: at typical stated edges (4% EV at ~+170) full Kelly is ~2.4% of bankroll; 1u=$10 at the $800 level-up floor is ~1.25%, roughly half Kelly IF stated edges are real. Since they are unproven, fixed units are correct; keep the ladder, Kelly stays gated (FUTURE.md). Below ~$400 bankroll 1.5u plays exceed half Kelly; the min_bankroll gates are what keep the ladder sane, do not remove them. (b) Correlation: one play per game enforced (F18); different MLB games are independent; the real risk is same-slate VOLUME, so MAX_DAILY_UNITS=6u guidance added, surfaced in tracker bar + console, plays still logged (paper trade wants all data). (c) Drawdown expectations (20k-trial MC at the tool's price/stake profile, 100 bets): real +3.5% edge: median max drawdown ~15u, median worst streak 8 (95th pct 13), finishes NEGATIVE ~40% of the time; no edge: median DD ~16.5u, final P/L 5th-95th pct -26u to +26u. Conclusion: W/L over 100 bets cannot distinguish edge from no edge; clv_fair and CLV are the only meaningful gauges at this scale. A variance card now states this on the Results tab so a normal losing streak is not misread as model failure. | SHIPPED (guidance + card + docs) |
| F10 | MED | (carried from batch 1) Team-name join risk across APIs. | FIXED: per-run name-join alarm prints any AN scheduled game with splits that matched no Odds API game (suppressed when the odds feed returned nothing, which prints its own error). Verified live: fired correctly on a real 13-game AN slate with the odds feed empty, including the "Athletics" no-city name this alarm exists for |
| F11 | HIGH->closed | Stale close (batch 1). | RESOLVED by F15 + F16 + F17 combined |


### Batch 2 addendum (2026-07-03, coverage check vs the original audit): items 0-5 re-verified

Line-by-line recheck of DONE items against the original file's sub-checklists after restoring the detail. Three real gaps found; two closed immediately, one queued.

| ID | Sev | Finding | Status |
|---|---|---|---|
| F22 | HIGH | Orig item 1 "weather delays" was never actually handled: NO stale-pending void mechanism existed in the code, despite earlier session notes claiming one shipped in v10. A postponed or cancelled game left its play pending forever (pending count and open-exposure polluted permanently; a game rescheduled >6h away also could never grade, correctly avoiding a mis-grade but never resolving). July is MLB rainout season; this was live and time-sensitive. | FIXED: void pass in grade_pending. Pending plays 72h past scheduled start grade 'void', 0 units_pl, void_reason recorded, excluded from record like pushes (mirrors real book settlement: books refund postponed MLB bets). Surfaced in tracker bar, Results note, stats, CSV. MODEL_VERSION unchanged (settlement-only, not a decision change). Lesson recorded: trust the code, not prior chat claims |
| F23 | MED | Orig 2 "bookmaker disagreement" + orig 6 "confidence intervals" have no data to run on: analyze_game builds the full per-book price maps every run and discards them. Snapshots persist consensus-level fields only. Per-book dispersion at entry is capture-or-lose and is being lost every run. | OPEN, queued into batch 4 (item 7 logging work): persist per-book prices (or at minimum best/median/stdev + book count per market) in snapshots, sized against F13's whole-file-rewrite pattern |
| F24 | - | Orig 11 leftovers closed. Risk of ruin (20k-trial MC, same price/stake profile as F21, 80u bankroll, 500 bets): ~0.5% with a real +3.5% edge, ~2.1% at zero edge, ~6.2% at a NEGATIVE 3% edge; within 250 bets all are under 0.4%. The ladder can also step DOWN, so true risk is lower than modeled. Verdict: ruin is a non-issue at $10 units; the binding risk is wasted TIME on a no-edge model, which is what clv_fair exists to catch early. Portfolio optimization: N/A with reason (one book, one sport, fixed units, one play per game; nothing to optimize until multi-sport real money). | SHIPPED (ledger analysis; numbers also in HANDOFF changelog) |

Coverage verdicts for everything else in the original's DONE-item checklists:
- Orig 1 data quality: missing data F2, duplicates F7/F8, timestamps/TZ F7+F17 (UTC math), API inconsistencies F10, scraping failures = feed-down paths tested batch 2, closing line accuracy F6/F15/F16/F17, incorrect line movements = entry side covered by the Bovada-vs-consensus sanity gate; CLOSE-side glitch guard added to item 13 detail. Injury timing and line availability: deferred to items 6/7 (already noted there). Leakage verdict unchanged.
- Orig 5 CLV: average/by-bet-type/by-confidence/by-timing all logged as of v11, segmentation deferred to item 13 (fields exist). CLV by sportsbook: structurally N/A, one entry book; the clv vs clv_fair pair already spans the Bovada/Pinnacle references. CLV by league: dormant until multi-sport reactivates; 'sport' is on every play, ready.
- Orig 6 EV: implied probs, vig removal, fair estimation, EV formulas verified batch 1 (F4). Confidence intervals on per-bet EV: the one true leftover, blocked on F23 data, added to item 11 detail.
- Orig 11 risk: Kelly/fractional F21, drawdown F21, ruin F24, correlation F18/F21, exposure F21, bankroll volatility F21 distributions, portfolio optimization N/A (F24).
- Orig 16 (item 4 slice): F19/F20 swept the play schema; F23 is the snapshot-side gap that sweep missed.

Addendum validation: py_compile pass; live EDGEFINDER_CI=1 full run wrote docs/index.html; RS_MODE=close run clean; synthetic 4-play void test (fresh pending untouched, stale voided, legacy no-commence voided via date fallback, graded play untouched; tracker voids=2, pending=1); both dashboard script blocks executed under the stubbed DOM, results and board views rendered. Zero em dashes.

### Batch 2 validation performed
- py_compile pass; EDGEFINDER_CI=1 full run wrote docs/index.html against live Action Network data (odds key absent, feed-down path exercised); RS_MODE=close run verified (updates closes, grades, exits without dashboard or new plays); both generated script blocks executed under a stubbed DOM with populated stats, showView('results') rendered the new CLV card, variance card, and exposure warning with no reference errors; synthetic betlog test exercised seeding, the event guard, close refresh (fair capture, obs count, line-move marker), grading (clv, clv_fair, measured flags), measured-only stats with legacy-play handling, and open-units exposure. Zero em dashes.

### Batch 3 (2026-07-03, this chat): FIXED-claim verification sweep, batch 2 red-team, item 6

**Verification sweep:** every FIXED claim F1-F24 checked against the live code. All present and correctly wired: F2 backfill called in main, F3 no key material (env or gitignored file only), F4 fair_pair drives all three market branches, F5/F22 grading conventions, F6 clock+event-id guards in update_closes, F7 event_id dedupe (_bkey), F8 finals-as-lists with honest ambiguity skip, F10 alarm live in the sports loop, F12 only deliberate legacy-migration references remain, F15 seeding block confirmed, F17 close mode exits before snapshots/CSV/dashboard, F18 pending-only open_events (correct: a voided game's relisting can be re-bet fresh), F19/F20 fields at log site, F21 surfaces. This sweep exists because F22 proved prior-chat claims can be false; from now on any batch may spot-verify old claims cheaply.

**Red-team of batch 2 (one real hit, rest held):**

| ID | Sev | Finding | Status |
|---|---|---|---|
| F25 | HIGH | Live-entry hole, the F6 bug class at the MONEY decision: log_plays' pregame check was status-feed-only (state in (None,'scheduled')). AN down = state None for every game, so a delayed scheduled run or a manual run mid-slate would log LIVE in-play prices as pregame plays, corrupting the record with entries nobody could have made pregame. Asymmetry made it worse: closes (measurement) had the clock guard, entry (money) did not. | FIXED: entry now also requires commence in the future by clock; None or unparseable timestamps skip conservatively. Unit-tested (future logs, live/past/garbage skip). state None still allowed when clock says pregame, so an AN outage does not stop logging |
| F25a | LOW | Red-team probes that HELD: close side-matching is exact-string on our side (no cross-side capture); same-point rule with ML exemption correct; close_line_moved unreachable for ML; doubleheader close fallback honest (len==1 only); void ages from commence so future-game plays safe; suspended games completing inside 72h grade before the void pass (order within grade_pending); voids excluded from settled/ROI/open-exposure (re-verified); update_closes strict state=='scheduled' means an AN outage freezes closes at the seed rather than guessing, correct behavior. F14's deliberateness now documented in the soft_fair_map docstring; void_reason added to bets.csv. | CLOSED |

**Item 6 findings (data sources within API budget):**

| ID | Sev | Finding | Status |
|---|---|---|---|
| F26 | HIGH (opportunity) | Credit model rework, from the v4 docs: a `bookmakers` parameter accepts named books from ANY region, and every group of up to 10 books bills as ONE region. Current fetch (regions=us,eu, 3 markets) costs 6/full run. A curated 10-book list spanning the same decision inputs (bovada, pinnacle, betfair_ex_eu, matchbook, betonlineag, lowvig, draftkings, fanduel, betmgm, marathonbet) would cost 3/full run and 1/close run: 7/day, ~210/month, freeing budget for the West-coast close run (~240/month with it) or a third full board. Tradeoff: consensus nb shrinks from every-us-eu-book to 10 curated (arguably an upgrade: drops mybookieag-class noise). TWO VERIFICATIONS REQUIRED BEFORE IMPLEMENTING, owner curls below: (a) which of the 10 actually carry baseball_mlb, (b) whether exchange h2h_lay rows count as a billed market (docs say cost = unique markets IN THE RESPONSE x regions; lay rows arriving automatically could double the h2h bill). | OPEN, implement in batch 4 after curl results |
| F27 | MED (opportunity) | betfair_ex_eu and matchbook are IN the eu region (docs-confirmed) that the tool ALREADY fetches. Meaning: (a) exchange prices are likely inside today's consensus median and get power-devigged like vigged books, a category error (an exchange's back price carries spread, not vig): mild, median-dampened, but real (new assumption A9); (b) their h2h_lay rows arrive and are silently skipped by the parser; (c) the biggest unused asset in hand: Betfair back/lay MIDPOINT is a vig-free true-market fair probability, a potential anchor upgrade or cross-check on Pinnacle (which the docs note is scraped from the public site and may lag). Plan: log-only alongside pin fields, compare anchors at N. | OPEN, log-only implementation in batch 4 |
| F28 | - | AN finals VERIFIED LIVE to retain per-book odds after completion (markets dict keyed by book id, ML/spread/total rows, is_live flags; 9/9 finals had them). Free, zero credits, already inside the grading payload. Candidate: a second close reading captured AT GRADING TIME. Unknowns: book-id-to-name mapping (ids 15/30/68/69/71 observed) and whether the stored odds are the last pregame or last overall update (is_live False on final games suggests pregame lock, unproven). | OPEN, log-only after a short observation window; do not use in clv_fair until semantics proven |
| F29 | - | MLB Stats API verified live, free, keyless: finals with scores (grading backup, supersedes the paid /scores parking-lot idea), probable pitchers (13/13 of today's games already posted), venue, dayNight, doubleheader flag. This is item 7's feature backbone and the F2 backup path. statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=probablePitcher,weather | VERIFIED, wire in batch 4 (log-only) |

**Owner curls before batch 4 (run locally with your rotated key, paste both outputs into the batch 4 chat):**
```
curl -s "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey=KEY&bookmakers=bovada,pinnacle,betfair_ex_eu,matchbook,betonlineag,lowvig,draftkings,fanduel,betmgm,marathonbet&markets=h2h,spreads,totals&oddsFormat=american" -D headers.txt -o board.json
grep -i x-requests headers.txt
python -c "import json;d=json.load(open('board.json'));print(sorted({b['key'] for g in d for b in g['bookmakers']}));print(sorted({m['key'] for g in d for b in g['bookmakers'] for m in b['markets']}))"
```
Read: x-requests-last shows the true credit cost of that call (answers the h2h_lay billing question); the two printed lists show which books carry MLB and whether h2h_lay arrived.

**Batch 3 validation:** py_compile; live EDGEFINDER_CI=1 full run; RS_MODE=close run; stubbed-DOM execution of both script blocks (results + board views); clock-guard unit test (future/live/None/garbage timestamps); AN finals and MLB Stats API checked with live fetches, Odds API facts taken from the official v4 docs pages, not memory. Zero em dashes.

### Batch 4 (2026-07-03, this chat): Item 7 feature engineering + F23/F26/F27/F29 implementation

**Feature disposition (orig 2 brainstorm, MLB-translated). The organizing principle: log stable IDs, because `mlb_gamePk` and pitcher ids make nearly everything retroactively reconstructable from the free MLB Stats API. Capture keys now, derive features later.**

| Disposition | Features | Why |
|---|---|---|
| LOGGED NOW (v12) | probable pitchers + ids, venue/park, day/night, doubleheader flag, mlb_gamePk, weather-when-posted, per-book h2h prices + implied-prob stdev (snapshots), exchange back/lay/midpoint | Capture-or-lose at bet time, zero decision changes |
| Reconstructable later via logged keys, no action | pitcher handedness + any career/season stat (ids), park factors, altitude, indoor/outdoor (venue), line-move velocity + reverse line movement (snapshots run_ts series + tickets), series game number (gamePk), divisional familiarity (team names), umpire (gamePk boxscore), bullpen fatigue (gamePk game logs) | Derivable offline whenever analysis wants them |
| Needs a fetch-cadence change, deferred | confirmed lineups (posted 2-4h pregame; would need a late fetch), real-time injury/questionable status (no free timely feed worth the complexity yet) | Revisit if calibration work shows lineup-sensitive misses |
| SKIP with reason | travel distance, rest days (near-uniform in MLB, low signal per effort), back-to-back/3-in-4/byes (NFL-isms), pace, coaching tendencies, revenge games (narrative), playoff implications (irrelevant until September) | Effort exceeds plausible signal at this scale |

**Implementation findings/status updates:**

| ID | Status change |
|---|---|
| F23 | FIXED: snapshots persist per-book h2h dict, h2h_disp (population stdev of vigged-book implied probs), exchange quotes, ml_ex_mid. bets.csv +14 columns, snapshots.csv +2 |
| F26 | IMPLEMENTED, FLAG OFF: BOOKMAKERS_PARAM behind RS_BOOKMAKERS env. Zero behavior change until enabled. Enable ONLY after the owner curl (batch 3 section) answers MLB coverage + h2h_lay billing; MODEL_VERSION auto-appends +bk10 when on |
| F27 | SHIPPED, two parts. (a) Log-only: ex_back/ex_lay/ex_mid on every ML play and rec (midpoint of back/lay implied probs, vig-free fair). (b) DECISION CHANGE, deliberate: exchange books are now EXCLUDED from the vigged-consensus median (matched by stable API key, not display title). Power-devigging an exchange back price was the A9 category error; fixed at the source rather than logged around. Pinnacle-anchored games unaffected; consensus-fallback games get a cleaner median and slightly lower nb. MODEL_VERSION bumped to v12-audit4 accordingly |
| F29 | SHIPPED log-only: fetch_mlb_context() (free, keyless, one call per full run, skipped in close mode, graceful on failure) stamps plays with gamePk/venue/dayNight/doubleheader/probables+ids/weather. Join misses counted and printed (A8 discipline), never fatal |

**Batch 4 validation:** py_compile; live EDGEFINDER_CI=1 full run (docs + CSVs written, new columns confirmed present: 14 in bets.csv, 2 in snapshots.csv); RS_MODE=close run clean (context fetch correctly skipped); synthetic 4-book payload test proved exchange exclusion from consensus, ex_mid math (0.4025 on the fabricated quotes), Pinnacle anchor precedence, dispersion 0.0096, and field threading through build_recommendation; live fetch_mlb_context returned all 13 of today's games with probables, joined by full-name key; stubbed-DOM execution of both script blocks (results + board). Zero em dashes.

### Batch 5 (2026-07-03, this chat): Items 8 + 16, market efficiency and microstructure

| ID | Finding |
|---|---|
| F30 | Item 8 verdicts. HONEST FRAME: MLB full-game ML/SPR/TOT at a major book is among the MOST efficient betting markets that exist; the plausible edge is small (1-3% when real) and lives in specific windows, not everywhere. Where Bovada plausibly lags Pinnacle: (1) morning boards (15:00 UTC) before sharp volume matures: more raw gap, but the fair itself is less settled, so apparent EV is partly noise; (2) news shocks (scratched starter, weather): probable-pitcher ids + wx now logged (F29) make these auditable; (3) totals more than sides (weather/park driven, MLB totals are weather markets in disguise); (4) intra-day steam that the 2-observation cadence structurally CANNOT see (the AN-based steam flag is move-since-open, not real-time). Out of scope with reasons: props/alternates (per-event endpoint credit costs), live/halftime (paper-trade design excludes in-play by F25's own guard), true openers (post overnight; a pre-15:00 observation is a credit question for after F26). PRE-SPECIFIED gated analyses the v12 data can answer at N, written so batch 10+ runs them instead of inventing new ones: (a) clv_fair by run hour (does the 15:00 or 21:30 board realize better), (b) does h2h_disp at entry predict realized clv_fair (disagreement = opportunity), (c) does sharp gap at entry predict subsequent Bovada movement in snapshots (A2 test), (d) EV persistence 15:00 to 21:30 on the same event (if edges vanish intra-day, Bovada corrects and entry timing is everything), (e) added post-F44: clv_fair bucketed by pin_age_min (0-2, 2-5, 5-15 min) so the stale-anchor threshold gets set by data instead of by a props-market rule of thumb |
| F31 | Item 16 verdicts. Bid/ask: LITERALLY CAPTURED since v12 (ex_back/ex_lay is the exchange's two-sided quote; wide spread = thin market = distrust ex_mid, usable as a liquidity filter later). Limits: Bovada MLB main-market limits (~$1k+) are 50-100x current $10-15 stakes, a non-issue until real scale; the REAL microstructure risk is account limiting of winners at recreational books, unknowable until live and unhedgeable in paper. Line freezes: Bovada delisting a game while the consensus prices it is now counted per run (bov_absent, shipped batch 7) and alarmed on the health strip. Latency/execution: the human bets minutes-to-hours after a run; paper assumes fill at logged price (A3). At real-money start, record the actually-placed price beside the logged one and track execution slippage as its own CLV-style metric (FUTURE.md real-money note). Book-specific behavior: Pinnacle = market-maker model (welcomes sharps, moves on money, but scraped and can lag, A10); Bovada = retail model (shades popular sides, slow on news, bans winners). The tool's thesis restated in microstructure terms: it harvests the retail book's update lag against the market-maker's price |

### Batch 6 (2026-07-03, this chat): Items 12 + 17 + power analysis (pulled from 11)

| ID | Finding |
|---|---|
| F32 | POWER ANALYSIS, the numbers that set the whole timeline (simulated at the actual price/stake profile, one-sided alpha 5%, power 80%). W/L-based proof of a real +3.5% edge: ~8,100 bets, which is ~11 MLB seasons at 4 plays/day. It is not a viable endpoint and never was. clv_fair-based proof: 15-100 measured closes depending on its per-bet stdev (unknown until ~30 closes accumulate; bracket 3-8%). Falsification (true clv_fair of -1%): 55-400 measured. CONSEQUENCE: the pre-registered protocol (now in FUTURE.md section 1) sets success = mean clv_fair > 0 with 90% bootstrap CI above 0 at n>=50 measured; failure = mean < 0 with 90% CI below 0 at n>=150 measured, which halts real-money plans. The W/L record, expected-vs-realized gap, and drift card are monitoring surfaces, NOT endpoints. Segments are exploratory, never victory conditions |
| F33 | Items 12 + 17 codified rules. Bias map onto the forward test: look-ahead prevented by clock guards + capture-at-log schema; survivorship prevented by append-only log with voids visible; selection bias ACKNOWLEDGED as the product (the record measures "this tool's picks", segment any cross-regime comparison by MODEL_VERSION); confirmation bias prevented by the pre-registration above, written BEFORE results exist; snooping/multiple-testing rule: thresholds and anchors may only be revisited at the N-gates (100 graded: anchor A/B + devig comparison; 150: calibration; 250: full review), never between them, and every decision-logic change bumps MODEL_VERSION and restarts that logic's evidence clock; overfitting rule: no fitted calibration (Platt/isotonic) before n>=150 with a time-based holdout. Retraining is N-based, not calendar-based. Changes are never retroactive (verified v11.1: no overwrite path). Drift detection shipped in batch 7 (rolling vs cumulative clv_fair); concept-drift note: segment by month across season boundaries |

### Batch 7 (2026-07-03, this chat): Item 13 monitoring, implemented

| ID | Finding |
|---|---|
| F34 | SHIPPED. (1) Feed-health strip on Results, rendering even with zero settled bets (its job is catching a dead pipeline before results exist): last run ts/mode, odds and AN game counts, plays logged, closes touched, graded, with alarms for empty odds feed, name-join misses (F10 was console-only), Bovada-absent games (F31 freeze marker), MLB-context misses. (2) Per-run runlog: ridgeseeker_runlog.json, append-only, trimmed to last 500 runs (~5 months) per F13 discipline, exported as runlog.csv; joins betlog/snapshots in the never-hand-back set. (3) Expected-vs-realized card: sum of stated EV units vs delivered units on settled bets, the earliest inflation detector. (4) Drift card: rolling last-20 vs cumulative clv_fair (item 17's decay detector). (5) EV-at-close segment card by market and run hour, labeled exploratory per F32, hidden below n=10. Deferred with reasons: calibration view (gated on item 10 at ~150), h2h_disp trend chart (needs weeks of snapshot rows first) |
| F35 | BUG found and fixed during batch 7 wiring, introduced in batch 4: the _books_h2h/_ex_* card pops were placed in the sports loop, which runs BEFORE log_snapshots, so every F23 snapshot field would have persisted as None. Slipped through because the batch 4 synthetic tested analyze_game output directly and the keyless CI run produced zero snapshot rows. Fixed: internal fields now stripped AFTER snapshots persist, before template embedding; proven with a direct log_snapshots test (fields present in the written row). Lesson appended to the F22 one: synthetic tests must cross the same function boundaries production does |

**Batches 5-7 validation:** py_compile; live full CI run + close-mode run (both append runlog entries, verified 2 entries with correct modes and live AN counts); snapshot persistence test through log_snapshots proper (F35 proof); stats test with 24 fabricated graded plays exercising ev_real, clv_roll (win=20), and all three segment keys; stubbed-DOM execution with health strip asserted present on the zero-bets branch and alarm logic asserted. Zero em dashes.

### Feature drop (2026-07-04, this chat): Tier-NOW roadmap items 1-5 + data-source sweep

| ID | Finding |
|---|---|
| F36 | SHIPPED, all log-only, MODEL_VERSION unchanged: (1) best-price capture (`bo_price`/`best_price`/`best_book`, same-point discipline verified: a BetOnline total at 9.0 correctly refuses to price Bovada's 8.5 line); (2) starter-scratch detector (per-gamePk probable diff between runs, alarms + `probable_changed` + `probable_changed_post_log` stamps, once-only firing verified); (3) open-meteo weather at start hour + `roof` + `park_rf_approx` (approx values, Statcast swap noted; park wind-azimuth table DEFERRED rather than half-guessed); (4) `RS_MODE=observe` so the opener cron cannot silently change entry timing (the F18 first-logged-wins guard would otherwise have claimed games at immature 13:30 prices: a model change nobody ordered); (5) new workflow with commented expansion crons gated on F26, and an RS_BOOKMAKERS truthiness fix ('0' now means off). One process note: an edit script printed instead of saving, leaving SPR/TOT referencing a helper that did not exist; compile cannot catch runtime names, the unit battery did. Validation: 3-mode live sequence (full/observe/close) with runlog mode integrity, live weather for 2 parks, live AN capture 15/15 games, DOM pass |
| F37 | Source-sweep verdicts. CAPTURED NOW at zero credits: AN per-book pregame ML odds (`an_ml`, book ids 15/30/68/69/71, is_live rows excluded) on sharp entries, ML plays, and snapshots: a free second odds source riding a payload already fetched; mapping/timestamp semantics proven offline before any metric uses it (extends F28). EVALUATED AND DEFERRED: us2 region or a wider named-book list (post-F26 decision: 10 curated books at 3 credits beats 20 at 6 until dispersion data argues otherwise); umpire assignments (day-of timing limits value, roadmap #15 stands); confirmed lineups (needs a late fetch cadence, revisit if calibration shows lineup-sensitive misses). SKIPPED WITH REASONS: direct Betfair API (needs an account/key; the Odds API exchange rows already provide back/lay), Pinnacle direct (no public API), ESPN scoreboards (redundant to MLB Stats), Odds API /historical (paid tier). The honest summary: after this drop the tool captures every free source identified; the remaining data upside is credit-gated behind the F26 curls |

### Multi-sport activation (2026-07-04, this chat): owner-directed

| ID | Finding |
|---|---|
| F38 | SHIPPED (see HANDOFF v13). Verification performed: all six AN league slugs returned live payloads in the parser's exact shape (nfl 16 listings, ncaaf 99, nba 4 summer-league, nhl 1, wnba 2, ncaab 0 offseason); Odds API pricing confirmed from the official site (free 500; 20K $30/mo; 100K $59). CREDIT TABLE, the decision that matters: November with 5 active sports at 2 full + 1 close per day = ~2,100 credits/month on regions billing, ~1,050 with F26, ~600 even degraded to 1 full + 1 close with F26. NO free-tier configuration carries 5 sports at audit-grade cadence. Verdict: MLB-only summer stays free; fall multi-sport requires the $30 20K plan (~4,200/month worst case incl. the expanded schedule = 21% utilization) OR cutting to 2-3 sports with F26. A startup credit warning enforces awareness. Known risks ledgered: college team-name joins across APIs will produce F10 alarm noise in week one (name normalization is the expected first CFB/CBB fix); Bovada carries thin markets on small-conference games (MIN_BOOKS gate handles); NCAAB slate size will bloat the board page in Feb-Mar (render cap parked to item 20). Flagged and dismissed: a competitor blog (OddsPapi) claiming The Odds API lacks Pinnacle and Betfair Exchange; the official bookmaker page lists both and this tool anchors on Pinnacle from this API daily. Alternative provider noted for the far future: TheRundown normalizes Bovada+Pinnacle+BetOnline+Matchbook+Kalshi in one schema (free tier 3 books) |

### Prediction-market venues (2026-07-04, this chat): Kalshi + Polymarket

| ID | Finding |
|---|---|
| F39 | SHIPPED log-only (HANDOFF v13.1). Both public APIs keyless-verified live; joined 15/15 of today's slate on each venue. THE STRATEGIC POINT: these are the two venues where winning is ALLOWED. Assumption A3 (Bovada limits winners, paper ROI overstates live ROI) does not exist there. If the Pinnacle-anchored fair finds persistent mispricing on Kalshi or Polymarket, that is a durable engine, not a bannable one. The venue-EV columns now accumulate exactly that evidence on every ML play |
| F40 | Venue economics ledgered honestly. Kalshi taker fee 0.07*P*(1-P) per contract = ~4.2% of stake at 40c: a taker strategy CANNOT clear a 3% edge; maker (limit) fills pay zero fee, so kalshi_ev_maker at the bid is the number that matters, at the cost of fill risk. Polymarket: no fee, but resting overnight books are wide (bid 2c ask 95c observed); the outcomePrices mid is the honest pregame signal and poly_ev_mid is logged against it; executable EV at a real moment needs the live book, which is a real-money-phase concern. Traps fixed during build, recorded so no chat re-trips them: Poly event startDate = creation time; derivative F5/props events share the title shape; Kalshi codes CWS/AZ. Deferred with reasons: college PM coverage (thin/absent game markets), NFL/NBA/NHL Kalshi series tickers unverified until season, Poly bid/ask for outcome[1] derived as complement of outcome[0]'s book (approximation until per-token CLOB reads are added) |

### Batches 8-10 (2026-07-04, this chat): architecture, community sweep, deliverables. SCHEDULED AUDIT PHASE COMPLETE.

| ID | Finding |
|---|---|
| F41 | Item 20 verdicts. SHIPPED: monthly snapshot rotation (live file holds current month only, rewritten each run at bounded size; prior months roll once to write-never-again archives; nothing deleted; F13 CLOSED) and model_version stamped on every snapshot row. ASSESSED, kept as-is with reasons: JSON storage is correct at this scale, SQLite trigger documented at betlog >5k plays or ad-hoc query need; feature stores N/A; linear synchronous pipeline is correct for a cron batch job (~10 HTTP calls, 30-60s; async adds failure modes for zero product value); nothing hot is recomputed; the 137KB single file with a 93KB embedded template is a DELIBERATE deployment choice (web-editor paste workflow), modularization rejected, the DOM test harness is the maintenance mitigation; NCAAB Feb board (~150 cards, ~300-400KB page) acceptable for Pages, render cap stays parked; runlog capped at 500, probables file overwritten daily |
| F42 | Item 18, evidence-labeled per owner rules. DIRECT REDDIT EVIDENCE: none; two searches surfaced zero actual threads and that is disclosed rather than laundered. VENDOR DOCS (Outlier, BetHero; both sell +EV tooling, flagged): devig landscape matches the F4 choice (power = general-purpose middle ground; Shin hits longshots harder; worst-case = min across methods); NEW additions folded into gated menus: worst-case and average devig join the 100-graded devig A/B, additive/worst-case preferred for three-way markets if soccer activates, and multi-book weighted devig folds into the anchor A/B. ACADEMIC (arXiv 1211.4000, NFL): no significant open-vs-close predictive difference and 2+ pt moves in only ~10% of games, a caution that per-sport CLV magnitude expectations differ and MLB assumptions must not be copied onto NFL spreads. OWN IMPLEMENTED EVIDENCE: 18 of the original's 21 techniques already live in the ledger; the cross-reference is section 7 of AUDIT_DELIVERABLES.md. Optional batch 9b (true research mode) remains open |

### Research-report integration (2026-07-04, this chat): v14

| ID | Finding |
|---|---|
| F43 | SHIPPED (HANDOFF v14). Fee sources: official Kalshi schedule PDF (June 2026) for the round-up-per-order rule and the existence of maker fees; third-party writeups (pm.wiki, MarketMath, PredictionHunt, LaikaLabs: all commercial prediction-market content sites, flagged) converge on maker = 25% of taker where charged but CONFLICT on universality (some standard markets may be 0% maker; special events flat 0.25%/contract). Modeled conservatively: maker fee always charged, so logged Kalshi EV errs LOW. Quantified impact at owner stakes: the old no-fee maker model overstated EV by ~1.2 points on the reference case; cent rounding adds up to 4% of stake on 1-contract orders. Suppression rules shipped as DECISION changes under MODEL_VERSION v13-research1: stale-Pinnacle discard (pin_age_min > 15, phantom-edge A10 mitigation via the payload's own last_update field, no manual spot-check dependency) and the news-window one-cycle sit-out on probable changes. Adverse-selection caveat documented on kalshi_ev_maker. Poly NCAAB taker fee wired ahead of CBB. Float-boundary bug found in testing: exact-cent fees ceiled to a phantom extra cent (42.000000000000006), fixed with pre-round |

### External research integration, ChatGPT Reddit report (2026-07-04, this chat)

| ID | Finding |
|---|---|
| F44 | Owner-supplied ChatGPT Deep Research report on 6 Reddit questions, evaluated before adoption. VERIFICATION: direct thread fetches blocked from this environment; structural checks run instead. Post-ID era analysis: 15 of 16 links have plausible ID-to-topic eras; ONE flagged near-certainly wrong (r/EVbetting bdvcei: 2019-era ID on an OddsJam topic, OddsJam launched 2021, and the URL slug says giveaway while the title claims stale lines). The report's date column is demonstrably sloppy throughout (several 2021-2023 IDs labeled months old). All upvote counts missing; per-question sample sizes are 1-3 commenters, so its Strong labels overstate n. OWNER ACTION: tap 3-4 of the decision-driving links to confirm they exist as described. INDEPENDENT CORROBORATION found during verification: a fee-calculator site publishes Kalshi's formulas verbatim as ceil(0.07 x contracts x P x (1-P)) taker and ceil(0.0175 x ...) maker, matching v14's implementation exactly; sports-business journalism (InGame via Yahoo) confirms maker fees exist only on some markets with rebate offsets and that platform-wide fees run ~1-1.2% of volume, confirming A11's always-charge stance errs conservative. ADOPTED, labeled Reddit-reported-unverified: (Q1) Bovada limits winners fast at $100+ scale (reports of $500 profit in 2 weeks triggering caps to $10-40 max bets); $10-25 stakes likely under the radar; withdrawals slow. A3 refined: paper stakes probably survive live, the CEILING is what is low. (Q3) Kalshi maker workflow validated by users: rest limits 5-15c off the touch and wait; a user-quoted ~1.25% effective maker cost is consistent with our mult; one +54% on $100 anecdote; still zero data on adverse-selection timing (gap stands). (Q4) Polymarket withdrawal-friction reports; no spread/fill data (report says so honestly). (Q5) CLV split ~3 for vs 2 against; the MLB-veteran line "closing line is not the probability, ROI pays" adopted as a protocol nuance, not a change. (Q6) Community devig practice (power/Shin for lopsided, worst-case near even, run several take the conservative) matches what is already shipped and gated. (Q2) Stale-line warnings are real but from a PROPS/steam-racing context; this tool is a 2x-daily batch design whose thesis is hours-scale retail lag, so seconds-fresh is neither possible nor the game. PIN_STALE_MIN=15 stays as an outage guard; the data decides the rest via a new pre-registered analysis (e) below |

### Data leakage verdict (item 1 core question)
No look-ahead leakage found in DECISIONS: recommendations use only prices/splits available at run time; close_price is future info but used only for evaluation, never selection. The leakage risks that existed were in EVALUATION (F2, F5, F6, F7), which is where a self-grading system quietly lies to you. All patched.

### Repo cleanup checklist (owner actions in GitHub)
- [ ] Copy in updated `ridgeseeker.py`, `HANDOFF.md`, `AUDIT_TODO.md`, `.gitignore`, `README.md` at repo root
- [ ] Edit `.github/workflows/edgefinder.yml` in the web editor, RENAME it to `ridgeseeker.yml` in the filename box, paste the new contents provided
- [ ] Rotate the Odds API key, update the `ODDS_KEY` repo secret
- [ ] Run the workflow manually once, confirm it commits `ridgeseeker_betlog.json` (with all 5 graded plays incl. the Angels loss) and `ridgeseeker_snapshots.json`
- [ ] AFTER that first successful run: delete `edgefinder_betlog.json` and the `edgefinder_history/` folder (both are then dead weight; history is preserved in the migrated files)

---

## Batch plan (one item per chat; pairs only where flagged)

Reorganized 2026-07-03 at the owner's request: 3 items per chat kept exhausting the token budget. Pairs exist only where two items answer the same underlying question or are both light design work.

| Batch | Items | Why solo / why paired | Files owner should upload |
|---|---|---|---|
| 3 | 6 data sources + verification sweep + red-team | DONE this chat (owner asked for all three at once) | done |
| 4 | 7 feature engineering (+ F23, F26, F27, F29) | DONE this chat. F26 shipped FLAG OFF; owner curls still required before enabling | done |
| 5 | 8 + 16 | DONE this chat | done |
| 6 | 12 + 17 + power analysis | DONE this chat; pre-registered protocol written into FUTURE.md section 1 | done |
| 7 | 13 monitoring dashboards | DONE this chat (health strip, expected-vs-realized, drift, exploratory segments, runlog) | done |
| 8 | 20 architecture | DONE this chat | done |
| 9 | 18 community ideas | DONE this chat (evidence-labeled; no-Reddit disclosure) | done |
| 10 | 19 deliverables | DONE this chat: AUDIT_DELIVERABLES.md | done |
| gated | 11 stat testing (~100 graded), then 10 calibration (~150 graded) | Each solo, inserted between scheduled batches whenever its N clears | bets.csv (the export, NOT the betlog JSON) + ridgeseeker.py only if dashboard code results |
| gated | 14 ML, 15 ensembles | Far future or N/A; own batches if ever unblocked | decide then |

Item 9 (assumptions) stays standing: every batch ends by checking whether its changes added or violated an entry in the assumptions register below.

Owner actions still pending: paste the new ridgeseeker.yml (adds the 22:45 UTC close cron), confirm the ODDS_KEY rotation from batch 1 actually happened.

---

## Item detail (restored 2026-07-03 from the original audit; do not compress again)

The original audit file's sub-checklists were lost in the first consolidation. Restored here per item, translated to this tool where the original assumed a generic multi-sport ML system. Items 0-5 are DONE; their residuals: integer-push EV haircut (F9, recheck ~100 bets), power vs proportional devig comparison (F4/F14, ~100 bets), CLV segmentation moved to item 13.

**Item 6, data sources within API budget.** Existing pointers: Odds API /scores as grading backup (~2 credits with daysFrom); AN finals payload as a free ML close source (semantics unverified); Betfair/Matchbook via the eu region (check whether exchange prices already arrive in the current payload before assuming a new fetch is needed); MLB Stats API as free score fallback. From orig 1, evaluate sources for: injury timing, weather delays/park weather, line availability across books, lineup confirmation timing. Budget frame: ~80 credits/month of headroom after the 14/day schedule. NOTE: verifying the eu payload needs a live key the chat must NOT be given; give the owner a curl to run and paste back, or have him commit a one-off sample JSON.

**Item 7, feature engineering (orig 2 full brainstorm).** Market: line movement, steam moves, reverse line movement, sharp/public splits, consensus disagreement, bookmaker disagreement, closing line distance. Team: travel distance, rest days, altitude, humidity, temperature, wind, rain, indoor/outdoor, revenge games, divisional familiarity, pace, coaching tendencies. Player: injuries, questionable players, backup quality, usage changes, lineup continuity. Schedule: back-to-back, 3-in-4, byes, playoff implications. MLB translation: starter quality/handedness, bullpen fatigue (usage last 3 days), park factor, day/night, umpire, series game number; byes/B2B are NFL-isms, skip. Deliverable: which features to START LOGGING NOW (log-only, zero decision changes from unproven features) vs which are reconstructable later from snapshots, vs which need a source from item 6. MUST include F23: persist per-book prices (or best/median/stdev + count per market) so bookmaker-dispersion features and per-bet EV confidence intervals become possible; size the addition against F13's whole-file-rewrite pattern.

**Item 8, market efficiency (orig 3).** Original candidates: early lines, overnight markets, props, alternate lines, niche books, weather markets, halftime, live betting, player props. This tool's reality: full-game ML/spread/total at Bovada only, so the real question is WHEN Bovada lags Pinnacle (morning lines? steam windows? closing hour?) and whether the 15:00/21:30 UTC boards sit inside those windows. Design the snapshots-based analysis that answers it at N; decide which original candidates (props, alternates, live) are ever reachable within budget or are out of scope, and say so explicitly.

**Item 10, probability calibration (orig 4). GATED ~150 graded plays.** Reliability diagrams, Brier score, Expected Calibration Error, log loss, calibration curves; Platt scaling, isotonic regression, Bayesian calibration as remedies if miscalibrated. Calibrate the devigged fair probs (the model's real prediction), segmented by MODEL_VERSION (pre-v10 proportional vs v10+ power). All required fields already logged as of v11.

**Item 11, statistical testing (orig 7). GATED ~100 graded plays, EXCEPT power analysis (pure math, pulled into batch 6).** Bootstrap confidence intervals on realized ROI and on mean clv_fair; Monte Carlo (F21 variance work done, reuse it); Bayesian estimate of true edge; hypothesis test vs zero edge; variance estimation; edge significance; power analysis (bets required to detect a 2-4% edge at given confidence, which sets the real paper-trading timeline); per-bet EV confidence intervals (orig 6 leftover, needs F23 per-book dispersion data).

**Item 12, backtesting/forward-test hygiene (orig 8).** Look-ahead bias, survivorship bias, selection bias, confirmation bias, data snooping, multiple testing, overfitting, curve fitting. Forward-test translation: threshold tuning on the same data being collected is snooping (any GRADE_THRESHOLDS change mid-sample must be version-stamped); one-play-per-game selection rule creates a selection effect worth documenting; never delete losing versions from the log (survivorship); segment everything by MODEL_VERSION.

**Item 13, monitoring dashboards (orig 13).** ROI, expected ROI (sum of stated EV vs realized), CLV/clv_fair trend, calibration view (once item 10 exists), feature drift, prediction drift, market drift, API failure counts, data freshness stamps. Plus parked: CLV segment views (by market, rec_type, EV tier, run time; all fields logged as of v11), name-join alarm surfacing (F10 prints to console only), close-coverage% trend, and a close-price glitch guard (orig 1 'incorrect line movements' leftover: entry prices pass the sanity gate, but a glitchy Bovada close would silently corrupt CLV; flag closes implying >8pts of fair-prob move).

**Item 14, ML models (orig 9). GATED ~500+ graded plays or external historical data.** Gradient boosting, XGBoost, LightGBM, CatBoost, random forest, logistic regression, Bayesian models, neural nets, stacked ensembles, model averaging. Honest framing when unblocked: at this data scale, regularized logistic regression on a handful of features is the ceiling; anything deeper is overfit theater.

**Item 15, ensembles (orig 10). GATED: needs a second model to exist.** Weighted averages, Bayesian model averaging, stacking, blending, dynamic weighting, context-aware weighting.

**Item 16, market microstructure (orig 12).** Bid/ask spreads, liquidity, limits, line freezes, market makers, latency, execution timing, book-specific behavior. Relevance here: Bovada limits are unknowable via API (F20 accepted); execution timing = the gap between run time and a human actually placing the bet (price may move; consider logging a decision-to-execution staleness assumption); book-specific behavior IS the edge thesis, hence pairing with item 8.

**Item 17, continuous learning (orig 14).** Retraining schedule, feature importance drift, adaptive weighting, online learning, performance decay detection, concept drift detection. Translation: when and how thresholds/devig choices get revisited (calendar? every N bets?), what triggers a MODEL_VERSION bump, and a rule that changes are never applied retroactively to logged plays.

**Item 18, community ideas sweep (orig 15). RESEARCH MODE ON.** Techniques to research from experienced bettors/quants: removing vig correctly, closing line prediction, market maker modeling, ensemble forecasts, Bayesian updating, feature stability, probability calibration, CLV optimization, market timing, correlated bet detection, bootstrap confidence intervals, Monte Carlo bankroll simulation, Kelly optimization, model explainability, drift detection, outlier detection, market regime detection, change-point detection, meta-models that decide when NOT to bet, confidence scoring, EV confidence intervals. Cross-reference each against the ledger: already done, worth adding, or N/A at this scale.

**Item 19, final deliverables (original Deliverables section, full spec).** (1) Ranked list of top improvements by expected ROI (original said 50; rank whatever the ledger honestly supports, do not pad). (2) Quick wins (1-2 hours). (3) Medium projects (1-2 days). (4) Major architectural improvements (1-4 weeks). (5) Technical debt assessment. (6) Roadmap toward an institutional-quality platform. (7) Ideas advanced communities discuss that hobbyist models overlook (feeds from item 18). (8) For EACH recommendation: expected impact, difficulty, confidence, dependencies, and how to validate it actually improved performance.

**Item 20, architecture review (remainder of orig 16).** Is the storage schema right (JSON blobs vs SQLite), what is recomputed that should be cached, pipeline structure, what should be async, SQL vs Python boundaries, feature stores (almost certainly N/A at this scale, say so), how historical snapshots are versioned. Carries F13 (snapshots file rewritten whole every run, fine for months at MLB scale, not fine multi-sport).

---

## Assumptions register (item 9, standing; check every batch)

For each: why it could be wrong, how to test, impact if false.

| ID | Assumption | Why it could be wrong | Test | Impact if false |
|---|---|---|---|---|
| A1 | Power-devigged Pinnacle = true fair probability | Pinnacle carries its own favorite-longshot structure at extreme prices | Calibration of pin-implied probs vs outcomes (item 10) | Entire EV signal biased; the model's core belief |
| A2 | AN sharp splits are accurate and timely | AN aggregates unknown books, unknown delay | Does sharp gap predict subsequent line movement in the snapshots (item 8 analysis; h2h_disp + per-book series shipped v12 make this runnable) | Sharp-signal plays are noise |
| A3 | Logged Bovada price is executable (limits, availability, account health) | Recreational books limit winners; API price is not a fill | Untestable via API; at real-money start, record placed price beside logged price and track execution slippage (F31) | Paper ROI overstates live ROI |
| A4 | Games are independent (one play per game since F18) | Same-slate weather/ump clusters could correlate totals mildly | Correlation of same-day totals results at N | Mild variance understatement, MAX_DAILY_UNITS already hedges |
| A5 | 1.5pt steam threshold (tuned on proportional devig, F14) still meaningful under power devig | Threshold semantics shifted with the devig change | Compare steam-flag hit rate pre/post v10 at N | Steam signal mistuned |
| A6 | The us-region board CI sees = the board a Dallas bettor sees | Region/geo price differences exist | Spot-check a few lines manually vs the app | CLV and EV measured on a board nobody can bet |
| A7 | The 15:00/21:30/22:45 cadence captures the value window | Sharp money may mature after 21:30; close run does not log plays | clv_fair by run time (item 13 segment view) | Systematically betting into stale value |
| A8 | Team-name join across APIs is stable | Renames like "Athletics" | F10 alarm now watches every run | Silent data loss for a team (was F10, mitigated) |
| A9 | Every book in the consensus is a vigged sportsbook | RESOLVED v12: exchange books excluded from the consensus median by stable API key; their quotes logged separately (ex_back/ex_lay/ex_mid) | Fixed at source (F27b); anchor A/B at N decides if ex_mid becomes primary | Was: consensus fallback fair slightly biased |
| A10 | Pinnacle anchor beats the exchange midpoint as fair | Docs note Pinnacle odds are scraped and can lag; Betfair MLB EU liquidity can be thin pre-morning, so neither wins by definition | MITIGATED v14: pin_age_min logged on every play; value recs on quotes >15 min old are discarded, not bet. Anchor A/B at ~100 graded still decides the winner | Wrong anchor = systematically mismeasured EV |
| A11 | Kalshi maker fee = 25% of taker wherever charged; no special-event flat fees on our markets | Official schedule says maker fees vary by market and special events differ; third-party sources conflict on standard-market maker rates | Verify per-market via the app's fee display at first real Kalshi order; revisit each season | Logged Kalshi EV errs low (safe direction) if a market is actually 0% maker |

## Parking lot (ideas surfaced early, belongs to later items)
- Odds API /scores endpoint as a grading backup: SUPERSEDED by the free MLB Stats API (F29, verified live batch 3)
- Pinnacle-anchored EV means the model is really measuring "Bovada mispricing vs Pinnacle": frame item 8 (market efficiency) around when Bovada lags (steam windows, morning lines)
- MODEL_VERSION now v10: all pre-v10 plays used proportional devig; segment any future EV-vs-results analysis by version
- MODEL_VERSION v11: pre-v11 graded plays have biased-coverage CLV (F15); prefer clv_fair on v11+ plays for the headline read
- Per-sport streams (v13): non-MLB thresholds run on _default until calibrated; NEVER pool sports in the primary endpoint; the F32 success/failure gates apply independently per sport
- AN finals odds VERIFIED (F28): free per-book close reading at grading time; book-id mapping + timestamp semantics still to prove before any metric uses it
- Integer-total push haircut (F9): still OPEN, recheck at ~100 bets
