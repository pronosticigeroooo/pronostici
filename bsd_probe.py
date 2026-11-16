#!/usr/bin/env python3
"""TEST TEMPORANEO di Bzzoiro Sports Data: controlla che la chiave funzioni e mostra la STRUTTURA dei dati
(nomi dei campi e piccoli esempi, mai la chiave) nella pagina docs/bsd-test.html."""
import html, json, os, urllib.error, urllib.request
from datetime import date, timedelta

BASE = "https://sports.bzzoiro.com/api/v2/"
KEY = os.environ.get("BSD_KEY", "").strip()


def call(path, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(BASE + path + ("?" + q if q else ""),
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


def main():
    parts = []
    if not KEY:
        parts.append("<p><b>Chiave mancante:</b> il segreto BSD_KEY non è stato impostato su GitHub.</p>")
    else:
        today = date.today()
        st, hdr, ev, err = fetch_all("events/", date_from=today.isoformat(), date_to=(today + timedelta(days=7)).isoformat())
        parts.append(f"<h2>Prossimi 7 giorni</h2><p>Codice risposta: <b>{st}</b> · partite trovate: <b>{len(ev)}</b></p>")
        for k in ("RateLimit-Policy", "RateLimit"):
            if k in hdr:
                parts.append(f"<p>{k}: {html.escape(hdr[k])}</p>")
        if err:
            parts.append("<pre>" + html.escape(json.dumps(err, ensure_ascii=False)[:600]) + "</pre>")
        if ev:
            cnt = {}
            for e in ev:
                cnt[league_of(e)] = cnt.get(league_of(e), 0) + 1
            rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in sorted(cnt.items(), key=lambda x: -x[1]))
            parts.append(f"<h2>Campionati ({len(cnt)})</h2><table>{rows}</table>")
            parts.append("<h2>Struttura di una partita</h2><pre>" + html.escape(json.dumps(shape(ev[0]), ensure_ascii=False, indent=1)) + "</pre>")
            withodds = next((e for e in ev if any("odds" in k for k in e)), None)
            if withodds:
                parts.append("<h2>Campi con le quote</h2><pre>" + html.escape(json.dumps({k: shape(v) for k, v in withodds.items() if "odds" in k or "prob" in k}, ensure_ascii=False, indent=1)) + "</pre>")
        st2, _, fin, err2 = fetch_all("events/", pages=1, status="finished", date_from=(today - timedelta(days=7)).isoformat(), date_to=today.isoformat())
        parts.append(f"<h2>Partite finite (ultimi 7 giorni)</h2><p>Codice: <b>{st2}</b> · trovate in 1 pagina: <b>{len(fin)}</b></p>")
        if fin:
            parts.append("<pre>" + html.escape(json.dumps({k: v for k, v in shape(fin[0]).items() if k in ("home_score", "away_score", "status", "score", "scores", "result")}, ensure_ascii=False, indent=1)) + "</pre>")
        if err2:
            parts.append("<pre>" + html.escape(json.dumps(err2, ensure_ascii=False)[:400]) + "</pre>")
    page = ("<!DOCTYPE html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Test BSD</title><style>body{font:15px system-ui;max-width:800px;margin:0 auto;padding:16px}pre{background:#f2f4f7;padding:10px;overflow:auto;font-size:12px}"
            "td{padding:3px 10px;border-bottom:1px solid #eee}</style></head><body><h1>Test BSD (temporaneo)</h1>" + "".join(parts) + "</body></html>")
    os.makedirs("docs", exist_ok=True)
    open("docs/bsd-test.html", "w", encoding="utf-8").write(page)
    print("pagina creata")


if __name__ == "__main__":
    main()
