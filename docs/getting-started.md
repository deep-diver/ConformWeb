# Getting Started With ConformWeb

This guide takes an app from a local directory or URL to a ConformWeb result. It
uses only released CLI behavior and target files.

## 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
conformweb --version
```

On Linux CI, `playwright install --with-deps chromium` also installs Chromium's
system libraries.

## 2. Choose A Runnable Target

```bash
conformweb list-targets
```

The current release contains 21 complete targets and 732 scenarios: 264 public
and 468 private. Every listed target includes its contract, both scenario sets,
and reference app.

Use `--json` when selecting targets programmatically:

```bash
conformweb list-targets --json > target-inventory.json
```

Compile the selected contract and scenario set before generating or launching an
app:

```bash
conformweb validate-target \
  --target targets/web/stayflow_concierge/tier_a \
  --scenario-set public
```

This validates component/action references and DSL semantics without starting a
browser.

## 3. Implement The Public Contract

The candidate may be a static directory or any app reachable at a local URL.
The evaluator requires browser-observable behavior, not a particular framework.

The candidate must:

- implement each selector and action in `contract.dsl.yaml`;
- keep declared controls directly actionable by Playwright;
- expose the exact `runtime.state_probe.expression` object;
- initialize and update the declared public state paths;
- preserve declared routes, persistence, roles, services, tables, uploads, and
  other runtime semantics used by that target.

For the paper's single-shot protocol only, generation is constrained to exactly
`index.html`, `styles.css`, and `app.js`. The evaluator itself does not impose
that source layout and can evaluate framework or backend-backed apps by URL.

## 4. Preserve The Evaluation Boundary

The camera-ready protocol exposes the product premise, public contract,
disclosed public scenarios, and fixed DSL interpretation instructions to the
model. It does not expose private scenarios, reference source, evaluator traces,
screenshots, failure feedback, or expected private trajectories.

The public repository necessarily makes evaluation files inspectable. For a
blind generation experiment, put only the contract and
`scenarios.public.dsl.yaml` into the model context. Keep
`scenarios.private.dsl.yaml` evaluator-side until the candidate is frozen.

## 5. Evaluate

Static directory:

```bash
conformweb evaluate-dsl \
  --target targets/web/stayflow_concierge/tier_a \
  --scenario-set public \
  --static-dir /absolute/path/to/candidate \
  --run-subject candidate-001 \
  --screenshot-policy failures \
  --output .conformweb-runs/candidate-001-public
```

Running application:

```bash
conformweb evaluate-dsl \
  --target targets/web/stayflow_concierge/tier_a \
  --scenario-set public \
  --app-url http://127.0.0.1:5173 \
  --run-subject candidate-001 \
  --screenshot-policy failures \
  --output .conformweb-runs/candidate-001-public
```

Add `--headed --slow-mo 100` for interactive debugging. The default action
timeout is 5,000 ms; change it only when the evaluation protocol requires a
different value.

Screenshot retention defaults to `all`, matching the paper protocol. Use
`--screenshot-policy failures` for routine evaluation to keep only failed
assertion pairs and pre-error evidence, or `--screenshot-policy none` when JSON
state evidence is sufficient.

After freezing the candidate, replace `public` with `private` for held-out
evaluation or `all` for the combined public-plus-private score.

## 6. Read The Result

Each invocation creates a timestamped run directory beneath `--output`:

```text
<output>/<run-id>/
  summary.json
  events.jsonl
  screenshots/
```

`summary.json` contains formal whole-scenario scoring, stepwise diagnostics,
capability/tier breakdowns, first failed steps, and failure categories.
`events.jsonl` retains per-step before/after public state and assertion evidence.
Screenshots are diagnostic evidence and are not used as the scoring oracle.

The evaluator starts every scenario in a fresh Chromium browser context at
1280x900, installs contract-declared deterministic service fixtures, and uses a
5,000 ms default action timeout.

## 7. Build A Dashboard

When run artifacts live beneath a target's cohort tree:

```bash
conformweb dashboard --target targets/web/stayflow_concierge/tier_a
```

For custom `--output` directories, inspect `summary.json` directly or pass an
appropriate run root with `--runs-dir`.

## 8. Generate A Paper-Protocol Candidate

The released static generator accepts OpenAI, Anthropic, and Google provider
identifiers. Only the OpenAI path needs the optional Python SDK; the other two
use their HTTP APIs directly.

```bash
pip install -e ".[generation]"
python tools/generate_blind_dsl_static_app.py \
  --contract-dsl targets/web/stayflow_concierge/tier_a/contract.dsl.yaml \
  --public-scenarios-dsl targets/web/stayflow_concierge/tier_a/scenarios.public.dsl.yaml \
  --output-dir /absolute/path/to/candidate \
  --variant "clear travel booking workspace" \
  --provider openai \
  --model YOUR_MODEL_ID
```

Set the matching `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`.
Generation writes the fully instantiated prompt hash, contract hash, requested
provider/model, and response metadata to `generation.json`.

## Release Scope

The camera-ready study evaluates 24 instances and 756 scenarios. The current
public evaluator release is the supported 21-target, 732-scenario set reported
by `conformweb list-targets`.
