# RidgeSeeker

Finds real sports betting edges (MLB now; more sports in season) and tracks whether they actually work. Runs itself on GitHub twice a day (plus a cheap close-capture pass that logs no new plays); you open one web page on your phone.

## How it decides
- **Fair value:** Pinnacle (the sharpest book in the world) with the vig stripped out. When Pinnacle skips a market, the no-vig median of ~25 books fills in.
- **Sharp money:** ticket% vs money% gaps from Action Network, graded S/A/B/C/D. This is what the tool actually bets. S and A require *contrarian* confirmation — a big money-vs-ticket gap only counts as sharp when the ticket count is low, because few bets carrying much money is a syndicate while the same gap inside a crowd is just a whale on a popular side.
- **Value bet:** Bovada's price beats fair value by 3%+ after sanity gates. **Honest status: this has never fired on a pregame game.** Across 1,114 pregame moneyline legs the best edge Bovada ever offered was +0.91%, median -4.39%. On one book the threshold is unreachable, so today the tool is a sharp-money follower and the value gate is dormant. It reopens when you add a second book.
- **Unit sizing:** 1u / 1.5u / 2u with a hard +250 longshot cap.

## The thing that decides whether this makes money
Not the model — **the price you pay to get the bet on**. Every signal in here is worth at most ~1.5 points of edge, while the median Bovada moneyline costs -4.39% against devigged Pinnacle. On one counter the vig is bigger than the edge and no threshold tuning changes that.

So the tool now routes each selected bet to the cheapest venue you can actually reach (`EXECUTABLE_VENUES`, currently Bovada + Polymarket + Kalshi) and tells you where to put it. Measured on the logged history the same bet prices at -4.81% EV at Bovada versus -1.40% at Polymarket's ask, so routing is worth about +3.4 points per bet with **no change to what gets bet**. Kalshi is compared net of its taker fee. P&L is graded at the price actually paid.

One thing it deliberately does not do: treat a cheap prediction-market quote as a *reason* to bet. Polymarket priced 10 of 48 logged plays at +3%-or-better against our fair, and those ten went 3-7 with -10.16% CLV. That gap is our Pinnacle anchor going stale, not an edge appearing — Polymarket's midpoint agrees with our fair to within a quarter of a point on average. Take its price; ignore its apparent edge.

**Liquidity is the open question.** A quote proves the price existed, not that your stake fits inside it. Check depth at your real bet size before trusting the routing.

## How it grades itself
- Every recommended play is logged and graded automatically off final scores.
- **EV at close** is the headline metric: your entry price scored against the market's final fair value (devigged Pinnacle when available). Price CLV (did your entry beat the last Bovada price?) is tracked alongside. Consistently positive over 50+ measured bets is proof of edge long before wins and losses settle the argument.
- Results tab: record, ROI, CLV, and breakdowns by stated EV, sharp grade, unit size, market, price, and time-to-game.
- **Signal lab:** every sharp lean S through D and every value flag is also logged as a zero-unit shadow row and graded against real closes, so "do the C's carry EV?" gets answered with data. Shadow rows never touch the record, the tracker, or the level-up gates.

## Schedule
Covers MLB now, with NFL, NBA, NHL, college football, and college basketball lighting up automatically when their seasons start (off-season sports cost nothing, and every sport grades itself with no code changes needed). Four runs daily: 15:00 UTC (~10am Central: grades last night, morning board), 21:30 UTC (~4:30pm Central: pre-slate board with matured sharp money), 22:45 UTC (~5:45pm Central: a cheap close-capture pass before the night slate, no new plays), and 01:45 UTC (~8:45pm Central: the same cheap pass for the West-coast slate, roughly doubling how many bets get a truly measured close). Credit reality: MLB alone fits the free 500/month tier; the moment a second sport is in season (college football joined August 1) the startup log prints a credit warning with the fix — run the one-click `verify` mode from the Actions tab and flip `RS_BOOKMAKERS` to halve costs, and upgrade to the $30 Odds API plan before the 4-sport autumn.

## Honest use
Paper trade until CLV is positive over 100+ bets. Level-up gates ($10 to $20 to $50 units) are built in and deliberately strict.

Where it stands after ~6 weeks (v15): 55 real bets, 21-31, -10.6% ROI, EV-at-close -3.84%. The v15 tier split is a response to that — the old A tier merged three different populations, and the worst of them (large gap, but the public on the same side) closed at -8.27% CLV while supplying a third of every bet placed. Re-graded on the same history the surviving bet set closes at +0.08% instead of -3.84%. Two caveats worth keeping in front of you: that is an in-sample backtest on the data that motivated the change, and 22 bets is far too few to call an edge either way. Judge it forward, on CLV, not on the record.

## Your data is safe when the code changes
History lives in `ridgeseeker_betlog.json` and `ridgeseeker_snapshots.json`, separate from the code, committed back after every run. Zips from your AI assistant never include them.
