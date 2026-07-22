#!/usr/bin/env python3
"""
RidgeSeeker: Sports Edge Dashboard (formerly EdgeFinder)
=========================================================
Run this and it will:
  1. Fetch fresh odds, sharp money, and live game status for all in-season sports
  2. Run the full value + sharp-grade engine
  3. Save a timestamped copy into the "ridgeseeker_history" folder
  4. Open the dashboard in your browser

Run:  python ridgeseeker.py

Honest notes:
  - Sharp grades + live status are real for US team sports (MLB now; NFL/NBA/NHL/CFB/CBB in season).
  - World Cup & UFC have value scanning but no sharp data (Action Network covers US sports only).
  - Fair value is anchored to devigged Pinnacle (the sharpest book) when available,
    falling back to the multi-book no-vig median when it is not.
  - Lines move, so always re-check Bovada before betting.
"""

import json, urllib.request, urllib.error, statistics, os, sys, webbrowser, time
from datetime import datetime, timezone, timedelta

# ============================ CONFIG ============================
import os
# Key comes from the ODDS_KEY env var (GitHub secret) or, for local runs, a file named
# odds_key.txt sitting next to this script (gitignored, never committed). The key must
# NEVER be hardcoded here: this repo is public (GitHub Pages requires it on the free
# tier), so a hardcoded key is a stolen key.
ODDS_KEY = os.environ.get("ODDS_KEY", "")
if not ODDS_KEY:
    _kf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odds_key.txt")
    if os.path.exists(_kf):
        try: ODDS_KEY = open(_kf).read().strip()
        except Exception: pass
# Stamp every logged bet so history survives retunes and versions can be compared.
MODEL_VERSION = "2026-07-21.v14-suppressfix1"
HISTORY_FOLDER = "ridgeseeker_history"           # timestamped HTMLs saved here
# Auto-detect: are we running on GitHub's servers (cloud) or on a personal laptop?
CI = (os.environ.get("GITHUB_ACTIONS") == "true") or bool(os.environ.get("EDGEFINDER_CI"))
# Run mode: 'full' (default) = whole pipeline. 'close' = cheap close-capture run:
# fetches h2h only (2 API credits instead of 6), refreshes close prices on pending
# pregame plays, grades finished ones, and exits. It NEVER logs new plays (an
# h2h-only board would bias play selection) and does not rebuild the dashboard.
# Modes: full (fetch, log plays, everything) / observe (full pipeline but NEVER logs
# plays: for the pre-15:00 opener board, so extra observations sharpen closes and
# line-velocity data WITHOUT changing entry timing, which would be a silent model
# change) / close (h2h only, refresh closes + grade, cheapest).
RUN_MODE = os.environ.get("RS_MODE", "full").strip().lower()

# F26 (default OFF): named-bookmaker fetch. Up to 10 named books from ANY region
# bill as ONE region, so this curated list would cut a full run from 6 credits to
# 3 and a close run from 2 to 1. DO NOT enable until the owner's verification curl
# confirms (a) these keys carry baseball_mlb and (b) whether exchange h2h_lay rows
# bill as an extra market (docs price by unique markets IN THE RESPONSE).
# To enable: set env RS_BOOKMAKERS=1 or paste the list into BOOKMAKERS_PARAM.
# Enabling changes the consensus composition, so MODEL_VERSION auto-appends +bk10.
BOOKMAKERS_CURATED = "bovada,pinnacle,betfair_ex_eu,matchbook,betonlineag,lowvig,draftkings,fanduel,betmgm,marathonbet"
_bk_env=os.environ.get("RS_BOOKMAKERS","").strip().lower()
BOOKMAKERS_PARAM = BOOKMAKERS_CURATED if _bk_env not in ("","0","false","no","off") else ""
# Exchange books quote back/lay spread, not vig; matched by stable API key, not title
EXCHANGE_KEYS = {"betfair_ex_eu","betfair_ex_uk","betfair_ex_au","matchbook"}

# Prediction-market venues (owner bets both). LOG-ONLY capture per ML play; venue
# routing as a DECISION stays gated (FUTURE roadmap). These are the two venues where
# winning is allowed: no limits, no bans, real two-sided prices. Kalshi taker fee is
# the killer detail: 0.07 * price * (1-price) per contract, i.e. ~4% of stake on a
# 40c dog, which eats a 3% edge whole. Maker (limit) fills pay no fee. Polymarket
# charges no fee; overnight resting quotes are wide, so the mid is the signal.
KALSHI_SERIES = {'mlb':'KXMLBGAME','nfl':'KXNFLGAME','nba':'KXNBAGAME','nhl':'KXNHLGAME'}
POLY_TAGS = {'mlb':'mlb','nfl':'nfl','nba':'nba','nhl':'nhl','ncaaf':'cfb','ncaab':'cbb'}
KALSHI_MLB = {  # Odds API full name -> Kalshi ticker code (verify misses via alarm)
 'Arizona Diamondbacks':'AZ','Atlanta Braves':'ATL','Baltimore Orioles':'BAL','Boston Red Sox':'BOS',
 'Chicago Cubs':'CHC','Chicago White Sox':'CWS','Cincinnati Reds':'CIN','Cleveland Guardians':'CLE',
 'Colorado Rockies':'COL','Detroit Tigers':'DET','Houston Astros':'HOU','Kansas City Royals':'KC',
 'Los Angeles Angels':'LAA','Los Angeles Dodgers':'LAD','Miami Marlins':'MIA','Milwaukee Brewers':'MIL',
 'Minnesota Twins':'MIN','New York Mets':'NYM','New York Yankees':'NYY','Athletics':'ATH',
 'Oakland Athletics':'ATH','Philadelphia Phillies':'PHI','Pittsburgh Pirates':'PIT','San Diego Padres':'SD',
 'San Francisco Giants':'SF','Seattle Mariners':'SEA','St. Louis Cardinals':'STL','Tampa Bay Rays':'TB',
 'Texas Rangers':'TEX','Toronto Blue Jays':'TOR','Washington Nationals':'WSH'}

# Kalshi fee model, corrected per the 2026-07 research pass against the OFFICIAL
# schedule (kalshi.com/docs/kalshi-fee-schedule.pdf, June 2026): taker fee per order
# = ROUND UP(0.07 x contracts x P x (1-P)) to the cent. Maker fees now EXIST on many
# markets; third-party sources converge on ~25% of taker (0.0175 mult) where charged,
# and special events can carry a flat per-contract maker fee this model does NOT
# capture. We charge the maker fee by default: if a given market is actually 0%
# maker, our logged EV is UNDERSTATED, which is the safe direction. Per-order cent
# rounding matters at $10-20 stakes and is modeled. Assumption A11 tracks this.
KALSHI_TAKER_MULT = 0.07
KALSHI_MAKER_MULT = 0.0175
import math as _math
def kalshi_fee(price, contracts, mult):
    if not price or contracts<1: return 0.0
    # round before ceil: exact-cent boundaries float to 42.000000000000006 and
    # would overcharge a phantom cent
    return _math.ceil(round(mult*contracts*price*(1.0-price)*100.0,6))/100.0
def kalshi_ev(fair, price, contracts, mult):
    """EV per $1 of cost, fee-adjusted with per-order rounding. Payout = contracts x $1."""
    if not (fair and price and contracts>=1): return None
    cost=contracts*price + kalshi_fee(price, contracts, mult)
    return round(fair*contracts/cost - 1.0, 4)
# Polymarket: MLB/NFL/NBA/NHL game markets are fee-free (0% maker, taker rebates fund
# makers). NCAAB markets created after 2026-02-18 carry a 0.0625 x P x (1-P) taker
# fee; modeled when CBB activates.
POLY_TAKER_MULT = {'ncaab':0.0625}

# Stale-anchor discard (research: Pinnacle odds here are scraped and can lag their
# real trading prices; an "edge" against a stale quote is a phantom). Value recs
# anchored on a Pinnacle quote older than this many minutes are NOT logged and are
# labeled on the board. A10 mitigation.
PIN_STALE_MIN = 15

VENUE_GEO = {  # name -> (lat, lon, roof: open/fixed/retract). Weather-grid precision only.
 'Fenway Park':(42.346,-71.097,'open'),'Yankee Stadium':(40.829,-73.926,'open'),
 'Oriole Park at Camden Yards':(39.284,-76.622,'open'),'Tropicana Field':(27.768,-82.653,'fixed'),
 'George M. Steinbrenner Field':(27.980,-82.507,'open'),'Rogers Centre':(43.641,-79.389,'retract'),
 'Rate Field':(41.830,-87.634,'open'),'Guaranteed Rate Field':(41.830,-87.634,'open'),
 'Progressive Field':(41.496,-81.685,'open'),'Comerica Park':(42.339,-83.049,'open'),
 'Kauffman Stadium':(39.051,-94.480,'open'),'Target Field':(44.982,-93.278,'open'),
 'Angel Stadium':(33.800,-117.883,'open'),'Daikin Park':(29.757,-95.356,'retract'),
 'Minute Maid Park':(29.757,-95.356,'retract'),'Sutter Health Park':(38.580,-121.513,'open'),
 'T-Mobile Park':(47.591,-122.332,'retract'),'Globe Life Field':(32.747,-97.081,'retract'),
 'Truist Park':(33.890,-84.468,'open'),'loanDepot park':(25.778,-80.220,'retract'),
 'Citi Field':(40.757,-73.846,'open'),'Citizens Bank Park':(39.906,-75.166,'open'),
 'Nationals Park':(38.873,-77.007,'open'),'Wrigley Field':(41.948,-87.655,'open'),
 'Great American Ball Park':(39.097,-84.507,'open'),'PNC Park':(40.447,-80.006,'open'),
 'Busch Stadium':(38.623,-90.193,'open'),'American Family Field':(43.028,-87.971,'retract'),
 'Chase Field':(33.445,-112.067,'retract'),'Coors Field':(39.756,-104.994,'open'),
 'Dodger Stadium':(34.074,-118.240,'open'),'Petco Park':(32.707,-117.157,'open'),
 'Oracle Park':(37.778,-122.389,'open')}

PARK_RF_APPROX = {  # APPROXIMATE run factors (100=neutral). Replace with an official
 # Statcast park-factor export before using in any decision; logged as *_approx.
 'Coors Field':113,'Fenway Park':108,'Great American Ball Park':107,'Yankee Stadium':104,
 'Citizens Bank Park':104,'Chase Field':103,'Rogers Centre':102,'Wrigley Field':102,
 'Kauffman Stadium':101,'Truist Park':101,'Rate Field':101,'Guaranteed Rate Field':101,
 'American Family Field':101,'Nationals Park':100,'Oriole Park at Camden Yards':100,
 'Target Field':99,'Progressive Field':99,'Daikin Park':99,'Minute Maid Park':99,
 'Angel Stadium':98,'Dodger Stadium':98,'Globe Life Field':98,'Comerica Park':97,
 'Busch Stadium':97,'PNC Park':97,'loanDepot park':97,'Citi Field':96,'Petco Park':96,
 'Oracle Park':95,'T-Mobile Park':93,'Tropicana Field':98,'Sutter Health Park':105,
 'George M. Steinbrenner Field':104}
if BOOKMAKERS_PARAM: MODEL_VERSION += "+bk10"   # curated-book consensus is a different model
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Sports to scan: (tab_key, odds_api_key, sport_kind, action_network_league_or_None)
# Multi-sport registry (2026-07-04). Every entry: dashboard key, Odds API sport key,
# kind (drives spread label + grading), Action Network slug (live-verified for all
# six), label, active months UTC (season window: OFF-SEASON SPORTS ARE NEVER FETCHED,
# zero credits), enabled flag. Preseason months excluded on purpose (garbage lines).
# CREDIT REALITY (see AUDIT_TODO F38): 5 overlapping sports in Oct-Nov at the proper
# cadence needs the $30/mo 20K plan. The free 500 carries MLB-only summer fine.
# Sharp thresholds for new sports use _default until each earns its own calibration;
# every play carries 'sport', and the pre-registered protocol applies PER SPORT.
# RS_SPORTS env (comma keys) overrides windows/flags for testing or manual runs.
SPORTS = [
    {'key':'mlb',  'odds':'baseball_mlb',          'kind':'baseball',         'an':'mlb',  'label':'MLB',  'months':{3,4,5,6,7,8,9,10,11}, 'enabled':True},
    {'key':'nfl',  'odds':'americanfootball_nfl',  'kind':'americanfootball', 'an':'nfl',  'label':'NFL',  'months':{9,10,11,12,1,2},      'enabled':True},
    {'key':'nba',  'odds':'basketball_nba',        'kind':'basketball',       'an':'nba',  'label':'NBA',  'months':{10,11,12,1,2,3,4,5,6},'enabled':True},
    {'key':'nhl',  'odds':'icehockey_nhl',         'kind':'icehockey',        'an':'nhl',  'label':'NHL',  'months':{10,11,12,1,2,3,4,5,6},'enabled':True},
    {'key':'ncaaf','odds':'americanfootball_ncaaf','kind':'americanfootball', 'an':'ncaaf','label':'CFB',  'months':{8,9,10,11,12,1},      'enabled':True},
    {'key':'ncaab','odds':'basketball_ncaab',      'kind':'basketball',       'an':'ncaab','label':'CBB',  'months':{11,12,1,2,3,4},       'enabled':True},
    # WNBA: feed live-verified, in season NOW. Disabled until F26 halves per-sport
    # cost; enabling it today on the free tier overruns the monthly budget.
    {'key':'wnba', 'odds':'basketball_wnba',       'kind':'basketball',       'an':'wnba', 'label':'WNBA', 'months':{5,6,7,8,9,10},        'enabled':False},
]

def active_sports():
    ov=os.environ.get("RS_SPORTS","").strip().lower()
    if ov:
        want={k.strip() for k in ov.split(',') if k.strip()}
        return [s for s in SPORTS if s['key'] in want]
    m=datetime.now(timezone.utc).month
    return [s for s in SPORTS if s['enabled'] and m in s['months']]

# Your Odds API plan's monthly credits; used only to WARN when the active-sport
# schedule projects over budget. Set to 20000 after upgrading.
PLAN_CREDITS = 500

# Per-sport sharp-grade thresholds (gap = money% minus tickets% on the sharp side).
# Anchored to the real MLB gap distribution: median ~9, 75th pctile ~15, 90th ~22.
# So a +15 gap is a B (good, ordinary), NOT an A. A/S are reserved for the true tail.
GRADE_THRESHOLDS = {
    'baseball': {'S':25, 'A':20, 'B':13, 'C':9, 'D':6},
    # defaults for other sports until we calibrate them with their own data:
    '_default': {'S':25, 'A':20, 'B':13, 'C':9, 'D':6},
}

# Sanity gate
MIN_EV, LONGSHOT_CAP, EV_CEILING, MIN_BOOKS = 0.03, 500, 0.25, 3

# Your unit size in dollars. Change this when you level up ($10 -> $20 -> $50).
# The app tracks your results and tells you when you've earned the next level.
UNIT_DOLLARS = 10
BANKROLL = None   # optional: set your total betting bankroll for level-up safety checks
# Daily exposure guidance. Bets on different games are independent, but 6 dogs on one
# slate is still 6-9u of one-day variance (up to ~10-20% of a small bankroll). Plays
# past this are still LOGGED (the tracker wants all data while paper trading); the
# dashboard just flags the total so real-money days get prioritized by EV.
MAX_DAILY_UNITS = 6.0

# ============================ HELPERS ============================
import ssl

_SSL_TIERS = None
def _ssl_tiers():
    """Ordered list of connection strategies, tried in sequence until one works.
    Designed to handle: normal machines, antivirus/proxy TLS interception (needs the
    system/local cert store), and handshake failures (needs widened ciphers)."""
    tiers = []
    # Tier 0: default context honoring the OS / environment cert store (SSL_CERT_FILE etc.)
    try:
        tiers.append(ssl.create_default_context())
    except Exception:
        pass
    # Tier 1: certifi bundle + widened ciphers (fixes handshake failures)
    try:
        import certifi
        c1 = ssl.create_default_context(cafile=certifi.where())
        for cc in ('DEFAULT@SECLEVEL=1', 'ALL:@SECLEVEL=1'):
            try: c1.set_ciphers(cc); break
            except Exception: continue
        tiers.append(c1)
    except Exception:
        pass
    # Tier 2: system store + widened ciphers
    try:
        c2 = ssl.create_default_context()
        for cc in ('DEFAULT@SECLEVEL=1', 'ALL:@SECLEVEL=1'):
            try: c2.set_ciphers(cc); break
            except Exception: continue
        tiers.append(c2)
    except Exception:
        pass
    # Tier 3 (last resort): no verification (only reached if everything above fails).
    # This lets the tool work behind aggressive AV/proxy interception. It still encrypts;
    # it just doesn't verify the cert chain (acceptable for reading public odds data).
    try:
        c3 = ssl.create_default_context()
        c3.check_hostname = False
        c3.verify_mode = ssl.CERT_NONE
        for cc in ('DEFAULT@SECLEVEL=1', 'ALL:@SECLEVEL=1'):
            try: c3.set_ciphers(cc); break
            except Exception: continue
        tiers.append(c3)
    except Exception:
        pass
    return tiers

_SSL_WORKING_IDX = None  # index of the tier that worked
def gj(url, t=40, retries=3):
    global _SSL_TIERS, _SSL_WORKING_IDX
    if _SSL_TIERS is None:
        _SSL_TIERS = _ssl_tiers()
    # try the known-working tier first, then the rest in order
    idxs = list(range(len(_SSL_TIERS)))
    if _SSL_WORKING_IDX is not None:
        idxs = [_SSL_WORKING_IDX] + [j for j in idxs if j != _SSL_WORKING_IDX]
    last = None
    for i in range(retries):
        for j in idxs:
            ctx = _SSL_TIERS[j]
            try:
                resp = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t, context=ctx)
                _SSL_WORKING_IDX = j
                return json.load(resp)
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (403, 429): time.sleep(2 * (i + 1)); break
                raise
            except ssl.SSLError as e:
                last = e; continue   # next tier
            except Exception as e:
                last = e; break      # network/timeout, wait then retry
        time.sleep(1)
    if last: raise last

def am2prob(o): o=float(o); return (-o)/(-o+100) if o<0 else 100/(o+100)
def am2dec(o):  o=float(o); return 1+(o/100 if o>0 else 100/(-o))
def prob2am(p):
    if p is None or p<=0 or p>=1: return None
    return round(-100*p/(1-p)) if p>0.5 else round(100*(1-p)/p)
def _power_k(qa, qb):
    """Solve qa**k + qb**k = 1 by bisection (k >= 1 whenever there is vig)."""
    lo, hi = 1.0, 3.0
    while qa**hi + qb**hi > 1 and hi < 50: hi *= 2
    for _ in range(60):
        mid=(lo+hi)/2
        if qa**mid + qb**mid > 1: lo=mid
        else: hi=mid
    return (lo+hi)/2
def fair_pair(pa, pb):
    """No-vig fair probability of side A from a two-way pair of American prices,
    using the POWER method rather than proportional scaling. Proportional devig
    systematically overstates the fair probability of the longer-priced side
    (favorite-longshot bias), which inflates apparent EV on exactly the underdog
    bets this tool prefers. Power devig removes most of that bias."""
    qa, qb = am2prob(pa), am2prob(pb)
    if qa<=0 or qb<=0: return None
    if qa+qb<=1: return qa/(qa+qb)   # degenerate no-vig or negative-vig pair
    return qa**_power_k(qa, qb)
def novig(pairs):
    """Returns (fair_power_median, fair_proportional_median, n_books). The power
    number drives decisions; the proportional number is logged alongside every play
    so the two methods can be compared on real results later."""
    if not pairs: return None, None, 0
    pw=[fair_pair(a,b) for a,b in pairs]
    pw=[p for p in pw if p is not None]
    pm=[am2prob(a)/(am2prob(a)+am2prob(b)) for a,b in pairs]
    if not pw: return None, (statistics.median(pm) if pm else None), 0
    return statistics.median(pw), statistics.median(pm), len(pw)
def novig3(triples):
    if not triples: return None, 0
    aw,hm,dr=[],[],[]
    for a,h,d in triples:
        t=am2prob(a)+am2prob(h)+am2prob(d)
        aw.append(am2prob(a)/t); hm.append(am2prob(h)/t); dr.append(am2prob(d)/t)
    return {'away':statistics.median(aw),'home':statistics.median(hm),'draw':statistics.median(dr)}, len(aw)
def gate(price, ev, nb):
    return price is not None and ev is not None and price<=LONGSHOT_CAP and ev<=EV_CEILING and nb>=MIN_BOOKS and ev>=MIN_EV

SPREAD_LABEL={'baseball':'Run Line','soccer':'Asian Handicap','americanfootball':'Spread','basketball':'Spread','icehockey':'Puck Line','mma':None}


# ============================ DATA FETCH ============================
def fetch_odds(sport_key, markets="h2h,spreads,totals"):
    # Credit cost = number of markets x number of regions. Full run: 3 x 2 = 6.
    # Close-capture run passes markets="h2h": 1 x 2 = 2.
    src=(f"bookmakers={BOOKMAKERS_PARAM}" if BOOKMAKERS_PARAM else "regions=us,eu")
    url=f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={ODDS_KEY}&{src}&markets={markets}&oddsFormat=american"
    try: return gj(url)
    except Exception as e: print(f"    ! odds fetch failed for {sport_key}: {e}"); return []

def _an_same_game(entry, commence):
    """F45: an AN entry only belongs to an odds-API game if their start times sit
    within 12h. Same-series matchups repeat (away,home) on consecutive days and the
    evening board lists both; without this check tomorrow's card inherits today's
    splits, status, and sharp grade."""
    try:
        a=datetime.fromisoformat(str(entry.get('an_start')).replace('Z','+00:00'))
        c=datetime.fromisoformat(str(commence).replace('Z','+00:00'))
        return abs((a-c).total_seconds())<12*3600
    except Exception:
        return True   # missing timestamps: keep old behavior rather than dropping data

def fetch_sharp_and_status(league):
    """Returns (sharp_map, status_map). sharp_map keyed (away,home)->{splits,num_bets}; status_map->{state,display}"""
    if not league: return {}, {}, None
    try: raw=gj(f"https://api.actionnetwork.com/web/v2/scoreboard/publicbetting/{league}")
    except Exception as e: print(f"    ! sharp/status fetch failed for {league}: {e}"); return {}, {}, None
    sharp, status = {}, {}
    for g in raw.get('games', []):
        def nm(tid):
            for t in g.get('teams', []):
                if t['id']==tid: return t.get('full_name')
        a,h=nm(g['away_team_id']),nm(g['home_team_id'])
        # status
        st=g.get('status'); disp=g.get('status_display')
        if st=='inprogress': state='live'
        elif st in ('complete','closed'): state='final'
        elif st=='weatherdelay': state='delay'
        else: state='scheduled'
        status[(a,h)]={'state':state,'display':disp,'an_start':g.get('start_time')}
        # sharp splits
        sd={}
        for bid,mk in g.get('markets',{}).items():
            for o in (mk.get('event',{}).get('moneyline',[]) or []):
                bi=o.get('bet_info') or {}; tk=(bi.get('tickets') or {}).get('percent'); mn=(bi.get('money') or {}).get('percent')
                side=o.get('side'); ov=o.get('odds')
                if side in ('home','away') and (tk or mn):
                    key=h if side=='home' else a
                    sd.setdefault(key,{'tk':[],'mn':[],'od':[]})
                    if tk: sd[key]['tk'].append(tk)
                    if mn: sd[key]['mn'].append(mn)
                    if ov: sd[key]['od'].append(ov)
        # Source sweep (roadmap): AN carries per-book pregame ML odds in the SAME free
        # payload (book ids observed: 15/30/68/69/71). Capture-or-lose; book-id
        # mapping and timestamp semantics get proven offline (F28/F36) before any
        # metric uses these. is_live rows are excluded.
        an_ml={}
        for bid,mk in g.get('markets',{}).items():
            for o in (mk.get('event',{}).get('moneyline',[]) or []):
                if o.get('is_live'): continue
                sde=o.get('side'); ov=o.get('odds')
                if sde in ('home','away') and ov:
                    an_ml.setdefault(str(bid),{})[sde]=ov
        if len(sd)==2:
            sharp[(a,h)]={'splits':{k:{'tickets':statistics.mean(v['tk']) if v['tk'] else 0,
                                       'money':statistics.mean(v['mn']) if v['mn'] else 0,
                                       'odds':statistics.median(v['od']) if v['od'] else None} for k,v in sd.items()},
                          'num_bets':g.get('num_bets'),'an_ml':an_ml or None,'an_start':g.get('start_time')}
    return sharp, status, raw

def fetch_mlb_context():
    """F29, LOG-ONLY features from the free keyless MLB Stats API: probable pitchers
    (ids logged so handedness and every career stat stay reconstructable forever),
    park, day/night, doubleheader flag, and mlb_gamePk, the master join key into the
    entire MLB stats universe. Keyed by (away_full_name, home_full_name), the same
    full-name style the Odds API uses. A join miss is non-fatal (fields stay None)
    and is counted so silent decay is visible (A8 discipline)."""
    try:
        day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
        d=gj(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={day}&hydrate=probablePitcher,weather")
        out={}
        for dt in (d or {}).get('dates',[]):
            for g in dt.get('games',[]):
                aw=g['teams']['away']['team']['name']; hm=g['teams']['home']['team']['name']
                pa=g['teams']['away'].get('probablePitcher') or {}
                ph=g['teams']['home'].get('probablePitcher') or {}
                wx=g.get('weather') or {}
                out[(aw,hm)]={
                    'mlb_gamePk':g.get('gamePk'),
                    'venue':(g.get('venue') or {}).get('name'),
                    'day_night':g.get('dayNight'),
                    'double_header':g.get('doubleHeader'),
                    'probable_away':pa.get('fullName'),'probable_away_id':pa.get('id'),
                    'probable_home':ph.get('fullName'),'probable_home_id':ph.get('id'),
                    'wx_condition':wx.get('condition'),'wx_temp_f':wx.get('temp'),'wx_wind':wx.get('wind'),
                }
        return out
    except Exception as e:
        print(f"    ! MLB Stats context unavailable this run: {e}")
        return {}

def fetch_prediction_markets(sport_keys):
    """LOG-ONLY (F39). Free keyless reads of Kalshi + Polymarket game-winner quotes
    for the active sports. Returns (kalshi_map, poly_map, counts):
      kalshi_map[frozenset({CODE_A,CODE_B})] -> list of {'teams':{code:{'bid','ask','ticker'}}, 'close':iso}
      poly_map[(away_full, home_full)] -> {team_full:{'mid','bid','ask'}}
    Join misses are counted upstream and alarmed, never fatal (A8 discipline)."""
    kal={}; pol={}; kn=0; pn=0
    for sk in sport_keys:
        ser=KALSHI_SERIES.get(sk)
        if ser:
            try:
                d=gj(f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={ser}&status=open&limit=1000")
                ev={}
                for m in d.get('markets',[]):
                    et=m.get('event_ticker') or ''
                    codes=et.split('-')[-1] if '-' in et else ''
                    yes=(m.get('ticker') or '').split('-')[-1]
                    try:
                        bid=float(m.get('yes_bid_dollars') or 0) or None
                        ask=float(m.get('yes_ask_dollars') or 0) or None
                    except Exception: bid=ask=None
                    if not yes: continue
                    ev.setdefault(et,{'teams':{},'close':m.get('close_time'),'codes':codes})
                    ev[et]['teams'][yes]={'bid':bid,'ask':ask,'ticker':m.get('ticker')}
                for et,e in ev.items():
                    ks=frozenset(e['teams'].keys())
                    if len(ks)==2:
                        kal.setdefault(ks,[]).append(e); kn+=1
            except Exception as e:
                print(f"    ! Kalshi fetch failed ({ser}): {e}")
        tag=POLY_TAGS.get(sk)
        if tag:
            try:
                # NOTE: event startDate is CREATION time (markets open days early),
                # so filter on the moneyline market's own gameStartTime instead.
                evs=[]
                for off in (0,250):
                    d=gj(f"https://gamma-api.polymarket.com/events?closed=false&tag_slug={tag}&limit=250&offset={off}")
                    page=d if isinstance(d,list) else d.get('events',d.get('data',[]))
                    if not page: break
                    evs+=page
                    if len(page)<250: break
                now=datetime.now(timezone.utc)
                for e in (evs or []):
                    title=e.get('title') or ''
                    # main game event title is exactly "Away vs. Home"; derivative
                    # events append " - Player Props" / " - First 5 Innings Winner"
                    # and must never masquerade as the game moneyline
                    if ' vs. ' not in title or ' - ' in title: continue
                    for mq in e.get('markets',[]):
                        if mq.get('sportsMarketType')!='moneyline': continue
                        try:
                            outs=json.loads(mq.get('outcomes') or '[]')
                            prs=[float(x) for x in json.loads(mq.get('outcomePrices') or '[]')]
                        except Exception: continue
                        if len(outs)!=2 or len(prs)!=2: continue
                        gst=str(mq.get('gameStartTime') or '')
                        try:
                            gdt=datetime.fromisoformat(gst.replace(' ','T').replace('+00','+00:00')) if gst else None
                        except Exception: gdt=None
                        if gdt is None or not (-6*3600 < (gdt-now).total_seconds() < 40*3600): continue
                        bb=mq.get('bestBid'); ba=mq.get('bestAsk')
                        rec={outs[0]:{'mid':prs[0],'bid':bb,'ask':ba},
                             outs[1]:{'mid':prs[1],
                                      'bid':(round(1-ba,3) if isinstance(ba,(int,float)) else None),
                                      'ask':(round(1-bb,3) if isinstance(bb,(int,float)) else None)}}
                        pol[(outs[0],outs[1])]=rec; pol[(outs[1],outs[0])]=rec; pn+=1
                        break
            except Exception as e:
                print(f"    ! Polymarket fetch failed ({tag}): {e}")
    return kal,pol,{'kalshi_events':kn,'poly_games':pn}

def fetch_park_weather(venue_commence):
    """Feature roadmap #3, LOG-ONLY. One multi-point open-meteo call (free, keyless)
    for every distinct outdoor/retractable park with a game today; returns
    venue -> {om_temp_f, om_wind_kph, om_wind_dir_deg} at each game's start hour UTC.
    Wind-out/wind-in needs a park-orientation azimuth table; deliberately deferred
    (FUTURE.md) rather than shipping half-guessed bearings. Raw speed/direction plus
    the roof flag are the honest capture."""
    try:
        items=[(v,ct) for v,ct in venue_commence.items() if v in VENUE_GEO]
        if not items: return {}
        lats=",".join(str(VENUE_GEO[v][0]) for v,_ in items)
        lons=",".join(str(VENUE_GEO[v][1]) for v,_ in items)
        d=gj(f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}"
             f"&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&forecast_days=2&timezone=UTC")
        blocks=d if isinstance(d,list) else [d]
        out={}
        for (v,ct),blk in zip(items,blocks):
            try:
                hh=str(ct)[:13]+":00"
                times=blk['hourly']['time']; i=times.index(hh) if hh in times else None
                if i is None: continue
                out[v]={'om_temp_f':round(blk['hourly']['temperature_2m'][i]*9/5+32,1),
                        'om_wind_kph':round(blk['hourly']['wind_speed_10m'][i],1),
                        'om_wind_dir_deg':blk['hourly']['wind_direction_10m'][i]}
            except Exception: continue
        return out
    except Exception as e:
        print(f"    ! open-meteo unavailable this run: {e}")
        return {}

def detect_scratches(mlb_ctx, path):
    """Feature roadmap #2, LOG-ONLY + alarm. Diffs today's probable-pitcher ids
    against the previous run's stored set (per gamePk, same date only). A probable
    change between boards is exactly the news window where a retail book lags
    (AUDIT_TODO F30). Returns {gamePk: 'away'/'home'/'both'}."""
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d')
    cur={str(v['mlb_gamePk']):{'a':v.get('probable_away_id'),'h':v.get('probable_home_id'),
         'an':v.get('probable_away'),'hn':v.get('probable_home')}
         for v in mlb_ctx.values() if v.get('mlb_gamePk')}
    prev={}
    try:
        if os.path.exists(path):
            old=json.load(open(path))
            if old.get('date')==today: prev=old.get('probables',{})
    except Exception: prev={}
    scratches={}
    for pk,c in cur.items():
        p=prev.get(pk)
        if not p: continue
        a_ch=(p.get('a') and c.get('a') and p['a']!=c['a'])
        h_ch=(p.get('h') and c.get('h') and p['h']!=c['h'])
        if a_ch or h_ch:
            scratches[pk]='both' if (a_ch and h_ch) else ('away' if a_ch else 'home')
            print(f"    ! probable-pitcher CHANGE gamePk {pk}: "
                  f"{'away '+str(p.get('an'))+' -> '+str(c.get('an')) if a_ch else ''}"
                  f"{' ' if a_ch and h_ch else ''}"
                  f"{'home '+str(p.get('hn'))+' -> '+str(c.get('hn')) if h_ch else ''}")
    try: json.dump({'date':today,'probables':cur}, open(path,'w'))
    except Exception: pass
    return scratches

def fetch_scores_for_dates(league, days_back=3):
    """Fetch the Action Network scoreboard for each of the past N days (free, no auth).
    Why: the current-day scoreboard rolls over each morning, so a night game that ends
    after the last run of the day never appears final to this tool and its bets stay
    pending forever (this happened to a real logged play). Backfilling a few days
    closes that hole and also covers days the tool simply did not run."""
    raws=[]
    if not league: return raws
    for d in range(1, days_back+1):
        day=(datetime.now(timezone.utc)-timedelta(days=d)).strftime('%Y%m%d')
        try:
            raws.append(gj(f"https://api.actionnetwork.com/web/v2/scoreboard/publicbetting/{league}?date={day}"))
        except Exception as e:
            print(f"    ! score backfill failed for {league} {day}: {e}")
    return raws

def pin_pair(book_map, a, b):
    """Return Pinnacle's (price_a, price_b) if Pinnacle quotes both sides, else None."""
    p=book_map.get('Pinnacle')
    if p and a in p and b in p: return (p[a], p[b])
    return None

def soft_fair_map(odds):
    """Fair-prob map feeding STEAM detection only. Deliberately still proportional
    devig: the 1.5pt steam threshold was tuned around proportional numbers (F14).
    Do not switch this to the power method without retuning the threshold on data."""
    m={}
    for g in odds:
        a,h=g['away_team'],g['home_team']; rows=[]
        for b in g['bookmakers']:
            for mk in b['markets']:
                if mk['key']=='h2h':
                    d={o['name']:o['price'] for o in mk['outcomes']}
                    if a in d and h in d: rows.append((b['title'],d))
        fg={}
        pin=next((d for t,d in rows if t=='Pinnacle'), None)
        for s in (a,h):
            o=h if s==a else a
            if pin:
                fg[s]=am2prob(pin[s])/(am2prob(pin[s])+am2prob(pin[o]))
            else:
                ps=[am2prob(d[s])/(am2prob(d[s])+am2prob(d[o])) for t,d in rows]
                if ps: fg[s]=statistics.median(ps)
        m[(a,h)]=fg
    return m

# ============================ ENGINE ============================
def analyze_game(g, sport_kind, sharp_map, status_map, soft_fair):
    away,home=g['away_team'],g['home_team']
    ml={}; spr={}; tot={}; ex_back={}; ex_lay={}
    pin_lu=None
    for b in g['bookmakers']:
        if b.get('key')=='pinnacle': pin_lu=b.get('last_update')
        is_ex=b.get('key') in EXCHANGE_KEYS   # exchanges quote spread, not vig (F27/A9)
        for m in b['markets']:
            if m['key']=='h2h':
                d={o['name']:o['price'] for o in m['outcomes']}
                if is_ex: ex_back.update({k:v for k,v in d.items() if k not in ex_back})
                else: ml[b['title']]=d
            elif m['key']=='h2h_lay':
                if is_ex: ex_lay.update({o['name']:o['price'] for o in m['outcomes'] if o['name'] not in ex_lay})
            elif m['key']=='spreads': spr[b['title']]={o['name']:{'pt':o.get('point'),'pr':o['price']} for o in m['outcomes']}
            elif m['key']=='totals': tot[b['title']]={o['name']:{'pt':o.get('point'),'pr':o['price']} for o in m['outcomes']}
    bov_ml=ml.get('Bovada',{})
    def bo_best(mkt_dict, side, point=None):
        # Feature roadmap #1, LOG-ONLY: BetOnline.ag price for our side (second
        # executable offshore venue) and the best vigged-book price at Bovada's
        # point. Exchanges are already excluded from these dicts (F27), so "best"
        # means best actually-bettable sportsbook price. Price shopping is worth
        # roughly 0.5-1.5% EV per bet it improves, with zero model risk.
        bo=None; best=None; bb=None
        for t,d in mkt_dict.items():
            v=d.get(side)
            if v is None: continue
            pr=v if not isinstance(v,dict) else (v.get('pr') if (point is None or v.get('pt')==point) else None)
            if pr is None: continue
            if t=='BetOnline.ag': bo=pr
            if best is None or pr>best: best,bb=pr,t
        return bo,best,bb
    def ex_mid(side):
        # Vig-free true-market fair prob: midpoint of back/lay implied probabilities.
        # LOG-ONLY (F27): never drives decisions until compared against the Pinnacle
        # anchor on real graded results. Requires both sides of the quote.
        bk,ly=ex_back.get(side),ex_lay.get(side)
        if bk is None or ly is None: return None
        try: return round((am2prob(bk)+am2prob(ly))/2,4)
        except Exception: return None
    three_way=(sport_kind=='soccer')
    plays=[]
    # ML
    if three_way:
        triples=[(dd[away],dd[home],dd.get('Draw')) for dd in ml.values() if away in dd and home in dd and 'Draw' in dd]
        fair,nb=novig3(triples)
        if fair:
            fmap={away:fair['away'],home:fair['home'],'Draw':fair['draw']}
            for s in (away,home,'Draw'):
                if s in bov_ml:
                    ev=fmap[s]*am2dec(bov_ml[s])-1
                    plays.append({'mkt':'ML','side':s,'point':None,'price':bov_ml[s],'fair':fmap[s],'ev':ev,'nb':nb,'pass':gate(bov_ml[s],ev,nb)})
    else:
        pinp=pin_pair(ml,away,home)
        for s in (away,home):
            pairs=[(dd[s],dd[home if s==away else away]) for dd in ml.values() if away in dd and home in dd]
            f,fm,n=novig(pairs); anc='consensus'; pp=po=None
            if pinp:
                pa,pb=(pinp[0],pinp[1]) if s==away else (pinp[1],pinp[0])
                f=fair_pair(pa,pb); fm=am2prob(pa)/(am2prob(pa)+am2prob(pb)); anc='pinnacle'; pp,po=pa,pb
            if f and s in bov_ml:
                ev=f*am2dec(bov_ml[s])-1
                _bo,_bp,_bb=bo_best(ml,s)
                plays.append({'mkt':'ML','side':s,'point':None,'price':bov_ml[s],'fair':f,'fair_mult':fm,'ev':ev,'nb':n,'anchor':anc,'pin_price':pp,'pin_opp':po,
                              'ex_back':ex_back.get(s),'ex_lay':ex_lay.get(s),'ex_mid':ex_mid(s),
                              'bo_price':_bo,'best_price':_bp,'best_book':_bb,'pass':gate(bov_ml[s],ev,n)})
    # Spread (sport-aware) with consensus-favorite data-error guard
    spread_label=SPREAD_LABEL.get(sport_kind); rl_dataerror=False
    bov_spr=spr.get('Bovada',{})
    if spread_label and bov_spr:
        bov_fav=bov_favpt=bov_fav_pr=bov_dog=bov_dogpt=bov_dog_pr=None
        for nm2,info in bov_spr.items():
            if info['pt'] is not None and info['pt']<0: bov_fav,bov_favpt,bov_fav_pr=nm2,info['pt'],info['pr']
            elif info['pt'] is not None and info['pt']>0: bov_dog,bov_dogpt,bov_dog_pr=nm2,info['pt'],info['pr']
        negc={}
        for bk,d2 in spr.items():
            for nm2,info in d2.items():
                if info['pt'] is not None and info['pt']<0: negc[nm2]=negc.get(nm2,0)+1
        consensus_fav=max(negc,key=negc.get) if negc else None
        if bov_fav and consensus_fav and bov_fav!=consensus_fav: rl_dataerror=True
        if not rl_dataerror and bov_fav and bov_favpt is not None:
            pairs=[]; pinsp=None
            for bk,d2 in spr.items():
                fp=dp=None
                for nm2,info in d2.items():
                    if nm2==bov_fav and info['pt']==bov_favpt: fp=info['pr']
                    if nm2!=bov_fav and info['pt']==-bov_favpt: dp=info['pr']
                if fp and dp:
                    pairs.append((fp,dp))
                    if bk=='Pinnacle': pinsp=(fp,dp)
            f,fm,n=novig(pairs); anc='consensus'
            if pinsp:
                f=fair_pair(pinsp[0],pinsp[1]); fm=am2prob(pinsp[0])/(am2prob(pinsp[0])+am2prob(pinsp[1])); anc='pinnacle'
            if f:
                ev=f*am2dec(bov_fav_pr)-1
                _bo,_bp,_bb=bo_best(spr,bov_fav,bov_favpt)
                plays.append({'mkt':'SPR','side':bov_fav,'point':bov_favpt,'price':bov_fav_pr,'fair':f,'fair_mult':fm,'ev':ev,'nb':n,'anchor':anc,'pin_price':(pinsp[0] if pinsp else None),'pin_opp':(pinsp[1] if pinsp else None),'bo_price':_bo,'best_price':_bp,'best_book':_bb,'pass':gate(bov_fav_pr,ev,n),'label':spread_label})
                if bov_dog and bov_dog_pr:
                    evd=(1-f)*am2dec(bov_dog_pr)-1
                    _bo,_bp,_bb=bo_best(spr,bov_dog,bov_dogpt)
                    plays.append({'mkt':'SPR','side':bov_dog,'point':bov_dogpt,'price':bov_dog_pr,'fair':1-f,'fair_mult':(1-fm) if fm is not None else None,'ev':evd,'nb':n,'anchor':anc,'pin_price':(pinsp[1] if pinsp else None),'pin_opp':(pinsp[0] if pinsp else None),'bo_price':_bo,'best_price':_bp,'best_book':_bb,'pass':gate(bov_dog_pr,evd,n),'label':spread_label})
    # Totals
    bov_t=tot.get('Bovada',{})
    if 'Over' in bov_t:
        line=bov_t['Over']['pt']
        pairs=[]; pint=None
        for bk,d2 in tot.items():
            if 'Over' in d2 and 'Under' in d2 and d2['Over']['pt']==line:
                pairs.append((d2['Over']['pr'],d2['Under']['pr']))
                if bk=='Pinnacle': pint=(d2['Over']['pr'],d2['Under']['pr'])
        f,fm,n=novig(pairs); anc='consensus'
        if pint:
            f=fair_pair(pint[0],pint[1]); fm=am2prob(pint[0])/(am2prob(pint[0])+am2prob(pint[1])); anc='pinnacle'
        if f:
            for s,fp,fmp,pr,pnp,pno in [('Over',f,fm,bov_t['Over']['pr'],(pint[0] if pint else None),(pint[1] if pint else None)),
                                        ('Under',1-f,(1-fm) if fm is not None else None,bov_t['Under']['pr'],(pint[1] if pint else None),(pint[0] if pint else None))]:
                ev=fp*am2dec(pr)-1
                _bo,_bp,_bb=bo_best(tot,s,line)
                plays.append({'mkt':'TOT','side':s,'point':line,'price':pr,'fair':fp,'fair_mult':fmp,'ev':ev,'nb':n,'anchor':anc,'pin_price':pnp,'pin_opp':pno,'bo_price':_bo,'best_price':_bp,'best_book':_bb,'pass':gate(pr,ev,n)})
    passed=[p for p in plays if p['pass']]
    best=max(passed,key=lambda x:x['ev']) if passed else None
    sm=sharp_map.get((away,home))
    if sm is not None and isinstance(sm,dict) and sm.get('an_start') is not None and not _an_same_game(sm, g['commence_time']):
        sm=None   # F45
    # F23 capture-or-lose: per-book h2h prices + dispersion, persisted in snapshots.
    # Compact on purpose (h2h only): the fields that make bookmaker-disagreement
    # features and per-bet EV confidence intervals possible later. Kept off the
    # betlog to respect snapshot growth limits (F13).
    books_h2h={t:{k:v for k,v in d.items() if k in (away,home)} for t,d in ml.items() if away in d and home in d}
    disp=None
    try:
        import statistics as _st
        pa=[am2prob(d[away])/(am2prob(d[away])+am2prob(d[home])) for d in books_h2h.values()]
        if len(pa)>=2: disp=round(_st.pstdev(pa),4)
    except Exception: disp=None
    pin_age_min=None
    try:
        if pin_lu:
            pin_age_min=round((datetime.now(timezone.utc)-datetime.fromisoformat(str(pin_lu).replace('Z','+00:00'))).total_seconds()/60.0,1)
    except Exception: pin_age_min=None
    return {'away':away,'home':home,'time':g['commence_time'],'event_id':g.get('id'),'plays':plays,'best':best,
            'pin_age_min':pin_age_min,
            '_books_h2h':books_h2h,'_h2h_disp':disp,
            '_ex_back':ex_back if ex_back else None,'_ex_lay':ex_lay if ex_lay else None,
            'sharp':sm if sm else None,'rl_dataerror':rl_dataerror,
            'spread_label':spread_label,'three_way':three_way,
            'status':(lambda _st: _st if (_st and _an_same_game(_st, g['commence_time'])) else {'state':'scheduled','display':None})(status_map.get((away,home))),
            'has_value':any(p['pass'] for p in plays),'value_play':best,
            '_sharp_raw':sm,'_soft_fair':soft_fair.get((away,home),{})}



# ============================ EMBEDDED TEMPLATE ============================
TEMPLATE_HEAD = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RidgeSeeker</title>
<style>
  :root{
    --bg:#14161d;--bg2:#1a1d26;--card:#1e222d;--card2:#252a37;--line:#2e3442;
    --txt:#eef1f6;--mut:#9aa6b6;--dim:#8f9aa8;
    --sharp:#34d399;--sharpd:#0f6b4a;--public:#fb7185;--split:#fbbf24;--gold:#f5c451;
    --tick:#fb7185;--hand:#34d399;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:"SF Mono",ui-monospace,"Roboto Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5;
    -webkit-font-smoothing:antialiased;padding-bottom:92px}
  .wrap{max-width:760px;margin:0 auto;padding:0 14px}
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
  /* Keyboard focus: visible on every interactive control (none existed before). */
  :focus-visible{outline:2px solid var(--gold);outline-offset:2px}
  header{padding:22px 0 16px}
  .mast{display:flex;align-items:center;justify-content:space-between}
  .logo{font-size:25px;font-weight:800;letter-spacing:-.6px}.logo b{color:var(--sharp)}
  .clock{font-family:var(--mono);font-size:11px;color:var(--mut);text-align:right;line-height:1.5}
  .clock .lv{color:var(--sharp)}
  .sub{font-size:12.5px;color:var(--mut);margin-top:6px}
  .srcrow{display:flex;flex-wrap:wrap;gap:5px;margin-top:11px}
  .src{font-family:var(--mono);font-size:9.5px;padding:3px 8px;border-radius:6px;background:var(--card);border:1px solid var(--line);color:var(--mut)}
  .src .on{color:var(--sharp)} .src .off{color:var(--dim)}
  .hero{margin-top:14px;border-radius:14px;overflow:hidden;border:1px solid var(--line)}
  .hero.has{border-color:var(--sharpd);background:linear-gradient(135deg,rgba(52,211,153,.09),rgba(245,196,81,.05))}
  .hero.none{background:var(--card)}
  .hero-h{padding:11px 15px;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
    color:var(--gold);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:7px}
  .hero-b{padding:14px 15px}.hero.none .hero-b{color:var(--mut);font-size:13px}
  .disc{background:#1d1810;border:1px solid #3a2e18;color:#c9a86a;font-size:11px;padding:10px 13px;border-radius:10px;margin-top:14px;line-height:1.55}
  .tabs{display:flex;gap:6px;overflow-x:auto;padding:16px 0 12px;position:sticky;top:0;background:var(--bg);z-index:20;scrollbar-width:none}
  .tabs::-webkit-scrollbar{display:none}
  .tab{flex-shrink:0;padding:9px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);min-height:44px;font-family:inherit;
    cursor:pointer;font-size:13px;font-weight:700;color:var(--mut);white-space:nowrap;display:flex;align-items:center;gap:7px}
  .tab .led{width:7px;height:7px;border-radius:50%;background:var(--dim)}
  .tab.live .led{background:var(--sharp);box-shadow:0 0 7px var(--sharp)}
  .tab.active{background:var(--card2);color:var(--txt);border-color:var(--sharp)}
  .tab.off{opacity:.5}.tab .ret{font-size:9px;color:var(--dim);font-weight:600}.tab.temp .ret{color:var(--split)}
  .view{display:none;padding-top:6px}.view.active{display:block;animation:fade .2s}
  @keyframes fade{from{opacity:0}to{opacity:1}}
  .sect{font-size:11px;text-transform:uppercase;letter-spacing:1.3px;color:var(--dim);font-weight:700;
    margin:20px 2px 11px;display:flex;align-items:center;gap:10px}
  .sect::after{content:"";flex:1;height:1px;background:var(--line)}
  .sect .ct{color:var(--mut);font-family:var(--mono);font-size:10px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;margin-bottom:12px;overflow:hidden}
  .card.conf{border-color:var(--gold)}
  .badgebar{display:flex;align-items:center;gap:7px;padding:9px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
  .badge{font-size:10.5px;font-weight:800;letter-spacing:.5px;padding:4px 9px;border-radius:7px;display:inline-flex;align-items:center;gap:5px}
  .badge .d{width:6px;height:6px;border-radius:50%}
  .b-SHARP{background:rgba(52,211,153,.13);color:var(--sharp)}.b-SHARP .d{background:var(--sharp)}
  .b-VALUE{background:rgba(52,211,153,.13);color:var(--sharp)}
  .b-PASS{background:rgba(154,166,182,.1);color:var(--mut)}
  .body{padding:14px}
  .teams{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px}
  .team{flex:1}.team .nm{font-size:15.5px;font-weight:700}.team .meta{font-size:11px;color:var(--dim);margin-top:2px}.team.r{text-align:right}
  .at{font-family:var(--mono);font-size:11px;color:var(--dim)}
  .sharpbox{margin-top:12px;background:var(--bg2);border-radius:10px;padding:12px;border:1px solid var(--line)}
  .sharpbox .sh-h{display:flex;justify-content:space-between;margin-bottom:10px}
  .sharpbox .ttl{font-size:10.5px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:var(--mut)}
  .sharpbox .src2{font-family:var(--mono);font-size:9px;color:var(--dim)}
  .splitrow{margin-bottom:11px}.splitrow:last-child{margin-bottom:0}
  .splitrow .lbl{display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:5px}
  .splitrow .tm{font-weight:600}.splitrow .pct{font-family:var(--mono);color:var(--mut)}
  .dualbar{height:9px;border-radius:5px;background:#11131a;overflow:hidden;display:flex}
  .dualbar .tk{background:var(--tick);opacity:.85}.dualbar .hd{background:var(--hand);opacity:.85}
  .barkey{display:flex;gap:14px;margin-top:9px;font-size:9.5px;color:var(--dim);font-family:var(--mono)}
  .barkey i{width:8px;height:8px;border-radius:2px;margin-right:4px;display:inline-block;vertical-align:middle}
  .sh-read{margin-top:10px;font-size:11.5px;line-height:1.5}.sh-read b{color:var(--sharp)}
  .note{font-size:12px;color:var(--mut);margin-top:11px;line-height:1.55;background:var(--bg2);border-radius:9px;padding:10px 12px}
  .note b{color:var(--txt)}.note .g{color:var(--sharp)}.note .gold{color:var(--gold)}
  .nodata{font-size:11px;color:var(--dim);margin-top:11px;font-style:italic}
  .empty{border:1px dashed var(--line);border-radius:13px;padding:36px 20px;text-align:center}
  .empty .ic{font-size:24px;opacity:.5;margin-bottom:10px}.empty h3{font-size:14px;color:var(--mut);margin-bottom:6px}
  .empty p{font-size:12.5px;color:var(--dim);max-width:380px;margin:0 auto;line-height:1.5}
  footer{color:var(--dim);font-size:10.5px;text-align:center;padding:26px 14px;line-height:1.7}footer b{color:var(--mut)}

  .markets{display:flex;flex-direction:column;gap:9px}
  .mblock{background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:10px 11px}
  .mblock .mh{font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:var(--mut);margin-bottom:8px}
  .mkrow{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px}
  .mkrow .mlbl{font-family:var(--mono);font-size:9px;color:var(--dim);width:22px}
  .mkrow .mside{flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .mkrow .mprice{font-family:var(--mono);font-weight:800;width:48px;text-align:right}
  .mkrow.best{background:rgba(52,211,153,.07);margin:0 -6px;padding:5px 6px;border-radius:6px}
  .mkrow.best .mprice{color:var(--sharp)}
  .mderr{font-size:11px;color:var(--split);background:rgba(251,191,36,.06);border-radius:7px;padding:8px 10px;line-height:1.45}

  .gradechip{font-family:var(--mono);font-size:15px;font-weight:800;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;border-radius:8px}
  .gradechip.none{background:var(--card2);color:var(--dim);font-size:13px}
  .vyes{font-family:var(--mono);font-size:9px;font-weight:800;color:var(--sharp);margin-left:auto;background:rgba(52,211,153,.13);padding:2px 6px;border-radius:4px}
  .sharptag{font-size:9px;color:var(--sharp);font-weight:700}

  .ctags{display:flex;flex-direction:column;gap:4px;margin-top:8px}
  .ctag{font-size:10px;padding:3px 8px;border-radius:5px;display:inline-block;width:fit-content}
  .ctag.good{background:rgba(52,211,153,.1);color:var(--sharp)}
  .ctag.meh{background:rgba(154,166,182,.08);color:var(--mut)}

  .topplay{display:flex;align-items:center;gap:11px;padding:2px 0}
  .tp-l{flex-shrink:0}
  .tp-grade{font-family:var(--mono);font-size:15px;font-weight:800;width:30px;height:30px;display:flex;align-items:center;justify-content:center;border-radius:8px;color:#0c0f16}
  .tp-mid{flex:1;min-width:0}
  .tp-bet{font-size:15px;font-weight:800;color:var(--txt)}
  .unitbadge{font-family:var(--mono);font-size:10px;font-weight:800;padding:2px 7px;border-radius:5px;margin-left:4px;vertical-align:middle}
  .unitbadge.u2{background:var(--gold);color:#3a2c08}
  .unitbadge.u15{background:rgba(52,211,153,.16);color:var(--sharp)}
  .unitbadge.u1{background:rgba(154,166,182,.13);color:var(--mut)}
  .ureason{color:var(--dim);font-size:10.5px}
  .trackbar{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:11px 14px;margin-top:12px;font-size:12px}
  .tk-row{display:flex;justify-content:space-between;align-items:center}
  .tk-l{font-size:10px;font-weight:800;letter-spacing:.8px;text-transform:uppercase;color:var(--dim)}
  .tk-rec{font-family:var(--mono);font-size:13px}
  .tk-rec .pos{color:var(--sharp)}.tk-rec .neg{color:var(--public)}
  .tk-v{color:var(--mut);font-size:11.5px;margin-left:10px}
  .tk-row2{margin-top:6px;font-size:10.5px;font-family:var(--mono);display:flex;gap:10px;flex-wrap:wrap}
  .tk-prog{color:var(--mut)}.tk-ready{color:var(--gold);font-weight:700}
  .tk-warn{color:var(--split)}.tk-pend{color:var(--dim)}
  .tp-game{font-size:11.5px;color:var(--mut);margin-top:1px}
  .altmk{font-size:10.5px;color:var(--dim);margin-top:3px;font-family:var(--mono)}
  .tp-r{flex-shrink:0;text-align:right}
  .ddtag{font-family:var(--mono);font-size:9px;font-weight:800;color:var(--gold);background:rgba(245,196,81,.13);padding:3px 7px;border-radius:5px;white-space:nowrap}
  .ddtag.val{color:var(--sharp);background:rgba(52,211,153,.13)}
  .tp-why{font-size:11px;color:var(--mut);margin:5px 0 0 41px;line-height:1.45}
  .tp-div{height:1px;background:var(--line);margin:12px 0}

  .livepill{font-family:var(--mono);font-size:9.5px;font-weight:800;color:#fff;background:#dc2626;padding:3px 8px;border-radius:5px;display:inline-flex;align-items:center;gap:5px;animation:livepulse 2s infinite}
  .livedot{width:6px;height:6px;border-radius:50%;background:#fff;animation:blink 1s infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
  @keyframes livepulse{0%,100%{box-shadow:0 0 0 0 rgba(220,38,38,.4)}50%{box-shadow:0 0 0 4px rgba(220,38,38,0)}}
  .finalpill{font-family:var(--mono);font-size:9.5px;font-weight:700;color:var(--dim);background:rgba(154,166,182,.1);padding:3px 8px;border-radius:5px}
  .delaypill{font-family:var(--mono);font-size:9.5px;font-weight:700;color:var(--split);background:rgba(251,191,36,.1);padding:3px 8px;border-radius:5px}
  .tplive{font-family:var(--mono);font-size:9.5px;font-weight:800;color:#fff;background:#dc2626;padding:1px 6px;border-radius:4px;animation:blink 1.4s infinite}
  .tpfinal{font-family:var(--mono);font-size:9.5px;color:var(--dim)}
  .tpdelay{font-family:var(--mono);font-size:9.5px;color:var(--split)}
  .viewtoggle{display:flex;gap:8px;margin-top:12px}
  .vtab{flex:0 0 auto;background:var(--card2);border:1px solid var(--line);color:var(--mut);font-size:14px;font-weight:700;padding:9px 18px;border-radius:999px;cursor:pointer;transition:all .15s;font-family:inherit;min-height:44px;display:inline-flex;align-items:center;justify-content:center}
  .vtab.active{background:var(--sharp);color:#04130c;border-color:var(--sharp)}
  .rbig{display:flex;gap:8px;margin:14px 0 4px;flex-wrap:wrap}
  .rstat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;flex:1;min-width:96px}
  .rstat .l{font-size:9px;text-transform:uppercase;letter-spacing:.6px;color:var(--dim);font-weight:700}
  .rstat .v{font-size:21px;font-weight:800;font-family:var(--mono);margin-top:2px}
  .rsect{font-size:11px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:var(--mut);margin:20px 0 9px;border-bottom:1px solid var(--line);padding-bottom:6px}
  .rtable{width:100%;border-collapse:collapse;font-size:13px}
  .rtable th,.rtable td{text-align:right;padding:7px 8px;border-bottom:1px solid var(--line)}
  .rtable th:first-child,.rtable td:first-child{text-align:left}
  .rtable th{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--dim);font-weight:700}
  .rtable td.g{font-family:var(--mono);font-weight:800}
  .rcard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}
  .pos{color:var(--sharp)}.neg{color:var(--public)}
  .thin2{color:var(--dim);font-size:10px;font-style:italic}
  .rnote{color:var(--mut);font-size:11.5px;line-height:1.5;margin-top:7px}
  .dlrow{display:flex;gap:10px;margin:12px 0;flex-wrap:wrap}
  .dlrow a{background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:9px 14px;font-size:13px;font-weight:600;color:#60a5fa;text-decoration:none;min-height:44px;display:inline-flex;align-items:center}
  .rbar{height:20px;border-radius:5px;display:flex;align-items:center;padding:0 8px;font-size:11px;font-family:var(--mono);font-weight:700;color:#0a0d12;min-width:28px}
  .rempty{text-align:center;color:var(--mut);padding:40px 20px}
  .rempty h3{margin-bottom:8px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="mast"><h1 class="logo">ridge<b>seeker</b></h1><div class="clock" id="clock"></div></div>
    <div class="viewtoggle" role="group" aria-label="View">
      <button class="vtab active" id="vtab-board" onclick="showView('board')" aria-pressed="true">Today's Board</button>
      <button class="vtab" id="vtab-results" onclick="showView('results')" aria-pressed="false">Results</button>
    </div>
  </header>

  <div id="view-board">
    <div class="sub">Fair value = devigged Pinnacle (the sharpest book), consensus median as fallback, compared to Bovada. Sharp money where available. Only real edges surface.</div>
    <div class="srcrow" id="srcrow"></div>
    <div class="hero" id="hero"></div>
    <div class="disc">⚠️ <b>All signals are real data.</b> Fair probability = Pinnacle with the vig removed (falling back to the no-vig median of ~25 books when Pinnacle skips a market). Sharp money = live ticket/handle from Action Network (US team sports). Estimates, not guarantees; lines move; re-check before betting. 21+ · 1-800-522-4700.</div>
    <div class="tabs" id="tabs" role="tablist" aria-label="Sports"></div>
    <div id="views"></div>
  </div>

  <div id="view-results" style="display:none"></div>
</div>
<footer>true-prob blend + sharp money, computed live · entertainment / analysis only</footer>
"""

TEMPLATE_APP = r"""
const GC={S:'#f5c451',A:'#34d399',B:'#60a5fa',C:'#9aa6b6',D:'#646f7f'};


function statusPill(st){
  if(!st) return '';
  if(st.state==='live') return `<span class="livepill"><span class="livedot"></span>LIVE${st.display?' · '+st.display:''}</span>`;
  if(st.state==='final') return `<span class="finalpill">${st.display||'Final'}</span>`;
  if(st.state==='delay') return `<span class="delaypill">⏸ ${st.display||'Delayed'}</span>`;
  return '';
}


function tStr(iso){return new Date(iso).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'});}
function amStr(o){o=+o;return o>0?'+'+o:''+o;}
const GRADE_COLOR={S:'#f5c451',A:'#34d399',B:'#60a5fa',C:'#9aa6b6',D:'#646f7f'};
function marketRow(lbl,side,point,price,isVal){
  const pt=(point!=null&&point!=='None')?` <span style="color:var(--dim)">${(+point>0?'+':'')+point}</span>`:'';
  const valtag=isVal?`<span class="vyes">✓ VALUE</span>`:'';
  return `<div class="mkrow ${isVal?'best':''}"><span class="mlbl">${lbl}</span><span class="mside">${side}${pt}</span><span class="mprice">${price!=null?amStr(price):'-'}</span>${valtag}</div>`;
}
function gameCard(c){
  const sg=c.sharp_grade;const v=c.value_play;
  let chip = sg?`<span class="gradechip" style="background:${GRADE_COLOR[sg.grade]};color:#0c0f16">${sg.grade}</span>`:`<span class="gradechip none">-</span>`;
  let valbadge = c.has_value?`<span class="badge b-VALUE">✓ VALUE</span>`:`<span class="badge b-PASS">no value</span>`;
  let sharpbadge = sg?`<span class="badge b-SHARP"><span class="d"></span>SHARP ${sg.grade}${sg.contrarian?' ◆':''}${sg.steam?' ⚡':''}</span>`:`<span class="badge b-PASS">no sharp signal</span>`;
  const byMkt={ML:[],SPR:[],TOT:[]};
  c.plays.forEach(p=>{if(byMkt[p.mkt])byMkt[p.mkt].push(p);});
  const isVal=(p)=>p.pass;
  function block(title,arr,labelShort,dataerror){
    if(dataerror)return `<div class="mblock"><div class="mh">${title}</div><div class="mderr">⚠ Bovada line contradicts the market consensus, suppressed to avoid a false edge.</div></div>`;
    if(!arr.length)return '';
    const rows=arr.map(p=>marketRow(labelShort,p.side,p.point,p.price,isVal(p))).join('');
    return `<div class="mblock"><div class="mh">${title}</div>${rows}</div>`;
  }
  let blocks='';
  blocks+=block(c.three_way?'Moneyline (3-way)':'Moneyline',byMkt.ML,'ML',false);
  if(c.spread_label)blocks+=block(c.spread_label,byMkt.SPR,c.spread_label==='Asian Handicap'?'AH':(c.spread_label==='Run Line'?'RL':(c.spread_label==='Puck Line'?'PL':'SP')),c.rl_dataerror);
  blocks+=block('Total',byMkt.TOT,'O/U',false);
  let sharpHtml='';
  if(sg&&c.sharp){
    const teams=Object.keys(c.sharp);let rows='';
    teams.forEach(tm=>{const tk=Math.round(c.sharp[tm].tickets||0),mn=Math.round(c.sharp[tm].money||0);const isS=(tm===sg.side);
      rows+=`<div class="splitrow"><div class="lbl"><span class="tm">${tm}${isS?' <span class="sharptag">← sharp side</span>':''}</span><span class="pct">${tk}% tix · ${mn}% $</span></div><div class="dualbar"><div class="tk" style="width:${tk/2}%"></div><div class="hd" style="width:${mn/2}%"></div></div></div>`;});
    let why=`<b>${sg.side}</b>: ${sg.money}% money vs ${sg.tickets}% tickets (gap ${sg.gap>0?'+':''}${sg.gap}).`;
    let tags='';
    if(sg.contrarian)tags+=`<span class="ctag good">◆ contrarian: sharp money on the unpopular side</span>`;
    else tags+=`<span class="ctag meh">money follows the public (weaker)</span>`;
    if(sg.steam)tags+=`<span class="ctag good">⚡ steam: market moved this way</span>`;
    if(sg.capped)tags+=`<span class="ctag meh">capped at B (thin/early market)</span>`;
    sharpHtml=`<div class="sharpbox"><div class="sh-h"><span class="ttl">Sharp grade · <b style="color:${GRADE_COLOR[sg.grade]}">${sg.grade}</b></span><span class="src2">Action Network</span></div>${rows}<div class="barkey"><span><i style="background:var(--tick)"></i>tickets (public)</span><span><i style="background:var(--hand)"></i>money (sharp)</span></div><div class="sh-read">${why}</div><div class="ctags">${tags}</div></div>`;
  } else sharpHtml=`<div class="nodata">No sharp-money data (US team sports only).</div>`;
  let note='';
  if(c.has_value&&v){const pt=v.point!=null?` ${(+v.point>0?'+':'')+v.point}`:'';const ml=v.mkt==='SPR'?(c.spread_label||'spread'):(v.mkt==='TOT'?'total':'ML');note=`<div class="note"><b class="g">✓ Value:</b> ${ml} ${v.side}${pt} at ${amStr(v.price)} beats fair value. ${sg&&v.side===sg.side?`<b class="gold">+ sharp ${sg.grade} agrees: double-down spot.</b>`:(sg?`Sharp leans ${sg.side} (${sg.grade}).`:'')}</div>`;}
  else if(sg&&sg.grade!=='D')note=`<div class="note">Sharp money grades <b style="color:${GRADE_COLOR[sg.grade]}">${sg.grade}</b> on ${sg.side}. No price value on Bovada, a sharp lean, not a value bet.</div>`;
  else if(sg)note=`<div class="note">Weak/noise-level signal (D). Not a real edge. <b>Pass.</b></div>`;
  else note=`<div class="note">No value, no sharp signal. <b>Pass.</b></div>`;
  return `<div class="card ${sg&&(sg.grade==='S')?'conf':''}">
    <div class="badgebar">${chip}${sharpbadge}${valbadge}${statusPill(c.status)}</div>
    <div class="body"><div class="teams"><div class="team"><div class="nm">${c.away}</div><div class="meta">${tStr(c.time)}</div></div><div class="at">${c.three_way?'v':'@'}</div><div class="team r"><div class="nm">${c.home}</div></div></div>
    <div class="markets">${blocks}</div>${sharpHtml}${note}</div></div>`;
}



function tpStatus(st){
  if(!st) return '';
  if(st.state==='live') return ` <span class="tplive">● LIVE${st.display?' '+st.display:''}</span>`;
  if(st.state==='final') return ` <span class="tpfinal">${st.display||'final'}</span>`;
  if(st.state==='delay') return ` <span class="tpdelay">⏸ delayed</span>`;
  return '';
}
function amDec(o){o=+o;return o>0?1+o/100:1+100/(-o);}
function decAm(d){return d>=2?'+'+Math.round((d-1)*100):''+Math.round(-100/(d-1));}
const GORDER={S:5,A:4,B:3,C:2,D:1};
const SPORTS=__SPORTS_JS__;
const now=new Date();
document.getElementById('clock').innerHTML=now.toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'})+'<br><span class="lv">● live feed</span>';
const anySharp=Object.values(ALL).flat().some(c=>c.sharp_grade);
const anyPin=Object.entries(ALL).filter(([k])=>!k.startsWith('_')).some(([k,cs])=>cs.some&&cs.some(c=>(c.plays||[]).some(p=>p.anchor==='pinnacle')));
document.getElementById('srcrow').innerHTML=[{n:'Pinnacle anchor',on:anyPin},{n:'soft books',on:true},{n:'Bovada',on:true},{n:'sharp grade',on:anySharp},{n:'value scan',on:true}].map(s=>`<span class="src">${s.n} <span class="${s.on?'on':'off'}">${s.on?'●':'○'}</span></span>`).join('');
// TOP PLAYS: all S/A grades + double-downs, each with a specific market recommendation
const TOP = ALL['_top']||[];
const he=document.getElementById('hero');
function recLine(t){
  const r=t.rec; if(!r) return '';
  const dd = r.double?`<span class="ddtag">◆◆ DOUBLE-DOWN</span>`:'';
  // unit badge
  let unitHtml='';
  if(t.units){
    const dollars=t.unit_dollars?(' · $'+Math.round(t.units*t.unit_dollars)):'';
    const uc = t.units>=2?'u2':(t.units>=1.5?'u15':'u1');
    unitHtml=`<span class="unitbadge ${uc}">${t.units}u${dollars}</span>`;
  }
  // alt markets for sharp-only plays
  let altHtml='';
  if(r.alts && r.alts.length>1){
    const others=r.alts.slice(1).map(a=>{const pt=a.point!=null?' '+((+a.point>0?'+':'')+(''+a.point).replace('.0','')):'';return `${a.market}${pt} ${a.price>0?'+'+a.price:a.price}`;}).join(' · ');
    altHtml=`<div class="altmk">or: ${others}</div>`;
  }
  return `<div class="topplay">
    <div class="tp-l"><span class="tp-grade" style="background:${GC[t.grade]||'#646f7f'}">${t.grade||'•'}</span></div>
    <div class="tp-mid"><div class="tp-bet">${r.text} ${unitHtml}</div><div class="tp-game">${t.away} @ ${t.home} · ${t.sport} · ${tStr(t.time)}${tpStatus(t.status)}</div>${altHtml}</div>
    <div class="tp-r">${dd||(t.has_value?'<span class="ddtag val">✓ value</span>':'')}</div>
  </div>
  <div class="tp-why">${r.why}${t.units_reason?' · <span class="ureason">'+t.units+'u: '+t.units_reason+'</span>':''}</div>`;
}
// ---- tracker panel ----
(function(){
  const tr=ALL['_tracker']; if(!tr) return;
  const host=document.getElementById('hero');
  if(!host) return;
  let panel=document.createElement('div'); panel.className='trackbar';
  if(tr.n===0){
    panel.innerHTML=`<span class="tk-l">Bet tracker</span><span class="tk-v">No settled bets yet. Your record builds automatically as games finish.</span>`;
  } else {
    const ud=ALL['_unit_dollars']||10;
    const dollars=Math.round(tr.units_pl*ud);
    let prog='';
    if(tr.progress){
      const p=tr.progress;
      if(p.ready) prog=`<span class="tk-ready">✓ Ready for $${p.to}/unit (want ~$${p.bankroll_need} bankroll)</span>`;
      else prog=`<span class="tk-prog">→ $${p.to}/u: ${p.bets_done}/${p.bets_need} bets · ${p.units_done>=0?'+':''}${p.units_done}/${p.units_need}u</span>`;
    }
    const expo=tr.open_units?` <span class="${tr.open_units>(tr.max_daily_units||6)?'tk-warn':'tk-pend'}">${tr.open_units}u open${tr.open_units>(tr.max_daily_units||6)?' (over '+(tr.max_daily_units||6)+'u guidance)':''}</span>`:'';
    panel.innerHTML=`<div class="tk-row"><span class="tk-l">Tracker</span><span class="tk-rec">${tr.wins}-${tr.losses} · <b class="${tr.units_pl>=0?'pos':'neg'}">${tr.units_pl>=0?'+':''}${tr.units_pl}u (${dollars>=0?'+$':'-$'}${Math.abs(dollars)})</b></span></div><div class="tk-row2">${prog}${tr.concentrated?' <span class="tk-warn">profit concentrated in 1 hit (small sample)</span>':''}${tr.pending?' <span class="tk-pend">'+tr.pending+' pending</span>':''}${tr.voids?' <span class="tk-pend">'+tr.voids+' void</span>':''}${expo}</div>`;
  }
  host.parentNode.insertBefore(panel, host.nextSibling);
})();
if(TOP.length){
  he.className='hero has';
  he.innerHTML=`<div class="hero-h">★ Plays worth your attention today · ${TOP.length}</div><div class="hero-b">${TOP.map(recLine).join('<div class="tp-div"></div>')}</div>`;
}else{
  he.className='hero none';
  he.innerHTML=`<div class="hero-h" style="color:var(--mut)">Plays worth your attention</div><div class="hero-b">Nothing graded S or A and no double-downs right now. The honest move is to sit out or wait for live games. B-grade sharp leans are on the board below if you want a lighter look.</div>`;
}
// tabs
const tabsEl=document.getElementById('tabs');
SPORTS.forEach((s,i)=>{const t=document.createElement('button');t.type='button';t.className='tab'+(s.live?' live':' off')+(i===0?' active':'');t.dataset.k=s.key;t.setAttribute('role','tab');t.setAttribute('aria-selected',i===0?'true':'false');if(!s.live){t.setAttribute('aria-disabled','true');t.setAttribute('aria-label',s.label+' (out of season)');}let ret=!s.live?`<span class="ret">${s.ret}</span>`:'';t.innerHTML=`<span class="led" aria-hidden="true"></span>${s.label}${ret}`;if(s.live)t.onclick=()=>switchTab(s.key);tabsEl.appendChild(t);});
function switchTab(k){document.querySelectorAll('.tab').forEach(t=>{const on=t.dataset.k===k;t.classList.toggle('active',on);t.setAttribute('aria-selected',on?'true':'false');});document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));document.getElementById('view-'+k).classList.add('active');}
const viewsEl=document.getElementById('views');
function mkView(k,a){const v=document.createElement('div');v.className='view'+(a?' active':'');v.id='view-'+k;v.setAttribute('role','tabpanel');v.setAttribute('aria-label',k+' games');return v;}
// sort: sharp grade desc (S→D), then value, then time
function sortKey(c){const g=c.sharp_grade?GORDER[c.sharp_grade.grade]:0;const val=c.has_value?0.5:0;return g+val;}
function buildSportView(key,label,active){
  const cards=ALL[key]||[];
  const v=mkView(key,active);
  if(!cards.length){v.innerHTML=`<div class="empty"><div class="ic">◍</div><h3>No ${label} games on the board</h3><p>Re-run when games post.</p></div>`;viewsEl.appendChild(v);return;}
  const sorted=[...cards].sort((a,b)=>sortKey(b)-sortKey(a));
  const graded=sorted.filter(c=>c.sharp_grade);
  const ungraded=sorted.filter(c=>!c.sharp_grade);
  let h='';
  if(graded.length)h+=`<h2 class="sect">sharp board · S → D<span class="ct">${graded.length} graded</span></h2>`+graded.map(gameCard).join('');
  if(ungraded.length)h+=`<h2 class="sect">${graded.length?'no sharp signal':'full slate'}<span class="ct">${ungraded.length}</span></h2>`+ungraded.map(gameCard).join('');
  v.innerHTML=h;viewsEl.appendChild(v);
}
buildSportView('mlb','MLB',true);
SPORTS.filter(s=>!s.live).forEach(s=>{const v=mkView(s.key,false);v.innerHTML=`<div class="empty"><div class="ic">◍</div><h3>${s.label} is out of season</h3><p>Lights up around <b>${s.ret}</b>. Full sharp grades + value scan when it's live.</p></div>`;viewsEl.appendChild(v);});

// ===== view toggle: Board <-> Results =====
let _resultsBuilt=false;
function showView(which){
  const board=document.getElementById('view-board'), results=document.getElementById('view-results');
  const tb=document.getElementById('vtab-board'), tr=document.getElementById('vtab-results');
  if(which==='results'){
    board.style.display='none'; results.style.display='block';
    tb.classList.remove('active'); tr.classList.add('active');
    tb.setAttribute('aria-pressed','false'); tr.setAttribute('aria-pressed','true');
    if(!_resultsBuilt){ renderResults(); _resultsBuilt=true; }
    window.scrollTo(0,0);
  } else {
    results.style.display='none'; board.style.display='block';
    tr.classList.remove('active'); tb.classList.add('active');
    tr.setAttribute('aria-pressed','false'); tb.setAttribute('aria-pressed','true');
    window.scrollTo(0,0);
  }
}

// ===== Results view (folded-in stats) =====
function healthStrip(){
  const rl=(ALL._runlog||[]);
  if(!rl.length) return '';
  const last=rl[rl.length-1]; const al=[];
  if(last.mode==='full'&&!last.odds_games) al.push('odds feed EMPTY');
  if(last.unmatched) al.push(last.unmatched+' name-join miss');
  if(last.bov_absent) al.push(last.bov_absent+' game(s) missing Bovada (freeze?)');
  if(last.ctx_misses) al.push(last.ctx_misses+' MLB-context miss');
  return `<div class="rcard"><b>Feed health:</b> last run ${last.ts?String(last.ts).slice(0,16).replace('T',' ')+' UTC':'?'} (${last.mode}) · odds ${last.odds_games==null?'-':last.odds_games} games · AN ${last.an_games==null?'-':last.an_games} · logged ${last.plays_logged||0} · closes ${last.closes||0} · graded ${last.graded||0}${al.length?` <span style="color:#e66">! ${al.join(' · ')}</span>`:' · all clear'}</div>`;
}
function renderResults(){
  const S=ALL['_stats']||{}; const ud=S.unit_dollars||ALL['_unit_dollars']||10;
  const host=document.getElementById('view-results');
  const o=S.overall||{n:0};
  const money=(u)=>{const d=Math.round(u*ud);return (u>=0?'+':'')+u+'u ('+(d>=0?'+$':'-$')+Math.abs(d)+')';};
  const cls=(u)=>u>=0?'pos':'neg';
  const pct=(v)=>v==null?'-':`<span class="${v>=0?'pos':'neg'}">${v>=0?'+':''}${v}%</span>`;
  // Signal lab (shadow ledger): rendered on BOTH paths. A stretch of C-only boards
  // is exactly when the shadow table matters most, and it can have data while the
  // real record is still empty.
  function shadowLab(){
    if(!(S.shadow&&S.shadow.rows&&Object.keys(S.shadow.rows).length)) return '';
    const sh=S.shadow; let srows='';
    ['S','A','B','C','D','value flag'].forEach(k=>{const r=sh.rows[k];if(!r)return;
      const thin=r.graded<30?'<span class="thin2"> small</span>':'';
      srows+=`<tr><td class="g" style="color:${GC[k]||'#9aa6b6'}">${k}</td><td>${r.graded}/${r.n}${thin}</td><td>${r.win_pct==null?'-':r.win_pct+'%'}</td><td class="${cls(r.flat_pl||0)}">${r.flat_roi==null?'-':(r.flat_roi>=0?'+':'')+r.flat_roi+'%'}</td><td>${r.fair_avg==null?'-':pct(r.fair_avg)}${r.fair_n?` <span class="thin2">n=${r.fair_n}</span>`:''}</td></tr>`;});
    return `<h2 class="rsect">Signal lab (shadow board, not bets)</h2><table class="rtable"><tr><th scope="col">Signal</th><th scope="col">Graded/Logged</th><th scope="col">Win%</th><th scope="col">Flat ROI</th><th scope="col">EV at close</th></tr>${srows}</table><div class="rnote">Every sharp lean S through D (sharp-side moneyline at Bovada, entry frozen at first sighting) and every value flag is logged here at ZERO units, purely to measure the signals the tool sees but does not bet. EV at close is the same headline metric as above, measured closes only. Flat ROI assumes 1u on every row. Excluded from the record, tracker, level gates, and the pre-registered endpoint. A row means little before ~30 graded.${sh.pending?' '+sh.pending+' pending.':''}</div>`;
  }
  if(!o.n){
    host.innerHTML=healthStrip()+`<div class="rempty"><h3>No settled bets yet</h3><p>Your results build automatically as recommended games finish. Check back after a few slates.</p></div>`
    +shadowLab()+`
    <h2 class="rsect">Raw data</h2><div class="dlrow"><a href="bets.csv" download>⬇ bets.csv</a><a href="snapshots.csv" download>⬇ snapshots.csv</a></div>
    <div class="rnote">bets.csv = every recommended play and its result. snapshots.csv = each run's readings, for edge-over-time analysis.</div>`;
    return;
  }
  let h=`<div class="rbig">
    <div class="rstat"><div class="l">Record</div><div class="v">${o.wins}-${o.losses}</div></div>
    <div class="rstat"><div class="l">Win %</div><div class="v">${o.win_pct}%</div></div>
    <div class="rstat"><div class="l">Units</div><div class="v ${cls(o.units_pl)}">${o.units_pl>=0?'+':''}${o.units_pl}</div></div>
    <div class="rstat"><div class="l">ROI</div><div class="v ${cls(o.roi||0)}">${o.roi==null?'-':o.roi+'%'}</div></div>
    <div class="rstat"><div class="l">Profit</div><div class="v ${cls(o.units_pl)}">${o.dollars>=0?'+$':'-$'}${Math.abs(o.dollars)}</div></div>
  </div><div class="rnote">${o.pending||0} bets still pending.${o.voids?` ${o.voids} voided (postponed/cancelled, refunded like a book would).`:''}${o.pushes?` ${o.pushes} pushed.`:''} $${ud}/unit.</div>`;
  if(S.clv&&S.clv.n_graded){
    const c=S.clv;
    h+=`<div class="rcard"><b>Closing line value:</b> EV at close avg ${pct(c.fair_avg)} (positive ${c.fair_pos==null?'-':c.fair_pos+'%'} of ${c.fair_n}) · price CLV avg ${pct(c.avg)} (beat the close ${c.pos_pct==null?'-':c.pos_pct+'%'} of ${c.n}).<div class="rnote">EV at close = the entry price scored against the devigged, Pinnacle-anchored fair probability at the last pregame observation: the market's final verdict on each bet, and the headline metric. Price CLV = entry vs the last Bovada price, same-book line movement. Coverage: ${c.n_measured} of ${c.n_graded} graded plays had a post-entry close observation${c.coverage==null?'':' ('+c.coverage+'%)'}; the rest are excluded, not counted as zero. The close is still the last reading this tool saw, an approximation given the run schedule.</div></div>`;
  }
  h+=healthStrip();
  const evr=S.ev_real;
  if(evr&&evr.n){ h+=`<div class="rcard"><b>Expected vs realized:</b> stated EV summed to ${evr.exp>0?'+':''}${evr.exp}u across ${evr.n} settled bets; reality delivered ${evr.act>0?'+':''}${evr.act}u (gap ${evr.gap>0?'+':''}${evr.gap}u).<div class="rnote">A persistently large negative gap means stated edges are inflated. Meaningless before ~50 bets.</div></div>`; }
  const cr=S.clv_roll;
  if(cr&&cr.n>=10){ h+=`<div class="rcard"><b>Drift check:</b> EV-at-close rolling last ${cr.win}: ${pct(cr.roll)} vs cumulative ${pct(cr.cum)} (n=${cr.n}).<div class="rnote">Rolling far below cumulative suggests the edge is decaying or the market adapted (item 17).</div></div>`; }
  const cs=S.clv_seg;
  if(cs&&cs.rows&&cs.rows.length&&S.clv&&S.clv.fair_n>=10){ h+=`<div class="rcard"><b>EV-at-close by segment</b> <span class="rnote">(exploratory only; the pre-registered endpoint is the overall number)</span>${cs.rows.map(r=>`<div class="rnote">${r.k}: ${pct(r.avg)} (n=${r.n})</div>`).join('')}</div>`; }
  h+=`<div class="rcard"><b>What normal variance looks like</b> (simulation at this tool's price and stake profile, 20k trials of 100 bets): even a model with a REAL +3.5% edge hits a median max drawdown of ~15u and an 8-loss streak, and still finishes negative about 40% of the time; a no-edge model lands anywhere in roughly -26u to +26u. At this sample size, judge the model on EV at close and CLV, not on the W/L record.</div>`;
  h+=`<h2 class="rsect">By stated EV</h2>`+simpleTbl(S.by_ev);
  // by grade
  h+=`<h2 class="rsect">By sharp grade</h2>`+gradeTbl(S.by_grade);
  // Signal lab (shadow ledger): the answer to "do C leans or raw value flags carry
  // EV" lives here, on real closes, without ever risking a unit on them.
  h+=shadowLab();
  if(S.cumulative&&S.cumulative.length>1) h+=`<h2 class="rsect">Cumulative units</h2><div class="rcard">${lineChart(S.cumulative,ud)}</div>`;
  h+=`<h2 class="rsect">Units won by grade</h2><div class="rcard">${gradeBars(S.by_grade)}</div>`;
  h+=`<h2 class="rsect">By unit size</h2>`+simpleTbl(S.by_units);
  h+=`<h2 class="rsect">By signal type</h2>`+simpleTbl(S.by_signal);
  h+=`<h2 class="rsect">By price range</h2>`+simpleTbl(S.by_price);
  h+=`<h2 class="rsect">By market</h2>`+simpleTbl(S.by_market);
  h+=`<h2 class="rsect">By time until game</h2>`+simpleTbl(S.by_htg);
  if(S.edge_by_htg&&Object.keys(S.edge_by_htg).length){
    let rows=Object.entries(S.edge_by_htg).map(([k,v])=>`<tr><td>${k}</td><td class="g">${v} pts</td></tr>`).join('');
    h+=`<h2 class="rsect">Avg sharp gap by time-to-game</h2><div class="rcard"><table class="rtable"><tr><th scope="col">Hours out</th><th scope="col">Avg gap</th></tr>${rows}</table><div class="rnote">Bigger gaps closer to game time = sharp money arriving late (bet later). Bigger early = bet early. Needs a couple weeks of data to trust.</div></div>`;
  }
  h+=`<h2 class="rsect">Raw data</h2><div class="dlrow"><a href="bets.csv" download>⬇ bets.csv</a><a href="snapshots.csv" download>⬇ snapshots.csv</a></div><div class="rnote">Every bet and snapshot, for your own sorting.</div>`;
  host.innerHTML=h;

  function badge(g){return `<td class="g" style="color:${GC[g]||'#888'}">${g}</td>`;}
  function gradeTbl(d){
    if(!d)return '<div class="rcard thin2">Not enough graded bets yet.</div>';
    let rows='';
    ['S','A','B','C','D'].forEach(g=>{const r=d[g];if(!r)return;const thin=r.n<8?'<span class="thin2"> small</span>':'';
      rows+=`<tr>${badge(g)}<td>${r.n}${thin}</td><td>${r.win_pct==null?'-':r.win_pct+'%'}</td><td class="${cls(r.units_pl)}">${r.units_pl>=0?'+':''}${r.units_pl}u</td><td class="${cls(r.roi||0)}">${r.roi==null?'-':r.roi+'%'}</td><td class="${cls(r.dollars)}">${r.dollars>=0?'+$':'-$'}${Math.abs(r.dollars)}</td></tr>`;});
    if(!rows)return '<div class="rcard thin2">Not enough graded bets yet.</div>';
    return `<table class="rtable"><tr><th scope="col">Grade</th><th scope="col">Bets</th><th scope="col">Win%</th><th scope="col">Units</th><th scope="col">ROI</th><th scope="col">$</th></tr>${rows}</table><div class="rnote">"small" = under 8 bets, don't over-read it. You want ROI to rank S ≥ A ≥ B; if it's scrambled, the grading needs tuning.</div>`;
  }
  function simpleTbl(d){
    if(!d||!Object.keys(d).length)return '<div class="rcard thin2">No data yet.</div>';
    let rows=Object.entries(d).map(([k,r])=>{const thin=r.n<8?'<span class="thin2"> sm</span>':'';
      return `<tr><td>${k}</td><td>${r.n}${thin}</td><td>${r.win_pct==null?'-':r.win_pct+'%'}</td><td class="${cls(r.units_pl)}">${r.units_pl>=0?'+':''}${r.units_pl}u</td><td class="${cls(r.roi||0)}">${r.roi==null?'-':r.roi+'%'}</td></tr>`;}).join('');
    return `<table class="rtable"><tr><th scope="col"></th><th scope="col">Bets</th><th scope="col">Win%</th><th scope="col">Units</th><th scope="col">ROI</th></tr>${rows}</table>`;
  }
  function gradeBars(d){
    const vals=['S','A','B','C','D'].map(g=>d&&d[g]?d[g].units_pl:0);
    const max=Math.max(1,...vals.map(Math.abs));let bars='';
    ['S','A','B','C','D'].forEach((g,i)=>{const v=vals[i];const w=Math.abs(v)/max*100;
      bars+=`<div style="display:flex;align-items:center;gap:8px;margin:6px 0"><span style="width:16px;font-family:var(--mono);font-weight:800;color:${GC[g]}">${g}</span><div style="flex:1;background:#0a0d12;border-radius:5px;overflow:hidden"><div class="rbar" style="width:${Math.max(w,7)}%;background:${v>=0?GC[g]:'#f87171'}">${v>=0?'+':''}${v}u</div></div></div>`;});
    return bars;
  }
  function lineChart(pairs,ud){
    const W=680,H=150,pad=22;const vals=pairs.map(p=>p[1]);const mn=Math.min(0,...vals),mx=Math.max(0,...vals);const rng=(mx-mn)||1;
    const pts=pairs.map((p,i)=>{const x=pad+i/(pairs.length-1||1)*(W-2*pad);const y=H-pad-((p[1]-mn)/rng)*(H-2*pad);return [x,y];});
    const path=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
    const zeroY=H-pad-((0-mn)/rng)*(H-2*pad);const last=vals[vals.length-1];
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%"><line x1="${pad}" y1="${zeroY}" x2="${W-pad}" y2="${zeroY}" stroke="#232b36" stroke-dasharray="3 3"/><path d="${path}" fill="none" stroke="${last>=0?'#34d399':'#f87171'}" stroke-width="2.5"/><circle cx="${pts[pts.length-1][0]}" cy="${pts[pts.length-1][1]}" r="4" fill="${last>=0?'#34d399':'#f87171'}"/><text x="${pad}" y="12" fill="#9aa6b6" font-size="11" font-family="monospace">${mx>=0?'+':''}${mx}u</text><text x="${pad}" y="${H-3}" fill="#9aa6b6" font-size="11" font-family="monospace">${mn}u</text></svg>`;
  }
}




"""


# ============================ SHARP GRADING ============================
def grade_sharp(splits, soft_fair_game, num_bets=None, is_early_week=False, sport_kind='baseball'):
    teams=list(splits.keys())
    if len(teams)!=2: return None
    th=GRADE_THRESHOLDS.get(sport_kind, GRADE_THRESHOLDS['_default'])
    gaps={k:(splits[k]['money'] or 0)-(splits[k]['tickets'] or 0) for k in teams}
    sharp_side=max(teams,key=lambda k:gaps[k]); gap=gaps[sharp_side]
    tickets=splits[sharp_side]['tickets'] or 0; money=splits[sharp_side]['money'] or 0
    if gap<th['D']: return None
    contrarian=tickets<=35
    steam=False; steam_delta=None
    sf=soft_fair_game.get(sharp_side) if soft_fair_game else None
    odds=splits[sharp_side].get('odds')
    if sf is not None and odds is not None:
        _raw=(am2prob(odds)-sf)*100                   # pts of implied prob vs soft fair
        steam_delta=round(_raw,1)
        if _raw>1.5: steam=True                       # same threshold as before, unrounded
    # percentile-anchored, sport-specific: S/A require the tail AND contrarian confirmation
    if gap>=th['S'] and contrarian and steam: grade='S'
    elif (gap>=th['A'] and contrarian) or (gap>=th['S']): grade='A'
    elif gap>=th['B']: grade='B'
    elif gap>=th['C']: grade='C'
    else: grade='D'
    if not contrarian and tickets>=55: grade='D'   # money following the public = not sharp
    thin=(num_bets is not None and num_bets<1500); capped=False
    if (thin or is_early_week) and grade in ('S','A'): grade='B'; capped=True
    return {'side':sharp_side,'grade':grade,'gap':round(gap,1),'tickets':round(tickets),'money':round(money),
            'contrarian':contrarian,'steam':steam,'steam_delta':steam_delta,'num_bets':num_bets,
            'capped':capped,'thin':thin}

def am_str(o): o=int(round(float(o))); return ('+'+str(o)) if o>0 else str(o)
def pt_str(pt):
    if pt is None: return ''
    f=float(pt); s=('+'+str(f)) if f>0 else str(f); return s.replace('.0','')

# ============================ UNIT SIZING ============================
def suggest_units(card):
    """1u / 1.5u / 2u based on EV%, sharp confirmation, and a price cap.
    The price cap is the underdog guardrail: a long price is already its own reward,
    so longshots never earn more than 1u no matter how strong the signal."""
    sg = card.get('sharp_grade'); v = card.get('value_play')
    has_value = card.get('has_value'); rec = card.get('rec')
    if not rec: return (None, None)
    price = rec.get('price')
    try: price = float(price)
    except: price = None
    ev = v.get('ev') if v else None
    sharp_agrees = bool(sg and v and str(sg.get('side'))==str(v.get('side')) and sg.get('grade') in ('A','S'))
    grade = sg.get('grade') if sg else None
    longshot = (price is not None and price > 250)
    # 2u: rare back-up-the-truck: strong value + sharp agrees + not a longshot
    if has_value and ev is not None and ev >= 0.08 and sharp_agrees and price is not None and price <= 200:
        return (2.0, "Strong value + sharp agree, fair price")
    # 1.5u
    if has_value and ev is not None and 0.04 <= ev < 0.08 and not longshot:
        return (1.5, "Solid value, sharp confirms" if sharp_agrees else "Solid value edge")
    if (not has_value) and grade=='S' and sg.get('contrarian') and sg.get('steam') and not longshot:
        return (1.5, "Elite sharp signal (no price edge, so not 2u)")
    # 1u: any single real signal, or anything long-priced
    if has_value:
        return (1.0, "Value but longshot, capped 1u" if longshot else "Value present")
    if grade in ('S','A','B'):
        return (1.0, "Sharp lean, longshot: price is the reward" if longshot else "Single sharp signal")
    return (None, None)  # C/D no value = skip

def build_recommendation(c, sg):
    plays=c.get('plays',[]); v=c.get('value_play')
    def find_play(mkt,side):
        for p in plays:
            if p['mkt']==mkt and str(p['side'])==str(side): return p
        return None
    if v:
        mlabel=(c.get('spread_label') or 'Spread') if v['mkt']=='SPR' else ('Total' if v['mkt']=='TOT' else 'Moneyline')
        pt=pt_str(v.get('point')); sidetxt=f"{v['side']} {pt}".strip()
        agree=sg and str(v['side'])==str(sg['side'])
        cross=''
        if agree and v['mkt']!='ML': cross=f" (sharp money backs {sg['side']} to win; this {mlabel.lower()} is the value angle on the same side)"
        return {'type':'value','market':mlabel,'side':str(v['side']),'point':v.get('point'),'price':v['price'],
                'fair':v.get('fair'),'fair_mult':v.get('fair_mult'),'anchor':v.get('anchor'),'nb':v.get('nb'),
                'pin_price':v.get('pin_price'),'pin_opp':v.get('pin_opp'),
                'ex_back':v.get('ex_back'),'ex_lay':v.get('ex_lay'),'ex_mid':v.get('ex_mid'),
                'bo_price':v.get('bo_price'),'best_price':v.get('best_price'),'best_book':v.get('best_book'),
                'text':f"{mlabel} · {sidetxt} at {am_str(v['price'])}",
                'why':("Value + sharp agree: double-down." if agree else "Value bet (price beats fair value).")+cross,
                'double':bool(agree)}
    if sg and sg['grade'] in ('S','A','B','C'):
        ml=find_play('ML',sg['side']); sp=find_play('SPR',sg['side']); alts=[]
        if ml and ml.get('price') is not None: alts.append({'market':'Moneyline','point':None,'price':ml['price']})
        if sp and sp.get('price') is not None: alts.append({'market':c.get('spread_label') or 'Spread','point':sp.get('point'),'price':sp['price']})
        if alts:
            p0=alts[0]; pt=pt_str(p0['point']); sidetxt=f"{sg['side']} {pt}".strip()
            src=ml if (ml and ml.get('price') is not None) else sp   # play the rec is priced from
            return {'type':'sharp','market':p0['market'],'side':sg['side'],'point':p0['point'],'price':p0['price'],
                    'fair':(src or {}).get('fair'),'fair_mult':(src or {}).get('fair_mult'),
                    'anchor':(src or {}).get('anchor'),'nb':(src or {}).get('nb'),
                    'pin_price':(src or {}).get('pin_price'),'pin_opp':(src or {}).get('pin_opp'),
                    'ex_back':(src or {}).get('ex_back'),'ex_lay':(src or {}).get('ex_lay'),'ex_mid':(src or {}).get('ex_mid'),
                    'bo_price':(src or {}).get('bo_price'),'best_price':(src or {}).get('best_price'),'best_book':(src or {}).get('best_book'),
                    'text':f"{p0['market']} · {sidetxt} at {am_str(p0['price'])}",
                    'why':"Sharp signal is moneyline-based, so the ML is the cleanest expression. Alt markets shown if you want a different risk/reward.",
                    'alts':alts,'double':False}
    return None

# ============================ RESULTS TRACKER ============================
LEVELS = [
    {'from':10, 'to':20, 'min_bets':50,  'min_units':5,  'min_bankroll':800},
    {'from':20, 'to':50, 'min_bets':175, 'min_units':12, 'min_bankroll':2000},
]
def _bkey(p):
    """Dedupe key for logged plays. The Odds API event id is stable across runs and
    days, so it prevents two failure modes the old date-based key allowed: (1) a game
    scheduled for tomorrow getting logged again tomorrow under a new date, and (2)
    doubleheader games colliding. Legacy plays without an event id keep the old key."""
    eid=p.get('event_id')
    # Shadow rows live in their own key namespace, WITH the kind: on a double-down
    # game the sharp lean and the value flag are the same (event, market, side), and
    # both ledgers need their row (the S gradient must include every S game, the
    # value ledger every value game). Without the kind the second row silently drops.
    pre=f"sh|{p.get('shadow_kind') or ''}|" if p.get('shadow') else ''
    if eid: return f"{pre}{eid}|{p['market']}|{p['side']}"
    return f"{pre}{p['date']}|{p['away']}|{p['home']}|{p['market']}|{p['side']}"
def load_log(path):
    if os.path.exists(path):
        try: return json.load(open(path))
        except Exception:
            # A corrupt or half-written betlog must NEVER be silently replaced: the
            # caller saves right over it, so returning an empty log here would wipe all
            # history with no signal. Preserve the raw bytes to a timestamped sidecar
            # and alarm loudly, so the record is recoverable.
            try:
                if os.path.getsize(path)>0:
                    import shutil
                    bak=f"{path}.corrupt-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                    shutil.copyfile(path, bak)
                    print(f"  !! WARNING: {os.path.basename(path)} did not parse as JSON. "
                          f"Backed up the existing bytes to {os.path.basename(bak)} before "
                          f"continuing. History was NOT lost, restore from that file if needed.")
            except Exception: pass
    return {'plays':[]}
def save_log(path, log): json.dump(log, open(path,'w'), indent=2, default=str)
def log_plays(path, recs):
    log=load_log(path); existing={_bkey(p) for p in log['plays']}
    # One play per game: build_recommendation names ONE market per game, but the rec
    # can flip (ML in the morning, total in the afternoon) as prices move. Without this
    # guard both would log under different keys: correlated double exposure on one game
    # and a double-counted result. First logged play wins; later flips are skipped.
    # Shadow rows are excluded here on purpose: a pending zero-unit shadow on a game
    # must never block the real play from logging (exposure is a real-play concept).
    open_events={p.get('event_id') for p in log['plays'] if p.get('result') is None and p.get('event_id') and not p.get('shadow')}
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d'); added=0
    for r in recs:
        p=dict(r); p['date']=today; p['result']=None; p['units_pl']=None
        if p.get('event_id') and p['event_id'] in open_events: continue
        if _bkey(p) not in existing:
            log['plays'].append(p); existing.add(_bkey(p)); added+=1
            if p.get('event_id'): open_events.add(p['event_id'])
    save_log(path, log); return added

def build_shadow_plays(allc, now_iso):
    """SIGNAL LAB (shadow ledger, zero units, measurement only). The real betlog only
    ever receives hero plays (S/A grades and double-downs), so 'do C leans carry EV?'
    and 'does the value engine work when sharp money does not agree?' were structurally
    unanswerable: the data was never captured. FUTURE.md section 1 even asks to compare
    S/A vs B/C, which the real ledger cannot do on a uniform basis. This builds one
    zero-unit shadow row per pregame game for (a) the sharp side's MONEYLINE at Bovada
    for EVERY grade S through D (uniform basis: same market, same book, first-signal
    entry) and (b) the value play on every has_value game. Rows are flagged shadow=True,
    keyed in their own namespace, and excluded from the record, tracker, exposure,
    level gates, and the pre-registered clv_fair endpoint. They flow through the normal
    close-refresh and grading machinery, so each earns its own clv_fair: the same
    headline metric, on signals the tool deliberately does not bet. No suppressions
    apply (capture-or-lose: stale-anchor and news-window rows are stamped via
    pin_age_min and can be filtered in analysis; clv_fair itself only depends on the
    CLOSING fair, so entry-anchor staleness does not corrupt the shadow metric).
    Costs zero API credits: everything here is already fetched."""
    out=[]
    for sport,cards in allc.items():
        if sport.startswith('_'): continue
        for c in cards:
            if (hours_until(c.get('time')) or 0)<=0: continue          # clock guard, mirrors real entry
            if (c.get('status') or {}).get('state') not in (None,'scheduled'): continue
            base={'away':c['away'],'home':c['home'],'sport':sport,
                  'commence':c['time'],'event_id':c.get('event_id'),
                  'model_version':MODEL_VERSION,'run_ts':now_iso,
                  'hours_to_game':hours_until(c['time']),
                  'pin_age_min':c.get('pin_age_min'),
                  'units':0.0,'units_reason':None,'rec_type':None,
                  'shadow':True,'has_value':c.get('has_value')}
            sg=c.get('sharp_grade')
            if sg:
                mlp=next((p for p in c.get('plays',[]) if p['mkt']=='ML' and str(p['side'])==str(sg['side'])),None)
                if mlp and mlp.get('price') is not None:
                    out.append({**base,'shadow_kind':'sharp',
                                'market':'Moneyline','side':str(sg['side']),'point':None,'price':mlp['price'],
                                'grade':sg['grade'],'gap':sg.get('gap'),'tickets':sg.get('tickets'),
                                'money':sg.get('money'),'num_bets':sg.get('num_bets'),
                                'contrarian':sg.get('contrarian'),'steam':sg.get('steam'),
                                'steam_delta':sg.get('steam_delta'),
                                'ev':mlp.get('ev'),'fair':mlp.get('fair'),'fair_mult':mlp.get('fair_mult'),
                                'anchor':mlp.get('anchor'),'nb':mlp.get('nb'),
                                'pin_price':mlp.get('pin_price'),'pin_opp':mlp.get('pin_opp'),
                                'close_price':mlp['price'],'close_fair':mlp.get('fair'),
                                'close_anchor':mlp.get('anchor'),'close_point':None,
                                'close_ts':now_iso,'close_obs':0,'clv':None,'clv_fair':None})
            v=c.get('value_play')
            if c.get('has_value') and v and v.get('price') is not None:
                mlabel=(c.get('spread_label') or 'Spread') if v['mkt']=='SPR' else ('Total' if v['mkt']=='TOT' else 'Moneyline')
                out.append({**base,'shadow_kind':'value',
                            'market':mlabel,'side':str(v['side']),'point':v.get('point'),'price':v['price'],
                            'grade':(sg or {}).get('grade'),'gap':(sg or {}).get('gap'),
                            'tickets':(sg or {}).get('tickets'),'money':(sg or {}).get('money'),
                            'num_bets':(sg or {}).get('num_bets'),
                            'contrarian':(sg or {}).get('contrarian'),'steam':(sg or {}).get('steam'),
                            'steam_delta':(sg or {}).get('steam_delta'),
                            'ev':v.get('ev'),'fair':v.get('fair'),'fair_mult':v.get('fair_mult'),
                            'anchor':v.get('anchor'),'nb':v.get('nb'),
                            'pin_price':v.get('pin_price'),'pin_opp':v.get('pin_opp'),
                            'close_price':v['price'],'close_fair':v.get('fair'),
                            'close_anchor':v.get('anchor'),'close_point':v.get('point'),
                            'close_ts':now_iso,'close_obs':0,'clv':None,'clv_fair':None})
    return out

def log_shadow_plays(path, shadows):
    """Same freeze-on-first-sight discipline as log_plays, in the shadow namespace.
    One PENDING shadow per (event, kind): if the sharp side flips between the 15:00
    and 21:30 runs, the first observation wins, exactly like real entries freeze.
    Sharp and value shadows on the same game are both kept (different questions)."""
    if not shadows: return 0
    log=load_log(path); existing={_bkey(p) for p in log['plays']}
    open_shadow={(p.get('event_id'),p.get('shadow_kind'))
                 for p in log['plays']
                 if p.get('shadow') and p.get('result') is None and p.get('event_id')}
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d'); added=0
    for r in shadows:
        p=dict(r); p['date']=today; p['result']=None; p['units_pl']=None
        k=(p.get('event_id'),p.get('shadow_kind'))
        if p.get('event_id') and k in open_shadow: continue
        if _bkey(p) in existing: continue
        log['plays'].append(p); existing.add(_bkey(p))
        if p.get('event_id'): open_shadow.add(k)
        added+=1
    if added: save_log(path, log)
    return added

def _grade_one(p, res):
    """Returns 'win' / 'loss' / 'push' / None (None = cannot grade). Pushes MUST be
    graded as pushes: the old version returned None on a pushed line, which left the
    bet pending forever and quietly corrupted the pending count."""
    mkt=str(p['market']).lower(); side=p['side']; aw,hm=p['away'],p['home']
    ar,hr=res.get('away_runs'),res.get('home_runs')
    if ar is None or hr is None: return None
    if 'moneyline' in mkt or mkt=='ml':
        if side==aw: return 'win' if ar>hr else 'loss'
        if side==hm: return 'win' if hr>ar else 'loss'
        return None
    if any(k in mkt for k in ('run line','spread','handicap','puck')):
        pt=p.get('point')
        if pt is None: return None
        margin=(ar-hr) if side==aw else (hr-ar); adj=margin+float(pt)
        return 'win' if adj>0 else ('loss' if adj<0 else 'push')
    if 'total' in mkt or mkt=='o/u':
        pt=p.get('point')
        if pt is None: return None
        tot=ar+hr; pt=float(pt)
        if tot==pt: return 'push'
        return 'win' if ((tot>pt) if side=='Over' else (tot<pt)) else 'loss'
    return None
def _pick_result(p, cands):
    """Choose which final score belongs to this play. Results are now a LIST per
    matchup (backfill days + doubleheaders can produce several finals for the same
    away/home pair). Matching order: (1) game start time recorded on the play,
    (2) legacy plays: the play's log date vs the game's US calendar date,
    (3) only one candidate exists. Anything still ambiguous is honestly skipped."""
    if not cands: return None
    pc=p.get('commence')
    if pc:
        try:
            pt_=datetime.fromisoformat(str(pc).replace('Z','+00:00'))
            best=None; bestd=None
            for e in cands:
                st=e.get('start')
                if not st: continue
                d=abs((datetime.fromisoformat(str(st).replace('Z','+00:00'))-pt_).total_seconds())
                if bestd is None or d<bestd: best,bestd=e,d
            if best is not None and bestd is not None and bestd<=6*3600:
                return best
        except Exception: pass
    dt=p.get('date')
    if dt:
        matches=[]
        for e in cands:
            st=e.get('start')
            try:
                # minus 5h maps any US game start (roughly 16:00-03:00 UTC) onto its
                # US calendar date, which is what the play's log date represents
                sd=(datetime.fromisoformat(str(st).replace('Z','+00:00'))-timedelta(hours=5)).strftime('%Y-%m-%d')
            except Exception: continue
            if sd==dt: matches.append(e)
        if len(matches)==1: return matches[0]
    if len(cands)==1: return cands[0]
    return None

def grade_pending(path, results):
    log=load_log(path); n=0
    for p in log['plays']:
        if p.get('result') is not None: continue
        res=_pick_result(p, results.get((p['away'],p['home'])))
        if not res: continue
        outcome=_grade_one(p,res)
        if outcome is None: continue
        p['result']=outcome
        pr=float(p['price']); dec=am2dec(pr); u=float(p['units'])
        p['units_pl']=0.0 if outcome=='push' else (round(u*(dec-1),2) if outcome=='win' else round(-u,2)); n+=1
        # Closing line value, two flavors:
        # clv      = entry price vs the last pregame BOVADA price seen (same-book line movement).
        # clv_fair = stated-EV formula re-run with the CLOSING fair probability (devigged,
        #            Pinnacle-anchored when available): the market's final verdict on the
        #            bet's EV. This answers "should CLV be measured vs Pinnacle?" correctly,
        #            in probability space, instead of mixing two books' vigged prices.
        # clv_measured = True only if at least one post-entry pregame observation updated
        # the close. Plays are seeded with close=entry at log time so nothing is ever
        # silently dropped, but seeded values carry no information: stats exclude them.
        cp=p.get('close_price')
        if cp is not None:
            try: p['clv']=round((am2dec(p['price'])/am2dec(cp)-1)*100,2)
            except Exception: p['clv']=None
        cf=p.get('close_fair')
        if cf is not None:
            try: p['clv_fair']=round((float(cf)*am2dec(p['price'])-1)*100,2)
            except Exception: p['clv_fair']=None
        p['clv_measured']=bool((p.get('close_obs') or 0)>0)
    # Void pass: a play still pending 72h after its scheduled start is voided.
    # The score backfill covers 3 days; if that window produced no matchable final,
    # the game was postponed, cancelled, or rescheduled outside the 6h match window.
    # Sportsbooks void (refund) such bets, so 'void' mirrors real settlement:
    # units_pl 0, excluded from the record like pushes. Without this, a rainout
    # sits pending forever, polluting the pending count and open-exposure total.
    now=datetime.now(timezone.utc)
    for p in log['plays']:
        if p.get('result') is not None: continue
        age_from=None
        try:
            age_from=datetime.fromisoformat(str(p.get('commence')).replace('Z','+00:00'))
        except Exception:
            try:
                # legacy play without commence: age off the log date plus a day of margin
                age_from=datetime.strptime(p['date'],'%Y-%m-%d').replace(tzinfo=timezone.utc)+timedelta(hours=24)
            except Exception:
                continue
        if now-age_from>timedelta(hours=72):
            p['result']='void'; p['units_pl']=0.0
            p['void_reason']='no matchable final within 72h of scheduled start (postponed, cancelled, or rescheduled)'
            n+=1
    save_log(path, log); return n

MARKET_TO_MKT={'moneyline':'ML','run line':'SPR','spread':'SPR','asian handicap':'SPR','puck line':'SPR','total':'TOT'}
def update_closes(path, allc):
    """While a logged bet's game is still pregame, keep refreshing close_price (Bovada,
    same market/side/point) and close_fair (devigged fair prob, Pinnacle-anchored when
    available) with the latest observation. The stored value is the last pregame reading
    we saw: an honest approximation of the close given the run schedule. Plays are
    SEEDED with close=entry at log time; close_obs counts post-entry observations, and
    only close_obs>0 plays count as measured CLV (seeded values carry no information).

    Two guards matter here:
    1. Pregame is checked by the CLOCK (commence_time in the future), not only the
       status feed. If Action Network is down, every game defaults to 'scheduled' and
       the old code would happily overwrite the close with LIVE in-play prices, which
       silently corrupts CLV, the primary validation metric.
    2. Cards are matched by event id when the play has one (doubleheader-proof);
       matchup-name matching is only trusted when it is unambiguous."""
    log=load_log(path); touched=0
    by_eid={}; by_matchup={}
    for sport,cs in allc.items():
        if sport.startswith('_'): continue
        for c in cs:
            if c.get('event_id'): by_eid[c['event_id']]=c
            by_matchup.setdefault((c['away'],c['home']),[]).append(c)
    for p in log['plays']:
        if p.get('result') is not None: continue
        c=by_eid.get(p.get('event_id'))
        if c is None:
            lst=by_matchup.get((p['away'],p['home']),[])
            c=lst[0] if len(lst)==1 else None
        if not c: continue
        hu=hours_until(c.get('time'))
        if (c.get('status') or {}).get('state')!='scheduled' or hu is None or hu<=0: continue
        want=MARKET_TO_MKT.get(str(p.get('market','')).lower())
        if not want: continue
        for pl in c.get('plays',[]):
            if pl['mkt']==want and str(pl['side'])==str(p['side']):
                same_pt=(pl.get('point')==p.get('point')) or (want=='ML')
                if same_pt and pl.get('price') is not None:
                    p['close_price']=pl['price']
                    # the closing FAIR probability (devigged, Pinnacle-anchored when
                    # available) powers clv_fair, the market's final EV verdict
                    if pl.get('fair') is not None:
                        p['close_fair']=pl['fair']; p['close_anchor']=pl.get('anchor')
                    p['close_point']=pl.get('point')
                    p['close_ts']=datetime.now(timezone.utc).isoformat()
                    p['close_obs']=int(p.get('close_obs') or 0)+1
                    touched+=1
                elif pl.get('point') is not None:
                    # Bovada moved the line off our entry point: the same-line close
                    # freezes (prices at different lines are not comparable), but record
                    # where the line went so the movement itself is not lost forever.
                    p['close_line_moved']=pl.get('point')
                break
    if touched: save_log(path, log)
    return touched
def append_runlog(path, entry, keep=500):
    """Per-run health record (item 13): tiny append-only file, trimmed to the last
    500 runs (~5 months at 3/day) to respect the F13 whole-file-rewrite pattern.
    Feeds the dashboard health strip; never contains plays or prices."""
    try: rl=json.load(open(path)) if os.path.exists(path) else {'runs':[]}
    except Exception: rl={'runs':[]}
    runs=(rl.get('runs') or [])[-(keep-1):]
    runs.append(entry); rl['runs']=runs
    json.dump(rl, open(path,'w'))
    return runs

def tracker_summary(path, current_unit):
    log=load_log(path)
    real=[p for p in log['plays'] if not p.get('shadow')]   # shadow rows are measurement, never exposure
    settled=[p for p in real if p.get('result') in ('win','loss')]
    n=len(settled); wins=sum(1 for p in settled if p['result']=='win')
    units_pl=round(sum(p.get('units_pl',0) or 0 for p in settled),2)
    biggest=max((p.get('units_pl',0) or 0 for p in settled), default=0)
    concentrated=(units_pl>0 and biggest>0.6*units_pl and n>5)
    nxt=next((lv for lv in LEVELS if current_unit==lv['from']), None)
    progress=None
    if nxt:
        progress={'to':nxt['to'],'bets_done':n,'bets_need':nxt['min_bets'],
                  'units_done':units_pl,'units_need':nxt['min_units'],'bankroll_need':nxt['min_bankroll'],
                  'ready':(n>=nxt['min_bets'] and units_pl>=nxt['min_units'] and not concentrated)}
    pend=[p for p in real if p.get('result') is None]
    open_units=round(sum(float(p.get('units') or 0) for p in pend),2)
    return {'n':n,'wins':wins,'losses':n-wins,'units_pl':units_pl,
            'pushes':len([p for p in real if p.get('result')=='push']),
            'voids':len([p for p in real if p.get('result')=='void']),
            'pending':len(pend),'open_units':open_units,'max_daily_units':MAX_DAILY_UNITS,
            'concentrated':concentrated,'progress':progress,'current_unit':current_unit}

def collect_results(sharp_raw_by_league):
    """Pull final scores from every Action Network payload fetched this run (today
    plus several days of backfill). Returns {(away,home): [finals...]}, each final
    carrying its start_time so grading can match a logged play to the CORRECT game.
    This replaces the old single-payload AMBIG flag, which would have wrongly marked
    the same matchup on consecutive backfill days as ambiguous and skipped both."""
    out={}
    for raw in sharp_raw_by_league:
        for g in (raw.get('games',[]) if raw else []):
            if g.get('status') not in ('complete','closed'): continue
            def nm(tid):
                for t in g.get('teams',[]):
                    if t['id']==tid: return t.get('full_name')
            bs=g.get('boxscore') or {}; stats=bs.get('stats') or {}
            ar=(stats.get('away') or {}).get('runs'); hr=(stats.get('home') or {}).get('runs')
            if ar is None or hr is None: continue
            k=(nm(g['away_team_id']),nm(g['home_team_id']))
            entry={'away_runs':ar,'home_runs':hr,'start':g.get('start_time')}
            lst=out.setdefault(k,[])
            if not any(e.get('start')==entry['start'] for e in lst):
                lst.append(entry)
    return out

def hours_until(iso):
    try:
        start=datetime.fromisoformat(iso.replace('Z','+00:00'))
        return round((start-datetime.now(timezone.utc)).total_seconds()/3600.0, 2)
    except: return None

def log_snapshots(path, allc):
    """Append one row per game that has a sharp grade this run. F13/F41: the live
    file holds ONLY the current month (rewritten each run, bounded size); at each
    month boundary, prior-month rows roll to <path stem>_YYYY-MM.json, written once
    and never rewritten. Nothing is ever deleted. Every row carries model_version
    so any future analysis can segment snapshot-derived features by model era."""
    snaps=[]
    if os.path.exists(path):
        try: snaps=json.load(open(path)).get('snaps',[])
        except: snaps=[]
    run_ts=datetime.now(timezone.utc).isoformat()
    cur_month=run_ts[:7]
    old_rows=[r for r in snaps if str(r.get('run_ts',''))[:7]!=cur_month]
    if old_rows:
        try:
            by_m={}
            for r in old_rows: by_m.setdefault(str(r.get('run_ts',''))[:7] or 'unknown',[]).append(r)
            for m,rows in by_m.items():
                ap=path.replace('.json','')+f'_{m}.json'
                existing=[]
                if os.path.exists(ap):
                    try: existing=json.load(open(ap)).get('snaps',[])
                    except: existing=[]
                json.dump({'snaps':existing+rows}, open(ap,'w'))
            snaps=[r for r in snaps if str(r.get('run_ts',''))[:7]==cur_month]
            print(f"    snapshots: rolled {len(old_rows)} prior-month row(s) to archive")
        except Exception as e:
            print(f"    ! snapshot rotation skipped: {e}")
    for sport,cards in allc.items():
        if sport.startswith('_'): continue
        for c in cards:
            sg=c.get('sharp_grade')
            if not sg: continue
            snaps.append({
                'run_ts':run_ts,'model_version':MODEL_VERSION,'sport':sport,'game':f"{c['away']} @ {c['home']}",
                'away':c['away'],'home':c['home'],'commence':c['time'],
                'hours_to_game':hours_until(c['time']),
                'sharp_side':sg['side'],'grade':sg['grade'],'gap':sg['gap'],
                'tickets':sg['tickets'],'money':sg['money'],
                'contrarian':sg['contrarian'],'steam':sg['steam'],
                'has_value':c.get('has_value'),
                'rec_price':(c.get('rec') or {}).get('price'),
                'rec_market':(c.get('rec') or {}).get('market'),
                'rec_side':(c.get('rec') or {}).get('side'),
                'ev':(c.get('value_play') or {}).get('ev'),
                'fair':(c.get('value_play') or {}).get('fair'),
                'fair_mult':(c.get('value_play') or {}).get('fair_mult'),
                'nb':(c.get('value_play') or {}).get('nb'),
                'anchor':(c.get('value_play') or {}).get('anchor'),
                'event_id':c.get('event_id'),
                'units':c.get('units'),
                'books_h2h':c.get('_books_h2h'),'h2h_disp':c.get('_h2h_disp'),
                'an_ml':c.get('an_ml'),
                'ex_back':c.get('_ex_back'),'ex_lay':c.get('_ex_lay'),
                'ml_ex_mid':next((p.get('ex_mid') for p in c.get('plays',[]) if p['mkt']=='ML' and p.get('ex_mid') is not None),None),
            })
    json.dump({'snaps':snaps}, open(path,'w'), default=str)
    return len(snaps)

def write_csv(path, rows, cols):
    import csv
    with open(path,'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in rows: w.writerow(r)

def compute_stats(log_path, snap_path, unit_dollars):
    """Aggregate settled bets into success/profitability by grade, unit size, market,
    value-vs-sharp, price bucket, and hours-to-game. Also pull edge-over-time from snapshots."""
    log=load_log(log_path)
    # Shadow rows (signal lab) are excluded from EVERY aggregate below, including the
    # pre-registered clv_fair endpoint: mixing zero-unit measurement rows into the
    # record or the primary metric would move the goalposts. They get their own
    # section at the bottom.
    plays_real=[p for p in log['plays'] if not p.get('shadow')]
    settled=[p for p in plays_real if p.get('result') in ('win','loss')]
    def agg(rows):
        n=len(rows); w=sum(1 for r in rows if r['result']=='win')
        risked=sum(float(r.get('units',1)) for r in rows)
        pl=round(sum(r.get('units_pl',0) or 0 for r in rows),2)
        roi=round(100*pl/risked,1) if risked>0 else None
        return {'n':n,'wins':w,'losses':n-w,'win_pct':round(100*w/n,1) if n else None,
                'units_pl':pl,'roi':roi,'dollars':round(pl*unit_dollars)}
    def by(keyfn, order=None):
        buckets={}
        for r in settled:
            k=keyfn(r)
            if k is None: continue
            buckets.setdefault(k,[]).append(r)
        out={k:agg(v) for k,v in buckets.items()}
        if order: out={k:out[k] for k in order if k in out}
        return out
    def price_bucket(r):
        try: p=float(r['price'])
        except: return None
        if p<=-150: return 'chalk (≤-150)'
        if p<100: return 'short (-150..-100)'
        if p<=150: return 'pick (+100..+150)'
        if p<=250: return 'dog (+150..+250)'
        return 'longdog (+250+)'
    def htg_bucket(r):
        h=r.get('hours_to_game')
        if h is None: return None
        if h<1: return '<1h'
        if h<3: return '1-3h'
        if h<6: return '3-6h'
        return '6h+'
    overall=agg(settled)
    overall['pending']=len([p for p in plays_real if p.get('result') is None])
    overall['pushes']=len([p for p in plays_real if p.get('result')=='push'])
    overall['voids']=len([p for p in plays_real if p.get('result')=='void'])
    # cumulative units over time (by date)
    from collections import OrderedDict
    cum=OrderedDict(); running=0.0
    for r in sorted(settled, key=lambda x:x.get('date','')):
        running+=(r.get('units_pl',0) or 0); cum[r.get('date','?')]=round(running,2)
    # edge-over-time from snapshots: avg gap by hours-to-game bucket
    edge_time={}
    if os.path.exists(snap_path):
        try: snaps=json.load(open(snap_path)).get('snaps',[])
        except: snaps=[]
        b={}
        for s in snaps:
            h=s.get('hours_to_game')
            if h is None: continue
            k='<1h' if h<1 else '1-3h' if h<3 else '3-6h' if h<6 else '6h+'
            b.setdefault(k,[]).append(s.get('gap',0))
        edge_time={k:round(sum(v)/len(v),1) for k,v in b.items() if v}
    # CLV: the fastest truth-teller. Positive average CLV over 50+ bets is the
    # strongest evidence of a real edge, long before W/L stabilizes.
    # Only MEASURED closes count (at least one post-entry pregame observation);
    # entry-seeded closes are excluded, NOT averaged in as zeros, which would
    # dilute the metric toward 0 and quietly hide the coverage problem.
    graded_all=[p for p in plays_real if p.get('result') is not None]
    def _measured(p):
        if 'clv_measured' in p: return bool(p.get('clv_measured'))
        return p.get('clv') is not None   # legacy plays: close was only ever set post-entry
    meas=[p for p in graded_all if _measured(p)]
    clvs=[p['clv'] for p in meas if p.get('clv') is not None]
    fairs=[p['clv_fair'] for p in meas if p.get('clv_fair') is not None]
    clv={'n_graded':len(graded_all),'n_measured':len(meas),
         'coverage':round(100*len(meas)/len(graded_all)) if graded_all else None,
         'n':len(clvs),
         'avg':round(sum(clvs)/len(clvs),2) if clvs else None,
         'pos_pct':round(100*sum(1 for c in clvs if c>0)/len(clvs)) if clvs else None,
         'fair_n':len(fairs),
         'fair_avg':round(sum(fairs)/len(fairs),2) if fairs else None,
         'fair_pos':round(100*sum(1 for c in fairs if c>0)/len(fairs)) if fairs else None}
    # Expected vs realized (item 13): the earliest read on whether stated edges are
    # inflated. Settled only; voided bets never had money at risk.
    evs=[p for p in settled if p.get('ev') is not None and p.get('units')]
    ev_real=None
    if evs:
        exp=round(sum(float(p['units'])*float(p['ev']) for p in evs),2)
        act=round(sum(p.get('units_pl') or 0 for p in evs),2)
        ev_real={'n':len(evs),'exp':exp,'act':act,'gap':round(act-exp,2)}
    # Rolling EV-at-close vs cumulative (item 17 decay detection), measured plays only,
    # ordered by date then run_ts
    fair_seq=[x[2] for x in sorted((p.get('date') or '', p.get('run_ts') or '', p['clv_fair'])
              for p in meas if p.get('clv_fair') is not None)]
    WIN=20
    clv_roll=({'n':len(fair_seq),'win':min(WIN,len(fair_seq)),
               'roll':round(sum(fair_seq[-WIN:])/len(fair_seq[-WIN:]),2),
               'cum':round(sum(fair_seq)/len(fair_seq),2)} if fair_seq else None)
    # Segment means (EXPLORATORY: pre-registered primary endpoint is overall clv_fair;
    # segments are hypothesis generators, never victory conditions, see AUDIT_TODO F32)
    def _seg(keyfn):
        d={}
        for p in meas:
            if p.get('clv_fair') is None: continue
            k=keyfn(p)
            if k: d.setdefault(k,[]).append(p['clv_fair'])
        return [{'k':k,'n':len(v),'avg':round(sum(v)/len(v),2)} for k,v in sorted(d.items())]
    def _run_hr(p):
        ts=p.get('run_ts') or ''
        return (ts[11:13]+':xx UTC run') if len(ts)>=13 else None
    _sports_present={p.get('sport') for p in meas if p.get('sport')}
    clv_seg={'rows':(_seg(lambda p:(p.get('sport') or '').upper() or None) if len(_sports_present)>1 else [])
                    +_seg(lambda p:p.get('market'))+_seg(_run_hr)}
    def ev_bucket(r):
        e=r.get('ev')
        if e is None: return 'sharp only (no price edge)'
        return '3-5%' if e<0.05 else '5-8%' if e<0.08 else '8%+'
    # ---- Signal lab (shadow ledger): the sharp-grade gradient S through D on a
    # uniform basis (sharp-side ML at Bovada, first-signal entry), plus the raw
    # value flag. flat_pl/flat_roi assume a hypothetical flat 1u per row; the
    # comparable headline is fair_avg (EV at close), same metric as real plays,
    # measured closes only. Exploratory always: never a level gate, never the
    # pre-registered endpoint.
    sh=[p for p in log['plays'] if p.get('shadow')]
    shadow=None
    if sh:
        def _sh_agg(rows):
            graded=[p for p in rows if p.get('result') in ('win','loss')]
            w=sum(1 for p in graded if p['result']=='win'); fl=0.0
            for p in graded:
                try: fl+=(am2dec(float(p['price']))-1) if p['result']=='win' else -1.0
                except Exception: pass
            meas=[p for p in graded if p.get('clv_measured') and p.get('clv_fair') is not None]
            return {'n':len(rows),'graded':len(graded),'wins':w,
                    'win_pct':round(100*w/len(graded),1) if graded else None,
                    'flat_pl':round(fl,2),
                    'flat_roi':round(100*fl/len(graded),1) if graded else None,
                    'fair_n':len(meas),
                    'fair_avg':round(sum(p['clv_fair'] for p in meas)/len(meas),2) if meas else None}
        rows={}
        for g in ('S','A','B','C','D'):
            rr=[p for p in sh if p.get('shadow_kind')=='sharp' and p.get('grade')==g]
            if rr: rows[g]=_sh_agg(rr)
        vv=[p for p in sh if p.get('shadow_kind')=='value']
        if vv: rows['value flag']=_sh_agg(vv)
        shadow={'rows':rows,'pending':len([p for p in sh if p.get('result') is None])}
    return {'overall':overall,
            'shadow':shadow,
            'clv':clv,'ev_real':ev_real,'clv_roll':clv_roll,'clv_seg':clv_seg,
            'by_ev':by(ev_bucket, order=['3-5%','5-8%','8%+','sharp only (no price edge)']),
            'by_grade':by(lambda r:r.get('grade'), order=['S','A','B','C','D']),
            'by_units':by(lambda r:f"{r.get('units')}u"),
            'by_market':by(lambda r:r.get('market')),
            'by_signal':by(lambda r:'value+sharp' if r.get('has_value') and r.get('grade') in ('S','A','B') else ('value' if r.get('has_value') else 'sharp-only')),
            'by_price':by(price_bucket),
            'by_htg':by(htg_bucket),
            'cumulative':list(cum.items()),
            'edge_by_htg':edge_time,
            'unit_dollars':unit_dollars}

# ============================ MAIN ============================
def main():
    here=os.path.dirname(os.path.abspath(__file__))
    hist=os.path.join(here, HISTORY_FOLDER)
    os.makedirs(hist, exist_ok=True)   # create history folder if missing
    print("RidgeSeeker: fetching fresh data...")
    print(f"  (python {sys.version.split()[0]} · {ssl.OPENSSL_VERSION})\n")
    if not ODDS_KEY:
        print("  !! No Odds API key found. Set the ODDS_KEY env var (GitHub secret) or put")
        print("     the key in odds_key.txt next to this script for local runs.\n")
    allc={}
    run_odds_games=0; run_an_games=0; run_unmatched=0; run_bov_absent=0
    _asp=active_sports()
    _per_full=(3 if BOOKMAKERS_PARAM else 6); _per_close=(1 if BOOKMAKERS_PARAM else 2)
    _proj=len(_asp)*(2*_per_full+_per_close)*30
    if _proj>PLAN_CREDITS:
        print(f"  !! CREDIT WARNING: {len(_asp)} active sport(s) at 2 full + 1 close/day projects ~{_proj}/month vs plan {PLAN_CREDITS}. Fix: fewer sports, RS_BOOKMAKERS after the F26 curl, or the $30 20K plan (set PLAN_CREDITS=20000).")
    raw_payloads=[]
    for sp in active_sports():
        key, skey, kind, an = sp['key'], sp['odds'], sp['kind'], sp['an']
        print(f"  [{key.upper()}] odds...", end=" ", flush=True)
        odds=fetch_odds(skey, markets=("h2h" if RUN_MODE=='close' else "h2h,spreads,totals"))
        print(f"{len(odds)} games", end="")
        sharp_map, status_map, raw = fetch_sharp_and_status(an)
        if raw: raw_payloads.append(raw)
        raw_payloads.extend(fetch_scores_for_dates(an))   # grade night games + missed days
        sf = soft_fair_map(odds)
        cards=[]
        for g in odds:
            c=analyze_game(g, kind, {k:v['splits'] for k,v in sharp_map.items()}, status_map, sf)
            # grade
            sm=sharp_map.get((c['away'],c['home']))
            if sm and not _an_same_game(sm, c['time']): sm=None   # F45: wrong-day splits never attach
            if sm is None:
                c['sharp']=None   # F45: board chips must not show yesterday's splits either
            c['an_ml']=(sm or {}).get('an_ml')   # F45c: an_ml now actually reaches cards
            sg=None
            if sm: sg=grade_sharp(sm['splits'], c['_soft_fair'], num_bets=sm.get('num_bets'), sport_kind=kind)
            c['sharp_grade']=sg
            c['rec']=build_recommendation(c, sg) if (hours_until(c['time']) or 0)>0 else None
            u, ureason = suggest_units(c)
            c['units']=u; c['units_reason']=ureason
            c['unit_dollars']=UNIT_DOLLARS
            # strip internal keys
            c.pop('_sharp_raw',None); c.pop('_soft_fair',None)
            cards.append(c)
        allc[key]=cards
        run_odds_games+=len(cards); run_an_games+=len(sharp_map)
        # Bovada listed nothing while the consensus priced the game: a line freeze or
        # suspension marker (item 16); alarmed on the health strip, logged in the runlog
        run_bov_absent+=sum(1 for c in cards if c.get('_books_h2h') and 'Bovada' not in c['_books_h2h'])
        g_ct=sum(1 for c in cards if c['sharp_grade'])
        print(f"  ·  {g_ct} sharp-graded")
        # Name-join alarm: the two APIs are joined on (away, home) full names. A silent
        # mismatch (a team rename, an "Athletics" style change) kills sharp data AND
        # grading for that team with no symptom. Only scheduled AN games should exist
        # in the odds feed, so alarm on those; finished games dropping out is normal.
        odds_keys={(c['away'],c['home']) for c in cards}
        unmatched=[k for k in sharp_map if k not in odds_keys and (status_map.get(k) or {}).get('state')=='scheduled'] if cards else []
        if unmatched:
            print(f"    ! name-join alarm: {len(unmatched)} AN game(s) with splits matched no Odds API game: {unmatched}")
        run_unmatched+=len(unmatched)
    # ---- persistence paths + one-time migration (both run modes need these) ----
    log_path=os.path.join(here, "ridgeseeker_betlog.json")
    snap_path=os.path.join(here, "ridgeseeker_snapshots.json")
    runlog_path=os.path.join(here, "ridgeseeker_runlog.json")
    # one-time migration: adopt the old EdgeFinder files so no history is lost
    for old,new in [("edgefinder_betlog.json",log_path),("edgefinder_snapshots.json",snap_path)]:
        op=os.path.join(here,old)
        if os.path.exists(op) and not os.path.exists(new):
            try:
                import shutil; shutil.copyfile(op,new); print(f"  (migrated {old} -> {os.path.basename(new)})")
            except Exception as e: print(f"  ! migration failed for {old}: {e}")

    # ---- close-capture mode: refresh closes + grade, then stop ----
    # Cheap run (h2h only, 2 credits) fired shortly before the evening slate so night
    # games get a close observation much nearer first pitch, and plays logged at the
    # 21:30 run get a close at all. Never logs plays (an h2h-only board would bias
    # play selection), never snapshots (keeps the edge-over-time cadence clean),
    # never rebuilds the dashboard. Spread/total closes freeze at the last full-run
    # observation in this mode; that is deliberate and labeled in the docs.
    if RUN_MODE=='close':
        touched=update_closes(log_path, allc)
        graded=grade_pending(log_path, collect_results(raw_payloads))
        append_runlog(runlog_path, {'ts':datetime.now(timezone.utc).isoformat(),'mode':'close',
            'model_version':MODEL_VERSION,'odds_games':run_odds_games,'an_games':run_an_games,
            'unmatched':run_unmatched,'bov_absent':run_bov_absent,'ctx_misses':None,
            'plays_logged':0,'closes':touched,'graded':graded})
        print(f"\nClose-capture run done: refreshed {touched} close(s), graded {graded} bet(s).")
        print("No plays logged, no dashboard rebuilt (h2h only, 2 API credits).")
        return

    # build _top
    GORD={'S':5,'A':4,'B':3,'C':2,'D':1,None:0}
    top=[]
    for sport,cards in allc.items():
        for c in cards:
            sg=c.get('sharp_grade'); rec=c.get('rec')
            if (sg and sg['grade'] in ('S','A')) or (rec and rec.get('double')):
                vp=c.get('value_play') or {}
                top.append({'sport':sport.upper(),'away':c['away'],'home':c['home'],'time':c['time'],
                            'event_id':c.get('event_id'),
                            'grade':sg['grade'] if sg else None,'rec':rec,'sg':sg,'has_value':c.get('has_value'),
                            'status':c.get('status'),'units':c.get('units'),'units_reason':c.get('units_reason'),
                            'ev':vp.get('ev'),'fair':vp.get('fair'),'fair_mult':vp.get('fair_mult'),'anchor':vp.get('anchor'),
                            'pin_age_min':c.get('pin_age_min'),
                            'unit_dollars':UNIT_DOLLARS})
    top.sort(key=lambda x:(-(2 if x['rec'] and x['rec'].get('double') else 0), -GORD.get(x['grade'],0)))
    allc['_top']=top

    # ---- results tracker ----
    # 0. refresh close prices for pending pregame bets (CLV needs the last pregame price)
    touched=update_closes(log_path, allc)
    # 1. grade any pending bets we now have final scores for
    results=collect_results(raw_payloads)
    graded=grade_pending(log_path, results)
    # 2. log today's recommended plays with full feature set (grade, gap, hours-to-game)
    todays=[]
    now_iso=datetime.now(timezone.utc).isoformat()
    mlb_ctx=fetch_mlb_context()   # F29 log-only features, free, one keyless call
    ctx_misses=0
    probables_path=os.path.join(here, "ridgeseeker_probables.json")
    scratches=detect_scratches(mlb_ctx, probables_path) if mlb_ctx else {}
    _vc={}
    for _v in mlb_ctx.values():
        if _v.get('venue') and _v.get('mlb_gamePk'):
            _vc.setdefault(_v['venue'], None)
    # per-venue commence: earliest game at that venue today (weather at start hour)
    for t in top:
        _cx=mlb_ctx.get((t['away'],t['home']))
        if _cx and _cx.get('venue') and _vc.get(_cx['venue']) is None:
            _vc[_cx['venue']]=t['time']
    wx=fetch_park_weather({v:c for v,c in _vc.items() if c}) if _vc else {}
    pm_kal,pm_pol,pm_counts=fetch_prediction_markets([sp['key'] for sp in _asp])
    pm_miss=0; stale_skips=0; news_skips=0
    for t in top:
        # Pregame is checked by the CLOCK, not only the AN status feed (state is None
        # for every game when AN is down, and a delayed or manual run mid-slate would
        # otherwise log LIVE in-play prices as pregame entries: same bug class F6
        # fixed for closes, now guarded at entry where the money decision is made).
        if t.get('units') and t.get('rec') and (t.get('status') or {}).get('state') in (None,'scheduled') and (hours_until(t['time']) or 0)>0:
            r=t['rec']; sg=t.get('sg') or {}
            # fair/anchor: the value play's when there is one, else the rec's own side
            # (previously sharp-only plays logged fair=None even though it was computed:
            # a capture-now-or-lose-forever field)
            fair=t.get('fair') if t.get('fair') is not None else r.get('fair')
            fmult=t.get('fair_mult') if t.get('fair_mult') is not None else r.get('fair_mult')
            anchor=t.get('anchor') if t.get('anchor') is not None else r.get('anchor')
            play={'away':t['away'],'home':t['home'],'sport':t['sport'],
                           'market':r['market'],'side':str(r['side']),'point':r.get('point'),
                           'price':r['price'],'units':t['units'],'units_reason':t.get('units_reason'),
                           'rec_type':r.get('type'),
                           'grade':t.get('grade'),'gap':sg.get('gap'),
                           'tickets':sg.get('tickets'),'money':sg.get('money'),
                           'num_bets':sg.get('num_bets'),
                           'contrarian':sg.get('contrarian'),'steam':sg.get('steam'),
                           'steam_delta':sg.get('steam_delta'),
                           'has_value':t.get('has_value'),
                           'ev':t.get('ev'),'fair':fair,'fair_mult':fmult,'anchor':anchor,
                           'nb':r.get('nb'),'pin_price':r.get('pin_price'),'pin_opp':r.get('pin_opp'),
                           'ex_back':r.get('ex_back'),'ex_lay':r.get('ex_lay'),'ex_mid':r.get('ex_mid'),
                           'bo_price':r.get('bo_price'),'best_price':r.get('best_price'),'best_book':r.get('best_book'),
                           'commence':t['time'],'event_id':t.get('event_id'),
                           'model_version':MODEL_VERSION,'run_ts':now_iso,
                           # close fields SEEDED with the entry snapshot so every play can
                           # be graded for CLV; close_obs counts post-entry observations
                           # and only close_obs>0 counts as measured (see update_closes)
                           'close_price':r['price'],'close_fair':fair,'close_anchor':anchor,
                           'close_point':r.get('point'),'close_ts':now_iso,'close_obs':0,
                           'clv':None,'clv_fair':None,
                           'hours_to_game':hours_until(t['time'])}
            # Research-pass suppressions (v14, MODEL_VERSION bump): (a) a VALUE rec
            # anchored on a stale Pinnacle quote is a phantom-edge candidate: label
            # it on the board and do NOT log it; (b) any rec on a game whose probable
            # pitcher changed THIS run sits out one cycle: the market is mid-move on
            # news and our anchor may itself be stale (information-window rule).
            _skip=None
            # gamePk lives on the MLB context, not on `play` (the context fields are
            # attached only AFTER this block, so play.get('mlb_gamePk') was always None
            # and this suppression never fired). Read it from mlb_ctx; scratch keys are
            # str(gamePk). The rec's market-type key is 'type', not 'rec_type' (that key
            # only exists on `play`), and pin_age_min is now threaded onto `t` above, so
            # both suppressions can finally fire as the v14 comment intended.
            _gp=(mlb_ctx.get((t['away'],t['home'])) or {}).get('mlb_gamePk') if t.get('sport')=='mlb' else None
            if scratches and _gp is not None and str(_gp) in scratches:
                _skip='news'
            elif r.get('type')=='value' and r.get('anchor')=='pinnacle' and (t.get('pin_age_min') or 0)>PIN_STALE_MIN:
                _skip='stale'
            if _skip:
                if _skip=='news':
                    news_skips+=1; t['rec']['text']='(news window, not logged this run) '+t['rec']['text']
                else:
                    stale_skips+=1; t['rec']['text']='(stale Pinnacle quote, not logged) '+t['rec']['text']
                continue
            # Prediction-market quotes for our side (F39, LOG-ONLY). fair = the
            # devigged Pinnacle-anchored prob already on the rec.
            play['kalshi_ticker']=play['kalshi_bid']=play['kalshi_ask']=play['kalshi_ev_taker']=play['kalshi_ev_maker']=None
            play['poly_mid']=play['poly_bid']=play['poly_ask']=play['poly_ev_mid']=None
            _fairp=r.get('fair')
            if r.get('market')=='Moneyline':
                _side=str(r.get('side'))
                if t.get('sport')=='mlb':
                    _ca,_cb=KALSHI_MLB.get(t['away']),KALSHI_MLB.get(t['home'])
                    _my=KALSHI_MLB.get(_side)
                    _evs=pm_kal.get(frozenset({_ca,_cb})) if (_ca and _cb) else None
                    if _evs and _my:
                        _e=min(_evs,key=lambda e:abs((datetime.fromisoformat(str(e.get('close')).replace('Z','+00:00'))-datetime.fromisoformat(str(t['time']).replace('Z','+00:00'))).total_seconds()) if e.get('close') else 9e9)
                        _q=_e['teams'].get(_my)
                        if _q:
                            play['kalshi_ticker']=_q.get('ticker'); play['kalshi_bid']=_q.get('bid'); play['kalshi_ask']=_q.get('ask')
                            _n=max(1,int(float(r.get('units') or 1.0)*UNIT_DOLLARS/max(_q.get('ask') or 0.5,0.01)))
                            play['kalshi_n']=_n
                            play['kalshi_ev_taker']=kalshi_ev(_fairp,_q.get('ask'),_n,KALSHI_TAKER_MULT)
                            # Maker caveat (adverse selection, from the research pass):
                            # resting bids fill disproportionately when the market is
                            # moving AGAINST you; this number is an upper bound.
                            play['kalshi_ev_maker']=kalshi_ev(_fairp,_q.get('bid'),_n,KALSHI_MAKER_MULT)
                    elif _ca and _cb:
                        pm_miss+=1
                _pq=pm_pol.get((t['away'],t['home']))
                if _pq and _pq.get(_side):
                    _p=_pq[_side]
                    play['poly_mid']=_p.get('mid'); play['poly_bid']=_p.get('bid'); play['poly_ask']=_p.get('ask')
                    if _fairp and _p.get('mid'):
                        _pm=POLY_TAKER_MULT.get(t.get('sport'),0.0)
                        _pcost=_p['mid']+(_pm*_p['mid']*(1-_p['mid']) if _pm else 0.0)
                        play['poly_ev_mid']=round(_fairp/_pcost-1,4)
            # best executable venue by fee-adjusted EV (LOG-ONLY, decisions unchanged)
            _cand={'bovada':r.get('ev')}
            if r.get('bo_price') is not None and _fairp: _cand['betonline']=round(_fairp*am2dec(r['bo_price'])-1,4)
            if play.get('kalshi_ev_taker') is not None: _cand['kalshi']=play['kalshi_ev_taker']
            if play.get('poly_ev_mid') is not None: _cand['polymarket']=play['poly_ev_mid']
            _cand={k:v for k,v in _cand.items() if v is not None}
            play['exec_best_venue']=max(_cand,key=_cand.get) if _cand else None
            play['exec_best_ev']=round(_cand[play['exec_best_venue']],4) if _cand else None
            # our-side AN per-book ML prices (source sweep, log-only)
            _anm=t.get('an_ml') or None
            if _anm and r.get('market')=='Moneyline':
                _sk='away' if str(r.get('side'))==str(t['away']) else ('home' if str(r.get('side'))==str(t['home']) else None)
                play['an_ml']={b:v.get(_sk) for b,v in _anm.items() if v.get(_sk)} if _sk else None
            else:
                play['an_ml']=None
            ctx=mlb_ctx.get((t['away'],t['home'])) if t.get('sport')=='mlb' else None
            if ctx is None and mlb_ctx and t.get('sport')=='mlb': ctx_misses+=1
            for k in ('mlb_gamePk','venue','day_night','double_header','probable_away','probable_away_id',
                      'probable_home','probable_home_id','wx_condition','wx_temp_f','wx_wind'):
                play[k]=(ctx or {}).get(k)
            play['pin_age_min']=t.get('pin_age_min')
            _ven=(ctx or {}).get('venue')
            play['roof']=VENUE_GEO[_ven][2] if _ven in VENUE_GEO else None
            play['park_rf_approx']=PARK_RF_APPROX.get(_ven)
            for k,v in (wx.get(_ven) or {}).items(): play[k]=v
            play['probable_changed']=(str((ctx or {}).get('mlb_gamePk')) in scratches) or None
            todays.append(play)
    if ctx_misses: print(f"    ! MLB Stats context: {ctx_misses} logged play(s) had no schedule match (fields logged as None)")
    if pm_miss: print(f"    ! Kalshi join: {pm_miss} ML play(s) had team codes but no matching market (check KALSHI_MLB map)")
    if stale_skips: print(f"    ! {stale_skips} value rec(s) NOT logged: Pinnacle quote older than {PIN_STALE_MIN} min (phantom-edge discard)")
    if news_skips: print(f"    ! {news_skips} rec(s) NOT logged this run: probable-pitcher change in progress (news window)")
    if RUN_MODE=='observe':
        added=0; sh_added=0
        print("  Observe mode: board read, snapshots and closes updated, NO plays logged (entry timing stays 15:00/21:30).")
    else:
        added=log_plays(log_path, todays)
        # Signal lab: zero-unit shadow rows for every graded lean (S through D) and
        # every value flag, logged only when real plays log so the two ledgers share
        # entry timing. Zero API credits; excluded from record, gates, and endpoint.
        sh_added=log_shadow_plays(log_path, build_shadow_plays(allc, now_iso))
        if sh_added: print(f"  Signal lab: {sh_added} zero-unit shadow row(s) logged (sharp S-D leans + value flags, measurement only)")
    # a scratch AFTER we bet changes the bet's quality: stamp pending plays (capture-or-lose)
    if scratches:
        try:
            _lg=load_log(log_path); _n=0
            for _p in _lg['plays']:
                if _p.get('result') is None and str(_p.get('mlb_gamePk')) in scratches and not _p.get('probable_changed_post_log'):
                    _p['probable_changed_post_log']=True; _n+=1
            if _n: save_log(log_path,_lg); print(f"    ! {_n} pending play(s) stamped probable_changed_post_log")
        except Exception as _e: print(f"    ! scratch stamping skipped: {_e}")
    runs=append_runlog(runlog_path, {'ts':now_iso,'mode':RUN_MODE,'model_version':MODEL_VERSION,
        'odds_games':run_odds_games,'an_games':run_an_games,'unmatched':run_unmatched,
        'bov_absent':run_bov_absent,'ctx_misses':ctx_misses,'plays_logged':added,
        'closes':touched,'graded':graded,'scratches':len(scratches),'wx_parks':len(wx),
        'pm_kalshi':pm_counts.get('kalshi_events'),'pm_poly':pm_counts.get('poly_games'),'pm_miss':pm_miss,
        'stale_skips':stale_skips,'news_skips':news_skips,'shadows':sh_added})
    allc['_runlog']=runs[-30:]
    # 3. snapshot every graded game this run (edge-over-time dataset)
    n_snaps=log_snapshots(snap_path, allc)
    for _k,_cards in allc.items():
        if isinstance(_cards,list):
            for _c in _cards:
                if isinstance(_c,dict):
                    _c.pop('_books_h2h',None); _c.pop('_ex_back',None); _c.pop('_ex_lay',None)
    # 4. summary + full stats for the dashboards
    summ=tracker_summary(log_path, UNIT_DOLLARS)
    stats=compute_stats(log_path, snap_path, UNIT_DOLLARS)
    allc['_tracker']=summ
    allc['_stats']=stats
    allc['_unit_dollars']=UNIT_DOLLARS

    # 5. CSV exports (for manual sorting), written to docs/ when on GitHub, else here
    csv_dir = os.path.join(here,"docs") if CI else here
    os.makedirs(csv_dir, exist_ok=True)
    try:
        _rl=json.load(open(runlog_path)).get('runs',[]) if os.path.exists(runlog_path) else []
    except Exception: _rl=[]
    if _rl:
        write_csv(os.path.join(csv_dir,"runlog.csv"), _rl,
                  ['ts','mode','model_version','odds_games','an_games','unmatched','bov_absent',
                   'ctx_misses','plays_logged','closes','graded'])
    betlog=load_log(log_path)
    write_csv(os.path.join(csv_dir,"bets.csv"), betlog['plays'],
              ['date','run_ts','commence','sport','away','home','market','side','point','price','units',
               'units_reason','rec_type','grade','gap','tickets','money','num_bets',
               'contrarian','steam','steam_delta','has_value','ev','fair','fair_mult','anchor',
               'nb','pin_price','pin_opp','ex_back','ex_lay','ex_mid',
               'mlb_gamePk','venue','day_night','double_header',
               'probable_away','probable_away_id','probable_home','probable_home_id',
               'wx_condition','wx_temp_f','wx_wind',
               'roof','park_rf_approx','om_temp_f','om_wind_kph','om_wind_dir_deg','pin_age_min',
               'bo_price','best_price','best_book','an_ml','probable_changed','probable_changed_post_log',
               'kalshi_ticker','kalshi_bid','kalshi_ask','kalshi_n','kalshi_ev_taker','kalshi_ev_maker',
               'poly_mid','poly_bid','poly_ask','poly_ev_mid','exec_best_venue','exec_best_ev',
               'close_price','close_fair','close_anchor','close_point','close_ts','close_obs',
               'close_line_moved','clv','clv_fair','clv_measured',
               'shadow','shadow_kind',
               'hours_to_game','result','void_reason','units_pl','model_version','event_id'])
    snaps_all=(json.load(open(snap_path)).get('snaps',[]) if os.path.exists(snap_path) else [])
    write_csv(os.path.join(csv_dir,"snapshots.csv"), snaps_all,
              ['run_ts','sport','game','commence','hours_to_game','sharp_side','grade','gap',
               'h2h_disp','ml_ex_mid','an_ml',
               'tickets','money','contrarian','steam','has_value','rec_price','rec_market','rec_side',
               'ev','fair','fair_mult','nb','anchor','event_id','units'])

    # render HTML
    MON=['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    _now_m=datetime.now(timezone.utc).month
    _active={sp['key'] for sp in active_sports()}
    def _ret_month(sp):
        for i in range(1,13):
            m=(_now_m+i-1)%12+1
            if m in sp['months']: return MON[m]
        return ''
    sports_js=[{'key':sp['key'],'label':sp['label'],'live':sp['key'] in _active,
                **({} if sp['key'] in _active else {'ret':_ret_month(sp)})}
               for sp in SPORTS if sp['enabled'] or sp['key'] in _active]
    html = TEMPLATE_HEAD + "\n<script>\nconst ALL=" + json.dumps(allc, default=str) + ";\n</script>\n<script>\n" + TEMPLATE_APP.replace("__SPORTS_JS__", json.dumps(sports_js)) + "\n</script>\n</body>\n</html>"
    ts=datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive=os.path.join(hist, f"ridgeseeker_{ts}.html")
    with open(archive,'w',encoding='utf-8') as f: f.write(html)
    latest=os.path.join(here,"ridgeseeker_latest.html")
    with open(latest,'w',encoding='utf-8') as f: f.write(html)
    # When running on GitHub, also publish to docs/ (served by GitHub Pages)
    if CI:
        docs=os.path.join(here,"docs")
        os.makedirs(docs, exist_ok=True)
        with open(os.path.join(docs,"index.html"),'w',encoding='utf-8') as f: f.write(html)

    n_top=len(top)
    print(f"\nDone. {n_top} play(s) worth attention today.")
    if graded: print(f"Graded {graded} finished bet(s) from earlier.")
    s=summ
    if s['n']>0:
        print(f"Record: {s['wins']}-{s['losses']} · {s['units_pl']:+.2f}u at ${UNIT_DOLLARS}/unit (${s['units_pl']*UNIT_DOLLARS:+.0f})")
        p=s['progress']
        if p:
            if p['ready']: print(f"  >> You've hit the bar to move to ${p['to']}/unit. (Check bankroll: want ~${p['bankroll_need']}+ behind it.)")
            else: print(f"  Toward ${p['to']}/unit: {p['bets_done']}/{p['bets_need']} bets, {p['units_done']:+.1f}/{p['units_need']}u")
            if s['concentrated']: print(f"  (Heads up: profit is concentrated in one big hit, so keep going before trusting it.)")
    if s.get('open_units'):
        flag=" !! over the daily exposure guidance, prioritize by EV if betting real money" if s['open_units']>MAX_DAILY_UNITS else ""
        print(f"Open exposure: {s['open_units']:.1f}u pending (guidance: <= {MAX_DAILY_UNITS:.0f}u/slate){flag}")
    print(f"Saved: {archive}")
    if not CI:
        print(f"Opening dashboard...")
        webbrowser.open('file://'+os.path.abspath(latest))

if __name__=='__main__':
    try:
        main()
    except Exception as e:
        msg = str(e)
        print("\n!! Error:", msg)
        if 'SSL' in msg or 'HANDSHAKE' in msg.upper() or 'CERTIFICATE' in msg.upper():
            print("\nThis is an SSL/connection problem on this computer (not the script or the APIs).")
            print("Most likely one of these, in order:")
            print("  1. Antivirus/security software is scanning HTTPS traffic and blocking Python.")
            print("     -> In your AV settings, turn off 'HTTPS scanning' / 'SSL scanning' / 'web shield',")
            print("        or add Python to its exceptions. (Avast, AVG, ESET, Kaspersky, Bitdefender all do this.)")
            print("  2. Your Python is old. Check the version printed at the top. If OpenSSL is older than")
            print("     3.0, install the latest Python from python.org (check 'Add to PATH') and try again.")
            print("  3. A VPN or work network is filtering traffic. Try on your home Wi-Fi with VPN off.")
            print("  Quick test: run  pip install certifi  then run this again (the script will use it).")
        else:
            print("If this keeps happening, check your internet connection or that your Odds API key is still valid.")
    if not CI:
        input("\nPress Enter to close...")
