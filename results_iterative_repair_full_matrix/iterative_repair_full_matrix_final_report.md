# Iterative Repair Full Matrix Final Summary

Generated: 2026-07-09T13:46:19+00:00

## Completion

| Scope | Round 0 records | Round 1 records (@2) | Round 2 records (@3) | Planned denominator |
|---|---:|---:|---:|---:|
| Included retained originals | 1650 | 1650 | 1650 | 2160 |
| Omitted cells counted as zero | 510 | 510 | 510 | 2160 |

The paper table keeps the requested fixed denominator: 60 per model-by-tier cell, 240 per model, 720 per capability band, and 2160 overall. A follow-up artifact audit found that the 510 omitted cells are not all missing source apps: 90 Clinic Shift Command Tier A source apps are retained, but the active target DSL files are absent from `targets/web/clinic_shift_command/tier_a` and only present in the contract-pack archive; the remaining 420 Campus/Media Tier A/B blind candidate apps were not located in the checkout, sibling worktrees, zip backup, or git objects. Omitted cells remain in the denominator as zero-credit cells. Stale pre-retry Gemini records in the non-Gemini root are excluded.

## Overall Fixed-Denominator Results

| Round | Full pass | S_scen | S_step | Included records |
|---|---:|---:|---:|---:|
| @1 | 252/2160 (11.7%) | 36.7% | 49.4% | 2160 |
| @2 | 185/2160 (8.6%) | 19.8% | 24.4% | 1650 |
| @3 | 252/2160 (11.7%) | 21.9% | 26.7% | 1650 |

## Capability Bands

| Group | @1 full pass | @2 full pass | @3 full pass | @1 S_step | @2 S_step | @3 S_step |
|---|---:|---:|---:|---:|---:|---:|
| Mini | 6/720 (0.8%) | 7/720 (1.0%) | 12/720 (1.7%) | 24.8% | 15.7% | 22.1% |
| Turbo | 72/720 (10.0%) | 43/720 (6.0%) | 52/720 (7.2%) | 43.9% | 17.7% | 17.7% |
| Frontier | 174/720 (24.2%) | 135/720 (18.8%) | 188/720 (26.1%) | 79.3% | 39.7% | 40.4% |

## Per-Model Full Pass

| Group | Model | @1 | @2 | @3 |
|---|---|---:|---:|---:|
| Mini | GPT-5.4 nano | 5/240 (2.1%) | 7/240 (2.9%) | 10/240 (4.2%) |
| Mini | Claude Haiku 4.5 | 1/240 (0.4%) | 0/240 (0.0%) | 2/240 (0.8%) |
| Mini | Gemini 3.1 Flash Lite | 0/240 (0.0%) | 0/240 (0.0%) | 0/240 (0.0%) |
| Turbo | GPT-5.4 mini | 3/240 (1.3%) | 0/240 (0.0%) | 1/240 (0.4%) |
| Turbo | Claude Sonnet 4.6 | 46/240 (19.2%) | 32/240 (13.3%) | 38/240 (15.8%) |
| Turbo | Gemini 3.1 Flash | 23/240 (9.6%) | 11/240 (4.6%) | 13/240 (5.4%) |
| Frontier | GPT-5.4 | 47/240 (19.6%) | 43/240 (17.9%) | 65/240 (27.1%) |
| Frontier | Claude Opus 4.6 | 69/240 (28.8%) | 47/240 (19.6%) | 57/240 (23.8%) |
| Frontier | Gemini 3.1 Pro Preview | 58/240 (24.2%) | 45/240 (18.8%) | 66/240 (27.5%) |

## Excluded Stale Records

| Root/Round/Provider | Records |
|---|---:|
| full_matrix_20260709:0:google | 102 |
| full_matrix_20260709:1:google | 102 |
| full_matrix_20260709:2:google | 4 |

## Updated Files

- `tables/main_model_tier_conformance.tex`
- `results_iterative_repair_full_matrix/fixed_denominator_final_snapshot_20260709T134619Z.json`
- `results_iterative_repair_full_matrix/iterative_repair_full_matrix_final_report.md`
