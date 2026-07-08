import sqlite3

conn = sqlite3.connect("config/bets.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, strategy_name, event_name, league, result, result_type FROM bets ORDER BY id DESC LIMIT 20").fetchall()
for r in rows:
    print(dict(r))
conn.close()