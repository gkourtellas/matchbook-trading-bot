"""Simple dashboard. Run this separately from the bot.

    python dashboard.py

Then open http://localhost:8050 in your browser.
Reads config/bets.db — does not touch the bot or place any bets.

Set DASHBOARD_PASSWORD in your .env to require a password when accessed
from outside (e.g. through the Cloudflare tunnel).
"""

import os
import re
import json
import sqlite3
import subprocess
import shutil
from datetime import datetime
from functools import wraps
from flask import Flask, jsonify, render_template_string, request, Response

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "bets.db")
STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "strategies.json")
LEAGUES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "leagues.json")
STATE_DIR = os.path.join(os.path.dirname(__file__), "..", "config", "state")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")

app = Flask(__name__)


def get_enabled_strategy_names():
    try:
        with open(STRATEGIES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {s["name"] for s in data.get("strategies", []) if s.get("enabled", True)}
    except Exception:
        return None


REQUIRED_FIELDS = [
    "name", "enabled", "sport_name", "market_name",
    "min_back_odds", "max_back_odds",
]


def load_strategies_file():
    if not os.path.isfile(STRATEGIES_FILE):
        return []
    with open(STRATEGIES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("strategies", [])


def validate_strategies(strategies):
    if not isinstance(strategies, list):
        return "strategies must be a list."

    names = []
    for i, s in enumerate(strategies):
        if not isinstance(s, dict):
            return f"Strategy #{i+1} is not a valid object."
        for field in REQUIRED_FIELDS:
            if field not in s:
                return f"Strategy '{s.get('name', f'#{i+1}')}' is missing required field '{field}'."
        names.append(s["name"])

        is_compound = s.get("strategy_type") == "compound"

        if is_compound:
            for f in ("compound_start", "compound_target"):
                if not s.get(f):
                    return f"Strategy '{s['name']}': compound strategy missing '{f}'."
        else:
            ladder = s.get("staking_plan", [])
            if not isinstance(ladder, list) or not ladder:
                return f"Strategy '{s['name']}': staking_plan must be a non-empty list."

            steps = s.get("staking_steps", len(ladder))
            if len(ladder) != steps:
                return (f"Strategy '{s['name']}': staking_steps ({steps}) doesn't match "
                        f"staking_plan length ({len(ladder)}).")

            if s.get("cash_out_at_percent") and len(ladder) > 1:
                return (f"Strategy '{s['name']}': cash_out_at_percent is only supported for "
                        f"single-step strategies (staking_plan with one number).")

        if s.get("min_back_odds", 0) > s.get("max_back_odds", 0):
            return f"Strategy '{s['name']}': min_back_odds is greater than max_back_odds."

        market = s.get("market_name") or (s.get("market_names") or [None])[0]
        bet_side = s.get("bet_side", "back")
        bet_mode = s.get("bet_mode", "normal")

        if bet_mode == "double_chance":
            if market != "Match Odds":
                return (f"Strategy '{s['name']}': bet_mode 'double_chance' requires "
                        f"market_name 'Match Odds' (used as the trigger).")
            if bet_side == "lay":
                return (f"Strategy '{s['name']}': bet_mode 'double_chance' only supports "
                        f"backing, not laying.")

        if bet_side == "lay" and market not in ("Match Odds", "Moneyline"):
            return (f"Strategy '{s['name']}': bet_side 'lay' is only supported for "
                    f"'Match Odds'/'Moneyline' markets right now.")
        if bet_side == "lay" and s.get("cash_out_at_percent"):
            return (f"Strategy '{s['name']}': cash_out_at_percent is not yet supported "
                    f"for lay-side strategies.")

        if market == "Total" and not (s.get("total_range") and s.get("total_direction")):
            return f"Strategy '{s['name']}': market is 'Total' but total_range/total_direction are missing."
        if market != "Total" and (s.get("total_range") or s.get("total_direction")):
            return f"Strategy '{s['name']}': total_range/total_direction are set but market isn't 'Total'."

        spread_cap = s.get("spread_cap_percent")
        if spread_cap is not None and spread_cap <= 0:
            return f"Strategy '{s['name']}': spread_cap_percent must be greater than 0."

        min_field_size = s.get("min_field_size")
        if min_field_size is not None and min_field_size < 1:
            return f"Strategy '{s['name']}': min_field_size must be at least 1."

    if len(names) != len(set(names)):
        return "Two strategies have the same name. Names must be unique."

    return None


def save_strategies_file(strategies):
    error = validate_strategies(strategies)
    if error:
        raise ValueError(error)

    if os.path.isfile(STRATEGIES_FILE):
        backup_dir = os.path.join(os.path.dirname(STRATEGIES_FILE), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(STRATEGIES_FILE, os.path.join(backup_dir, f"strategies_{stamp}.json"))

    with open(STRATEGIES_FILE, "w", encoding="utf-8") as f:
        json.dump({"strategies": strategies}, f, indent=2)


def restart_bot_container():
    try:
        result = subprocess.run(
            ["docker", "restart", "matchbook_trading_bot"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, "Bot restarted."
        return False, f"Restart failed: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Could not restart bot: {e}"


def require_password(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not DASHBOARD_PASSWORD:
            return view(*args, **kwargs)
        auth = request.authorization
        if not auth or auth.password != DASHBOARD_PASSWORD:
            return Response(
                "Password required.", 401,
                {"WWW-Authenticate": 'Basic realm="Dashboard"'}
            )
        return view(*args, **kwargs)
    return wrapped


PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bet Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0e14;
    --card: #11161f;
    --card2: #141a25;
    --border: #1c2330;
    --border-thick: #2a3344;
    --text: #e4e7ec;
    --muted: #7a8699;
    --win: #2dd4a8;
    --loss: #ff6b5e;
    --pending: #f5b942;
    --accent: #5b8def;
  }
  * { box-sizing: border-box; }
  body {
    font-family: 'Inter', -apple-system, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    margin: 0;
    padding: 28px 32px 60px;
  }
  .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
  .topbar h0 {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: var(--muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .nav-btn {
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    font-weight: 600;
    color: var(--bg);
    background: var(--accent);
    border: none;
    border-radius: 8px;
    padding: 9px 16px;
    text-decoration: none;
    cursor: pointer;
  }
  .nav-btn:hover { opacity: 0.85; }
  h1 {
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    margin: 36px 0 12px;
  }
  h1:first-of-type { margin-top: 0; }
  table { border-collapse: collapse; width: 100%; }
  th, td {
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    font-size: 13.5px;
  }
  td { font-family: 'JetBrains Mono', monospace; }
  td:first-child, th:first-child { font-family: 'Inter', sans-serif; }
  th {
    color: var(--muted);
    font-weight: 500;
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 4px 16px; overflow-x: auto; }
  .profit { color: var(--win); }
  .loss { color: var(--loss); }
  .pending { color: var(--pending); }
  .strategy-block { border-top: 2px solid var(--border-thick); }
  .strategy-block:first-child { border-top: none; }
  .hero-row { display: flex; gap: 16px; margin-bottom: 8px; flex-wrap: wrap; }
  .hero-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 20px;
    flex: 1;
    min-width: 150px;
  }
  .hero-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
  .hero-value { font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 700; }
  .sub-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
  .sub-tab {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--muted);
    background: var(--card2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 12px;
    cursor: pointer;
  }
  .sub-tab.active { color: var(--text); border-color: var(--accent); }
  .period-row { display: none; }
  .period-row.active { display: block; }
  .small { color: var(--muted); font-size: 11.5px; font-family: 'JetBrains Mono', monospace; margin-bottom: 14px; }
  canvas { max-width: 100%; }
</style>
</head>
<body>
  <div class="topbar">
    <h0>matchbook // live dashboard</h0>
    <div style="display:flex; gap:10px;">
      <a class="nav-btn" style="background: var(--card2); color: var(--text); border: 1px solid var(--border);" href="/strategies">⚙ Manage Strategies</a>
      <a class="nav-btn" href="/analytics">Analytics →</a>
    </div>
  </div>

  <h1>Open Positions <span style="font-weight:400; text-transform:none; letter-spacing:0;">— currently pending</span></h1>
  <div class="card"><div id="pending"></div></div>

  <h1>Strategy Performance</h1>
  <div class="card"><div id="summary"></div></div>

  <h1>Profit</h1>
  <div class="card" style="padding: 16px;">
    <div class="sub-tabs">
      <div class="sub-tab active" data-period="daily">Daily (7d)</div>
      <div class="sub-tab" data-period="monthly">Monthly</div>
      <div class="sub-tab" data-period="yearly">Yearly</div>
    </div>
    <canvas id="profitChart" height="90"></canvas>
  </div>

  <h1>Step Frequency <span style="font-weight:400; text-transform:none; letter-spacing:0;">— multi-step strategies only</span></h1>
  <div class="card"><div id="steps"></div></div>

  <h1>Win Rate by League <span style="font-weight:400; text-transform:none; letter-spacing:0;">— per strategy</span></h1>
  <div class="card"><div id="leagueBreakdown"></div></div>

  <h1>Recent Bets <span style="font-weight:400; text-transform:none; letter-spacing:0;">— last 50</span></h1>
  <div class="card"><div id="recent"></div></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-datalabels/2.2.0/chartjs-plugin-datalabels.min.js"></script>
<script>
function fmt(n) { return (n >= 0 ? '+' : '') + n.toFixed(2); }
function cls(n) { return n >= 0 ? 'profit' : 'loss'; }
if (window.ChartDataLabels) { Chart.register(window.ChartDataLabels); }

fetch('/api/summary').then(r => r.json()).then(data => {
  let html = '<table><tr><th>Strategy</th><th>Bets</th><th>Won</th><th>Lost</th><th>Pending</th><th>Win %</th><th>Profit</th></tr>';
  data.forEach(s => {
    const rowStyle = s.enabled ? '' : ' style="opacity:0.45;"';
    const nameLabel = s.enabled ? s.strategy_name : `${s.strategy_name} (inactive)`;
    html += `<tr${rowStyle}>
      <td>${nameLabel}</td>
      <td>${s.total}</td>
      <td>${s.won}</td>
      <td>${s.lost}</td>
      <td class="pending">${s.pending}</td>
      <td>${s.win_rate}%</td>
      <td class="${cls(s.profit)}">${fmt(s.profit)}</td>
    </tr>`;
  });
  html += '</table>';
  document.getElementById('summary').innerHTML = html;
});

fetch('/api/steps').then(r => r.json()).then(data => {
  if (!data.length) {
    document.getElementById('steps').innerHTML = '<p class="small">No multi-step strategies with bets yet.</p>';
    return;
  }
  let html = '<table><tr><th>Strategy</th><th>Step</th><th>Times Reached</th></tr>';
  let lastStrategy = null;
  data.forEach(s => {
    const newBlock = lastStrategy !== null && lastStrategy !== s.strategy_name;
    html += `<tr class="${newBlock ? 'strategy-block' : ''}"><td>${s.strategy_name}</td><td>${s.step}</td><td>${s.count}</td></tr>`;
    lastStrategy = s.strategy_name;
  });
  html += '</table>';
  document.getElementById('steps').innerHTML = html;
});

fetch('/api/strategy_league_breakdown').then(r => r.json()).then(data => {
  if (!data.length) {
    document.getElementById('leagueBreakdown').innerHTML = '<p class="small">No settled bets with a captured league yet.</p>';
    return;
  }
  let html = '<table><tr><th>Strategy</th><th>League</th><th>Bets</th><th>Won</th><th>Lost</th><th>Win %</th><th>Profit</th></tr>';
  let lastStrategy = null;
  data.forEach(r => {
    const newBlock = lastStrategy !== null && lastStrategy !== r.strategy_name;
    html += `<tr class="${newBlock ? 'strategy-block' : ''}">
      <td>${r.strategy_name}</td>
      <td>${r.league}</td>
      <td>${r.total}</td>
      <td>${r.won}</td>
      <td>${r.lost}</td>
      <td>${r.win_rate}%</td>
      <td class="${cls(r.profit)}">${fmt(r.profit)}</td>
    </tr>`;
    lastStrategy = r.strategy_name;
  });
  html += '</table>';
  document.getElementById('leagueBreakdown').innerHTML = html;
});

fetch('/api/pending').then(r => r.json()).then(data => {
  if (!data.length) {
    document.getElementById('pending').innerHTML = '<p class="small">No open positions right now.</p>';
    return;
  }
  let html = '<table><tr><th>Placed</th><th>Strategy</th><th>League</th><th>Match</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Step</th></tr>';
  let lastStrategy = null;
  data.forEach(b => {
    const newBlock = lastStrategy !== null && lastStrategy !== b.strategy_name;
    html += `<tr class="${newBlock ? 'strategy-block' : ''}">
      <td>${(b.placed_at || '').replace('T', ' ').slice(0, 16)}</td>
      <td>${b.strategy_name}</td>
      <td>${b.league || '-'}</td>
      <td>${b.event_name}</td>
      <td>${b.selection_name}</td>
      <td>${b.odds}</td>
      <td>${b.stake}</td>
      <td>${b.step}</td>
    </tr>`;
    lastStrategy = b.strategy_name;
  });
  html += '</table>';
  document.getElementById('pending').innerHTML = html;
});

fetch('/api/recent').then(r => r.json()).then(data => {
  let html = '<table><tr><th>Time</th><th>Strategy</th><th>League</th><th>Match</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Step</th><th>Result</th><th>Profit</th></tr>';
  data.forEach(b => {
    const resultClass = b.result === 'won' ? 'profit' : 'loss';
    html += `<tr>
      <td>${(b.placed_at || '').replace('T', ' ').slice(0, 16)}</td>
      <td>${b.strategy_name}</td>
      <td>${b.league || '-'}</td>
      <td>${b.event_name}</td>
      <td>${b.selection_name}</td>
      <td>${b.odds}</td>
      <td>${b.stake}</td>
      <td>${b.step}</td>
      <td class="${resultClass}">${b.result}</td>
      <td class="${cls(b.profit || 0)}">${fmt(b.profit)}</td>
    </tr>`;
  });
  html += '</table>';
  document.getElementById('recent').innerHTML = html;
});

let profitChart = null;
fetch('/api/profit_periods').then(r => r.json()).then(data => {
  function draw(period) {
    const rows = data[period];
    const labels = rows.map(r => r.period);
    const values = rows.map(r => r.profit);
    const colors = values.map(v => v >= 0 ? '#2dd4a8' : '#ff6b5e');
    if (profitChart) profitChart.destroy();
    profitChart = new Chart(document.getElementById('profitChart'), {
      type: 'bar',
      data: { labels: labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 4 }] },
      options: {
        plugins: {
          legend: { display: false },
          datalabels: {
            color: '#e4e7ec',
            font: { family: 'JetBrains Mono', size: 11, weight: '600' },
            anchor: 'end',
            align: 'end',
            formatter: v => fmt(v)
          }
        },
        scales: {
          x: { grid: { color: '#1c2330' }, ticks: { color: '#7a8699', font: { family: 'JetBrains Mono', size: 11 } } },
          y: { grid: { color: '#1c2330' }, ticks: { color: '#7a8699', font: { family: 'JetBrains Mono', size: 11 } } }
        }
      }
    });
  }
  draw('daily');
  document.querySelectorAll('.sub-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      draw(tab.dataset.period);
    });
  });
});
</script>
</body>
</html>
"""


ANALYTICS_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analytics</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0e14; --card: #11161f; --card2: #141a25;
    --border: #1c2330; --text: #e4e7ec; --muted: #7a8699;
    --win: #2dd4a8; --loss: #ff6b5e; --pending: #f5b942; --accent: #5b8def;
  }
  * { box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, Arial, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 28px 32px 60px; }
  .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
  .topbar h0 { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--muted); letter-spacing: 0.12em; text-transform: uppercase; }
  .nav-btn { font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 600; color: var(--bg); background: var(--accent); border: none; border-radius: 8px; padding: 9px 16px; text-decoration: none; cursor: pointer; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  .full { grid-column: 1 / -1; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; }
  .card h2 { font-size: 13px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); margin: 0 0 14px; }
  canvas { max-width: 100%; }
  .empty { color: var(--muted); font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 30px 0; text-align: center; }
</style>
</head>
<body>
  <div class="topbar">
    <h0>matchbook // analytics</h0>
    <a class="nav-btn" href="/">← Dashboard</a>
  </div>

  <div class="grid">
    <div class="card full">
      <h2>Cumulative Profit Over Time</h2>
      <canvas id="cumulativeChart" height="70"></canvas>
    </div>

    <div class="card">
      <h2>Win Rate by Odds Range</h2>
      <canvas id="oddsChart" height="160"></canvas>
    </div>

    <div class="card">
      <h2>Bet Volume by Strategy</h2>
      <canvas id="mixChart" height="160"></canvas>
    </div>

    <div class="card">
      <h2>Bets Placed by Day of Week</h2>
      <canvas id="weekdayChart" height="160"></canvas>
    </div>

    <div class="card">
      <h2>Stake vs Profit</h2>
      <canvas id="scatterChart" height="160"></canvas>
    </div>

    <div class="card full">
      <h2>Profit per Strategy</h2>
      <canvas id="profitPerStrategyChart" height="90"></canvas>
    </div>

    <div class="card full">
      <h2>Profit per League <span style="font-weight:400; text-transform:none; letter-spacing:0;">— worst to best</span></h2>
      <canvas id="profitPerLeagueChart" height="120"></canvas>
    </div>
  </div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-datalabels/2.2.0/chartjs-plugin-datalabels.min.js"></script>
<script>
if (window.ChartDataLabels) { Chart.register(window.ChartDataLabels); }
const muted = '#7a8699';
const gridColor = '#1c2330';
const win = '#2dd4a8';
const loss = '#ff6b5e';
const accent = '#5b8def';
const palette = ['#5b8def', '#2dd4a8', '#f5b942', '#ff6b5e', '#a78bfa', '#38bdf8'];

const baseTicks = { color: muted, font: { family: 'JetBrains Mono', size: 11 } };
const baseGrid = { color: gridColor };

fetch('/api/chart_data').then(r => r.json()).then(data => {

  if (data.cumulative.length) {
    let running = 0;
    const labels = [];
    const values = [];
    data.cumulative.forEach(b => {
      running += b.profit;
      labels.push((b.settled_at || '').slice(0, 16).replace('T', ' '));
      values.push(running);
    });
    new Chart(document.getElementById('cumulativeChart'), {
      type: 'line',
      data: { labels: labels, datasets: [{
        data: values, borderColor: accent, backgroundColor: 'rgba(91,141,239,0.08)',
        fill: true, tension: 0.25, pointRadius: 0, borderWidth: 2
      }]},
      options: {
        plugins: { legend: { display: false }, datalabels: { display: false } },
        scales: {
          x: { grid: baseGrid, ticks: { ...baseTicks, maxTicksLimit: 8, maxRotation: 0 } },
          y: { grid: baseGrid, ticks: baseTicks }
        }
      }
    });
  } else {
    document.getElementById('cumulativeChart').outerHTML = '<div class="empty">No settled bets yet</div>';
  }

  if (data.odds_buckets.length) {
    const labels = data.odds_buckets.map(b => b.bucket);
    const rates = data.odds_buckets.map(b => b.total ? Math.round(100 * b.won / b.total) : 0);
    new Chart(document.getElementById('oddsChart'), {
      type: 'bar',
      data: { labels, datasets: [{ data: rates, backgroundColor: win, borderRadius: 4 }] },
      options: {
        plugins: {
          legend: { display: false },
          datalabels: {
            color: '#0a0e14',
            font: { family: 'JetBrains Mono', size: 11, weight: '600' },
            anchor: 'end',
            align: 'top',
            formatter: v => v + '%'
          }
        },
        scales: { x: { grid: baseGrid, ticks: baseTicks }, y: { grid: baseGrid, ticks: baseTicks, max: 100 } }
      }
    });
  } else {
    document.getElementById('oddsChart').outerHTML = '<div class="empty">No settled bets yet</div>';
  }

  if (data.market_mix.length) {
    new Chart(document.getElementById('mixChart'), {
      type: 'doughnut',
      data: {
        labels: data.market_mix.map(m => m.strategy_name),
        datasets: [{ data: data.market_mix.map(m => m.total), backgroundColor: palette, borderWidth: 0 }]
      },
      options: {
        plugins: {
          legend: { position: 'bottom', labels: { color: muted, font: { size: 11 } } },
          datalabels: {
            color: '#0a0e14',
            font: { family: 'JetBrains Mono', size: 11, weight: '600' },
            formatter: v => v
          }
        }
      }
    });
  } else {
    document.getElementById('mixChart').outerHTML = '<div class="empty">No bets yet</div>';
  }

  if (data.weekday.length) {
    new Chart(document.getElementById('weekdayChart'), {
      type: 'bar',
      data: { labels: data.weekday.map(d => d.day), datasets: [{ data: data.weekday.map(d => d.total), backgroundColor: accent, borderRadius: 4 }] },
      options: {
        plugins: {
          legend: { display: false },
          datalabels: {
            color: '#e4e7ec',
            font: { family: 'JetBrains Mono', size: 11, weight: '600' },
            anchor: 'end',
            align: 'top'
          }
        },
        scales: { x: { grid: baseGrid, ticks: baseTicks }, y: { grid: baseGrid, ticks: baseTicks } }
      }
    });
  } else {
    document.getElementById('weekdayChart').outerHTML = '<div class="empty">No bets yet</div>';
  }

  if (data.stake_vs_profit.length) {
    const points = data.stake_vs_profit.map(b => ({ x: b.stake, y: b.profit }));
    const colors = data.stake_vs_profit.map(b => b.result === 'won' ? win : loss);
    new Chart(document.getElementById('scatterChart'), {
      type: 'scatter',
      data: { datasets: [{ data: points, backgroundColor: colors, pointRadius: 5 }] },
      options: {
        plugins: { legend: { display: false }, datalabels: { display: false } },
        scales: {
          x: { title: { display: true, text: 'Stake', color: muted }, grid: baseGrid, ticks: baseTicks },
          y: { title: { display: true, text: 'Profit', color: muted }, grid: baseGrid, ticks: baseTicks }
        }
      }
    });
  } else {
    document.getElementById('scatterChart').outerHTML = '<div class="empty">No settled bets yet</div>';
  }

  if (data.profit_per_strategy && data.profit_per_strategy.length) {
    const labels = data.profit_per_strategy.map(s => s.strategy_name);
    const values = data.profit_per_strategy.map(s => s.profit);
    const colors = values.map(v => v >= 0 ? win : loss);
    new Chart(document.getElementById('profitPerStrategyChart'), {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 4 }] },
      options: {
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          datalabels: {
            color: '#e4e7ec',
            font: { family: 'JetBrains Mono', size: 11, weight: '600' },
            anchor: 'end',
            align: 'right',
            formatter: v => (v >= 0 ? '+' : '') + v.toFixed(2)
          }
        },
        scales: { x: { grid: baseGrid, ticks: baseTicks }, y: { grid: baseGrid, ticks: baseTicks } }
      }
    });
  } else if (document.getElementById('profitPerStrategyChart')) {
    document.getElementById('profitPerStrategyChart').outerHTML = '<div class="empty">No settled bets yet</div>';
  }

  if (data.profit_per_league && data.profit_per_league.length) {
    const labels = data.profit_per_league.map(l => l.league);
    const values = data.profit_per_league.map(l => l.profit);
    const winRates = data.profit_per_league.map(l => l.win_rate);
    const colors = values.map(v => v >= 0 ? win : loss);
    new Chart(document.getElementById('profitPerLeagueChart'), {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 4 }] },
      options: {
        indexAxis: 'y',
        plugins: {
          legend: { display: false },
          datalabels: {
            color: '#e4e7ec',
            font: { family: 'JetBrains Mono', size: 11, weight: '600' },
            anchor: 'end',
            align: 'right',
            formatter: v => (v >= 0 ? '+' : '') + v.toFixed(2)
          },
          tooltip: {
            callbacks: {
              afterLabel: (ctx) => `Win rate: ${winRates[ctx.dataIndex]}%`
            }
          }
        },
        scales: { x: { grid: baseGrid, ticks: baseTicks }, y: { grid: baseGrid, ticks: baseTicks } }
      }
    });
  } else if (document.getElementById('profitPerLeagueChart')) {
    document.getElementById('profitPerLeagueChart').outerHTML = '<div class="empty">No league data yet — leagues are captured as new bets are placed</div>';
  }
});
</script>
</body>
</html>
"""


STRATEGIES_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manage Strategies</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0e14; --card: #11161f; --card2: #141a25;
    --border: #1c2330; --text: #e4e7ec; --muted: #7a8699;
    --win: #2dd4a8; --loss: #ff6b5e; --pending: #f5b942; --accent: #5b8def;
  }
  * { box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, Arial, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 28px 32px 60px; }
  .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
  .topbar h0 { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--muted); letter-spacing: 0.12em; text-transform: uppercase; }
  .nav-btn { font-family: 'Inter', sans-serif; font-size: 13px; font-weight: 600; color: var(--bg); background: var(--accent); border: none; border-radius: 8px; padding: 9px 16px; text-decoration: none; cursor: pointer; }
  .nav-btn.secondary { background: var(--card2); color: var(--text); border: 1px solid var(--border); }
  .nav-btn.danger { background: var(--loss); }
  h1 { font-size: 14px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); margin: 30px 0 12px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }
  .strat-row { display: flex; justify-content: space-between; align-items: center; }
  .strat-name { font-weight: 600; font-size: 14.5px; }
  .strat-meta { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--muted); margin-top: 4px; }
  .badge { font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 3px 8px; border-radius: 4px; margin-right: 8px; }
  .badge.on { background: rgba(45,212,168,0.15); color: var(--win); }
  .badge.off { background: rgba(122,134,153,0.15); color: var(--muted); }
  .row-actions { display: flex; gap: 8px; }
  .btn { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--card2); color: var(--text); cursor: pointer; }
  .btn:hover { border-color: var(--accent); }
  .btn.danger:hover { border-color: var(--loss); color: var(--loss); }
  .btn.reset:hover { border-color: var(--pending); color: var(--pending); }
  .add-btn { font-family: 'JetBrains Mono', monospace; font-size: 13px; padding: 10px 16px; border-radius: 8px; border: 1px dashed var(--border); background: transparent; color: var(--muted); cursor: pointer; width: 100%; margin-top: 6px; }
  .add-btn:hover { border-color: var(--accent); color: var(--accent); }

  .modal-bg { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); align-items: center; justify-content: center; z-index: 10; }
  .modal-bg.open { display: flex; }
  .modal { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; width: 600px; max-height: 85vh; overflow-y: auto; }
  .modal h2 { margin: 0 0 16px; font-size: 15px; }
  .field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .field { margin-bottom: 12px; }
  .field.full { grid-column: 1 / -1; }
  .field label { display: block; font-size: 11.5px; color: var(--muted); margin-bottom: 5px; font-family: 'JetBrains Mono', monospace; }
  .field input, .field select { width: 100%; background: var(--card2); border: 1px solid var(--border); border-radius: 6px; color: var(--text); padding: 8px 10px; font-family: 'JetBrains Mono', monospace; font-size: 13px; }
  .field input[type="checkbox"] { width: auto; }
  .checkbox-row { display: flex; align-items: center; gap: 8px; }
  .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
  .error-box { background: rgba(255,107,94,0.12); border: 1px solid var(--loss); color: var(--loss); padding: 10px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 14px; display: none; }
  .saving-banner { display: none; background: rgba(245,185,66,0.12); border: 1px solid var(--pending); color: var(--pending); padding: 10px 14px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 13px; margin-bottom: 16px; }
</style>
</head>
<body>
  <div class="topbar">
    <h0>matchbook // manage strategies</h0>
    <div style="display:flex; gap:10px;">
      <button class="nav-btn" style="background: var(--pending); color: #1a1300;" onclick="restartBot()">⟲ Restart Bot</button>
      <a class="nav-btn secondary" href="/">← Dashboard</a>
    </div>
  </div>

  <div class="saving-banner" id="savingBanner">Saving…</div>
  <div class="saving-banner" id="restartBanner" style="border-color: var(--accent); color: var(--accent); background: rgba(91,141,239,0.12);">Restarting the bot…</div>

  <h1>Strategies</h1>
  <p style="font-family:'JetBrains Mono', monospace; font-size:12px; color:var(--muted); margin-top:-6px;">
    Changes are saved immediately, but the bot doesn't pick them up until you click Restart Bot above.
  </p>
  <div id="strategyList"></div>
  <button class="add-btn" onclick="openModal(null)">+ Add strategy (single sport)</button>
  <button class="add-btn" onclick="openMultiModal(null)" style="margin-top:4px;">+ Add strategy (multi-sport)</button>

  <div class="modal-bg" id="modalBg">
    <div class="modal">
      <h2 id="modalTitle">Add Strategy</h2>
      <div class="error-box" id="errorBox"></div>
      <div class="field-grid">
        <div class="field full"><label>Name</label><input id="f_name"></div>
        <div class="field"><label>Sport</label><input id="f_sport" placeholder="e.g. Soccer"></div>
        <div class="field"><label>Market</label><input id="f_market" placeholder="e.g. Match Odds"></div>
        <div class="field">
          <label>Bet side</label>
          <select id="f_bet_side">
            <option value="back">Back the matched selection</option>
            <option value="lay">Lay the opponent (Match Odds/Moneyline only)</option>
          </select>
        </div>
        <div class="field">
          <label>Bet mode</label>
          <select id="f_bet_mode">
            <option value="normal">Normal — bet on the matched market</option>
            <option value="double_chance">Double Chance — Match Odds triggers, bets on Double Chance</option>
          </select>
        </div>
        <div class="field"><label>Min back odds</label><input id="f_min_odds" type="number" step="0.01"></div>
        <div class="field"><label>Max back odds</label><input id="f_max_odds" type="number" step="0.01"></div>
        <div class="field">
          <label>Total line <span style="color:var(--muted); text-transform:none;">(Total market only)</span></label>
          <input id="f_total_range" placeholder="e.g. 2.5">
        </div>
        <div class="field">
          <label>Direction <span style="color:var(--muted); text-transform:none;">(Total market only)</span></label>
          <select id="f_total_direction">
            <option value="">— not a Total market —</option>
            <option value="Over">Over</option>
            <option value="Under">Under</option>
          </select>
        </div>
        <div class="field full">
          <label>Strategy type</label>
          <select id="f_strategy_type" onchange="onStrategyTypeChange()">
            <option value="normal">Normal (staking plan)</option>
            <option value="compound">Compound (all-in, compounding)</option>
          </select>
        </div>
        <div id="compound_fields" style="display:none;">
          <div class="field"><label>Starting balance</label><input id="f_compound_start" type="number" step="0.01" placeholder="e.g. 10"></div>
          <div class="field"><label>Target amount</label><input id="f_compound_target" type="number" step="0.01" placeholder="e.g. 20"></div>
        </div>
        <div id="normal_fields">
          <div class="field full"><label>Staking plan (comma-separated)</label><input id="f_staking_plan" placeholder="0.1, 0.3, 0.9, 2.7, 8.1, 24.3"></div>
        </div>
        <div class="field"><label>Max open bets</label><input id="f_max_open_bets" type="number"></div>
        <div class="field"><label>Bankroll</label><input id="f_bankroll" type="number" step="0.01"></div>
        <div class="field"><label>Max session loss</label><input id="f_max_session_loss" type="number" step="0.01"></div>
        <div class="field"><label>Target profit</label><input id="f_target_profit" type="number" step="0.01"></div>
        <div class="field"><label>Poll interval (seconds)</label><input id="f_poll_interval" type="number"></div>
        <div class="field"><label>Cooldown after bet (seconds)</label><input id="f_cooldown" type="number"></div>
        <div class="field"><label>Lookahead (minutes)</label><input id="f_lookahead" type="number"></div>
        <div class="field"><label>Min seconds to start</label><input id="f_min_seconds" type="number"></div>
        <div class="field"><label>Minimum liquidity</label><input id="f_min_liquidity" type="number" step="0.01"></div>
        <div class="field">
          <label>Cash out at % of stake <span style="color:var(--muted); text-transform:none;">(single-step only)</span></label>
          <input id="f_cash_out_percent" type="number" step="0.1" placeholder="e.g. 5 — leave blank to disable">
        </div>
        <div class="field">
          <label>Spread cap % <span style="color:var(--muted); text-transform:none;">(skip if back/lay gap too wide)</span></label>
          <input id="f_spread_cap_percent" type="number" step="0.1" placeholder="e.g. 5 — leave blank to disable">
        </div>
        <div class="field">
          <label>Min field size <span style="color:var(--muted); text-transform:none;">(racing mainly — blank for soccer/tennis)</span></label>
          <input id="f_min_field_size" type="number" placeholder="e.g. 4 — leave blank to disable">
        </div>
        <div class="field full">
          <label>Exclude leagues <span style="color:var(--muted); text-transform:none;">(this strategy will skip matches in checked leagues)</span></label>
          <div id="f_excluded_leagues" style="max-height: 160px; overflow-y: auto; background: var(--card2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;"></div>
        </div>
        <div class="field">
          <label>Betting timing</label>
          <select id="f_live_mode">
            <option value="pre">Pre-match only</option>
            <option value="live">Live only</option>
            <option value="both">Both</option>
          </select>
        </div>
        <div class="field full">
          <div class="checkbox-row"><input type="checkbox" id="f_enabled"><label style="margin:0;">Enabled</label></div>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn" onclick="closeModal()">Cancel</button>
        <button class="btn" style="border-color: var(--accent); color: var(--accent);" onclick="saveStrategy()">Save</button>
      </div>
    </div>
  </div>

  <!-- Multi-sport modal -->
  <div class="modal-bg" id="multiModalBg">
    <div class="modal" style="max-width:780px;">
      <h2 id="multiModalTitle">Add Multi-Sport Strategy</h2>
      <div class="error-box" id="multiErrorBox"></div>

      <div class="field-grid">
        <div class="field full"><label>Name</label><input id="mf_name"></div>

        <div class="field full">
          <label>Sports / Markets</label>
          <div id="mf_sport_rows" style="display:flex; flex-direction:column; gap:10px; margin-top:6px;"></div>
          <button class="btn" onclick="addSportRow()" style="margin-top:8px; font-size:12px;">+ Add sport</button>
        </div>

        <div class="field full">
          <label>Strategy type</label>
          <select id="mf_strategy_type" onchange="onMultiStrategyTypeChange()">
            <option value="normal">Normal (staking plan)</option>
            <option value="compound">Compound (all-in, compounding)</option>
          </select>
        </div>
        <div id="mf_compound_fields" style="display:none;">
          <div class="field"><label>Starting balance</label><input id="mf_compound_start" type="number" step="0.01" placeholder="e.g. 10"></div>
          <div class="field"><label>Target amount</label><input id="mf_compound_target" type="number" step="0.01" placeholder="e.g. 20"></div>
        </div>
        <div id="mf_normal_fields">
          <div class="field full"><label>Staking plan (comma-separated)</label><input id="mf_staking_plan" placeholder="0.1, 0.3, 0.9, 2.7, 8.1, 24.3"></div>
        </div>

        <div class="field"><label>Max open bets</label><input id="mf_max_open_bets" type="number" value="1"></div>
        <div class="field"><label>Bankroll</label><input id="mf_bankroll" type="number" step="0.01" value="10"></div>
        <div class="field"><label>Max session loss</label><input id="mf_max_session_loss" type="number" step="0.01" value="10"></div>
        <div class="field"><label>Target profit</label><input id="mf_target_profit" type="number" step="0.01" value="10"></div>
        <div class="field"><label>Poll interval (seconds)</label><input id="mf_poll_interval" type="number" value="600"></div>
        <div class="field"><label>Cooldown after bet (seconds)</label><input id="mf_cooldown" type="number" value="600"></div>
        <div class="field"><label>Lookahead (minutes)</label><input id="mf_lookahead" type="number" value="180"></div>
        <div class="field"><label>Min seconds to start</label><input id="mf_min_seconds" type="number" value="300"></div>
        <div class="field"><label>Minimum liquidity</label><input id="mf_min_liquidity" type="number" step="0.01" value="2"></div>
        <div class="field">
          <label>Spread cap % <span style="color:var(--muted); text-transform:none;">(skip if back/lay gap too wide)</span></label>
          <input id="mf_spread_cap_percent" type="number" step="0.1" placeholder="e.g. 5 — leave blank to disable">
        </div>
        <div class="field">
          <label>Min field size <span style="color:var(--muted); text-transform:none;">(racing mainly)</span></label>
          <input id="mf_min_field_size" type="number" placeholder="e.g. 4 — leave blank to disable">
        </div>
        <div class="field">
          <label>Betting timing</label>
          <select id="mf_live_mode">
            <option value="pre">Pre-match only</option>
            <option value="live">Live only</option>
            <option value="both">Both</option>
          </select>
        </div>
        <div class="field full">
          <label>Exclude leagues</label>
          <div id="mf_excluded_leagues" style="max-height:160px; overflow-y:auto; background:var(--card2); border:1px solid var(--border); border-radius:6px; padding:8px 10px;"></div>
        </div>
        <div class="field full">
          <div class="checkbox-row"><input type="checkbox" id="mf_enabled" checked><label style="margin:0;">Enabled</label></div>
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn" onclick="closeMultiModal()">Cancel</button>
        <button class="btn" style="border-color:var(--accent); color:var(--accent);" onclick="saveMultiStrategy()">Save</button>
      </div>
    </div>
  </div>

<script>
let strategies = [];
let editingIndex = null;
let allLeagues = [];

function fetchLeagues() {
  fetch('/api/leagues').then(r => r.json()).then(data => {
    allLeagues = Array.isArray(data) ? data : [];
  });
}

function fetchStrategies() {
  fetch('/api/strategies').then(r => r.json()).then(data => {
    if (data && data.error) {
      document.getElementById('strategyList').innerHTML =
        `<div class="card" style="border-color: var(--loss); color: var(--loss); font-family: 'JetBrains Mono', monospace; font-size: 13px;">
          Could not read strategies.json: ${data.error}
        </div>`;
      strategies = [];
      return;
    }
    strategies = data;
    renderList();
  });
}

function renderList() {
  let html = '';
  strategies.forEach((s, i) => {
    const badgeClass = s.enabled ? 'on' : 'off';
    const badgeText = s.enabled ? 'ACTIVE' : 'INACTIVE';
    const isMulti = s.strategy_mode === 'multi_sport';
    const liveTag = s.live_mode === 'live' ? ' · LIVE' : s.live_mode === 'both' ? ' · pre+live' : '';
    let metaLine;
    if (isMulti) {
      const sportList = (s.sport_configs || []).map(r => r.sport_name + '/' + r.market_name).join(', ');
      metaLine = `MULTI: ${sportList}${liveTag}`;
    } else {
      const sport = s.sport_name || (s.sport_names || [])[0] || '?';
      const market = s.market_name || (s.market_names || [])[0] || '?';
      metaLine = `${sport} · ${market}${s.bet_mode === 'double_chance' ? ' → Double Chance' : ''}${s.bet_side === 'lay' ? ' (LAY opponent)' : ''}${s.total_direction ? ' ' + s.total_direction + ' ' + s.total_range : ''} · odds ${s.min_back_odds}-${s.max_back_odds}${s.cash_out_at_percent ? ' · cash out @ ' + s.cash_out_at_percent + '%' : ''}${s.spread_cap_percent ? ' · spread cap ' + s.spread_cap_percent + '%' : ''}${s.min_field_size ? ' · min field ' + s.min_field_size : ''}${liveTag}`;
    }
    const editFn = isMulti ? `openMultiModal(${i})` : `openModal(${i})`;
    html += `<div class="card strat-row">
      <div>
        <div class="strat-name"><span class="badge ${badgeClass}">${badgeText}</span>${s.name}</div>
        <div class="strat-meta">${metaLine}</div>
      </div>
      <div class="row-actions">
        <button class="btn" onclick="${editFn}">Edit</button>
        <button class="btn" onclick="toggleActive(${i})">${s.enabled ? 'Disable' : 'Enable'}</button>
        <button class="btn reset" onclick="resetState('${s.name.replace(/'/g, "\\'")}')">Reset State</button>
        <button class="btn danger" onclick="removeStrategy(${i})">Remove</button>
      </div>
    </div>`;
  });
  document.getElementById('strategyList').innerHTML = html || '<p style="color:var(--muted); font-family:JetBrains Mono, monospace; font-size:13px;">No strategies yet.</p>';
}

function resetState(name) {
  if (!confirm('Reset state for "' + name + '"?\\nSteps and balance will restart from scratch on next bot start.')) return;
  fetch('/api/reset_state/' + encodeURIComponent(name), { method: 'DELETE' })
    .then(r => r.json())
    .then(() => alert('Done. Restart the bot to take effect.'))
    .catch(err => alert('Failed: ' + err));
}

function openModal(index) {
  editingIndex = index;
  document.getElementById('errorBox').style.display = 'none';
  const s = index === null ? {} : strategies[index];
  document.getElementById('modalTitle').textContent = index === null ? 'Add Strategy' : `Edit: ${s.name}`;
  document.getElementById('f_name').value = s.name || '';
  document.getElementById('f_sport').value = s.sport_name || (s.sport_names || [])[0] || '';
  document.getElementById('f_market').value = s.market_name || (s.market_names || [])[0] || '';
  document.getElementById('f_bet_side').value = s.bet_side || 'back';
  document.getElementById('f_bet_mode').value = s.bet_mode || 'normal';
  document.getElementById('f_min_odds').value = s.min_back_odds ?? 1.45;
  document.getElementById('f_max_odds').value = s.max_back_odds ?? 1.6;
  document.getElementById('f_total_range').value = s.total_range ?? '';
  document.getElementById('f_total_direction').value = s.total_direction ?? '';
  const stratType = s.strategy_type || 'normal';
  document.getElementById('f_strategy_type').value = stratType;
  document.getElementById('f_staking_plan').value = (s.staking_plan || [0.1,0.3,0.9,2.7,8.1,24.3]).join(', ');
  document.getElementById('f_compound_start').value = s.compound_start ?? '';
  document.getElementById('f_compound_target').value = s.compound_target ?? '';
  onStrategyTypeChange();
  document.getElementById('f_max_open_bets').value = s.max_open_bets ?? 1;
  document.getElementById('f_bankroll').value = s.bankroll ?? 10;
  document.getElementById('f_max_session_loss').value = s.max_session_loss ?? 10;
  document.getElementById('f_target_profit').value = s.target_profit ?? 10;
  document.getElementById('f_poll_interval').value = s.poll_interval_seconds ?? 600;
  document.getElementById('f_cooldown').value = s.open_positions_cooldown_seconds ?? 600;
  document.getElementById('f_lookahead').value = s.event_lookahead_minutes ?? 180;
  document.getElementById('f_min_seconds').value = s.min_seconds_to_start ?? 300;
  document.getElementById('f_min_liquidity').value = s.minimum_liquidity ?? 2;
  document.getElementById('f_cash_out_percent').value = s.cash_out_at_percent ?? '';
  document.getElementById('f_spread_cap_percent').value = s.spread_cap_percent ?? '';
  document.getElementById('f_min_field_size').value = s.min_field_size ?? '';

  const excluded = new Set(s.excluded_leagues || []);
  const leagueBox = document.getElementById('f_excluded_leagues');
  if (!allLeagues.length) {
    leagueBox.innerHTML = '<span style="color:var(--muted); font-size:12px;">No leagues captured yet — run get_leagues.py first.</span>';
  } else {
    leagueBox.innerHTML = allLeagues.map(name => {
      const checked = excluded.has(name) ? 'checked' : '';
      const safeId = 'league_' + name.replace(/[^a-zA-Z0-9]/g, '_');
      return `<div class="checkbox-row" style="margin-bottom:4px;">
        <input type="checkbox" id="${safeId}" data-league="${name.replace(/"/g, '&quot;')}" ${checked}>
        <label for="${safeId}" style="margin:0; font-family:'JetBrains Mono', monospace; font-size:12px; text-transform:none;">${name}</label>
      </div>`;
    }).join('');
  }

  document.getElementById('f_live_mode').value = s.live_mode || 'pre';
  document.getElementById('f_enabled').checked = s.enabled !== false;
  document.getElementById('modalBg').classList.add('open');
}


// ── Multi-sport modal ──────────────────────────────────────────
let editingMultiIndex = null;

const SPORT_ROW_TEMPLATE = (idx, data={}) => `
  <div class="sport-row" id="sport_row_${idx}" style="background:var(--card2); border:1px solid var(--border); border-radius:8px; padding:10px 12px; position:relative;">
    <button onclick="removeSportRow(${idx})" style="position:absolute;top:8px;right:10px;background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px;">✕</button>
    <div class="field-grid" style="grid-template-columns:1fr 1fr; gap:8px;">
      <div class="field"><label>Sport</label><input class="sr_sport" placeholder="e.g. Soccer" value="${data.sport_name||''}"></div>
      <div class="field"><label>Market</label><input class="sr_market" placeholder="e.g. Match Odds" value="${data.market_name||''}"></div>
      <div class="field">
        <label>Bet side</label>
        <select class="sr_bet_side">
          <option value="back" ${(data.bet_side||'back')==='back'?'selected':''}>Back</option>
          <option value="lay" ${data.bet_side==='lay'?'selected':''}>Lay</option>
        </select>
      </div>
      <div class="field">
        <label>Bet mode</label>
        <select class="sr_bet_mode">
          <option value="normal" ${(data.bet_mode||'normal')==='normal'?'selected':''}>Normal</option>
          <option value="double_chance" ${data.bet_mode==='double_chance'?'selected':''}>Double Chance</option>
        </select>
      </div>
      <div class="field"><label>Min odds</label><input class="sr_min_odds" type="number" step="0.01" value="${data.min_back_odds??1.45}"></div>
      <div class="field"><label>Max odds</label><input class="sr_max_odds" type="number" step="0.01" value="${data.max_back_odds??1.6}"></div>
      <div class="field"><label>Total line</label><input class="sr_total_range" placeholder="e.g. 2.5" value="${data.total_range||''}"></div>
      <div class="field">
        <label>Direction</label>
        <select class="sr_total_direction">
          <option value="" ${!data.total_direction?'selected':''}>— none —</option>
          <option value="Over" ${data.total_direction==='Over'?'selected':''}>Over</option>
          <option value="Under" ${data.total_direction==='Under'?'selected':''}>Under</option>
        </select>
      </div>
    </div>
  </div>`;

let sportRowCount = 0;

function addSportRow(data={}) {
  const idx = sportRowCount++;
  const container = document.getElementById('mf_sport_rows');
  const div = document.createElement('div');
  div.innerHTML = SPORT_ROW_TEMPLATE(idx, data);
  container.appendChild(div.firstElementChild);
}

function removeSportRow(idx) {
  const el = document.getElementById('sport_row_' + idx);
  if (el) el.remove();
}

function openMultiModal(index) {
  editingMultiIndex = index;
  sportRowCount = 0;
  document.getElementById('multiErrorBox').style.display = 'none';
  document.getElementById('mf_sport_rows').innerHTML = '';
  const s = index === null ? {} : strategies[index];
  document.getElementById('multiModalTitle').textContent = index === null ? 'Add Multi-Sport Strategy' : `Edit: ${s.name}`;
  document.getElementById('mf_name').value = s.name || '';
  document.getElementById('mf_strategy_type').value = s.strategy_type || 'normal';
  document.getElementById('mf_staking_plan').value = (s.staking_plan || [0.1,0.3,0.9,2.7,8.1,24.3]).join(', ');
  document.getElementById('mf_compound_start').value = s.compound_start ?? '';
  document.getElementById('mf_compound_target').value = s.compound_target ?? '';
  document.getElementById('mf_max_open_bets').value = s.max_open_bets ?? 1;
  document.getElementById('mf_bankroll').value = s.bankroll ?? 10;
  document.getElementById('mf_max_session_loss').value = s.max_session_loss ?? 10;
  document.getElementById('mf_target_profit').value = s.target_profit ?? 10;
  document.getElementById('mf_poll_interval').value = s.poll_interval_seconds ?? 600;
  document.getElementById('mf_cooldown').value = s.open_positions_cooldown_seconds ?? 600;
  document.getElementById('mf_lookahead').value = s.event_lookahead_minutes ?? 180;
  document.getElementById('mf_min_seconds').value = s.min_seconds_to_start ?? 300;
  document.getElementById('mf_min_liquidity').value = s.minimum_liquidity ?? 2;
  document.getElementById('mf_spread_cap_percent').value = s.spread_cap_percent ?? '';
  document.getElementById('mf_min_field_size').value = s.min_field_size ?? '';
  document.getElementById('mf_live_mode').value = s.live_mode || 'pre';
  document.getElementById('mf_enabled').checked = s.enabled !== false;

  const sports = s.sport_configs || (s.sport_name ? [{
    sport_name: s.sport_name, market_name: s.market_name,
    bet_side: s.bet_side, bet_mode: s.bet_mode,
    min_back_odds: s.min_back_odds, max_back_odds: s.max_back_odds,
    total_range: s.total_range, total_direction: s.total_direction
  }] : [{}]);
  sports.forEach(d => addSportRow(d));

  const excluded = new Set(s.excluded_leagues || []);
  const leagueBox = document.getElementById('mf_excluded_leagues');
  leagueBox.innerHTML = allLeagues.length
    ? allLeagues.map(name => {
        const safeId = 'ml_' + name.replace(/[^a-zA-Z0-9]/g, '_');
        return `<div class="checkbox-row" style="margin-bottom:4px;">
          <input type="checkbox" id="${safeId}" data-league="${name.replace(/"/g,'&quot;')}" ${excluded.has(name)?'checked':''}>
          <label for="${safeId}" style="margin:0;font-family:'JetBrains Mono',monospace;font-size:12px;text-transform:none;">${name}</label>
        </div>`;
      }).join('')
    : '<span style="color:var(--muted);font-size:12px;">No leagues captured yet.</span>';

  onMultiStrategyTypeChange();
  document.getElementById('multiModalBg').classList.add('open');
}

function closeMultiModal() {
  document.getElementById('multiModalBg').classList.remove('open');
}

function onMultiStrategyTypeChange() {
  const isCompound = document.getElementById('mf_strategy_type').value === 'compound';
  document.getElementById('mf_compound_fields').style.display = isCompound ? '' : 'none';
  document.getElementById('mf_normal_fields').style.display = isCompound ? 'none' : '';
}

function getSportRows() {
  return Array.from(document.querySelectorAll('#mf_sport_rows .sport-row')).map(row => ({
    sport_name: row.querySelector('.sr_sport').value.trim(),
    market_name: row.querySelector('.sr_market').value.trim(),
    bet_side: row.querySelector('.sr_bet_side').value,
    bet_mode: row.querySelector('.sr_bet_mode').value,
    min_back_odds: parseFloat(row.querySelector('.sr_min_odds').value),
    max_back_odds: parseFloat(row.querySelector('.sr_max_odds').value),
    total_range: row.querySelector('.sr_total_range').value.trim() || null,
    total_direction: row.querySelector('.sr_total_direction').value || null,
  }));
}

function showMultiError(msg) {
  const b = document.getElementById('multiErrorBox');
  b.textContent = msg; b.style.display = 'block';
}

function saveMultiStrategy() {
  const name = document.getElementById('mf_name').value.trim();
  if (!name) { showMultiError('Name is required.'); return; }

  const sportRows = getSportRows();
  if (!sportRows.length) { showMultiError('Add at least one sport.'); return; }
  for (const r of sportRows) {
    if (!r.sport_name || !r.market_name) { showMultiError('Each sport row needs a sport and market.'); return; }
    if (r.min_back_odds > r.max_back_odds) { showMultiError(`Min odds > max odds in one of the sport rows.`); return; }
    if (r.market_name === 'Total' && (!r.total_range || !r.total_direction)) {
      showMultiError(`Total market requires line and direction (row: ${r.sport_name}).`); return;
    }
  }

  const stratType = document.getElementById('mf_strategy_type').value;
  let plan = null, compoundStart = null, compoundTarget = null;
  if (stratType === 'compound') {
    compoundStart = parseFloat(document.getElementById('mf_compound_start').value);
    compoundTarget = parseFloat(document.getElementById('mf_compound_target').value);
    if (!compoundStart || !compoundTarget) { showMultiError('Compound strategy needs starting balance and target.'); return; }
    if (compoundTarget <= compoundStart) { showMultiError('Target must be greater than starting balance.'); return; }
  } else {
    plan = document.getElementById('mf_staking_plan').value
      .split(',').map(x => parseFloat(x.trim())).filter(x => !isNaN(x));
    if (!plan.length) { showMultiError('Staking plan must have at least one number.'); return; }
  }

  const spreadCapValue = document.getElementById('mf_spread_cap_percent').value;
  const spreadCap = spreadCapValue === '' ? null : parseFloat(spreadCapValue);
  const minFieldValue = document.getElementById('mf_min_field_size').value;
  const minField = minFieldValue === '' ? null : parseInt(minFieldValue);

  const existing = editingMultiIndex === null ? {} : strategies[editingMultiIndex];
  const checkedLeagues = Array.from(document.querySelectorAll('#mf_excluded_leagues input[type="checkbox"]:checked'))
    .map(el => el.dataset.league);

  const updated = {
    ...existing,
    name,
    strategy_mode: 'multi_sport',
    strategy_type: stratType,
    sport_configs: sportRows,
    sport_name: sportRows[0].sport_name,
    sport_names: sportRows.map(r => r.sport_name),
    market_name: sportRows[0].market_name,
    market_names: sportRows.map(r => r.market_name),
    min_back_odds: sportRows[0].min_back_odds,
    max_back_odds: sportRows[0].max_back_odds,
    staking_plan: plan,
    staking_steps: plan ? plan.length : null,
    base_stake: plan ? plan[0] : null,
    compound_start: compoundStart,
    compound_target: compoundTarget,
    max_open_bets: parseInt(document.getElementById('mf_max_open_bets').value) || 1,
    bankroll: parseFloat(document.getElementById('mf_bankroll').value),
    max_total_exposure: existing.max_total_exposure ?? parseFloat(document.getElementById('mf_bankroll').value),
    max_session_loss: parseFloat(document.getElementById('mf_max_session_loss').value),
    target_profit: parseFloat(document.getElementById('mf_target_profit').value),
    poll_interval_seconds: parseInt(document.getElementById('mf_poll_interval').value) || 600,
    open_positions_cooldown_seconds: parseInt(document.getElementById('mf_cooldown').value) || 600,
    pause_scanning_with_open_positions: existing.pause_scanning_with_open_positions ?? true,
    event_lookahead_minutes: parseInt(document.getElementById('mf_lookahead').value) || 180,
    min_seconds_to_start: parseInt(document.getElementById('mf_min_seconds').value) || 300,
    odds_type: existing.odds_type || 'DECIMAL',
    currency: existing.currency || 'EUR',
    minimum_liquidity: parseFloat(document.getElementById('mf_min_liquidity').value),
    spread_cap_percent: spreadCap,
    min_field_size: minField,
    live_mode: document.getElementById('mf_live_mode').value,
    enabled: document.getElementById('mf_enabled').checked,
    excluded_leagues: checkedLeagues,
    keep_in_play: existing.keep_in_play ?? false,
    autoRestart: existing.autoRestart ?? false,
    bet_side: sportRows[0].bet_side,
    bet_mode: sportRows[0].bet_mode,
    cash_out_at_percent: existing.cash_out_at_percent ?? null,
    total_range: null,
    total_direction: null,
  };

  if (editingMultiIndex === null) {
    strategies.push(updated);
  } else {
    strategies[editingMultiIndex] = updated;
  }

  fetch('/api/strategies', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(strategies)
  }).then(r => r.json()).then(data => {
    if (data.error) { showMultiError(data.error); strategies = data.strategies || strategies; return; }
    closeMultiModal();
    fetchStrategies();
  });
}
// ── end multi-sport ────────────────────────────────────────────

function onStrategyTypeChange() {
  const isCompound = document.getElementById('f_strategy_type').value === 'compound';
  document.getElementById('compound_fields').style.display = isCompound ? '' : 'none';
  document.getElementById('normal_fields').style.display = isCompound ? 'none' : '';
}

function closeModal() {
  document.getElementById('modalBg').classList.remove('open');
}

function saveStrategy() {
  const stratType = document.getElementById('f_strategy_type').value;
  const plan = document.getElementById('f_staking_plan').value
    .split(',').map(x => parseFloat(x.trim())).filter(x => !isNaN(x));

  const name = document.getElementById('f_name').value.trim();
  if (!name) { showError('Name is required.'); return; }

  if (stratType === 'compound') {
    const cs = parseFloat(document.getElementById('f_compound_start').value);
    const ct = parseFloat(document.getElementById('f_compound_target').value);
    if (!cs || !ct) { showError('Compound strategy requires Starting balance and Target amount.'); return; }
    if (ct <= cs) { showError('Target amount must be greater than Starting balance.'); return; }
  } else {
    if (!plan.length) { showError('Staking plan must have at least one number.'); return; }
  }

  const existing = editingIndex === null ? {} : strategies[editingIndex];
  const cashOutValue = document.getElementById('f_cash_out_percent').value;
  const cashOutPercent = cashOutValue === '' ? null : parseFloat(cashOutValue);
  const spreadCapValue = document.getElementById('f_spread_cap_percent').value;
  const spreadCapPercent = spreadCapValue === '' ? null : parseFloat(spreadCapValue);
  const minFieldValue = document.getElementById('f_min_field_size').value;
  const minFieldSize = minFieldValue === '' ? null : parseInt(minFieldValue);

  if (cashOutPercent && plan.length > 1) {
    showError('Cash out is only supported for single-step strategies (staking plan with one number). Remove the extra steps or clear the cash out field.');
    return;
  }

  if (spreadCapPercent !== null && spreadCapPercent <= 0) {
    showError('Spread cap % must be greater than 0.');
    return;
  }

  if (minFieldSize !== null && minFieldSize < 1) {
    showError('Min field size must be at least 1.');
    return;
  }

  const market = document.getElementById('f_market').value.trim();
  const betSide = document.getElementById('f_bet_side').value;
  const betMode = document.getElementById('f_bet_mode').value;
  const totalRange = document.getElementById('f_total_range').value.trim();
  const totalDirection = document.getElementById('f_total_direction').value;

  if (betMode === 'double_chance') {
    if (market !== 'Match Odds') {
      showError('Bet mode "Double Chance" requires Market to be "Match Odds" (used as the trigger).');
      return;
    }
    if (betSide === 'lay') {
      showError('Bet mode "Double Chance" only supports backing, not laying. Set Bet side to "Back".');
      return;
    }
  }

  if (betSide === 'lay' && market !== 'Match Odds' && market !== 'Moneyline') {
    showError('Lay side is only supported for Match Odds / Moneyline markets right now.');
    return;
  }
  if (betSide === 'lay' && cashOutPercent) {
    showError('Cash out is not supported yet for lay-side strategies. Clear the cash out field.');
    return;
  }

  if (market === 'Total' && (!totalRange || !totalDirection)) {
    showError('Market is "Total" — Total line and Direction are both required (e.g. 2.5 + Over).');
    return;
  }
  if (market !== 'Total' && (totalRange || totalDirection)) {
    showError('Total line / Direction are set but Market is not "Total". Clear them or change the market.');
    return;
  }

  const checkedLeagues = Array.from(document.querySelectorAll('#f_excluded_leagues input[type="checkbox"]:checked'))
    .map(el => el.dataset.league);

  const updated = {
    ...existing,
    name: name,
    live_mode: document.getElementById('f_live_mode').value,
    enabled: document.getElementById('f_enabled').checked,
    sport_name: document.getElementById('f_sport').value.trim(),
    sport_names: [document.getElementById('f_sport').value.trim()],
    market_name: document.getElementById('f_market').value.trim(),
    market_names: [document.getElementById('f_market').value.trim()],
    min_back_odds: parseFloat(document.getElementById('f_min_odds').value),
    max_back_odds: parseFloat(document.getElementById('f_max_odds').value),
    strategy_type: stratType,
    staking_plan: stratType === 'compound' ? null : plan,
    staking_steps: stratType === 'compound' ? null : plan.length,
    base_stake: stratType === 'compound' ? null : plan[0],
    compound_start: stratType === 'compound' ? parseFloat(document.getElementById('f_compound_start').value) : null,
    compound_target: stratType === 'compound' ? parseFloat(document.getElementById('f_compound_target').value) : null,
    max_open_bets: parseInt(document.getElementById('f_max_open_bets').value) || 1,
    bankroll: parseFloat(document.getElementById('f_bankroll').value),
    max_total_exposure: existing.max_total_exposure ?? parseFloat(document.getElementById('f_bankroll').value),
    max_session_loss: parseFloat(document.getElementById('f_max_session_loss').value),
    target_profit: parseFloat(document.getElementById('f_target_profit').value),
    poll_interval_seconds: parseInt(document.getElementById('f_poll_interval').value) || 600,
    open_positions_cooldown_seconds: parseInt(document.getElementById('f_cooldown').value) || 600,
    pause_scanning_with_open_positions: existing.pause_scanning_with_open_positions ?? true,
    event_lookahead_minutes: parseInt(document.getElementById('f_lookahead').value) || 180,
    min_seconds_to_start: parseInt(document.getElementById('f_min_seconds').value) || 300,
    odds_type: existing.odds_type || 'DECIMAL',
    currency: existing.currency || 'EUR',
    minimum_liquidity: parseFloat(document.getElementById('f_min_liquidity').value),
    cash_out_at_percent: cashOutPercent,
    spread_cap_percent: spreadCapPercent,
    min_field_size: minFieldSize,
    bet_side: betSide,
    bet_mode: betMode,
    excluded_leagues: checkedLeagues,
    keep_in_play: existing.keep_in_play ?? false,
    autoRestart: existing.autoRestart ?? false,
    total_range: market === 'Total' ? totalRange : null,
    total_direction: market === 'Total' ? totalDirection : null,
    description: existing.description || '',
  };

  if (editingIndex === null) {
    strategies.push(updated);
  } else {
    strategies[editingIndex] = updated;
  }

  persist();
}

function toggleActive(index) {
  strategies[index].enabled = !strategies[index].enabled;
  persist();
}

function removeStrategy(index) {
  if (!confirm(`Remove strategy "${strategies[index].name}"? This cannot be undone (a backup is kept).`)) return;
  strategies.splice(index, 1);
  persist();
}

function showError(msg) {
  const box = document.getElementById('errorBox');
  box.textContent = msg;
  box.style.display = 'block';
}

function persist() {
  document.getElementById('savingBanner').style.display = 'block';
  fetch('/api/strategies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(strategies)
  }).then(r => r.json()).then(result => {
    document.getElementById('savingBanner').style.display = 'none';
    if (result.error) {
      showError(result.error);
      return;
    }
    closeModal();
    fetchStrategies();
  }).catch(err => {
    document.getElementById('savingBanner').style.display = 'none';
    showError('Save failed: ' + err);
  });
}

function restartBot() {
  document.getElementById('restartBanner').style.display = 'block';
  fetch('/api/restart_bot', { method: 'POST' })
    .then(r => r.json())
    .then(result => {
      document.getElementById('restartBanner').style.display = 'none';
      alert(result.restarted ? 'Bot restarted.' : ('Restart failed: ' + result.message));
    })
    .catch(err => {
      document.getElementById('restartBanner').style.display = 'none';
      alert('Restart failed: ' + err);
    });
}

fetchLeagues();
fetchStrategies();
</script>
</body>
</html>
"""


def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_name TEXT,
            event_name TEXT,
            selection_name TEXT,
            odds REAL,
            stake REAL,
            step INTEGER,
            placed_at TEXT,
            settled_at TEXT,
            result TEXT,
            profit REAL
        )
    """)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.route("/")
@require_password
def home():
    return render_template_string(PAGE)


@app.route("/analytics")
@require_password
def analytics_page():
    return render_template_string(ANALYTICS_PAGE)


@app.route("/api/summary")
@require_password
def summary():
    rows = query("""
        SELECT strategy_name,
               COUNT(*) as total,
               SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as won,
               SUM(CASE WHEN result = 'lost' THEN 1 ELSE 0 END) as lost,
               SUM(CASE WHEN result IS NULL THEN 1 ELSE 0 END) as pending,
               COALESCE(SUM(profit), 0) as profit
        FROM bets
        GROUP BY strategy_name
        ORDER BY strategy_name
    """)
    enabled_names = get_enabled_strategy_names()
    for r in rows:
        settled = r["won"] + r["lost"]
        r["win_rate"] = round(100 * r["won"] / settled, 1) if settled else 0
        r["enabled"] = True if enabled_names is None else (r["strategy_name"] in enabled_names)

    rows.sort(key=lambda r: (not r["enabled"], r["strategy_name"]))
    return jsonify(rows)


@app.route("/api/strategy_league_breakdown")
@require_password
def strategy_league_breakdown():
    rows = query("""
        SELECT strategy_name, league,
               COUNT(*) as total,
               SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as won,
               SUM(CASE WHEN result = 'lost' THEN 1 ELSE 0 END) as lost,
               COALESCE(SUM(profit), 0) as profit
        FROM bets
        WHERE result IS NOT NULL AND league IS NOT NULL
        GROUP BY strategy_name, league
        ORDER BY strategy_name, profit ASC
    """)
    for r in rows:
        r["win_rate"] = round(100 * r["won"] / r["total"], 1) if r["total"] else 0
    return jsonify(rows)


@app.route("/api/steps")
@require_password
def steps():
    rows = query("""
        SELECT strategy_name, step, COUNT(*) as count
        FROM bets
        WHERE strategy_name IN (
            SELECT strategy_name FROM bets GROUP BY strategy_name HAVING MAX(step) > 1
        )
        GROUP BY strategy_name, step
        ORDER BY strategy_name, step
    """)
    return jsonify(rows)


@app.route("/api/profit_periods")
@require_password
def profit_periods():
    daily = query("""
        SELECT date(settled_at) as period, COALESCE(SUM(profit), 0) as profit
        FROM bets
        WHERE result IS NOT NULL AND date(settled_at) >= date('now', '-6 days')
        GROUP BY period
        ORDER BY period
    """)
    monthly = query("""
        SELECT strftime('%Y-%m', settled_at) as period, COALESCE(SUM(profit), 0) as profit
        FROM bets
        WHERE result IS NOT NULL
        GROUP BY period
        ORDER BY period
    """)
    yearly = query("""
        SELECT strftime('%Y', settled_at) as period, COALESCE(SUM(profit), 0) as profit
        FROM bets
        WHERE result IS NOT NULL
        GROUP BY period
        ORDER BY period
    """)
    return jsonify({"daily": daily, "monthly": monthly, "yearly": yearly})


@app.route("/api/chart_data")
@require_password
def chart_data():
    cumulative = query("""
        SELECT settled_at, strategy_name, profit
        FROM bets
        WHERE result IS NOT NULL
        ORDER BY settled_at ASC
    """)

    odds_buckets = query("""
        SELECT
          CASE
            WHEN odds < 1.5 THEN '< 1.50'
            WHEN odds < 1.55 THEN '1.50-1.54'
            WHEN odds < 1.6 THEN '1.55-1.59'
            ELSE '1.60+'
          END as bucket,
          COUNT(*) as total,
          SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as won
        FROM bets
        WHERE result IS NOT NULL
        GROUP BY bucket
    """)

    weekday = query("""
        SELECT
          CASE CAST(strftime('%w', placed_at) AS INTEGER)
            WHEN 0 THEN 'Sun' WHEN 1 THEN 'Mon' WHEN 2 THEN 'Tue'
            WHEN 3 THEN 'Wed' WHEN 4 THEN 'Thu' WHEN 5 THEN 'Fri'
            ELSE 'Sat'
          END as day,
          CAST(strftime('%w', placed_at) AS INTEGER) as day_num,
          COUNT(*) as total
        FROM bets
        GROUP BY day, day_num
        ORDER BY day_num
    """)

    stake_vs_profit = query("""
        SELECT strategy_name, stake, profit, result
        FROM bets
        WHERE result IS NOT NULL
    """)

    market_mix = query("""
        SELECT strategy_name, COUNT(*) as total
        FROM bets
        GROUP BY strategy_name
    """)

    profit_per_strategy = query("""
        SELECT strategy_name, COALESCE(SUM(profit), 0) as profit
        FROM bets
        WHERE result IS NOT NULL
        GROUP BY strategy_name
        ORDER BY profit DESC
    """)

    profit_per_league = query("""
        SELECT league,
               COUNT(*) as total,
               SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as won,
               COALESCE(SUM(profit), 0) as profit
        FROM bets
        WHERE result IS NOT NULL AND league IS NOT NULL
        GROUP BY league
        ORDER BY profit ASC
    """)
    for r in profit_per_league:
        r["win_rate"] = round(100 * r["won"] / r["total"], 1) if r["total"] else 0

    return jsonify({
        "cumulative": cumulative,
        "odds_buckets": odds_buckets,
        "weekday": weekday,
        "stake_vs_profit": stake_vs_profit,
        "market_mix": market_mix,
        "profit_per_strategy": profit_per_strategy,
        "profit_per_league": profit_per_league,
    })


@app.route("/api/pending")
@require_password
def pending():
    rows = query("""
        SELECT * FROM bets
        WHERE result IS NULL
        ORDER BY strategy_name, placed_at DESC
    """)
    return jsonify(rows)


@app.route("/api/recent")
@require_password
def recent():
    rows = query("""
        SELECT * FROM bets
        WHERE result IS NOT NULL
        ORDER BY placed_at DESC
        LIMIT 50
    """)
    return jsonify(rows)


@app.route("/api/leagues")
@require_password
def get_leagues():
    if not os.path.isfile(LEAGUES_FILE):
        return jsonify([])
    try:
        with open(LEAGUES_FILE, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies", methods=["GET"])
@require_password
def get_strategies():
    try:
        return jsonify(load_strategies_file())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies", methods=["POST"])
@require_password
def save_strategies():
    strategies = request.get_json(force=True)
    try:
        save_strategies_file(strategies)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Could not save: {e}"}), 500

    return jsonify({"saved": True})


@app.route("/api/restart_bot", methods=["POST"])
@require_password
def restart_bot():
    ok, msg = restart_bot_container()
    return jsonify({"restarted": ok, "message": msg})


@app.route("/api/reset_state/<strategy_name>", methods=["DELETE"])
@require_password
def reset_state(strategy_name):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", strategy_name.strip())
    path = os.path.join(STATE_DIR, f"{cleaned}.json")
    if os.path.isfile(path):
        os.remove(path)
    return jsonify({"reset": True})


@app.route("/strategies")
@require_password
def strategies_page():
    return render_template_string(STRATEGIES_PAGE)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
