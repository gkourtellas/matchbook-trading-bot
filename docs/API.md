# API reference

This project uses the Matchbook REST API via `MatchbookClient` in `src/api_client.py`. Official documentation: [Matchbook Developers](https://developers.matchbook.com/).

## Base URLs

| Purpose | URL |
|---------|-----|
| Authentication | `https://api.matchbook.com/bpapi/rest/security/session` |
| Edge API | `https://api.matchbook.com/edge/rest` |

After login, requests include header `session-token: <token>` plus:

```
content-type: application/json;charset=UTF-8
accept: application/json
```

## Class: `MatchbookClient`

### Constructor

Reads from environment:

- `MATCHBOOK_USERNAME`, `MATCHBOOK_PASSWORD`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional)

### `login()`

- **Method:** `POST` to auth URL
- **Body:** `{ "username", "password" }`
- **Success:** Stores `session-token` in `self.headers`; sends Telegram success message
- **Returns:** `True` / `False`

### `get_navigation()`

- **GET** `{base_url}/navigation`
- **Returns:** JSON hierarchy or `None`
- **401:** Re-login and retry once

Not used by the current strategy loop.

### `get_live_events(sport_ids, per_page=20)`

- **GET** `{base_url}/events`
- **Query params:** `sport-ids`, `states=open`, `include-prices=true`, `price-depth=3`, `price-mode=expanded`, `odds-type=DECIMAL`, `exchange-type=back-lay`, `per-page`
- **Returns:** Events JSON or `None`
- **401:** Re-login and retry once

Available on the client; the strategy uses its own `/events` request with `price-depth=1` and `per-page=30`.

### `submit_order(runner_id, side, odds, stake)`

- **POST** `{base_url}/v2/offers`
- **Body:**

```json
{
  "odds-type": "DECIMAL",
  "exchange-type": "back-lay",
  "offers": [
    {
      "runner-id": "<id>",
      "side": "back",
      "odds": 1.5,
      "stake": 0.10
    }
  ]
}
```

- **Success:** HTTP 200/201, returns response JSON
- **Failure:** Logs status and body; returns `None`
- **401:** Re-login and retry once

### `get_order_status(offer_id)`

- **GET** `{base_url}/v2/offers/{offer_id}`
- **Returns:** Offer JSON (includes `status`, `settled-items`) or `None`
- **401:** Re-login and retry once

Settlement logic in the strategy checks `status` for `SETTLED` / `FLUSHED` and `settled-items[].profit-loss`.

### `send_telegram(message)`

- **POST** `https://api.telegram.org/bot{token}/sendMessage`
- **Body:** `{ "chat_id", "text" }`
- No-op if token or chat ID is missing; exceptions are swallowed

---

## Strategy direct API usage

`strategy_one.py` also calls the events endpoint directly:

```
GET https://api.matchbook.com/edge/rest/events
```

**Query parameters (scan loop):**

| Parameter | Value |
|-----------|-------|
| `sport-ids` | `15` |
| `states` | `open` |
| `include-prices` | `true` |
| `price-depth` | `1` |
| `price-mode` | `expanded` |
| `odds-type` | `DECIMAL` |
| `exchange-type` | `back-lay` |
| `per-page` | `30` |

**Settlement fallback check:**

```
GET .../events?sport-ids=15&states=open
```

Compares whether the bet’s event name still appears in the open list.

---

## Error handling pattern

Most client methods:

1. Attempt request with session headers
2. On **401**, call `login()` and retry the same request once
3. On other errors, log/print and return `None`

The strategy does not always use the client wrapper for event fetches; those calls do not auto-retry on 401 unless you add that logic.

---

## Related docs

- [STRATEGY.md](STRATEGY.md) — how endpoints are used in the betting loop
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — auth and order errors
