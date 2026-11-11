# Energy Audit

Know what every machine costs you, and where the savings are. Built for factories, companies and government facilities.

## Run it

    python app.py                  # http://127.0.0.1:8000
    python app.py 0.0.0.0 8080     # share on a company network

No installs needed (Python 3.8+ standard library only).

## Run the tests

    python -m unittest -v test_core

## What it does

- Machine register: power, quantity, hours/day, load factor, days/month
- Grid tariff plus diesel generator mix, with a true blended cost per kWh
- Cost per machine, yearly cost, connected load (kW), diesel litres, CO2
- What-if scenario: efficiency upgrades and solar share, with monthly and yearly savings
- Export CSV (formula-injection safe), print-ready report, save and open audit files
- Input validation on every field; server never leaks internal errors

## Files

| File | Purpose |
|---|---|
| `energy_core.py` | Calculation engine and validation |
| `app.py` | Local web server and JSON API (`/api/calculate`, `/api/export.csv`) |
| `index.html` | Dashboard interface |
| `test_core.py` | Engine and server tests |

## Notes on defaults

Tariff (209.5), diesel price (1200), kWh per litre (3.0) and CO2 factors are placeholders. Replace them with figures from your latest bill and fuel receipts before presenting results.

## Roadmap to make it sellable

1. Multi-site and multi-user accounts with login (for company groups and ministries)
2. Tariff bands and time-of-use pricing, plus demand charges for large industrial users
3. Import meter or smart-meter readings (CSV) to compare estimates against measured data
4. Database storage and audit history, so users can track savings month by month
5. PDF report with company branding, for boards and funders
6. Solar and battery sizing from the connected-load and hours data already collected
7. Aggregated dashboards for government: compare facilities, sectors and regions
