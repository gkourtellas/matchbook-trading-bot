"""Simple dashboard. Run this separately from the bot.

    python dashboard.py

Then open http://localhost:8050 in your browser.
Reads config/bets.db — does not touch the bot or place any bets.

Set DASHBOARD_PASSWORD in your .env to require a password when accessed
from outside (e.g. through the Cloudflare tunnel).
"""

import os
import json
import sqlite3
from functools import wraps
from flask import Flask, jsonify, render_template_string, request, Response

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "bets.db")
STRATEGIES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "strategies.json")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")

app = Flask(__name__)


def get_enabled_strategy_names():
    """Returns the set of strategy names currently enabled in strategies.json."""
    try:
        with open(STRATEGIES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {s["name"] for s in data.get("strategies", []) if s.get("enabled", True)}
    except Exception:
        return None  # unknown — don't mark anything inactive if file can't be read


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
    <a class="nav-btn" href="/analytics">Analytics →</a>
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

  <h1>Recent Bets <span style="font-weight:400; text-transform:none; letter-spacing:0;">— last 50</span></h1>
  <div class="card"><div id="recent"></div></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
function fmt(n) { return (n >= 0 ? '+' : '') + n.toFixed(2); }
function cls(n) { return n >= 0 ? 'profit' : 'loss'; }

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

fetch('/api/pending').then(r => r.json()).then(data => {
  if (!data.length) {
    document.getElementById('pending').innerHTML = '<p class="small">No open positions right now.</p>';
    return;
  }
  let html = '<table><tr><th>Placed</th><th>Strategy</th><th>Match</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Step</th></tr>';
  data.forEach(b => {
    html += `<tr>
      <td>${(b.placed_at || '').replace('T', ' ').slice(0, 16)}</td>
      <td>${b.strategy_name}</td>
      <td>${b.event_name}</td>
      <td>${b.selection_name}</td>
      <td>${b.odds}</td>
      <td>${b.stake}</td>
      <td>${b.step}</td>
    </tr>`;
  });
  html += '</table>';
  document.getElementById('pending').innerHTML = html;
});

fetch('/api/recent').then(r => r.json()).then(data => {
  let html = '<table><tr><th>Time</th><th>Strategy</th><th>Match</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Step</th><th>Result</th><th>Profit</th></tr>';
  data.forEach(b => {
    const resultClass = b.result === 'won' ? 'profit' : 'loss';
    html += `<tr>
      <td>${(b.placed_at || '').replace('T', ' ').slice(0, 16)}</td>
      <td>${b.strategy_name}</td>
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
        plugins: { legend: { display: false } },
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
  </div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const muted = '#7a8699';
const gridColor = '#1c2330';
const win = '#2dd4a8';
const loss = '#ff6b5e';
const accent = '#5b8def';
const palette = ['#5b8def', '#2dd4a8', '#f5b942', '#ff6b5e', '#a78bfa', '#38bdf8'];

const baseTicks = { color: muted, font: { family: 'JetBrains Mono', size: 11 } };
const baseGrid = { color: gridColor };

fetch('/api/chart_data').then(r => r.json()).then(data => {

  // 1. Cumulative profit line
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
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: baseGrid, ticks: { ...baseTicks, maxTicksLimit: 8, maxRotation: 0 } },
          y: { grid: baseGrid, ticks: baseTicks }
        }
      }
    });
  } else {
    document.getElementById('cumulativeChart').outerHTML = '<div class="empty">No settled bets yet</div>';
  }

  // 2. Win rate by odds bucket
  if (data.odds_buckets.length) {
    const labels = data.odds_buckets.map(b => b.bucket);
    const rates = data.odds_buckets.map(b => b.total ? Math.round(100 * b.won / b.total) : 0);
    new Chart(document.getElementById('oddsChart'), {
      type: 'bar',
      data: { labels, datasets: [{ data: rates, backgroundColor: win, borderRadius: 4 }] },
      options: {
        plugins: { legend: { display: false } },
        scales: { x: { grid: baseGrid, ticks: baseTicks }, y: { grid: baseGrid, ticks: baseTicks, max: 100 } }
      }
    });
  } else {
    document.getElementById('oddsChart').outerHTML = '<div class="empty">No settled bets yet</div>';
  }

  // 3. Market mix donut
  if (data.market_mix.length) {
    new Chart(document.getElementById('mixChart'), {
      type: 'doughnut',
      data: {
        labels: data.market_mix.map(m => m.strategy_name),
        datasets: [{ data: data.market_mix.map(m => m.total), backgroundColor: palette, borderWidth: 0 }]
      },
      options: { plugins: { legend: { position: 'bottom', labels: { color: muted, font: { size: 11 } } } } }
    });
  } else {
    document.getElementById('mixChart').outerHTML = '<div class="empty">No bets yet</div>';
  }

  // 4. Weekday activity
  if (data.weekday.length) {
    new Chart(document.getElementById('weekdayChart'), {
      type: 'bar',
      data: { labels: data.weekday.map(d => d.day), datasets: [{ data: data.weekday.map(d => d.total), backgroundColor: accent, borderRadius: 4 }] },
      options: { plugins: { legend: { display: false } }, scales: { x: { grid: baseGrid, ticks: baseTicks }, y: { grid: baseGrid, ticks: baseTicks } } }
    });
  } else {
    document.getElementById('weekdayChart').outerHTML = '<div class="empty">No bets yet</div>';
  }

  // 5. Stake vs profit scatter
  if (data.stake_vs_profit.length) {
    const points = data.stake_vs_profit.map(b => ({ x: b.stake, y: b.profit }));
    const colors = data.stake_vs_profit.map(b => b.result === 'won' ? win : loss);
    new Chart(document.getElementById('scatterChart'), {
      type: 'scatter',
      data: { datasets: [{ data: points, backgroundColor: colors, pointRadius: 5 }] },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { title: { display: true, text: 'Stake', color: muted }, grid: baseGrid, ticks: baseTicks },
          y: { title: { display: true, text: 'Profit', color: muted }, grid: baseGrid, ticks: baseTicks }
        }
      }
    });
  } else {
    document.getElementById('scatterChart').outerHTML = '<div class="empty">No settled bets yet</div>';
  }
});
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

    return jsonify({
        "cumulative": cumulative,
        "odds_buckets": odds_buckets,
        "weekday": weekday,
        "stake_vs_profit": stake_vs_profit,
        "market_mix": market_mix,
    })


@app.route("/api/pending")
@require_password
def pending():
    rows = query("""
        SELECT * FROM bets
        WHERE result IS NULL
        ORDER BY placed_at DESC
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
