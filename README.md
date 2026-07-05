# RidgeSeeker

Finds real sports betting edges (MLB now; more sports in season) and tracks whether they actually work. Runs itself on GitHub twice a day; you open one web page on your phone.

## How it decides
- **Fair value:** Pinnacle (the sharpest book in the world) with the vig stripped out. When Pinnacle skips a market, the no-vig median of ~25 books fills in.
- **Value bet:** Bovada's price beats fair value by 3%+ after sanity gates (longshot cap, plausibility ceiling, minimum book count).
- **Sharp money:** ticket% vs money% gaps from Action Network, graded S/A/B/C/D. Treated as a secondary signal until the tracker proves it earns its keep.
- **Unit sizing:** 1u / 1.5u / 2u with a hard +250 longshot cap.

## How it grades itself
- Every recommended play is logged and graded automatically off final scores.
- **EV at close** is the headline metric: your entry price scored against the market's final fair value (devigged Pinnacle when available). Price CLV (did your entry beat the last Bovada price?) is tracked alongside. Consistently positive over 50+ measured bets is proof of edge long before wins and losses settle the argument.
- Results tab: record, ROI, CLV, and breakdowns by stated EV, sharp grade, unit size, market, price, and time-to-game.

## Schedule
Covers MLB now, with NFL, NBA, NHL, college football, and college basketball lighting up automatically when their seasons start (off-season sports cost nothing). Three runs daily: 15:00 UTC (~10am Central: grades last night, morning board), 21:30 UTC (~4:30pm Central: pre-slate board with matured sharp money), and 22:45 UTC (~5:45pm Central: a cheap close-capture pass that sharpens CLV right before the night slate, no new plays). Uses ~420 of the ~500 free monthly API credits, leaving headroom for manual runs.

## Honest use
Paper trade until CLV is positive over 100+ bets. Level-up gates ($10 to $20 to $50 units) are built in and deliberately strict.

## Your data is safe when the code changes
History lives in `ridgeseeker_betlog.json` and `ridgeseeker_snapshots.json`, separate from the code, committed back after every run. Zips from your AI assistant never include them.
