# S02 — Proposed source clocks and acceptance

Date: 2026-10-28 (Asia/Colombo). Base: `74007b2efd243e17bb6e8f65c193a028dc57b5c4`.
Branch: `codex/final-s02-source-contract-sol`. Status: **PROPOSED / research only**.
Tracking: [#22](https://github.com/KasunKarandagolla/AstraBot/issues/22),
[#18](https://github.com/KasunKarandagolla/AstraBot/issues/18).

**Decision: `SOURCE_CONTRACT_PARTIAL_BUT_IMPLEMENTABLE`.** The proposed clock,
typed adapters and read-only diagnostic can support Session 03 fail-closed
integration. Mandatory historical source facts remain unaccepted. Recommend
approval of this version for research evaluation only; production C02 v1 stays
unchanged. Hold new market-evidence spending, policy implementation and promotion.

Session 01's economic result is binding: PC2 v0.1 has 392 formations, 70
confirmations and two base survivors; FR2 has 361/3/0. PC2's target is already
at/behind its required confirmation boundary in 240 formations. Both remain
REVISE_BEFORE_IMPLEMENTATION. More feed data cannot fix that geometry. No target,
confirmation, stop, management, R0 result or reserved outcome is amended here.
Formal qualification remains 45%, P3 INSUFFICIENT_EVIDENCE, original T1/R1/B1
RESEARCH_ONLY; no positive after-cost expectancy has been established.

## Problem and reuse decision

C02 `universe/eligibility.py` requires 59 adjacent **raw event** deltas of exactly
60 seconds. Issue #22 reports 60 reconstructed minute slots but 2/59, 0/59 and
1/59 exact source-event intervals at 01:05, 08:05 and 16:05 on October 1. Those
are prior owner-agent observations, not S02 remeasurement. Exchange messages are
irregular; sampling cadence and event clocks describe different facts.

Reuse C01 Decimal/UTC/frozen contracts, C02 instrument IDs and spread formula,
C05-G header/time/Decimal/source-row hashing, and C05-H dated evidence/unit
validation. The existing `c05g.periodic-spread.v1` already supplies a useful
research boundary but uses strict `(endpoint-60s,endpoint]` windows, provider
arrival proxies and an iterator that removes duplicates/inverted clocks. S02
adds one bounded pure reducer and one offline command so rejected rows and
four clock meanings can be audited. It does not replace G/H, production
`scan_universe`, strategy reducers, C04 execution models, or C06 tools. No new
dependency, framework, queue, database, collector or agent architecture.

## Frozen proposed mathematical contract

Version `proposed.c02.sample-clock.v2.0.0`; wire envelope
`proposed.market-observation.v2.0.0`. Machine schemas and rules:
[`S02_SOURCE_CONTRACT.json`](../../research/p3/S02_SOURCE_CONTRACT.json).

All timestamps are explicitly UTC, with microsecond resolution. Raw CSV clocks
are integer epoch microseconds parsed without floats. For row r retain exchange
event e(r), provider arrival p(r), nullable genuinely observed owner receipt
o(r), immutable source digest/record ordinal/raw cells/row ID, exact Decimal
bid/ask and quantities, symbol, full venue/contract/settlement instrument ID,
source class and evidence scope. Generic field measurements have their own
nullable measured_at/available_at/evidence_id: an OI clock never inherits a
changing mark's clock. Retrieval time is neither provider nor owner history.

Let M=60 seconds, decision cutoff c, f=M floor(c/M), and endpoints
s_i=f-(59-i)M for i=0,...,59, traversed in increasing order. Only endpoints are
rounded. The cutoff itself, source clocks and prices are never rounded.

Before selection, reject mismatched source digest/class/scope/instrument,
raw-to-normalized mismatch, unknown exchange clock or unverified/fallback
exchange-time origin, e>p, e>o or p>o when those clocks are recorded,
nonpositive prices, ask<=bid, and negative size. Locked BBO is conservatively
invalid in this proposal; zero displayed quantity is retained but proves no
executable liquidity. Empty/malformed cells abort the strict file parser rather
than producing an empirical acceptance report.

Define availability predicate A(r,s):

- PROVIDER_HISTORY: p exists and p<=s.
- OWNER_RECEIPT: o exists, its reviewed receipt evidence reference exists,
  o<=s, and p<=s if p is recorded. Unknown provider arrival is not filled from o;
  a source format that requires p still must pass its own schema.

Provider mode establishes only conditional provider-history observability;
it cannot assert historical receipt by the owner's system. Missing original
publisher/clock provenance still blocks source acceptance even if the
mechanical predicate succeeds. A caller-supplied receipt reference is a typed
claim, not automatic external authentication: verify it against a pinned
original artifact before calling the reducer. No original owner receipts exist
for these historical CSVs and the command cannot create them.

For each endpoint, source-order/duplicate/conflict checks consider **only rows
known by that endpoint**. Sort offered references by immutable file ordinal,
row hash and serialized body to remove caller iteration-order dependence;
do not sort raw events to repair the source. Event/provider clocks below a prior
known high-water mark are quarantined. Same raw-row identity offered again is a
duplicate. Conflicting payloads at one source locator are quarantined. A native
identity means a reviewed venue/channel/session/update identifier; conflicting
payloads under that identity quarantine all currently known members. Later
contradictions never rewrite a prior endpoint.

Normalized CSV has no native update ID. Its conservative **observed-payload
fingerprint** is H(instrument, class, e, bid, bid size, ask, ask size), with exact
numeric equivalence (lexical zeros do not create new events). It excludes
arrival, filename and row ordinal. This cannot certify exchange sequence
uniqueness. Identical event payloads under different arrivals are duplicates;
the earliest source occurrence is canonical. Preserve source-row identity
separately using the existing C05-G dataset/digest/ordered-cell hash.

Let U_i be identities already selected at earlier endpoints. After the above
checks, E_i={r: A(r,s_i), 0<=s_i-e(r)<=M, identity(r) not in U_i}. If E_i is empty,
record MISSING_EVIDENCE when no event was observed in the inclusive age band,
or OBSERVED_REJECTED when the band has events but all are excluded. For nonempty
E_i choose lexicographic max(e,p-or-e,source ordinal,row ID); update U_i. Provider
arrival is the second tie-break only when present; its absence remains null in
the observation. No reassignment, interpolation, future backward-fill or event
reuse. Eligibility exclusions and source-clock regressions are not repaired.

Each slot returns the exact row and event identity, original clocks/bid/ask,
integer event age and machine exclusion counts. Every offered observation and
its final row audit remains in the result; `endpoint_reasons` independently
recomputes temporal reasons for any row/slot. Row reasons aggregate exclusions
encountered across endpoints: a selected row can correctly show EVENT_ALREADY_USED
at a later endpoint. Invalid, unused, stale and missing are not interchangeable.
Counts are explicitly per row, per slot or per exclusion membership.
Exclusion counters describe the retrospective offered-input audit, including
future/late offers; they must never become causal trading features. Only the
causally selected slot identities and prices enter the proposed spread statistic.

Only with 60 selected slots compute median((ask-bid)/((ask+bid)/2)) using local
Decimal precision 28, ROUND_HALF_EVEN and the original statistics.median operation. Preserve the
<=0.001 fraction (0.10%) threshold. Preserve the additional existing freshness
veto: c-e(last selected)<=60 seconds at the actual decision cutoff. Missing slots
produce null median and false. All other C02 vetoes remain outside this diagnostic
and unchanged. The strict-v1 comparison applies its event cadence/order/unique
and freshness/spread conditions to the **same selected immutable rows**; it is a
spread-only comparison, not execution of or eligibility under the full scanner.
A production-scanner regression also proves sampled_at does not bypass v1.

All results say `PROPOSED_C02_SAMPLE_CLOCK_V2_DIAGNOSTIC` and
`production_c02_eligibility=NOT_EVALUATED_UNCHANGED`. Input above 100,000 rows
aborts before a result; the CLI partitions only the four predeclared one-hour
source windows. Original source files remain the immutable full-day audit root.

## Alternatives evaluated without outcome-based tuning

| Choice | Consequence | Frozen recommendation |
|---|---|---|
| Exact adjacent raw-event 60s | Conflates exchange updates with sample cadence | Keep v1 for compatibility; do not use as proposed sample clock |
| Strict age<60s, G v1 | Disjoint event windows; exact left boundary excluded | Keep existing G version unchanged |
| Age<=60s plus distinct identity | Includes an exactly 60s-old first usable event; neighboring boundary cannot reuse it | Select for proposed v2; conservative freshness/no-reuse remain explicit |
| Wider age or reuse | Can create apparent coverage from a stale/repeated event | Reject; needs distinct future proposal, no threshold sweep here |
| Require owner receipt for all historical study | Accurately blocks owner-causal claims but discards separately evidenced provider history | Expose both modes with distinct claims; never substitute clocks |
| Latest arrival instead of latest event | Can select an older source state that arrived later | Use event-first with arrival/ordinal tie-breaks |
| Optimize assignment across all endpoints | Later observations can influence earlier choices | Reject; causal ascending greedy rule |

The age boundary is a versioned engineering choice, not calibrated on October
eligibility or policy outcomes. No alternative threshold search was run.

## Nine-source acceptance and Session 03 adapter contract

[`S02_SOURCE_ACCEPTANCE.json`](../../research/p3/S02_SOURCE_ACCEPTANCE.json)
is the single detailed matrix: native fields, units, timestamps, provenance,
coverage, validation tests, missingness, adapter map, conversions and A01–A10
readiness. **A–F,H PARTIAL; G,I UNVERIFIED; zero SOURCE_ACCEPTED.** The C05-I/M
local reports and originals are absent; use only their retained preflights,
issue #18 owner reports and explicit limitations. A documentation capability is
not an accepted historical record.

| Existing boundary | Session 03 implementation instruction |
|---|---|
| C02 `data/models.py`, `data/replay.py` | Keep models; wrap with MarketObservationV2 and nullable per-field clocks. Existing archive availability proxies remain labeled proxies. Do not map `ingested_at` to owner receipt when `ingestion_time_semantics=PROVIDER_ARRIVAL_PROXY`. |
| C05-G `historical_sources.py` | Reuse strict parsers/hash helpers. S02 quote adapter retains rows that G intentionally filters, including duplicate/inverted-clock evidence. Keep raw CSV class; native book_ticker timestamp origin defaults UNVERIFIED. |
| C05-G `historical_replay.py` | Retain existing version and outputs; proposed research calls use `source_clock.sample_bbo`. scanner_diagnostic/replay_diagnostic are aliases to that exact reducer; wire serialization cannot change selected identities. |
| C05-H `historical_evidence.py` | Require reviewed original artifacts/dated intervals/units/field clocks. Empty authentic manifest stays empty. Current metadata and provider best-effort history cannot populate 2024 gaps. |
| C04 `public_archive.py`, research/replay | Existing closed-candle clocks/fixed cohort remain limited. No dynamic-universe, order-flow or fill inference; original October evaluation stays unopened. |
| C05-J `research/integrated.py`, C06 research operator | Consume readiness/exclusion facts read-only; produce NO_TRADE on missing mandatory source facts. Diagnostic pass never becomes an executable candidate or qualified registry version. |

Date-effective conversion rules are settled in the matrix: half-open metadata
intervals cover both decision and observation; quantities use only reviewed
BASE_ASSET or CONTRACTS×dated base-per-contract; linear USDT notional is
sum(price×base). Unknown/inverse/quanto/mismatched settlement fails closed. OI
requires its own measurement and accepted aligned mark. Top-25 can support visible
partial depth only: full 0.20%-of-mid band coverage requires a known frontier
beyond both boundaries or independently proven full exhausted book, plus native
sequence/reset evidence. Displayed size never certifies executable fills.

A01–A10 dependency/readiness entries are complete in the matrix. Missing features
stay UNAVAILABLE/DEGRADED and veto dependent entries, without stopping independent
position protection. G freezes all eleven v1.5 event categories and preserves
section 4.4's explicitly unvalidated research defaults: verified high-impact
macro releases veto new approvals inclusively from 30 minutes before through
15 minutes after the confirmed time; causally known severe delisting/suspension/
incompatible-change or mapped security notices veto pending manual release.
Unlock/listing is event-risk/watchlist, not invented directional evidence;
rumors cannot manufacture a blackout. Coverage/outages, causal revisions and
symbol mapping still require original historical evidence. Unknown required
coverage/timing/category-specific interval means UNKNOWN, never CLEAR. Luna
receives these exact rules and must not invent additional windows or promote
the existing research examples to production policy.

## Evidence routes, costs and STOP decisions

Public documentation was inspected on 2026-10-28 via the browsing tool. No vendor
contact, account, paid request, raw source download or repeated blocked executor
probe occurred. Executor policy excludes Tardis; documentation inspection through
the available web tool does not establish executor download access.

**Historical:** the [provider coverage page](https://docs.tardis.dev/historical-data-details/binance-futures)
advertises USD-M history from 2019-11-17, native bookTicker/depth/ticker/markPrice,
REST-generated OI about every six seconds since May 2020, and first-of-month CSV
samples. Its generated depthSnapshot is a REST initial book, not a native WS
snapshot. [CSV schemas](https://docs.tardis.dev/downloadable-csv-files/data-types)
distinguish native book_ticker, L2-derived quotes/top-25 and changing normalized
derivative fields; timestamp fallback must be checked. These capability claims
do not verify exact SOLUSDT channel incidents/date continuity or original records.
The [metadata API](https://docs.tardis.dev/api/instruments-metadata-api) explicitly
limits completeness of non-multiplier change history. Thus even paid raw feeds
cannot automatically solve A/E/F/G/I.

[Billing documentation](https://docs.tardis.dev/faq/billing-and-subscriptions)
currently describes monthly history of four months, quarterly twelve months,
and yearly four years (Business yearly all available; invoicing has extensions).
An October 2026 monthly/quarterly start therefore does not cover October 2024
under those default windows; confirm exact plan and historical start date.
The [public pricing page](https://tardis.dev/#pricing) displayed Perpetuals
Solo/Professional/Business at $700/$1,000/$3,000 per month in the rendered table,
and a $300 minimum order. These are displayed monthly figures, **not an annual
quote**, not a narrow SOLUSDT quotation and not authorization to spend. Exact
annual amount/tax/selected-symbol price/rights are unknown; the earlier $350
proposal is not a verified current quote. Raw replay and metadata access differ
from CSV-only plan access. Do not multiply a monthly display into an actual offer.

[Terms last modified 2026-10-20](https://docs.tardis.dev/legal/terms-of-service)
provide internal permitted-use licensing and conditional continued use of lawfully
downloaded paid/free samples; external raw/sampled-data distribution is restricted.
Sampled tick records are not automatically unrestricted Derived Data. Hosted
assistant analysis is addressed, but foundation-model training/public model
redistribution is restricted. Confirm applicable customer users/cloud processing,
Binance licensor terms, original acquisition terms and secure retention before
external data transfer. Keep raw and detailed sampled records owner-local; publish
only permitted derived findings and hashes after rights review.

Cheapest immediate step: use **already lawfully held originals** with the pinned
Windows command, no new cash obligation. In one local offline run it can validate
schema/CRC/counts, clocks/age/duplicates and selected source identities. It cannot
recover native IDs, sequence gaps, OI measurement time, historical metadata or
owner arrival that were never retained. If an essential field is genuinely absent,
STOP that acceptance claim. Optional no-key first-of-month native-bookTicker/raw
sample requests are a later owner/rights/network decision, not performed here.

**Prospective:** owner-authorized capture could retain native messages, local
receipt, clock-sync uncertainty, snapshots/sequence resets, dated metadata and
outage logs. It still needs a news coverage source and later authentic execution
qualification. C05-M's host findings (retained summary only, original inspection
not available) lacked the proposed 500GB allocation, independent backup and
continuous operation. No collection is deployed; the 210-day programme remains
DEFERRED. If begun after separate approval on October 28, 210 uninterrupted days
would finish around May 26, 2027; outages/acceptance can extend that. New data
cannot recreate 2024 owner receipts or validate the frozen October policy split.

Storage planning, not an empirical capacity guarantee: the prior compressed
one-day files total 110,788,433 bytes for one symbol. A naive unchanged-rate
210-day extrapolation is 23.27GB per symbol, 162.86GB for seven, or 325.72GB for
two compressed copies of seven; native full-depth/raw channels, decompression,
indices, OS reserve and independent backups are additional and rates vary.
Do not revive a 500GB sufficiency claim from this sample. Historical bounded
verification needs the originals (~111MB) plus measured temporary disk/outputs;
a wider historical acquisition requires a provider byte inventory before budget.
Prospective host/power/network/storage/backup costs have no approved quote.

| Route | Obtainable evidence/calendar | Hard STOP |
|---|---|---|
| Existing local originals | Run now after PR review; no new session/purchase. Fixed one-day source-only diagnostic. | Hash/schema/count failure, unknown rights, no clock/unit artifact: keep claim unaccepted. |
| Licensed historical native feeds | Potentially quicker than months of capture after exact channel/date/rights quote; delivery and missing ancillary evidence unknown. | Missing native clock/units/history/rights, unaffordable total quote, or unchanged failed S01 economic gate. |
| Prospective continuous source capture | Only after separate host/backup/availability acceptance and owner authorization; calendar months. | Host readiness, capacity, backup/restore, 24/7 operation or source rights absent; no deployment now. |

Neither source route is currently accepted end-to-end. **HOLD new expenditure**;
source-independent Luna integration is useful now. Reconsider spending only after
a separately frozen economically coherent policy version and a small claim-specific
source test succeed, without opening reserved outcomes to tune it.

## No-obligation provider questions (owner may send later)

1. Can you confirm exact SOLUSDT Binance USD-M channel and instrument date coverage
   for the separately authorized research dates, including 2024-10-01? Supply
   incident/gap/disconnect/reconnect/correction inventory and an original sample
   for native bookTicker, depth plus snapshots, ticker, markPrice and raw OI polls.
2. Which fields are recorded native, generated REST records, forward-carried or
   L2-reconstructed? Preserve E, T, u/U/pu, original poll response measurement
   fields, request/receipt times and provider arrival. Where does timestamp fall
   back to arrival? Can you substantiate field-specific OI/mark timing?
3. Can you provide authoritative, date-effective SOLUSDT unit/multiplier/settlement,
   lifecycle and complete tick/lot/notional filter change evidence, not current
   metadata or best-effort changes? Which fields/history are unavailable?
4. What source clocks, precision, clock synchronization uncertainty and capture
   location apply in 2024? How are duplicates, sequence gaps, crossed books,
   resets, missing fields and later corrections represented in raw versus CSV?
5. Does reconstructed depth prove complete +/-0.20%-of-mid band coverage, and
   what truncation/frontier information exists? We do not request fill guarantees.
6. Which historical 24h quote-turnover and full active/delisted membership records
   are available? Do you provide historical news/publication/revision coverage?
   Explicitly identify feeds you do not provide; do not bundle unsupported claims.
7. Please provide a **nonbinding** narrow-date/symbol quote with exact total,
   currency, tax, billing obligation/renewal/cancellation, minimum order, history
   start/end, CSV versus raw replay/metadata entitlements, byte inventory and
   download limits. Can these dates be bought without an annual commitment?
8. Confirm rights for internal offline/hosted-assistant processing, secure backup,
   retention after access ends, collaborators/customer users, and publication of
   summary statistics/hashes versus sampled raw rows. Identify venue restrictions.
   No order, subscription, trial obligation or purchase is authorized by this inquiry.

## Four separate owner decisions

| Decision | Recommendation now | What approval would mean |
|---|---|---|
| Proposed C02 v2 research clock | Approve for research evaluation after independent PR review | Frozen typed contract/sampler only; a production migration is separately explicit |
| Data rights/spending/hosting | HOLD new spending and capture; verify existing files locally within existing rights | Any later purchase/transfer/host commitment needs exact scoped terms and budget |
| Revised PC2/FR2 version | HOLD pending distinct preregistered formulas and owner decision before Session 04 | No permission to implement v0.1 or silently alter frozen geometry |
| Strategy promotion | HOLD | Requires real source acceptance and economic/operational qualification; no relabeling |

Luna must not fabricate clocks/units/metadata/news/fills, deploy collection, buy
feeds, inspect October strategy outcomes, change C02 v1, implement PC2/FR2 v0.1,
change risk/stop/TP/12h rules, or add a writer/runtime. Exactly one future exchange
writer and owner-controlled one-use approval remain binding. The complete safe
integration allowlist and A01–A10 readiness map are machine-readable in the matrix.
The diagnostic report holds empirical results and reproduction; this ADR does not
duplicate them.
