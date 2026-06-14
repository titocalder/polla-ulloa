#!/usr/bin/env python3
"""
Scraper para pollamundialera.com/ranking/5129
Genera index.html con ranking + partidos + apuestas.
"""
import asyncio
import json
import re
import sys
from datetime import datetime
from playwright.async_api import async_playwright

POLLA_ID = "5129"
BASE_URL = "https://www.pollamundialera.com"
RANKING_URL = f"{BASE_URL}/ranking/{POLLA_ID}"
PRONOSTICOS_URL = f"{BASE_URL}/pronosticos/{POLLA_ID}"

# Jugadores en orden (como aparece en la tabla de pronósticos)
# Si el orden cambia en el sitio, se actualiza aquí.
YOU = "Héctor Calderon"

MONTHS_ES = {
    "Jan":"Ene","Feb":"Feb","Mar":"Mar","Apr":"Abr","May":"May","Jun":"Jun",
    "Jul":"Jul","Aug":"Ago","Sep":"Sep","Oct":"Oct","Nov":"Nov","Dec":"Dic",
    "enero":"Ene","febrero":"Feb","marzo":"Mar","abril":"Abr","mayo":"May",
    "junio":"Jun","julio":"Jul","agosto":"Ago","septiembre":"Sep",
    "octubre":"Oct","noviembre":"Nov","diciembre":"Dic",
}

def fmt_date(s):
    """Intenta formatear una fecha corta."""
    s = s.strip()
    for en, es in MONTHS_ES.items():
        s = s.replace(en, es)
    # Deja solo día y mes
    m = re.search(r'(\d{1,2})\s+(\w+)', s)
    if m:
        return f"{m.group(1)} {m.group(2)[:3]}"
    return s


async def scrape():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        ctx = await browser.new_context(
            locale="es-CL",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
        page = await ctx.new_page()

        # ── RANKING ────────────────────────────────────────────────────────
        print(f"Cargando {RANKING_URL}", flush=True)
        await page.goto(RANKING_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(4000)

        ranking = []
        # Intentamos distintos selectores comunes
        rows = await page.query_selector_all("table tr")
        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) >= 2:
                texts = [await c.inner_text() for c in cells]
                # Busca filas con nombre + puntos
                pts_match = None
                name = None
                for t in texts:
                    t = t.strip()
                    pm = re.search(r'\b(\d+)\s*(pts?|puntos?|p\.?)\b', t, re.IGNORECASE)
                    if pm:
                        pts_match = int(pm.group(1))
                    elif t and not re.match(r'^\d+$', t) and len(t) > 2:
                        name = t
                if name and pts_match is not None:
                    ranking.append({"name": name, "pts": pts_match})

        # Fallback: buscar divs/li con puntos
        if not ranking:
            items = await page.query_selector_all("[class*='rank'], [class*='posicion'], [class*='jugador'], li")
            for el in items:
                text = (await el.inner_text()).strip()
                pm = re.search(r'(.+?)\s+(\d+)\s*(pts?|puntos?|p\.?)', text, re.IGNORECASE)
                if pm:
                    ranking.append({"name": pm.group(1).strip(), "pts": int(pm.group(2))})

        print(f"  → {len(ranking)} jugadores en ranking", flush=True)

        # ── PRONÓSTICOS ───────────────────────────────────────────────────
        print(f"Cargando {PRONOSTICOS_URL}", flush=True)
        await page.goto(PRONOSTICOS_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(4000)

        matches = []
        # Buscar tabla principal de pronósticos
        tables = await page.query_selector_all("table")
        for tbl in tables:
            headers = await tbl.query_selector_all("th")
            h_texts = [await h.inner_text() for h in headers]
            # Tiene columnas de jugadores?
            if len(h_texts) >= 4:
                players = [t.strip() for t in h_texts if t.strip() and
                           t.strip().lower() not in ("partido","fecha","resultado","res","match","goles","score")]
                rows = await tbl.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) < 3:
                        continue
                    texts = [await c.inner_text() for c in cells]
                    # Primer cell: partido (equipos)
                    match_text = texts[0].strip()
                    result_text = ""
                    bets = []
                    pts_list = []
                    # Busca resultado (e.g. "2-1")
                    for t in texts[1:3]:
                        if re.search(r'\d+\s*[-–]\s*\d+', t):
                            result_text = re.search(r'\d+\s*[-–]\s*\d+', t).group().replace("–","-")
                            break
                    # Resto son apuestas
                    for t in texts:
                        bm = re.search(r'(\d+)\s*[-–]\s*(\d+)', t)
                        if bm and t != result_text:
                            bets.append(bm.group().replace("–","-"))

                    # Equipos
                    teams = re.split(r'\s+vs\.?\s+|\s+-\s+', match_text, flags=re.IGNORECASE)
                    home = teams[0].strip() if teams else match_text
                    away = teams[1].strip() if len(teams) > 1 else ""

                    if home and result_text:
                        # Calcular puntos
                        for bet in bets:
                            if bet == result_text:
                                pts_list.append(3)
                            elif result_text and bet:
                                rh, ra = map(int, result_text.split("-"))
                                bh, ba = map(int, bet.split("-"))
                                if (rh > ra and bh > ba) or (rh < ra and bh < ba) or (rh == ra and bh == ba):
                                    pts_list.append(1)
                                else:
                                    pts_list.append(0)
                            else:
                                pts_list.append(0)

                        matches.append({
                            "date": "",
                            "home": home,
                            "away": away,
                            "result": result_text,
                            "players": players,
                            "bets": bets,
                            "pts": pts_list,
                        })

        print(f"  → {len(matches)} partidos encontrados", flush=True)

        # Guarda datos crudos para debugging
        with open("scraped_data.json", "w", encoding="utf-8") as f:
            json.dump({"ranking": ranking, "matches": matches}, f, ensure_ascii=False, indent=2)

        await browser.close()
        return ranking, matches


def pts_badge(p, bet):
    if bet in ("—", "", None):
        return '<span style="color:#b4b2a9;">—</span>'
    if p == 3:
        return '<span class="badge b-exact">3</span>'
    if p == 1:
        return '<span class="badge b-ok">1</span>'
    return '<span class="badge b-zero">0</span>'


def generate_html(ranking, matches):
    now = datetime.now().strftime("%-d %b %H:%M")

    # Ranking HTML
    max_pts = ranking[0]["pts"] if ranking else 1
    rank_rows_html = ""
    pos = 0
    prev_pts = None
    for i, p in enumerate(ranking):
        if p["pts"] != prev_pts:
            pos = i + 1
            prev_pts = p["pts"]
        pct = round(p["pts"] / max_pts * 100, 1) if max_pts else 0
        is_you = YOU in p["name"]
        row_cls = "rank-row you-row" if is_you else "rank-row"
        if pos == 1:
            num_color = "#B8860B"
            badge_cls = "b-gold"
        elif pos == 2:
            num_color = "#888"
            badge_cls = "b-silver"
        else:
            num_color = "#888"
            badge_cls = "b-gray"
        bar_color = "#85B7EB" if is_you else ("#9FE1CB" if pos == 1 else "#C0DD97" if pos == 2 else "#D3D1C7")
        name_html = p["name"] + (' <span style="font-size:10px;background:#B5D4F4;color:#0C447C;padding:1px 6px;border-radius:4px;margin-left:4px;">tú</span>' if is_you else "")
        rank_rows_html += f"""
    <div class="{row_cls}">
      <span class="rank-num" style="color:{num_color};">{pos}</span>
      <span style="flex:1;font-weight:500;{'color:#185FA5;' if is_you else ''}">{name_html}</span>
      <span style="font-size:13px;color:#888780;margin-right:8px;">{p['pts']} pts</span>
      <div class="bar-wrap"><div class="bar" style="width:{pct}%;background:{bar_color};"></div></div>
      <span class="badge {badge_cls}">{pos}°</span>
    </div>"""

    # Match más actual
    last_match_html = ""
    if matches:
        lm = matches[-1]
        players = lm.get("players", [])
        bets = lm.get("bets", [])
        pts = lm.get("pts", [])
        chips = ""
        for j, player in enumerate(players):
            bet = bets[j] if j < len(bets) else "—"
            p_val = pts[j] if j < len(pts) else 0
            is_you_chip = YOU in player
            chip_cls = "bet-chip you" if is_you_chip else "bet-chip"
            pts_cls = "pts-exact" if p_val == 3 else "pts-ok" if p_val == 1 else "pts-zero" if lm["result"] else "pts-pending"
            pts_label = f"+{p_val} pt" if lm["result"] else "pendiente"
            chips += f"""
      <div class="{chip_cls}">
        <span class="name">{player}</span>
        <span class="apuesta">{bet}</span>
        <span class="pts-chip {pts_cls}">{pts_label}</span>
      </div>"""
        last_match_html = f"""
  <div class="match-hero">
    <div class="match-tag"><span class="live-dot"></span> Match más actual</div>
    <div class="match-title">{lm['home']} vs {lm['away']}</div>
    <div class="match-meta">{lm.get('date','')}</div>
    <div class="score-big">{lm['result'].replace('-',' – ') if lm['result'] else '? – ?'}</div>
    <div class="score-label">{'Resultado final' if lm['result'] else 'En curso / pendiente'}</div>
    <div class="bets-grid">{chips}
    </div>
  </div>"""

    # Historial HTML
    players_header = ""
    if matches:
        for pl in matches[0].get("players", []):
            is_you = YOU in pl
            players_header += f'<th>{"★ " if is_you else ""}{pl}</th>'

    match_rows_js = json.dumps(matches, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>La Polla de Ulloa — Mundial 2026</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f2; color: #1a1a18; padding: 1.5rem 1rem; max-width: 960px; margin: 0 auto; }}
h1 {{ font-size: 20px; font-weight: 600; margin-bottom: 0.15rem; }}
.subtitle {{ font-size: 13px; color: #888780; margin-bottom: 1.25rem; }}
.tabs {{ display: flex; gap: 8px; margin-bottom: 1.25rem; flex-wrap: wrap; }}
.tab {{ padding: 7px 16px; border: 0.5px solid #b4b2a9; border-radius: 8px; font-size: 13px; cursor: pointer; background: transparent; color: #5f5e5a; font-family: inherit; }}
.tab.active {{ background: #1a1a18; color: #fff; font-weight: 500; border-color: #1a1a18; }}
.section {{ display: none; }}
.section.active {{ display: block; }}
.match-hero {{ background: #fff; border: 2px solid #85B7EB; border-radius: 16px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; }}
.match-tag {{ font-size: 11px; font-weight: 600; color: #185FA5; text-transform: uppercase; letter-spacing: 0.06em; display: flex; align-items: center; gap: 6px; margin-bottom: 0.6rem; }}
.live-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #27B07C; }}
.match-title {{ font-size: 17px; font-weight: 700; margin-bottom: 0.3rem; }}
.match-meta {{ font-size: 12px; color: #888780; margin-bottom: 1rem; }}
.score-big {{ font-size: 32px; font-weight: 700; color: #185FA5; margin-bottom: 0.25rem; }}
.score-label {{ font-size: 11px; color: #888780; margin-bottom: 1.25rem; }}
.bets-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.bet-chip {{ display: flex; flex-direction: column; align-items: center; background: #f1efe8; border-radius: 10px; padding: 8px 12px; min-width: 80px; flex: 1; }}
.bet-chip.you {{ background: #EBF4FD; border: 1.5px solid #85B7EB; }}
.bet-chip .name {{ font-size: 10px; color: #888780; margin-bottom: 3px; white-space: nowrap; }}
.bet-chip.you .name {{ color: #185FA5; }}
.bet-chip .apuesta {{ font-size: 15px; font-weight: 700; }}
.bet-chip.you .apuesta {{ color: #185FA5; }}
.bet-chip .pts-chip {{ margin-top: 4px; font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 999px; }}
.pts-exact {{ background: #9FE1CB; color: #085041; }}
.pts-ok    {{ background: #C0DD97; color: #27500A; }}
.pts-zero  {{ background: #F1EFE8; color: #5F5E5A; }}
.pts-pending {{ background: #B5D4F4; color: #0C447C; }}
.rank-rows {{ display: flex; flex-direction: column; gap: 8px; }}
.rank-row {{ display: flex; align-items: center; gap: 12px; padding: 10px 14px; background: #fff; border: 0.5px solid #d3d1c7; border-radius: 12px; }}
.rank-num {{ font-size: 18px; font-weight: 600; width: 28px; text-align: center; }}
.bar-wrap {{ flex: 1; background: #f1efe8; border-radius: 4px; height: 9px; overflow: hidden; min-width: 50px; }}
.bar {{ height: 100%; border-radius: 4px; }}
.you-row {{ background: #EBF4FD !important; border: 1.5px solid #85B7EB !important; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }}
.b-gold   {{ background:#FAC775; color:#633806; }}
.b-silver {{ background:#D3D1C7; color:#2C2C2A; }}
.b-gray   {{ background:#F1EFE8; color:#5F5E5A; }}
.b-exact  {{ background:#9FE1CB; color:#085041; }}
.b-ok     {{ background:#C0DD97; color:#27500A; }}
.b-zero   {{ background:#F1EFE8; color:#5F5E5A; }}
.b-you    {{ background:#B5D4F4; color:#0C447C; }}
.overflow {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ font-weight: 500; font-size: 11px; color: #888780; padding: 8px 8px; text-align: center; border-bottom: 0.5px solid #e8e7e3; white-space: nowrap; }}
th:first-child {{ text-align: left; }}
td {{ padding: 7px 8px; border-bottom: 0.5px solid #e8e7e3; color: #1a1a18; vertical-align: middle; text-align: center; }}
td:first-child {{ text-align: left; }}
tr:last-child td {{ border-bottom: none; }}
.res {{ display: inline-block; background: #f1efe8; border: 0.5px solid #b4b2a9; border-radius: 4px; padding: 1px 6px; font-size: 12px; font-weight: 500; }}
.note {{ font-size: 12px; color: #b4b2a9; margin-top: 1rem; }}
.legend {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 1rem; font-size: 12px; color: #888780; align-items: center; }}
</style>
</head>
<body>

<h1>⚽ La Polla de Ulloa</h1>
<p class="subtitle">Copa Mundial 2026 · actualizado {now}</p>

<div class="tabs">
  <button class="tab active" onclick="showTab('actual',this)">🔥 Match más actual</button>
  <button class="tab" onclick="showTab('ranking',this)">🏆 Ranking</button>
  <button class="tab" onclick="showTab('partidos',this)">📋 Historial</button>
</div>

<div id="actual" class="section active">
{last_match_html}
</div>

<div id="ranking" class="section">
  <div class="rank-rows">
{rank_rows_html}
  </div>
  <p class="note" style="margin-top:1rem;">Acierto exacto = 3 pts · ganador correcto = 1 pt</p>
</div>

<div id="partidos" class="section">
  <div class="overflow">
  <table>
    <thead>
      <tr>
        <th>Partido</th>
        <th>Res.</th>
        {players_header}
      </tr>
    </thead>
    <tbody id="matchBody"></tbody>
  </table>
  </div>
  <div class="legend">
    <span><span class="badge b-exact">3</span> exacto</span>
    <span><span class="badge b-ok">1</span> ganador ok</span>
    <span><span class="badge b-zero">0</span> fallo</span>
    <span style="color:#b4b2a9;">★ = tú</span>
  </div>
</div>

<script>
const matches = {match_rows_js};
function cell(p, bet) {{
  if (!bet || bet === '—') return '<td style="color:#b4b2a9;">—</td>';
  const cls = p===3 ? 'b-exact' : p===1 ? 'b-ok' : 'b-zero';
  return `<td><span class="badge ${{cls}}">${{p}}</span><div style="font-size:10px;color:#888780;margin-top:1px;">${{bet}}</div></td>`;
}}
const body = document.getElementById('matchBody');
matches.forEach(m => {{
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><span style="font-size:10px;color:#888780;">${{m.date}}</span><br><strong>${{m.home}}</strong> vs ${{m.away}}</td>
    <td><span class="res">${{m.result || '—'}}</span></td>
    ${{(m.bets||[]).map((b,i) => cell((m.pts||[])[i]||0, b)).join('')}}
  `;
  body.appendChild(tr);
}});
function showTab(id, el) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
}}
</script>
</body>
</html>"""


async def main():
    ranking, matches = await scrape()
    if not ranking and not matches:
        print("ERROR: No se pudo extraer datos. Revisa scraped_data.json", file=sys.stderr)
        sys.exit(1)
    html = generate_html(ranking, matches)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ index.html generado", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
