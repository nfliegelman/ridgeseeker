# RidgeSeeker Audit Deliverables

**Produced 2026-07-04** at the close of the scheduled audit (items 0-9, 12-13, 16-20 done; 10, 11, 14, 15 sample-gated). Source of record: AUDIT_TODO.md ledger F1-F42. Per-recommendation columns follow the original spec: impact, difficulty, confidence, dependencies, validation.

## 1. Ranked improvements by expected ROI

| # | Improvement | Impact | Diff | Conf | Depends on | Validate by |
|---|---|---|---|---|---|---|
| 1 | Flip F26 (named-book fetch) and expand to 5 observations/day | HIGH (halves credit cost, funds everything below, sharpens every close) | LOW | HIGH | owner curls | x-requests headers + coverage% jump |
| 2 | $30 20K plan + WNBA now + fall multi-sport | HIGH on time-to-proof (3-4x graded plays) | LOW | HIGH | $30/mo | per-sport clv_fair accrual rate |
| 3 | Venue routing from exec_best_venue evidence, Kalshi MAKER workflow | HIGH on realized ROI; the A3-free (unbannable) legs | MED | MED | ~100 graded + F40/F43 (fee model corrected v14) | realized fill EV vs Bovada baseline |
| 4 | Anchor A/B: Betfair ex_mid vs Pinnacle (phantom-lag check) | HIGH (the fair IS the model) | LOW (logged since v12) | MED | 100 graded | which anchor's stated EV predicts clv_fair and results |
| 5 | No-bet meta-filters (nb, h2h_disp, exchange spread, evaporating morning edges) | MED-HIGH (cutting worst bets beats adding bets) | LOW-MED | MED | 100-150 graded | filtered-subset clv_fair vs full set |
| 6 | Devig A/B: power vs proportional vs Shin vs worst-case on logged pin prices | MED | LOW | MED | 100 graded | per-method calibration + clv_fair |
| 7 | Best-price execution across Bovada/BetOnline | MED (0.5-1.5% per improved bet, mechanical) | LOW | HIGH | none (logged now) | best-minus-Bovada distribution |
| 8 | Starter-scratch alerting (push, not just console) | MED (news window is where retail lags) | MED | MED | Telegram/Todoist infra exists | clv_fair on scratch-flagged plays |
| 9 | Calibration program (isotonic, time-split) | MED | MED | MED | 150 graded | Brier/ECE before-after |
| 10 | Kelly-fraction sizing | MED via compounding | LOW | HIGH once gated | proven calibration | drawdown vs growth realized |
| 11 | Weather/park features into totals analysis | MED (totals only) | LOW (logged now) | MED | ~100 totals | wind-bucket clv_fair split |
| 12 | AN book-id mapping + AN-close enrichment | LOW-MED (metric fidelity) | LOW | MED | 2-week observation | AN close vs captured close deltas |
| 13 | College name normalization | required for CFB/CBB week one | LOW | HIGH | season start | F10 alarm count to zero |
| 14 | Statcast park factors replacing approx table | LOW-MED | LOW | HIGH | one offline export | n/a (data hygiene) |
| 15 | SQLite migration | LOW now | MED | HIGH | betlog >5k plays | n/a (scale trigger) |

## 2. Quick wins (1-2 hours)
Run the F26 curls and flip the flag; set PLAN_CREDITS=20000 after upgrading; enable WNBA; swap in official Statcast park factors; paste the expanded workflow crons; wire scratch alarms into the existing Telegram digest.

## 3. Medium projects (1-2 days)
Venue-routing recommendation layer (6b) with a Kalshi maker workflow; no-bet filter analysis harness; anchor and devig A/B notebooks against bets.csv; AN book-id semantics study; college name-map builder fed by F10 alarm output.

## 4. Major projects (1-4 weeks)
Calibration program at the 150 gate; per-sport threshold calibration cycles as each sport accrues N; real-money execution framework (placed-price capture, slippage metric, maker fill tracking); SQLite + query layer at the scale trigger.

## 5. Technical debt assessment

| Debt | Severity | Plan |
|---|---|---|
| park_rf_approx values are approximate | LOW | Statcast export swap (quick win) |
| Polymarket outcome-2 quotes complement-derived | LOW | per-token CLOB reads with venue routing |
| Kalshi NFL/NBA/NHL series tickers unverified | LOW | verify at each season start |
| College name joins across 4 APIs | MED (seasonal) | normalization map, week one of CFB |
| _default sharp thresholds on new sports | MED | per-sport calibration at each sport's gates |
| F9 integer-total push haircut unmodeled | LOW | recheck at ~100 bets |
| betlog unbounded growth | LOW | SQLite trigger documented |
| Template is 93KB of a 137KB single file | ACCEPTED | single-file deployment is a feature; DOM harness mitigates |

## 6. Roadmap to institutional quality
Phase 1 (now, free-to-$30): paper trade, accumulate measured closes, run the manual Pinnacle spot-checks. Phase 2 (gates 50-150): pre-registered verdicts; anchor/devig/filter decisions from data; venue economics settled. Phase 3 (real capital, small): execution capture, slippage metric, Kalshi maker discipline, the A3-free venues as primary if evidence points there. Phase 4 (scale): multi-sport calibrated per sport, SQLite, alerting, and only then any ML (item 14 stands: below ~500 plays, regularized logistic regression is the ceiling and anything deeper is overfit theater).

## 7. Ideas advanced communities use that hobbyist models overlook (this audit's implementations)
EV-at-close (clv_fair) instead of naive same-book price CLV; devigging in probability space, never across two books' vigged prices; pre-registered success AND failure gates written before results exist; power analysis before trusting any sample; capture-or-lose logging keyed on stable ids (gamePk) so features are retroactively derivable; observe-mode so extra observations never change entry timing; maker-only execution on fee-bearing prediction markets; voiding as real book settlement; one play per game as correlation control; version-stamping every decision change.

## 8. Community-sweep evidence disclosure (item 18)
No actual Reddit threads were reachable via search from this environment; nothing here is presented as Reddit sentiment. Sources used and labeled: vendor education docs (Outlier, BetHero: both sell +EV tooling, treat method rankings as directionally useful, not neutral) confirming the devig-method landscape and adding worst-case/average devig and the three-way-market additive preference (relevant if soccer activates); one academic study (arXiv 1211.4000, NFL) finding no significant predictive difference between opening and closing lines and 2+ point moves in only ~10% of games, a caution against assuming large CLV magnitudes in low-move markets; everything else is this audit's own implemented evidence. An optional research-mode pass (batch 9b) remains available if deeper community sourcing is wanted.
