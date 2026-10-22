"""Tests the per-day performance reports on the analytics page.

Covers:
  /api/weekday_performance  - Mon..Sun breakdown (the day-of-week report)
  /api/daily_performance    - calendar-day breakdown

No bot, no network — just the dashboard against a read-only copy of the
bets database. Proves the aggregation reconciles with raw SQL: totals,
the won/lost/cash-out split, the strategy filter and the Athens-local
day boundaries.

Run:
    python3 test_performance_reports.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, "src")

import dashboard  # noqa: E402


DB_PATH = os.path.join(os.path.dirname(__file__), "config", "bets.db")


def raw(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def get(client, path, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.get(path + ("?" + q if q else ""))
    assert resp.status_code == 200, f"HTTP {resp.status_code}"
    return resp.get_json()


def check(title, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {title}{(' — ' + detail) if detail else ''}")
    assert cond, f"{title} {detail}"


def truth_totals():
    return raw("""
        SELECT COUNT(*) AS bets,
               ROUND(SUM(profit), 4) AS profit,
               ROUND(SUM(stake), 4) AS staked
        FROM bets WHERE result IS NOT NULL
    """)[0]


def truth_split():
    rows = raw("""
        SELECT result, result_type, COUNT(*) AS n
        FROM bets WHERE result IS NOT NULL
        GROUP BY result, result_type
    """)
    return {
        "won": sum(r["n"] for r in rows if r["result"] == "won"),
        "lost": sum(r["n"] for r in rows if r["result"] == "lost"),
        "cashed": sum(r["n"] for r in rows if r["result_type"] == "cashed_out"),
        "push": sum(r["n"] for r in rows if r["result"] == "push"),
    }


# ---------------------------------------------------------------------------
# Day of week report
# ---------------------------------------------------------------------------

def test_weekday_totals(client):
    print("\n[1] weekday report totals reconcile with raw SQL")
    data = get(client, "/api/weekday_performance")
    s = data["summary"]
    truth = truth_totals()

    check("bet count", s["bets"] == truth["bets"], f"{s['bets']} vs {truth['bets']}")
    check("profit", abs(s["profit"] - truth["profit"]) < 0.01, f"{s['profit']} vs {truth['profit']}")
    check("staked", abs(s["staked"] - truth["staked"]) < 0.05, f"{s['staked']} vs {truth['staked']}")

    summed = round(sum(w["profit"] for w in data["weekdays"]), 4)
    check("weekday rows sum to total profit", abs(summed - s["profit"]) < 0.01, f"{summed} vs {s['profit']}")

    counted = sum(w["bets"] for w in data["weekdays"])
    check("weekday rows account for every bet", counted == s["bets"], f"{counted} vs {s['bets']}")


def test_weekday_shape(client):
    print("\n[2] weekday report shape")
    data = get(client, "/api/weekday_performance")
    days = data["weekdays"]

    check("seven buckets", len(days) == 7, str(len(days)))
    check("Mon..Sun order", [d["name"] for d in days] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
          str([d["name"] for d in days]))
    check("weekday index starts at Mon", days[0]["weekday"] == 0 and days[-1]["weekday"] == 6)

    # each weekday's trading days must equal the number of distinct local dates
    # that fell on it
    from datetime import datetime
    counts = {}
    for r in raw("SELECT settled_at FROM bets WHERE result IS NOT NULL"):
        day = dashboard._local_day(r["settled_at"])
        if not day:
            continue
        wd = datetime.fromisoformat(day).weekday()
        counts[wd] = counts.get(wd, 0) | 0
        counts.setdefault(wd + 1000, set()).add(day)
    for d in days:
        expected = len(counts.get(d["weekday"] + 1000, set()))
        check(f"{d['name']} trading days", d["days"] == expected, f"{d['days']} vs {expected}")

    split = truth_split()
    check("won (includes cash-outs)", sum(d["won"] for d in days) == split["won"])
    check("lost", sum(d["lost"] for d in days) == split["lost"])
    check("cash-outs", sum(d["cashed_out"] for d in days) == split["cashed"])


def test_weekday_avg(client):
    print("\n[3] avg-per-day is consistent with the totals")
    data = get(client, "/api/weekday_performance")
    for d in data["weekdays"]:
        if d["days"] == 0:
            continue
        expected = round(d["profit"] / d["days"], 4)
        check(f"{d['name']} avg/day", abs(d["avg_profit"] - expected) < 0.001, f"{d['avg_profit']} vs {expected}")

    active = [d for d in data["weekdays"] if d["days"] > 0]
    if active:
        best = max(active, key=lambda d: d["avg_profit"])
        worst = min(active, key=lambda d: d["avg_profit"])
        check("best weekday reported", data["summary"]["best_day"]["name"] == best["name"],
              f"{data['summary']['best_day']['name']} vs {best['name']}")
        check("worst weekday reported", data["summary"]["worst_day"]["name"] == worst["name"],
              f"{data['summary']['worst_day']['name']} vs {worst['name']}")


def test_weekday_strategy_filter(client):
    print("\n[4] weekday report honours the strategy filter")
    names = [r["strategy_name"] for r in raw(
        "SELECT DISTINCT strategy_name FROM bets WHERE strategy_name IS NOT NULL ORDER BY strategy_name"
    )]
    assert names, "no strategies in the database"

    name = names[0]
    data = get(client, "/api/weekday_performance", strategy=name.replace(" ", "%20"))
    s = data["summary"]
    truth = raw("""
        SELECT COUNT(*) AS bets, ROUND(SUM(profit), 4) AS profit
        FROM bets WHERE result IS NOT NULL AND strategy_name = ?
    """, (name,))[0]

    check("filter echoed back", data["strategy"] == name, data["strategy"])
    check("bet count", s["bets"] == truth["bets"], f"{s['bets']} vs {truth['bets']}")
    check("profit", abs(s["profit"] - truth["profit"]) < 0.01, f"{s['profit']} vs {truth['profit']}")

    counted = sum(w["bets"] for w in data["weekdays"])
    check("filtered rows account for every bet", counted == s["bets"], f"{counted} vs {s['bets']}")


# ---------------------------------------------------------------------------
# Calendar day report
# ---------------------------------------------------------------------------

def test_daily_totals(client):
    print("\n[5] calendar-day report totals reconcile with raw SQL")
    data = get(client, "/api/daily_performance", days=0)
    s = data["summary"]
    truth = truth_totals()

    check("bet count", s["bets"] == truth["bets"], f"{s['bets']} vs {truth['bets']}")
    check("profit", abs(s["profit"] - truth["profit"]) < 0.01, f"{s['profit']} vs {truth['profit']}")
    check("staked", abs(s["staked"] - truth["staked"]) < 0.05, f"{s['staked']} vs {truth['staked']}")

    summed = round(sum(d["profit"] for d in data["days"]), 4)
    check("daily rows sum to total profit", abs(summed - s["profit"]) < 0.01, f"{summed} vs {s['profit']}")


def test_daily_shape(client):
    print("\n[6] calendar-day report shape")
    data = get(client, "/api/daily_performance", days=0)
    days = data["days"]

    check("rows are sorted ascending", all(days[i]["date"] < days[i + 1]["date"] for i in range(len(days) - 1)))
    check("no duplicate days", len({d["date"] for d in days}) == len(days))
    check("timezone reported", data["timezone"] == "Europe/Athens", data["timezone"])

    for days_n in (7, 30, 90):
        d = get(client, "/api/daily_performance", days=days_n)
        check(f"{days_n}D window has {days_n} calendar days",
              len(d["days"]) == days_n, f"got {len(d['days'])}")
        check(f"{days_n}D window ends today", d["days"][-1]["date"] == d["range"]["to"])


def test_daily_strategy_filter(client):
    print("\n[7] calendar-day report honours the strategy filter")
    names = [r["strategy_name"] for r in raw(
        "SELECT DISTINCT strategy_name FROM bets WHERE strategy_name IS NOT NULL ORDER BY strategy_name"
    )]
    name = names[0]
    data = get(client, "/api/daily_performance", days=0, strategy=name.replace(" ", "%20"))
    s = data["summary"]
    truth = raw("""
        SELECT COUNT(*) AS bets, ROUND(SUM(profit), 4) AS profit
        FROM bets WHERE result IS NOT NULL AND strategy_name = ?
    """, (name,))[0]

    check("filter echoed back", data["strategy"] == name, data["strategy"])
    check("bet count", s["bets"] == truth["bets"], f"{s['bets']} vs {truth['bets']}")
    check("profit", abs(s["profit"] - truth["profit"]) < 0.01, f"{s['profit']} vs {truth['profit']}")


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def test_bad_input(client):
    print("\n[8] bad input does not blow up")
    for path in ("/api/weekday_performance", "/api/daily_performance"):
        for qs in ("days=abc", "days=-5", "strategy=does_not_exist", "days=", "strategy="):
            resp = client.get(path + "?" + qs)
            check(f"{path}?{qs} -> 200", resp.status_code == 200, str(resp.status_code))
            body = resp.get_json()
            key = "weekdays" if "weekday" in path else "days"
            check(f"{path}?{qs} -> usable payload", isinstance(body.get(key), list))


def main():
    print("=" * 66)
    print("Performance reports — dashboard tests")
    print("=" * 66)
    client = dashboard.app.test_client()

    test_weekday_totals(client)
    test_weekday_shape(client)
    test_weekday_avg(client)
    test_weekday_strategy_filter(client)
    test_daily_totals(client)
    test_daily_shape(client)
    test_daily_strategy_filter(client)
    test_bad_input(client)

    print("\n" + "=" * 66)
    print("ALL TESTS PASSED")
    print("=" * 66)


if __name__ == "__main__":
    main()
