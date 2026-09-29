# Current Public Release

Release date: 2026-09-29 (Asia/Seoul)

Publication status: Accepted to the EMNLP 2026 Main Conference.

## Source Provenance

- Source workspace branch: `exp/missing-families-full-rerun`
- Source base commit: `d35e67d9fc33304cf1064e85b285a2974b9b2d1f`
- Source base commit date: `2026-07-11T11:21:22+09:00`
- Publication method: selected-file snapshot from the retained working tree
- File-level provenance: `PACK_MANIFEST.csv`

The source working tree also contained retained experiment outputs and audit documents that
were not committed to the source branch. Those selected artifacts are content-addressed in
the public manifest rather than represented as a single source-repository commit.

## Included Updates

- External-user workflow with the `conformweb` CLI entry point.
- Machine-readable target inventory via `conformweb list-targets --json`.
- Compile-only target validation via `conformweb validate-target`.
- Optional failure-only or disabled screenshot retention for storage-efficient runs.
- Camera-ready information boundary corrected across public documentation.
- Corrected primary run accounting and provenance appendix.
- Exact public-feedback repair `{context}` and `{feedback}` audit.
- Probe-scenario and current-target inventory audit.
- Backend-backed generation runner and compact full-run accounting artifacts.
- Repair runners, fixed-denominator snapshots, and compact six-family summaries.
- Current static/backend generator code and prompt templates.
- Retained screen and provenance assets used for paper presentation.

## Release Scope

The current supported public release contains 21 complete targets and 732 scoring
scenarios: 264 public and 468 private. Each released target includes its contract,
public scenarios, private scenarios, and reference app. Run `conformweb list-targets`
for the machine-derived inventory.

The retained primary result aggregate remains the fixed 2,160-run paper experiment.
Its accounting and provenance are documented under `reports/conformweb_visualizations/`.

Detailed provenance audits:

- `reports/conformweb_visualizations/run_accounting_and_provenance_appendix.md`
- `reports/conformweb_visualizations/probe_scenario_audit.md`
- `reports/conformweb_visualizations/repair_context_feedback_audit.md`

## Exclusions

The release is not a byte-for-byte copy of the full experiment workspace. Large generated
apps, uncurated screenshots, per-run evaluator logs, traces, aborted batches, and full repair
patch trees remain excluded. Their compact aggregate/accounting artifacts are retained where
available. See `EXCLUDED_PATTERNS.md`.
