# Investigation and Remediation Report

Pass run 2026-07-21 against `nfliegelman/ridgeseeker` on branch `claude/ai-residue-remediation-0lcs9a`. Scope: investigate generated-default / AI-residue and incomplete-implementation problems, fix the justified ones, verify, document. This project is a mature, heavily iterated single-file tool; the mandate here was correction where justified, not a rewrite. Most findings sit at the edges (repo hygiene, frontend, two latent safety bugs), not in the core model, which is specific and well authored.

## Result
- Before residue score: ~26 / 100 (higher = more residue). The core (odds math, devig, grading, tracker, honesty philosophy, copy) already scored very low residue; the points came from two documented safety features that silently never ran, a non-functional `.gitignore`, dead frontend CSS from a removed feature, and real accessibility gaps.
- After residue score: ~9 / 100. Remaining points are the deliberately deferred items in Unresolved (MLB-only grading for future sports; an inert-but-harmless guard).
- Evidence confidence: HIGH for the code findings (each verified by grep cross-reference, a before/after logic harness, and a stubbed-DOM render test), MEDIUM for the qualitative residue scores (no prior authorship-audit baseline existed; the numbers are this pass's assessment).
- Research-completeness gate: PASSED for the layers that were consequential here (see "Intensive research"). Most classic layers (database, auth, object storage, payments, search, notifications) are Not Applicable to a single-file, read-only, statically-hosted tool and are marked so with reasons.
- Build status: `python -c "py_compile"` passes on 3.11 and the workflow pins 3.12.
- Test status: app runs end to end in `full`, `observe`, and `close` modes (exit 0); stubbed-DOM harness renders both Board and the settled Results view with zero JS errors; suppression-fix logic harness passes with negative controls.
- Deployment status: unchanged. GitHub Actions cron + commit-back + GitHub Pages from `/docs`. No workflow change required.
- Highest remaining risk: when a second sport comes into season, its games will not grade (grading parses MLB `runs` only) and will void after 72h until per-sport final parsing is added. Documented in FUTURE.md and Unresolved below.

## Product truth
- Primary user: the owner, a hobbyist MLB bettor (not a professional developer), reading one mobile web page.
- Primary workflow: twice-daily automated run fetches odds (The Odds API) and sharp splits/scores (Action Network), computes devigged-Pinnacle fair value, flags value and sharp-grade plays, logs and grades them against closing lines, and renders a mobile dashboard (Board + Results).
- Owner constraints: edits arrive as a whole-file upload via the GitHub web UI, so single-file deployment is a hard requirement; the owner's work firewall blocks the odds APIs, which is why the run lives on GitHub; free tiers only (public repo, free Pages, ~500 API credits/month); no em dashes anywhere (output is forwarded to people).
- Security/privacy boundary: the repo is PUBLIC. The only secret is the Odds API key, which must live solely in the `ODDS_KEY` GitHub secret or a git-ignored `odds_key.txt`, never hardcoded and never committed. No user PII; all displayed numbers must trace to a real API response.
- Key assumptions: paper-trading only until CLV is proven; "no plays today" is a correct, valuable output; the tracker/betlog JSON files are the durable record and must never be lost.

## Current-state inventory
| Layer | Before | Provenance | Fit | Research tier |
|---|---|---|---|---|
| Product form | Single Python script -> static HTML dashboard | Authored | Appropriate | A |
| Runtime | GitHub Actions cron (cloud), local Windows fallback | Authored | Appropriate | A |
| Language/framework | Python 3.12 stdlib only, no web framework | Authored | Appropriate | B |
| Data fetch | The Odds API (odds), Action Network (splits/status/scores), MLB Stats, open-meteo, Kalshi, Polymarket | Authored | Appropriate | A |
| Persistence | JSON files committed back to the repo | Validated inheritance | Appropriate (< 5k plays) | A |
| Secrets | `ODDS_KEY` env / git-ignored `odds_key.txt` | Authored, but ignore file BROKEN | Fixed | A |
| Network/TLS | Layered SSL fallback (`_ssl_tiers`) | Authored | Appropriate | B |
| Decision engine | devig (power), value gate, sharp grade, unit sizing, suppressions | Authored | 2 suppressions silently inert | A |
| Frontend | Embedded raw-string HTML/CSS/JS, mobile-first dark theme | Authored | Dead CSS + a11y gaps | B |
| Deployment | GitHub Pages from `/docs`, commit-back | Authored | Appropriate | B |
| Backup/recovery | Commit-back + monthly snapshot rotation | Authored | `load_log` could wipe on corrupt file | B |
| Auth / authz / payments / object storage / search / notifications | none | n/a | Not Applicable (single-user, read-only, static) | C |

## Intensive research completed

### Decision-engine suppressions (Tier A)
- Candidates: (a) fix the two guards so they fire as documented; (b) delete the guards as unused; (c) leave as-is.
- Primary sources: the code itself (build_recommendation returns key `type`; `play['mlb_gamePk']` is attached only after the block; `_top` never carried `pin_age_min`), cross-checked against the v14 changelog intent and the working `probable_changed` stamp two lines below the broken check.
- Operational evidence: `stale_skips`/`news_skips` counters would always print 0; the logged `pin_age_min` field is always null on real plays (correct on shadow rows, which thread it).
- Adversarial findings: fixing them changes play selection (skips some double-down/stale/news plays), so it is a decision change and must bump MODEL_VERSION for honest betlog segmentation; deleting them would discard documented, wanted phantom-edge and news-window protections.
- Contradictions: the v14 comment claims a "MODEL_VERSION bump" for these rules, yet they never ran, so the stamped version misrepresented behavior. Resolved by fixing and bumping the version.
- Validation spike: standalone before/after harness proves both guards were False-always before and fire correctly now, with negative controls that stay off. (See Verification.)
- Decision: FIX both, bump MODEL_VERSION to `v14-suppressfix1`, document, keep reversible.
- Confidence: HIGH. What could change it: if the owner intends these suppressions to stay off pending an N-gate, revert the commit (behavior and version string restored).

### Persistence: JSON vs database (Tier A) -> RETAIN
- Candidates: current JSON+commit-back; SQLite; hosted DB.
- Evidence: betlog is a few thousand rows at most for years; a DB adds a service, breaks the single-file/whole-file-upload constraint, and costs money or a runner dependency. The project already documents SQLite as the trigger at > 5k plays.
- Decision: RETAIN JSON. Hardened the failure mode instead (corrupt-file backup) rather than migrating.
- Confidence: HIGH. What could change it: betlog crosses ~5k plays.

### Single-file architecture, SSL tiers, sync pipeline (Tier A/B) -> RETAIN
- Each is documented, load-bearing (web-UI upload, corporate-firewall TLS, simplicity), and wins honestly. No change; challenged and kept.

### Frontend accessibility approach (Tier B)
- Candidates for keyboard tabs: native `<button role="tab">` (chosen) vs div + tabindex + keydown shim vs full ARIA roving-tabindex arrow-key pattern.
- Evidence: native buttons are focusable and Enter/Space-activatable for free, satisfying WCAG 2.1.1/4.1.2 with the least code and no new library; the full arrow-key pattern is a best-practice nicety, not a requirement, and only one tab is live today.
- Decision: native buttons + tablist/tab/tabpanel + aria-selected; defer arrow-key roving as optional.
- Confidence: HIGH.

## Exclusion log
| Candidate | Layer | Exclusion reason | Evidence | Reconsideration trigger |
|---|---|---|---|---|
| SQLite / hosted DB | Persistence | Breaks single-file upload; adds a service; unneeded at this scale | HANDOFF ADR; row counts | betlog > 5k plays |
| Web framework (Flask/FastAPI/React) | Product form | Static output on free Pages; no server needed | Deployment model | interactive server features required |
| Full ARIA roving-tabindex tabs | Frontend | Not required by WCAG; one live tab today; extra code | WCAG 2.1.1 met by buttons | multiple sports live and users request arrow-key nav |
| Deleting the two suppressions | Engine | They are wanted safety features; fixing beats deleting | v14 intent, code | owner decides to gate them off |
| Row-header `scope="row"` on stat tables | Frontend a11y | Visual regression risk (th styling); low benefit on single-header tables | `.rtable th` styling | a later CSS pass separates row-header styling |

## Stack and service decisions
| Layer | Before | After | Why | Migration | Rollback | Cost impact |
|---|---|---|---|---|---|---|
| Ignore file | `gitignore.txt` (inert) | `.gitignore` (working) | Key file was unprotected on a public repo | rename + untrack dup | restore file name | none |
| Persistence | JSON, silent-wipe on corrupt | JSON, corrupt-file backup + alarm | Prevent history loss | none (in-place) | git revert | none |
| Engine suppressions | 2 guards inert | 2 guards active, MODEL_VERSION bumped | Restore documented safety behavior | version segments betlog | git revert | none |
| Frontend | dead CSS + a11y gaps | cleaned + accessible | Authorship + WCAG | none (behavior-preserving) | git revert | none |

## Changes implemented
### Product and information architecture
No change. Product form, workflow, and data model are appropriate and were retained.

### Visual system
Removed ~6.2KB of dead CSS: the glassmorphism "bet-slip dock" (removed-parlay artifact), the unused `--rlm` purple token, and the dead `.srcprob/.lines/.infohd/.hero-pick/.row` blocks, dead badge/grade variants, a duplicate `.b-VALUE`. Lightened `--dim` and the chart axis for contrast. No new visual patterns added.

### Interaction states
Existing empty/loading/no-data/final states are intentional and were kept. Added keyboard operability and focus states so those controls are reachable.

### Copy
Reconciled README "twice a day" with the real three-run schedule. No other copy changes (copy was already specific and honest).

### Frontend and code architecture
Removed unused JS `addable` var, unused `fair_am` compute, and the dead `.tab.temp` path with its stale hardcoded date. Sport tabs converted from `<div onclick>` to `<button role="tab">`.

### Backend, data, authorization, and security
Fixed the misnamed `.gitignore` (key exposure); untracked the duplicate `ridgeseeker_latest.html`; hardened `load_log` against corrupt-file history loss; fixed the two inert safety suppressions (news-window, stale-Pinnacle) and bumped MODEL_VERSION.

### Accessibility and performance
Keyboard-operable tabs, `role=tablist/tab/tabpanel`, `aria-selected`, `aria-pressed` toggle, `:focus-visible` ring, WCAG-AA contrast, real `<h1>`/`<h2>` headings, `scope="col"` table headers, >=44px targets. Reduced-motion and text-plus-color status (already correct) left as-is.

### Testing and operations
No CI test suite exists (single-file hobby tool); added the verification harnesses described below and ran them. Workflow unchanged.

## Files changed
| File | Purpose |
|---|---|
| `.gitignore` (was `gitignore.txt`) | Make the ignore file actually work (key protection) |
| `ridgeseeker_latest.html` | Untracked (byte-identical duplicate of docs/index.html) |
| `README.md` | Reconcile the schedule copy |
| `ridgeseeker.py` | Two suppression fixes + MODEL_VERSION bump, load_log hardening, dead-code removal, accessibility |
| `HANDOFF.md` | v14.4 changelog, doc version, corrected line count |
| `FUTURE.md` | Corrected the `.gitignore` note; logged MLB-only grading + inert-guard known items |
| `REMEDIATION_REPORT.md` | This report |

## Verification performed
| Check | Procedure | Result | Notes |
|---|---|---|---|
| Compile | `py_compile` on 3.11 | PASS | workflow pins 3.12 |
| Run modes | `EDGEFINDER_CI=1` full/observe/close in a scratch copy | PASS (exit 0) | no repo state polluted |
| Suppression logic | standalone before/after harness with negative controls | PASS | both guards inert-before, fire-now, off when they should be |
| Render | stubbed-DOM Node harness evals page scripts, drives showView(board) and showView(results) | PASS, 0 JS errors | settled Results path (v14.3 crash site) renders with real 12-11 betlog |
| Dead-code safety | regenerate + diff `<body>` old vs new | IDENTICAL after normalizing the 3 intended changes | proves removals changed no behavior |
| Contrast | WCAG relative-luminance math for `--dim` new | PASS AA on all 4 backgrounds (5.0 to 6.3:1) | was 2.8 to 3.6:1 |
| A11y attributes | grep generated HTML + runtime harness | present | tablist/tab/tabpanel/aria-selected/aria-pressed/scope/h1/h2/focus-visible/44px |
| Secret ignore | `git check-ignore -v odds_key.txt` | now IGNORED | was NOT matched before |
| Em dashes | grep U+2014 in source and output | 0 | house rule intact |

## Before-and-after audit
Residue points per category, 0 (clean) to 10 (heavy residue); lower is better.
| Category | Before | After | Evidence |
|---|---:|---:|---|
| Product specificity | 1 | 1 | Domain-specific throughout; unchanged |
| Research integrity | 1 | 1 | Honest labeling, pre-registered gates; unchanged |
| Architecture fit | 2 | 1 | Single-file/JSON/SSL retained as correct |
| Backend/data/security | 6 | 1 | `.gitignore` fixed; corrupt-file guard added |
| Correctness (safety features) | 8 | 1 | Two inert suppressions now fire; validated |
| Visual system | 5 | 1 | Dead glassmorphism/purple/duplicate CSS removed |
| Accessibility | 7 | 2 | Keyboard, focus, contrast, semantics, targets |
| Copy | 2 | 1 | Schedule wording reconciled |
| Testing/ops | 4 | 3 | Verification harnesses added; still no CI suite |
| Docs/backup | 3 | 1 | Changelog, known-items, recovery hardening |

## Deliberately retained common patterns
- Single Python file: a hard constraint of the owner's whole-file GitHub-web-UI upload workflow; documented; wins honestly.
- JSON files + commit-back persistence: free, durable across ephemeral runners, right-sized below ~5k plays; DB is the pre-registered trigger, not now.
- Layered SSL fallback: every tier fixed a real firewall/TLS failure; not simplified.
- Dark mobile-first theme, monospace numerals, "no plays today" empty state, responsible-gambling disclaimer: all authored and appropriate; kept.
- Grade thresholds, +250 longshot cap, unit ladder, anchor/devig choices: deliberate and calibrated; untouched (only the two broken guards were fixed).

## Unresolved items
| Item | Reason | Risk | Required research or action |
|---|---|---|---|
| MLB-only grading | Out of scope; MLB is the only live sport | Other sports will not grade and will void after 72h once in season | Add per-sport final-score parsing (points/goals) before each sport's first live week |
| Inert F45 guard in `analyze_game` | Provably harmless (real F45 re-applies in main) | None functionally; mild confusion | Optional: delete the dead branch |
| No CI test suite | Single-file hobby tool; owner uploads manually | Regressions rely on manual/AI validation | Optional: a tiny smoke test in the workflow |
| Prospective `.corrupt-*` sidecars | New hardening writes a backup on parse failure | Could accumulate rare files | Acceptable; corruption is rare and the file is recoverable |

## Migration and rollback notes
- No data migration. Betlog/snapshots/probables/runlog were never touched by this pass (verified in git status).
- The only decision-path change is the two suppression fixes + MODEL_VERSION bump. Rollback: `git revert` the `ridgeseeker.py` correctness commit; behavior and the `v13-research1` version string return, and betlog segmentation still reads cleanly because the version stamp marks the boundary.
- `.gitignore` rename and the untracked duplicate are pure repo hygiene; reverting is a `git mv` back (not recommended).
- If re-uploading via the GitHub web UI, create `.gitignore` with "Add file -> Create new file" (dotfiles work there) rather than drag-drop.

## Updated ADRs and project instructions
- HANDOFF.md: v14.4 changelog entry (full detail), doc version bumped, stale line count corrected.
- FUTURE.md: corrected the `.gitignore` note; added MLB-only grading and inert-guard as known items.
- README.md: schedule copy reconciled.

## What could change these decisions
- betlog crossing ~5k plays -> revisit SQLite.
- A second sport going live -> per-sport grading becomes required, not optional.
- The owner choosing to gate the suppressions off pending an N-gate -> revert the correctness commit.
- Multiple live sports + user demand -> add full arrow-key tab navigation.
