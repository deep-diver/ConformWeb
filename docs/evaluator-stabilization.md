# Evaluator Stabilization

DetoxBench is not only a collection of benchmark apps. It is also a method for
building evaluators whose measurement error can be inspected and reduced.

The goal is not to prove that an evaluator is perfect. The goal is to make
evaluator error visible, classify it consistently, and drive the false positive
rate low enough that candidate failures are fair to use as benchmark evidence.

## Stabilization Loop

Use this loop on one target before expanding the same practice to the full
suite:

1. Choose one target with a non-trivial contract and scenario suite.
2. Generate several blind implementations from the public contract and
   disclosed public scenarios.
3. Evaluate every blind implementation with the current evaluator.
4. Classify every failed scenario and first failed step.
5. Fix unfair failures by improving the contract, scenario assertions, or
   evaluator semantics.
6. Re-run the reference app and at least one independent passing app.
7. Generate a fresh blind cohort from the updated contract.
8. Repeat until remaining failures are mostly fair candidate failures or
   explicitly marked probes.

When the contract changes, old blind implementations are no longer a clean
cohort for formal pass-rate claims. They remain useful as historical artifacts,
but the next stabilization pass should generate new blind implementations from
the updated contract.

## Failure Classification

Every blind failure should be assigned one primary category.

- `candidate_bug`: the contract required the behavior, the evaluator stayed
  inside the contract surface, and the candidate failed the behavior.
- `contract_gap`: the expected behavior is reasonable, but the public contract
  did not actually require it.
- `evaluator_overfit`: the assertion depends on reference-specific internals,
  exact bookkeeping shape, or an implementation strategy not promised by the
  contract.
- `evaluator_bug`: the evaluator action, state lookup, assertion semantics, or
  artifact handling is incorrect.
- `ambiguous`: the result cannot yet be classified without a contract or
  evaluator design decision.
- `accepted_pass`: the subject passed the relevant scoring surface.

The highest-priority error is a false positive: a candidate that reasonably
satisfies the public contract but is failed by the evaluator. False positives
damage benchmark fairness. False negatives are also important because they
reduce benchmark discrimination, but they are safer than false positives during
early target stabilization.

## Measurement Metrics

For each target stabilization pass, record at least:

- blind cohort size
- scenario pass rate by tier
- step progress by tier
- first failed step distribution
- failure classification counts
- false positive rate
- known-bad detection rate
- reference regression count
- independent regression count
- number of assertions converted from exact values to public relations
- number of scoring assertions downgraded to probes
- number of contract requirements added

Suggested definitions:

```text
false_positive_rate =
  unfair_failures / total_blind_scoring_failures

known_bad_detection_rate =
  known_bad_subjects_failed_as_expected / total_known_bad_subjects

reference_regression_count =
  scoring scenarios newly failed by the reference app after an evaluator change

independent_regression_count =
  scoring scenarios newly failed by previously passing independent apps
```

`unfair_failures` includes `contract_gap`, `evaluator_overfit`,
`evaluator_bug`, and unresolved `ambiguous` failures. A strict maturity review
may count `ambiguous` separately, but it should not be treated as fair candidate
failure.

## Stabilization Criteria

A target can be called stabilized for internal comparison when:

- reference and independent subjects still pass all scoring scenarios
- compiler validation passes
- known-bad fixtures fail for the intended reasons
- the latest blind cohort has a low false positive rate
- remaining blind failures are mostly `candidate_bug`
- any unresolved `contract_gap` or `evaluator_overfit` checks are probes, not
  formal scores

The exact acceptable false positive threshold is empirical. A useful starting
target is below 5% of blind scoring failures for mature targets, with zero
known false positives in `smoke` and `behavior` tiers. The threshold should be
revisited after running several targets and model cohorts.

## What To Change

If a failure is `candidate_bug`, keep the scenario and add the failure mode to
the taxonomy or known-bad suite when useful.

If a failure is `contract_gap`, update the public contract before treating the
behavior as scoreable. Then regenerate blind implementations from the updated
contract.

If a failure is `evaluator_overfit`, replace exact-value assertions with
contract-visible relations, changed/unchanged checks, parent-state presence
checks, or cross-state consistency checks. If the behavior cannot be expressed
without reference internals, move it to a probe.

If a failure is `evaluator_bug`, fix evaluator semantics and rerun reference,
independent, blind, and known-bad subjects.

If a failure is `ambiguous`, do not count it as formal evidence. Decide whether
the behavior belongs in the public contract, the evaluator, or a probe.

## Relation To Maturity

Level 2 asks whether failures can be fair for a single target. Level 3 asks
whether those failures remain meaningful across implementation styles, blind
cohorts, and known-bad subjects.

Beyond Level 3, the exact maturity ladder is provisional. The next levels
should be discovered by applying this stabilization loop across multiple
targets and observing which bottlenecks dominate: contract governance, private
scenario review, artifact reproducibility, cohort calibration, scoring
semantics, or release operations.
