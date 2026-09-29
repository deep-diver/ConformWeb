# Repair Context And Feedback Audit

This note audits the `{context}` and `{feedback}` fields inserted into `REPAIR_PROMPT` for the retained public-feedback repair experiments. It uses only the repair runner code and retained patch/round metadata in the local repository.

## Scope

| Item | Actual value | Evidence |
|---|---|---|
| Public-feedback repair runner | `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py` | `REPAIR_PROMPT` at `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:88-146`; prompt formatting at `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:839-861`. |
| Final public-feedback repair artifact audited | `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3` | Retained patch metadata under `runs/*/tier_*/*/seed_*/apps/round_*/patch_metadata.json`; retained round records under `runs/*/tier_*/*/seed_*/records/round_*.json`. |
| Legacy repair artifact caveat | `results_iterative_repair_full_matrix/full_matrix_20260709` and `full_matrix_20260709_gemini_retry_partial` are legacy repair roots; their patch metadata does not record `feedback_source_scenario_set` and includes private scenario IDs in some feedback. | Local audit found 109 private scenario IDs in `full_matrix_20260709` patch metadata and 60 in `full_matrix_20260709_gemini_retry_partial` patch metadata. These are not treated here as the final public-feedback repair artifact. |

## `{context}` Structure

The exact context object inserted into `REPAIR_PROMPT` is:

```json
{
  "family": "<task family slug>",
  "tier": "<target tier>",
  "instance": "<family>/tier_<lowercase tier>",
  "seed": <integer generation seed>,
  "repair_round": <1 or 2>,
  "model": "<provider requested model id>",
  "model_slug": "<local model slot slug>",
  "model_tier": "<M, T, or F>"
}
```

| Field | Source in runner | Evaluator-derived? | Notes |
|---|---|---:|---|
| `family` | `task["family"]` | No | Target family slug. |
| `tier` | `task["tier"]` | No | Target tier A-D. |
| `instance` | `task["instance"]`; constructed as `f"{family}/tier_{tier.lower()}"` | No | Instance identity string from target metadata. |
| `seed` | `task["seed"]` | No | Experimental replicate ID, not a provider sampling seed. |
| `repair_round` | `repair_round` function argument | No | `1` for Repair 1, `2` for Repair 2. |
| `model` | `task["model"]` | No | Provider requested model identifier. |
| `model_slug` | `task["model_slug"]` | No | Local model slot slug. |
| `model_tier` | `task["model_tier"]` | No | Capability band label. |

Evidence: target `instance` construction in `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:275-297`; context construction in `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:842-851`; prompt insertion by `json.dumps(context, ensure_ascii=False, indent=2)` in `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:852-860`.

## `{context}` Audit Findings

| Question | Finding | Evidence |
|---|---|---|
| Does `{context}` contain only public/run metadata? | Yes. It contains only target identity, replicate seed, repair round, and model identity fields. | Context construction uses only `task[...]` fields and `repair_round`: `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:842-851`. |
| Does `{context}` contain evaluator-derived data? | No. It does not include scenario IDs, scores, assertions, expected/observed values, screenshots, trace paths, or result summaries. | Exact context keys above; prompt formatting separates `context` from `feedback`: `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:852-860`. |
| Does `{context}` differ between Repair 1 and Repair 2? | The key set is identical. For the same task, the only context field that changes is `repair_round` (`1` vs `2`). Across tasks, family/tier/instance/seed/model fields differ by design. | Context construction is fixed in code; local reconstruction from 1,448 final missing-family patch records found one key set and zero null values. |
| Does `{context}` contain private scenario identifiers or hidden evaluation artifacts? | No. There is no field capable of carrying scenario identifier, private result, expected value, trace, screenshot, or hidden artifact path. | Exact context keys in code; final missing-family patch metadata audit found zero `private_` strings in 1,448 patch metadata files. |
| Is `{context}` serialized in retained `patch_metadata.json`? | No. The full context object is not stored as a `context` field. The same run/task identity values are retained in `records/round_*.json`, and model/round values are retained in `patch_metadata.json`. | Sample round record: `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/campus_registrar_command/tier_c/gpt54/seed_01/records/round_1.json`; sample patch metadata: `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/campus_registrar_command/tier_c/gpt54/seed_01/apps/round_1/patch_metadata.json:1-39`. |

## Representative `{context}` Example

This example is reconstructed from the runner's exact context construction for the retained task whose round record and patch metadata are stored at:

- `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/campus_registrar_command/tier_c/gpt54/seed_01/records/round_1.json`
- `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/campus_registrar_command/tier_c/gpt54/seed_01/apps/round_1/patch_metadata.json`

```json
{
  "family": "campus_registrar_command",
  "tier": "C",
  "instance": "campus_registrar_command/tier_c",
  "seed": 1,
  "repair_round": 1,
  "model": "gpt-5.4",
  "model_slug": "gpt54",
  "model_tier": "F"
}
```

For Repair 2 of the same task, the context key set is the same and `repair_round` becomes `2`; the source app files and feedback may differ, but `source_app` is not part of `{context}`.

## `{feedback}` Schema

The exact feedback object passed into `REPAIR_PROMPT` is produced by `summarize_first_failure(summary)`:

```json
{
  "scenario_id": "<public scenario id or null>",
  "scenario_tier": "<scenario tier>",
  "first_failed_step": <integer or null>,
  "failed_action": "<action or null>",
  "failed_component": "<component id or null>",
  "failed_assertion": "<assertion type>",
  "expected_value": "<scalar, list, dict, or null>",
  "observed_value": "<scalar, list, dict, or null>",
  "message": "<failure message>",
  "failure_category": "<failure category>",
  "scenario_set": "public"
}
```

| Field | Source in runner |
|---|---|
| `scenario_id` | `failed.get("id")` |
| `scenario_tier` | `failed.get("tier")` |
| `first_failed_step` | `failed.get("first_failed_step") or first_failure.get("step_index")` |
| `failed_action` | `assertion.get("action")` |
| `failed_component` | `assertion.get("component")` |
| `failed_assertion` | `assertion.get("assertion_type") or assertion.get("type") or assertion.get("kind")` |
| `expected_value` | `assertion.get("expected")` |
| `observed_value` | `assertion.get("actual")` |
| `message` | `assertion.get("message")` |
| `failure_category` | `failed.get("failure_category")` |
| `scenario_set` | `summary.get("scenario_set")` |

Evidence: feedback summarizer in `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:782-801`; public-only filter in `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:804-822`; public feedback probe/evaluation flow in `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:463-480` and `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:558-574`; patch metadata stores `feedback` and `feedback_source_scenario_set` in `results_iterative_repair_full_matrix/run_iterative_repair_public_feedback_ad_subset.py:924-940`.

## `{feedback}` Retained Artifact Audit

| Item | Actual value | Evidence |
|---|---|---|
| Patch metadata count audited | 1,448 retained patch metadata records in the final missing-family public-feedback repair artifact. | `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/*/tier_*/*/seed_*/apps/round_*/patch_metadata.json`. |
| Patch metadata statuses | `ok`: 984; `partial_file_set`: 236; `failed`: 224; `bad_file_set`: 4. | Same retained patch metadata files. |
| Repair rounds represented in patch metadata | Repair 1: 799 patch metadata records; Repair 2: 649 patch metadata records. | Same retained patch metadata files. |
| Feedback source recorded in patch metadata | `feedback_source_scenario_set` is `public` in all 1,448 patch metadata records. | Same retained patch metadata files; sample at `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/campus_registrar_command/tier_c/gpt54/seed_01/apps/round_1/patch_metadata.json:10-28`. |
| Feedback scenario set recorded in patch metadata | `feedback.scenario_set` is `public` in all 1,448 patch metadata records. | Same retained patch metadata files. |
| Private scenario IDs in patch metadata feedback | 0. | Local audit over the 1,448 retained patch metadata files found no `private_` strings. |
| Public feedback probe records | 1,452 `public_feedback_round_*.json` records; all have top-level `scenario_set: public`; 1,323 have `failure_feedback.scenario_set: public`; 129 have no `failure_feedback` because the public probe did not expose a failure. | `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/*/tier_*/*/seed_*/records/public_feedback_round_*.json`. |
| Private scenario IDs in public feedback probe records | 0. | Local audit over `public_feedback_round_*.json` found zero `failure_feedback.scenario_id` values beginning with `private_`. |

## Representative `{feedback}` Example

The following retained patch metadata is public and app-specific. For paper display, the object can be anonymized as shown below without changing the schema:

Source: `results_missing_families_full_rerun/public_feedback_repair_at1_at2_at3/runs/campus_registrar_command/tier_c/gpt54/seed_01/apps/round_1/patch_metadata.json:10-25`.

```json
{
  "scenario_id": "public_01_<public_task_name>",
  "scenario_tier": "smoke",
  "first_failed_step": 6,
  "failed_action": "snapshot",
  "failed_component": null,
  "failed_assertion": "table_order_equals",
  "expected_value": ["<PUBLIC_ROW_ID_1>", "<PUBLIC_ROW_ID_2>", "<PUBLIC_ROW_ID_3>"],
  "observed_value": [],
  "message": "table '<PUBLIC_TABLE_ID>' row order should equal [...]",
  "failure_category": "assertion_table_order_equals",
  "scenario_set": "public"
}
```

The exact retained value in that patch metadata has `scenario_id: public_01_filter_queue_and_select_nova`, `scenario_tier: smoke`, `first_failed_step: 6`, `failed_action: snapshot`, `failed_component: null`, `failed_assertion: table_order_equals`, `failure_category: assertion_table_order_equals`, and `scenario_set: public`.
