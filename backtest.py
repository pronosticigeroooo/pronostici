#!/usr/bin/env python3
"""BACKTEST TEMPORANEO (da eliminare dopo l'uso: questo file, backtest.yml e docs/backtest.html).
Simula le ultime 2 stagioni concluse: per ogni partita il modello usa solo i dati precedenti,
poi confronta previsioni, bookmaker e profitto delle giocate consigliate."""
import os
from datetime import date, timedelta
import update as U

VARIANTS = {   # prima = modello vecchio, dopo = modello con piu' stagioni e tiri
    "Prima (3 stagioni, solo gol)": {"years": 3, "xi": 0.004, "shots": False},
    "Dopo (5 stagioni, gol + tiri)": {"years": 5, "xi": 0.002, "shots": True},
}
BINS = [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.01)]


def load_all(today):
    U.SEASONS_BACK = 7
    data = {}
    for si, s in enumerate(U.seasons(today)):
        for c in U.LEAGUES:
            try:
                text = U.get(f"{U.BASE}/mmz4281/{s}/{c}.csv")
            except Exception as e:
                print("salto", s, c, e)
                continue
            for r in U.rows(text):
                d = U.pdate(r.get("Date"))
                try:
                    hg, ag = int(r["FTHG"]), int(r["FTAG"])
                except (KeyError, ValueError, TypeError):
                    continue
                if d and r.get("HomeTeam") and r.get("AwayTeam"):
                    data.setdefault(c, []).append({"s": si, "d": d, "h": r["HomeTeam"].strip(),
                                                   "a": r["AwayTeam"].strip(), "hg": hg, "ag": ag, "r": r})
    return data


def probs(pr):
    g = {}
    for lab, mk, p, o in pr["pk"]:
        if mk == "Esito finale":
            g["H" if lab.startswith("1 ") else "A" if lab.startswith("2 ") else "D"] = p
    return [g["H"], g["D"], g["A"]]


def run_league(rows, v):
    rows.sort(key=lambda x: x["d"])
    test = [x for x in rows if x["s"] in (1, 2)]
    out, model, last = [], None, None
    for x in test:
        if last is None or (x["d"] - last).days >= 14:      # il modello si ricalcola ogni 2 settimane
            lo = x["d"] - timedelta(days=365 * v["years"])
            train = [y for y in rows if lo <= y["d"] < x["d"]]
            if len(train) < 100:
                continue
            model, last = U.fit(U.obs(train, v["shots"]), v["xi"]), x["d"]
        if model is None or x["h"] not in model[0] or x["a"] not in model[0]:
            continue
        out.append((x, U.predict(model, x["h"], x["a"], x["r"])))
    return out


def new():
    return {"n": 0, "nb": 0, "brm": 0.0, "brb": 0.0, "am": 0, "ab": 0, "bets": 0, "w": 0, "profit": 0.0,
            "cal": [[0, 0.0, 0] for _ in BINS]}


def stats(res):
    s = new()
    s["n"] = len(res)
    for x, pr in res:
        hg, ag = x["hg"], x["ag"]
        y = [hg > ag, hg == ag, hg < ag]
        pm = probs(pr)
        od = [U.odd(x["r"], k) for k in ("H", "D", "A")]
        if all(od):
            inv = [1 / o for o in od]
            t = sum(inv)
            pb = [v / t for v in inv]
            s["nb"] += 1
            s["brm"] += sum((p - int(v)) ** 2 for p, v in zip(pm, y))
            s["brb"] += sum((p - int(v)) ** 2 for p, v in zip(pb, y))
            s["am"] += y[pm.index(max(pm))]
            s["ab"] += y[pb.index(max(pb))]
        rc = pr["rec"]
        if rc and rc["odd"]:
            w = U.won(rc["key"], hg, ag)
            s["bets"] += 1
            s["w"] += bool(w)
            s["profit"] += (rc["odd"] - 1) if w else -1
        t = pr["top"]
        for b, (lo, hi) in enumerate(BINS):
            if lo <= t["p"] < hi:
                s["cal"][b][0] += 1
                s["cal"][b][1] += t["p"]
                s["cal"][b][2] += bool(U.won(t["key"], hg, ag))
    return s


def merge(a, b):
    for k in ("n", "nb", "brm", "brb", "am", "ab", "bets", "w", "profit"):
        a[k] += b[k]
    for i in range(len(BINS)):
        for j in range(3):
            a["cal"][i][j] += b["cal"][i][j]


def line(name, s):
    nb = s["nb"] or 1
    b = s["bets"]
    return [name, s["n"], f"{s['brm'] / nb:.3f}", f"{s['brb'] / nb:.3f}", f"{100 * s['am'] / nb:.0f}%",
            f"{100 * s['ab'] / nb:.0f}%", b, f"{100 * s['w'] / b:.0f}%" if b else "-",
            f"{100 * s['profit'] / b:+.1f}%" if b else "-"]


def table(head, rows):
    h = "".join(f"<th>{x}</th>" for x in head)
    r = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in row) + "</tr>" for row in rows)
    return f"<div style='overflow-x:auto'><table><tr>{h}</tr>{r}</table></div>"


def main():
    data = load_all(date.today())
    out = {}
    for name, v in VARIANTS.items():
        tot, rows = new(), []
        for c, ms in data.items():
            res = run_league(list(ms), v)
            if len(res) < 50:
                continue
            s = stats(res)
            merge(tot, s)
            co, lg = U.LEAGUES[c]
            rows.append(line(f"{co} - {lg}", s))
        out[name] = (tot, rows)
        print(name, line("TOTALE", tot))
    names = list(VARIANTS)
    (t0, _), (t1, r1) = out[names[0]], out[names[1]]
    f = lambda t: t["brm"] / (t["nb"] or 1)
    roi = lambda t: 100 * t["profit"] / t["bets"] if t["bets"] else 0
    if t1["bets"] < 100:
        verdict = "Poche giocate simulate: il risultato non è affidabile."
    else:
        better = "Il modello nuovo prevede meglio del vecchio" if f(t1) < f(t0) else "Il modello nuovo NON prevede meglio del vecchio"
        beat = "e batte i bookmaker" if f(t1) < t1["brb"] / (t1["nb"] or 1) else "ma non batte i bookmaker"
        verdict = f"{better} {beat}. ROI delle giocate consigliate: {roi(t0):+.1f}% prima, {roi(t1):+.1f}% dopo. Un buon risultato passato non garantisce il futuro."
    cal = [[f"{int(lo * 100)}-{min(int(hi * 100), 100)}%", n, f"{100 * sp / n:.0f}%" if n else "-", f"{100 * w / n:.0f}%" if n else "-"]
           for (lo, hi), (n, sp, w) in zip(BINS, t1["cal"])]
    head = ["Campionato", "Partite", "Brier modello", "Brier bookmaker", "Esito modello", "Esito bookm.", "Giocate", "Vinte", "ROI"]
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Backtest</title><style>body{{font:15px system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;color:#1d1e22}}
table{{border-collapse:collapse;width:100%;font-size:.82rem}}td,th{{padding:5px 7px;border-bottom:1px solid #e8eaee;text-align:right}}td:first-child,th:first-child{{text-align:left}}
.v{{background:#e3f6ec;padding:10px;border-radius:8px}}</style></head><body>
<h1>Backtest (ultime 2 stagioni concluse)</h1><p class="v"><b>{verdict}</b></p>
<p>Brier: più basso = previsioni migliori. Esito: % di 1X2 indovinati. Giocate: quelle che l'app avrebbe consigliato, puntata 1 e quote medie di mercato. ROI: profitto medio per puntata.</p>
<h2>Confronto</h2>{table(head, [line(n, out[n][0]) for n in names])}
<h2>Dettaglio per campionato ({names[1]})</h2>{table(head, r1)}
<h2>Affidabilità delle percentuali ({names[1]})</h2><p>Per la scommessa a probabilità più alta di ogni partita: la % stimata dovrebbe somigliare alla % realmente vinta.</p>
{table(["Fascia", "Partite", "Stimata", "Vinta"], cal)}</body></html>"""
    os.makedirs("docs", exist_ok=True)
    open("docs/backtest.html", "w", encoding="utf-8").write(html)
    print(verdict)


if __name__ == "__main__":
    main()
