"""Tier-ladder and value-gate tests for the v15 split.

Run: python3 test_tiers.py   (no deps, no network, no API credits)

These lock down the two behaviours v15 changed, both of which were silent failures
that cost real money and could regress without a symptom:

  1. grade_sharp: S and A now REQUIRE contrarian confirmation. The old ladder let a
     large money-vs-ticket gap reach A with no public-side test at all, and the whole
     36-54% ticket band fell through the demotion guard. That population closed at
     -8.27% CLV over 32 graded observations and supplied a third of every real bet.

  2. analyze_game: a value flag may only be raised on a PREGAME game. Every value flag
     in the tool's history fired after first pitch, when Bovada has repriced to the
     live game state and the devigged anchor has not, manufacturing fake 3-23% edges.
"""
import importlib.util

spec = importlib.util.spec_from_file_location("rs", "ridgeseeker.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

FAILURES = []


def check(name, got, expect):
    ok = got == expect
    print(f"  {'ok  ' if ok else 'FAIL'} {name}: expected {expect!r}, got {got!r}")
    if not ok:
        FAILURES.append(name)


# am2prob(-110) == 0.5238; steam fires when (am2prob(odds) - soft_fair) * 100 > 1.5
STEAM = 0.50      # -> +2.38 pts, steam True
NO_STEAM = 0.52   # -> +0.38 pts, steam False


def graded(tickets, money, soft_fair, num_bets=5000):
    splits = {
        'TeamA': {'tickets': tickets, 'money': money, 'odds': -110},
        'TeamB': {'tickets': 100 - tickets, 'money': 100 - money, 'odds': -110},
    }
    r = rs.grade_sharp(splits, {'TeamA': soft_fair}, num_bets=num_bets)
    return r['grade'] if r else None


print("grade_sharp ladder (gap = money% - tickets%, contrarian = tickets <= 35)")
# --- the bet set: contrarian + tail gap only -------------------------------------
check("gap 30, contrarian, steam        -> S", graded(20, 50, STEAM), 'S')
check("gap 30, contrarian, no steam     -> A", graded(20, 50, NO_STEAM), 'A')
check("gap 25 exactly, contrarian, steam-> S", graded(20, 45, STEAM), 'S')

# --- the v15 regression guards: these used to reach A ----------------------------
check("gap 30, tickets 45 (was A2)      -> B", graded(45, 75, STEAM), 'B')
check("gap 30, tickets 50 (dead band)   -> B", graded(50, 80, STEAM), 'B')
check("gap 40, tickets 40 (huge, public)-> B", graded(40, 80, STEAM), 'B')
check("gap 22, contrarian (was A3)      -> B", graded(25, 47, STEAM), 'B')

# --- unchanged lower rungs -------------------------------------------------------
check("gap 30, tickets 60 (public)      -> D", graded(60, 90, STEAM), 'D')
check("gap 15, contrarian               -> B", graded(20, 35, STEAM), 'B')
check("gap 10, contrarian               -> C", graded(20, 30, STEAM), 'C')
check("gap 7,  contrarian               -> D", graded(20, 27, STEAM), 'D')
check("gap 4  below floor               -> None", graded(20, 24, STEAM), None)

# --- thin-book cap still demotes the bet set -------------------------------------
check("gap 30, contrarian, steam, thin  -> B", graded(20, 50, STEAM, num_bets=900), 'B')

print("\nvalue gate: has_value must never fire on a started game")


def card(hours_from_now):
    """Minimal Odds API game shaped so the ML value gate passes on Bovada: Pinnacle
    devigs TeamA to ~0.538, and Bovada's +115 pays 2.15, for ~+15.7% EV — inside the
    sanity gate's [MIN_EV 3%, EV_CEILING 25%] band and over MIN_BOOKS."""
    from datetime import datetime, timedelta, timezone
    commence = (datetime.now(timezone.utc) + timedelta(hours=hours_from_now)).isoformat()
    books = []
    for title, a, b in [('Pinnacle', -120, +110), ('Bovada', +115, -160),
                        ('DraftKings', -118, +108), ('FanDuel', -119, +109)]:
        books.append({'title': title, 'key': title.lower(), 'markets': [
            {'key': 'h2h', 'outcomes': [{'name': 'TeamA', 'price': a},
                                        {'name': 'TeamB', 'price': b}]}]})
    g = {'id': 'evt1', 'commence_time': commence, 'away_team': 'TeamA',
         'home_team': 'TeamB', 'bookmakers': books}
    return rs.analyze_game(g, 'baseball', {}, {}, {})


pre = card(+6)
post = card(-2)
check("pregame (+6h): value flag raised", bool(pre['has_value']), True)
check("started (-2h): value flag suppressed", bool(post['has_value']), False)
check("started (-2h): value_play is None", post['value_play'], None)

print("\nprice shopping fields present on plays")
ml = [p for p in pre['plays'] if p['mkt'] == 'ML']
check("ML plays built", len(ml) > 0, True)
if ml:
    p = ml[0]
    check("best_price captured", p.get('best_price') is not None, True)
    check("avail_price captured", p.get('avail_price') is not None, True)
    check("avail_book in EXECUTABLE_BOOKS",
          p.get('avail_book') in rs.EXECUTABLE_BOOKS, True)
    check("shop_gain >= 0 (best cannot be worse than available)",
          p.get('shop_gain') is None or p['shop_gain'] >= -1e-9, True)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    raise SystemExit(1)
print("all tests passed")
