"""Nazionali (Nations League) e coppe europee dei club (Champions, Europa, Conference League).
Non ha quote di mercato: calcola solo le percentuali. Se qualcosa non funziona, update.py lo salta."""
import csv, difflib, io, json, math, re, unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FD = "https://fixturedownload.com/"
FEEDS = {  # codice: (slug, nome in pagina)
    "NL": ("nations-league-2026", "UEFA Nations League"),
    "CL": ("champions-league-2026", "UEFA Champions League"),
    "EL": ("europa-league-2026", "UEFA Europa League"),
    "ECL": ("conference-league-2026", "UEFA Conference League"),
}
RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
ELO_URL = "http://api.clubelo.com/"
HORIZON_DAYS = 10       # si mostrano le partite dei prossimi giorni
HFA = 65                # vantaggio del campo (punti Elo) per i club
NAT_ALIAS = {"Türkiye": "Turkey", "Czechia": "Czech Republic"}
CLUB_ALIAS = {"Atleti": "Atletico", "Paris": "Paris SG", "Man Utd": "Man United", "Bayern München": "Bayern",
              "B. Dortmund": "Dortmund", "Real Betis": "Betis", "Real Sociedad": "Sociedad", "Sporting CP": "Sporting",
              "Club Brugge": "Brugge", "S. Bratislava": "Slovan Bratislava", "Union SG": "St Gillis",
              "AZ Alkmaar": "AZ", "N.E.C.": "Nijmegen", "Leverkusen": "Leverkusen", "Milan": "Milan"}
ROME, UTC = ZoneInfo("Europe/Rome"), ZoneInfo("UTC")


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def feed(U, slug):
    """Partite (data UTC, casa, trasferta, gol casa, gol trasferta) dal calendario."""
    out = []
    try:
        for r in json.loads(U.get(FD + "feed/json/" + slug)):
            dt = datetime.fromisoformat(r["DateUtc"].replace(" ", "T").replace("Z", "+00:00"))
            out.append((dt, r["HomeTeam"], r["AwayTeam"], r.get("HomeTeamScore"), r.get("AwayTeamScore")))
        return out
    except Exception as e:
        print("extra: json non disponibile", slug, e)
    try:
        for r in csv.DictReader(io.StringIO(U.get(FD + "download/csv/" + slug))):
            dt = datetime.strptime(r["Date"].strip(), "%d/%m/%Y %H:%M").replace(tzinfo=UTC)
            m = re.match(r"\s*(\d+)\s*-\s*(\d+)", r.get("Result") or "")
            out.append((dt, r["Home Team"], r["Away Team"], m and m.group(1), m and m.group(2)))
    except Exception as e:
        print("extra: csv non disponibile", slug, e)
    return out


def score(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def lambdas(U, dr, T=2.7):
    """Trasforma la differenza di Elo in gol attesi (stessa probabilita' di vittoria attesa)."""
    E = 1 / (1 + 10 ** (-dr / 400))
    lo, hi = -T + 0.05, T - 0.05
    for _ in range(40):
        s = (lo + hi) / 2
        lh, la = (T + s) / 2, (T - s) / 2
        H = D = 0.0
        for i in range(9):
            pi = U.pois(lh, i)
            for j in range(9):
                p = pi * U.pois(la, j)
                H += p if i > j else 0
                D += p if i == j else 0
        lo, hi = (s, hi) if H + D / 2 < E else (lo, s)
    return lh, la


def record(code, lg, dt, h, a, pr, hist_key):
    d = dt.astimezone(ROME)
    pr["rec"] = None            # niente quote: nessuna giocata "consigliata"
    return {"c": code, "co": "Europa", "lg": lg, "d": d.date().isoformat(), "t": d.strftime("%H:%M"),
            "h": h, "a": a, "hl": None, "al": None, **pr}


def build(U, today):
    out, res, feeds = [], {}, {}
    end = today + timedelta(days=HORIZON_DAYS)
    for code, (slug, lg) in FEEDS.items():
        feeds[code] = feed(U, slug)
        for dt, h, a, hs, as_ in feeds[code]:
            hs, as_ = score(hs), score(as_)
            if hs is not None and as_ is not None:
                res.setdefault((code, h, a), []).append((dt.astimezone(ROME).date(), hs, as_))

    def upcoming(code):
        for dt, h, a, hs, as_ in feeds[code]:
            if score(hs) is None and today <= dt.astimezone(ROME).date() <= end:
                yield dt, h, a

    # --- Nazionali: modello Poisson sui risultati storici ---
    try:
        rows = []
        for r in csv.DictReader(io.StringIO(U.get(RESULTS_URL))):
            d = U.pdate(r.get("date"))
            hg, ag = score(r.get("home_score")), score(r.get("away_score"))
            if d and hg is not None and ag is not None and d >= today - timedelta(days=2200):
                rows.append({"d": d, "h": r["home_team"], "a": r["away_team"], "hg": hg, "ag": ag, "r": {}})
        names = {x["h"] for x in rows} | {x["a"] for x in rows}
        have = {(x["h"], x["a"], x["d"]) for x in rows}

        def nat(n):
            n = NAT_ALIAS.get(n, n)
            if n in names:
                return n
            m = difflib.get_close_matches(n, names, 1, 0.85)
            return m[0] if m else None
        for (code, h, a), lst in res.items():
            if code == "NL" and nat(h) and nat(a):
                for d, hg, ag in lst:
                    if (nat(h), nat(a), d) not in have:
                        rows.append({"d": d, "h": nat(h), "a": nat(a), "hg": hg, "ag": ag, "r": {}})
        model = U.fit(U.obs(rows, False))
        for dt, h, a in upcoming("NL"):
            h2, a2 = nat(h), nat(a)
            if h2 in model[0] and a2 in model[0]:
                out.append(record("NL", FEEDS["NL"][1], dt, h, a, U.predict(model, h2, a2, {}), None))
        print("extra: nazionali", sum(1 for x in out if x["c"] == "NL"))
    except Exception as e:
        print("extra: nazionali saltate", e)

    # --- Coppe dei club: rating Elo (clubelo.com) ---
    try:
        elo = {}
        for r in csv.DictReader(io.StringIO(U.get(ELO_URL + today.isoformat()))):
            if r.get("Club") and r.get("Elo"):
                elo[r["Club"]] = float(r["Elo"])
        keys = {norm(k): k for k in elo}

        def club(n):
            n = CLUB_ALIAS.get(n, n)
            k = keys.get(norm(n)) or (lambda m: keys.get(m[0]) if m else None)(difflib.get_close_matches(norm(n), keys, 1, 0.85))
            return k
        miss = 0
        for code in ("CL", "EL", "ECL"):
            for dt, h, a in upcoming(code):
                eh, ea = club(h), club(a)
                if not eh or not ea:
                    miss += 1
                    continue
                lh, la = lambdas(U, elo[eh] - elo[ea] + HFA)
                out.append(record(code, FEEDS[code][1], dt, h, a, U.predict_l(lh, la, h, a, {}), None))
        print("extra: coppe", sum(1 for x in out if x["c"] != "NL"), "partite; squadre non trovate:", miss)
    except Exception as e:
        print("extra: coppe saltate", e)
    return out, res
