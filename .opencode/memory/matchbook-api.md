---
name: matchbook-api
description: The Matchbook REST endpoints that actually work, learned by probing the live account
metadata:
  type: reference
---

Verified against the live account on 2026-10-22. Base: `https://api.matchbook.com`

**Login** — `POST /bpapi/rest/security/session` with `{"username","password"}` -> `session-token`.
Send it back as the `session-token` header.

**Read**
- `GET /edge/rest/lookups/sports` — sport ids. Horse Racing = `24735152712200`
- `GET /edge/rest/events?sport-ids=..&states=open&include-prices=true&price-mode=expanded&odds-type=DECIMAL&exchange-type=back-lay`
- `GET /edge/rest/events/{event_id}/markets/{market_id}/runners/{runner_id}/prices` — live price ladder
- `GET /edge/rest/account` — balance, currency, commission-type
- `GET /edge/rest/account/balance` — balance / free-funds / exposure
- `GET /edge/rest/v2/offers` — open offers (this is the orders list, NOT /edge/rest/orders)

**Write (money)**
- `POST /edge/rest/v2/offers` with
  `{"odds-type":"DECIMAL","exchange-type":"back-lay","offers":[{"runner-id":..,"side":"back","odds":..,"stake":..}]}`
  -> `{"offers":[{"id":..,"status":"matched",...}]}`

**Settlement**
- `GET /edge/rest/reports/v2/bets/settled?sport-ids=..&per-page=500` -> `markets[].selections[].bets[]`
  each bet has `offer-id`, `result` (WIN/LOSE/PUSH/VOID), `odds`, `net-profit-and-loss`.
  The `after` param needs a full timestamp `2026-10-22T07:46:31.000Z`, not a plain date.

**Dead ends (404)**: `/edge/rest/orders`, `/edge/rest/transactions`, `/edge/rest/positions`,
`/edge/rest/runner/{id}/prices`, `/edge/rest/markets/{id}`, `/edge/rest/events/{id}`,
`/edge/rest/users/{id}`, `/edge/rest/globals`, `/edge/rest/orders/statuses`.
`/bpapi/rest/orders` is 403.

**Account**: username `nintza13`, EUR, country CY, commission-type VOLUME on the account but
per-offer `NET_WIN` with 4% originator + 4% acceptor rate.
