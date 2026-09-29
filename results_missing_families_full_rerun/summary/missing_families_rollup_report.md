# Missing Families Full Rerun Rollup

- Scope: Clinic Shift Command, Campus Registrar Command, Media Campaign Launch Desk.
- Strict metrics use expected-run denominators and assign zero score to failed or unevaluated runs.
- Repair feedback policy: public scenario first-failure feedback only; reported evaluation uses public + private scenarios.
- Public-feedback audit violations: 0.

## Completion

| Batch | Expected | Evaluated | Failed | Completed |
|---|---:|---:|---:|---:|
| static_blind_at1 | 1080 | 1046 | 34 | 1080 |
| public_feedback_repair_at1_at2_at3 | 3240 | 2904 | 323 | 3244 |
| backend_backed | 1080 | 1008 | 72 | 1080 |

Note: completion counts can exceed expected counts when retry/alias manifest records exist. The rollup tables below use the unique expected matrix cells from the summary CSVs.

## Missing-Family Public Feedback Trend

| Round | Full pass strict | S_scen strict | S_step strict | Full pass evaluated-only |
|---|---:|---:|---:|---:|
| @1 | 201/1080 (18.6%) | 43.0% | 51.7% | 201/1047 (19.2%) |
| @2 | 301/1080 (27.9%) | 50.3% | 57.9% | 301/920 (32.7%) |
| @3 | 344/1080 (31.9%) | 55.6% | 63.4% | 344/937 (36.7%) |

## Missing-Family Target Trend

| Target | @1 | @2 | @3 | S_scen @3 | S_step @3 |
|---|---:|---:|---:|---:|---:|
| Campus Registrar Command | 70/360 (19.4%) | 113/360 (31.4%) | 132/360 (36.7%) | 55.7% | 63.7% |
| Clinic Shift Command | 48/360 (13.3%) | 62/360 (17.2%) | 68/360 (18.9%) | 49.8% | 57.8% |
| Media Campaign Launch Desk | 83/360 (23.1%) | 126/360 (35.0%) | 144/360 (40.0%) | 61.4% | 68.7% |

## Static And Backend

| Batch | Full pass strict | S_scen strict | S_step strict | Evaluated | Failed |
|---|---:|---:|---:|---:|---:|
| Static blind @1 | 200/1080 (18.5%) | 42.8% | 51.5% | 1046 | 34 |
| Backend-backed | 169/1080 (15.6%) | 37.9% | 45.5% | 1008 | 72 |

## Combined Six-Family Public Feedback

| Round | Full pass strict | S_scen strict | S_step strict |
|---|---:|---:|---:|
| @1 | 249/2160 (11.5%) | 37.0% | 47.7% |
| @2 | 406/2160 (18.8%) | 44.0% | 53.7% |
| @3 | 505/2160 (23.4%) | 48.1% | 57.6% |
