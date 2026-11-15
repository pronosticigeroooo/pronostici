#!/usr/bin/env python3
"""Scarica risultati e calendari reali da football-data.co.uk, stima le probabilita'
con un modello Poisson e genera docs/index.html (la pagina pubblicata)."""
import csv, difflib, io, json, math, os, re, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BASE = "https://www.football-data.co.uk"
LEAGUES = {  # codice: (paese, campionato)
    "E0": ("Inghilterra", "Premier League"), "E1": ("Inghilterra", "Championship"),
    "E2": ("Inghilterra", "League One"), "E3": ("Inghilterra", "League Two"),
    "SP1": ("Spagna", "La Liga"), "SP2": ("Spagna", "La Liga 2"),
    "I1": ("Italia", "Serie A"), "I2": ("Italia", "Serie B"),
    "D1": ("Germania", "Bundesliga"), "D2": ("Germania", "2. Bundesliga"),
    "F1": ("Francia", "Ligue 1"), "F2": ("Francia", "Ligue 2"),
    "N1": ("Paesi Bassi", "Eredivisie"), "B1": ("Belgio", "Jupiler Pro League"),
    "P1": ("Portogallo", "Primeira Liga"), "T1": ("Turchia", "Süper Lig"),
    "G1": ("Grecia", "Super League"),
    "SC0": ("Scozia", "Premiership"), "SC1": ("Scozia", "Championship"),
    "SC2": ("Scozia", "League One"), "SC3": ("Scozia", "League Two"),
}
TOP = ["Inghilterra", "Spagna", "Italia", "Germania", "Francia"]
SEASONS_BACK = 5      # stagioni usate per allenare il modello
USE_SHOTS = True      # True = il modello usa anche i tiri (non solo i gol); False = solo gol
SHOT_W = 0.5          # peso dei gol veri rispetto ai gol stimati dai tiri
XI = 0.002            # peso decrescente nel tempo (per giorno)
MIN_VALUE = 0.03      # valore minimo per consigliare una giocata
MIN_PROB = 0.30       # probabilita' minima per consigliare una giocata


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def pdate(s):
    s = (s or "").strip()
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def seasons(today):
    y = today.year if today.month >= 7 else today.year - 1
    return [f"{(y - i) % 100:02d}{(y - i + 1) % 100:02d}" for i in range(SEASONS_BACK)]


def load_results(today):
    res = {c: [] for c in LEAGUES}
    for s in seasons(today):
        for c in LEAGUES:
            try:
                text = get(f"{BASE}/mmz4281/{s}/{c}.csv")
            except Exception as e:
                print("salto", s, c, e)
                continue
            for r in rows(text):
                d = pdate(r.get("Date"))
                try:
                    hg, ag = int(r["FTHG"]), int(r["FTAG"])
                except (KeyError, ValueError, TypeError):
                    continue
                if d and r.get("HomeTeam") and r.get("AwayTeam"):
                    res[c].append({"d": d, "h": r["HomeTeam"].strip(), "a": r["AwayTeam"].strip(),
                                   "hg": hg, "ag": ag, "r": r})
    return res


def load_fixtures():
    out = []
    for r in rows(get(f"{BASE}/fixtures.csv")):
        c = (r.get("Div") or "").strip()
        d = pdate(r.get("Date"))
        if d and c in LEAGUES and r.get("HomeTeam") and r.get("AwayTeam"):
            out.append((c, d, (r.get("Time") or "").strip(), r["HomeTeam"].strip(), r["AwayTeam"].strip(), r))
    return out


def num(r, k):
    try:
        return float(r[k])
    except (KeyError, ValueError, TypeError):
        return None


def obs(rows, use_shots=True, w=SHOT_W):
    """Converte le partite in 'gol effettivi': mix tra gol veri e gol stimati dai tiri (tiri in porta pesano di piu')."""
    def proxy(r, p):
        sh, st = num(r, p + "S"), num(r, p + "ST")
        return None if sh is None or st is None or st > sh else 0.30 * st + 0.05 * (sh - st)
    pr = [(proxy(x["r"], "H"), proxy(x["r"], "A")) if use_shots else (None, None) for x in rows]
    pairs = [(x["hg"] + x["ag"], a + b) for x, (a, b) in zip(rows, pr) if a is not None and b is not None]
    tp = sum(p for _, p in pairs)
    k = sum(g for g, _ in pairs) / tp if tp > 0 else 0
    out = []
    for x, (a, b) in zip(rows, pr):
        if a is None or b is None or k == 0:
            gh, ga = x["hg"], x["ag"]
        else:
            gh, ga = w * x["hg"] + (1 - w) * k * a, w * x["ag"] + (1 - w) * k * b
        out.append((x["d"], x["h"], x["a"], gh, ga))
    return out


def fit(ms, xi=XI):
    last = max(m[0] for m in ms)
    w = [math.exp(-xi * (last - m[0]).days) for m in ms]
    teams = {t for m in ms for t in (m[1], m[2])}
    at = dict.fromkeys(teams, 1.0)
    de = dict.fromkeys(teams, 1.0)
    mu, ha, K = 1.3, 1.25, 2.0
    for _ in range(40):
        na, da = dict.fromkeys(teams, K), dict.fromkeys(teams, K)
        nd, dd = dict.fromkeys(teams, K), dict.fromkeys(teams, K)
        for (d, h, a, hg, ag), wi in zip(ms, w):
            na[h] += wi * hg; da[h] += wi * mu * ha * de[a]
            na[a] += wi * ag; da[a] += wi * mu * de[h]
            nd[h] += wi * ag; dd[h] += wi * mu * at[a]
            nd[a] += wi * hg; dd[a] += wi * mu * ha * at[h]
        at = {t: na[t] / da[t] for t in teams}
        de = {t: nd[t] / dd[t] for t in teams}
        ma, md = sum(at.values()) / len(at), sum(de.values()) / len(de)
        at = {t: v / ma for t, v in at.items()}
        de = {t: v / md for t, v in de.items()}
        hn = hd = an = ad = 0.0
        for (d, h, a, hg, ag), wi in zip(ms, w):
            hn += wi * hg; hd += wi * mu * at[h] * de[a]
            an += wi * ag; ad += wi * at[a] * de[h]
        ha, mu = hn / hd, an / ad
    return at, de, mu, ha


def pois(l, k):
    return math.exp(-l) * l ** k / math.factorial(k)


def odd(r, key):
    for pre in ("Avg", "B365", "PS"):
        try:
            v = float(r[pre + key])
            if v > 1:
                return v
        except (KeyError, ValueError, TypeError):
            pass
    return None


def predict(model, h, a, r):
    at, de, mu, ha = model
    lh, la = mu * ha * at[h] * de[a], mu * at[a] * de[h]
    H = D = A = o = b = 0.0
    sc = []
    for i in range(10):
        for j in range(10):
            p = pois(lh, i) * pois(la, j)
            if i > j: H += p
            elif i < j: A += p
            else: D += p
            if i + j > 2: o += p
            if i > 0 and j > 0: b += p
            sc.append([f"Risultato {i}-{j}", "Risultato esatto", p, None])
    s = H + D + A
    H, D, A, o, b = H / s, D / s, A / s, o / s, b / s
    picks = [
        ["1 " + h, "Esito finale", H, odd(r, "H")], ["X", "Esito finale", D, odd(r, "D")],
        ["2 " + a, "Esito finale", A, odd(r, "A")],
        ["1X", "Doppia chance", H + D, None], ["X2", "Doppia chance", D + A, None],
        ["12", "Doppia chance", H + A, None],
        ["Over 2,5", "Under/Over", o, odd(r, ">2.5")], ["Under 2,5", "Under/Over", 1 - o, odd(r, "<2.5")],
        ["Gol", "Gol/No Gol", b, None], ["No Gol", "Gol/No Gol", 1 - b, None],
    ]
    for x, k in zip(picks, ["1", "X", "2", "1X", "X2", "12", "O", "U", "G", "NG"]):
        x.append(k)
    core = [x for x in picks if x[1] in ("Esito finale", "Under/Over", "Gol/No Gol")]
    cands = [x for x in picks if x[3]]
    rec = None
    best = max(cands, key=lambda x: x[2] * x[3] - 1, default=None)
    if best and best[2] * best[3] - 1 >= MIN_VALUE and best[2] >= MIN_PROB:
        rec = best
    elif not cands:
        top = max(core, key=lambda x: x[2])
        if top[2] >= 0.60:
            rec = top
    allp = sorted(picks + sorted(sc, key=lambda x: -x[2])[:3], key=lambda x: -x[2])
    rd = lambda x: round(x, 4)
    return {
        "pk": [[x[0], x[1], rd(x[2]), x[3]] for x in allp],
        "rec": None if not rec else {"label": rec[0], "key": rec[4], "market": rec[1], "p": rd(rec[2]), "odd": rec[3],
                                      "v": rd(rec[2] * rec[3] - 1) if rec[3] else None},
        "conf": rd(max(x[2] for x in core)),
        "top": (lambda t: {"label": t[0], "market": t[1], "p": rd(t[2]), "key": t[4]})(max(picks, key=lambda x: x[2])),
    }


def local_time(d, t):
    try:
        hh, mm = map(int, t.split(":"))
        dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=ZoneInfo("Europe/London")).astimezone(ZoneInfo("Europe/Rome"))
        return dt.date(), dt.strftime("%H:%M")
    except Exception:
        return d, ""


EN = {"Inghilterra": "England", "Spagna": "Spain", "Italia": "Italy", "Germania": "Germany", "Francia": "France",
      "Paesi Bassi": "Netherlands", "Belgio": "Belgium", "Portogallo": "Portugal", "Turchia": "Turkey",
      "Grecia": "Greece", "Scozia": "Scotland"}
ALIAS = {"Man City": "Manchester City", "Man United": "Manchester United", "Inter": "Inter Milan", "Milan": "AC Milan",
         "Nott'm Forest": "Nottingham Forest", "Sheffield Utd": "Sheffield United", "Wolves": "Wolverhampton Wanderers",
         "Tottenham": "Tottenham Hotspur", "Newcastle": "Newcastle United", "West Ham": "West Ham United",
         "Leeds": "Leeds United", "Brighton": "Brighton & Hove Albion", "Ath Madrid": "Atletico Madrid",
         "Ath Bilbao": "Athletic Bilbao", "Betis": "Real Betis", "Sociedad": "Real Sociedad", "Espanol": "Espanyol",
         "Vallecano": "Rayo Vallecano", "Celta": "Celta Vigo", "M'gladbach": "Borussia Monchengladbach",
         "Dortmund": "Borussia Dortmund", "Leverkusen": "Bayer Leverkusen", "Ein Frankfurt": "Eintracht Frankfurt",
         "Paris SG": "Paris Saint-Germain", "St Etienne": "Saint-Etienne", "Sp Lisbon": "Sporting CP",
         "Sp Braga": "Braga"}
LOGO_FILE = "logos.json"
MAX_LOOKUPS = 60      # ricerche nuove per ogni esecuzione (le altre si completano nei giorni dopo)


def find_logo(name, co):
    q = urllib.parse.quote(ALIAS.get(name, name))
    data = json.loads(get(f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={q}"))
    for t in data.get("teams") or []:
        if t.get("strSport") == "Soccer" and t.get("strCountry") == EN.get(co):
            return t.get("strBadge") or t.get("strTeamBadge") or ""
    return ""   # risposta valida ma squadra non trovata


def load_logos(pairs):
    try:
        cache = json.load(open(LOGO_FILE, encoding="utf-8"))
    except Exception:
        cache = {}
    n = 0
    for name, co in sorted(pairs):
        if name in cache or n >= MAX_LOOKUPS:
            continue
        try:
            cache[name] = find_logo(name, co)
        except Exception as e:      # errore di rete o limite: riprova al prossimo giro
            print("logo non scaricato", name, e)
        n += 1
        time.sleep(2.5)
    json.dump(cache, open(LOGO_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    return cache


HIST_FILE = "history.json"


def won(key, hg, ag):
    return {"1": hg > ag, "X": hg == ag, "2": hg < ag, "1X": hg >= ag, "X2": hg <= ag, "12": hg != ag,
            "O": hg + ag > 2, "U": hg + ag <= 2, "G": hg > 0 and ag > 0, "NG": hg == 0 or ag == 0}.get(key)


def update_history(out, res, today):
    """Memorizza la scommessa con probabilita' piu' alta di ogni partita e, a gara finita, la verifica."""
    try:
        hist = json.load(open(HIST_FILE, encoding="utf-8"))
    except Exception:
        hist = {}
    t0 = today.isoformat()
    for x in out:
        i = f"{x['c']}|{x['d']}|{x['h']}|{x['a']}"
        if x["d"] > t0 or i not in hist:      # fino al giorno prima la previsione si aggiorna, poi si congela
            hist[i] = {k: x[k] for k in ("c", "co", "lg", "d", "t", "h", "a", "top", "hl", "al")}
    idx = {}
    for c, ms in res.items():
        for x in ms:
            idx.setdefault((c, x["h"], x["a"]), []).append((x["d"], x["hg"], x["ag"]))
    for i in list(hist):
        e = hist[i]
        if e["d"] < (today - timedelta(days=120)).isoformat():
            del hist[i]
        elif e.get("res") is None and e["d"] <= t0:
            ed = date.fromisoformat(e["d"])
            for d, hg, ag in idx.get((e["c"], e["h"], e["a"]), []):
                if abs((d - ed).days) <= 1:
                    e["res"] = [hg, ag]
                    e["won"] = won(e["top"]["key"], hg, ag)
                    break
    json.dump(hist, open(HIST_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    return hist


def norm(s):
    return re.sub(r"[^a-z]", "", s.lower())


def same(a, b):
    a, b = norm(ALIAS.get(a, a)), norm(b)
    return bool(a and b) and (a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)


def load_world(today, out):
    """Calendario di tutte le altre partite di calcio nel mondo (senza pronostico), da TheSportsDB."""
    pred = {}
    for x in out:
        pred.setdefault(x["d"], []).append(x["h"])
    world = []
    for k in range(7):
        day = (today + timedelta(days=k)).isoformat()
        try:
            data = json.loads(get(f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={day}&s=Soccer"))
        except Exception as e:
            print("mondo: salto", day, e)
            continue
        for ev in data.get("events") or []:
            h, a, lg = (ev.get("strHomeTeam") or "").strip(), (ev.get("strAwayTeam") or "").strip(), (ev.get("strLeague") or "").strip()
            if not h or not a or not lg or ev.get("strSport", "Soccer") != "Soccer":
                continue
            d, t = ev.get("dateEvent") or day, ""
            try:
                if ev.get("strTime"):
                    dt = datetime.fromisoformat((ev.get("strTimestamp") or f"{d}T{ev['strTime']}").replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                    dt = dt.astimezone(ZoneInfo("Europe/Rome"))
                    d, t = dt.date().isoformat(), dt.strftime("%H:%M")
            except Exception:
                pass
            if any(same(p, h) for p in pred.get(d, [])):
                continue            # gia' presente con pronostico
            world.append({"c": "w|" + lg, "co": "", "lg": lg, "d": d, "t": t, "h": h, "a": a,
                          "hl": ev.get("strHomeTeamBadge") or None, "al": ev.get("strAwayTeamBadge") or None, "w": 1})
    world.sort(key=lambda x: (x["lg"], x["d"], x["t"]))
    print("mondo:", len(world), "partite")
    return world[:2500]


def main():
    today = date.today()
    res = load_results(today)
    models = {c: fit(obs(ms, USE_SHOTS)) for c, ms in res.items() if len(ms) >= 30}
    out = []
    for c, d, t, h, a, r in load_fixtures():
        m = models.get(c)
        d, t = local_time(d, t)
        if not m or h not in m[0] or a not in m[0] or d < today:
            continue
        co, lg = LEAGUES[c]
        out.append({"c": c, "co": co, "lg": lg, "d": d.isoformat(), "t": t, "h": h, "a": a, **predict(m, h, a, r)})
    logos = load_logos({(x["h"], x["co"]) for x in out} | {(x["a"], x["co"]) for x in out})
    for x in out:
        x["hl"], x["al"] = logos.get(x["h"]) or None, logos.get(x["a"]) or None
    sk = lambda x: (TOP.index(x["co"]) if x["co"] in TOP else 10, "" if x["co"] in TOP else x["co"],
                    list(LEAGUES).index(x["c"]), x["d"], x["t"])
    out.sort(key=sk)
    hist = update_history(out, res, today)
    cut = (today - timedelta(days=14)).isoformat()
    done = sorted([e for e in hist.values() if e.get("res") and e["d"] >= cut], key=sk)
    fin = [e for e in hist.values() if e.get("res")]
    stats = {"n": len(fin), "w": sum(1 for e in fin if e.get("won"))}
    world = load_world(today, out)
    data = {"updated": datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M"),
            "demo": bool(os.environ.get("DEMO")), "matches": out, "world": world, "done": done, "stats": stats}
    tpl = open("template.html", encoding="utf-8").read()
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    os.makedirs("docs", exist_ok=True)
    open("docs/index.html", "w", encoding="utf-8").write(tpl.replace("__DATA__", js))
    print(f"Fatto: {len(out)} partite in {len({x['c'] for x in out})} campionati")


if __name__ == "__main__":
    main()
