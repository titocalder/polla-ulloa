#!/usr/bin/env python3
"""
Scraper FIFA -> genera index.html para La Polla de Ulloa.
Usa Playwright para renderizar la página de FIFA (JS-heavy).
"""
import asyncio, json, re, sys
from datetime import datetime
from playwright.async_api import async_playwright

FIFA_URL = "https://www.fifa.com/es/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures?country=CL&wtw-filter=ALL"

# Apuestas de cada jugador por partido (orden fijo)
PLAYERS = ["I.Bastías","N.Zarges","K.Sepúlveda","I.Ulloa","D.Mediano","H.Calderon","🌸 A.Fernandez","R.Lamas"]
YOU = "H.Calderon"

BETS = {
    "México vs Sudáfrica":            ["2-0","2-0","2-0","2-1","2-0","2-1","2-0","1-0"],
    "República de Corea vs Chequia":  ["2-1","1-1","1-1","0-2","1-1","1-0","1-1","1-1"],
    "Canadá vs Bosnia y Herzegovina": ["2-1","1-1","2-1","2-1","2-1","2-1","1-0","1-0"],
    "EE. UU. vs Paraguay":            ["2-1","0-1","1-0","0-1","2-0","1-2","1-1","2-1"],
    "Catar vs Suiza":                 ["0-3","0-2","0-2","0-3","0-2","—","0-2","0-2"],
    "Brasil vs Marruecos":            ["2-1","2-1","2-1","1-1","2-0","3-1","1-0","2-1"],
    "Haití vs Escocia":               ["0-3","0-2","0-1","0-2","0-2","0-1","0-2","0-2"],
    "Australia vs Turquía":           ["1-2","1-2","1-2","0-3","1-1","1-2","1-2","0-1"],
    "Alemania vs Curazao":            ["5-0","3-0","3-0","5-0","4-0","4-0","2-0","4-0"],
}

DATE_MAP = {
    "jueves":"Jue","viernes":"Vie","sábado":"Sáb","domingo":"Dom",
    "lunes":"Lun","martes":"Mar","miércoles":"Mié",
    "enero":"Ene","febrero":"Feb","marzo":"Mar","abril":"Abr","mayo":"May",
    "junio":"Jun","julio":"Jul","agosto":"Ago","septiembre":"Sep",
    "octubre":"Oct","noviembre":"Nov","diciembre":"Dic",
}

def short_date(s):
    s = s.lower()
    for k,v in DATE_MAP.items():
        s = s.replace(k, v)
    m = re.search(r'(\d{1,2})\s+(\w+)', s)
    return f"{m.group(1)} {m.group(2)[:3].capitalize()}" if m else s

def calc_pts(result, bet):
    if not result or not bet or bet == "—":
        return None  # pendiente
    try:
        rh, ra = map(int, result.split("-"))
        bh, ba = map(int, bet.split("-"))
    except:
        return None
    if rh == bh and ra == ba:
        return 3
    if (rh > ra and bh > ba) or (rh < ra and bh < ba) or (rh == ra and bh == ba):
        return 1
    return 0

def find_bets(home, away):
    key = f"{home} vs {away}"
    if key in BETS:
        return BETS[key]
    # Buscar parcial
    for k, v in BETS.items():
        kh, ka = k.split(" vs ")
        if kh[:4].lower() in home.lower() or home.lower()[:4] in kh.lower():
            if ka[:4].lower() in away.lower() or away.lower()[:4] in ka.lower():
                return v
    return ["—"] * len(PLAYERS)

async def scrape_fifa():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(locale="es-ES")
        print(f"Cargando FIFA...", flush=True)
        await page.goto(FIFA_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(4000)
        # Refrescar para obtener datos actualizados
        await page.reload(wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        full = await page.evaluate("document.body.innerText")
        await browser.close()

    lines = [l.strip() for l in full.split('\n') if l.strip()]
    matches = []
    for i in range(len(lines) - 5):
        is_result = bool(re.search(r'FINAL|SUSP|EN CURSO|\d+\'', lines[i+2]))
        is_future = bool(re.match(r'^\d{2}:\d{2}$', lines[i+2]))
        if (is_result or is_future) and re.match(r'^\d+$', lines[i+1]) and re.match(r'^\d+$', lines[i+3]):
            date = ""
            for j in range(i, -1, -1):
                if re.search(r'\d{4}', lines[j]) and len(lines[j]) > 8:
                    date = lines[j]; break
            group = ""
            for k in range(i+5, min(i+10, len(lines))):
                if "Grupo" in lines[k]:
                    group = lines[k]; break
            home, away = lines[i], lines[i+4]
            hs, as_ = lines[i+1], lines[i+3]
            status = lines[i+2]
            result = f"{hs}-{as_}" if is_result else ""
            bets = find_bets(home, away)
            pts = [calc_pts(result, b) for b in bets]
            matches.append({
                "date": short_date(date),
                "home": home, "away": away,
                "result": result, "status": status,
                "group": group, "bets": bets, "pts": pts
            })

    print(f"  → {len(matches)} partidos", flush=True)
    return matches

def ranking(matches):
    totals = {p: 0 for p in PLAYERS}
    for m in matches:
        for i, p in enumerate(PLAYERS):
            v = m["pts"][i]
            if v is not None:
                totals[p] += v
    sorted_players = sorted(totals.items(), key=lambda x: -x[1])
    result = []
    pos, prev = 0, None
    for i, (name, pts) in enumerate(sorted_players):
        if pts != prev:
            pos = i + 1
            prev = pts
        result.append({"name": name, "pts": pts, "pos": pos})
    return result

def pts_label(p):
    if p is None: return ("pp", "?")
    if p == 3: return ("pe", "+3 pts")
    if p == 1: return ("po", "+1 pt")
    return ("pz", "0 pts")

def generate_html(matches):
    now = datetime.now().strftime("%-d %b %H:%M")
    rank = ranking(matches)
    max_pts = rank[0]["pts"] if rank else 1

    # ── Ranking HTML ──
    rank_html = ""
    for r in rank:
        pct = round(r["pts"] / max_pts * 100) if max_pts else 0
        is_you = YOU in r["name"]
        row_cls = "rrow you-row" if is_you else "rrow"
        num_color = "#B8860B" if r["pos"]==1 else "#888"
        badge_cls = "bg" if r["pos"]==1 else "bs" if r["pos"]==2 else "bx"
        bar_color = "#85B7EB" if is_you else "#9FE1CB" if r["pos"]==1 else "#C0DD97" if r["pos"]==2 else "#D3D1C7"
        you_tag = ' <span style="font-size:10px;background:#B5D4F4;color:#0C447C;padding:1px 6px;border-radius:4px;margin-left:4px">tú</span>' if is_you else ""
        name_style = "color:#185FA5;" if is_you else ""
        rank_html += f"""
    <div class="{row_cls}">
      <span class="rnum" style="color:{num_color}">{r["pos"]}</span>
      <span style="flex:1;font-weight:500;{name_style}">{r["name"]}{you_tag}</span>
      <span style="font-size:13px;color:#888780;margin-right:8px">{r["pts"]} pts</span>
      <div class="bar-w"><div class="bar" style="width:{pct}%;background:{bar_color}"></div></div>
      <span class="badge {badge_cls}">{r["pos"]}°</span>
    </div>"""

    # ── Último partido HTML ──
    last = next((m for m in reversed(matches) if m["result"]), None) or (matches[-1] if matches else None)
    hero_html = ""
    if last:
        score_disp = last["result"].replace("-"," – ") if last["result"] else "? – ?"
        chips = ""
        for j, pl in enumerate(PLAYERS):
            bet = last["bets"][j]
            p = last["pts"][j]
            cls, lbl = pts_label(p)
            is_you = YOU in pl
            chip_cls = "chip you" if is_you else "chip"
            chips += f"""
      <div class="{chip_cls}"><span class="cn">{pl}</span><span class="ca">{bet}</span><span class="cp {cls}">{lbl}</span></div>"""
        hero_html = f"""
  <div class="hero">
    <div class="hero-tag"><span class="dot"></span>Último partido</div>
    <div class="hero-title">{last["home"]} vs {last["away"]}</div>
    <div class="hero-meta">{last["date"]} · {last["group"]}</div>
    <div class="score">{score_disp}</div>
    <div class="score-lbl">Resultado final</div>
    <div class="chips">{chips}
    </div>
  </div>"""

    # ── Table headers ──
    headers = "".join(f"<th>{'★ ' if YOU in p else ''}{p}</th>" for p in PLAYERS)

    # ── Matches JS ──
    matches_js = json.dumps(matches, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>La Polla de Ulloa — Mundial 2026</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f2;color:#1a1a18;padding:1.5rem 1rem;max-width:900px;margin:0 auto}}
h1{{font-size:20px;font-weight:600;margin-bottom:.15rem}}
.sub{{font-size:13px;color:#888780;margin-bottom:1.25rem}}
.tabs{{display:flex;gap:8px;margin-bottom:1.25rem;flex-wrap:wrap}}
.tab{{padding:7px 16px;border:.5px solid #b4b2a9;border-radius:8px;font-size:13px;cursor:pointer;background:transparent;color:#5f5e5a;font-family:inherit}}
.tab.active{{background:#1a1a18;color:#fff;font-weight:500;border-color:#1a1a18}}
.section{{display:none}}.section.active{{display:block}}
.hero{{background:#fff;border:2px solid #85B7EB;border-radius:16px;padding:1.25rem 1.5rem;margin-bottom:1rem}}
.hero-tag{{font-size:11px;font-weight:600;color:#185FA5;text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:center;gap:6px;margin-bottom:.6rem}}
.dot{{width:7px;height:7px;border-radius:50%;background:#27B07C}}
.hero-title{{font-size:18px;font-weight:700;margin-bottom:.2rem}}
.hero-meta{{font-size:12px;color:#888780;margin-bottom:.9rem}}
.score{{font-size:34px;font-weight:700;color:#185FA5;margin-bottom:.15rem}}
.score-lbl{{font-size:11px;color:#888780;margin-bottom:1.1rem}}
.chips{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{display:flex;flex-direction:column;align-items:center;background:#f1efe8;border-radius:10px;padding:8px 12px;min-width:78px;flex:1}}
.chip.you{{background:#EBF4FD;border:1.5px solid #85B7EB}}
.chip .cn{{font-size:10px;color:#888780;margin-bottom:3px;white-space:nowrap}}
.chip.you .cn{{color:#185FA5}}
.chip .ca{{font-size:15px;font-weight:700}}
.chip.you .ca{{color:#185FA5}}
.chip .cp{{margin-top:4px;font-size:10px;font-weight:600;padding:1px 7px;border-radius:999px}}
.pe{{background:#9FE1CB;color:#085041}}.po{{background:#C0DD97;color:#27500A}}
.pz{{background:#F1EFE8;color:#5F5E5A}}.pp{{background:#B5D4F4;color:#0C447C}}
.rrows{{display:flex;flex-direction:column;gap:8px}}
.rrow{{display:flex;align-items:center;gap:12px;padding:10px 14px;background:#fff;border:.5px solid #d3d1c7;border-radius:12px}}
.rnum{{font-size:18px;font-weight:600;width:28px;text-align:center}}
.bar-w{{flex:1;background:#f1efe8;border-radius:4px;height:9px;overflow:hidden;min-width:50px}}
.bar{{height:100%;border-radius:4px}}
.you-row{{background:#EBF4FD!important;border:1.5px solid #85B7EB!important}}
.badge{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}}
.bg{{background:#FAC775;color:#633806}}.bs{{background:#D3D1C7;color:#2C2C2A}}
.bx{{background:#F1EFE8;color:#5F5E5A}}.be{{background:#9FE1CB;color:#085041}}
.bo{{background:#C0DD97;color:#27500A}}.bz{{background:#F1EFE8;color:#5F5E5A}}
.by{{background:#B5D4F4;color:#0C447C}}
.ov{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{font-weight:500;font-size:11px;color:#888780;padding:8px;text-align:center;border-bottom:.5px solid #e8e7e3;white-space:nowrap}}
th:first-child{{text-align:left}}
td{{padding:7px 8px;border-bottom:.5px solid #e8e7e3;color:#1a1a18;vertical-align:middle;text-align:center}}
td:first-child{{text-align:left}}
tr:last-child td{{border-bottom:none}}
.res{{display:inline-block;background:#f1efe8;border:.5px solid #b4b2a9;border-radius:4px;padding:1px 6px;font-size:12px;font-weight:500}}
.note{{font-size:12px;color:#b4b2a9;margin-top:1rem}}
.leg{{display:flex;gap:12px;flex-wrap:wrap;margin-top:1rem;font-size:12px;color:#888780;align-items:center}}
</style>
</head>
<body>
<h1>⚽ La Polla de Ulloa</h1>
<p class="sub">Copa Mundial 2026 · actualizado {now}</p>
<div class="tabs">
  <button class="tab active" onclick="show('actual',this)">🔥 Último partido</button>
  <button class="tab" onclick="show('ranking',this)">🏆 Ranking</button>
  <button class="tab" onclick="show('partidos',this)">📋 Historial</button>
</div>
<div id="actual" class="section active">{hero_html}</div>
<div id="ranking" class="section">
  <div class="rrows">{rank_html}
  </div>
  <p class="note">Exacto = 3 pts · ganador correcto = 1 pt</p>
</div>
<div id="partidos" class="section">
  <div class="ov"><table>
    <thead><tr><th>Partido</th><th>Res.</th>{headers}</tr></thead>
    <tbody id="tb"></tbody>
  </table></div>
  <div class="leg">
    <span><span class="badge be">3</span> exacto</span>
    <span><span class="badge bo">1</span> ganador ok</span>
    <span><span class="badge bz">0</span> fallo</span>
    <span style="color:#b4b2a9">★ = tú</span>
  </div>
</div>
<script>
const M={matches_js};
function cell(p,b){{
  if(p===null||!b||b==='—') return '<td style="color:#b4b2a9">—</td>';
  const c=p===3?'be':p===1?'bo':'bz';
  return `<td><span class="badge ${{c}}">${{p}}</span><div style="font-size:10px;color:#888780;margin-top:1px">${{b}}</div></td>`;
}}
const tb=document.getElementById('tb');
M.forEach(m=>{{
  if(!m.result) return;
  const tr=document.createElement('tr');
  tr.innerHTML=`<td><span style="font-size:10px;color:#888780">${{m.date}}</span><br><strong>${{m.home}}</strong> vs ${{m.away}}</td><td><span class="res">${{m.result}}</span></td>${{m.bets.map((b,i)=>cell(m.pts[i],b)).join('')}}`;
  tb.appendChild(tr);
}});
function show(id,el){{
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
}}
</script>
</body>
</html>""".replace("{matches_js}", matches_js)

async def main():
    matches = await scrape_fifa()
    if not matches:
        print("ERROR: no se encontraron partidos", file=sys.stderr)
        sys.exit(1)
    with open("scraped_data.json","w",encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)
    html = generate_html(matches)
    with open("index.html","w",encoding="utf-8") as f:
        f.write(html)
    print("✓ index.html generado", flush=True)

    # Notificación de escritorio si hay partido próximo (≤15 min)
    now = datetime.now()
    # (se puede ampliar con hora real del partido cuando FIFA la exponga)

if __name__ == "__main__":
    asyncio.run(main())
