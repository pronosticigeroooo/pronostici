"""Aggiorna docs/live.json con le partite in corso e quelle finite da poco (da BSD). Si lancia ogni 5 minuti."""
import json, os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import bsd

NO_LIVE = ("", "notstarted", "scheduled", "postponed", "canceled", "cancelled", "abandoned")


def main():
    key = os.environ.get("BSD_KEY", "").strip()
    if not key:
        print("live: chiave mancante")
        return
    today = date.today()
    ev = bsd.pages("events/", key, 4, date_from=(today - timedelta(days=1)).isoformat(),
                   date_to=(today + timedelta(days=1)).isoformat())
    out = {}
    for e in ev:
        st = str(e.get("status") or "").lower()
        if st in NO_LIVE:
            continue
        d = bsd.when(e["event_date"])
        k = f"b{e['league_id']}|{d.date().isoformat()}|{e['home_team']}|{e['away_team']}"
        s = "finished" if st == "finished" else ("ht" if st in ("ht", "halftime", "half_time") or "half" in st else "live")
        out[k] = {"st": s, "m": e.get("current_minute"), "hs": e.get("home_score"), "as": e.get("away_score")}
    path = "docs/live.json"
    try:
        old = json.load(open(path, encoding="utf-8")).get("events")
    except Exception:
        old = None
    n_live = sum(1 for v in out.values() if v["st"] != "finished")
    if old == out:
        print(f"live: nessun cambiamento ({n_live} in corso, {len(out) - n_live} finite)")
        return
    os.makedirs("docs", exist_ok=True)
    json.dump({"updated": datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="seconds"), "events": out},
              open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"live: aggiornato ({n_live} in corso, {len(out) - n_live} finite)")


if __name__ == "__main__":
    main()
