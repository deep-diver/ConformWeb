# Authoring DSL Targets

New DetoxBench web targets must be compiler-first DSL targets.

Each target should start with:

```text
targets/web/<target_id>/
  contract.dsl.yaml
  scenarios.dsl.yaml
  scenarios.public.dsl.yaml
  scenarios.private.dsl.yaml
  reference_app/
  fixtures/known_bad/
  artifacts/
```

Small internal targets may keep only `scenarios.dsl.yaml`. Release-boundary
targets should split public examples from private scoring scenarios. When split
files exist, the evaluator loads both by default and can run either side with
`--scenario-set public` or `--scenario-set private`.

## Contract

`contract.dsl.yaml` is public and is the normative behavioral specification
given to an LLM candidate builder. The paper protocol also supplies disclosed
public scenarios as examples; they do not extend the contract.

It must define:

- `dsl_version`, currently `"1.0.0"` for deterministic single-page release
  targets, `"1.1.0"` for page-aware targets, `"1.2.0"` for deterministic async
  lifecycle targets, `"1.3.0"` for dynamic row-action targets, `"1.4.0"`
  for bulk/multi-item operation targets, `"1.5.0"` for structured
  field-validation targets, `"1.6.0"` for nested parent/child collection
  targets, `"1.7.0"` for deterministic logical-time and scheduled-transition
  targets, `"2.0.0"` for role/session permission targets, `"2.1.0"` for
  browser lifecycle targets, `"2.2.0"` for actor-scoped targets, `"2.3.0"`
  for deterministic service-fixture targets, `"2.4.0"` for event-stream
  targets, `"2.5.0"` for runtime table/grid targets, `"2.6.0"` for upload
  targets, `"2.7.0"` for declared normalization targets, `"2.8.0"` for
  conflict-branch targets, `"2.9.0"` for join-projection targets, or
  `"3.0.0"` for the integrated post-2.0 release boundary with typed upload
  schemas
- `app.id`, `app.name`, and `app.capability`
- `runtime.target: web`
- `runtime.state_probe.expression`
- `runtime.pages` when the target requires browser-visible pages or routes
- `runtime.persistence.reload` when scenarios evaluate browser reload safety
- `runtime.tables` when scenarios evaluate rendered table/grid rows or cells
- `state.initial` and `state.schema`
- every evaluated component selector
- every component `page` binding for page-aware targets
- every supported component action
- public action preconditions, effects, blocked effects, and rejected effects
- public role/session semantics, allowed roles, and unauthorized effects when a
  target uses permissions
- public service, event, table, upload schema, normalizer, conflict, and join
  semantics whenever scenarios rely on those behaviors

The selector must point at the element the evaluator can directly operate on.
Do not put the selector on a hidden input, disabled proxy, or covered decorative
element.

For `dsl_version: "1.1.0"` page-aware targets, each declared page must map to a
public browser path. A component that is only actionable on a specific page
should declare `page: <page_id>`, and an action that navigates must declare
`navigate_to: <page_id>`. Candidate apps must make the browser location match
the declared path; panel-only navigation behind one unchanged URL is not enough.

For `dsl_version: "1.2.0"` async targets, actions with delayed completion must
declare immediate pending-state `effects` and delayed `async_effects` with a
positive `after_ms`. The delay must be long enough for scenarios to observe the
pending public state with `wait_ms`. Completion effects should declare the
post-request state explicitly, including whether the app returns to `idle`.

For `dsl_version: "1.3.0"` row-action targets, use `selector_template` for
row-local controls and use `value_from: input.*` in item `where` predicates to
bind the clicked row to the public collection item. Candidate apps must render
the templated row selector as an actionable DOM element, not just expose a
matching state field.

For `dsl_version: "1.4.0"` bulk targets, use `updated_all_where` and
`removed_all_where` when a command intentionally affects every matching public
array item. The contract must declare the complete predicate set and the exact
updates. Non-matching rows must be preserved unless another public effect
changes them.

For `dsl_version: "1.5.0"` field-validation targets, expose validation state as
declared public object paths, not just UI text. Use `updated_object_fields` for
rejected validation attempts that add or replace specific field errors,
`removed_object_fields` for corrections that clear only specific keys, and
`equals_object_key_count` for derived error counters. Clearing one field must
preserve unrelated errors unless the public effect explicitly lists those keys.

For `dsl_version: "1.6.0"` nested collection targets, keep parent arrays and
child arrays in public state. Use `updated_first_child_where` and
`removed_first_child_where` when an action scopes a child mutation by both
`parent_where` and `child_where`. Use `equals_nested_count_where` and
`equals_nested_sum` for derived projections across child arrays. Do not require
the evaluator to infer parent-child relationships from row text or visual
layout.

For `dsl_version: "1.7.0"` logical-time targets, expose the logical clock as a
declared numeric public state path. Use `advanced_time_by` to move that clock,
`updated_all_where_after` when rows should be updated using predicates evaluated
against the after-action public state, and `removed_all_where_after` when rows
should be removed using after-state predicates. Do not rely on `Date.now()`,
real time zones, or evaluator sleeps for deterministic schedule behavior.

For `dsl_version: "2.0.0"` role/session targets, declare
`runtime.session.role_path` and the complete `runtime.session.roles` set. Any
action with `allowed_roles` must remain directly clickable for every role. When
the current role is allowed, normal effects apply. When the current role is not
allowed, `mode: unauthorized` scenarios score the declared
`unauthorized_effects`; the app should not hide, disable, or remove the control
instead of producing the public denied transition.

For `dsl_version: "2.0.1"` reload-persistence targets, declare
`runtime.persistence.reload.paths`. These paths are the public state that must
survive a real browser reload. Scenarios can then use componentless
`browser: reload` steps and assert public before/after relations such as
`unchanged`. Candidate apps must implement the declared persistence behavior
through browser-visible persistence mechanisms such as `localStorage`,
`sessionStorage`, or URL-backed state. Do not test reload persistence for paths
that are not named in the contract.

For `dsl_version: "2.1.0"` browser-lifecycle targets, scenarios may use
componentless `browser: back`, `browser: forward`, and
`browser: {action: goto, page: <page_id>}` steps. The contract should declare
all browser-visible pages in `runtime.pages`, and candidate apps must keep the
public route state synchronized with `window.location` during direct deep-link
entry and history traversal. A fake tab switch without browser location changes
is out of contract.

For `dsl_version: "2.5.0"` table/grid targets, declare every scored grid in
`runtime.tables`. A scenario may then assert table row counts, row order, and
cell values. Do not score table rendering by relying on arbitrary text scraping
or a reference-private row model.

For `dsl_version: "2.6.0"` upload targets, declare an `upload` component action
on the actual file input or its directly actionable proxy. In DSL `3.0.0`,
prefer `file_schema` for CSV uploads whenever scenario rows include typed
values. If the contract does not declare numeric or boolean columns, failures
caused by string-vs-number parsing are contract-gap findings.

For `dsl_version: "2.7.0"` normalization targets, use
`equals_normalized` only when the normalizers are part of the intended public
behavior. A private scenario must not silently require whitespace trimming,
case folding, digit extraction, or currency parsing unless that rule appears in
the DSL.

For `dsl_version: "2.8.0"` conflict targets, actions that can hit an
optimistic-conflict branch should declare both `conflict_when` and
`conflict_effects`. Conflict scenarios should use `mode: conflict`, and the UI
control must remain directly actionable so the evaluator can observe the public
conflict transition.

For `dsl_version: "2.9.0"` join targets, use `equals_join_projection` for
visible rows derived from multiple public collections. Declare source
collections, key fields, and projected fields instead of maintaining a
scenario-only expected table.

## Scenarios

`scenarios.dsl.yaml` is the legacy unsplit evaluator input. Release targets use
explicit public and private files.

For release-boundary work, use:

- `scenarios.public.dsl.yaml` for public examples and visible diagnostics;
- `scenarios.private.dsl.yaml` for hidden formal scoring scenarios.

Public scenarios are part of the camera-ready candidate-generation prompt.
Private scenarios remain evaluator-side and must not be supplied to the model.

A scenario is an ordered list of component/action steps:

```yaml
dsl_version: "1.0.0"
scenarios:
  - id: create_and_filter_ticket
    tier: behavior
    steps:
      - do: title_input.fill
        input: {value: Broken pump}
      - do: priority_urgent_button.click
      - do: create_button.click
      - do: filter_urgent_button.click
        expect:
          - op: equals
            path: visible_count
            value: 1
```

In DSL 2.0.1 and later, a scenario may also contain a browser lifecycle step:

```yaml
- browser: reload
  expect:
    - op: unchanged
      path: draft_id
```

This lowers to a real browser reload. It is only valid when the contract
declares `runtime.persistence.reload`.

In DSL 2.1.0 and later, lifecycle steps can also drive browser history:

```yaml
- browser:
    action: goto
    page: ledger
- browser: back
  expect_page: workspace
- browser: forward
  expect_page: ledger
```

`goto` requires either a declared page id or a browser path beginning with `/`.
`back` and `forward` require `expect_page` so the browser-visible route is
scored directly.

Scenario-local `expect` checks are allowed, but they must remain inside the
public contract surface. Repeated derived rules should move into the contract
as DSL effects instead of living as private scenario arithmetic.

Scenario files may declare `tier_weights`, and each scenario may declare
`weight`. Formal weighted scoring is computed over `kind: scoring` scenarios.
`kind: probe` scenarios are reported but excluded from the formal score.

Scenarios may also declare `difficulty`. This is a model-facing difficulty
ladder and is intentionally separate from `tier`. Use `tier` for product
capability or failure class reporting, such as `roles`, `history`, or `complex`.
Use `difficulty` for evaluation strata, such as `d1_smoke`, `d2_core`,
`d3_integrated`, `d4_adversarial`, and `d5_stress`.

## Fairness Rule

Candidate generation receives:

- product/task description
- complete `contract.dsl.yaml`
- disclosed `scenarios.public.dsl.yaml`
- fixed DSL interpretation instructions from the released prompt
- allowed runtime shape, such as static files or app URL

Candidate generation must not receive:

- `scenarios.private.dsl.yaml`
- private scenario files
- run artifacts
- reference app source
- evaluator implementation details beyond the public DSL semantics

Private scenarios may hide action order and scenario-created values, but they
must not hide requirements. If a scenario checks behavior that is not derivable
from `contract.dsl.yaml`, it is a contract-gap probe, not a formal score.

## Scenario Tiers And Difficulty

Use tiers to make capability coverage visible in dashboards and reports:

- `service`: external-service or derived-service state
- `roles`: role, permission, and session behavior
- `history`: browser history, route, and reload behavior
- `complex`: multi-ledger or multi-feature workflows
- app-specific labels such as `conflict`, `event`, or `persistence`

Use difficulty to make model-level challenge visible:

- `d1_smoke`: wiring and one small transition
- `d2_core`: focused feature or policy rule
- `d3_integrated`: realistic multi-feature flow
- `d4_adversarial`: failed commands, blocked/rejected paths, rollback, mode
  switches, or long state preservation checks
- `d5_stress`: long-horizon, cross-ledger, cross-route, or dense end-to-end
  workflows

For release-boundary targets, prefer enough scenarios per meaningful capability
tier and difficulty bucket to distinguish small-model smoke failures from
frontier-model projection, persistence, and composition failures.

## DSL Authoring Rules

The contract should carry the semantics, not the evaluator.

- Derived strings: use `equals_template`.
- Linear numeric rules: use `equals_linear`.
- Ordered threshold or priority formulas: use `equals_piecewise_linear`.
- Counts and sums from public arrays: use `equals_length`,
  `equals_count_where`, `equals_sum`, and first/last projections.
- Item updates or transfers: use `updated_first_where`,
  `removed_first_where`, `moved_first_where`, and
  `appended_from_first_where`.
- Scenario-created records: use `appended_object`.
- Filtered or sorted views: use `equals_filter`.
- Selection-bound identity: use `value_path` predicates.
- Invalid form submission: use `rejected_when` and `rejected_effects`.
- Capacity or locked-state no-op attempts: use `blocked_when` and
  `blocked_effects`.
- Browser page transitions: use `runtime.pages`, component `page`, and
  action-level `navigate_to`.
- Async request lifecycles: use immediate pending-state `effects`,
  `async_effects`, scenario `wait_ms`, and scenario `await`.
- Row-local commands: use `selector_template` plus item predicate
  `value_from: input.*`.
- Bulk commands: use `updated_all_where` for all matching item updates and
  `removed_all_where` for all matching item removals.
- Membership checks: use `one_of` and `not_one_of` for public enum or role
  membership.
- Role/session permissions: use `runtime.session`, action `allowed_roles`, and
  `unauthorized_effects`.
- Browser lifecycle: use `runtime.persistence.reload`, componentless
  `browser: reload`, `browser: {action: goto, page: ...}`, `browser: back`,
  and `browser: forward`.

Blocked, rejected, and unauthorized controls must remain directly actionable. A
native disabled button prevents the evaluator from performing the action and is
a UI-contract failure, not a successful blocked/rejected/unauthorized behavior.

## Evaluating Candidates

Run a reference app:

```bash
conformweb evaluate-dsl \
  --target targets/web/stayflow_concierge/tier_a \
  --static-dir targets/web/stayflow_concierge/tier_a/reference_app \
  --headless
```

Run a generated candidate:

```bash
conformweb evaluate-dsl \
  --target targets/web/stayflow_concierge/tier_a \
  --static-dir targets/web/stayflow_concierge/tier_a/generated_candidate_app \
  --run-subject generated_candidate_app \
  --headless
```

Use `--app-url` instead of `--static-dir` for a separately running framework app.
Use `--action-timeout` to make missing selectors or stalled interactions fail
quickly and reproducibly.

Run only private scoring scenarios when split files exist:

```bash
conformweb evaluate-dsl \
  --target targets/web/stayflow_concierge/tier_b \
  --static-dir targets/web/stayflow_concierge/tier_b/reference_app \
  --scenario-set private \
  --headless
```

Verify known-bad fixtures:

```bash
conformweb known-bad --target targets/web/<target-with-known-bad-fixtures>
```

## Benchmark Maturity

A target that merely passes its reference scenarios is a runnable prototype, not
automatically a mature benchmark target. Use `docs/maturity.md` to decide
whether a target is experimental, fair for internal comparison, calibrated, or
release-ready.
