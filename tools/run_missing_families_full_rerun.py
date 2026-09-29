#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "results_missing_families_full_rerun"
MANIFEST_PATH = RESULT_ROOT / "manifest.jsonl"
SUMMARY_DIR = RESULT_ROOT / "summary"
TIERS = ["A", "B", "C", "D"]
SEEDS = list(range(1, 11))

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class ModelSpec:
    model_tier: str
    slug: str
    provider: str
    model: str
    max_output_tokens: int
    request_timeout: int
    base_url: str | None = None


@dataclass(frozen=True)
class FamilySpec:
    slug: str
    label: str
    snapshot_sources: dict[str, str]


@dataclass(frozen=True)
class Cell:
    family: str
    tier: str
    model: ModelSpec
    seed: int
    target_dir: Path
    visual: str


@dataclass
class Job:
    job_id: str
    deps: list[str]
    run: Callable[[], dict[str, Any]]


MODELS: list[ModelSpec] = [
    ModelSpec("M", "gpt54_nano", "openai", "gpt-5.4-nano", 64000, 900),
    ModelSpec("M", "claude_haiku45", "anthropic", "claude-haiku-4-5", 64000, 900, "https://api.anthropic.com"),
    ModelSpec("M", "gemini31_flash_lite", "google", "gemini-3.1-flash-lite", 64000, 900),
    ModelSpec("T", "gpt54_mini", "openai", "gpt-5.4-mini", 64000, 900),
    ModelSpec("T", "claude_sonnet46", "anthropic", "claude-sonnet-4-6", 64000, 900, "https://api.anthropic.com"),
    ModelSpec("T", "gemini_flash_latest", "google", os.environ.get("GEMINI_FLASH_MODEL", "gemini-flash-latest"), 64000, 900),
    ModelSpec("F", "gpt54", "openai", "gpt-5.4", 80000, 1200),
    ModelSpec("F", "claude_opus46", "anthropic", "claude-opus-4-6", 80000, 1200, "https://api.anthropic.com"),
    ModelSpec("F", "gemini31_pro_preview", "google", "gemini-3.1-pro-preview", 80000, 1200),
]

FAMILIES: list[FamilySpec] = [
    FamilySpec("clinic_shift_command", "Clinical Command", {"A": "codex/clinic-shift-tier-a"}),
    FamilySpec("campus_registrar_command", "Campus Registrar", {}),
    FamilySpec("media_campaign_launch_desk", "Media Campaign", {}),
]

CLINIC_TIER_A_VISUAL = (
    "Clinic Shift Command Tier A blind cohort. Build a polished, production-quality "
    "ambulatory clinic operations SaaS UI comparable to the reference target quality. "
    "Follow the contract app.ui_ux_brief exactly as the shared visual and interaction "
    "quality brief. The app should feel like a real clinical command center used by "
    "front desk, nursing, clinician, billing, and operations staff, not a grocery app, "
    "hotel app, generic dashboard, state debugger, or bare test harness. Use a dense "
    "but calm desktop-first layout with credible patient queue management, schedule "
    "visibility, room status, chart preparation, insurance verification, clinician "
    "controls, handoff tasks, and role-aware actions. Implement Clinic Shift Command "
    "Tier A behavior exactly: role switching, triage queue filtering and sorting, "
    "patient chart selection, assessment documentation, insurance flag resolution, "
    "room status transitions, clinician assignment, delayed-room escalation, handoff "
    "task completion, route history, and reload persistence. Keep all DetoxBench "
    "selectors directly actionable and keep rendered table/list cells synchronized "
    "with public state. You receive only the public contract and public scenario "
    "examples; do not use private scenarios, evaluator logs, reference screenshots, "
    "or hard-coded hidden answers."
)


manifest_lock = threading.Lock()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run missing-family full rerun batches into an isolated result root.")
    parser.add_argument("--output-root", type=Path, default=RESULT_ROOT)
    parser.add_argument(
        "--batches",
        nargs="+",
        choices=["static", "repair", "backend"],
        default=["static", "repair", "backend"],
    )
    parser.add_argument("--families", nargs="+", choices=[family.slug for family in FAMILIES])
    parser.add_argument("--tiers", nargs="+", choices=TIERS)
    parser.add_argument("--models", nargs="+", choices=[model.slug for model in MODELS])
    parser.add_argument("--seeds", nargs="+", default=["1-10"])
    parser.add_argument("--max-parallel-jobs", type=int, default=int(os.environ.get("MAX_PARALLEL_JOBS", "2")))
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--evaluation-timeout", type=int, default=300)
    parser.add_argument("--request-timeout-cap", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_genai_rc()
    result_root = args.output_root.resolve()
    configure_result_root(result_root)
    selected_families = [family for family in FAMILIES if not args.families or family.slug in set(args.families)]
    selected_tiers = args.tiers or TIERS
    selected_models = [model for model in MODELS if not args.models or model.slug in set(args.models)]
    if args.request_timeout_cap:
        selected_models = [
            ModelSpec(m.model_tier, m.slug, m.provider, m.model, m.max_output_tokens, min(m.request_timeout, args.request_timeout_cap), m.base_url)
            for m in selected_models
        ]
    seeds = parse_seeds(args.seeds)

    result_root.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    cells = build_cells(selected_families, selected_tiers, selected_models, seeds, result_root)
    run_config = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "result_root": str(result_root),
        "batches": args.batches,
        "families": [family.slug for family in selected_families],
        "tiers": selected_tiers,
        "models": [model.__dict__ for model in selected_models],
        "seeds": seeds,
        "max_parallel_jobs": args.max_parallel_jobs,
        "max_retries": args.max_retries,
        "evaluation_timeout": args.evaluation_timeout,
        "request_timeout_cap": args.request_timeout_cap,
        "expected_cells": len(cells),
        "expected_static_runs": len(cells) if "static" in args.batches else 0,
        "expected_repair_round_records": len(cells) * 3 if "repair" in args.batches else 0,
        "expected_backend_runs": len(cells) if "backend" in args.batches else 0,
        "target_policy": "read existing target DSLs; when a current-worktree target is absent, copy the existing git branch snapshot under this result root only",
        "protocol": {
            "static_blind_at1": "public contract plus public scenarios only; evaluated on scenario-set=all",
            "public_feedback_repair_at1_at2_at3": "public-scenario first-failure feedback only; reported evaluation on scenario-set=all",
            "backend_backed": "same evaluator and assertions; Express plus JSON-file storage substrate",
        },
    }
    write_run_config(result_root, run_config)

    if args.dry_run:
        print(json.dumps({"result_root": str(result_root), "cells": len(cells), "batches": args.batches}, indent=2))
        write_summaries(result_root, cells)
        return 0

    run_jobs(args, result_root, cells)
    write_static_aggregate(result_root, cells)
    write_backend_aggregate(result_root, cells)
    write_summaries(result_root, cells)
    report = completion_report(result_root, cells)
    print(render_completion_report(report))
    return 0


def configure_result_root(result_root: Path) -> None:
    global RESULT_ROOT, MANIFEST_PATH, SUMMARY_DIR
    RESULT_ROOT = result_root
    MANIFEST_PATH = RESULT_ROOT / "manifest.jsonl"
    SUMMARY_DIR = RESULT_ROOT / "summary"


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
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) and value:
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


def build_cells(families: list[FamilySpec], tiers: list[str], models: list[ModelSpec], seeds: list[int], result_root: Path) -> list[Cell]:
    visuals = load_visual_prompts()
    cells: list[Cell] = []
    for family in families:
        for tier in tiers:
            target_dir = resolve_target_dir(family, tier, result_root)
            visual = visuals.get((family.slug, tier)) or fallback_visual(family, tier)
            for model in models:
                for seed in seeds:
                    cells.append(Cell(family.slug, tier, model, seed, target_dir, visual))
    return cells


def load_visual_prompts() -> dict[tuple[str, str], str]:
    visuals: dict[tuple[str, str], str] = {("clinic_shift_command", "A"): CLINIC_TIER_A_VISUAL}
    try:
        from tools import run_campus_repeat_cohort as campus

        for target in campus.TARGETS:
            visuals[("campus_registrar_command", target.tier)] = target.visual
    except Exception:
        pass
    try:
        from tools import run_media_repeat_cohort as media

        for target in media.TARGETS:
            visuals[("media_campaign_launch_desk", target.tier)] = target.visual
    except Exception:
        pass
    for tier, module_name in [
        ("B", "tools.run_clinic_tier_b_repeat_cohort"),
        ("C", "tools.run_clinic_tier_c_repeat_cohort"),
        ("D", "tools.run_clinic_tier_d_repeat_cohort"),
    ]:
        try:
            module = __import__(module_name, fromlist=["VARIANT"])
            visuals[("clinic_shift_command", tier)] = str(module.VARIANT)
        except Exception:
            pass
    return visuals


def fallback_visual(family: FamilySpec, tier: str) -> str:
    return (
        f"{family.label} Tier {tier} blind cohort. Build a polished production-quality web app "
        "that implements the public DSL behavior exactly, keeps every declared DetoxBench selector "
        "directly actionable, and uses only the public product premise, public contract, and public scenarios."
    )


def resolve_target_dir(family: FamilySpec, tier: str, result_root: Path) -> Path:
    target_dir = ROOT / "targets" / "web" / family.slug / f"tier_{tier.lower()}"
    if has_required_target_files(target_dir):
        return target_dir
    source_branch = family.snapshot_sources.get(tier)
    if not source_branch:
        return target_dir
    return ensure_target_snapshot(family.slug, tier, source_branch, result_root)


def has_required_target_files(path: Path) -> bool:
    return (path / "contract.dsl.yaml").is_file() and (path / "scenarios.public.dsl.yaml").is_file()


def ensure_target_snapshot(family: str, tier: str, source_branch: str, result_root: Path) -> Path:
    prefix = f"targets/web/{family}/tier_{tier.lower()}"
    snapshot_dir = result_root / "target_snapshots" / family / f"tier_{tier.lower()}"
    if has_required_target_files(snapshot_dir):
        return snapshot_dir
    ensure_result_path(snapshot_dir)
    files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", source_branch, "--", prefix],
        cwd=ROOT,
        text=True,
    ).splitlines()
    if not files:
        return ROOT / prefix
    for git_path in files:
        rel = Path(git_path).relative_to(prefix)
        destination = snapshot_dir / rel
        ensure_result_path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.check_output(["git", "show", f"{source_branch}:{git_path}"], cwd=ROOT)
        destination.write_bytes(blob)
    write_json(
        snapshot_dir / "target_snapshot_manifest.json",
        {
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source_branch": source_branch,
            "source_prefix": prefix,
            "files": files,
            "note": "Snapshot copied under result root so the completed target DSL is not modified in targets/.",
        },
    )
    return snapshot_dir


def run_jobs(args: argparse.Namespace, result_root: Path, cells: list[Cell]) -> None:
    jobs: dict[str, Job] = {}
    for cell in cells:
        cell_id = cell_key(cell)
        if "static" in args.batches or "repair" in args.batches:
            jobs[f"static:{cell_id}"] = Job(
                f"static:{cell_id}",
                [],
                lambda cell=cell: run_static_job(cell, args.max_retries, args.evaluation_timeout),
            )
        if "backend" in args.batches:
            jobs[f"backend:{cell_id}"] = Job(
                f"backend:{cell_id}",
                [],
                lambda cell=cell: run_backend_job(cell, args.max_retries, args.evaluation_timeout),
            )
        if "repair" in args.batches:
            deps = [f"static:{cell_id}"] if "static" in args.batches else []
            jobs[f"repair:{cell_id}"] = Job(
                f"repair:{cell_id}",
                deps,
                lambda cell=cell: run_repair_job(cell, args.evaluation_timeout),
            )

    completed: dict[str, dict[str, Any]] = {}
    skipped: set[str] = set()
    in_flight: dict[Any, str] = {}
    pending = set(jobs)
    with ThreadPoolExecutor(max_workers=max(1, args.max_parallel_jobs)) as pool:
        while pending or in_flight:
            ready = [
                job_id
                for job_id in sorted(pending, key=job_sort_key)
                if all(dep in completed for dep in jobs[job_id].deps)
                and not any(completed[dep].get("status") not in {"ok", "skipped_existing"} for dep in jobs[job_id].deps)
            ]
            blocked = [
                job_id
                for job_id in sorted(pending, key=job_sort_key)
                if any(dep in completed and completed[dep].get("status") not in {"ok", "skipped_existing"} for dep in jobs[job_id].deps)
            ]
            for job_id in blocked:
                pending.remove(job_id)
                skipped.add(job_id)
                record = dependency_skipped_record(job_id, completed)
                completed[job_id] = record
                print(f"[skip] {job_id} dependency_failed", flush=True)
            while ready and len(in_flight) < max(1, args.max_parallel_jobs):
                job_id = ready.pop(0)
                if job_id not in pending:
                    continue
                pending.remove(job_id)
                future = pool.submit(jobs[job_id].run)
                in_flight[future] = job_id
            if not in_flight:
                if pending and not skipped:
                    raise RuntimeError(f"No runnable jobs remain: {sorted(pending, key=job_sort_key)[:5]}")
                continue
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                job_id = in_flight.pop(future)
                try:
                    result = future.result()
                except KeyboardInterrupt:
                    raise
                except BaseException as exc:
                    result = {"status": "failed", "error": repr(exc), "job_id": job_id}
                    append_manifest(job_failure_manifest(job_id, result))
                completed[job_id] = result
                print(status_line(job_id, result), flush=True)


def dependency_skipped_record(job_id: str, completed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    batch, rest = job_id.split(":", 1)
    family, tier_part, model, seed_part = rest.split("/")
    tier = tier_part.removeprefix("tier_").upper()
    seed = int(seed_part.removeprefix("seed_"))
    record = {
        "experiment_batch": batch_name(batch),
        "family": family,
        "tier": tier,
        "model": model,
        "generation_seed": seed,
        "output_path": "",
        "status": "skipped_dependency_failed",
        "error": "dependency_failed",
        "evaluated": False,
        "full_pass": None,
        "S_scen": None,
        "S_step": None,
        "first_failure_category": None,
    }
    append_manifest(record)
    return {"status": "failed", "error": "dependency_failed"}


def job_sort_key(job_id: str) -> tuple[str, int]:
    batch, rest = job_id.split(":", 1)
    priority = {"static": 0, "backend": 1, "repair": 2}.get(batch, 9)
    try:
        family, tier_part, model, seed_part = rest.split("/")
    except ValueError:
        return (rest, priority)
    return (tier_part, model, seed_part, family, priority)


def run_static_job(cell: Cell, max_retries: int, evaluation_timeout: int) -> dict[str, Any]:
    task = static_task(cell)
    if not has_required_target_files(cell.target_dir):
        record = manifest_record("static_blind_at1", cell, None, task["candidate_dir"], "missing_target", "missing contract or public scenarios")
        append_manifest(record)
        return {"status": "failed", "error": record["error"]}
    generation = generate_static(task, max_retries)
    if generation.get("status") not in {"ok", "skipped_existing"}:
        append_manifest(manifest_record("static_blind_at1", cell, None, task["candidate_dir"], "generation_failed", generation.get("error") or generation.get("stderr_tail")))
        return {"status": "failed", "error": generation.get("error") or generation.get("stderr_tail")}
    evaluation = evaluate_static(task, evaluation_timeout)
    append_manifest(record_from_summary("static_blind_at1", cell, None, task["eval_dir"], evaluation))
    return {"status": "ok", "static_evaluated": bool(evaluation.get("evaluated")), "error": evaluation.get("error")}


def generate_static(task: dict[str, Any], max_retries: int) -> dict[str, Any]:
    if static_generation_ok(task["candidate_dir"]):
        return {"status": "skipped_existing"}
    result = None
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            remove_static_partial(task["candidate_dir"])
        timeout = int(task["request_timeout"]) * (1 if attempt == 1 else 2)
        max_tokens = capped_output_tokens(
            task["provider"],
            task["model_name"],
            int(task["max_output_tokens"]) * (1 if attempt == 1 else 2),
        )
        cmd = [
            sys.executable,
            str(ROOT / "tools/generate_blind_dsl_static_app.py"),
            "--contract-dsl",
            str(task["contract"]),
            "--public-scenarios-dsl",
            str(task["public_scenarios"]),
            "--output-dir",
            str(task["candidate_dir"]),
            "--variant",
            task["variant"],
            "--provider",
            task["provider"],
            "--model",
            task["model_name"],
            "--max-output-tokens",
            str(max_tokens),
            "--request-timeout",
            str(timeout),
            "--member-id",
            task["subject"],
            "--metadata-output",
            str(task["candidate_dir"] / "generation.json"),
        ]
        if task["base_url"]:
            cmd.extend(["--base-url", task["base_url"]])
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode == 0 and static_generation_ok(task["candidate_dir"]):
            return {"status": "ok", "attempts": attempt}
    assert result is not None
    return {
        "status": "failed",
        "returncode": result.returncode,
        "stdout_tail": tail(result.stdout),
        "stderr_tail": tail(result.stderr),
    }


def evaluate_static(task: dict[str, Any], evaluation_timeout: int) -> dict[str, Any]:
    summary = latest_summary(task["eval_dir"])
    if summary is None:
        cmd = [
            sys.executable,
            "-m",
            "detoxbench",
            "evaluate-dsl",
            "--target",
            str(task["target_dir"]),
            "--scenario-set",
            "all",
            "--static-dir",
            str(task["candidate_dir"]),
            "--output",
            str(task["eval_dir"]),
            "--run-subject",
            task["subject"],
            "--headless",
            "--json",
        ]
        started = time.time()
        result, timed_out = run_with_process_group_timeout(cmd, ROOT, evaluation_timeout)
        write_json(
            task["eval_dir"] / "evaluation_command.json",
            {
                "cmd": cmd,
                "returncode": result.returncode,
                "timed_out": timed_out,
                "timeout_sec": evaluation_timeout,
                "elapsed_sec": round(time.time() - started, 3),
                "stdout_tail": tail(result.stdout),
                "stderr_tail": tail(result.stderr),
            },
        )
        summary = latest_summary(task["eval_dir"])
        if summary is None:
            return {
                "evaluated": False,
                "status": "evaluation_timeout" if timed_out else "evaluation_failed",
                "error": "evaluation timeout" if timed_out else (tail(result.stderr) or tail(result.stdout) or f"returncode={result.returncode}"),
            }
    return summary_metrics(summary, "evaluated")


def run_repair_job(cell: Cell, evaluation_timeout: int) -> dict[str, Any]:
    if not static_generation_ok(static_task(cell)["candidate_dir"]):
        append_manifest(manifest_record("public_feedback_repair_at1_at2_at3", cell, None, repair_task_root(cell), "missing_original", "static @1 candidate missing"))
        return {"status": "failed", "error": "static @1 candidate missing"}
    repair = load_public_repair_module()
    model = cell.model
    task = {
        "family": cell.family,
        "tier": cell.tier,
        "instance": f"{cell.family}/tier_{cell.tier.lower()}",
        "seed": cell.seed,
        "model": model.model,
        "model_slug": model.slug,
        "model_tier": model.model_tier,
        "provider": model.provider,
        "target": {
            "family": cell.family,
            "tier": cell.tier,
            "instance": f"{cell.family}/tier_{cell.tier.lower()}",
            "target_dir": cell.target_dir,
            "contract": cell.target_dir / "contract.dsl.yaml",
            "public_scenarios": cell.target_dir / "scenarios.public.dsl.yaml",
            "contract_exists": (cell.target_dir / "contract.dsl.yaml").is_file(),
            "public_scenarios_exists": (cell.target_dir / "scenarios.public.dsl.yaml").is_file(),
        },
        "model_spec": repair.ModelSpec(
            model.model_tier,
            model.slug,
            model.provider,
            model.model,
            model.max_output_tokens,
            model.request_timeout,
            model.base_url,
        ),
        "source": {
            "candidate_dir": str(static_task(cell)["candidate_dir"]),
            "source_aggregate": str(RESULT_ROOT / "static_blind_at1" / "aggregate.json"),
            "candidate_exists": True,
        },
    }
    root = RESULT_ROOT / "public_feedback_repair_at1_at2_at3"
    try:
        result = repair.run_task(task, root, 2, evaluation_timeout, True)
    except BaseException as exc:
        append_manifest(manifest_record("public_feedback_repair_at1_at2_at3", cell, None, repair_task_root(cell), "failed", repr(exc)))
        return {"status": "failed", "error": repr(exc)}
    emit_repair_manifest_records(cell)
    return {"status": result.get("status", "ok")}


def load_public_repair_module() -> Any:
    module_path = ROOT / "results_iterative_repair_full_matrix" / "run_iterative_repair_public_feedback_ad_subset.py"
    spec = importlib.util.spec_from_file_location("public_feedback_repair_runner", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("public_feedback_repair_runner", module)
    spec.loader.exec_module(module)
    return module


def emit_repair_manifest_records(cell: Cell) -> None:
    task_root = repair_task_root(cell)
    for round_index in [0, 1, 2]:
        path = task_root / "records" / f"round_{round_index}.json"
        if not path.is_file():
            append_manifest(manifest_record("public_feedback_repair_at1_at2_at3", cell, round_index, path, "missing", "round record missing", public_feedback_audit_status=audit_status_for_cell(cell)))
            continue
        record = read_json(path)
        append_manifest(repair_manifest_record(cell, round_index, path, record))


def repair_manifest_record(cell: Cell, round_index: int, path: Path, record: dict[str, Any]) -> dict[str, Any]:
    scenario_score = record.get("scenario_score") or {}
    step_score = record.get("step_score") or {}
    return manifest_record(
        "public_feedback_repair_at1_at2_at3",
        cell,
        round_index,
        path,
        record.get("status", "unknown"),
        record.get("error") or record.get("skip_reason"),
        evaluated=isinstance(scenario_score, dict) and scenario_score.get("ratio") is not None,
        full_pass=record.get("full_pass"),
        s_scen=scenario_score.get("ratio") if isinstance(scenario_score, dict) else None,
        s_step=step_score.get("ratio") if isinstance(step_score, dict) else None,
        first_failure_category=record.get("first_failure_category"),
        public_feedback_audit_status=audit_status_for_cell(cell),
    )


def run_backend_job(cell: Cell, max_retries: int, evaluation_timeout: int) -> dict[str, Any]:
    if not has_required_target_files(cell.target_dir):
        append_manifest(manifest_record("backend_backed", cell, None, backend_task(cell)["candidate_dir"], "missing_target", "missing contract or public scenarios"))
        return {"status": "failed", "error": "missing target"}
    backend = load_backend_module()
    backend.RESULTS_ROOT = RESULT_ROOT / "backend_backed"
    task = backend_task(cell)
    generation = generate_backend(task, max_retries)
    if generation.get("status") not in {"ok", "skipped_existing"}:
        append_manifest(manifest_record("backend_backed", cell, None, task["candidate_dir"], "generation_failed", generation.get("stderr_tail") or generation.get("error")))
        return {"status": "failed", "error": generation.get("stderr_tail") or generation.get("error")}
    evaluation = evaluate_backend(task, backend, evaluation_timeout)
    append_manifest(backend_manifest_record(cell, task, evaluation))
    return {"status": "ok" if evaluation.get("formal_ratio") is not None else "failed", "error": evaluation.get("stderr_tail") or evaluation.get("error")}


def evaluate_backend(task: dict[str, Any], backend: Any, evaluation_timeout: int) -> dict[str, Any]:
    existing = backend.latest_summary(task["eval_dir"])
    if existing:
        return backend.eval_record(task, existing, status="skipped_existing")
    if not backend.generation_ok(task):
        return backend.task_record(task, status="missing_generation")

    install = backend.ensure_node_dependencies(task)
    if install.get("status") != "ok":
        install_detail = {key: value for key, value in install.items() if key != "status"}
        return backend.task_record(
            task,
            status="npm_install_failed",
            install_status=install.get("status"),
            **install_detail,
        )

    task["eval_dir"].mkdir(parents=True, exist_ok=True)
    backend.ensure_results_path(task["storage_dir"])
    if task["storage_dir"].exists():
        shutil.rmtree(task["storage_dir"])
    task["storage_dir"].mkdir(parents=True, exist_ok=True)

    with backend.running_backend(task) as running:
        if running["status"] != "ok":
            backend_detail = {key: value for key, value in running.items() if key != "status"}
            return backend.task_record(
                task,
                status="backend_start_failed",
                backend_status=running.get("status"),
                **backend_detail,
            )
        app_url = backend.app_start_url(task["contract"], running["base_url"])
        reset_status = backend.reset_backend(running["base_url"])
        cmd = [
            sys.executable,
            "-m",
            "detoxbench",
            "evaluate-dsl",
            "--target",
            str(task["target_dir"]),
            "--scenario-set",
            "all",
            "--app-url",
            app_url,
            "--output",
            str(task["eval_dir"]),
            "--run-subject",
            task["subject"],
            "--headless",
            "--json",
        ]
        result, timed_out = run_with_process_group_timeout(cmd, ROOT, evaluation_timeout)
    summary = backend.latest_summary(task["eval_dir"])
    if summary:
        return backend.eval_record(
            task,
            summary,
            status="ok",
            returncode=result.returncode,
            timed_out=timed_out,
            timeout_sec=evaluation_timeout,
            app_url=app_url,
            backend_reset=reset_status,
            stdout_tail=tail(result.stdout),
            stderr_tail=tail(result.stderr),
        )
    return backend.task_record(
        task,
        status="evaluation_timeout" if timed_out else "eval_failed",
        returncode=result.returncode,
        timed_out=timed_out,
        timeout_sec=evaluation_timeout,
        app_url=app_url,
        backend_reset=reset_status,
        stdout_tail=tail(result.stdout),
        stderr_tail=tail(result.stderr),
    )


def generate_backend(task: dict[str, Any], max_retries: int) -> dict[str, Any]:
    if backend_generation_ok(task["candidate_dir"]):
        return {"status": "skipped_existing"}
    result = None
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            remove_backend_partial(task["candidate_dir"])
        timeout = int(task["request_timeout"]) * (1 if attempt == 1 else 2)
        max_tokens = capped_output_tokens(
            task["provider"],
            task["model"],
            int(task["max_output_tokens"]) * (1 if attempt == 1 else 2),
        )
        cmd = [
            sys.executable,
            str(ROOT / "tools/generate_blind_dsl_backend_app.py"),
            "--contract-dsl",
            str(task["contract"]),
            "--public-scenarios-dsl",
            str(task["public_scenarios"]),
            "--output-dir",
            str(task["candidate_dir"]),
            "--variant",
            task["variant"],
            "--provider",
            task["provider"],
            "--model",
            task["model"],
            "--max-output-tokens",
            str(max_tokens),
            "--request-timeout",
            str(timeout),
            "--member-id",
            task["subject"],
            "--metadata-output",
            str(task["candidate_dir"] / "generation.json"),
        ]
        if task["base_url"]:
            cmd.extend(["--base-url", task["base_url"]])
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode == 0 and backend_generation_ok(task["candidate_dir"]):
            return {"status": "ok", "attempts": attempt}
    assert result is not None
    return {
        "status": "failed",
        "returncode": result.returncode,
        "stdout_tail": tail(result.stdout),
        "stderr_tail": tail(result.stderr),
    }


def backend_generation_ok(candidate_dir: Path) -> bool:
    expected = [
        "package.json",
        "server.js",
        "public/index.html",
        "public/styles.css",
        "public/app.js",
        "generation.json",
    ]
    return candidate_dir.is_dir() and all((candidate_dir / name).is_file() for name in expected)


def remove_backend_partial(candidate_dir: Path) -> None:
    for name in [
        "package.json",
        "server.js",
        "generation.json",
        "GENERATION.md",
        "public/index.html",
        "public/styles.css",
        "public/app.js",
    ]:
        path = candidate_dir / name
        if path.is_file():
            path.unlink()


def load_backend_module() -> Any:
    from tools import run_backend_backed_target_apps as backend

    return backend


def static_task(cell: Cell) -> dict[str, Any]:
    model = cell.model
    base = RESULT_ROOT / "static_blind_at1"
    subject = f"missingfam_static_{cell.family}_tier_{cell.tier.lower()}_{model.model_tier.lower()}_{model.slug}_s{cell.seed:02d}"
    return {
        "family": cell.family,
        "target_tier": cell.tier,
        "model_tier": model.model_tier,
        "slug": model.slug,
        "provider": model.provider,
        "model_name": model.model,
        "base_url": model.base_url,
        "max_output_tokens": model.max_output_tokens,
        "request_timeout": model.request_timeout,
        "seed": cell.seed,
        "subject": subject,
        "target_dir": cell.target_dir,
        "contract": cell.target_dir / "contract.dsl.yaml",
        "public_scenarios": cell.target_dir / "scenarios.public.dsl.yaml",
        "candidate_dir": base / "candidates" / cell.family / f"tier_{cell.tier.lower()}" / model.slug / f"seed_{cell.seed:02d}",
        "eval_dir": base / "runs" / cell.family / f"tier_{cell.tier.lower()}" / model.slug / f"seed_{cell.seed:02d}",
        "variant": f"{cell.visual} This is generation seed {cell.seed:02d} for Model Tier {model.model_tier} and model {model.slug}.",
    }


def backend_task(cell: Cell) -> dict[str, Any]:
    model = cell.model
    base = RESULT_ROOT / "backend_backed"
    tier_name = f"tier_{cell.tier.lower()}"
    subject = f"missingfam_backend_{cell.family}_{tier_name}_{model.model_tier.lower()}_{model.slug}_s{cell.seed:02d}"
    return {
        "suite": cell.family,
        "target_tier": cell.tier,
        "model_tier": model.model_tier,
        "slug": model.slug,
        "provider": model.provider,
        "model": model.model,
        "base_url": model.base_url,
        "max_output_tokens": max(model.max_output_tokens, 64000),
        "request_timeout": max(model.request_timeout, 900),
        "rep": cell.seed,
        "subject": subject,
        "target_dir": cell.target_dir,
        "contract": cell.target_dir / "contract.dsl.yaml",
        "public_scenarios": cell.target_dir / "scenarios.public.dsl.yaml",
        "candidate_dir": base / "candidates" / cell.family / tier_name / model.slug / f"seed_{cell.seed:02d}",
        "eval_dir": base / "runs" / cell.family / tier_name / model.slug / f"seed_{cell.seed:02d}",
        "storage_dir": base / "runs" / cell.family / tier_name / model.slug / f"seed_{cell.seed:02d}" / "backend_storage",
        "variant": (
            f"Backend-backed variant for {cell.visual} Generate a minimal frontend plus local "
            "Express backend with JSON-file persistent storage. Keep the UI small and functional; "
            "all behavior must come from the public DSL contract and public examples, not hidden scenario assumptions."
        ),
    }


def repair_task_root(cell: Cell) -> Path:
    return (
        RESULT_ROOT
        / "public_feedback_repair_at1_at2_at3"
        / "runs"
        / cell.family
        / f"tier_{cell.tier.lower()}"
        / cell.model.slug
        / f"seed_{cell.seed:02d}"
    )


def static_generation_ok(candidate_dir: Path) -> bool:
    if not candidate_dir.is_dir():
        return False
    return all((candidate_dir / name).is_file() for name in ["index.html", "styles.css", "app.js", "generation.json"])


def remove_static_partial(candidate_dir: Path) -> None:
    for name in ["index.html", "styles.css", "app.js", "generation.json", "GENERATION.md"]:
        path = candidate_dir / name
        if path.is_file():
            path.unlink()


def capped_output_tokens(provider: str, model: str, requested: int) -> int:
    if provider == "anthropic":
        return min(requested, 64000)
    return requested


def latest_summary(eval_dir: Path) -> dict[str, Any] | None:
    for summary_path in sorted(eval_dir.glob("*/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def summary_metrics(summary: dict[str, Any], status: str) -> dict[str, Any]:
    score = summary.get("score", {})
    scenarios = summary.get("scenarios", [])
    failed = [scenario for scenario in scenarios if not scenario.get("passed")]
    passed_count = len(scenarios) - len(failed)
    return {
        "status": status,
        "evaluated": True,
        "full_pass": bool(summary.get("passed")),
        "S_scen": (passed_count / len(scenarios)) if scenarios else None,
        "S_step": nested_get(score, "stepwise", "ratio"),
        "formal_ratio": nested_get(score, "formal", "ratio"),
        "contract_ratio": nested_get(score, "contract", "ratio"),
        "scenarios_passed": passed_count,
        "scenarios_total": len(scenarios),
        "first_failure_category": failed[0].get("failure_category") if failed else None,
        "first_failure": failed[0].get("id") if failed else None,
        "run_id": summary.get("run_id"),
        "summary_path": str(Path(summary.get("output_dir", "")) / "summary.json"),
    }


def record_from_summary(
    batch: str,
    cell: Cell,
    round_index: int | None,
    output_path: Path,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    return manifest_record(
        batch,
        cell,
        round_index,
        output_path,
        evaluation.get("status", "unknown"),
        evaluation.get("error"),
        evaluated=bool(evaluation.get("evaluated")),
        full_pass=evaluation.get("full_pass"),
        s_scen=evaluation.get("S_scen"),
        s_step=evaluation.get("S_step"),
        first_failure_category=evaluation.get("first_failure_category"),
        extra={
            "run_id": evaluation.get("run_id"),
            "summary_path": evaluation.get("summary_path"),
            "scenarios_passed": evaluation.get("scenarios_passed"),
            "scenarios_total": evaluation.get("scenarios_total"),
            "formal_ratio": evaluation.get("formal_ratio"),
            "contract_ratio": evaluation.get("contract_ratio"),
        },
    )


def backend_manifest_record(cell: Cell, task: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    evaluated = evaluation.get("formal_ratio") is not None
    scenarios_passed = evaluation.get("scenarios_passed")
    scenarios_total = evaluation.get("scenarios_total")
    s_scen = (float(scenarios_passed) / float(scenarios_total)) if evaluated and scenarios_total else None
    return manifest_record(
        "backend_backed",
        cell,
        None,
        task["eval_dir"],
        evaluation.get("status", "unknown"),
        evaluation.get("stderr_tail") or evaluation.get("error"),
        evaluated=evaluated,
        full_pass=evaluation.get("passed"),
        s_scen=s_scen,
        s_step=evaluation.get("stepwise_ratio"),
        first_failure_category=evaluation.get("first_failure_raw") or evaluation.get("first_failure_group"),
        extra={
            "run_id": evaluation.get("run_id"),
            "summary_path": evaluation.get("summary_path"),
            "scenarios_passed": scenarios_passed,
            "scenarios_total": scenarios_total,
            "formal_ratio": evaluation.get("formal_ratio"),
            "contract_ratio": evaluation.get("contract_ratio"),
            "backend_status": evaluation.get("backend_status"),
            "install_status": evaluation.get("install_status"),
            "app_url": evaluation.get("app_url"),
        },
    )


def manifest_record(
    batch: str,
    cell: Cell,
    round_index: int | None,
    output_path: Path,
    status: str,
    error: Any,
    *,
    evaluated: bool = False,
    full_pass: Any = None,
    s_scen: Any = None,
    s_step: Any = None,
    first_failure_category: Any = None,
    public_feedback_audit_status: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "experiment_batch": batch,
        "family": cell.family,
        "tier": cell.tier,
        "model": cell.model.slug,
        "model_name": cell.model.model,
        "model_tier": cell.model.model_tier,
        "generation_seed": cell.seed,
        "round": round_index,
        "output_path": str(output_path),
        "status": status,
        "error": stringify_error(error),
        "evaluated": evaluated,
        "full_pass": full_pass,
        "S_scen": s_scen,
        "S_step": s_step,
        "first_failure_category": first_failure_category,
        "public_feedback_audit_status": public_feedback_audit_status,
    }
    if extra:
        record.update(extra)
    return record


def job_failure_manifest(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    batch, rest = job_id.split(":", 1)
    family, tier_part, model_slug, seed_part = rest.split("/")
    model = next((item for item in MODELS if item.slug == model_slug), MODELS[0])
    cell = Cell(family, tier_part.removeprefix("tier_").upper(), model, int(seed_part.removeprefix("seed_")), ROOT, "")
    return manifest_record(batch_name(batch), cell, None, RESULT_ROOT, "failed", result.get("error"))


def batch_name(short: str) -> str:
    return {
        "static": "static_blind_at1",
        "repair": "public_feedback_repair_at1_at2_at3",
        "backend": "backend_backed",
    }.get(short, short)


def append_manifest(record: dict[str, Any]) -> None:
    ensure_result_path(MANIFEST_PATH)
    with manifest_lock:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MANIFEST_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_PATH.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"status": "manifest_decode_error", "raw": line})
    return rows


def write_static_aggregate(result_root: Path, cells: list[Cell]) -> None:
    rows = []
    for cell in cells:
        task = static_task(cell)
        summary = latest_summary(task["eval_dir"])
        row = {
            "suite": cell.family,
            "target_tier": cell.tier,
            "model_tier": cell.model.model_tier,
            "slug": cell.model.slug,
            "model": cell.model.model,
            "rep": cell.seed,
            "candidate_dir": str(task["candidate_dir"]),
            "eval_dir": str(task["eval_dir"]),
            "status": "evaluated" if summary else ("generated_only" if static_generation_ok(task["candidate_dir"]) else "missing_generation"),
        }
        if summary:
            row.update(summary_metrics(summary, "evaluated"))
        rows.append(row)
    write_json(result_root / "static_blind_at1" / "aggregate.json", {"rows": rows, "generated_at": datetime.now(UTC).isoformat(timespec="seconds")})


def write_backend_aggregate(result_root: Path, cells: list[Cell]) -> None:
    rows = []
    for cell in cells:
        task = backend_task(cell)
        summary = latest_summary(task["eval_dir"])
        row = {
            "suite": cell.family,
            "target_tier": cell.tier,
            "model_tier": cell.model.model_tier,
            "slug": cell.model.slug,
            "model": cell.model.model,
            "rep": cell.seed,
            "candidate_dir": str(task["candidate_dir"]),
            "eval_dir": str(task["eval_dir"]),
            "status": "evaluated" if summary else "missing_eval",
        }
        if summary:
            row.update(summary_metrics(summary, "evaluated"))
        rows.append(row)
    write_json(result_root / "backend_backed" / "aggregate.json", {"rows": rows, "generated_at": datetime.now(UTC).isoformat(timespec="seconds")})


def write_summaries(result_root: Path, cells: list[Cell]) -> None:
    rows = read_manifest()
    expected = expected_records(cells)
    write_csv(SUMMARY_DIR / "gemini_flash_latest_invalid_alias_report.csv", [])
    write_csv(SUMMARY_DIR / "static_at1_summary.csv", summary_rows(rows, expected, "static_blind_at1"))
    write_csv(SUMMARY_DIR / "repair_at1_at2_at3_summary.csv", summary_rows(rows, expected, "public_feedback_repair_at1_at2_at3"))
    write_csv(SUMMARY_DIR / "backend_backed_summary.csv", summary_rows(rows, expected, "backend_backed"))
    write_csv(SUMMARY_DIR / "combined_missing_families_summary.csv", combined_summary_rows(rows, expected))
    write_csv(SUMMARY_DIR / "missing_records_report.csv", missing_records(rows, expected))
    write_csv(SUMMARY_DIR / "public_feedback_audit_report.csv", public_feedback_audit_rows(cells))
    write_csv(SUMMARY_DIR / "backend_runtime_failures_report.csv", backend_runtime_failure_rows(rows))


def invalid_gemini_flash_alias_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    invalid_names = {"gemini-flash-latest", "models/gemini-flash-latest", "gemini-3.5-flash", "models/gemini-3.5-flash"}
    return [
        row
        for row in rows
        if row.get("model") == "gemini_flash_latest" and str(row.get("model_name") or "") in invalid_names
    ]


def expected_records(cells: list[Cell]) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    for cell in cells:
        base = {
            "family": cell.family,
            "tier": cell.tier,
            "model": cell.model.slug,
            "generation_seed": cell.seed,
        }
        expected.append({**base, "experiment_batch": "static_blind_at1", "round": None})
        expected.append({**base, "experiment_batch": "backend_backed", "round": None})
        for round_index in [0, 1, 2]:
            expected.append({**base, "experiment_batch": "public_feedback_repair_at1_at2_at3", "round": round_index})
    return expected


def summary_rows(rows: list[dict[str, Any]], expected: list[dict[str, Any]], batch: str) -> list[dict[str, Any]]:
    groups = sorted({
        (item["family"], item["tier"], item["model"], item.get("round"))
        for item in expected
        if item["experiment_batch"] == batch
    })
    out = []
    for family, tier, model, round_index in groups:
        records = matching_records(rows, batch, family, tier, model, round_index)
        expected_n = sum(
            1
            for item in expected
            if item["experiment_batch"] == batch
            and item["family"] == family
            and item["tier"] == tier
            and item["model"] == model
            and item.get("round") == round_index
        )
        out.append(aggregate_group(batch, family, tier, model, round_index, records, expected_n))
    out.append(aggregate_group(batch, "ALL", "ALL", "ALL", "ALL", [r for r in rows if r.get("experiment_batch") == batch], sum(1 for item in expected if item["experiment_batch"] == batch)))
    return out


def combined_summary_rows(rows: list[dict[str, Any]], expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for batch in ["static_blind_at1", "public_feedback_repair_at1_at2_at3", "backend_backed"]:
        rounds = sorted({item.get("round") for item in expected if item["experiment_batch"] == batch}, key=lambda value: -1 if value is None else int(value))
        for round_index in rounds:
            records = [r for r in rows if r.get("experiment_batch") == batch and normalize_round(r.get("round")) == round_index]
            expected_n = sum(1 for item in expected if item["experiment_batch"] == batch and item.get("round") == round_index)
            out.append(aggregate_group(batch, "ALL", "ALL", "ALL", round_index, records, expected_n))
    return out


def aggregate_group(
    batch: str,
    family: str,
    tier: str,
    model: str,
    round_index: Any,
    records: list[dict[str, Any]],
    expected_n: int,
) -> dict[str, Any]:
    deduped = dedupe_records(records)
    evaluated = [row for row in deduped if row.get("evaluated") is True]
    full_pass = sum(1 for row in evaluated if row.get("full_pass") is True)
    audit_violations = sum(1 for row in deduped if row.get("public_feedback_audit_status") == "violation")
    backend_generation_failures = sum(1 for row in deduped if batch == "backend_backed" and row.get("status") == "generation_failed")
    backend_evaluation_failures = sum(
        1
        for row in deduped
        if batch == "backend_backed" and row.get("status") in {"eval_failed", "evaluation_failed", "npm_install_failed", "backend_start_failed"}
    )
    return {
        "experiment_batch": batch,
        "family": family,
        "tier": tier,
        "model": model,
        "round": round_index,
        "evaluated_runs": len(evaluated),
        "expected_runs": expected_n,
        "missing_runs": max(0, expected_n - len(deduped)),
        "failed_runs": sum(1 for row in deduped if row.get("status") not in {"evaluated", "ok", "skipped", "skipped_existing"}),
        "completed_records": len(deduped),
        "full_pass_count": full_pass,
        "full_pass_rate": (full_pass / len(evaluated)) if evaluated else 0.0,
        "S_scen": mean([row.get("S_scen") for row in evaluated]),
        "S_step": mean([row.get("S_step") for row in evaluated]),
        "recovered_count": sum(1 for row in deduped if row.get("recovered_from_previous_round") is True),
        "public_feedback_audit_violations": audit_violations,
        "backend_generation_failures": backend_generation_failures,
        "backend_evaluation_failures": backend_evaluation_failures,
    }


def matching_records(rows: list[dict[str, Any]], batch: str, family: str, tier: str, model: str, round_index: Any) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("experiment_batch") == batch
        and row.get("family") == family
        and row.get("tier") == tier
        and row.get("model") == model
        and normalize_round(row.get("round")) == round_index
    ]


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in records:
        key = (
            row.get("experiment_batch"),
            row.get("family"),
            row.get("tier"),
            row.get("model"),
            row.get("generation_seed"),
            normalize_round(row.get("round")),
        )
        by_key[key] = row
    return list(by_key.values())


def missing_records(rows: list[dict[str, Any]], expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    present = {
        (
            row.get("experiment_batch"),
            row.get("family"),
            row.get("tier"),
            row.get("model"),
            int(row.get("generation_seed")),
            normalize_round(row.get("round")),
        )
        for row in rows
        if row.get("generation_seed") is not None
    }
    out = []
    for item in expected:
        for seed in [item["generation_seed"]]:
            key = (item["experiment_batch"], item["family"], item["tier"], item["model"], seed, item.get("round"))
            if key not in present:
                out.append({**item, "status": "missing"})
    return out


def public_feedback_audit_rows(cells: list[Cell]) -> list[dict[str, Any]]:
    rows = []
    for cell in cells:
        task_root = repair_task_root(cell)
        status = audit_status_for_cell(cell)
        details = audit_details_for_cell(cell)
        rows.append(
            {
                "family": cell.family,
                "tier": cell.tier,
                "model": cell.model.slug,
                "generation_seed": cell.seed,
                "public_feedback_audit_status": status,
                "violation_count": len(details),
                "violations": json.dumps(details, ensure_ascii=False),
                "task_root": str(task_root),
            }
        )
    return rows


def audit_status_for_cell(cell: Cell) -> str:
    details = audit_details_for_cell(cell)
    if details:
        return "violation"
    task_root = repair_task_root(cell)
    if not (task_root / "records").is_dir():
        return "missing"
    return "ok"


def audit_details_for_cell(cell: Cell) -> list[dict[str, Any]]:
    task_root = repair_task_root(cell)
    violations: list[dict[str, Any]] = []
    for round_index in [1, 2]:
        path = task_root / "apps" / f"round_{round_index}" / "patch_metadata.json"
        if not path.is_file():
            continue
        metadata = safe_read_json(path)
        feedback = metadata.get("feedback") or {}
        if metadata.get("feedback_source_scenario_set") != "public":
            violations.append({"path": str(path), "type": "non_public_patch_source", "value": metadata.get("feedback_source_scenario_set")})
        if feedback.get("scenario_set") not in (None, "public"):
            violations.append({"path": str(path), "type": "non_public_patch_feedback_scenario_set", "value": feedback.get("scenario_set")})
        if feedback.get("scenario_id") and not str(feedback.get("scenario_id")).startswith("public_"):
            violations.append({"path": str(path), "type": "non_public_patch_feedback_scenario_id", "value": feedback.get("scenario_id")})
    for round_index in [0, 1]:
        path = task_root / "records" / f"public_feedback_round_{round_index}.json"
        if not path.is_file():
            continue
        record = safe_read_json(path)
        feedback = record.get("failure_feedback") or {}
        scenario_set = record.get("scenario_set") or feedback.get("scenario_set")
        if scenario_set != "public":
            violations.append({"path": str(path), "type": "non_public_feedback_probe", "value": scenario_set})
        if feedback.get("scenario_id") and not str(feedback.get("scenario_id")).startswith("public_"):
            violations.append({"path": str(path), "type": "non_public_feedback_probe_scenario_id", "value": feedback.get("scenario_id")})
    return violations


def backend_runtime_failure_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failure_statuses = {"generation_failed", "eval_failed", "evaluation_failed", "npm_install_failed", "backend_start_failed", "missing_target"}
    return [
        row
        for row in dedupe_records([row for row in rows if row.get("experiment_batch") == "backend_backed"])
        if row.get("status") in failure_statuses or row.get("evaluated") is not True
    ]


def completion_report(result_root: Path, cells: list[Cell]) -> dict[str, Any]:
    rows = read_manifest()
    expected = expected_records(cells)
    report = {}
    for batch in ["static_blind_at1", "public_feedback_repair_at1_at2_at3", "backend_backed"]:
        batch_rows = dedupe_records([row for row in rows if row.get("experiment_batch") == batch])
        batch_expected = [row for row in expected if row["experiment_batch"] == batch]
        report[batch] = {
            "expected": len(batch_expected),
            "generated": generated_count(batch, cells),
            "evaluated": sum(1 for row in batch_rows if row.get("evaluated") is True),
            "missing": max(0, len(batch_expected) - len(batch_rows)),
            "failed": sum(1 for row in batch_rows if row.get("status") not in {"evaluated", "ok", "skipped", "skipped_existing"}),
            "completed": len(batch_rows),
        }
    return report


def generated_count(batch: str, cells: list[Cell]) -> int:
    if batch == "static_blind_at1":
        return sum(1 for cell in cells if static_generation_ok(static_task(cell)["candidate_dir"]))
    if batch == "backend_backed":
        return sum(1 for cell in cells if (backend_task(cell)["candidate_dir"] / "generation.json").is_file())
    return sum(1 for cell in cells if (repair_task_root(cell) / "apps" / "round_0").is_dir())


def render_completion_report(report: dict[str, Any]) -> str:
    lines = ["\n=== Missing Families Full Rerun Completion ==="]
    for batch, row in report.items():
        lines.append(
            f"{batch}: expected={row['expected']} generated={row['generated']} evaluated={row['evaluated']} "
            f"missing={row['missing']} failed={row['failed']} completed={row['completed']}"
        )
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_result_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: Any) -> None:
    ensure_result_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_run_config(result_root: Path, payload: dict[str, Any]) -> None:
    timestamp = str(payload.get("created_at") or datetime.now(UTC).isoformat(timespec="seconds"))
    safe_timestamp = re.sub(r"[^0-9A-Za-z]+", "", timestamp)
    model_part = "_".join(str(model.get("slug", "model")) for model in payload.get("models", [])) or "models"
    if len(model_part) > 120:
        model_part = f"{len(payload.get('models', []))}_models"
    config_path = result_root / f"run_config_{safe_timestamp}_{model_part}.json"
    write_json(config_path, payload)
    canonical_path = result_root / "run_config.json"
    if not canonical_path.exists():
        write_json(canonical_path, payload)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_read_json(path: Path) -> dict[str, Any]:
    try:
        return read_json(path)
    except Exception as exc:
        return {"_json_error": repr(exc)}


def ensure_result_path(path: Path) -> None:
    root = RESULT_ROOT.resolve()
    resolved = path.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise SystemExit(f"Refusing to write outside result root {root}: {resolved}")


def nested_get(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def mean(values: list[Any]) -> float:
    numbers = [float(value) for value in values if value not in (None, "")]
    return sum(numbers) / len(numbers) if numbers else 0.0


def normalize_round(value: Any) -> Any:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def cell_key(cell: Cell) -> str:
    return f"{cell.family}/tier_{cell.tier.lower()}/{cell.model.slug}/seed_{cell.seed:02d}"


def status_line(job_id: str, result: dict[str, Any]) -> str:
    status = result.get("status", "?")
    message = f"[done] {job_id} status={status}"
    if result.get("error"):
        message += f" error={str(result['error'])[:200]}"
    return message


def stringify_error(error: Any) -> str | None:
    if error in (None, ""):
        return None
    return str(error)[-4000:]


def run_with_process_group_timeout(cmd: list[str], cwd: Path, timeout: int) -> tuple[subprocess.CompletedProcess[str], bool]:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd, process.returncode, stdout or "", stderr or ""), False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(cmd, process.returncode if process.returncode is not None else -signal.SIGTERM, stdout or "", stderr or ""), True


def tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


if __name__ == "__main__":
    raise SystemExit(main())
