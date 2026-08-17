#!/usr/bin/env python3
"""
Fly — přepočet baseline.

Z data/history.jsonl a routes.yaml spočítá baseline.json, který čte
generate_dashboard.py. Baseline = nejnižší cena viděná na trase za 90 dní.

    python3 build_baseline.py
"""
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import yaml

HIST = Path("data/history.jsonl")
VYSTUP = Path("baseline.json")
OKNO_DNI = 90
MAX_NA_KATEGORII = 8      # kolik nejlevnějších destinací ukázat v dashboardu

MESTA = {
    "BKK": "Bangkok", "HKT": "Phuket", "NRT": "Tokio", "HND": "Tokio",
    "DPS": "Bali", "SGN": "Ho Či Min", "HAN": "Hanoj", "SIN": "Singapur",
    "KUL": "Kuala Lumpur", "ICN": "Soul", "DEL": "Dillí", "CMB": "Kolombo",
    "KTM": "Káthmándú",
    "GIG": "Rio de Janeiro", "GRU": "São Paulo", "BOG": "Bogotá",
    "LIM": "Lima", "EZE": "Buenos Aires", "SCL": "Santiago de Chile",
    "MVD": "Montevideo", "UIO": "Quito", "CUZ": "Cusco",
    "JFK": "New York", "EWR": "Newark", "BOS": "Boston", "ORD": "Chicago",
    "YYZ": "Toronto", "MIA": "Miami", "LAX": "Los Angeles",
    "SFO": "San Francisco", "SEA": "Seattle", "YVR": "Vancouver",
    "MLE": "Maledivy", "MRU": "Mauricius", "CPT": "Kapské Město",
    "JNB": "Johannesburg", "PUJ": "Punta Cana", "CUN": "Cancún",
    "HAV": "Havana", "SEZ": "Seychely", "ZNZ": "Zanzibar",
    "SYD": "Sydney", "AKL": "Auckland",
    "DXB": "Dubaj", "RAK": "Marrákeš", "CAI": "Káhira", "AMM": "Ammán",
    "TLV": "Tel Aviv", "AGA": "Agadir", "TUN": "Tunis", "MCT": "Maskat",
    "LIS": "Lisabon", "OPO": "Porto", "FCO": "Řím", "CPH": "Kodaň",
    "DUB": "Dublin", "ATH": "Athény", "BCN": "Barcelona", "MAD": "Madrid",
    "EDI": "Edinburgh",
    "KEF": "Reykjavík", "TRF": "Oslo", "GVA": "Ženeva", "INN": "Innsbruck",
    "TRD": "Trondheim", "SZG": "Salcburk",
}


def nacti_historii():
    if not HIST.exists():
        raise SystemExit(f"CHYBA: {HIST} neexistuje — nejdřív spusť fetch.py.")
    radky = []
    for radek in HIST.read_text(encoding="utf-8").splitlines():
        radek = radek.strip()
        if radek:
            radky.append(json.loads(radek))
    if not radky:
        raise SystemExit(f"CHYBA: {HIST} je prázdný.")
    return radky


def main():
    cfg = yaml.safe_load(Path("routes.yaml").read_text(encoding="utf-8"))
    nast = cfg["nastaveni"]
    hist = nacti_historii()

    behy = sorted({r["beh"] for r in hist})
    posledni_beh = behy[-1]
    hranice = dt.datetime.fromisoformat(posledni_beh) - dt.timedelta(days=OKNO_DNI)

    # nejnižší cena za posledních 90 dní na trase — POUZE z minulých běhů.
    # Kdyby se do minima počítal i aktuální běh, byla by reference vždycky
    # rovná dnešní ceně nebo nižší a pravidlo "12 % pod referencí" by nikdy
    # nemohlo nastat.
    minima = defaultdict(lambda: None)
    for r in hist:
        if r["beh"] == posledni_beh:
            continue
        if dt.datetime.fromisoformat(r["beh"]) < hranice:
            continue
        k = (r["kategorie"], r["kod"])
        if minima[k] is None or r["cena"] < minima[k]:
            minima[k] = r["cena"]

    # nejlevnější aktuální nabídka na trase z posledního běhu
    aktualni = {}
    for r in hist:
        if r["beh"] != posledni_beh:
            continue
        k = (r["kategorie"], r["kod"])
        if k not in aktualni or r["cena"] < aktualni[k]["cena"]:
            aktualni[k] = r

    kategorie = []
    for kat_id, kat in cfg["kategorie"].items():
        if not kat.get("aktivni", True):
            continue
        dest = []
        for kod in kat["destinace"]:
            r = aktualni.get((kat_id, kod))
            if not r:
                continue
            dest.append({
                "kod": kod,
                "mesto": MESTA.get(kod, kod),
                "cena": r["cena"],
                "odlet": r["odlet"],
                "navrat": r["navrat"],
                "prestupy": r["prestupy"],
                # při prvním běhu ještě žádná minulost není → reference = dnešní nález
                "baseline": minima[(kat_id, kod)] or r["cena"],
                "link": r.get("link", ""),
            })
        if not dest:
            continue
        dest.sort(key=lambda x: x["cena"])
        kategorie.append({
            "id": kat_id,
            "nazev": kat["nazev"],
            "tvrdy_prah": kat["prah_kc"],
            "destinace": dest[:MAX_NA_KATEGORII],
        })

    out = {
        "meta": {
            "origin": nast["origin"],
            "mena": nast["mena"],
            "typ": nast["typ"],
            "zalozeno": behy[0][:10],
            "posledni_beh": posledni_beh,
            "pravidlo_alertu": "cena <= baseline * 0.88  NEBO  cena <= tvrdy_prah",
            "poznamka": f"baseline = nejnizsi cena videna za poslednich {OKNO_DNI} dni",
        },
        "kategorie": kategorie,
    }
    VYSTUP.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hotovo: {VYSTUP} — {sum(len(k['destinace']) for k in kategorie)} destinací, "
          f"{len(behy)} běhů v historii")


if __name__ == "__main__":
    main()
