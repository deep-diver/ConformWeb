# Candidate Workflow

This document describes the camera-ready ConformWeb protocol for generating and
evaluating LLM-created web apps.

## 1. Publish The Public Contract

Give the candidate builder the product/task premise, the complete
`contract.dsl.yaml`, the disclosed `scenarios.public.dsl.yaml`, and the fixed
DSL interpretation instructions in the released generator prompt.

The contract must include the full public behavior surface:

- app purpose and capability
- required components and stable selectors
- supported component actions
- public state schema and initial state
- preconditions, effects, blocked effects, and rejected effects
- the state probe expression, such as `window.__DETOX_STATE__`
- declared pages/routes when the target uses `runtime.pages`
- declared async lifecycle semantics when the target uses `async_effects`
- declared selector templates and row identity rules when the target uses
  `selector_template`
- declared bulk item predicates when the target uses `updated_all_where` or
  `removed_all_where`
- declared structured validation object semantics when the target uses
  `updated_object_fields`, `removed_object_fields`, or
  `equals_object_key_count`
- declared nested parent/child collection semantics when the target uses
  `updated_first_child_where`, `removed_first_child_where`,
  `equals_nested_count_where`, or `equals_nested_sum`
- declared logical-time semantics when the target uses `advanced_time_by`,
  `updated_all_where_after`, or `removed_all_where_after`
- declared role/session semantics when the target uses `runtime.session`,
  `allowed_roles`, or `unauthorized_effects`

The candidate builder must not receive `scenarios.private.dsl.yaml`, run
artifacts, evaluator traces, screenshots, failure feedback, reference source, or
expected private trajectories. Public scenarios are model-visible examples in
the single-shot, backend-backed, and public-feedback repair protocols.

## 2. Generate Or Collect Candidate Apps

The primary single-shot protocol requires exactly:

- `index.html`
- `styles.css`
- `app.js`

The general evaluator can also score a static directory, framework app, or
backend-backed app served at a URL; this broader evaluator mode is not the
paper's fixed three-file generation intervention. ConformWeb scores
browser-observable behavior:
declared controls must be actionable, public state must be exposed through the
declared probe, browser routes must match the declared page contract when
present, async pending/completion state must match the declared lifecycle when
present, dynamic row controls must match declared selector templates when
present, bulk item operations must update or remove all matching public items,
structured validation objects must preserve and clear the declared keys, and
nested child operations must preserve parent/child relationships. Logical-time
targets must use the declared public clock rather than real wall-clock time.
Role/session targets must keep denied controls clickable and apply the declared
public `unauthorized_effects` when the current role is not allowed. All state
transitions must satisfy the compiled DSL semantics.

## 3. Run The DSL Evaluator

The evaluator receives both `contract.dsl.yaml` and `scenarios.dsl.yaml` from
the target directory. It compiles them into deterministic browser actions and
rule-based assertions.

When a target has split scenario files, the evaluator loads
`scenarios.public.dsl.yaml` and `scenarios.private.dsl.yaml` by default. Use
`--scenario-set public` or `--scenario-set private` to run only one side.

For a static candidate:

```bash
conformweb evaluate-dsl \
  --target targets/web/stayflow_concierge/tier_a \
  --static-dir /absolute/path/to/generated_candidate_app \
  --run-subject generated_candidate_app \
  --scenario-set public
```

For an already running app:

```bash
conformweb evaluate-dsl \
  --target targets/web/stayflow_concierge/tier_a \
  --app-url http://127.0.0.1:5173 \
  --run-subject candidate_001 \
  --scenario-set public
```

Every run writes `summary.json`, `events.jsonl`, and screenshots under:

```text
targets/web/<suite>/<tier>/cohorts/manual/runs/<subject>/<run_id>/
```

## 4. Interpret Failures

A formal failure means one of the following happened inside the public contract
surface:

- a declared selector was missing, covered, or not directly actionable
- the state probe was missing or returned incompatible state
- an accepted action produced the wrong public transition
- a blocked action failed to behave as a public no-op
- a rejected validation attempt failed to preserve or annotate state as declared
- a declared page transition failed to update the browser path/page
- an async action skipped pending state, completed too early, never completed,
  or produced the wrong completion transition
- a dynamic row action targeted the wrong row, failed to render the declared
  row selector, or updated a public collection item whose identity did not match
  the scenario input
- a bulk action updated only one matching row, updated unrelated rows, removed
  the wrong set, or failed to preserve non-matching public items
- a field-validation action collapsed public errors into UI text, cleared
  unrelated error keys, failed to add declared error keys, or derived an error
  count from hidden state instead of the public object
- a nested collection action updated the wrong parent, flattened child rows,
  changed sibling children, lost parent order, or derived nested counts/sums
  from hidden bookkeeping instead of public child arrays
- a role-scoped action was hidden or disabled for unauthorized roles, allowed a
  denied role to perform normal effects, or failed to produce the declared
  public `unauthorized_effects`
- a compiled formula, template, collection projection, or identity relation did
  not match the actual after-state

If a scenario checks behavior that cannot be derived from `contract.dsl.yaml`,
the scenario is a contract-gap probe, not a fair candidate failure. The remedy is
to update the public contract or downgrade the check to diagnostic status.

## 5. Compare Runs

Build the per-target dashboard:

```bash
conformweb dashboard --target targets/web/stayflow_concierge/tier_a
```

Build the suite gallery:

```bash
conformweb gallery --targets-root targets/web --output reports/gallery/index.html
```

The dashboard shows selected subjects side by side, scenario progress, first
failed step, failure reason, screenshots, and before/after public state. It also
shows diagnostic stepwise progress and contract-surface failure counts next to
the formal score. Only the latest run per subject is shown by default so the UI
remains readable.

## 6. Reproduce Model Cohorts And Known-Bad Controls

Use cohort manifests to record model generation conditions:

```bash
conformweb cohort-info --manifest cohorts/stayflow-tier-b-model-tier-m.yaml
```

Use known-bad fixtures to confirm that the evaluator still catches established
defects:

```bash
conformweb known-bad --target targets/web/<target-with-known-bad-fixtures>
```

These commands are not replacements for candidate evaluation. They are
calibration controls that make score changes easier to interpret over time.
