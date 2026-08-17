#!/usr/bin/env python3
"""
Fly — stahovač cen.

Projede aktivní kategorie z routes.yaml, stáhne nejlevnější zpáteční nabídky
z Aviasales Data API a přidá nové řádky do data/history.jsonl.

    python3 fetch.py            # ostrý běh, potřebuje TP_TOKEN
    python3 fetch.py --sucho    # jen vypíše, co by stáhl, nic nezapíše
"""
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

API_GROUPED = "https://api.travelpayouts.com/aviasales/v3/grouped_prices"
API_DATES = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

TOKEN = os.environ.get("TP_TOKEN", "").strip()
PAUZA = 1.0          # sekundy mezi dotazy — kvůli rate limitům
HIST = Path("data/history.jsonl")


def hlavicky():
    # token jde v hlavičce, ne v URL — aby se neobjevil v logu při chybě
    return {"Accept-Encoding": "gzip, deflate", "X-Access-Token": TOKEN}


def mesice_dopredu(n):
    """['2026-08', '2026-09', ...] — n měsíců včetně aktuálního."""
    dnes = dt.date.today()
    out = []
    for i in range(n):
        m = dnes.month + i
        y = dnes.year + (m - 1) // 12
        out.append(f"{y}-{(m - 1) % 12 + 1:02d}")
    return out


def noci(odlet, navrat):
    a = dt.date.fromisoformat(odlet)
    b = dt.date.fromisoformat(navrat)
    return (b - a).days


def _zaznam(t):
    """Z odpovědi API udělá jeden řádek historie. None = nepoužitelné."""
    if not t or not t.get("departure_at") or not t.get("return_at"):
        return None
    odlet, navrat = t["departure_at"][:10], t["return_at"][:10]
    if noci(odlet, navrat) <= 0:
        return None
    return {
        "kod": t.get("destination", ""),
        "cena": int(round(float(t["price"]))),
        "odlet": odlet,
        "navrat": navrat,
        "prestupy": int(t.get("transfers", 0) or 0),
        "link": t.get("link", ""),
    }


def stahni_grouped(origin, dest, mena, min_noci, max_noci, horizont, market):
    """Jeden dotaz na destinaci — nejlevnější nabídka za každý měsíc."""
    par = {
        "origin": origin, "destination": dest, "currency": mena,
        "group_by": "month", "direct": "false",
        "min_trip_duration": min_noci, "max_trip_duration": max_noci,
    }
    if market:
        par["market"] = market
    r = requests.get(API_GROUPED, params=par, headers=hlavicky(), timeout=30)
    r.raise_for_status()
    j = r.json()
    if not j.get("success", False):
        raise RuntimeError(j.get("error") or "API vrátilo success=false")

    okno = set(mesice_dopredu(horizont))
    out = []
    for t in (j.get("data") or {}).values():
        z = _zaznam(t)
        if z and z["odlet"][:7] in okno and min_noci <= noci(z["odlet"], z["navrat"]) <= max_noci:
            z["kod"] = dest
            out.append(z)
    return out


def stahni_dates(origin, dest, mena, min_noci, max_noci, horizont, market):
    """Záloha: dotaz na každý měsíc zvlášť. Pomalejší, ale spolehlivější."""
    out = []
    for mesic in mesice_dopredu(horizont):
        par = {
            "origin": origin, "destination": dest, "currency": mena,
            "departure_at": mesic, "one_way": "false", "direct": "false",
            "sorting": "price", "limit": 1000, "page": 1,
        }
        if market:
            par["market"] = market
        r = requests.get(API_DATES, params=par, headers=hlavicky(), timeout=30)
        r.raise_for_status()
        j = r.json()
        if not j.get("success", False):
            raise RuntimeError(j.get("error") or "API vrátilo success=false")

        nej = None
        for t in (j.get("data") or []):
            z = _zaznam(t)
            if not z or not (min_noci <= noci(z["odlet"], z["navrat"]) <= max_noci):
                continue
            if nej is None or z["cena"] < nej["cena"]:
                nej = z
        if nej:
            nej["kod"] = dest
            out.append(nej)
        time.sleep(PAUZA)
    return out


def main():
    sucho = "--sucho" in sys.argv
    metoda = "dates" if "--dates" in sys.argv else "grouped"
    if not TOKEN and not sucho:
        sys.exit("CHYBA: chybí proměnná prostředí TP_TOKEN.")

    cfg = yaml.safe_load(Path("routes.yaml").read_text(encoding="utf-8"))
    nast = cfg["nastaveni"]
    origin = nast["origin"]
    mena = nast["mena"].lower()
    market = nast.get("market")

    beh = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    radky, chyby = [], 0

    for kat_id, kat in cfg["kategorie"].items():
        if not kat.get("aktivni", True):
            continue
        min_noci, max_noci = kat["delka_pobytu"]
        horizont = kat["horizont_mesicu"]

        for dest in kat["destinace"]:
            try:
                fce = stahni_dates if metoda == "dates" else stahni_grouped
                nalezy = fce(origin, dest, mena, min_noci, max_noci, horizont, market)
            except Exception as e:
                print(f"  ! {kat_id}/{dest}: {e}", file=sys.stderr)
                chyby += 1
                time.sleep(PAUZA)
                continue

            for z in nalezy:
                radky.append({"beh": beh, "kategorie": kat_id, **z})
            print(f"  {kat_id}/{dest}: {len(nalezy)} nabídek")
            if metoda == "grouped":
                time.sleep(PAUZA)

    print(f"Celkem {len(radky)} záznamů, {chyby} chyb.")
    if sucho:
        print("--sucho: nic se nezapisuje.")
        return
    if not radky:
        sys.exit("CHYBA: nestáhlo se nic — historie se nemění.")

    HIST.parent.mkdir(parents=True, exist_ok=True)
    with HIST.open("a", encoding="utf-8") as f:
        for r in radky:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Zapsáno do {HIST}")


if __name__ == "__main__":
    main()
