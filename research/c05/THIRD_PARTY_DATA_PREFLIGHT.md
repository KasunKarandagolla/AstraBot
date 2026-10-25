# C05 historical data provider micro-preflight: Tardis.dev

**Decision: STOP pending owner/provider access clarification.** The first GET to Tardis's authoritative Binance Futures documentation was blocked by the environment's CONNECT tunnel. Per the task limit, I stopped provider checks immediately. This is an access blocker, not evidence that Tardis lacks the data. No Tardis documentation content, coverage claim, terms, sample, or price was verified.

## Sources checked

Local project sources reviewed:

- `research/c05/DATA_FEASIBILITY.md` — existing C04/C05 evidence and remaining historical gaps.
- `research/c05/PROSPECTIVE_SMOKE.md` — the prior observer probe and access limits.
- `src/astrabot/universe/eligibility.py` and `src/astrabot/data/models.py` — C02 inputs and readiness requirements.

Tardis source URLs supplied for this preflight:

| Source | Attempt/result |
|---|---|
| https://docs.tardis.dev/historical-data-details/binance-futures | One GET attempted; no HTTP response (`HTTP=000`), 0 response bytes, `curl: (56) CONNECT tunnel failed, response 403`. |
| https://docs.tardis.dev/downloadable-csv-files | Not requested: stopped after the first Tardis network-policy block. |
| https://docs.tardis.dev/faq/data | Not requested: stopped after the first Tardis network-policy block. |
| https://docs.tardis.dev/faq/billing-and-subscriptions | Not requested: stopped after the first Tardis network-policy block. |

This preflight made **1 bounded Tardis HTTP GET** and received **0 response-body bytes**. No sample, downloadable CSV, metadata endpoint, Binance API, or alternate host was queried. The 8-request / 4 MB limits were not approached. No retry or route change was made.

## Exchange/date/feed coverage matrix

The requested exchange is Tardis `binance-futures`; requested dates are UTC 2024-09-01 and 2024-10-01. There is no inspected provider response or original historical byte for any cell below.

| Exchange | Symbol | 2024-09-01 | 2024-10-01 |
|---|---|---|---|
| `binance-futures` | SOLUSDT | **NOT VERIFIED** | **NOT VERIFIED** |
| `binance-futures` | DOGEUSDT | **NOT VERIFIED** | **NOT VERIFIED** |

The local report's Binance archive checks are separate provider evidence: they found candidate HTTP object responses for some trade, funding, and depth archive paths, but those archives were not inspected. They do not verify Tardis availability, coverage, or terms.

| Requested Tardis feed | Availability for both symbols/dates | Units, timestamps, provenance, gaps, sampling, mappings |
|---|---|---|
| `book_ticker` | **NOT VERIFIED** | No Tardis documentation or sample inspected. |
| `quotes` | **NOT VERIFIED** | No Tardis documentation or sample inspected. |
| `book_snapshot_5` | **NOT VERIFIED** | No Tardis documentation or sample inspected. |
| `trades` | **NOT VERIFIED** | No Tardis documentation or sample inspected. |
| `derivative_ticker` | **NOT VERIFIED** | No Tardis documentation or sample inspected. |
| Historical OI quantity/value | **NOT VERIFIED** | No field definition, original value, unit, contract mapping, or sample inspected; units cannot be independently validated. |

Whether rows preserve exchange event time and provider-local capture time is **NOT VERIFIED**. Any provider-local timestamp, if later documented, would describe provider capture; it would not by itself establish when AstraBot could have received or acted on that row. Coverage gaps, exchange-specific symbol mapping, collection incidents, correction policy, and the cadence or sampling rule are also **NOT VERIFIED**.

## No-key access and cost

The applicable research-use terms, no-key sample policy, downloadable sample availability, and any attribution or redistribution requirements are **NOT VERIFIED** because the provider documentation request was blocked. No sample was downloaded, so no claim is made that samples are legally accessible without a key.

Whether the full September–October study window is free or paid, and any verifiable cost, are **UNKNOWN**. The billing FAQ was not fetched. No account, subscription, purchase, or payment credential was used.

## Effect on AstraBot's P3 evidence gate

The requested data could materially reduce gaps only if provider access and actual historical rows later confirm complete symbol/date coverage, documented units, usable source timestamps, and sufficient cadence/continuity. None of those properties is established by this micro-preflight. A coverage statement alone would remain a provider claim until selected original bytes and their schema/checksums were inspected.

Even if the listed feeds are later verified and acquired, the following C02/P3 requirements remain separate:

- Point-in-time instrument status and trading filters for the historical universe. Current metadata cannot establish historical effective state.
- C02's 60 consecutive one-minute spread samples and freshness/order checks; `book_ticker` or `quotes` could help only if their timestamp semantics and cadence satisfy the contract.
- Validated OI quantity-to-USDT-notional units and contract mapping. A `derivative_ticker` field name alone does not validate units.
- Verified point-in-time event/news clearance with original publication and capture times. Market feeds do not establish that required sources were checked and clear.
- Realistic IOC arrival, queue position, rejection/partial-fill behavior, latency, and stop execution. Trades or a depth snapshot do not prove AstraBot's actual fill probability or fills.
- Account-specific historical fees and complete feed continuity/correction evidence.

Accordingly, no economic replay, strategy qualification, or C05 GO is supported by the result here. P3 remains unqualified and `C05 = INSUFFICIENT_EVIDENCE`.

## Recommended decision

**STOP this Tardis-specific historical-data work pending owner/provider access clarification.** Confirm an approved way to read Tardis's documentation and research terms before scheduling another bounded check. If access is later authorized, predeclare the exact feed/date/symbol sample and checksum/byte cap before any sample GET. Do not purchase provider access in this task.

Project status remains unchanged: verified phase credit **45%**; T1/R1/B1 `RESEARCH_ONLY`; OpenBot, human-approval rules, risk limits, and C06–C09 roadmap unchanged.
