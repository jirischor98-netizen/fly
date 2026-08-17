#!/usr/bin/env python3
"""
Fly — generátor dashboardu.

Přečte baseline.json a vygeneruje dashboard.html.
Spouští se na konci každého běhu hlídače.

    python3 generate_dashboard.py baseline.json dashboard.html
"""
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

MESICE = ["", "led", "úno", "bře", "dub", "kvě", "čvn",
          "čvc", "srp", "zář", "říj", "lis", "pro"]

ALERT_POMER = 0.88   # cena musí být aspoň o 12 % pod baseline


def datum(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.day}. {MESICE[d.month]} {d.year}"


def rozsah(od, do):
    a, b = datetime.strptime(od, "%Y-%m-%d"), datetime.strptime(do, "%Y-%m-%d")
    noci = (b - a).days
    if a.year == b.year:
        return f"{a.day}. {MESICE[a.month]} – {b.day}. {MESICE[b.month]} {b.year}", noci
    return f"{a.day}. {MESICE[a.month]} {a.year} – {b.day}. {MESICE[b.month]} {b.year}", noci


def kc(n):
    return f"{n:,}".replace(",", " ") + " Kč"


def noci_txt(n):
    if n == 1:
        return "1 noc"
    if 2 <= n <= 4:
        return f"{n} noci"
    return f"{n} nocí"


def stav(d, tvrdy_prah):
    """Vrátí (trida, popis, je_nalez)."""
    base = d.get("baseline", d["cena"])
    if d["cena"] <= tvrdy_prah:
        return "hit", "pod tvrdým prahem", True
    if base and d["cena"] <= base * ALERT_POMER:
        pokles = round((1 - d["cena"] / base) * 100)
        return "hit", f"o {pokles} % pod referencí", True
    if base and d["cena"] < base:
        pokles = round((1 - d["cena"] / base) * 100)
        return "down", f"−{pokles} % od minula", False
    if base and d["cena"] > base * 1.05:
        return "up", "dráž než reference", False
    return "flat", "beze změny", False


def render(data):
    meta = data["meta"]
    nalezy = []
    sekce = []

    for kat in data["kategorie"]:
        radky = []
        dest = sorted(kat["destinace"], key=lambda x: x["cena"])
        for d in dest:
            trida, popis, je_nalez = stav(d, kat["tvrdy_prah"])
            if je_nalez:
                nalezy.append((kat["nazev"], d, popis))
            obdobi, noci = rozsah(d["odlet"], d["navrat"])
            prestupy = "přímý" if d["prestupy"] == 0 else (
                f"{d['prestupy']} přestup" if d["prestupy"] == 1
                else f"{d['prestupy']} přestupy" if d["prestupy"] < 5
                else f"{d['prestupy']} přestupů")
            radky.append(f"""      <tr class="{trida}">
        <td class="mesto"><b>{d['mesto']}</b> <span class="kod">{d['kod']}</span></td>
        <td class="cena">{kc(d['cena'])}</td>
        <td class="termin">{obdobi}<span class="noci">{noci_txt(noci)}</span></td>
        <td class="prestupy">{prestupy}</td>
        <td class="stav"><span class="badge {trida}">{popis}</span></td>
      </tr>""")

        nejlevnejsi = kc(dest[0]["cena"]) if dest else "—"
        sekce.append(f"""  <section class="kat">
    <div class="kat-hlava">
      <h2>{kat['nazev']}</h2>
      <div class="kat-meta">nejlevněji <b>{nejlevnejsi}</b> · práh {kc(kat['tvrdy_prah'])}</div>
    </div>
    <table>
      <thead><tr><th>Destinace</th><th>Cena</th><th>Termín</th><th>Spojení</th><th>Stav</th></tr></thead>
      <tbody>
{chr(10).join(radky)}
      </tbody>
    </table>
  </section>""")

    if nalezy:
        polozky = "".join(
            f'<li><b>{d["mesto"]}</b> za {kc(d["cena"])} — {popis} <span class="kde">{kat}</span></li>'
            for kat, d, popis in sorted(nalezy, key=lambda x: x[1]["cena"]))
        banner = f"""  <div class="banner hit">
    <h3>{len(nalezy)}× stojí za pozornost</h3>
    <ul>{polozky}</ul>
  </div>"""
    else:
        banner = """  <div class="banner klid">
    <h3>Dnes nic mimořádného</h3>
    <p>Žádná cena nespadla dost hluboko pod svoji referenční hladinu. Přehled níž ukazuje aktuální stav.</p>
  </div>"""

    # běhy se zapisují v UTC (GitHub Actions), zobrazujeme je v našem čase
    beh = datetime.fromisoformat(meta["posledni_beh"]).astimezone(ZoneInfo("Europe/Prague"))
    return ŠABLONA.format(
        banner=banner,
        sekce="\n".join(sekce),
        cas=f"{beh.day}. {MESICE[beh.month]} {beh.year}, {beh.hour}:{beh.minute:02d}",
        pocet=sum(len(k["destinace"]) for k in data["kategorie"]),
        zalozeno=datum(meta["zalozeno"]),
    )


ŠABLONA = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fly — hlídač cen letenek z Prahy</title>
<style>
  :root{{
    --ink:#16150f;--soft:#4d4a42;--mute:#83807a;--line:#e5e2db;--line2:#f1efea;
    --bg:#faf9f6;--card:#fff;--acc:#1f6f5c;--acc-bg:#e9f3f0;
    --hit:#146c43;--hit-bg:#e6f4ec;--down:#1f6f5c;--up:#9a5b22;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);font-size:16px;line-height:1.6;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased}}
  .wrap{{max-width:900px;margin:0 auto;padding:48px 24px 90px}}
  header{{border-bottom:2px solid var(--ink);padding-bottom:20px;margin-bottom:28px}}
  .eyebrow{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);
    font-weight:600;margin:0 0 8px}}
  h1{{font-size:31px;letter-spacing:-.02em;margin:0 0 10px;font-weight:700}}
  .hmeta{{font-size:13.5px;color:var(--mute);display:flex;gap:18px;flex-wrap:wrap}}
  .hmeta b{{color:var(--soft);font-weight:600}}

  .banner{{border-radius:12px;padding:20px 24px;margin-bottom:34px}}
  .banner h3{{margin:0 0 8px;font-size:17px;font-weight:650}}
  .banner p{{margin:0;font-size:15px;color:var(--soft)}}
  .banner ul{{margin:0;padding-left:20px}}
  .banner li{{margin-bottom:5px;font-size:15px}}
  .banner .kde{{color:var(--mute);font-size:13px}}
  .banner.hit{{background:var(--hit-bg);border:1px solid #c3e2d1}}
  .banner.hit h3{{color:var(--hit)}}
  .banner.klid{{background:var(--card);border:1px solid var(--line)}}

  .kat{{margin-bottom:34px}}
  .kat-hlava{{display:flex;justify-content:space-between;align-items:baseline;
    gap:14px;flex-wrap:wrap;margin-bottom:9px}}
  h2{{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--acc);
    font-weight:700;margin:0}}
  .kat-meta{{font-size:13px;color:var(--mute)}}
  .kat-meta b{{color:var(--soft)}}

  table{{width:100%;border-collapse:collapse;background:var(--card);
    border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:14.5px}}
  th{{text-align:left;font-size:11px;letter-spacing:.09em;text-transform:uppercase;
    color:var(--mute);font-weight:650;padding:10px 14px;background:#fcfbf9;
    border-bottom:1px solid var(--line)}}
  td{{padding:12px 14px;border-bottom:1px solid var(--line2);vertical-align:middle}}
  tr:last-child td{{border-bottom:none}}
  tr.hit td{{background:var(--hit-bg)}}
  .kod{{color:var(--mute);font-size:12px;font-weight:600;letter-spacing:.04em}}
  .cena{{font-variant-numeric:tabular-nums;font-weight:650;white-space:nowrap}}
  .termin{{color:var(--soft);white-space:nowrap}}
  .noci{{display:block;font-size:12px;color:var(--mute)}}
  .prestupy{{color:var(--soft);white-space:nowrap}}
  .stav{{text-align:right}}
  .badge{{display:inline-block;font-size:11.5px;font-weight:600;padding:3px 9px;
    border-radius:20px;white-space:nowrap;background:var(--line2);color:var(--mute)}}
  .badge.hit{{background:#cfe9db;color:var(--hit)}}
  .badge.down{{background:var(--acc-bg);color:var(--down)}}
  .badge.up{{background:#fbf0e4;color:var(--up)}}

  footer{{margin-top:52px;padding-top:20px;border-top:1px solid var(--line);
    font-size:13.5px;color:var(--mute)}}
  footer p{{margin:0 0 8px;max-width:72ch}}

  @media(max-width:640px){{
    .wrap{{padding:32px 16px 60px}} h1{{font-size:25px}}
    table{{font-size:13px}} th,td{{padding:9px 9px}}
    .termin,.prestupy{{white-space:normal}}
  }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">Automatický přehled · odlet z Prahy · zpáteční</p>
  <h1>Hlídač cen letenek</h1>
  <div class="hmeta">
    <span><b>Poslední běh</b> {cas}</span>
    <span><b>Sledováno</b> {pocet} destinací</span>
    <span><b>Sbírá se od</b> {zalozeno}</span>
  </div>
</header>

{banner}

{sekce}

<footer>
  <p>Ceny pocházejí z databáze reálných vyhledávání Aviasales a mohou být několik dní staré — ber je jako signál, kde se dívat, ne jako závaznou nabídku. Před rezervací je potřeba cenu ověřit u prodejce.</p>
  <p>Přehled se přepisuje automaticky dvakrát denně. „Reference“ je nejnižší cena, kterou hlídač na dané trase viděl za posledních 90 dní; upozornění chodí, když cena spadne aspoň o 12 % pod ni nebo pod tvrdý práh kategorie.</p>
</footer>

</div>
</body>
</html>
"""


if __name__ == "__main__":
    vstup = sys.argv[1] if len(sys.argv) > 1 else "baseline.json"
    vystup = sys.argv[2] if len(sys.argv) > 2 else "dashboard.html"
    with open(vstup, encoding="utf-8") as f:
        data = json.load(f)
    with open(vystup, "w", encoding="utf-8") as f:
        f.write(render(data))
    print(f"Hotovo: {vystup}")
