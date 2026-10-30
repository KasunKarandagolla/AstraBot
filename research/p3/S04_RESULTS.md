# S04 VT4 empirical development result

Exploratory genuine OHLCV. No fills, C02 admission or independent profitability.

Census `ae1fee4e10382106d8992b091946706137c76c597641263facf02ec12aa22c88`; evidence `84cb5afcca3190b323eb7a528462b68427a79be409a715b61c24589352a5c19c`.

| Month | Raw / diagnostic / primary | Base complete / days / symbols | Target / stop first | Exact pairs / days | Decision |
|---|---:|---:|---:|---:|---|
| 2024-08 | 522/376/122 | 4/3/4 | 1/2 | 2/2 | REJECT |

## 2024-08

Scenarios optimistic/base/stress: {'optimistic': 4, 'base': 4, 'stress': 2}. Gate checks: `{"base_fraction_at_least10pct": false, "complete_base_at_least20": false, "complete_days_at_least8": false, "complete_symbols_at_least4": true, "conservative_target_first_at_least35pct": false, "exact_matched_at_least50pct": true, "matched_event_days_at_least8": false, "nonnegative_12h_contrast": false, "positive_1h_contrast": true, "positive_4h_contrast": false, "positive_4h_day_deletion_lower": false}`.

| Horizon | Paired equal-day bps | Delete-one-day range |
|---|---:|---|
| 60m | 2.71478854604428055607444163 | ['-28.0779033006124312541114157', '33.50748039270099236626029896'] |
| 240m | -356.6632757073646655895600277 | ['-702.1936918834559407864035847', '-11.13285953127339039271647079'] |
| 720m | -558.7451042541812525737585011 | ['-1034.859724805267947208111511', '-82.63048370309455793940549126'] |

Modeled cashflow mean, ideal close reference (not actual net_R): `{'optimistic': '-0.1243585370455374464341683550', 'base': '-0.1657154359992267578470962637', 'stress': '-0.2264756278903068348341232396'}`.
Adverse entry survivors `{'0': 4, '0.025': 3, '0.05': 3}`; funding5/10bps `{'5': 4, '10': 3}`; extra stop0.10R 3.

| Arm | Complete | Target-first | 4h paired bps | Base cashflow mean |
|---|---:|---:|---:|---:|
| base | 4 | 1 | -356.6632757073646655895600277 | -0.1657154359992267578470962637 |
| rejected | 369 | 27 | -39.91001993566108596363920127 | -0.1648136948930929027526825233 |
| no_compression | 4 | 1 | -356.6632757073646655895600277 | -0.1657154359992267578470962637 |
| no_volume | 5 | 1 | -356.6632757073646655895600277 | 0.09594661121420028349681935924 |
| no_bias | 16 | 6 | -356.6632757073646655895600277 | 0.2806060561604200712242894184 |
| no_three_filters | 19 | 6 | -356.6632757073646655895600277 | 0.1911732472965594520242690813 |
| 2024-09 | 540/347/113 | 2/2/2 | 0/2 | 0/0 | REJECT |

## 2024-09

Scenarios optimistic/base/stress: {'optimistic': 2, 'base': 2, 'stress': 1}. Gate checks: `{"base_fraction_at_least10pct": false, "complete_base_at_least20": false, "complete_days_at_least8": false, "complete_symbols_at_least4": false, "conservative_target_first_at_least35pct": false, "exact_matched_at_least50pct": false, "matched_event_days_at_least8": false, "nonnegative_12h_contrast": false, "positive_1h_contrast": false, "positive_4h_contrast": false, "positive_4h_day_deletion_lower": false}`.

| Horizon | Paired equal-day bps | Delete-one-day range |
|---|---:|---|
| 60m | None | None |
| 240m | None | None |
| 720m | None | None |

Modeled cashflow mean, ideal close reference (not actual net_R): `{'optimistic': '-1', 'base': '-1', 'stress': '-1'}`.
Adverse entry survivors `{'0': 2, '0.025': 2, '0.05': 2}`; funding5/10bps `{'5': 2, '10': 2}`; extra stop0.10R 2.

| Arm | Complete | Target-first | 4h paired bps | Base cashflow mean |
|---|---:|---:|---:|---:|
| base | 2 | 0 | None | -1 |
| rejected | 337 | 20 | -11.17814348150609783844164158 | -0.07131021696195336368856709114 |
| no_compression | 2 | 0 | None | -1 |
| no_volume | 3 | 0 | None | -1 |
| no_bias | 14 | 0 | None | -0.4175931171134451759212172700 |
| no_three_filters | 18 | 0 | None | -0.3507596409801138677468165368 |

See S04_OWNER_DECISION.md and S04_SESSION05_CONTRACT.json for decision, source and implementation gates.

```sh
python scripts/s04_economic_rescue.py --data-root /workspace/work/c04-data --output-dir work/s04-reproduction
```
