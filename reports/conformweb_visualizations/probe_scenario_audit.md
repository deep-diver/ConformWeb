# ConformWeb Probe Scenario Audit

Date audited: 2026-08-31 Asia/Seoul

Scope: local workspace at `<repository-root>`, current branch `exp/missing-families-full-rerun`, plus retained ConformWeb submission/log bundles under `reports/conformweb_visualizations/archives/` and `reports/conformweb_neurips_submission_pack_20260526_161109.tar.gz`.

## Bottom Line

The retained code documents and implements probe scenarios, but the frozen benchmark YAML files available in this workspace do **not** contain 51 scenarios marked as probes. The current `targets/web` benchmark contains 756 scenarios, all scoring, and zero `kind: probe` entries. The retained paper inventory and raw-log bundles report 779 scoring scenarios and zero probes. Therefore the statement "807 total scenarios become 756 scoring scenarios by excluding 51 probes" is **not confirmed by the actual local YAML, compiler, evaluator, scoring code, inventory, or retained bundles**.

Follow-up reconciliation: the 51-scenario difference between an 807-scenario sample inventory and the current 756-scenario `targets/web` tree is exactly explained by missing scenario files, not by probe exclusion:

```text
Clinical A: sample public=6, private=17; current targets/web public=0, private=0; delta=23
Campus B:   sample public=12, private=14; current targets/web public=12, private=0; delta=14
Media B:    sample public=12, private=14; current targets/web public=12, private=0; delta=14
Total delta: 23 + 14 + 14 = 51
```

The retained `contract_pack/20260517/combined` contains the Clinical A files, bringing that pack to 779 scenarios, but it still lacks Campus B private and Media B private files. Local git refs contain Clinical A scenario files on the `codex/clinic-shift-tier-*` branches, but no local ref inspected contains `targets/web/campus_registrar_command/tier_b/scenarios.private.dsl.yaml` or `targets/web/media_campaign_launch_desk/tier_b/scenarios.private.dsl.yaml`.

## Findings

| Question | Actual value found | Evidence | Concise paper-safe summary |
|---|---:|---|---|
| What exactly makes a scenario a probe? | A scenario is a probe when its scenario metadata has `kind: probe`. If `kind` is omitted, compiler default is `scoring`. | `detoxbench/dsl/compiler.py:118`, `detoxbench/dsl/compiler.py:961-968`, `detoxbench/dsl/compiler.py:2238-2245`; package spec in `tools/package_conformweb_contracts.py:427-431`. | Probe/scoring status is an explicit scenario `kind`; absent `kind` means scoring. |
| Allowed kind values | `scoring` and `probe`. | `detoxbench/dsl/compiler.py:118`, `detoxbench/dsl/compiler.py:2238-2245`. | The compiler accepts only `scoring` or `probe`. |
| Probe weight policy | Probe weights may be nonnegative, including zero; scoring weights must be positive. | `detoxbench/dsl/compiler.py:2248-2262`; package spec in `tools/package_conformweb_contracts.py:427-431`; compiler fixture in `tests/test_dsl_compiler.py:2499-2523`. | Probe weights are parsed but do not contribute to formal score. |
| Why probes were created | To keep contract gaps, evaluator-overfit checks, ambiguous checks, and reference-only behavior out of formal score while preserving them as diagnostics for benchmark repair/stabilization. | `docs/philosophy.md:26-33`; `docs/evaluator-stabilization.md:87-102`, `docs/evaluator-stabilization.md:111-127`; `docs/maturity.md:256-266`. | Probes diagnose benchmark/evaluator problems rather than candidate conformance. |
| Role during construction/evaluation | They are reported diagnostically and surfaced separately in dashboards; they guide contract/evaluator/scenario fixes. | `docs/authoring.md:227-229`; `docs/maturity.md:204-229`; `detoxbench/dashboard_template.html:806-850`, `detoxbench/dashboard_template.html:1088`, `detoxbench/dashboard_template.html:1209-1211`; `detoxbench/dashboard.py:408-425`, `detoxbench/dashboard.py:536-541`. | Probe outcomes are visible diagnostics, not benchmark scores. |
| Why excluded from `S_scen`/formal score | Scorer increments `probe.passed/total` then immediately skips formal, stepwise, tier, difficulty, and capability aggregation for `kind == "probe"`. Scenario `score.possible` is `0.0` for probes. | `detoxbench/core/models.py:196-215`; `detoxbench/core/models.py:254-292`; `detoxbench/core/models.py:383-411`. | Probe scenarios are excluded by scorer control flow, not by post-hoc filtering. |
| Why excluded from `S_step` | Same scorer skip occurs before `stepwise_possible` and `stepwise_earned` are updated. | `detoxbench/core/models.py:254-286`; dashboard mirror in `detoxbench/dashboard.py:408-425`. | Stepwise progress is computed only over scoring scenarios. |
| Why excluded from full-pass | `RunResult.passed` checks only scenarios whose `kind` is `scoring`; a failed probe does not fail the run. | `detoxbench/core/models.py:234-237`; explicit regression tests in `tests/test_scoring.py:47-58`. | Full-pass ignores probe failures. |
| Public/private/either? | Code permits `visibility: public` or `private` independently of `kind`; docs describe public scenarios as examples/smoke/diagnostics and private scenarios as hidden scoring. No actual local benchmark probes exist, so observed probe visibility distribution is not recorded. | `detoxbench/dsl/compiler.py:118-119`, `detoxbench/dsl/compiler.py:2199-2201`; `tests/test_dsl_compiler.py:2502-2523`; `docs/release-governance.md:30-42`; `docs/authoring.md:168-174`. | Probe kind is orthogonal to public/private visibility in the schema; this workspace records no benchmark probes to classify. |
| Actual benchmark probe count in current `targets/web` | `0`. | YAML audit over `targets/web/*/tier_*/scenarios.{public,private}.dsl.yaml`: `files=44`, `scenarios=756`, `scoring=756`, `probe=0`, `explicit_kind=0`. `rg '^\\s*kind:'` over those files returned no matches. | The current target benchmark has 756 scoring scenarios and no marked probes. |
| Public/private current scenario count | Public 288, private 468, total 756. | YAML audit over `targets/web/*/tier_*/scenarios.{public,private}.dsl.yaml`. | Current scoring denominator is 756 scenarios, split 288 public and 468 private. |
| Retained paper inventory count | 779 scoring, 0 probe, total 779. | `reports/conformweb_visualizations/tables/appendix_benchmark_inventory.csv`; same file extracted from `reports/conformweb_neurips_submission_pack_20260526_161109.tar.gz`; same counts in raw-log bundles `conformweb_raw_logs_bundle_20260525_192459.tar.gz`, `...201848.tar.gz`, `...203025.tar.gz`. | Retained paper inventory conflicts with the current target-tree count but also records zero probes. |
| `807 -> 756` confirmation | Not recorded / not confirmed. | No `kind: probe` in current target YAML, no `scenarios.probe.dsl.yaml`, no git-ref hit for probe scenario files or `kind: probe` in target YAML, no submission-pack YAML `kind: probe`, and inventories report probe count zero. | Do not state 807 total or 51 probes unless another frozen artifact is supplied. |
| Alternative explanation for `807 -> 756` | Confirmed as a missing-file delta against the sample inventory: Clinical A contributes 23 missing scenarios; Campus B private contributes 14; Media B private contributes 14. | Current YAML audit over `targets/web`; retained `contract_pack/20260517/combined`; local ref audit for the three missing split paths. | The 51-scenario gap is a missing-split accounting issue, not a probe-scenario exclusion. |

## Count Reproduction

Current benchmark tree:

```text
source,files,scenarios,scoring,probe,explicit_kind
targets/web,44,756,756,0,0
```

Per current `targets/web` instance:

```text
campus_registrar_command_tier_a,public=14,private=10,scoring=24,probe=0
campus_registrar_command_tier_b,public=12,private=0,scoring=12,probe=0
campus_registrar_command_tier_c,public=12,private=17,scoring=29,probe=0
campus_registrar_command_tier_d,public=14,private=20,scoring=34,probe=0
clinic_shift_command_tier_b,public=9,private=24,scoring=33,probe=0
clinic_shift_command_tier_c,public=15,private=37,scoring=52,probe=0
clinic_shift_command_tier_d,public=16,private=39,scoring=55,probe=0
freshcart_market_tier_a,public=5,private=19,scoring=24,probe=0
freshcart_market_tier_b,public=5,private=24,scoring=29,probe=0
freshcart_market_tier_c,public=7,private=24,scoring=31,probe=0
freshcart_market_tier_d,public=8,private=26,scoring=34,probe=0
homefix_hub_tier_a,public=14,private=10,scoring=24,probe=0
homefix_hub_tier_b,public=16,private=13,scoring=29,probe=0
homefix_hub_tier_c,public=17,private=32,scoring=49,probe=0
homefix_hub_tier_d,public=18,private=46,scoring=64,probe=0
media_campaign_launch_desk_tier_a,public=14,private=10,scoring=24,probe=0
media_campaign_launch_desk_tier_b,public=12,private=0,scoring=12,probe=0
media_campaign_launch_desk_tier_c,public=24,private=20,scoring=44,probe=0
media_campaign_launch_desk_tier_d,public=20,private=28,scoring=48,probe=0
stayflow_concierge_tier_a,public=5,private=18,scoring=23,probe=0
stayflow_concierge_tier_b,public=10,private=19,scoring=29,probe=0
stayflow_concierge_tier_c,public=10,private=15,scoring=25,probe=0
stayflow_concierge_tier_d,public=11,private=17,scoring=28,probe=0
TOTAL,public=288,private=468,scoring=756,probe=0
```

Retained paper inventory:

```text
reports/conformweb_visualizations/tables/appendix_benchmark_inventory.csv:
rows=24, scoring=779, probe=0, total=779

reports/conformweb_neurips_submission_pack_20260526_161109.tar.gz:
rows=24, scoring=779, probe=0, total=779

reports/conformweb_visualizations/archives/conformweb_raw_logs_bundle_20260525_192459.tar.gz:
rows=24, scoring=779, probe=0, total=779

reports/conformweb_visualizations/archives/conformweb_raw_logs_bundle_20260525_201848.tar.gz:
rows=24, scoring=779, probe=0, total=779

reports/conformweb_visualizations/archives/conformweb_raw_logs_bundle_20260525_203025.tar.gz:
rows=24, scoring=779, probe=0, total=779
```

## Representative Examples

No representative **benchmark probe** scenarios can be provided from the frozen local YAML, because none are present.

Representative ordinary scoring scenarios:

| Scenario | Why it is scoring | Evidence |
|---|---|---|
| `public_01_filter_fruit_catalog` in FreshCart Tier A | It appears in `scenarios.public.dsl.yaml`; it has no `kind`, so compiler default is `scoring`; it checks public filter/table behavior. | `targets/web/freshcart_market/tier_a/scenarios.public.dsl.yaml:13-33`; default kind in `detoxbench/dsl/compiler.py:2238-2245`. |
| `private_02_math_override_then_enroll` in Campus Registrar Tier A | It appears in `scenarios.private.dsl.yaml`; it has no `kind`, so compiler default is `scoring`; it checks hidden action order and values within the public contract surface. | `targets/web/campus_registrar_command/tier_a/scenarios.private.dsl.yaml:31-48`; fairness rule in `docs/authoring.md:255-257`. |

Representative non-benchmark probe fixtures:

| Fixture | What it shows | Evidence |
|---|---|---|
| Compiler fixture with `kind: probe`, `visibility: public`, `weight: 0`, `description: Public diagnostic example` | The compiler preserves probe metadata and allows zero weight for probes. This is a unit-test fixture, not a frozen benchmark scenario. | `tests/test_dsl_compiler.py:2499-2523`. |
| Scoring fixture `probe_fail` with `weight=99.0` | Formal and stepwise possible remain based only on scoring scenarios; probe is reported as `probe: 0/1`. This is a unit-test fixture, not a frozen benchmark scenario. | `tests/test_scoring.py:11-44`. |
| Scoring fixture `diagnostic_gap` failing while `formal_ok` passes | A failed probe does not make `RunResult.passed` false. This is a unit-test fixture, not a frozen benchmark scenario. | `tests/test_scoring.py:47-58`. |

## Notes On `scenarios.probe.dsl.yaml`

The figure-pack inventory code contains a branch that would count `scenarios.probe.dsl.yaml` and `scenarios.validation.dsl.yaml` if those files existed:

- `tools/build_conformweb_figure_pack.py:327-342` counts public/private scenarios, then optional `scenarios.probe.dsl.yaml` and `scenarios.validation.dsl.yaml`.
- `tools/build_conformweb_figure_pack.py:422-426` writes `num_scoring_scenarios = public + private` and `num_probe_scenarios = probe`.

However:

- `detoxbench/dsl/scenario_sets.py:10-31` only auto-discovers `public`, `private`, or legacy `scenarios.dsl.yaml` for `--scenario-set all/public/private`.
- `detoxbench/core/models.py:272-276` excludes scenarios from scoring only when `scenario.kind == "probe"`.
- No `scenarios.probe.dsl.yaml` files are present in current `targets/web` or retained `contract_pack/20260517`.

Thus, a separate probe file would still need either explicit `kind: probe` metadata or a loader path that assigns probe kind before scoring. No such frozen file or loader behavior is recorded here.

## Reproduction Commands Used

```bash
rg -n '^\\s*kind:' targets/web/*/tier_*/scenarios*.dsl.yaml reports/conformweb_visualizations/contract_pack/20260517/combined/*/tier_*/scenarios*.dsl.yaml
rg --files targets/web reports/conformweb_visualizations/contract_pack/20260517 | rg 'scenarios\\.probe\\.dsl\\.yaml$|scenarios\\.validation\\.dsl\\.yaml$'
git for-each-ref --format='%(refname:short)' refs/heads refs/remotes
git grep -n -e 'kind:[[:space:]]*probe' "$ref" -- 'targets/web/*/tier_*/scenarios*.dsl.yaml'
git ls-tree -r --name-only "$ref" -- targets/web | rg 'scenarios\\.probe\\.dsl\\.yaml$'
tar -xOzf reports/conformweb_neurips_submission_pack_20260526_161109.tar.gz --wildcards '*scenarios*.dsl.yaml' | rg -n '^\\s*kind:|probe'
awk -F, 'NR>1{sc+=$15; pr+=$16; n++} END{print "rows=" n ", scoring=" sc ", probe=" pr ", total=" sc+pr}' reports/conformweb_visualizations/tables/appendix_benchmark_inventory.csv
```

The grep commands above returned no benchmark probe matches.
