# Release Governance

DetoxBench release maturity depends on four operational controls:

1. public/private scenario separation;
2. score weighting;
3. model cohort reproducibility;
4. known-bad fixtures.

These controls do not change the core philosophy. In the camera-ready protocol,
candidate builders receive the public contract and disclosed public scenarios.
Private scenarios remain evaluator-side and are not part of the
candidate-generation prompt.

## Public And Private Scenario Files

A target may keep a legacy single scenario file:

```text
scenarios.dsl.yaml
```

For release-boundary work, prefer split files:

```text
scenarios.public.dsl.yaml
scenarios.private.dsl.yaml
```

When split files exist, `conformweb evaluate-dsl --target ...` loads both by
default. Use `--scenario-set public` or `--scenario-set private` to run only one
visibility class.

The public/private split is an evaluator data-management boundary:

- `public`: examples, smoke tests, and diagnostic scenarios that may be shown
  in docs or release previews;
- `private`: hidden scoring scenarios used for formal benchmark scores.

Both classes must be derivable from the public contract. Private scenarios may
hide action order and scenario-created values, but they must not hide product
requirements.

## Score Weighting

Scenario files may define tier weights:

```yaml
tier_weights:
  smoke: 1
  behavior: 2
  journey: 3
  end_to_end: 5
```

Individual scenarios may override the tier weight:

```yaml
- id: long_recovery_path
  tier: end_to_end
  weight: 8
```

Formal score uses scoring scenarios only. Probe scenarios are reported but do
not affect the formal ratio.

Diagnostic score fields may report stepwise progress, contract-surface failure
counts, and failure-category breakdowns. These are for interpretation and
calibration. They do not replace the formal weighted scenario score unless a
future release explicitly changes the scoring rule.

Weights should communicate benchmark importance, not rescue a weak suite. A
target whose only failures are tiny wiring mistakes or one catastrophic early
step still needs better scenario design even if its weighted score looks
reasonable.

## Model Cohort Reproducibility

A model cohort manifest records which model configurations are used for blind
candidate generation. Example:

```text
cohorts/gpt54-dsl20-frontier.yaml
```

The manifest records:

- member id;
- model name;
- generator script;
- generation parameters such as max output tokens and visual variant;
- target contract paths;
- intended scenario set for evaluation.

Run:

```bash
conformweb cohort-info --manifest cohorts/gpt54-dsl20-frontier.yaml
```

to validate the manifest and print reproducibility fingerprints. The
fingerprint includes the manifest hash and contract hashes. API-backed model
generation is not guaranteed byte-for-byte deterministic, but the cohort
manifest keeps the evaluation conditions inspectable and rerunnable.

`tools/generate_blind_dsl_static_app.py` now writes `generation.json` with the
model, member id, contract hash, prompt hash, output directory, response id when
available, and git commit. This metadata should be preserved with run artifacts
when comparing cohorts over time.

## Known-Bad Fixtures

Known-bad fixtures are intentionally flawed implementations. They are negative
controls: the evaluator should fail them.

Fixtures live under:

```text
targets/web/<target>/fixtures/known_bad/
```

with an optional manifest:

```text
targets/web/<target>/fixtures/known_bad/manifest.yaml
```

Run:

```bash
conformweb known-bad --target targets/web/<target-with-known-bad-fixtures>
```

The command evaluates every known-bad fixture and then checks the manifest
expectations. If a known-bad fixture passes, the evaluator or scenario suite is
too weak for that defect. If it fails for an unexpected category, the fixture or
failure taxonomy should be reviewed.

Known-bad fixtures should cover recurring failure modes:

- missing state probe;
- missing or covered component selectors;
- disabled blocked/rejected/unauthorized controls;
- wrong numeric delta or formula;
- wrong page navigation;
- wrong validation error map;
- partial bulk update;
- lost nested parent/child relationship.
