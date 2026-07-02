# RidgeSeeker: Future Inclusions Log

**Purpose:** planned improvements, known weaknesses, and gates, for the owner and any AI working on this repo. Move shipped items into the HANDOFF.md changelog. Companion to the owner's Nimbus weather project; the two share a philosophy: honest edges, calibration before scale, no manufactured signals.

## 1. Now through ~100 settled bets

- [ ] Let CLV accumulate. The single question this phase answers: is average CLV positive? Positive CLV at scale = the picks beat the market. Negative CLV with a winning record = the record is luck.
- [ ] Watch "By stated EV": if 8%+ stated edges do not outperform 3-5% ones, the fair value or the gate needs work.
- [ ] Watch "By sharp grade": the tickets/money gap signal is UNPROVEN. If S/A grades do not out-earn B/C over 100+ bets, demote the sharp signal to a tiebreaker or drop it. Do not defend it out of loyalty.

## 2. Sharpen the close (after CLV proves interesting)

- [ ] The current "close" is the last pregame price seen, 2 runs/day. A third run near first pitch (~23:30 UTC for 7pm ET slates) makes CLV much more honest, but 6 credits x 3/day x 30 = 540 > 500 free. Options: drop the spreads market (4 credits/run, 3 runs fit), or pay The Odds API $30/month tier. Decide with data, not upfront.
- [ ] Alternative: a separate tiny close-capture run that fetches h2h only (2 credits) near slate start.

## 3. Quality of life

- [ ] Telegram ping of the day's top plays after the morning run (owner already runs this pattern via Google Apps Script for work tasks; ten lines in the workflow with a bot token secret).
- [ ] Plain-English glossary on the Results tab (CLV, EV, devig, contrarian, steam).
- [ ] Freeze logged plays' prices at first log (already effectively true since _bkey dedupes; verify no overwrite path exists).

## 4. Bigger upgrades (gated on positive CLV over 100+ bets)

- [ ] Exchange blend: Betfair and Matchbook also arrive via the eu region; a Pinnacle-plus-exchange devig blend is sharper than Pinnacle alone.
- [ ] Kelly sizing from the Pinnacle-anchored fair prob instead of fixed unit tiers (needs proven calibration first).
- [ ] Re-add sports in season (NFL Sep, NBA/NHL Oct) with per-sport grade thresholds learned from each sport's own gap distribution, and redo the API credit math each time.
- [ ] Line shopping: the tool prices only Bovada. Adding one or two more executable books multiplies the number of real edges more than any model improvement would.

## 5. Known weaknesses (keep current)

- **Action Network dependency.** Unofficial, no-auth API used for sharp splits, live status, AND final scores. If it breaks, grading breaks. A fallback score source (MLB Stats API, free) is the mitigation when needed.
- **Tickets/money splits are a weak signal** in public research. The tracker will render the verdict; see item 1.
- **One executable book.** Bovada-only means many Pinnacle-vs-soft mispricings are visible but not bettable.
- **Close is approximate** (see item 2). Label it honestly everywhere.
- **Doubleheaders** are skipped rather than graded (deliberate).
- **API budget** is the binding constraint on everything: 6 credits/run, ~500/month free.
- **Hardcoded API key fallback** in the source is acceptable only while the repo is private.

*Maintenance rule: read this with HANDOFF.md; move shipped items to the changelog.*
