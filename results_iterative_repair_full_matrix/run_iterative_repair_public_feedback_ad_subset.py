#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "results_iterative_repair_public_feedback_ad_subset"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.generate_blind_dsl_static_app import generate_payload  # noqa: E402


@dataclass(frozen=True)
class ModelSpec:
    model_tier: str
    slug: str
    provider: str
    model: str
    max_output_tokens: int
    request_timeout: int
    base_url: str | None = None


MODELS: list[ModelSpec] = [
    ModelSpec("M", "gpt54_nano", "openai", "gpt-5.4-nano", 64000, 900),
    ModelSpec("M", "claude_haiku45", "anthropic", "claude-haiku-4-5", 64000, 900, "https://api.anthropic.com"),
    ModelSpec("M", "gemini31_flash_lite", "google", "gemini-3.1-flash-lite", 64000, 900),
    ModelSpec("T", "gpt54_mini", "openai", "gpt-5.4-mini", 64000, 900),
    ModelSpec("T", "claude_sonnet46", "anthropic", "claude-sonnet-4-6", 64000, 900, "https://api.anthropic.com"),
    ModelSpec("T", "gemini_flash_latest", "google", "gemini-flash-latest", 64000, 900),
    ModelSpec("F", "gpt54", "openai", "gpt-5.4", 80000, 1200),
    ModelSpec("F", "claude_opus46", "anthropic", "claude-opus-4-6", 80000, 1200, "https://api.anthropic.com"),
    ModelSpec("F", "gemini31_pro_preview", "google", "gemini-3.1-pro-preview", 80000, 1200),
]
MODEL_BY_SLUG = {model.slug: model for model in MODELS}
API_SEMAPHORES = {
    "openai": threading.BoundedSemaphore(4),
    "anthropic": threading.BoundedSemaphore(3),
    "google": threading.BoundedSemaphore(2),
}


# These are the retained local cohort aggregates that point at original blind
# generated apps. Some families have rerun aggregates because earlier raw batch
# roots were intentionally not retained in this checkout.
DEFAULT_AGGREGATES: list[Path] = [
    ROOT / "targets/web/stayflow_concierge/cohorts/_batches/20260511_stayflow_ab_mtf_10x/aggregate.json",
    ROOT / "targets/web/stayflow_concierge/cohorts/_batches/stayflow-tier-c-20260511T153500Z/aggregate.json",
    ROOT / "targets/web/stayflow_concierge/cohorts/_batches/rerun_missing_nongemini_20260525T171016Z/aggregate.json",
    ROOT / "targets/web/stayflow_concierge/cohorts/_batches/rerun_missing_gemini_20260525T132231Z/aggregate.json",
    ROOT / "targets/web/freshcart_market/tier_a/cohorts/_batches/20260511T180907Z/aggregate.json",
    ROOT / "targets/web/freshcart_market/tier_b/cohorts/_batches/20260512T015752Z_redesign/aggregate.json",
    ROOT / "targets/web/freshcart_market/tier_b/cohorts/_batches/20260512T025450Z/aggregate.json",
    ROOT / "targets/web/freshcart_market/tier_c/cohorts/_batches/20260512T152227Z_tierc_mtf_10x_genairc/aggregate.json",
    ROOT / "targets/web/freshcart_market/tier_d/cohorts/_batches/rerun_missing_nongemini_20260525T171016Z/aggregate.json",
    ROOT / "targets/web/freshcart_market/tier_d/cohorts/_batches/rerun_missing_gemini_20260525T132231Z/aggregate.json",
    ROOT / "targets/web/clinic_shift_command/tier_a/cohorts/_batches/20260513T003251Z_clinic_tiera_mtf_10x/aggregate.json",
    ROOT / "targets/web/clinic_shift_command/tier_b/cohorts/_batches/20260513T022902Z_clinic_tierb_plus_mtf_10x/aggregate.json",
    ROOT / "targets/web/clinic_shift_command/tier_c/cohorts/_batches/20260513T072758Z_clinic_tierc_readiness_mtf_10x/aggregate.json",
    ROOT / "targets/web/clinic_shift_command/tier_d/cohorts/_batches/rerun_missing_nongemini_20260525T171016Z/aggregate.json",
    ROOT / "targets/web/clinic_shift_command/tier_d/cohorts/_batches/rerun_missing_gemini_20260525T132231Z/aggregate.json",
    ROOT / "targets/web/homefix_hub/cohorts/_batches/20260514_homefix_all_tiers_10x/aggregate.json",
    ROOT / "targets/web/homefix_hub/cohorts/_batches/20260514_homefix_cd_recalibrated2_f_10x/aggregate.json",
    ROOT / "targets/web/campus_registrar_command/cohorts/_batches/rerun_missing_20260525T122900Z/aggregate.json",
    ROOT / "targets/web/campus_registrar_command/cohorts/_batches/rerun_missing_gemini_20260525T132231Z/aggregate.json",
    ROOT / "targets/web/media_campaign_launch_desk/cohorts/_batches/rerun_missing_nongemini_20260525T171016Z/aggregate.json",
    ROOT / "targets/web/media_campaign_launch_desk/cohorts/_batches/rerun_missing_gemini_20260525T132231Z/aggregate.json",
]


REPAIR_PROMPT = """You are repairing a previously generated blind DetoxBench static web app.

You may use only:
- the current app source files below,
- the public DSL contract below,
- the public scenario examples below,
- the single summarized evaluator failure below, which was produced only by
  running public scenarios.

Do not use private scenario files, reference implementations, existing
evaluator logs, hidden answers, or hard-coded scenario scripts. Generalize from
the public contract and the summarized failure. Keep all declared selectors
directly actionable and keep window.__DETOX_STATE__ synchronized with the UI.

Return only JSON matching this shape:
{{
  "files": [
    {{"path": "index.html", "content": "..."}},
    {{"path": "styles.css", "content": "..."}},
    {{"path": "app.js", "content": "..."}}
  ],
  "notes": "short patch summary"
}}

Patch context:
{context}

Summarized evaluator feedback:
```json
{feedback}
```

Public DSL contract:
```yaml
{contract}
```

Public scenario examples:
```yaml
{public_scenarios}
```

Current app files:

index.html
```html
{index_html}
```

styles.css
```css
{styles_css}
```

app.js
```javascript
{app_js}
```
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run public-feedback iterative repair over retained A-D targets.")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--resume", action="store_true", help="Resume an existing output root instead of failing.")
    parser.add_argument("--dry-run", action="store_true", help="Only write manifest and missing-original records.")
    parser.add_argument("--rounds", type=int, default=2, help="Number of repair rounds after round 0 evaluation.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel task workers. Each task runs rounds sequentially.")
    parser.add_argument("--evaluation-timeout", type=int, default=300)
    parser.add_argument("--request-timeout-cap", type=int, help="Optional cap for model repair API request timeouts.")
    parser.add_argument("--families", nargs="+", help="Optional target family slugs, e.g. homefix_hub stayflow_concierge.")
    parser.add_argument("--tiers", nargs="+", choices=["A", "B", "C", "D"], help="Optional tiers.")
    parser.add_argument("--models", nargs="+", help="Optional model slugs.")
    parser.add_argument("--seeds", nargs="+", default=["1-10"], help="Seeds like 1 2 3 or ranges like 1-10.")
    parser.add_argument("--limit", type=int, help="Optional task limit after filtering, useful for smoke tests.")
    parser.add_argument("--aggregate-json", type=Path, action="append", help="Override/add source aggregate JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_genai_rc()

    run_root = args.output_root or RESULT_ROOT / ("run_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    run_root = run_root.resolve()
    if run_root.exists() and not args.resume:
        raise SystemExit(f"Output root already exists: {run_root}. Pass --resume to continue.")
    run_root.mkdir(parents=True, exist_ok=True)

    seeds = parse_seeds(args.seeds)
    models = [model for model in MODELS if not args.models or model.slug in set(args.models)]
    if args.request_timeout_cap:
        models = [replace(model, request_timeout=min(model.request_timeout, args.request_timeout_cap)) for model in models]
    targets = discover_targets(args)
    source_rows, source_warnings = load_source_rows(args.aggregate_json or DEFAULT_AGGREGATES)
    tasks, missing = build_tasks(targets, models, seeds, source_rows, args.limit)

    manifest = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_root": str(run_root),
        "rounds": args.rounds,
        "dry_run": args.dry_run,
        "workers": args.workers,
        "repair_feedback_scenario_set": "public",
        "reported_evaluation_scenario_set": "all",
        "target_count": len(targets),
        "model_count": len(models),
        "seeds": seeds,
        "expected_task_count": len(targets) * len(models) * len(seeds),
        "scheduled_task_count": len(tasks),
        "missing_original_count": len(missing),
        "source_warnings": source_warnings,
        "source_aggregates": [str(path) for path in (args.aggregate_json or DEFAULT_AGGREGATES)],
        "targets": [target_manifest(target) for target in targets],
        "models": [model.__dict__ for model in models],
        "missing_originals": missing,
    }
    write_json_no_overwrite(run_root / "manifest.json", manifest, resume=args.resume)
    write_json_no_overwrite(run_root / "missing_originals.json", missing, resume=args.resume)

    if args.dry_run:
        print(json.dumps({"run_root": str(run_root), "tasks": len(tasks), "missing_originals": len(missing)}, indent=2))
        return 0

    progress_path = run_root / "progress.jsonl"
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_task, task, run_root, args.rounds, args.evaluation_timeout, args.resume): task
            for task in tasks
        }
        for future in as_completed(futures):
            try:
                record = future.result()
            except KeyboardInterrupt:
                raise
            except BaseException as exc:
                task = futures[future]
                record = {
                    "task": task_stem(task),
                    "status": "task_failed",
                    "error": repr(exc),
                    "rounds_written": None,
                    "last_round": None,
                    "last_full_pass": None,
                }
            append_jsonl(progress_path, record)
            print(status_line(record), flush=True)

    aggregate = aggregate_run_records(run_root)
    write_json_no_overwrite(run_root / "aggregate.json", aggregate, resume=args.resume)
    return 0


def load_genai_rc() -> None:
    rc_path = Path.home() / ".genai_rc"
    if not rc_path.is_file():
        return
    for line in rc_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            os.environ[key] = value


def parse_seeds(values: list[str]) -> list[int]:
    seeds: set[int] = set()
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                seeds.update(range(int(start), int(end) + 1))
            else:
                seeds.add(int(part))
    return sorted(seeds)


def discover_targets(args: argparse.Namespace) -> list[dict[str, Any]]:
    family_filter = set(args.families or [])
    tier_filter = set(args.tiers or [])
    targets: list[dict[str, Any]] = []
    for target_dir in sorted((ROOT / "targets/web").glob("*/tier_*")):
        family = target_dir.parent.name
        tier = target_dir.name.removeprefix("tier_").upper()
        if family_filter and family not in family_filter:
            continue
        if tier_filter and tier not in tier_filter:
            continue
        targets.append(
            {
                "family": family,
                "tier": tier,
                "instance": f"{family}/tier_{tier.lower()}",
                "target_dir": target_dir,
                "contract": target_dir / "contract.dsl.yaml",
                "public_scenarios": target_dir / "scenarios.public.dsl.yaml",
                "contract_exists": (target_dir / "contract.dsl.yaml").is_file(),
                "public_scenarios_exists": (target_dir / "scenarios.public.dsl.yaml").is_file(),
            }
        )
    return targets


def target_manifest(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "family": target["family"],
        "tier": target["tier"],
        "instance": target["instance"],
        "target_dir": str(target["target_dir"]),
        "contract": str(target["contract"]),
        "public_scenarios": str(target["public_scenarios"]),
        "contract_exists": target["contract_exists"],
        "public_scenarios_exists": target["public_scenarios_exists"],
    }


def load_source_rows(paths: list[Path]) -> tuple[dict[tuple[str, str, int], dict[str, Any]], list[str]]:
    rows_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    warnings: list[str] = []
    for priority, path in enumerate(paths):
        if not path.is_file():
            warnings.append(f"missing aggregate: {path}")
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            rows = []
        fallback_rows = rows_from_candidate_tree(path)
        if fallback_rows:
            rows = [*rows, *fallback_rows]
        if not rows:
            warnings.append(f"aggregate has no rows and no candidate fallback: {path}")
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            candidate_dir = Path(str(row.get("candidate_dir", "")))
            target_dir = infer_target_dir(candidate_dir)
            if not target_dir:
                continue
            family = target_dir.parent.name
            tier = target_dir.name.removeprefix("tier_").upper()
            slug = str(row.get("slug", ""))
            rep = int(row.get("rep", 0) or 0)
            if not slug or rep <= 0:
                continue
            key = (f"{family}/tier_{tier.lower()}", slug, rep)
            enriched = {
                **row,
                "family": family,
                "tier": tier,
                "instance": key[0],
                "target_dir": str(target_dir),
                "source_aggregate": str(path),
                "source_priority": priority,
                "candidate_exists": candidate_ok(candidate_dir),
            }
            old = rows_by_key.get(key)
            if old is None or (not old.get("candidate_exists") and enriched["candidate_exists"]) or priority >= old["source_priority"]:
                rows_by_key[key] = enriched
    return rows_by_key, warnings


def rows_from_candidate_tree(aggregate_path: Path) -> list[dict[str, Any]]:
    batch_id = aggregate_path.parent.name
    target_dirs = target_dirs_for_aggregate(aggregate_path)
    rows: list[dict[str, Any]] = []
    for target_dir in target_dirs:
        for candidate_dir in sorted(target_dir.glob(f"cohorts/*/{batch_id}/candidates/*/r*")):
            if not candidate_ok(candidate_dir):
                continue
            try:
                model_tier = candidate_dir.relative_to(target_dir).parts[1]
            except (ValueError, IndexError):
                continue
            slug = candidate_dir.parent.name
            match = re.fullmatch(r"r(\d+)", candidate_dir.name)
            if not match:
                continue
            model = MODEL_BY_SLUG.get(slug)
            rows.append(
                {
                    "target_tier": target_dir.name.removeprefix("tier_").upper(),
                    "model_tier": model_tier,
                    "slug": slug,
                    "model": model.model if model else slug,
                    "provider": model.provider if model else None,
                    "rep": int(match.group(1)),
                    "subject": f"filesystem_{target_dir.parent.name}_{target_dir.name}_{model_tier}_{slug}_{candidate_dir.name}",
                    "candidate_dir": str(candidate_dir),
                    "eval_dir": None,
                    "status": "candidate_tree",
                }
            )
    return rows


def target_dirs_for_aggregate(aggregate_path: Path) -> list[Path]:
    for parent in aggregate_path.parents:
        if parent.name.startswith("tier_") and (parent / "cohorts").is_dir():
            return [parent]
    for parent in aggregate_path.parents:
        if parent.parent.name == "web" and (parent / "cohorts").is_dir():
            return sorted(path for path in parent.glob("tier_*") if path.is_dir())
    return []


def infer_target_dir(candidate_dir: Path) -> Path | None:
    for parent in [candidate_dir, *candidate_dir.parents]:
        if parent.name.startswith("tier_") and (parent / "contract.dsl.yaml").is_file():
            return parent
    return None


def candidate_ok(candidate_dir: Path) -> bool:
    return all((candidate_dir / name).is_file() for name in ("index.html", "styles.css", "app.js"))


def build_tasks(
    targets: list[dict[str, Any]],
    models: list[ModelSpec],
    seeds: list[int],
    source_rows: dict[tuple[str, str, int], dict[str, Any]],
    limit: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tasks: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for target in targets:
        for model in models:
            for seed in seeds:
                key = (target["instance"], model.slug, seed)
                source = source_rows.get(key)
                base = {
                    "family": target["family"],
                    "tier": target["tier"],
                    "instance": target["instance"],
                    "seed": seed,
                    "model": model.model,
                    "model_slug": model.slug,
                    "model_tier": model.model_tier,
                    "provider": model.provider,
                }
                if not target["contract_exists"] or not target["public_scenarios_exists"]:
                    missing.append({**base, "reason": "missing_contract_or_public_scenarios"})
                    continue
                if not source or not source.get("candidate_exists"):
                    missing.append({**base, "reason": "missing_original"})
                    continue
                tasks.append({**base, "target": target, "model_spec": model, "source": source})
                if limit is not None and len(tasks) >= limit:
                    return tasks, missing
    return tasks, missing


def run_task(task: dict[str, Any], run_root: Path, rounds: int, evaluation_timeout: int, resume: bool) -> dict[str, Any]:
    stem = task_stem(task)
    task_root = run_root / "runs" / task["family"] / f"tier_{task['tier'].lower()}" / task["model_slug"] / f"seed_{task['seed']:02d}"
    records: list[dict[str, Any]] = []

    round0_app = task_root / "apps" / "round_0"
    if not round0_app.exists():
        copy_app(Path(task["source"]["candidate_dir"]), round0_app)
    round0_record = evaluate_round(task, round0_app, task_root, 0, None, evaluation_timeout, resume, "all", "round_0")
    write_round_record(task_root, 0, round0_record, resume)
    records.append(round0_record)
    public_feedback_record = None
    if round0_record.get("full_pass") is not True:
        public_feedback_record = evaluate_round(
            task,
            round0_app,
            task_root,
            0,
            {"status": "public_feedback_probe", "feedback_source_scenario_set": "public"},
            evaluation_timeout,
            resume,
            "public",
            "public_feedback_round_0",
            feedback_record_path(task_root, 0),
        )
        write_feedback_record(task_root, 0, public_feedback_record, resume)

    previous_record = round0_record
    previous_public_feedback = public_feedback_from_record(public_feedback_record) if public_feedback_record else None
    previous_app = round0_app
    for repair_round in range(1, rounds + 1):
        existing_record_path = round_record_path(task_root, repair_round)
        existing_app = task_root / "apps" / f"round_{repair_round}"
        if resume and existing_record_path.is_file():
            existing_record = json.loads(existing_record_path.read_text(encoding="utf-8"))
            records.append(existing_record)
            previous_record = existing_record
            if candidate_ok(existing_app):
                previous_app = existing_app
            existing_feedback_path = feedback_record_path(task_root, repair_round)
            if existing_feedback_path.is_file():
                previous_public_feedback = public_feedback_from_record(
                    json.loads(existing_feedback_path.read_text(encoding="utf-8"))
                )
            elif existing_record.get("full_pass") is True:
                previous_public_feedback = None
            elif repair_round < rounds and candidate_ok(existing_app):
                public_feedback_record = evaluate_round(
                    task,
                    existing_app,
                    task_root,
                    repair_round,
                    {"status": "public_feedback_probe", "feedback_source_scenario_set": "public"},
                    evaluation_timeout,
                    resume,
                    "public",
                    f"public_feedback_round_{repair_round}",
                    existing_feedback_path,
                )
                write_feedback_record(task_root, repair_round, public_feedback_record, resume)
                previous_public_feedback = public_feedback_from_record(public_feedback_record)
            else:
                previous_public_feedback = None
            continue
        if previous_record.get("full_pass") is True:
            skipped = skipped_record(task, repair_round, previous_record, "already_full_pass")
            write_round_record(task_root, repair_round, skipped, resume)
            records.append(skipped)
            previous_record = skipped
            previous_public_feedback = None
            continue
        feedback = previous_public_feedback
        if not feedback:
            skipped = skipped_record(task, repair_round, previous_record, "no_public_failure_feedback")
            skipped["patch_metadata"]["feedback_source_scenario_set"] = "public"
            write_round_record(task_root, repair_round, skipped, resume)
            records.append(skipped)
            previous_record = skipped
            previous_public_feedback = None
            continue

        assert_public_feedback(feedback, task)
        app_dir = task_root / "apps" / f"round_{repair_round}"
        patch_metadata = repair_app(task, previous_app, app_dir, feedback, repair_round, resume)
        if patch_metadata.get("status") not in {"ok", "partial_file_set"}:
            failed = base_run_record(task, repair_round)
            failed.update(
                {
                    "status": "patch_failed",
                    "full_pass": False,
                    "scenario_score": None,
                    "step_score": None,
                    "first_failure_category": feedback.get("failure_category"),
                    "failure_feedback": feedback,
                    "recovered_from_previous_round": False,
                    "patch_metadata": patch_metadata,
                }
            )
            write_round_record(task_root, repair_round, failed, resume)
            records.append(failed)
            previous_record = failed
            continue
        record = evaluate_round(task, app_dir, task_root, repair_round, patch_metadata, evaluation_timeout, resume, "all", f"round_{repair_round}")
        record["recovered_from_previous_round"] = bool(not previous_record.get("full_pass") and record.get("full_pass"))
        write_round_record(task_root, repair_round, record, resume)
        records.append(record)
        public_feedback_record = None
        if repair_round < rounds and record.get("full_pass") is not True:
            public_feedback_record = evaluate_round(
                task,
                app_dir,
                task_root,
                repair_round,
                {"status": "public_feedback_probe", "feedback_source_scenario_set": "public"},
                evaluation_timeout,
                resume,
                "public",
                f"public_feedback_round_{repair_round}",
                feedback_record_path(task_root, repair_round),
            )
            write_feedback_record(task_root, repair_round, public_feedback_record, resume)
        previous_record = record
        previous_public_feedback = public_feedback_from_record(public_feedback_record) if public_feedback_record else None
        previous_app = app_dir

    return {
        "task": stem,
        "status": "ok",
        "rounds_written": len(records),
        "last_round": records[-1].get("round") if records else None,
        "last_full_pass": records[-1].get("full_pass") if records else None,
    }


def task_stem(task: dict[str, Any]) -> str:
    return f"{task['family']}/tier_{task['tier'].lower()}/{task['model_slug']}/seed_{task['seed']:02d}"


def copy_app(source: Path, destination: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)


def evaluate_round(
    task: dict[str, Any],
    app_dir: Path,
    task_root: Path,
    round_index: int,
    patch_metadata: dict[str, Any] | None,
    evaluation_timeout: int,
    resume: bool,
    scenario_set: str,
    eval_label: str,
    record_path: Path | None = None,
) -> dict[str, Any]:
    if resume and record_path and record_path.is_file():
        return json.loads(record_path.read_text(encoding="utf-8"))
    eval_dir = task_root / "eval" / eval_label
    summary = latest_summary(eval_dir)
    evaluation_failure_feedback = None
    if summary is None:
        cmd = [
            sys.executable,
            "-m",
            "detoxbench",
            "evaluate-dsl",
            "--target",
            str(task["target"]["target_dir"]),
            "--scenario-set",
            scenario_set,
            "--static-dir",
            str(app_dir),
            "--output",
            str(eval_dir),
            "--run-subject",
            f"iterrepair_publicfb_{scenario_set}_{task['family']}_{task['tier']}_{task['model_slug']}_s{task['seed']:02d}_r{round_index}",
            "--headless",
            "--json",
        ]
        started = time.time()
        returncode, stdout_tail, stderr_tail = run_evaluation_command(cmd, evaluation_timeout)
        summary = latest_summary(eval_dir)
        if summary is None:
            failure_category = "evaluation_timeout" if returncode is None else "evaluation_failed"
            evaluation_failure_feedback = {
                "scenario_id": None,
                "scenario_tier": task["tier"],
                "first_failed_step": None,
                "failed_action": "evaluate-dsl",
                "failed_component": None,
                "failed_assertion": "evaluation_run",
                "expected_value": "summary.json",
                "observed_value": stderr_tail or stdout_tail or f"returncode={returncode}",
                "message": f"Evaluator did not produce a summary for round {round_index}.",
                "failure_category": failure_category,
                "scenario_set": scenario_set,
            }
        write_json_no_overwrite(
            eval_dir / "evaluation_command.json",
            {
                "cmd": cmd,
                "returncode": returncode,
                "elapsed_sec": round(time.time() - started, 3),
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
            },
            resume=resume,
        )
    if summary is None:
        record = base_run_record(task, round_index)
        record.update(
            {
                "status": "evaluation_failed",
                "scenario_set": scenario_set,
                "full_pass": False,
                "scenario_score": None,
                "step_score": None,
                "first_failure_category": (
                    evaluation_failure_feedback.get("failure_category") if evaluation_failure_feedback else None
                ),
                "failure_feedback": evaluation_failure_feedback,
                "recovered_from_previous_round": None if round_index == 0 else False,
                "patch_metadata": patch_metadata or {"status": "source_original"},
            }
        )
        return record
    record = record_from_summary(task, round_index, app_dir, eval_dir, summary, patch_metadata)
    record["scenario_set"] = scenario_set
    if record.get("failure_feedback"):
        record["failure_feedback"]["scenario_set"] = scenario_set
    return record


def latest_summary(eval_dir: Path) -> dict[str, Any] | None:
    for summary_path in sorted(eval_dir.glob("*/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def run_evaluation_command(cmd: list[str], timeout: int) -> tuple[int | None, str, str]:
    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, tail(stdout or ""), tail(stderr or "")
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="ignore")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="ignore")
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            more_stdout, more_stderr = process.communicate(timeout=5)
            stdout += more_stdout or ""
            stderr += more_stderr or ""
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            more_stdout, more_stderr = process.communicate()
            stdout += more_stdout or ""
            stderr += more_stderr or ""
        stderr = (stderr + "\n" if stderr else "") + f"evaluation timed out after {timeout}s"
        return None, tail(stdout), tail(stderr)


def record_from_summary(
    task: dict[str, Any],
    round_index: int,
    app_dir: Path,
    eval_dir: Path,
    summary: dict[str, Any],
    patch_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    score = summary.get("score", {})
    scenarios = summary.get("scenarios", [])
    passed = [scenario for scenario in scenarios if scenario.get("passed")]
    failure_feedback = summarize_first_failure(summary)
    record = base_run_record(task, round_index)
    record.update(
        {
            "status": "evaluated",
            "full_pass": bool(summary.get("passed")),
            "scenario_score": {
                "passed": len(passed),
                "total": len(scenarios),
                "ratio": (len(passed) / len(scenarios)) if scenarios else None,
                "formal_earned": nested_get(score, "formal", "earned"),
                "formal_possible": nested_get(score, "formal", "possible"),
                "formal_ratio": nested_get(score, "formal", "ratio"),
            },
            "step_score": {
                "earned": nested_get(score, "stepwise", "earned"),
                "possible": nested_get(score, "stepwise", "possible"),
                "ratio": nested_get(score, "stepwise", "ratio"),
            },
            "first_failure_category": failure_feedback.get("failure_category") if failure_feedback else None,
            "failure_feedback": failure_feedback,
            "recovered_from_previous_round": None if round_index == 0 else False,
            "patch_metadata": patch_metadata or {
                "status": "source_original",
                "source_candidate_dir": task["source"]["candidate_dir"],
                "source_aggregate": task["source"]["source_aggregate"],
            },
            "app_dir": str(app_dir),
            "eval_dir": str(eval_dir),
            "run_id": summary.get("run_id"),
            "summary_path": str(Path(summary.get("output_dir", "")) / "summary.json"),
        }
    )
    return record


def summarize_first_failure(summary: dict[str, Any]) -> dict[str, Any] | None:
    failed = next((scenario for scenario in summary.get("scenarios", []) if not scenario.get("passed")), None)
    if not failed:
        return None
    first_failure = failed.get("first_failure") or {}
    failed_assertions = failed.get("failed_assertions") or []
    assertion = first_failure or (failed_assertions[0] if failed_assertions else {})
    return {
        "scenario_id": failed.get("id"),
        "scenario_tier": failed.get("tier"),
        "first_failed_step": failed.get("first_failed_step") or first_failure.get("step_index"),
        "failed_action": assertion.get("action"),
        "failed_component": assertion.get("component"),
        "failed_assertion": assertion.get("assertion_type") or assertion.get("type") or assertion.get("kind"),
        "expected_value": assertion.get("expected"),
        "observed_value": assertion.get("actual"),
        "message": assertion.get("message"),
        "failure_category": failed.get("failure_category"),
        "scenario_set": summary.get("scenario_set"),
    }


def public_feedback_from_record(record: dict[str, Any]) -> dict[str, Any] | None:
    feedback = record.get("failure_feedback")
    if not feedback:
        return None
    scenario_set = feedback.get("scenario_set") or record.get("scenario_set")
    if scenario_set and scenario_set != "public":
        return None
    if record.get("scenario_set") == "public" and feedback.get("scenario_set") != "public":
        feedback = {**feedback, "scenario_set": "public"}
    return feedback


def assert_public_feedback(feedback: dict[str, Any], task: dict[str, Any]) -> None:
    scenario_set = feedback.get("scenario_set")
    scenario_id = feedback.get("scenario_id")
    if scenario_set and scenario_set != "public":
        raise RuntimeError(f"Refusing non-public repair feedback for {task_stem(task)}: scenario_set={scenario_set}")
    if scenario_id and not str(scenario_id).startswith("public_"):
        raise RuntimeError(f"Refusing non-public repair feedback for {task_stem(task)}: scenario_id={scenario_id}")


def repair_app(
    task: dict[str, Any],
    source_app: Path,
    destination: Path,
    feedback: dict[str, Any],
    repair_round: int,
    resume: bool,
) -> dict[str, Any]:
    metadata_path = destination / "patch_metadata.json"
    if resume and metadata_path.is_file() and candidate_ok(destination):
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    if destination.exists() and not resume:
        raise SystemExit(f"Refusing to overwrite existing patched app: {destination}")

    contract = task["target"]["contract"].read_text(encoding="utf-8")
    public_scenarios = task["target"]["public_scenarios"].read_text(encoding="utf-8")
    files = read_app_files(source_app)
    context = {
        "family": task["family"],
        "tier": task["tier"],
        "instance": task["instance"],
        "seed": task["seed"],
        "repair_round": repair_round,
        "model": task["model"],
        "model_slug": task["model_slug"],
        "model_tier": task["model_tier"],
    }
    prompt = REPAIR_PROMPT.format(
        context=json.dumps(context, ensure_ascii=False, indent=2),
        feedback=json.dumps(feedback, ensure_ascii=False, indent=2),
        contract=contract,
        public_scenarios=public_scenarios,
        index_html=files["index.html"],
        styles_css=files["styles.css"],
        app_js=files["app.js"],
    )
    prompt_sha = sha256(prompt.encode("utf-8")).hexdigest()
    model: ModelSpec = task["model_spec"]
    try:
        semaphore = API_SEMAPHORES.get(model.provider)
        if semaphore:
            with semaphore:
                payload, response_metadata = generate_payload(
                    provider=model.provider,
                    model=model.model,
                    prompt=prompt,
                    max_output_tokens=model.max_output_tokens,
                    base_url=model.base_url,
                    request_timeout=model.request_timeout,
                )
        else:
            payload, response_metadata = generate_payload(
                provider=model.provider,
                model=model.model,
                prompt=prompt,
                max_output_tokens=model.max_output_tokens,
                base_url=model.base_url,
                request_timeout=model.request_timeout,
            )
    except SystemExit as exc:
        metadata = {
            "status": "failed",
            "error": str(exc),
            "prompt_sha256": prompt_sha,
            "repair_round": repair_round,
            "provider": model.provider,
            "model": model.model,
            "model_slug": model.slug,
            "model_tier": model.model_tier,
            "feedback": feedback,
            "feedback_source_scenario_set": "public",
        }
        destination.mkdir(parents=True, exist_ok=True)
        write_json_no_overwrite(metadata_path, metadata, resume=resume)
        return metadata
    except Exception as exc:
        metadata = {
            "status": "failed",
            "error": repr(exc),
            "prompt_sha256": prompt_sha,
            "repair_round": repair_round,
            "provider": model.provider,
            "model": model.model,
            "model_slug": model.slug,
            "model_tier": model.model_tier,
            "feedback": feedback,
            "feedback_source_scenario_set": "public",
        }
        destination.mkdir(parents=True, exist_ok=True)
        write_json_no_overwrite(metadata_path, metadata, resume=resume)
        return metadata

    destination.mkdir(parents=True, exist_ok=True)
    expected = {"index.html", "styles.css", "app.js"}
    received = {normalize_file_path(item.get("path")) for item in payload.get("files", [])}
    received.discard(None)
    unknown_files = sorted(path for path in received if path not in expected)
    accepted_files = sorted(path for path in received if path in expected)
    status = "ok" if received == expected else "partial_file_set" if accepted_files and not unknown_files else "bad_file_set"
    metadata = {
        "status": status,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "repair_round": repair_round,
        "provider": model.provider,
        "model": model.model,
        "model_slug": model.slug,
        "model_tier": model.model_tier,
        "source_app": str(source_app),
        "feedback": feedback,
        "feedback_source_scenario_set": "public",
        "prompt_sha256": prompt_sha,
        "response": response_metadata,
        "notes": payload.get("notes"),
        "files": accepted_files,
        "unknown_files": unknown_files,
    }
    if status in {"ok", "partial_file_set"}:
        if status == "partial_file_set":
            ensure_app_base(source_app, destination)
        for item in payload["files"]:
            path = normalize_file_path(item.get("path"))
            if path in expected:
                (destination / path).write_text(item["content"], encoding="utf-8")
    write_json_no_overwrite(metadata_path, metadata, resume=resume)
    return metadata


def normalize_file_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    path = value.strip().replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return path


def ensure_app_base(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.js"):
        target = destination / name
        if not target.exists():
            shutil.copy2(source / name, target)


def read_app_files(app_dir: Path) -> dict[str, str]:
    return {
        name: (app_dir / name).read_text(encoding="utf-8", errors="ignore")
        for name in ("index.html", "styles.css", "app.js")
    }


def base_run_record(task: dict[str, Any], round_index: int) -> dict[str, Any]:
    return {
        "model": task["model"],
        "model_slug": task["model_slug"],
        "model_tier": task["model_tier"],
        "provider": task["provider"],
        "family": task["family"],
        "tier": task["tier"],
        "instance": task["instance"],
        "seed": task["seed"],
        "round": round_index,
    }


def skipped_record(task: dict[str, Any], round_index: int, previous_record: dict[str, Any], reason: str) -> dict[str, Any]:
    record = base_run_record(task, round_index)
    record.update(
        {
            "status": "skipped",
            "skip_reason": reason,
            "full_pass": previous_record.get("full_pass"),
            "scenario_score": previous_record.get("scenario_score"),
            "step_score": previous_record.get("step_score"),
            "first_failure_category": previous_record.get("first_failure_category"),
            "failure_feedback": previous_record.get("failure_feedback"),
            "recovered_from_previous_round": False,
            "patch_metadata": {"status": "skipped", "reason": reason},
        }
    )
    return record


def round_record_path(task_root: Path, round_index: int) -> Path:
    return task_root / "records" / f"round_{round_index}.json"


def feedback_record_path(task_root: Path, round_index: int) -> Path:
    return task_root / "records" / f"public_feedback_round_{round_index}.json"


def write_round_record(task_root: Path, round_index: int, record: dict[str, Any], resume: bool) -> None:
    write_json_no_overwrite(round_record_path(task_root, round_index), record, resume=resume)


def write_feedback_record(task_root: Path, round_index: int, record: dict[str, Any], resume: bool) -> None:
    write_json_no_overwrite(feedback_record_path(task_root, round_index), record, resume=resume)


def write_json_no_overwrite(path: Path, payload: Any, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not resume:
        raise SystemExit(f"Refusing to overwrite existing file: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def aggregate_run_records(run_root: Path) -> dict[str, Any]:
    records = []
    for path in sorted((run_root / "runs").glob("*/tier_*/**/records/round_*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    by_round: dict[str, dict[str, Any]] = {}
    for round_index in sorted({record.get("round") for record in records}):
        group = [record for record in records if record.get("round") == round_index and record.get("scenario_score")]
        by_round[str(round_index)] = {
            "evaluated": len(group),
            "full_pass": sum(1 for record in group if record.get("full_pass")),
            "scenario_ratio_mean": mean([nested_get(record, "scenario_score", "ratio") for record in group]),
            "step_ratio_mean": mean([nested_get(record, "step_score", "ratio") for record in group]),
            "recovered": sum(1 for record in group if record.get("recovered_from_previous_round")),
        }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_root": str(run_root),
        "record_count": len(records),
        "by_round": by_round,
    }


def nested_get(mapping: dict[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def mean(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return sum(numbers) / len(numbers) if numbers else None


def tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def status_line(record: dict[str, Any]) -> str:
    return (
        f"[iterrepair] {record['task']} status={record['status']} "
        f"rounds={record.get('rounds_written')} last_round={record.get('last_round')} "
        f"full_pass={record.get('last_full_pass')}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
