"""Simple dashboard. Run this separately from the bot.

    python dashboard.py

Then open http://localhost:8050 in your browser.
Reads config/bets.db — does not touch the bot or place any bets.
"""

import os
import sqlite3
from flask import Flask, jsonify, render_template_string

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "bets.db")

app = Flask(__name__)

PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Bet Dashboard</title>
<style>
  body { font-family: -apple-system, Arial, sans-serif; background: #111; color: #eee; padding: 20px; }
  h1 { font-size: 20px; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 30px; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #333; }
  th { color: #999; font-weight: normal; font-size: 13px; }
  .profit { color: #4caf50; }
  .loss { color: #f44336; }
  .card { background: #1c1c1c; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
</style>
</head>
<body>
  <h1>Strategy Performance</h1>
  <div id="summary"></div>

  <h1>Step Frequency</h1>
  <div id="steps"></div>

  <h1>Recent Bets</h1>
  <div id="recent"></div>

<script>
function fmt(n) { return (n >= 0 ? '+' : '') + n.toFixed(2); }
function cls(n) { return n >= 0 ? 'profit' : 'loss'; }

fetch('/api/summary').then(r => r.json()).then(data => {
  let html = '<table><tr><th>Strategy</th><th>Bets</th><th>Won</th><th>Lost</th><th>Win %</th><th>Profit</th></tr>';
  data.forEach(s => {
    html += `<tr>
      <td>${s.strategy_name}</td>
      <td>${s.total}</td>
      <td>${s.won}</td>
      <td>${s.lost}</td>
      <td>${s.win_rate}%</td>
      <td class="${cls(s.profit)}">${fmt(s.profit)}</td>
    </tr>`;
  });
  html += '</table>';
  document.getElementById('summary').innerHTML = html;
});

fetch('/api/steps').then(r => r.json()).then(data => {
  let html = '<table><tr><th>Strategy</th><th>Step</th><th>Times Reached</th></tr>';
  data.forEach(s => {
    html += `<tr><td>${s.strategy_name}</td><td>${s.step}</td><td>${s.count}</td></tr>`;
  });
  html += '</table>';
  document.getElementById('steps').innerHTML = html;
});

fetch('/api/recent').then(r => r.json()).then(data => {
  let html = '<table><tr><th>Time</th><th>Strategy</th><th>Match</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Step</th><th>Result</th><th>Profit</th></tr>';
  data.forEach(b => {
    html += `<tr>
      <td>${(b.placed_at || '').replace('T', ' ').slice(0, 16)}</td>
      <td>${b.strategy_name}</td>
      <td>${b.event_name}</td>
      <td>${b.selection_name}</td>
      <td>${b.odds}</td>
      <td>${b.stake}</td>
      <td>${b.step}</td>
      <td>${b.result || 'pending'}</td>
      <td class="${cls(b.profit || 0)}">${b.profit != null ? fmt(b.profit) : '-'}</td>
    </tr>`;
  });
  html += '</table>';
  document.getElementById('recent').innerHTML = html;
});
</script>
</body>
</html>
"""


def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.route("/")
def home():
    return render_template_string(PAGE)


@app.route("/api/summary")
def summary():
    rows = query("""
        SELECT strategy_name,
               COUNT(*) as total,
               SUM(CASE WHEN result = 'won' THEN 1 ELSE 0 END) as won,
               SUM(CASE WHEN result = 'lost' THEN 1 ELSE 0 END) as lost,
               COALESCE(SUM(profit), 0) as profit
        FROM bets
        WHERE result IS NOT NULL
        GROUP BY strategy_name
        ORDER BY strategy_name
    """)
    for r in rows:
        settled = r["won"] + r["lost"]
        r["win_rate"] = round(100 * r["won"] / settled, 1) if settled else 0
    return jsonify(rows)


@app.route("/api/steps")
def steps():
    rows = query("""
        SELECT strategy_name, step, COUNT(*) as count
        FROM bets
        GROUP BY strategy_name, step
        ORDER BY strategy_name, step
    """)
    return jsonify(rows)


@app.route("/api/recent")
def recent():
    rows = query("""
        SELECT * FROM bets
        ORDER BY placed_at DESC
        LIMIT 50
    """)
    return jsonify(rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050)
