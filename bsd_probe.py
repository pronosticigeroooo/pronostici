#!/usr/bin/env python3
"""TEST TEMPORANEO 3 di Bzzoiro Sports Data: cerca quote, pronostici, infortuni e formazioni."""
import html, json, os, urllib.error, urllib.request
from datetime import date, timedelta

BASE = "https://sports.bzzoiro.com/api/v2/"
KEY = os.environ.get("BSD_KEY", "").strip()
MAJOR = ("Serie A", "Premier League", "La Liga", "Bundesliga", "Ligue 1")


def call(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Token " + KEY, "User-Agent": "pronostici-bot"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "ignore")[:300]}
    except Exception as e:
        return 0, {"error": str(e)[:300]}


def shape(o, d=0):
    if isinstance(o, dict):
        return {k: shape(v, d + 1) for k, v in list(o.items())[:60]} if d < 4 else "{...}"
    if isinstance(o, list):
        return [shape(o[0], d + 1)] if o else []
    return type(o).__name__ + ": " + repr(o)[:40]


def items(b):
    return b.get("results", b) if isinstance(b, dict) else b


def sec(title, st, body):
    it = items(body)
    n = len(it) if isinstance(it, list) else "-"
    ex = shape(it[0]) if isinstance(it, list) and it else shape(it)
    return (f"<h3>{html.escape(title)} <small>(codice {st}, elementi {n})</small></h3><pre>"
            + html.escape(json.dumps(ex, ensure_ascii=False, indent=1)[:2200]) + "</pre>")


def main():
    parts = []
    if not KEY:
        parts.append("<p><b>Chiave mancante.</b></p>")
    else:
        today = date.today()
        st, b = call(f"events/?date_from={today}&date_to={today + timedelta(days=3)}&limit=200")
        ev = items(b) if st == 200 else []
        st, b = call(f"events/?status=finished&date_from={today - timedelta(days=7)}&date_to={today}&limit=200")
        fin = items(b) if st == 200 else []
        names = {x["id"]: x.get("name", "") for x in items(call("leagues/?limit=200")[1]) if isinstance(x, dict) and "id" in x}
        pick = [e for e in ev if names.get(e.get("league_id")) in MAJOR][:5] or ev[:5]
        old = [e for e in fin if names.get(e.get("league_id")) in MAJOR][:3] or fin[:3]
        parts.append(f"<h2>Partite nei prossimi 3 giorni: {len(ev)} · finite negli ultimi 7 giorni: {len(fin)}</h2>")
        for label, lst in (("PROSSIMA", pick), ("FINITA", old)):
            for e in lst:
                t = f"Quote partita {label} {e['id']}: {e.get('home_team')} - {e.get('away_team')} ({names.get(e.get('league_id'))}, {str(e.get('event_date'))[:10]})"
                s2, b2 = call(f"odds/?event_id={e['id']}")
                parts.append(sec(t, s2, b2))
        if pick:
            eid = pick[0]["id"]
            for path in (f"events/{eid}/", f"events/{eid}/odds/", f"events/{eid}/lineups/", f"events/{eid}/predictions/",
                         f"events/{eid}/unavailable-players/", "predictions/?limit=2", f"predictions/?event={eid}",
                         f"predictions/?match_id={eid}", "odds/?limit=2", "injuries/?limit=2", "lineups/?limit=2",
                         "unavailable-players/?limit=2"):
                s2, b2 = call(path)
                parts.append(sec("/api/v2/" + path, s2, b2))
    page = ("<!DOCTYPE html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Test BSD 3</title><style>body{font:15px system-ui;max-width:800px;margin:0 auto;padding:16px}pre{background:#f2f4f7;padding:10px;overflow:auto;font-size:12px}"
            "</style></head><body><h1>Test BSD 3 (temporaneo)</h1>" + "".join(parts) + "</body></html>")
    os.makedirs("docs", exist_ok=True)
    open("docs/bsd-test.html", "w", encoding="utf-8").write(page)
    print("pagina creata")


if __name__ == "__main__":
    main()
