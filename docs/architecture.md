# Architecture

```text
detoxbench/
  core/               Shared state-path lookup, assertions, result models
  dsl/                Versioned DSL validation and web-suite compilation
  web/                Playwright evaluator and local static server
targets/
  web/
    stayflow_concierge/
      tier_a/
      tier_b/
      tier_c/
    freshcart_market/
      tier_a/
      tier_b/
    <suite>/<tier>/
      contract.dsl.yaml   Public DSL contract
      scenarios.*.dsl.yaml  Evaluator-side DSL scenarios
      reference_app/      Runnable, productized reference implementation
      cohorts/            Gitignored blind candidates, logs, and screenshots
docs/                    Philosophy, DSL spec, authoring, and maturity notes
tools/                   Generation and experiment helpers
```

## Mainline Flow

DetoxBench main is now DSL-first. The historical hand-built target suite has
been removed from main, and new benchmark targets should use:

- `contract.dsl.yaml`
- `scenarios.dsl.yaml`
- `reference_app/`

The DSL compiler is the fairness boundary. It validates the contract and
scenario bundle, then lowers it into the existing web evaluator's deterministic
action/check format. The evaluator still performs browser actions, captures
state, writes screenshots, and emits run artifacts; it no longer needs
target-specific oracle logic.

Reference apps are allowed to be polished product surfaces, not raw evaluator
dashboards. Productization is valid only when it preserves every declared
selector, action, public state probe, route, and transition semantics compiled
from the DSL.

## Runtime Flow

1. CLI loads `contract.dsl.yaml` and `scenarios.dsl.yaml`.
2. The DSL compiler validates version support, component/action references,
   state paths, page references, navigation references, selector templates,
   bulk item predicates, structured object mutations, nested collection
   predicates, role/session declarations, permission membership, preconditions,
   effects, async effects, blocked/rejected/unauthorized semantics, and scenario
   expectations.
3. The compiler lowers the DSL bundle into a web `Contract` and `ScenarioSet`.
4. If `--app-url` is absent, the evaluator serves the supplied `--static-dir`.
5. Playwright opens a fresh browser context for each scenario.
6. For every compiled step:
   - capture before state via the declared public state probe plus browser page
     metadata
   - save before screenshot
  - perform the action unless the step is a snapshot
  - wait for a declared duration when the step is `wait_ms` or `await`
  - capture after state plus browser page metadata
   - save after screenshot
   - evaluate rule-based assertions
   - append JSONL event data
7. A `summary.json` file is written at the end of the run.

If a step assertion fails, the evaluator records the first failed step and
continues the scenario so later state drift remains visible. If the app crashes,
a selector is missing, or the state probe is unavailable, the evaluator records
that failure against the attempted step.

## Evaluator Boundary

The evaluator is intentionally allowed to be "cheating" in the
benchmark-design sense:

- It uses selectors declared in the public contract.
- It reads a public JSON-compatible state probe.
- It reads browser URL/path/page metadata when the contract declares pages.
- It does not infer intent visually or use AI.
- It resolves selector templates only from scenario input declared in the
  compiled step.
- It evaluates bulk item predicates against public before/after arrays.
- It evaluates structured object mutations and object key counts against public
  before/after object state.
- It evaluates nested child mutations and nested projections against public
  parent/child arrays.
- It evaluates role/session membership against the public session state path
  declared in `runtime.session`.
- It checks public before/after relations compiled from DSL operations.
- It waits only when the compiled DSL step explicitly declares `wait_ms` or an
  async action completion through `await`.

This is deliberate. DetoxBench measures whether a generated app satisfies a
behavioral contract, not whether an evaluator can discover the app unaided.

## Candidate Boundary

Candidate source layout is unrestricted. A candidate may be a single static HTML
file, a multi-file static app, or a framework app served at a URL. The evaluator
only needs:

- an app URL or static directory
- selectors declared in `contract.dsl.yaml`
- the declared state probe, such as `window.__DETOX_STATE__`
- declared browser routes when the contract uses `runtime.pages`
- declared async lifecycle state when the contract uses `async_effects`
- declared row selector templates when the contract uses `selector_template`
- declared bulk item predicates when the contract uses `updated_all_where` or
  `removed_all_where`
- declared object validation state when the contract uses `updated_object_fields`,
  `removed_object_fields`, or `equals_object_key_count`
- declared nested collection state when the contract uses
  `updated_first_child_where`, `removed_first_child_where`,
  `equals_nested_count_where`, or `equals_nested_sum`
- declared logical-time state when the contract uses `advanced_time_by`,
  `updated_all_where_after`, or `removed_all_where_after`
- declared role/session state when the contract uses `runtime.session`,
  `allowed_roles`, or `unauthorized_effects`
- state values matching the declared schema and transition semantics

The evaluator does not inspect candidate source code, import modules, or care how
many files the implementation uses.

## Artifact Contract

Every run creates:

- `events.jsonl`: one event per step plus scenario completion events
- `summary.json`: aggregate pass/fail result, score, step progress, and first
  failure reason
- `screenshots/<scenario>/<step>-before.png`
- `screenshots/<scenario>/<step>-after.png`

The formal score is whole-scenario weighted pass/fail over scoring scenarios.
Diagnostic score fields also report stepwise progress, tier/capability progress,
contract-surface failures, probe counts, and first-failure taxonomy counts.

By default, runs are grouped by evaluated subject:

```text
targets/web/<suite>/<tier>/cohorts/manual/runs/<subject>/<run_id>/
```

The JSONL event contains complete before and after state for each step.
For page-aware targets, that state includes a reserved `__browser` object with
the current URL, browser path, and resolved page id used by page assertions.

## Dashboard And Gallery

The dashboard is generated from existing run artifacts:

```bash
conformweb dashboard --target targets/web/stayflow_concierge/tier_a
```

It scans `cohorts/**/summary.json` by default for the consolidated target
layout, embeds the latest run data per subject, and links screenshots by
relative paths.

The suite gallery can discover DSL targets directly:

```bash
conformweb gallery --targets-root targets/web --output reports/gallery/index.html
```

or use `targets/web/suite.yaml` for a curated suite order.
