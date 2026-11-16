#!/usr/bin/env python3
"""TEST TEMPORANEO di Bzzoiro Sports Data: controlla che la chiave funzioni e mostra la STRUTTURA dei dati
(nomi dei campi e piccoli esempi, mai la chiave) nella pagina docs/bsd-test.html."""
import html, json, os, urllib.error, urllib.request
from datetime import date, timedelta

BASE = "https://sports.bzzoiro.com/api/v2/"
KEY = os.environ.get("BSD_KEY", "").strip()


def call(path, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    sep = "&" if "?" in path else "?"
    req = urllib.request.Request(BASE + path + (sep + q if q else ""),
                                 headers={"Authorization": "Token " + KEY, "User-Agent": "pronostici-bot"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), {"error": e.read().decode("utf-8", "ignore")[:400]}
    except Exception as e:
        return 0, {}, {"error": str(e)[:400]}


def shape(o, depth=0):
    if isinstance(o, dict):
        return {k: shape(v, depth + 1) for k, v in list(o.items())[:70]} if depth < 4 else "{...}"
    if isinstance(o, list):
        return [shape(o[0], depth + 1)] if o else []
    return type(o).__name__ + ": " + repr(o)[:40]


def league_of(e):
    for k in ("league", "league_name", "tournament", "competition"):
        v = e.get(k)
        if isinstance(v, dict):
            v = v.get("name")
        if isinstance(v, str) and v:
            return v
    return "?"


def fetch_all(path, pages=12, **params):
    out, st, hdr = [], 0, {}
    for p in range(pages):
        st, hdr, data = call(path, limit=200, offset=p * 200, **params)
        res = data.get("results") if isinstance(data, dict) else None
        if st != 200 or res is None:
            return st, hdr, out, data
        out += res
        if len(res) < 200:
            break
    return st, hdr, out, None


def sec(title, st, obj):
    return f"<h3>{html.escape(title)} <small>(codice {st})</small></h3><pre>" + html.escape(json.dumps(obj, ensure_ascii=False, indent=1)[:2500]) + "</pre>"


def main():
    parts = []
    if not KEY:
        parts.append("<p><b>Chiave mancante:</b> il segreto BSD_KEY non è stato impostato su GitHub.</p>")
    else:
        today = date.today()
        st, hdr, ev, err = fetch_all("events/", date_from=today.isoformat(), date_to=(today + timedelta(days=7)).isoformat())
        parts.append(f"<h2>Partite dei prossimi 7 giorni: {len(ev)} (codice {st})</h2>")
        stl, _, lg, errl = fetch_all("leagues/", pages=4)
        names = {}
        for x in lg:
            if isinstance(x, dict) and x.get("id") is not None:
                names[x["id"]] = x
        parts.append(f"<h2>Campionati: {len(lg)} (codice {stl})</h2>")
        if lg:
            parts.append("<pre>" + html.escape(json.dumps(shape(lg[0]), ensure_ascii=False, indent=1)) + "</pre>")
        if errl:
            parts.append("<pre>" + html.escape(json.dumps(errl, ensure_ascii=False)[:400]) + "</pre>")
        cnt = {}
        for e in ev:
            cnt[e.get("league_id")] = cnt.get(e.get("league_id"), 0) + 1
        def nm(i):
            x = names.get(i, {})
            return " / ".join(str(x.get(k)) for k in ("name", "country", "country_name") if x.get(k)) or "?"
        rows = "".join(f"<tr><td>{k}</td><td>{html.escape(nm(k))}</td><td>{v}</td></tr>" for k, v in sorted(cnt.items(), key=lambda x: -x[1]))
        parts.append(f"<h2>Partite per campionato ({len(cnt)})</h2><table>{rows}</table>")
        pick = next((e for e in ev if any(t in nm(e.get("league_id")).lower() for t in ("serie a", "premier", "la liga", "bundesliga"))), ev[0] if ev else None)
        if pick:
            eid = pick["id"]
            parts.append(f"<h2>Ricerca quote e infortuni (partita {eid}: {html.escape(str(pick.get('home_team')))} - {html.escape(str(pick.get('away_team')))})</h2>")
            for path in ("", f"events/{eid}/", f"odds/?event_id={eid}", f"odds/?event={eid}", f"predictions/?event_id={eid}",
                         f"events/{eid}/odds/", f"events/{eid}/lineups/", f"unavailable-players/?event_id={eid}"):
                s2, _, d2 = call(path, limit=3) if "?" not in path else call(path)
                body = d2.get("results", d2) if isinstance(d2, dict) else d2
                parts.append(sec("/api/v2/" + path, s2, shape(body[0] if isinstance(body, list) and body else body)))
    page = ("<!DOCTYPE html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Test BSD</title><style>body{font:15px system-ui;max-width:800px;margin:0 auto;padding:16px}pre{background:#f2f4f7;padding:10px;overflow:auto;font-size:12px}"
            "td{padding:3px 10px;border-bottom:1px solid #eee}</style></head><body><h1>Test BSD 2 (temporaneo)</h1>" + "".join(parts) + "</body></html>")
    os.makedirs("docs", exist_ok=True)
    open("docs/bsd-test.html", "w", encoding="utf-8").write(page)
    print("pagina creata")


if __name__ == "__main__":
    main()
