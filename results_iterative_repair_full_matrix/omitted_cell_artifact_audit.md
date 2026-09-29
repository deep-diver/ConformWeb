# Omitted Cell Artifact Audit

Generated after the follow-up audit of the iterative repair matrix.

## Correction

The earlier wording "510 missing original app artifacts" was too broad. The completed repair run omitted 510 planned cells, but the causes are mixed:

| Cause | Cells | Details |
|---|---:|---|
| Retained source apps, inactive target DSL path | 90 | `clinic_shift_command/tier_a`, all 9 models x 10 seeds. The source apps exist under `targets/web/clinic_shift_command/tier_a/cohorts/*/20260513T003251Z_clinic_tiera_mtf_10x/candidates/*/r*`, but `contract.dsl.yaml` and `scenarios.public.dsl.yaml` are absent from the active target directory. Matching DSL files exist in `reports/conformweb_visualizations/contract_pack/20260517/combined/clinic_shift_command/tier_a/`. |
| Blind candidate apps not located | 420 | `campus_registrar_command/tier_a` 90, `campus_registrar_command/tier_b` 90, Campus Tier C/D Frontier 60, `media_campaign_launch_desk/tier_a` 90, and `media_campaign_launch_desk/tier_b` 90. Searches over the current checkout, sibling worktrees under `<local-worktree-root>`, `detoxbench.zip`, and `git rev-list --all --objects` did not locate matching blind candidate app directories with `index.html`, `styles.css`, and `app.js`. |

## Current Target App Directory Counts

The current checkout contains these app directories with the full `index.html` / `styles.css` / `app.js` file set:

| Target | Tier | App dirs |
|---|---:|---:|
| `campus_registrar_command` | C | 75 |
| `campus_registrar_command` | D | 76 |
| `clinic_shift_command` | A | 90 |
| `clinic_shift_command` | B | 180 |
| `clinic_shift_command` | C | 270 |
| `clinic_shift_command` | D | 90 |
| `media_campaign_launch_desk` | C | 122 |
| `media_campaign_launch_desk` | D | 90 |

## Search Scope Checked

- `targets/web/**/cohorts/**/candidates/**/r*/`
- `reports/conformweb_visualizations/archives/**`
- sibling worktrees: `detoxbench-campus-registrar`, `detoxbench-media-campaign`, `detoxbench-main-merge`
- zip listing: `<repository-root>.zip`
- git object paths: `git rev-list --all --objects`

## Implication

The fixed-denominator table is still numerically consistent with the completed run, but its note must say "omitted cells" rather than "missing original app artifacts." Clinic Shift Command Tier A can be added in a follow-up repair run by using the contract-pack DSL bundle as the evaluation target source.
