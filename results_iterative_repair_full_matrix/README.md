# Iterative Repair Full Matrix

This directory is the only write target for the iterative repair experiment.
Existing generated apps, evaluation logs, JSON results, CSVs, and figures under
`targets/`, `reports/`, `tables/`, or prior artifact directories are treated as
read-only.

## Experiment

The runner builds the 24-instance web benchmark matrix from:

- 6 target families under `targets/web/*`
- 4 tiers per family, `tier_a` through `tier_d`
- 9 model slugs from the M/T/F model tiers
- seeds `1..10` by default

For each original generated app found in the retained cohort aggregates, it:

1. Copies the original app into this directory as `round_0`.
2. Reuses the existing `detoxbench evaluate-dsl` evaluator and writes fresh
   logs under this directory.
3. Summarizes only the first failed scenario, failed step, assertion type,
   expected value, observed value, and failure category.
4. Prompts the same model to patch the current app using only the app source,
   public contract, public scenario examples, and that summarized failure
   feedback. Private scenario files, reference implementations, and full
   evaluator logs are not included in the repair prompt.
5. Re-evaluates the patched app.
6. Repeats for two repair rounds total.

Each round writes a per-run JSON record containing at least:

- `model`
- `family`
- `tier`
- `instance`
- `seed`
- `round`
- `full_pass`
- `scenario_score`
- `step_score`
- `first_failure_category`
- `recovered_from_previous_round`
- `patch_metadata`

## Usage

Dry-run manifest only:

```bash
python3 results_iterative_repair_full_matrix/run_iterative_repair_full_matrix.py --dry-run
```

Run the full resumable matrix:

```bash
python3 results_iterative_repair_full_matrix/run_iterative_repair_full_matrix.py --resume --workers 2
```

Run a small smoke slice:

```bash
python3 results_iterative_repair_full_matrix/run_iterative_repair_full_matrix.py \
  --resume \
  --families homefix_hub \
  --tiers D \
  --models gpt54_nano \
  --seeds 1 \
  --workers 1
```

The script loads API keys from `~/.genai_rc` when those environment variables
are not already present.
