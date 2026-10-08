# RidgeSeeker: Future Inclusions Log

**Purpose:** planned improvements, known weaknesses, and gates, for the owner and any AI working on this repo. Move shipped items into the HANDOFF.md changelog. Companion to the owner's Nimbus weather project; the two share a philosophy: honest edges, calibration before scale, no manufactured signals.

## 1. Now through ~100 settled bets

- [ ] Let CLV accumulate. The single question this phase answers: is average EV-at-close (clv_fair, the headline metric since v11) positive? Positive at scale = the picks beat the market's final fair value. Negative with a winning record = the record is luck. Watch the coverage% too: it shows how many closes were actually observed post-entry.

### Pre-registered evaluation protocol (v12.1, written before results exist; do not move these goalposts)
- PRIMARY ENDPOINT: mean clv_fair on MEASURED plays (close_obs > 0), v11+ only.
- SUCCESS: at n >= 50 measured, mean clv_fair > 0 with a 90% bootstrap CI above 0. This is the evidence bar for trusting the model, alongside the existing LEVELS bankroll gates.
- FAILURE: at n >= 150 measured, mean clv_fair < 0 with a 90% CI below 0. The model as-is is falsified: halt real-money plans, return to anchor/threshold work, bump MODEL_VERSION on any change.
- Minority view worth recording (F44, Reddit-reported): "closing line is not the probability, ROI pays." Correct in the limit; the power analysis is WHY ROI cannot be the early metric here. If the model ever genuinely beats the close's information, clv_fair will understate it, and the long-run ROI record remains the final arbiter. The gates stand.
- The W/L record is NOT an endpoint: proving a +3.5% edge through wins and losses needs ~8,100 bets, about 11 seasons at this volume (AUDIT_TODO F32). The expected-vs-realized card and drift card are monitoring, not endpoints. Segment tables are exploratory, never victory conditions.
- Decision logic may only be revisited at the N-gates (100 graded: anchor A/B + devig comparison; 150: calibration; 250: full review). Between gates, no tuning.
- [ ] Watch "By stated EV": if 8%+ stated edges do not outperform 3-5% ones, the fair value or the gate needs work.
- [ ] Watch "By sharp grade": the tickets/money gap signal is UNPROVEN. If S/A grades do not out-earn B/C over 100+ bets, demote the sharp signal to a tiebreaker or drop it. Do not defend it out of loyalty. INSTRUMENT SHIPPED v14.3: the Signal lab shadow ledger logs the sharp-side ML for EVERY grade S through D at zero units (the real betlog only ever received hero plays, so this comparison had no uniform data before). The C/D verdict reads off the shadow table's EV-at-close column; treat ~30 graded per row as the earliest meaningful glance and the existing N-gates as the only decision points. Same for the value engine: value flags without sharp agreement were never logged either; the "value flag" shadow row now measures the Pinnacle-anchor engine on its own.

## 1b. Anchor A/B (v12 groundwork shipped, GATED ~100 graded plays)

- [ ] Every ML play now logs `ex_mid` (Betfair back/lay midpoint, vig-free) beside the Pinnacle-anchored fair. At N, compare which anchor's stated EV predicts results and clv_fair better. If the exchange wins, it becomes the anchor and Pinnacle the fallback. Do NOT switch on intuition; the docs note Pinnacle is scraped and can lag, but Betfair MLB EU liquidity can be thin pre-morning. Data decides.

## 2. Sharpen the close (v11 shipped the first pass; see HANDOFF changelog)

- [x] SHIPPED v11: close seeding + the tiny h2h-only close-capture run (RS_MODE=close, 2 credits) at 22:45 UTC. Note the old 23:30 UTC idea was wrong: 7:05pm ET starts are 23:05 UTC, 23:30 would miss the East slate.
- [x] SHIPPED v14.5: the West-coast close run (01:45 UTC) is live. Decision made on coverage data, as this item asked: measured-close coverage was 47% and the measured-accrual rate (~0.8/day) was the binding constraint on the pre-registered endpoint timeline — the single 22:45 close run structurally misses every game that starts after it. MLB-only cost fits the free tier (~496/31-day month); the F26 flip (verify mode, below) halves it.
- [x] VERIFIED live (batch 3): AN finals DO retain per-book odds (markets dict, ML/spread/total, is_live flags) in the same free payload the tool already fetches for grading. Book-id mapping and timestamp semantics still unverified; log-only enrichment queued behind F26/F27.

## 3. Quality of life

- [ ] Telegram ping of the day's top plays after the morning run (owner already runs this pattern via Google Apps Script for work tasks; ten lines in the workflow with a bot token secret).
- [ ] Plain-English glossary on the Results tab (CLV, EV, devig, contrarian, steam).
- [x] VERIFIED v11: entry prices are frozen. log_plays skips existing keys and blocks a second pending play per game; update_closes writes only close_* fields; grade_pending writes only result/units_pl/clv fields. No overwrite path exists.

## 4. Bigger upgrades (gated on positive CLV over 100+ bets)

- [ ] Exchange blend: Betfair and Matchbook also arrive via the eu region; a Pinnacle-plus-exchange devig blend is sharper than Pinnacle alone.
- [ ] Kelly sizing from the Pinnacle-anchored fair prob instead of fixed unit tiers (needs proven calibration first).
- [ ] Re-add sports in season (NFL Sep, NBA/NHL Oct) with per-sport grade thresholds learned from each sport's own gap distribution, and redo the API credit math each time.
- [ ] **Line shopping — now measured, and it is the whole ballgame (v15).** The tool prices only Bovada. Backfilled over 1,114 pregame ML legs against devigged Pinnacle: median Bovada price **-4.39% EV**, median best-of-all-books **-1.17%**, and Bovada held the best number on **2.2%** of legs. The earlier 0.5-1.5% estimate understated it by roughly half. Set against that, every signal in this file is worth at most ~1.5 points of edge (contrarian+steam closed at -2.94% vs a -4.42% baseline), so on one book the vig is larger than the edge and no threshold change can close the gap. Realistic ladders, same 1,114 legs: Bovada+BetOnline **-2.37%**, offshore six **-1.95%**, offshore six + legal US four **-1.60%**. Opening one more account is worth more than every model change in this repo combined. `EXECUTABLE_BOOKS` is the one-line switch; `shop_gain` on each play and the "Cost of one book" card on the Results tab report the running total.

## 5. Known weaknesses (keep current)

- **Action Network dependency.** Unofficial, no-auth API used for sharp splits, live status, AND final scores. If it breaks, grading breaks. A fallback score source (MLB Stats API, free) is the mitigation when needed.
- **Tickets/money splits are a weak signal** in public research. The tracker has now rendered a partial verdict: across 263 graded rows with a measured close, EVERY grade bucket had negative mean CLV against Bovada prices. The best sub-population (contrarian + steam, i.e. the S definition) closed at -2.94% against a -4.42% Bovada baseline, so the signal is worth roughly 1.5 points — real, but smaller than the vig it is being asked to overcome.
- **One executable book.** Bovada-only means many Pinnacle-vs-soft mispricings are visible but not bettable. As of v15 this is quantified rather than asserted: it costs ~3.2 points of EV per bet (see item 4). It is the binding constraint on profitability, ahead of every modelling question.
- **The cheapest fix to the one-book problem is not a sportsbook (v15.1).** Polymarket prices the same game moneyline at a mean -1.40% EV *at the ask* vs Bovada's -4.81%, beating it on 38/48 logged plays with a median 1-cent spread, and clearing +3% on 10/48 — a threshold Bovada has never met. It needs no offshore account. The unresolved question is depth at a real stake, which the quote feed cannot answer; check live order books before routing money. Kalshi is the other US-accessible venue and its feed returns in v15.1 (the join was dead, not empty).
- **The value engine has never produced a bettable pregame flag.** Zero of 1,114 pregame Bovada ML legs cleared MIN_EV=3%; the best pregame edge ever observed was +0.91%. All 15 historical value flags fired post-first-pitch off a stale anchor and are fixed in v15. On Bovada alone the 3% threshold is unreachable by construction, so the "value bet" half of the README is currently decorative — the tool is a sharp-money follower with a value gate that never opens. Adding books is what turns it back on: at best-of-all-books 175 of 1,114 legs price at 0%+ and 5 clear +3%.
- **Close is approximate** (see item 2). Since v11 every play carries close_obs and the stats report coverage, so the approximation is measured instead of assumed. Label it honestly everywhere.
- **Doubleheaders** are skipped rather than graded (deliberate).
- **API budget** is the binding constraint on everything: 6 credits per full run, 2 per close run, ~420 of the ~500/month free tier already committed to the schedule.
- **The repo is public** (free Pages requires it). The API key lives only in the `ODDS_KEY` secret or a gitignored `odds_key.txt`; never reintroduce a hardcoded fallback (the pre-v10 key was exposed in git history and had to be rotated). NOTE (v14.4): the ignore file had silently been named `gitignore.txt` for a long time, so `odds_key.txt` was NOT actually ignored; it is now a real `.gitignore` (verified). Keep it named `.gitignore`.
- **~~Grading is MLB-only by construction~~ FIXED v14.5.** `collect_results` now falls back from `boxscore.stats.{away,home}.runs` (baseball, unchanged proven path) to the sport-generic `boxscore.total_{away,home}_points`, verified live: equal to runs on 42/42 completed MLB games across 4 days, and populated on completed WNBA games where `stats` arrives empty. Totals reflect the official final (incl. OT/SO), which is what books settle on, so ML/spread/total grading is correct for every sport in the registry. Residual caution: NFL/NHL payloads could not show a completed game in the Aug 1 check (none had finished); the field is the same documented AN boxscore shape, but eyeball the first graded week of each new sport anyway.
- **Kalshi capture is MLB-only (log-only gap, not a bug).** The Kalshi join needs a per-sport team-code map and only `KALSHI_MLB` exists; NFL/NBA/NHL plays simply log Kalshi fields as None (the join is sport-gated, nothing breaks or alarms). Polymarket capture is name-based and sport-agnostic. Add `KALSHI_NFL/NBA/NHL` maps once those markets are live enough to verify codes against real tickers.
- **Inert wrong-day guard in `analyze_game`.** The F45 block near the top of `analyze_game` runs against the splits-only `sharp_map`, so its `an_start`/`_an_same_game` branch never fires; the real wrong-day protection re-applies in `main` (F45/F45b). Harmless, left in place; remove if it ever causes confusion.

*Maintenance rule: read this with HANDOFF.md; move shipped items to the changelog.*

## Feature roadmap (added 2026-07-03, owner directive: features ARE in scope)

Ranked by expected impact on accuracy and long-term profitability. Log-first discipline still applies: decision-affecting features flip on only at their evidence gate, with a MODEL_VERSION bump. Columns follow the deliverables spec (impact, difficulty, confidence, dependencies, validation).

### Tier NOW (STATUS 2026-07-04: items 1-4 SHIPPED log-only in v12.3; item 5 workflow ready, crons commented pending the F26 curls. Park azimuth table and official Statcast park factors are the two follow-ups.)

| # | Feature | Impact | Diff | Conf | Depends on | Validate by |
|---|---|---|---|---|---|---|
| 1 | Second executable price: log betonlineag (and best-offshore) price on every play beside Bovada; later, execute at the better price | HIGH for realized ROI: price shopping is worth roughly 0.5-1.5% EV per bet it improves, about a third of the whole target edge, with zero model risk | LOW (prices already in books_h2h; copy to the play) | HIGH (mechanical) | nothing | distribution of best-minus-Bovada price across logged plays; count of plays where the other book was better |
| 2 | Starter-scratch detector: diff probable-pitcher ids between the 15:00 and 21:30 boards per gamePk; flag and log scratch events on affected games | MED-HIGH: news lag is exactly where a retail book bleeds (F30); scratches move MLB lines 20-60 cents | MED | MED | probables logging (shipped v12) | clv_fair on scratch-flagged plays vs baseline; count of scratches caught before Bovada moved |
| 3 | Weather engine for totals: open-meteo (free, keyless) wind speed/direction + temp at outdoor parks via a static venue lat/lon table, logged on TOT plays | MED (totals only, but totals are weather markets in disguise per F30) | MED | MED | venue logging (shipped v12) | totals clv_fair bucketed by wind-out vs wind-in vs calm |
| 4 | Park-factor static table joined on venue, logged per play | LOW-MED | LOW | HIGH (public data) | venue logging | feeds later regressions; no standalone claim |
| 5 | F26 flip + third observation (true-opener run ~13:30 UTC) + West-coast close (~01:45 UTC) | MED-HIGH for measurement: opener-vs-close analytics, tighter closes, line-velocity features from 3+ snapshots/day, all inside ~240 credits/month | LOW (flag + cron lines) | HIGH | West close SHIPPED v14.5; F26 verification is now one click (Actions tab -> Run workflow -> mode: verify, ~4-7 credits, prints PASS/FAIL); opener cron stays commented until verify passes and RS_BOOKMAKERS='1' | coverage% jump; per-run clv_fair table gains an opener column |

### Tier GATED (decision changes; locked to the pre-registered N-gates above)

| # | Feature | Gate | Impact |
|---|---|---|---|
| 6 | Anchor upgrade: ex_mid (Betfair midpoint) vs Pinnacle A/B, winner becomes the fair | 100 graded | HIGH: the fair IS the model; already logging both sides since v12 |
| 6b | Venue routing: recommend the execution venue per play from exec_best_venue evidence (Bovada / BetOnline / Kalshi maker / Polymarket), and a Kalshi-maker workflow (rest limits at or below the bid) | 100 graded + F40/F43 economics | HIGH for realized ROI, and the Kalshi/Poly legs carry ZERO ban risk (A3-free). v14 corrections: maker fills are NOT free anymore (~25% of taker where charged) and carry adverse selection (fills cluster when the market moves against you), so kalshi_ev_maker is an upper bound; documented Polymarket arb profit is heavily concentrated among fast actors, so the plan is patience and price, never speed |
| 7 | Devig method A/B: power vs proportional vs Shin vs worst-case vs average, on the same history (pin raw prices logged since v11); additive/worst-case preferred for three-way markets if soccer activates | 100 graded | MED |
| 8 | No-bet meta-filters: suppress plays with low nb, high h2h_disp, wide exchange spread, or morning-only edges that historically evaporate | 100-150 graded | MED-HIGH: removing the worst bets raises realized ROI faster than adding bets; the community's most under-used idea |
| 9 | Calibration remedy (isotonic, time-split holdout) if item 10 shows miscalibration | 150 graded | MED |
| 10 | Fractional-Kelly sizing replacing the flat ladder | proven calibration | MED via compounding; existing FUTURE gate stands |
| 11 | AN-finals close enrichment as a second close reading | after a 2-week semantics observation window (F28) | LOW-MED, metric fidelity |

### Tier SEASONAL / SCALE

| # | Feature | Note |
|---|---|---|
| 12 | Multi-sport reactivation | SHIPPED v13 (NFL/NBA/NHL/CFB/CBB season-gated, WNBA staged behind F26). Remaining decisions: the $30 20K plan before October (no free-tier config carries 5 sports, AUDIT_TODO F38), college name normalization in week one, per-sport threshold calibration at each sport's own N-gates |
| 13 | Retro-enrichment script: backfill features onto historical plays via gamePk | Enabler; cheap once any Tier-NOW feature proves useful |
| 14 | Bullpen fatigue (pen innings last 2 days via gamePk boxscores) | MED effort, unproven signal; after 1-3 show value |
| 15 | Umpire totals lean | Day-of data timing limits it; low priority |

Out of scope with reasons: props/alternate lines (per-event credit model breaks the budget), live betting (excluded by design and by the F25 guard), ML models before ~500 plays (item 14 verdict stands).

## Real-money microstructure note (from audit F31)
- [ ] When real money starts: record the ACTUALLY PLACED price beside the logged price on every bet and track execution slippage as its own CLV-style metric. Paper trading assumes a fill at the logged price (assumption A3); this is the only way to measure how wrong that was.
