# ConformWeb Poster Asset Pack (Current Frozen 756)

This pack contains poster-ready actual browser screens and contract/private-scenario provenance figures.

## Ready-to-use assets

1. `ready_to_use/01_campus_family_complexity_a_to_d.png`
   Actual target-reference screens for one family across Tier A-D. Suggested overlay: state paths 27 -> 44 -> 64 -> 84; pages 3 -> 4 -> 5 -> 6; roles 2 -> 4 -> 5 -> 6.
2. `ready_to_use/02_public_contract_private_scenario_coverage_current756.png`
   Recomputed for the current frozen target tree only: 288 public + 468 private = 756 scenarios. Clinical A fallback is excluded.
3. `ready_to_use/03_homefix_private_journey_actual_screens.png`
   Four actual browser frames from a passing hidden scenario, aligned to public routes, actions, and state paths.
4. `ready_to_use/04_private_step_public_declaration_witness.png`
   Step-by-step mapping from a private journey to public declarations and compiled checks.
5. `ready_to_use/05_failure_before_after_example.png`
   Actual before/after failure evidence with expected/observed annotations.

## Audit scope

- Private files: 21
- Private scenarios: 468
- Private steps: 4239
- Compiled preconditions/checks: 40175
- Compile errors: 0

Correct poster claim: `Refs(private scenarios) subset-of Declarations(public contract)`. There is no separate private contract. Public scenario examples are disclosed generation inputs but are not exhaustive; private scenarios remain hidden from candidate generation.

## Additional choices

- `alternatives/family_rows/`: all six A-D family composites.
- `alternatives/failure_evidence/`: all 39 retained annotated failure panels.
- `source_screens/`: the four unannotated HomeFix frames used in the journey panel.
- `data/coverage_current756.csv`: counts behind the recomputed coverage figure.
- `manifest.csv`: SHA-256, byte size, and source/provenance note for every packaged file.

## Primary provenance

- `targets/web/homefix_hub/tier_c/contract.dsl.yaml`
- `targets/web/homefix_hub/tier_c/scenarios.private.dsl.yaml`
- `targets/web/homefix_hub/tier_c/cohorts/T/20260514_homefix_cd_recalibrated2_f_10x/runs/claude_sonnet46/r08/20260514-120945-96a346d8/summary.json`
- `reports/conformweb_visualizations/tables/private_reference_coverage.csv`
- `reports/conformweb_visualizations/tables/private_admissibility_audit.csv`
