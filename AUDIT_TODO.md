# RidgeSeeker Model Audit: TODO Tracker

**Purpose:** short-term tracker for the full model audit (source list: RIDGESEEKER_AUDIT.md, originally drafted by ChatGPT, reordered by Claude). This file is the cross-chat memory for the audit. It is separate from HANDOFF.md, which remains the permanent technical spec. Update BOTH whenever code changes.

**How to use this file (instructions for the next AI chat):**
1. Read HANDOFF.md first (prime directives, no em dashes anywhere, surgical edits only, hand back root files only, never hand back the betlog/snapshots files).
2. Then read this file top to bottom. Work the next PENDING batch (about 3 items per chat, owner's preference, option B: make fixes immediately, not just findings).
3. Findings go in the Findings Ledger below with an ID, so the final deliverables (ranked top-50 list, roadmap, tech debt assessment) can be assembled from the ledger at the end.
4. Sample-gated items must NOT be analyzed early with tiny N. Their job now is only to make sure the right data is being logged so the analysis is possible later.
5. Before starting item 15 (community ideas), tell the owner to turn ON advanced research mode for that chat. It is a pure web-research item and the one place deep research is the right tool.
6. Owner context: paper trading for now, several weeks of data gathering before real money. Optimize for long-term model quality, not quick wins on 4 bets.

---

## Audit order (reorganized) and status

Original item numbers from RIDGESEEKER_AUDIT.md in parentheses.

### Phase A: Make what is running now trustworthy
| # | Item | Status |
|---|---|---|
| 0 | Repo and CI cleanup (new) | DONE batch 1 |
| 1 | Data quality, leakage, timestamps (orig 2) | DONE batch 1 |
| 2 | EV calculations and vig removal (orig 6) | DONE batch 1 |
| 3 | CLV methodology as primary metric (orig 5) | PENDING (next batch) |
| 4 | Logging schema: capture-now-or-lose-forever fields (part of orig 16) | PENDING (next batch) |
| 5 | Risk management: unit ladder vs Kelly, bet correlation, exposure (orig 11) | PENDING (next batch) |

### Phase B: Strategy logic (auditable without sample size)
| # | Item | Status |
|---|---|---|
| 6 | Data sources worth adding within API budget (orig 1) | PENDING |
| 7 | Feature engineering brainstorm + which to start logging now (orig 3) | PENDING |
| 8 | Market efficiency: where the edge plausibly lives (orig 4) | PENDING |
| 9 | Challenge every assumption (orig 17): running checklist, revisit each batch | OPEN (standing) |

### Phase C: Sample-gated analytics (logic can be built now, conclusions blocked until N)
| # | Item | Status | Gate |
|---|---|---|---|
| 10 | Probability calibration (orig 4/5 in list: Brier, ECE, reliability) | BLOCKED | ~150 graded plays |
| 11 | Statistical testing (orig 7: bootstrap, MC, significance) | BLOCKED | ~100 graded plays |
| 12 | Backtesting audit (orig 8): forward-test hygiene review | PENDING (logic only) |
| 13 | Monitoring dashboards (orig 13) | PENDING |

### Phase D: Expansion and synthesis
| # | Item | Status | Gate |
|---|---|---|---|
| 14 | ML models (orig 9) | BLOCKED | ~500+ graded plays or external historical data |
| 15 | Ensembles (orig 10) | BLOCKED | needs a second model to exist |
| 16 | Market microstructure (orig 12): limited relevance (recreational book, no exchange), quick pass | PENDING |
| 17 | Continuous learning / retraining (orig 14) | PENDING |
| 18 | Community ideas sweep (orig 15): TURN ON RESEARCH MODE for this one | PENDING |
| 19 | Final deliverables: ranked improvements, roadmap, tech debt (assemble from ledger) | PENDING (last) |

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
| F13 | LOW | `log_snapshots` rewrites the whole growing JSON every run. Fine for months at MLB scale; revisit under item 16 (architecture) before adding sports. | OPEN |
| F14 | LOW | `soft_fair_map` (steam detection input) still uses proportional devig, deliberately, because the 1.5pt steam threshold was tuned around it. Reconcile when grades are recalibrated with real data. | OPEN |

### Data leakage verdict (item 1 core question)
No look-ahead leakage found in DECISIONS: recommendations use only prices/splits available at run time; close_price is future info but used only for evaluation, never selection. The leakage risks that existed were in EVALUATION (F2, F5, F6, F7), which is where a self-grading system quietly lies to you. All patched.

### Repo cleanup checklist (owner actions in GitHub)
- [ ] Copy in updated `ridgeseeker.py`, `HANDOFF.md`, `AUDIT_TODO.md`, `.gitignore`, `README.md` at repo root
- [ ] Edit `.github/workflows/edgefinder.yml` in the web editor, RENAME it to `ridgeseeker.yml` in the filename box, paste the new contents provided
- [ ] Rotate the Odds API key, update the `ODDS_KEY` repo secret
- [ ] Run the workflow manually once, confirm it commits `ridgeseeker_betlog.json` (with all 5 graded plays incl. the Angels loss) and `ridgeseeker_snapshots.json`
- [ ] AFTER that first successful run: delete `edgefinder_betlog.json` and the `edgefinder_history/` folder (both are then dead weight; history is preserved in the migrated files)

---

## Next batch (batch 2): items 3, 4, 5
- Item 3 CLV methodology: is last-seen-price an acceptable close proxy (F11)? Should CLV be measured vs Pinnacle close instead of Bovada close (devig question applies to the close too)? CLV by segment table design. Whether to add a late run and the credit math.
- Item 4 logging schema: what is NOT being captured that cannot be reconstructed later. Candidates: Pinnacle raw prices at log time, full book count, line/point at close (not just price), sharp splits at close, run timestamp on the play, Bovada limits (not available via API, note it).
- Item 5 risk management: unit ladder vs fractional Kelly at these EVs, same-slate correlation (multiple dogs same day), max drawdown expectations at 1-2u sizing so a normal losing streak does not get misread as model failure.

## Parking lot (ideas surfaced early, belongs to later items)
- Odds API /scores endpoint as a grading backup if AN ever breaks (item 6, costs ~2 credits/call with daysFrom)
- Pinnacle-anchored EV means the model is really measuring "Bovada mispricing vs Pinnacle": frame item 8 (market efficiency) around when Bovada lags (steam windows, morning lines)
- MODEL_VERSION now v10: all pre-v10 plays used proportional devig; segment any future EV-vs-results analysis by version
