#!/usr/bin/env python3
"""
RidgeSeeker: Sports Edge Dashboard (formerly EdgeFinder)
=========================================================
Run this and it will:
  1. Fetch fresh odds, sharp money, and live game status for all in-season sports
  2. Run the full value + sharp-grade engine
  3. Save a timestamped copy into the "edgefinder_history" folder
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
ODDS_KEY = os.environ.get("ODDS_KEY", "82149bd2ee25ae592612b8335b553d88")   # env (GitHub secret) or fallback
# Stamp every logged bet so history survives retunes and versions can be compared.
MODEL_VERSION = "2026-07-02.v9-ridgeseeker"
HISTORY_FOLDER = "ridgeseeker_history"           # timestamped HTMLs saved here
# Auto-detect: are we running on GitHub's servers (cloud) or on a personal laptop?
CI = (os.environ.get("GITHUB_ACTIONS") == "true") or bool(os.environ.get("EDGEFINDER_CI"))
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Sports to scan: (tab_key, odds_api_key, sport_kind, action_network_league_or_None)
SPORTS = [
    ('mlb', 'baseball_mlb',            'baseball', 'mlb'),
    # Focused on MLB for now (it's what you're betting + keeps API usage low).
    # When you add a sport, uncomment and drop your daily run count to stay under the
    # free API budget. Each sport adds ~3 credits per run.
    # ('wc',  'soccer_fifa_world_cup',   'soccer',   None),
    # ('mma', 'mma_mixed_martial_arts',  'mma',      None),
    # ('nfl', 'americanfootball_nfl',   'americanfootball', 'nfl'),
    # ('nba', 'basketball_nba',         'basketball', 'nba'),
    # ('nhl', 'icehockey_nhl',          'icehockey',  'nhl'),
]

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
def novig(pairs):
    if not pairs: return None, 0
    ps=[am2prob(a)/(am2prob(a)+am2prob(b)) for a,b in pairs]
    return statistics.median(ps), len(ps)
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
def fetch_odds(sport_key):
    url=f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={ODDS_KEY}&regions=us,eu&markets=h2h,spreads,totals&oddsFormat=american"
    try: return gj(url)
    except Exception as e: print(f"    ! odds fetch failed for {sport_key}: {e}"); return []

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
        status[(a,h)]={'state':state,'display':disp}
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
        if len(sd)==2:
            sharp[(a,h)]={'splits':{k:{'tickets':statistics.mean(v['tk']) if v['tk'] else 0,
                                       'money':statistics.mean(v['mn']) if v['mn'] else 0,
                                       'odds':statistics.median(v['od']) if v['od'] else None} for k,v in sd.items()},
                          'num_bets':g.get('num_bets')}
    return sharp, status, raw

def pin_pair(book_map, a, b):
    """Return Pinnacle's (price_a, price_b) if Pinnacle quotes both sides, else None."""
    p=book_map.get('Pinnacle')
    if p and a in p and b in p: return (p[a], p[b])
    return None

def soft_fair_map(odds):
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
    ml={}; spr={}; tot={}
    for b in g['bookmakers']:
        for m in b['markets']:
            if m['key']=='h2h': ml[b['title']]={o['name']:o['price'] for o in m['outcomes']}
            elif m['key']=='spreads': spr[b['title']]={o['name']:{'pt':o.get('point'),'pr':o['price']} for o in m['outcomes']}
            elif m['key']=='totals': tot[b['title']]={o['name']:{'pt':o.get('point'),'pr':o['price']} for o in m['outcomes']}
    bov_ml=ml.get('Bovada',{})
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
            f,n=novig(pairs); anc='consensus'
            if pinp:
                pa,pb=(pinp[0],pinp[1]) if s==away else (pinp[1],pinp[0])
                f=am2prob(pa)/(am2prob(pa)+am2prob(pb)); anc='pinnacle'
            if f and s in bov_ml:
                ev=f*am2dec(bov_ml[s])-1
                plays.append({'mkt':'ML','side':s,'point':None,'price':bov_ml[s],'fair':f,'ev':ev,'nb':n,'anchor':anc,'pass':gate(bov_ml[s],ev,n)})
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
            f,n=novig(pairs); anc='consensus'
            if pinsp:
                f=am2prob(pinsp[0])/(am2prob(pinsp[0])+am2prob(pinsp[1])); anc='pinnacle'
            if f:
                ev=f*am2dec(bov_fav_pr)-1
                plays.append({'mkt':'SPR','side':bov_fav,'point':bov_favpt,'price':bov_fav_pr,'fair':f,'ev':ev,'nb':n,'anchor':anc,'pass':gate(bov_fav_pr,ev,n),'label':spread_label})
                if bov_dog and bov_dog_pr:
                    evd=(1-f)*am2dec(bov_dog_pr)-1
                    plays.append({'mkt':'SPR','side':bov_dog,'point':bov_dogpt,'price':bov_dog_pr,'fair':1-f,'ev':evd,'nb':n,'anchor':anc,'pass':gate(bov_dog_pr,evd,n),'label':spread_label})
    # Totals
    bov_t=tot.get('Bovada',{})
    if 'Over' in bov_t:
        line=bov_t['Over']['pt']
        pairs=[]; pint=None
        for bk,d2 in tot.items():
            if 'Over' in d2 and 'Under' in d2 and d2['Over']['pt']==line:
                pairs.append((d2['Over']['pr'],d2['Under']['pr']))
                if bk=='Pinnacle': pint=(d2['Over']['pr'],d2['Under']['pr'])
        f,n=novig(pairs); anc='consensus'
        if pint:
            f=am2prob(pint[0])/(am2prob(pint[0])+am2prob(pint[1])); anc='pinnacle'
        if f:
            for s,fp,pr in [('Over',f,bov_t['Over']['pr']),('Under',1-f,bov_t['Under']['pr'])]:
                ev=fp*am2dec(pr)-1
                plays.append({'mkt':'TOT','side':s,'point':line,'price':pr,'fair':fp,'ev':ev,'nb':n,'anchor':anc,'pass':gate(pr,ev,n)})
    passed=[p for p in plays if p['pass']]
    best=max(passed,key=lambda x:x['ev']) if passed else None
    for p in plays: p['fair_am']=prob2am(p['fair'])
    sm=sharp_map.get((away,home))
    return {'away':away,'home':home,'time':g['commence_time'],'plays':plays,'best':best,
            'sharp':sm if sm else None,'rl_dataerror':rl_dataerror,
            'spread_label':spread_label,'three_way':three_way,
            'status':status_map.get((away,home),{'state':'scheduled','display':None}),
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
    --txt:#eef1f6;--mut:#9aa6b6;--dim:#646f7f;
    --sharp:#34d399;--sharpd:#0f6b4a;--public:#fb7185;--split:#fbbf24;--rlm:#a78bfa;--gold:#f5c451;
    --tick:#fb7185;--hand:#34d399;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:"SF Mono",ui-monospace,"Roboto Mono",Menlo,Consolas,monospace;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);font-family:var(--sans);line-height:1.5;
    -webkit-font-smoothing:antialiased;padding-bottom:92px}
  .wrap{max-width:760px;margin:0 auto;padding:0 14px}
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
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
  .hero-pick{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .hero-pick .t{font-size:17px;font-weight:800}.hero-pick .m{font-size:12px;color:var(--mut);margin-top:2px}
  .hero-pick .o{font-family:var(--mono);font-size:22px;font-weight:800;color:var(--sharp)}
  .hero-pick .ev{font-family:var(--mono);font-size:11px;color:var(--gold);text-align:right}
  .hero-why{margin-top:11px;font-size:12.5px;background:rgba(0,0,0,.18);border-radius:8px;padding:9px 11px}
  .hero-why b{color:var(--gold)}
  .disc{background:#1d1810;border:1px solid #3a2e18;color:#c9a86a;font-size:11px;padding:10px 13px;border-radius:10px;margin-top:14px;line-height:1.55}
  .tabs{display:flex;gap:6px;overflow-x:auto;padding:16px 0 12px;position:sticky;top:0;background:var(--bg);z-index:20;scrollbar-width:none}
  .tabs::-webkit-scrollbar{display:none}
  .tab{flex-shrink:0;padding:9px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);
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
  .card.add{cursor:pointer}.card.in{border-color:var(--sharp);box-shadow:0 0 0 1px var(--sharpd)}.card.conf{border-color:var(--gold)}
  .badgebar{display:flex;align-items:center;gap:7px;padding:9px 14px;border-bottom:1px solid var(--line);flex-wrap:wrap}
  .badge{font-size:10.5px;font-weight:800;letter-spacing:.5px;padding:4px 9px;border-radius:7px;display:inline-flex;align-items:center;gap:5px}
  .badge .d{width:6px;height:6px;border-radius:50%}
  .b-SHARP{background:rgba(52,211,153,.13);color:var(--sharp)}.b-SHARP .d{background:var(--sharp)}
  .b-PUBLIC{background:rgba(251,113,133,.13);color:var(--public)}.b-PUBLIC .d{background:var(--public)}
  .b-SPLIT{background:rgba(251,191,36,.13);color:var(--split)}.b-SPLIT .d{background:var(--split)}
  .b-VALUE{background:rgba(52,211,153,.13);color:var(--sharp)}
  .b-CONF{background:var(--gold);color:#3a2c08}.b-PASS{background:rgba(154,166,182,.1);color:var(--mut)}.b-WAIT{background:rgba(251,191,36,.1);color:var(--split)}
  .badgebar .gr{margin-left:auto;font-family:var(--mono);font-size:13px;font-weight:800}
  .gr-A{color:var(--gold)}.gr-B{color:var(--sharp)}.gr-C{color:var(--mut)}
  .body{padding:14px}
  .teams{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px}
  .team{flex:1}.team .nm{font-size:15.5px;font-weight:700}.team .meta{font-size:11px;color:var(--dim);margin-top:2px}.team.r{text-align:right}
  .at{font-family:var(--mono);font-size:11px;color:var(--dim)}
  .lines{display:grid;grid-template-columns:1fr 1fr;gap:9px}
  .ln{background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:11px;text-align:center}
  .ln.val{border-color:var(--sharpd);background:rgba(52,211,153,.06)}
  .ln .who{font-size:11px;color:var(--mut);margin-bottom:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .ln .pr{font-family:var(--mono);font-size:20px;font-weight:800}.ln.val .pr{color:var(--sharp)}
  .ln .fr{font-family:var(--mono);font-size:10px;color:var(--dim);margin-top:5px}
  .ln .ev{display:inline-block;font-family:var(--mono);font-size:10px;font-weight:800;padding:2px 7px;border-radius:5px;margin-top:6px}
  .ln.val .ev{background:var(--sharp);color:#04130c}.ln .ev.neg{color:var(--dim);border:1px solid var(--line)}
  /* multi-source probability strip */
  .srcprob{margin-top:12px;background:var(--bg2);border-radius:10px;padding:11px;border:1px solid var(--line)}
  .srcprob .h{font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:var(--mut);margin-bottom:9px;display:flex;justify-content:space-between}
  .srcprob .h .true{color:var(--sharp)}
  .pgrid{display:flex;flex-direction:column;gap:6px}
  .prow{display:flex;align-items:center;gap:8px;font-size:11px}
  .prow .src-l{width:64px;color:var(--mut);font-size:10px}
  .prow .bar{flex:1;height:6px;background:#11131a;border-radius:4px;overflow:hidden}
  .prow .fill{height:100%;background:linear-gradient(90deg,#34d399,#60a5fa);border-radius:4px}
  .prow .val{width:42px;text-align:right;font-family:var(--mono);font-size:10px;color:var(--txt)}
  .prow.true .src-l{color:var(--sharp);font-weight:700}.prow.true .fill{background:var(--sharp)}
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
  .sh-read{margin-top:10px;font-size:11.5px;line-height:1.5}.sh-read b{color:var(--sharp)}.sh-read .pub{color:var(--public)}
  .note{font-size:12px;color:var(--mut);margin-top:11px;line-height:1.55;background:var(--bg2);border-radius:9px;padding:10px 12px}
  .note b{color:var(--txt)}.note .g{color:var(--sharp)}.note .gold{color:var(--gold)}
  .nodata{font-size:11px;color:var(--dim);margin-top:11px;font-style:italic}
  .infohd{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:15px;margin-bottom:13px}
  .infohd .t{font-size:16px;font-weight:800}.infohd .d{font-size:12px;color:var(--mut);margin-top:3px}
  .infohd .warn{margin-top:11px;font-size:12px;border-radius:8px;padding:9px 11px;line-height:1.5}
  .infohd .warn.amber{background:rgba(251,191,36,.07);color:#e0b450}.infohd .warn.gray{background:rgba(154,166,182,.06);color:var(--mut)}.infohd .warn.green{background:rgba(52,211,153,.07);color:var(--sharp)}
  .row{display:flex;align-items:center;padding:11px 14px;border-bottom:1px solid var(--bg2);gap:12px}.row:last-child{border-bottom:none}
  .row .rk{font-family:var(--mono);font-size:11px;color:var(--dim);width:18px}.row .nm{flex:1;font-size:13.5px;font-weight:600}
  .row .nm .s{font-family:var(--mono);font-size:9px;color:var(--dim);font-weight:400}.row .pr{font-family:var(--mono);font-size:15px;font-weight:800}
  .empty{border:1px dashed var(--line);border-radius:13px;padding:36px 20px;text-align:center}
  .empty .ic{font-size:24px;opacity:.5;margin-bottom:10px}.empty h3{font-size:14px;color:var(--mut);margin-bottom:6px}
  .empty p{font-size:12.5px;color:var(--dim);max-width:380px;margin:0 auto;line-height:1.5}
  .dock{position:fixed;bottom:0;left:0;right:0;background:rgba(20,22,29,.98);border-top:1px solid var(--sharpd);backdrop-filter:blur(10px);z-index:50;transform:translateY(calc(100% - 52px));transition:transform .26s}
  .dock.open{transform:translateY(0)}.dock-w{max-width:760px;margin:0 auto;padding:0 14px}
  .dock-h{height:52px;display:flex;align-items:center;justify-content:space-between;cursor:pointer}
  .dock-h .t{font-size:13px;font-weight:800}.dock-h .cnt{background:var(--sharp);color:#04130c;font-size:11px;font-weight:800;border-radius:11px;padding:1px 8px;margin-left:7px}
  .dock-h .pay{font-family:var(--mono);font-size:15px;font-weight:800;color:var(--sharp)}
  .dock-body{max-height:44vh;overflow-y:auto;padding-bottom:16px}
  .leg{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--bg2);gap:8px}
  .leg .ln2{font-size:12.5px}.leg .ln2 .s{font-size:10px;color:var(--dim);display:block;margin-top:1px}.leg .lo{font-family:var(--mono);font-size:12.5px;color:var(--sharp)}.leg .x{color:var(--public);font-size:18px;cursor:pointer;padding:0 5px}
  .calc{display:flex;gap:11px;align-items:center;padding:13px 0 5px}
  .calc input{flex:1;background:var(--card2);border:1px solid var(--line);color:var(--txt);border-radius:9px;padding:10px 12px;font-family:var(--mono);font-size:14px;min-width:0}
  .calc .out{text-align:right}.calc .out .l{font-size:9px;color:var(--dim);text-transform:uppercase}.calc .out .v{font-family:var(--mono);font-size:18px;font-weight:800;color:var(--sharp)}.calc .out .o{font-family:var(--mono);font-size:10px;color:var(--mut)}
  .dock-empty{color:var(--dim);font-size:12px;text-align:center;padding:18px 0}
  .clr{background:none;border:1px solid var(--line);color:var(--mut);font-size:11px;padding:7px 11px;border-radius:8px;cursor:pointer}
  footer{color:var(--dim);font-size:10.5px;text-align:center;padding:26px 14px;line-height:1.7}footer b{color:var(--mut)}

  .markets{display:flex;flex-direction:column;gap:9px}
  .mblock{background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:10px 11px}
  .mblock .mh{font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:var(--mut);margin-bottom:8px}
  .mkrow{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px}
  .mkrow .mlbl{font-family:var(--mono);font-size:9px;color:var(--dim);width:22px}
  .mkrow .mside{flex:1;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .mkrow .mprice{font-family:var(--mono);font-weight:800;width:48px;text-align:right}
  .mkrow .mfair{font-family:var(--mono);font-size:9.5px;color:var(--dim);width:64px;text-align:right}
  .mkrow .mev{font-family:var(--mono);font-size:9.5px;font-weight:800;padding:2px 6px;border-radius:4px;width:54px;text-align:center}
  .mkrow .mev.pos{background:var(--sharp);color:#04130c}
  .mkrow .mev.neg{color:var(--dim);border:1px solid var(--line)}
  .mkrow.best{background:rgba(52,211,153,.07);margin:0 -6px;padding:5px 6px;border-radius:6px}
  .mkrow.best .mprice{color:var(--sharp)}
  .mderr{font-size:11px;color:var(--split);background:rgba(251,191,36,.06);border-radius:7px;padding:8px 10px;line-height:1.45}
  .shnote{font-size:10px;color:var(--dim);margin-top:7px;font-style:italic}

  .gradechip{font-family:var(--mono);font-size:15px;font-weight:800;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;border-radius:8px}
  .gradechip.none{background:var(--card2);color:var(--dim);font-size:13px}
  .vyes{font-family:var(--mono);font-size:9px;font-weight:800;color:var(--sharp);margin-left:auto;background:rgba(52,211,153,.13);padding:2px 6px;border-radius:4px}
  .herograde{font-family:var(--mono);font-weight:800;padding:1px 10px;border-radius:7px;color:#0c0f16;margin-right:6px}
  .sharptag{font-size:9px;color:var(--sharp);font-weight:700}
  .steam{color:var(--gold);font-weight:600}
  .b-VALUE{background:rgba(52,211,153,.13);color:var(--sharp)}

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
  .vtab{flex:0 0 auto;background:var(--card2);border:1px solid var(--line);color:var(--mut);font-size:14px;font-weight:700;padding:9px 18px;border-radius:999px;cursor:pointer;transition:all .15s;font-family:inherit}
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
  .dlrow a{background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:9px 14px;font-size:13px;font-weight:600;color:#60a5fa;text-decoration:none}
  .rbar{height:20px;border-radius:5px;display:flex;align-items:center;padding:0 8px;font-size:11px;font-family:var(--mono);font-weight:700;color:#0a0d12;min-width:28px}
  .rempty{text-align:center;color:var(--mut);padding:40px 20px}
  .rempty h3{margin-bottom:8px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="mast"><div class="logo">ridge<b>seeker</b></div><div class="clock" id="clock"></div></div>
    <div class="viewtoggle">
      <button class="vtab active" id="vtab-board" onclick="showView('board')">Today's Board</button>
      <button class="vtab" id="vtab-results" onclick="showView('results')">Results</button>
    </div>
  </header>

  <div id="view-board">
    <div class="sub">Fair value = devigged Pinnacle (the sharpest book), consensus median as fallback, compared to Bovada. Sharp money where available. Only real edges surface.</div>
    <div class="srcrow" id="srcrow"></div>
    <div class="hero" id="hero"></div>
    <div class="disc">⚠️ <b>All signals are real data.</b> Fair probability = Pinnacle with the vig removed (falling back to the no-vig median of ~25 books when Pinnacle skips a market). Sharp money = live ticket/handle from Action Network (US team sports). Estimates, not guarantees; lines move; re-check before betting. 21+ · 1-800-522-4700.</div>
    <div class="tabs" id="tabs"></div>
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
  const addable=c.has_value&&v;
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
const SPORTS=[{key:'mlb',label:'MLB',live:true},{key:'nfl',label:'NFL',live:false,ret:'Sep'},{key:'nba',label:'NBA',live:false,ret:'Oct'},{key:'nhl',label:'NHL',live:false,ret:'Oct'}];
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
    panel.innerHTML=`<div class="tk-row"><span class="tk-l">Tracker</span><span class="tk-rec">${tr.wins}-${tr.losses} · <b class="${tr.units_pl>=0?'pos':'neg'}">${tr.units_pl>=0?'+':''}${tr.units_pl}u (${dollars>=0?'+$':'-$'}${Math.abs(dollars)})</b></span></div><div class="tk-row2">${prog}${tr.concentrated?' <span class="tk-warn">profit concentrated in 1 hit (small sample)</span>':''}${tr.pending?' <span class="tk-pend">'+tr.pending+' pending</span>':''}</div>`;
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
SPORTS.forEach((s,i)=>{const t=document.createElement('div');t.className='tab'+(s.live?' live':' off')+(s.temp?' temp':'')+(i===0?' active':'');t.dataset.k=s.key;let ret=!s.live?`<span class="ret">${s.ret}</span>`:(s.temp?`<span class="ret">→Jul19</span>`:'');t.innerHTML=`<span class="led"></span>${s.label}${ret}`;if(s.live)t.onclick=()=>switchTab(s.key);tabsEl.appendChild(t);});
function switchTab(k){document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.k===k));document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));document.getElementById('view-'+k).classList.add('active');}
const viewsEl=document.getElementById('views');
function mkView(k,a){const v=document.createElement('div');v.className='view'+(a?' active':'');v.id='view-'+k;return v;}
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
  if(graded.length)h+=`<div class="sect">sharp board · S → D<span class="ct">${graded.length} graded</span></div>`+graded.map(gameCard).join('');
  if(ungraded.length)h+=`<div class="sect">${graded.length?'no sharp signal':'full slate'}<span class="ct">${ungraded.length}</span></div>`+ungraded.map(gameCard).join('');
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
    if(!_resultsBuilt){ renderResults(); _resultsBuilt=true; }
    window.scrollTo(0,0);
  } else {
    results.style.display='none'; board.style.display='block';
    tr.classList.remove('active'); tb.classList.add('active');
    window.scrollTo(0,0);
  }
}

// ===== Results view (folded-in stats) =====
function renderResults(){
  const S=ALL['_stats']||{}; const ud=S.unit_dollars||ALL['_unit_dollars']||10;
  const host=document.getElementById('view-results');
  const o=S.overall||{n:0};
  const money=(u)=>{const d=Math.round(u*ud);return (u>=0?'+':'')+u+'u ('+(d>=0?'+$':'-$')+Math.abs(d)+')';};
  const cls=(u)=>u>=0?'pos':'neg';
  if(!o.n){
    host.innerHTML=`<div class="rempty"><h3>No settled bets yet</h3><p>Your results build automatically as recommended games finish. Check back after a few slates.</p></div>
    <div class="rsect">Raw data</div><div class="dlrow"><a href="bets.csv" download>⬇ bets.csv</a><a href="snapshots.csv" download>⬇ snapshots.csv</a></div>
    <div class="rnote">bets.csv = every recommended play and its result. snapshots.csv = each run's readings, for edge-over-time analysis.</div>`;
    return;
  }
  let h=`<div class="rbig">
    <div class="rstat"><div class="l">Record</div><div class="v">${o.wins}-${o.losses}</div></div>
    <div class="rstat"><div class="l">Win %</div><div class="v">${o.win_pct}%</div></div>
    <div class="rstat"><div class="l">Units</div><div class="v ${cls(o.units_pl)}">${o.units_pl>=0?'+':''}${o.units_pl}</div></div>
    <div class="rstat"><div class="l">ROI</div><div class="v ${cls(o.roi||0)}">${o.roi==null?'-':o.roi+'%'}</div></div>
    <div class="rstat"><div class="l">Profit</div><div class="v ${cls(o.units_pl)}">${o.dollars>=0?'+$':'-$'}${Math.abs(o.dollars)}</div></div>
  </div><div class="rnote">${o.pending||0} bets still pending. $${ud}/unit.</div>`;
  if(S.clv&&S.clv.n){
    const c=S.clv;
    h+=`<div class="rcard"><b>Closing line value:</b> avg <span class="${c.avg>=0?'pos':'neg'}">${c.avg>=0?'+':''}${c.avg}%</span> across ${c.n} bets · beat the close ${c.pos_pct}% of the time.<div class="rnote">CLV is the fastest honest signal. Consistently positive CLV over 50+ bets means the picks beat the market even before wins and losses stabilize; negative CLV with a winning record means the record is luck. (Close = last pregame price this tool saw, an approximation given the run schedule.)</div></div>`;
  }
  h+=`<div class="rsect">By stated EV</div>`+simpleTbl(S.by_ev);
  // by grade
  h+=`<div class="rsect">By sharp grade</div>`+gradeTbl(S.by_grade);
  if(S.cumulative&&S.cumulative.length>1) h+=`<div class="rsect">Cumulative units</div><div class="rcard">${lineChart(S.cumulative,ud)}</div>`;
  h+=`<div class="rsect">Units won by grade</div><div class="rcard">${gradeBars(S.by_grade)}</div>`;
  h+=`<div class="rsect">By unit size</div>`+simpleTbl(S.by_units);
  h+=`<div class="rsect">By signal type</div>`+simpleTbl(S.by_signal);
  h+=`<div class="rsect">By price range</div>`+simpleTbl(S.by_price);
  h+=`<div class="rsect">By market</div>`+simpleTbl(S.by_market);
  h+=`<div class="rsect">By time until game</div>`+simpleTbl(S.by_htg);
  if(S.edge_by_htg&&Object.keys(S.edge_by_htg).length){
    let rows=Object.entries(S.edge_by_htg).map(([k,v])=>`<tr><td>${k}</td><td class="g">${v} pts</td></tr>`).join('');
    h+=`<div class="rsect">Avg sharp gap by time-to-game</div><div class="rcard"><table class="rtable"><tr><th>Hours out</th><th>Avg gap</th></tr>${rows}</table><div class="rnote">Bigger gaps closer to game time = sharp money arriving late (bet later). Bigger early = bet early. Needs a couple weeks of data to trust.</div></div>`;
  }
  h+=`<div class="rsect">Raw data</div><div class="dlrow"><a href="bets.csv" download>⬇ bets.csv</a><a href="snapshots.csv" download>⬇ snapshots.csv</a></div><div class="rnote">Every bet and snapshot, for your own sorting.</div>`;
  host.innerHTML=h;

  function badge(g){return `<td class="g" style="color:${GC[g]||'#888'}">${g}</td>`;}
  function gradeTbl(d){
    if(!d)return '<div class="rcard thin2">Not enough graded bets yet.</div>';
    let rows='';
    ['S','A','B','C','D'].forEach(g=>{const r=d[g];if(!r)return;const thin=r.n<8?'<span class="thin2"> small</span>':'';
      rows+=`<tr>${badge(g)}<td>${r.n}${thin}</td><td>${r.win_pct==null?'-':r.win_pct+'%'}</td><td class="${cls(r.units_pl)}">${r.units_pl>=0?'+':''}${r.units_pl}u</td><td class="${cls(r.roi||0)}">${r.roi==null?'-':r.roi+'%'}</td><td class="${cls(r.dollars)}">${r.dollars>=0?'+$':'-$'}${Math.abs(r.dollars)}</td></tr>`;});
    if(!rows)return '<div class="rcard thin2">Not enough graded bets yet.</div>';
    return `<table class="rtable"><tr><th>Grade</th><th>Bets</th><th>Win%</th><th>Units</th><th>ROI</th><th>$</th></tr>${rows}</table><div class="rnote">"small" = under 8 bets, don't over-read it. You want ROI to rank S ≥ A ≥ B; if it's scrambled, the grading needs tuning.</div>`;
  }
  function simpleTbl(d){
    if(!d||!Object.keys(d).length)return '<div class="rcard thin2">No data yet.</div>';
    let rows=Object.entries(d).map(([k,r])=>{const thin=r.n<8?'<span class="thin2"> sm</span>':'';
      return `<tr><td>${k}</td><td>${r.n}${thin}</td><td>${r.win_pct==null?'-':r.win_pct+'%'}</td><td class="${cls(r.units_pl)}">${r.units_pl>=0?'+':''}${r.units_pl}u</td><td class="${cls(r.roi||0)}">${r.roi==null?'-':r.roi+'%'}</td></tr>`;}).join('');
    return `<table class="rtable"><tr><th></th><th>Bets</th><th>Win%</th><th>Units</th><th>ROI</th></tr>${rows}</table>`;
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
    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%"><line x1="${pad}" y1="${zeroY}" x2="${W-pad}" y2="${zeroY}" stroke="#232b36" stroke-dasharray="3 3"/><path d="${path}" fill="none" stroke="${last>=0?'#34d399':'#f87171'}" stroke-width="2.5"/><circle cx="${pts[pts.length-1][0]}" cy="${pts[pts.length-1][1]}" r="4" fill="${last>=0?'#34d399':'#f87171'}"/><text x="${pad}" y="12" fill="#5c6673" font-size="11" font-family="monospace">${mx>=0?'+':''}${mx}u</text><text x="${pad}" y="${H-3}" fill="#5c6673" font-size="11" font-family="monospace">${mn}u</text></svg>`;
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
    steam=False
    sf=soft_fair_game.get(sharp_side) if soft_fair_game else None
    odds=splits[sharp_side].get('odds')
    if sf is not None and odds is not None and am2prob(odds)>sf+0.015: steam=True
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
            'contrarian':contrarian,'steam':steam,'capped':capped,'thin':thin}

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
                'text':f"{mlabel} · {sidetxt} at {am_str(v['price'])}",
                'why':("Value + sharp agree: double-down." if agree else "Value bet (price beats fair value).")+cross,
                'double':bool(agree)}
    if sg and sg['grade'] in ('S','A','B','C'):
        ml=find_play('ML',sg['side']); sp=find_play('SPR',sg['side']); alts=[]
        if ml and ml.get('price') is not None: alts.append({'market':'Moneyline','point':None,'price':ml['price']})
        if sp and sp.get('price') is not None: alts.append({'market':c.get('spread_label') or 'Spread','point':sp.get('point'),'price':sp['price']})
        if alts:
            p0=alts[0]; pt=pt_str(p0['point']); sidetxt=f"{sg['side']} {pt}".strip()
            return {'type':'sharp','market':p0['market'],'side':sg['side'],'point':p0['point'],'price':p0['price'],
                    'text':f"{p0['market']} · {sidetxt} at {am_str(p0['price'])}",
                    'why':"Sharp signal is moneyline-based, so the ML is the cleanest expression. Alt markets shown if you want a different risk/reward.",
                    'alts':alts,'double':False}
    return None

# ============================ RESULTS TRACKER ============================
LEVELS = [
    {'from':10, 'to':20, 'min_bets':50,  'min_units':5,  'min_bankroll':800},
    {'from':20, 'to':50, 'min_bets':175, 'min_units':12, 'min_bankroll':2000},
]
def _bkey(p): return f"{p['date']}|{p['away']}|{p['home']}|{p['market']}|{p['side']}"
def load_log(path):
    if os.path.exists(path):
        try: return json.load(open(path))
        except: pass
    return {'plays':[]}
def save_log(path, log): json.dump(log, open(path,'w'), indent=2, default=str)
def log_plays(path, recs):
    log=load_log(path); existing={_bkey(p) for p in log['plays']}
    today=datetime.now(timezone.utc).strftime('%Y-%m-%d'); added=0
    for r in recs:
        p=dict(r); p['date']=today; p['result']=None; p['units_pl']=None
        if _bkey(p) not in existing: log['plays'].append(p); existing.add(_bkey(p)); added+=1
    save_log(path, log); return added
def _grade_one(p, res):
    mkt=str(p['market']).lower(); side=p['side']; aw,hm=p['away'],p['home']
    ar,hr=res.get('away_runs'),res.get('home_runs')
    if ar is None or hr is None: return None
    if 'moneyline' in mkt or mkt=='ml':
        if side==aw: return ar>hr
        if side==hm: return hr>ar
        return None
    if any(k in mkt for k in ('run line','spread','handicap','puck')):
        pt=p.get('point')
        if pt is None: return None
        margin=(ar-hr) if side==aw else (hr-ar); adj=margin+float(pt)
        return True if adj>0 else (False if adj<0 else None)
    if 'total' in mkt or mkt=='o/u':
        pt=p.get('point')
        if pt is None: return None
        tot=ar+hr; pt=float(pt)
        if tot==pt: return None
        return (tot>pt) if side=='Over' else (tot<pt)
    return None
def grade_pending(path, results):
    log=load_log(path); n=0
    for p in log['plays']:
        if p.get('result') is not None: continue
        res=results.get((p['away'],p['home']))
        if not res or res=='AMBIG': continue
        won=_grade_one(p,res)
        if won is None: continue
        p['result']='win' if won else 'loss'
        pr=float(p['price']); dec=1+(pr/100 if pr>0 else 100/(-pr)); u=float(p['units'])
        p['units_pl']=round(u*(dec-1),2) if won else round(-u,2); n+=1
        # closing line value: how our entry price compares to the last pregame price seen.
        # Positive CLV = we beat the close. This converges on truth 10x faster than W/L.
        cp=p.get('close_price')
        if cp is not None:
            try: p['clv']=round((am2dec(p['price'])/am2dec(cp)-1)*100,2)
            except Exception: p['clv']=None
    save_log(path, log); return n

MARKET_TO_MKT={'moneyline':'ML','run line':'SPR','spread':'SPR','asian handicap':'SPR','puck line':'SPR','total':'TOT'}
def update_closes(path, allc):
    """While a logged bet's game is still pregame, keep refreshing close_price with the
    latest Bovada price for the same market/side/point. Once the game goes live the
    price stops updating, so the stored value is the last pregame price we saw: an
    honest approximation of the close given the run schedule (labeled as such)."""
    log=load_log(path); touched=0
    cards={}
    for sport,cs in allc.items():
        if sport.startswith('_'): continue
        for c in cs: cards[(c['away'],c['home'])]=c
    for p in log['plays']:
        if p.get('result') is not None: continue
        c=cards.get((p['away'],p['home']))
        if not c or (c.get('status') or {}).get('state')!='scheduled': continue
        want=MARKET_TO_MKT.get(str(p.get('market','')).lower())
        if not want: continue
        for pl in c.get('plays',[]):
            if pl['mkt']==want and str(pl['side'])==str(p['side']):
                same_pt=(pl.get('point')==p.get('point')) or (want=='ML')
                if same_pt and pl.get('price') is not None:
                    p['close_price']=pl['price']; touched+=1
                break
    if touched: save_log(path, log)
    return touched
def tracker_summary(path, current_unit):
    log=load_log(path)
    settled=[p for p in log['plays'] if p.get('result') in ('win','loss')]
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
    return {'n':n,'wins':wins,'losses':n-wins,'units_pl':units_pl,
            'pending':len([p for p in log['plays'] if p.get('result') is None]),
            'concentrated':concentrated,'progress':progress,'current_unit':current_unit}

def collect_results(sharp_raw_by_league):
    """Pull final scores from Action Network raw payloads already fetched.
    Doubleheaders (same matchup, two finals with different scores in one payload) are
    marked AMBIG and skipped by grading, because we cannot tell which game a logged bet
    belongs to. An honest skip beats a coin-flip grade."""
    out={}
    for raw in sharp_raw_by_league:
        for g in (raw.get('games',[]) if raw else []):
            if g.get('status') not in ('complete','closed'): continue
            def nm(tid):
                for t in g.get('teams',[]):
                    if t['id']==tid: return t.get('full_name')
            bs=g.get('boxscore') or {}; stats=bs.get('stats') or {}
            ar=(stats.get('away') or {}).get('runs'); hr=(stats.get('home') or {}).get('runs')
            if ar is not None and hr is not None:
                k=(nm(g['away_team_id']),nm(g['home_team_id']))
                if k in out and out[k]!='AMBIG' and (out[k]['away_runs'],out[k]['home_runs'])!=(ar,hr):
                    out[k]='AMBIG'
                elif k not in out:
                    out[k]={'away_runs':ar,'home_runs':hr}
    return out

def hours_until(iso):
    try:
        start=datetime.fromisoformat(iso.replace('Z','+00:00'))
        return round((start-datetime.now(timezone.utc)).total_seconds()/3600.0, 2)
    except: return None

def log_snapshots(path, allc):
    """Append one row per MLB game that has a sharp grade this run."""
    snaps=[]
    if os.path.exists(path):
        try: snaps=json.load(open(path)).get('snaps',[])
        except: snaps=[]
    run_ts=datetime.now(timezone.utc).isoformat()
    for sport,cards in allc.items():
        if sport.startswith('_'): continue
        for c in cards:
            sg=c.get('sharp_grade')
            if not sg: continue
            snaps.append({
                'run_ts':run_ts,'sport':sport,'game':f"{c['away']} @ {c['home']}",
                'away':c['away'],'home':c['home'],'commence':c['time'],
                'hours_to_game':hours_until(c['time']),
                'sharp_side':sg['side'],'grade':sg['grade'],'gap':sg['gap'],
                'tickets':sg['tickets'],'money':sg['money'],
                'contrarian':sg['contrarian'],'steam':sg['steam'],
                'has_value':c.get('has_value'),
                'rec_price':(c.get('rec') or {}).get('price'),
                'rec_market':(c.get('rec') or {}).get('market'),
                'units':c.get('units'),
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
    settled=[p for p in log['plays'] if p.get('result') in ('win','loss')]
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
    overall['pending']=len([p for p in log['plays'] if p.get('result') is None])
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
    clvs=[r['clv'] for r in settled if r.get('clv') is not None]
    clv={'n':len(clvs),
         'avg':round(sum(clvs)/len(clvs),2) if clvs else None,
         'pos_pct':round(100*sum(1 for c in clvs if c>0)/len(clvs)) if clvs else None}
    def ev_bucket(r):
        e=r.get('ev')
        if e is None: return 'sharp only (no price edge)'
        return '3-5%' if e<0.05 else '5-8%' if e<0.08 else '8%+'
    return {'overall':overall,
            'clv':clv,
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
    allc={}
    raw_payloads=[]
    for key, skey, kind, an in SPORTS:
        print(f"  [{key.upper()}] odds...", end=" ", flush=True)
        odds=fetch_odds(skey)
        print(f"{len(odds)} games", end="")
        sharp_map, status_map, raw = fetch_sharp_and_status(an)
        if raw: raw_payloads.append(raw)
        sf = soft_fair_map(odds)
        cards=[]
        for g in odds:
            c=analyze_game(g, kind, {k:v['splits'] for k,v in sharp_map.items()}, status_map, sf)
            # grade
            sm=sharp_map.get((c['away'],c['home']))
            sg=None
            if sm: sg=grade_sharp(sm['splits'], c['_soft_fair'], num_bets=sm.get('num_bets'), sport_kind=kind)
            c['sharp_grade']=sg
            c['rec']=build_recommendation(c, sg)
            u, ureason = suggest_units(c)
            c['units']=u; c['units_reason']=ureason
            c['unit_dollars']=UNIT_DOLLARS
            # strip internal keys
            c.pop('_sharp_raw',None); c.pop('_soft_fair',None)
            cards.append(c)
        allc[key]=cards
        g_ct=sum(1 for c in cards if c['sharp_grade'])
        print(f"  ·  {g_ct} sharp-graded")
    # build _top
    GORD={'S':5,'A':4,'B':3,'C':2,'D':1,None:0}
    top=[]
    for sport,cards in allc.items():
        for c in cards:
            sg=c.get('sharp_grade'); rec=c.get('rec')
            if (sg and sg['grade'] in ('S','A')) or (rec and rec.get('double')):
                vp=c.get('value_play') or {}
                top.append({'sport':sport.upper(),'away':c['away'],'home':c['home'],'time':c['time'],
                            'grade':sg['grade'] if sg else None,'rec':rec,'sg':sg,'has_value':c.get('has_value'),
                            'status':c.get('status'),'units':c.get('units'),'units_reason':c.get('units_reason'),
                            'ev':vp.get('ev'),'fair':vp.get('fair'),'anchor':vp.get('anchor'),
                            'unit_dollars':UNIT_DOLLARS})
    top.sort(key=lambda x:(-(2 if x['rec'] and x['rec'].get('double') else 0), -GORD.get(x['grade'],0)))
    allc['_top']=top

    # ---- results tracker ----
    log_path=os.path.join(here, "ridgeseeker_betlog.json")
    snap_path=os.path.join(here, "ridgeseeker_snapshots.json")
    # one-time migration: adopt the old EdgeFinder files so no history is lost
    for old,new in [("edgefinder_betlog.json",log_path),("edgefinder_snapshots.json",snap_path)]:
        op=os.path.join(here,old)
        if os.path.exists(op) and not os.path.exists(new):
            try:
                import shutil; shutil.copyfile(op,new); print(f"  (migrated {old} -> {os.path.basename(new)})")
            except Exception as e: print(f"  ! migration failed for {old}: {e}")
    # 0. refresh close prices for pending pregame bets (CLV needs the last pregame price)
    update_closes(log_path, allc)
    # 1. grade any pending bets we now have final scores for
    results=collect_results(raw_payloads)
    graded=grade_pending(log_path, results)
    # 2. log today's recommended plays with full feature set (grade, gap, hours-to-game)
    todays=[]
    for t in top:
        if t.get('units') and t.get('rec') and (t.get('status') or {}).get('state') in (None,'scheduled'):
            r=t['rec']; sg=t.get('sg') or {}
            todays.append({'away':t['away'],'home':t['home'],'sport':t['sport'],
                           'market':r['market'],'side':str(r['side']),'point':r.get('point'),
                           'price':r['price'],'units':t['units'],
                           'grade':t.get('grade'),'gap':sg.get('gap'),
                           'contrarian':sg.get('contrarian'),'steam':sg.get('steam'),
                           'has_value':t.get('has_value'),
                           'ev':t.get('ev'),'fair':t.get('fair'),'anchor':t.get('anchor'),
                           'model_version':MODEL_VERSION,'close_price':None,'clv':None,
                           'hours_to_game':hours_until(t['time'])})
    added=log_plays(log_path, todays)
    # 3. snapshot every graded game this run (edge-over-time dataset)
    n_snaps=log_snapshots(snap_path, allc)
    # 4. summary + full stats for the dashboards
    summ=tracker_summary(log_path, UNIT_DOLLARS)
    stats=compute_stats(log_path, snap_path, UNIT_DOLLARS)
    allc['_tracker']=summ
    allc['_stats']=stats
    allc['_unit_dollars']=UNIT_DOLLARS

    # 5. CSV exports (for manual sorting), written to docs/ when on GitHub, else here
    csv_dir = os.path.join(here,"docs") if CI else here
    os.makedirs(csv_dir, exist_ok=True)
    betlog=load_log(log_path)
    write_csv(os.path.join(csv_dir,"bets.csv"), betlog['plays'],
              ['date','sport','away','home','market','side','point','price','units',
               'grade','gap','contrarian','steam','has_value','hours_to_game','result','units_pl'])
    snaps_all=(json.load(open(snap_path)).get('snaps',[]) if os.path.exists(snap_path) else [])
    write_csv(os.path.join(csv_dir,"snapshots.csv"), snaps_all,
              ['run_ts','sport','game','commence','hours_to_game','sharp_side','grade','gap',
               'tickets','money','contrarian','steam','has_value','rec_price','rec_market','units'])

    # render HTML
    html = TEMPLATE_HEAD + "\n<script>\nconst ALL=" + json.dumps(allc, default=str) + ";\n</script>\n<script>\n" + TEMPLATE_APP + "\n</script>\n</body>\n</html>"
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
