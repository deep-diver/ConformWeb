# ConformWeb

> **Do LLM-Generated Web Apps Behave Correctly? A Contract-Grounded Benchmark for Behavioral Conformance**

This repository contains the benchmark implementation, frozen experiment aggregates, reproducibility audits, and public presentation assets for ConformWeb.

## Release Status

The repository was refreshed on 2026-09-29 from the retained ConformWeb experiment workspace. See [`CURRENT_RELEASE.md`](CURRENT_RELEASE.md) for source provenance and known artifact boundaries.

The repository intentionally distinguishes two scenario inventories:

| Inventory | Public | Private | Scoring | Probe | Scope |
|---|---:|---:|---:|---:|---|
| Current `targets/web` tree | 288 | 468 | 756 | 0 | YAML files currently retained in the target tree |
| Retained primary-result inventory | 294 | 485 | 779 | 0 | May contract/result bundle associated with the retained primary aggregate |

The local artifacts do **not** support the claim that 807 scenarios were reduced to 756 by excluding 51 probes. The 51-scenario difference is a missing-file delta in the current target tree. See [`probe_scenario_audit.md`](reports/conformweb_visualizations/probe_scenario_audit.md) for the code and artifact audit, and [`current_target_scenario_inventory_756.csv`](reports/conformweb_visualizations/tables/current_target_scenario_inventory_756.csv) for the reproducible 6-by-4 inventory.

## Primary Results

The primary experiment uses a fixed `6 families x 4 tiers x 9 models x 10 repetitions = 2,160` grid.

| Metric | Value |
|---|---:|
| Planned and scored primary runs | 2,160 |
| Strict full-pass runs | 252 |
| Strict full-pass rate | 11.7% |
| Scenario-level conformance (`S_scen`) | 36.7% |
| Step-level progress (`S_step`) | 49.4% |

The complete accounting policy, provider identifiers, prompts, sampling settings, dates, hashes, runtime details, backend experiment, and repair rounds are documented in [`run_accounting_and_provenance_appendix.md`](reports/conformweb_visualizations/run_accounting_and_provenance_appendix.md). Values absent from retained code or artifacts are explicitly marked `not recorded`.

## Repository Structure

```text
.
|-- detoxbench/                         # Evaluator, compiler, browser bridge, scoring
|-- targets/web/                        # Current retained target contracts and scenarios
|-- reports/conformweb_visualizations/  # Primary aggregates, audits, tables, and figures
|-- results_backend_backed_target_apps/ # Compact backend-backed accounting artifacts
|-- results_iterative_repair_full_matrix/ # Repair runners and fixed-denominator snapshots
|-- results_missing_families_full_rerun/  # Final compact six-family repair summaries
|-- tools/                              # Generation, experiment, audit, and figure scripts
|-- tests/                              # Evaluator/compiler/scoring tests
|-- docs/                               # Benchmark design documentation
|-- PACK_MANIFEST.csv                   # Included-file sizes, hashes, and provenance classes
`-- EXCLUDED_PATTERNS.md                 # Deliberately omitted large or sensitive artifacts
```

## Benchmark Contract

Each populated tier may contain:

| Artifact | Description |
|---|---|
| `contract.dsl.yaml` | Public behavioral contract defining admissible actions, observations, and relations |
| `scenarios.public.dsl.yaml` | Disclosed representative workflows |
| `scenarios.private.dsl.yaml` | Hidden evaluation workflows grounded in the public contract |
| `reference_app/` | Reference implementation source |
| `cohorts/` | Compact batch-level metadata |

The contract DSL exposes actions (`AC`), observations (`OC`), and relations (`RC`). A private scenario is admissible only when its references resolve through the public contract. Public scenarios are examples and are used to derive repair feedback; they are not supplied to the initial app generator and are not formal `kind: probe` scenarios.

## Generation And Repair Prompts

- Static generation prompt: `tools/generate_blind_dsl_static_app.py`
- Backend-backed generation prompt: `tools/generate_blind_dsl_backend_app.py`
- Public-feedback repair prompt: `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py`
- Exact repair `{context}` and `{feedback}` audit: [`repair_context_feedback_audit.md`](reports/conformweb_visualizations/repair_context_feedback_audit.md)

## Poster Assets

Poster-ready actual screens and provenance figures are under [`poster_asset_pack_20260929_current756`](reports/conformweb_visualizations/poster_asset_pack_20260929_current756). This is the only intentional PNG exception in the compact public release.

## Setup

Requires Python 3.11+:

```bash
pip install -e ".[dev]"
playwright install chromium
pytest
```

## Rebuilding Tables And Figures

```bash
python tools/build_conformweb_figure_pack.py
python tools/build_conformweb_pair_figure.py
python tools/export_conformweb_figure_source_data.py
python tools/build_main_model_experiment_table.py
python tools/audit_private_admissibility.py
```

Large screenshot trees, generated candidates, per-run event logs, browser traces, aborted batches, and intermediate archives are not published. Compact aggregate CSV/JSON files and selected failure evidence are retained where needed for accounting or presentation.
