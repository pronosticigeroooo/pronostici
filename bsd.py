"""Fonte dati principale: Bzzoiro Sports Data (calendario mondiale, quote, assenti, pronostici).
Se qualcosa non funziona, update.py usa le fonti di riserva."""
import difflib, json, re, time, unicodedata, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE = "https://sports.bzzoiro.com/api/v2/"
HORIZON = 7        # giorni di calendario mostrati
WORKERS = 6
ROME, UTC = ZoneInfo("Europe/Rome"), ZoneInfo("UTC")
FD = {("Serie A", "Italy"): "I1", ("Serie B", "Italy"): "I2", ("Premier League", "England"): "E0",
      ("Championship", "England"): "E1", ("League One", "England"): "E2", ("League Two", "England"): "E3",
      ("La Liga", "Spain"): "SP1", ("Segunda División", "Spain"): "SP2", ("Bundesliga", "Germany"): "D1",
      ("2. Bundesliga", "Germany"): "D2", ("Ligue 1", "France"): "F1", ("Ligue 2", "France"): "F2",
      ("Eredivisie", "Netherlands"): "N1", ("Pro League", "Belgium"): "B1", ("Primeira Liga", "Portugal"): "P1",
      ("Trendyol Super Lig", "Turkey"): "T1", ("Stoiximan Super League", "Greece"): "G1",
      ("Scottish Premiership", "Scotland"): "SC0"}
C = {  # paese in inglese: (italiano, codice bandiera)
    "Italy": ("Italia", "IT"), "England": ("Inghilterra", "ENG"), "Spain": ("Spagna", "ES"), "Germany": ("Germania", "DE"),
    "France": ("Francia", "FR"), "Netherlands": ("Paesi Bassi", "NL"), "Belgium": ("Belgio", "BE"), "Portugal": ("Portogallo", "PT"),
    "Turkey": ("Turchia", "TR"), "Greece": ("Grecia", "GR"), "Scotland": ("Scozia", "SCT"), "Wales": ("Galles", "WLS"),
    "Brazil": ("Brasile", "BR"), "Argentina": ("Argentina", "AR"), "USA": ("Stati Uniti", "US"), "Mexico": ("Messico", "MX"),
    "Japan": ("Giappone", "JP"), "Saudi Arabia": ("Arabia Saudita", "SA"), "South Korea": ("Corea del Sud", "KR"),
    "Australia": ("Australia", "AU"), "Poland": ("Polonia", "PL"), "Sweden": ("Svezia", "SE"), "Norway": ("Norvegia", "NO"),
    "Denmark": ("Danimarca", "DK"), "Switzerland": ("Svizzera", "CH"), "Austria": ("Austria", "AT"),
    "Czech Republic": ("Repubblica Ceca", "CZ"), "Romania": ("Romania", "RO"), "Bulgaria": ("Bulgaria", "BG"),
    "Slovakia": ("Slovacchia", "SK"), "Chile": ("Cile", "CL"), "Colombia": ("Colombia", "CO"), "Ecuador": ("Ecuador", "EC"),
    "Peru": ("Perù", "PE"), "Nigeria": ("Nigeria", "NG"), "Tunisia": ("Tunisia", "TN"), "Angola": ("Angola", "AO"),
    "Ukraine": ("Ucraina", "UA"), "Croatia": ("Croazia", "HR"), "Serbia": ("Serbia", "RS"), "Hungary": ("Ungheria", "HU"),
    "Ireland": ("Irlanda", "IE"), "Egypt": ("Egitto", "EG"), "Morocco": ("Marocco", "MA"), "South Africa": ("Sudafrica", "ZA"),
    "China": ("Cina", "CN"), "Israel": ("Israele", "IL"), "Russia": ("Russia", "RU"), "Finland": ("Finlandia", "FI"),
    "Iceland": ("Islanda", "IS"), "Uruguay": ("Uruguay", "UY"), "Paraguay": ("Paraguay", "PY"), "Bolivia": ("Bolivia", "BO"),
    "Venezuela": ("Venezuela", "VE"), "Costa Rica": ("Costa Rica", "CR"), "Cyprus": ("Cipro", "CY"), "Slovenia": ("Slovenia", "SI"),
    "Europe": ("Europa", "EU"), "International": ("Internazionale", "WLD"), "World": ("Mondo", "WLD"),
    "North America": ("Nord America", "WLD"), "South America": ("Sud America", "WLD"), "Africa": ("Africa", "WLD"), "Asia": ("Asia", "WLD")}


def flag(code):
    if code in ("ENG", "SCT", "WLS"):
        t = {"ENG": "gbeng", "SCT": "gbsct", "WLS": "gbwls"}[code]
        return chr(0x1F3F4) + "".join(chr(0xE0000 + ord(c)) for c in t) + chr(0xE007F)
    if code == "WLD":
        return "\U0001F30D"
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code) if len(code) == 2 else ""


def norm(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())


def api(path, key):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Token " + key, "User-Agent": "pronostici-bot"})
    for k in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and k < 2:
                time.sleep(5 * (k + 1))
                continue
            raise
        except Exception:
            if k == 2:
                raise
            time.sleep(2)


def pages(path, key, max_pages=15, **q):
    out = []
    for p in range(max_pages):
        body = api(path + "?" + urllib.parse.urlencode({**q, "limit": 200, "offset": p * 200}), key)
        res = body.get("results") if isinstance(body, dict) else body
        if not res:
            break
        out += res
        if len(res) < 200:
            break
    return out


def num(x):
    try:
        v = float(x)
        return v if v > 1 else None
    except (TypeError, ValueError):
        return None


def when(s):
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(ROME)


def mapteam(name, names, rev):
    n = rev.get(name, name)
    if n in names:
        return n
    cand = {norm(k): k for k in names}
    if norm(n) in cand:
        return cand[norm(n)]
    m = difflib.get_close_matches(norm(n), cand, 1, 0.8)
    return cand[m[0]] if m else None


def ours(U, models, rev, code, h, a):
    m = models.get(code)
    if not m:
        return None
    h2, a2 = mapteam(h, m[0], rev), mapteam(a, m[0], rev)
    if not h2 or not a2:
        return None
    g = {}
    for lab, mk, p, o in U.predict(m, h2, a2, {})["pk"]:
        if mk == "Esito finale":
            g["H" if lab.startswith("1 ") else "A" if lab.startswith("2 ") else "D"] = p
        elif lab == "Over 2,5":
            g["O"] = p
        elif lab == "Gol":
            g["B"] = p
    return [g["H"], g["D"], g["A"], g["O"], g["B"]]


def theirs(mk):
    try:
        r, ou, b = mk["match_result"], mk["over_under"], mk["btts"]
        return [r["prob_home"] / 100, r["prob_draw"] / 100, r["prob_away"] / 100, ou["prob_over_25"] / 100, b["prob_yes"] / 100]
    except (KeyError, TypeError):
        return None


def picks(U, h, a, v, od):
    H, D, A, o, b = v
    s = H + D + A
    H, D, A = H / s, D / s, A / s
    P = [["1 " + h, "Esito finale", H, num(od.get("home_win")), "1"], ["X", "Esito finale", D, num(od.get("draw")), "X"],
         ["2 " + a, "Esito finale", A, num(od.get("away_win")), "2"], ["1X", "Doppia chance", H + D, None, "1X"],
         ["X2", "Doppia chance", D + A, None, "X2"], ["12", "Doppia chance", H + A, None, "12"],
         ["Over 2,5", "Under/Over", o, num(od.get("over_25_goals")), "O"], ["Under 2,5", "Under/Over", 1 - o, num(od.get("under_25_goals")), "U"],
         ["Gol", "Gol/No Gol", b, num(od.get("btts_yes")), "G"], ["No Gol", "Gol/No Gol", 1 - b, num(od.get("btts_no")), "NG"]]
    rd = lambda x: round(x, 4)
    cands = [x for x in P if x[3]]
    val = lambda x: x[2] * x[3] - 1
    best = max(cands, key=val, default=None)
    weak = False
    if not (best and val(best) >= U.MIN_VALUE and best[2] >= U.MIN_PROB):
        c2 = [x for x in cands if x[2] >= U.MIN_PROB]
        best, weak = (max(c2, key=val) if c2 else None), True
    rec = None
    if best:
        rec = {"label": best[0], "key": best[4], "market": best[1], "p": rd(best[2]), "odd": best[3], "v": rd(val(best)), "weak": weak}
    t = max(P, key=lambda x: x[2])
    core = [x for x in P if x[1] in ("Esito finale", "Under/Over", "Gol/No Gol")]
    return {"pk": [[x[0], x[1], rd(x[2]), x[3]] for x in sorted(P, key=lambda x: -x[2])], "rec": rec,
            "conf": rd(max(x[2] for x in core)), "top": {"label": t[0], "market": t[1], "p": rd(t[2]), "key": t[4]}}


def build(U, today, key, models):
    end = today + timedelta(days=HORIZON)
    leagues = {x["id"]: x for x in pages("leagues/", key, 4) if isinstance(x, dict) and "id" in x}
    ev = [e for e in pages("events/", key, date_from=today.isoformat(), date_to=end.isoformat())
          if e.get("status") == "notstarted" and today <= when(e["event_date"]).date() <= end]
    preds = {}
    try:
        for p in pages("predictions/", key):
            e = p.get("event") or {}
            if e.get("id"):
                preds[e["id"]] = p.get("markets") or {}
    except Exception as e:
        print("bsd: pronostici non disponibili", e)

    def safe(path):
        try:
            return api(path, key)
        except Exception:
            return None
    ids = [e["id"] for e in ev]
    with ThreadPoolExecutor(WORKERS) as ex:
        odds = dict(zip(ids, ex.map(lambda i: safe(f"events/{i}/odds/"), ids)))
    rev = {v: k for k, v in U.ALIAS.items()}
    out, n_ours, n_odds = [], 0, 0
    for e in ev:
        L = leagues.get(e["league_id"], {})
        name, ctry = L.get("name") or f"Lega {e['league_id']}", L.get("country") or ""
        code = FD.get((name, ctry))
        h, a = e["home_team"], e["away_team"]
        vecs = [v for v in (ours(U, models, rev, code, h, a) if code else None, theirs(preds.get(e["id"], {}))) if v]
        if not vecs:
            continue
        v = [sum(x[i] for x in vecs) / len(vecs) for i in range(5)]
        od = ((odds.get(e["id"]) or {}).get("odds")) or {}
        n_odds += bool(od)
        n_ours += bool(code and ours(U, models, rev, code, h, a))
        d = when(e["event_date"])
        it, fl = C.get(ctry, (ctry, ""))
        rec = {"c": f"b{e['league_id']}", "co": it, "fl": flag(fl), "lg": name + (" (F)" if L.get("is_women") else ""),
               "d": d.date().isoformat(), "t": d.strftime("%H:%M"), "ts": int(d.timestamp()), "h": h, "a": a, "hl": None, "al": None,
               "src": "nostro modello + BSD" if len(vecs) == 2 else ("nostro modello" if code and ours(U, models, rev, code, h, a) else "BSD"),
               **picks(U, h, a, v, od)}
        out.append(rec)
    res = {}
    try:      # risultati recenti per verificare le scommesse passate
        for e in pages("events/", key, 3, status="finished", date_from=(today - timedelta(days=4)).isoformat(), date_to=today.isoformat()):
            if e.get("home_score") is not None and e.get("away_score") is not None:
                res.setdefault((f"b{e['league_id']}", e["home_team"], e["away_team"]), []).append(
                    (when(e["event_date"]).date(), int(e["home_score"]), int(e["away_score"])))
    except Exception as e:
        print("bsd: risultati non disponibili", e)
    print(f"bsd: {len(ev)} partite, {len(out)} con pronostico, {n_odds} con quote, {n_ours} col nostro modello, {len(res)} risultati")
    return out, res
