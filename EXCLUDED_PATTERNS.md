# Excluded Patterns

Excluded from this compact public release:

- `**/screenshots/**`, except the curated poster asset pack
- uncurated `**/*.png`, `**/*.jpg`, `**/*.jpeg`, `**/*.webp`, and video files
- per-run `summary.json`, `events.jsonl`, and browser trace directories
- generated candidate app directories and full repair patch trees
- API preflight artifacts, runner logs, PID/session files, and environment captures
- aborted, superseded, and intermediate rerun bundles
- `reports/conformweb_visualizations/archive/**` and `archives/**`
- `.git/**`, virtual environments, caches, and Python bytecode
- local absolute filesystem prefixes in newly added audit/release documents; retained historical raw tables may preserve their original provenance paths

The public release retains compact aggregate CSV/JSON/JSONL files, experiment manifests,
reproducibility audits, and a small curated set of poster/failure images.
