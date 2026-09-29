from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urljoin
from urllib.parse import quote
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_stayflow_repeat_cohort import MODELS, ModelSpec


RESULTS_ROOT = ROOT / "results_backend_backed_target_apps"
BASELINE_RUNS_CSV = ROOT / "reports/conformweb_visualizations/data/raw_runs.csv"
BASELINE_SCENARIOS_CSV = ROOT / "reports/conformweb_visualizations/data/raw_scenarios.csv"


@dataclass(frozen=True)
class TargetSpec:
    suite: str
    tier: str
    target_dir: Path
    brief: str


TARGETS = [
    TargetSpec(
        "freshcart_market",
        "A",
        ROOT / "targets/web/freshcart_market/tier_a",
        "Fresh Cart Market Tier A minimal grocery ordering frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "freshcart_market",
        "B",
        ROOT / "targets/web/freshcart_market/tier_b",
        "Fresh Cart Market Tier B minimal cold-chain cart, checkout, and fulfillment frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "freshcart_market",
        "C",
        ROOT / "targets/web/freshcart_market/tier_c",
        "Fresh Cart Market Tier C minimal grocery operations frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "freshcart_market",
        "D",
        ROOT / "targets/web/freshcart_market/tier_d",
        "Fresh Cart Market Tier D minimal grocery release and operations frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "homefix_hub",
        "A",
        ROOT / "targets/web/homefix_hub/tier_a",
        "HomeFix Hub Tier A minimal repair booking frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "homefix_hub",
        "B",
        ROOT / "targets/web/homefix_hub/tier_b",
        "HomeFix Hub Tier B minimal dispatch and parts readiness frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "homefix_hub",
        "C",
        ROOT / "targets/web/homefix_hub/tier_c",
        "HomeFix Hub Tier C minimal QA and clearance frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "homefix_hub",
        "D",
        ROOT / "targets/web/homefix_hub/tier_d",
        "HomeFix Hub Tier D minimal claims, warranty, and customer acknowledgement frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "stayflow_concierge",
        "A",
        ROOT / "targets/web/stayflow_concierge/tier_a",
        "StayFlow Concierge Tier A minimal travel booking frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "stayflow_concierge",
        "B",
        ROOT / "targets/web/stayflow_concierge/tier_b",
        "StayFlow Concierge Tier B minimal itinerary operations frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "stayflow_concierge",
        "C",
        ROOT / "targets/web/stayflow_concierge/tier_c",
        "StayFlow Concierge Tier C minimal premium booking frontend backed by local JSON persistence.",
    ),
    TargetSpec(
        "stayflow_concierge",
        "D",
        ROOT / "targets/web/stayflow_concierge/tier_d",
        "StayFlow Concierge Tier D minimal travel release war-room frontend backed by local JSON persistence.",
    ),
]


EXPECTED_CANDIDATE_FILES = [
    "package.json",
    "server.js",
    "public/index.html",
    "public/styles.css",
    "public/app.js",
    "generation.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backend-backed DetoxBench target app variants.")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--batch-id", default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--generation-workers", type=int, default=4)
    parser.add_argument("--evaluation-workers", type=int, default=2)
    parser.add_argument(
        "--suites",
        nargs="+",
        choices=["freshcart_market", "homefix_hub", "stayflow_concierge"],
        default=["freshcart_market", "homefix_hub", "stayflow_concierge"],
    )
    parser.add_argument("--tiers", nargs="+", choices=["A", "B", "C", "D"], default=["A", "B", "C", "D"])
    parser.add_argument("--model-tiers", nargs="+", choices=["M", "T", "F"], default=["M", "T", "F"])
    parser.add_argument("--model-slugs", nargs="+", help="Optional exact model slugs to run.")
    parser.add_argument("--output-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument("--compare-only", action="store_true")
    parser.add_argument(
        "--no-provider-preflight",
        action="store_true",
        help="Skip fail-fast provider credential checks before generation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    ensure_results_path(output_root)
    batch_root = (output_root / args.batch_id).resolve()
    ensure_results_path(batch_root)
    batch_root.mkdir(parents=True, exist_ok=True)

    tasks = build_tasks(args, batch_root)
    should_preflight = not args.compare_only and not args.skip_generation and not args.no_provider_preflight
    preflight = provider_preflight(tasks) if should_preflight else {"skipped": True, "ok": True}
    write_json(
        batch_root / "manifest.json",
        {
            "batch_id": args.batch_id,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "substrate": "backend_backed_express_json_file_storage",
            "results_root": str(RESULTS_ROOT),
            "repetitions": args.repetitions,
            "generation_workers": args.generation_workers,
            "evaluation_workers": args.evaluation_workers,
            "suites": args.suites,
            "tiers": args.tiers,
            "model_tiers": args.model_tiers,
            "model_slugs": args.model_slugs,
            "provider_preflight": preflight,
            "tasks": [task_manifest(task) for task in tasks],
        },
    )

    progress_path = batch_root / "progress.jsonl"
    print(f"Batch: {batch_root}")
    print(f"Tasks: {len(tasks)}")

    if not args.compare_only and not args.skip_generation and not preflight.get("ok", False):
        write_json(batch_root / "provider_preflight.json", preflight)
        raise SystemExit(f"Provider preflight failed: {preflight}")

    if not args.compare_only and not args.skip_generation:
        print(f"\n=== Phase 1: Backend-backed generation ({args.generation_workers} workers) ===")
        with ThreadPoolExecutor(max_workers=args.generation_workers) as pool:
            futures = {pool.submit(generate_task, task): task for task in tasks}
            for future in as_completed(futures):
                record = future.result()
                append_jsonl(progress_path, {"phase": "generate", **record})
                print(status_line("generate", record), flush=True)

    generated = [task for task in tasks if generation_ok(task)]
    print(f"\nGenerated candidates ready for evaluation: {len(generated)} / {len(tasks)}")

    if not args.compare_only and not args.skip_evaluation:
        print(f"\n=== Phase 2: Backend-backed evaluation ({args.evaluation_workers} workers) ===")
        with ThreadPoolExecutor(max_workers=args.evaluation_workers) as pool:
            futures = {pool.submit(evaluate_task, task): task for task in generated}
            for future in as_completed(futures):
                record = future.result()
                append_jsonl(progress_path, {"phase": "evaluate", **record})
                print(status_line("evaluate", record), flush=True)

    print("\n=== Phase 3: Aggregation and static-client comparison ===")
    aggregate = aggregate_results(batch_root, tasks)
    write_json(batch_root / "aggregate.json", aggregate)
    write_csv(batch_root / "raw_backend_runs.csv", aggregate["rows"])
    write_csv(batch_root / "raw_backend_scenarios.csv", aggregate["scenario_rows"])
    write_csv(batch_root / "comparison_static_client.csv", aggregate["comparison"]["rows"])
    (batch_root / "README.md").write_text(render_markdown(aggregate), encoding="utf-8")
    print(f"Aggregate: {batch_root / 'aggregate.json'}")
    print(f"Comparison: {batch_root / 'comparison_static_client.csv'}")
    print(f"Report: {batch_root / 'README.md'}")
    return 0


def build_tasks(args: argparse.Namespace, batch_root: Path) -> list[dict[str, Any]]:
    selected_targets = [
        target
        for target in TARGETS
        if target.suite in set(args.suites) and target.tier in set(args.tiers)
    ]
    selected_models = [model for model in MODELS if model.model_tier in set(args.model_tiers)]
    if args.model_slugs:
        selected_models = [model for model in selected_models if model.slug in set(args.model_slugs)]

    tasks: list[dict[str, Any]] = []
    for target in selected_targets:
        for model in selected_models:
            for rep in range(1, args.repetitions + 1):
                tier_name = f"tier_{target.tier.lower()}"
                subject = f"backend_{target.suite}_{tier_name}_{model.model_tier.lower()}_{model.slug}_r{rep:02d}"
                candidate_dir = batch_root / "candidates" / target.suite / tier_name / model.slug / f"r{rep:02d}"
                eval_dir = batch_root / "runs" / target.suite / tier_name / model.slug / f"r{rep:02d}"
                tasks.append(
                    {
                        "suite": target.suite,
                        "target_tier": target.tier,
                        "model_tier": model.model_tier,
                        "slug": model.slug,
                        "provider": model.provider,
                        "model": model.model,
                        "base_url": model.base_url,
                        "max_output_tokens": backend_token_limit(model),
                        "request_timeout": backend_timeout(model),
                        "max_retries": args.max_retries,
                        "rep": rep,
                        "subject": subject,
                        "target_dir": target.target_dir,
                        "contract": target.target_dir / "contract.dsl.yaml",
                        "public_scenarios": target.target_dir / "scenarios.public.dsl.yaml",
                        "candidate_dir": candidate_dir,
                        "eval_dir": eval_dir,
                        "storage_dir": eval_dir / "backend_storage",
                        "variant": (
                            f"Backend-backed variant for {target.brief} Generate a minimal frontend "
                            "plus local Express backend with JSON-file persistent storage. Keep the "
                            "UI small and functional; all behavior must come from the public DSL "
                            "contract and public examples, not hidden scenario assumptions. "
                            f"This is repetition {rep:02d} for model tier {model.model_tier} "
                            f"and model {model.slug}."
                        ),
                    }
                )
    return tasks


def provider_preflight(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    providers = sorted({str(task["provider"]) for task in tasks})
    checks: dict[str, dict[str, Any]] = {}
    ok = True
    for provider in providers:
        if provider == "openai":
            provider_ok = bool(os.environ.get("OPENAI_API_KEY"))
            checks[provider] = {"ok": provider_ok, "method": "env_presence", "env": "OPENAI_API_KEY"}
        elif provider == "anthropic":
            provider_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
            checks[provider] = {"ok": provider_ok, "method": "env_presence", "env": "ANTHROPIC_API_KEY"}
        elif provider == "google":
            checks[provider] = google_key_preflight()
            provider_ok = bool(checks[provider].get("ok"))
        else:
            checks[provider] = {"ok": False, "error": f"unknown provider {provider}"}
            provider_ok = False
        ok = ok and provider_ok
    return {"ok": ok, "checks": checks}


def google_key_preflight() -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"ok": False, "method": "models_list", "env": "GEMINI_API_KEY", "error": "missing GEMINI_API_KEY"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={quote(api_key, safe='')}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return {"ok": 200 <= response.status < 300, "method": "models_list", "status": response.status}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "method": "models_list",
            "status": error.code,
            "error": detail[:1000],
        }
    except Exception as exc:
        return {"ok": False, "method": "models_list", "error": f"{exc.__class__.__name__}: {exc}"}


def backend_token_limit(model: ModelSpec) -> int:
    return max(model.max_output_tokens, 64000)


def backend_timeout(model: ModelSpec) -> int:
    return max(model.request_timeout, 900)


def generate_task(task: dict[str, Any]) -> dict[str, Any]:
    if generation_ok(task):
        return task_record(task, status="skipped_existing")

    result = None
    max_retries = int(task.get("max_retries", 1))
    for attempt in range(1, max_retries + 1):
        if attempt > 1:
            remove_partial_candidate_files(task["candidate_dir"])
        timeout = int(task["request_timeout"]) * (1 if attempt == 1 else 2)
        max_tokens = int(task["max_output_tokens"]) * (1 if attempt == 1 else 2)
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
        if result.returncode == 0 and generation_ok(task):
            return task_record(
                task,
                status="ok",
                attempts=attempt,
                returncode=result.returncode,
                stdout_tail=tail(result.stdout),
                stderr_tail=tail(result.stderr),
            )
        if attempt < max_retries:
            print(
                f"  [retry] suite={task['suite']} tier={task['target_tier']} "
                f"group={task['model_tier']} model={task['slug']} rep={task['rep']:02d}",
                flush=True,
            )

    assert result is not None
    return task_record(
        task,
        status="failed",
        attempts=max_retries,
        returncode=result.returncode,
        stdout_tail=tail(result.stdout),
        stderr_tail=tail(result.stderr),
    )


def evaluate_task(task: dict[str, Any]) -> dict[str, Any]:
    existing = latest_summary(task["eval_dir"])
    if existing:
        return eval_record(task, existing, status="skipped_existing")
    if not generation_ok(task):
        return task_record(task, status="missing_generation")

    install = ensure_node_dependencies(task)
    if install.get("status") != "ok":
        install_detail = {key: value for key, value in install.items() if key != "status"}
        return task_record(
            task,
            status="npm_install_failed",
            install_status=install.get("status"),
            **install_detail,
        )

    task["eval_dir"].mkdir(parents=True, exist_ok=True)
    ensure_results_path(task["storage_dir"])
    if task["storage_dir"].exists():
        shutil.rmtree(task["storage_dir"])
    task["storage_dir"].mkdir(parents=True, exist_ok=True)

    with running_backend(task) as backend:
        if backend["status"] != "ok":
            backend_detail = {key: value for key, value in backend.items() if key != "status"}
            return task_record(
                task,
                status="backend_start_failed",
                backend_status=backend.get("status"),
                **backend_detail,
            )
        app_url = app_start_url(task["contract"], backend["base_url"])
        reset_status = reset_backend(backend["base_url"])
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
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    summary = latest_summary(task["eval_dir"])
    if summary:
        return eval_record(
            task,
            summary,
            status="ok",
            returncode=result.returncode,
            app_url=app_url,
            backend_reset=reset_status,
            stdout_tail=tail(result.stdout),
            stderr_tail=tail(result.stderr),
        )
    return task_record(
        task,
        status="eval_failed",
        returncode=result.returncode,
        app_url=app_url,
        backend_reset=reset_status,
        stdout_tail=tail(result.stdout),
        stderr_tail=tail(result.stderr),
    )


def ensure_node_dependencies(task: dict[str, Any]) -> dict[str, Any]:
    candidate_dir = task["candidate_dir"]
    express_dir = candidate_dir / "node_modules/express"
    if express_dir.exists():
        return {"status": "ok", "skipped_existing": True}
    log_dir = candidate_dir / "install_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["npm", "install", "--omit=dev", "--no-audit", "--no-fund", "--package-lock=false"]
    result = subprocess.run(cmd, cwd=candidate_dir, capture_output=True, text=True, check=False, timeout=180)
    (log_dir / "npm_install_stdout.log").write_text(result.stdout, encoding="utf-8")
    (log_dir / "npm_install_stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode == 0 and express_dir.exists():
        return {"status": "ok", "returncode": result.returncode}
    return {
        "status": "failed",
        "returncode": result.returncode,
        "stdout_tail": tail(result.stdout),
        "stderr_tail": tail(result.stderr),
    }


@contextmanager
def running_backend(task: dict[str, Any]):
    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_dir = task["eval_dir"] / "backend_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
    env = os.environ.copy()
    env.update(
        {
            "PORT": str(port),
            "HOST": "127.0.0.1",
            "NODE_ENV": "test",
            "DETOX_STORAGE_DIR": str(task["storage_dir"]),
        }
    )
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            ["node", "server.js"],
            cwd=task["candidate_dir"],
            env=env,
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
        try:
            ready = wait_for_http(base_url, timeout_s=45)
            if not ready:
                yield {
                    "status": "failed",
                    "base_url": base_url,
                    "returncode": process.poll(),
                    "stdout_log": str(stdout_path),
                    "stderr_log": str(stderr_path),
                }
            else:
                yield {
                    "status": "ok",
                    "base_url": base_url,
                    "pid": process.pid,
                    "stdout_log": str(stdout_path),
                    "stderr_log": str(stderr_path),
                }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def reset_backend(base_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        urljoin(base_url + "/", "__detox/reset"),
        data=b"{}",
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return {"ok": 200 <= response.status < 300, "status": response.status}
    except Exception as exc:
        return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}


def aggregate_results(batch_root: Path, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    scenario_rows: list[dict[str, Any]] = []
    for task in tasks:
        summary = latest_summary(task["eval_dir"])
        if summary:
            row = eval_record(task, summary, status="ok")
            rows.append(row)
            scenario_rows.extend(scenario_records(task, summary, row))
        else:
            rows.append(task_record(task, status="missing_eval" if generation_ok(task) else "missing_generation"))

    model_stats = model_group_stats(rows)
    tier_group_stats = tier_group_stats_from(rows)
    comparison = compare_to_static_client(rows, scenario_rows)

    return {
        "batch_root": str(batch_root),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "substrate": "backend_backed_express_json_file_storage",
        "baseline_runs_source": str(BASELINE_RUNS_CSV),
        "baseline_scenarios_source": str(BASELINE_SCENARIOS_CSV),
        "total_tasks": len(tasks),
        "generated": sum(1 for task in tasks if generation_ok(task)),
        "evaluated": sum(1 for row in rows if row.get("formal_ratio") is not None),
        "rows": rows,
        "scenario_rows": scenario_rows,
        "model_stats": model_stats,
        "tier_group_stats": tier_group_stats,
        "comparison": comparison,
    }


def compare_to_static_client(rows: list[dict[str, Any]], scenario_rows: list[dict[str, Any]]) -> dict[str, Any]:
    backend_by_key = summarize_runs(rows, scenario_rows)
    baseline_runs = read_baseline_runs()
    baseline_scenarios = read_baseline_scenarios()
    baseline_by_key = summarize_runs(baseline_runs, baseline_scenarios)
    keys = sorted(set(backend_by_key) | set(baseline_by_key))
    out_rows = []
    for key in keys:
        backend = backend_by_key.get(key, empty_summary(key))
        baseline = baseline_by_key.get(key, empty_summary(key))
        out_rows.append(
            {
                "suite": key[0],
                "tier": key[1],
                "model_tier": key[2],
                "model": key[3],
                "backend_runs": backend["runs"],
                "static_runs": baseline["runs"],
                "backend_formal_mean": backend["formal_mean"],
                "static_formal_mean": baseline["formal_mean"],
                "formal_delta_backend_minus_static": delta(backend["formal_mean"], baseline["formal_mean"]),
                "backend_stepwise_mean": backend["stepwise_mean"],
                "static_stepwise_mean": baseline["stepwise_mean"],
                "stepwise_delta_backend_minus_static": delta(backend["stepwise_mean"], baseline["stepwise_mean"]),
                "backend_full_pass": backend["full_pass"],
                "static_full_pass": baseline["full_pass"],
                "backend_route_persistence_failures": backend["route_persistence_failures"],
                "static_route_persistence_failures": baseline["route_persistence_failures"],
                "backend_service_interaction_failures": backend["service_interaction_failures"],
                "static_service_interaction_failures": baseline["service_interaction_failures"],
                "backend_service_scenario_failures": backend["service_scenario_failures"],
                "static_service_scenario_failures": baseline["service_scenario_failures"],
                "backend_service_scenarios": backend["service_scenarios"],
                "static_service_scenarios": baseline["service_scenarios"],
            }
        )
    return {"rows": out_rows}


def summarize_runs(
    run_rows: list[dict[str, Any]],
    scenario_rows: list[dict[str, Any]],
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in run_rows:
        if row.get("formal_ratio") is None:
            continue
        key = (str(row["suite"]), str(row["target_tier"]), str(row["model_tier"]), str(row["slug"]))
        grouped.setdefault(key, []).append(row)
    scenario_grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in scenario_rows:
        key = (str(row["suite"]), str(row["target_tier"]), str(row["model_tier"]), str(row["slug"]))
        scenario_grouped.setdefault(key, []).append(row)

    result = {}
    for key, group in grouped.items():
        scenarios = scenario_grouped.get(key, [])
        result[key] = {
            "runs": len(group),
            "formal_mean": mean([row.get("formal_ratio") for row in group]),
            "stepwise_mean": mean([row.get("stepwise_ratio") for row in group]),
            "full_pass": sum(1 for row in group if as_bool(row.get("passed"))),
            "route_persistence_failures": sum(1 for row in group if row.get("first_failure_group") == "route / persistence drift"),
            "service_interaction_failures": sum(1 for row in group if row.get("first_failure_group") == "service interaction failure"),
            "service_scenarios": sum(1 for row in scenarios if row.get("scenario_tier") == "service"),
            "service_scenario_failures": sum(
                1
                for row in scenarios
                if row.get("scenario_tier") == "service" and not as_bool(row.get("scenario_passed"))
            ),
        }
    return result


def read_baseline_runs() -> list[dict[str, Any]]:
    if not BASELINE_RUNS_CSV.exists():
        return []
    wanted_suites = {target.suite for target in TARGETS}
    wanted_tiers = {target.tier for target in TARGETS}
    rows = []
    with BASELINE_RUNS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("suite") not in wanted_suites or row.get("tier") not in wanted_tiers:
                continue
            if row.get("view_current_raw") not in {"True", "true", "1", True}:
                continue
            rows.append(
                {
                    "suite": row.get("suite"),
                    "target_tier": row.get("tier"),
                    "model_tier": row.get("model_tier"),
                    "slug": row.get("model"),
                    "passed": row.get("passed"),
                    "formal_ratio": to_float(row.get("formal_ratio")),
                    "stepwise_ratio": to_float(row.get("stepwise_ratio")),
                    "first_failure_group": row.get("primary_failure_group") or failure_label(row.get("primary_raw_failure")),
                }
            )
    return rows


def read_baseline_scenarios() -> list[dict[str, Any]]:
    if not BASELINE_SCENARIOS_CSV.exists():
        return []
    wanted_suites = {target.suite for target in TARGETS}
    wanted_tiers = {target.tier for target in TARGETS}
    rows = []
    with BASELINE_SCENARIOS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("suite") not in wanted_suites or row.get("tier") not in wanted_tiers:
                continue
            if row.get("view_current_raw") not in {"True", "true", "1", True}:
                continue
            rows.append(
                {
                    "suite": row.get("suite"),
                    "target_tier": row.get("tier"),
                    "model_tier": row.get("model_tier"),
                    "slug": row.get("model"),
                    "scenario_tier": row.get("scenario_tier"),
                    "scenario_passed": row.get("scenario_passed"),
                    "first_failure_group": row.get("first_failure_group"),
                }
            )
    return rows


def model_group_stats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["suite"], row["target_tier"], row["model_tier"], row["slug"])
        groups.setdefault(key, []).append(row)
    stats = []
    for (suite, tier, model_tier, slug), group_rows in sorted(groups.items()):
        evaluated = [row for row in group_rows if row.get("formal_ratio") is not None]
        stats.append(
            {
                "suite": suite,
                "target_tier": tier,
                "model_tier": model_tier,
                "slug": slug,
                "runs": len(group_rows),
                "evaluated": len(evaluated),
                "generation_or_eval_missing": len(group_rows) - len(evaluated),
                "scenario_pass_mean": mean([row.get("scenarios_passed") for row in evaluated]),
                "formal_mean": mean([row.get("formal_ratio") for row in evaluated]),
                "formal_sd": stdev([row.get("formal_ratio") for row in evaluated]),
                "stepwise_mean": mean([row.get("stepwise_ratio") for row in evaluated]),
                "stepwise_sd": stdev([row.get("stepwise_ratio") for row in evaluated]),
                "contract_mean": mean([row.get("contract_ratio") for row in evaluated]),
                "first_failure_groups": top_counts([row.get("first_failure_group") for row in evaluated if row.get("first_failure_group")]),
            }
        )
    return stats


def tier_group_stats_from(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats = []
    suites = sorted({row["suite"] for row in rows})
    tiers = sorted({row["target_tier"] for row in rows})
    model_tiers = sorted({row["model_tier"] for row in rows})
    for suite in suites:
        for tier in tiers:
            for model_tier in model_tiers:
                evaluated = [
                    row
                    for row in rows
                    if row["suite"] == suite
                    and row["target_tier"] == tier
                    and row["model_tier"] == model_tier
                    and row.get("formal_ratio") is not None
                ]
                if not evaluated:
                    continue
                stats.append(
                    {
                        "suite": suite,
                        "target_tier": tier,
                        "model_tier": model_tier,
                        "evaluated": len(evaluated),
                        "formal_mean": mean([row.get("formal_ratio") for row in evaluated]),
                        "formal_sd": stdev([row.get("formal_ratio") for row in evaluated]),
                        "stepwise_mean": mean([row.get("stepwise_ratio") for row in evaluated]),
                        "stepwise_sd": stdev([row.get("stepwise_ratio") for row in evaluated]),
                        "full_pass": sum(1 for row in evaluated if row.get("passed")),
                    }
                )
    return stats


def eval_record(task: dict[str, Any], summary: dict[str, Any], **extra: Any) -> dict[str, Any]:
    score = summary.get("score", {})
    scenarios = summary.get("scenarios", [])
    failed = [scenario for scenario in scenarios if not scenario.get("passed")]
    first_raw = failed[0].get("failure_category") if failed else None
    return {
        **task_record(task),
        "run_id": summary.get("run_id"),
        "passed": bool(summary.get("passed")),
        "scenarios_passed": sum(1 for scenario in scenarios if scenario.get("passed")),
        "scenarios_total": len(scenarios),
        "formal_ratio": safe_get(score, "formal", "ratio"),
        "stepwise_ratio": safe_get(score, "stepwise", "ratio"),
        "contract_ratio": safe_get(score, "contract", "ratio"),
        "first_failure": failed[0].get("id") if failed else None,
        "first_failure_raw": first_raw,
        "first_failure_group": failure_label(first_raw),
        "failure_breakdown": score.get("failure_breakdown", {}),
        "summary_path": str(Path(summary.get("output_dir", "")) / "summary.json"),
        **extra,
    }


def scenario_records(task: dict[str, Any], summary: dict[str, Any], run_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for scenario in summary.get("scenarios", []):
        first_raw = scenario.get("failure_category")
        rows.append(
            {
                "suite": task["suite"],
                "target_tier": task["target_tier"],
                "model_tier": task["model_tier"],
                "slug": task["slug"],
                "model": task["model"],
                "rep": f"r{int(task['rep']):02d}",
                "run_id": run_row.get("run_id"),
                "summary_path": run_row.get("summary_path"),
                "scenario_id": scenario.get("id"),
                "scenario_tier": scenario.get("tier"),
                "kind": scenario.get("kind"),
                "visibility": scenario.get("visibility"),
                "difficulty": scenario.get("difficulty"),
                "scenario_passed": bool(scenario.get("passed")),
                "scenario_score_ratio": safe_get(scenario, "score", "ratio"),
                "expected_step_count": scenario.get("expected_step_count"),
                "completed_step_count": scenario.get("completed_step_count"),
                "passed_step_count": scenario.get("passed_step_count"),
                "first_failed_step": scenario.get("first_failed_step"),
                "first_failure_raw": first_raw,
                "first_failure_group": failure_label(first_raw),
            }
        )
    return rows


def task_record(task: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "suite": task["suite"],
        "target_tier": task["target_tier"],
        "model_tier": task["model_tier"],
        "slug": task["slug"],
        "model": task["model"],
        "rep": f"r{int(task['rep']):02d}",
        "subject": task["subject"],
        "candidate_dir": str(task["candidate_dir"]),
        "eval_dir": str(task["eval_dir"]),
        **extra,
    }


def task_manifest(task: dict[str, Any]) -> dict[str, Any]:
    return {key: str(value) if isinstance(value, Path) else value for key, value in task.items()}


def generation_ok(task: dict[str, Any]) -> bool:
    candidate_dir = task["candidate_dir"]
    if not candidate_dir.is_dir():
        return False
    return all((candidate_dir / name).is_file() for name in EXPECTED_CANDIDATE_FILES)


def remove_partial_candidate_files(candidate_dir: Path) -> None:
    for name in EXPECTED_CANDIDATE_FILES + ["GENERATION.md"]:
        path = candidate_dir / name
        if path.exists() and path.is_file():
            path.unlink()


def latest_summary(eval_dir: Path) -> dict[str, Any] | None:
    summaries = sorted(eval_dir.glob("*/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for summary_path in summaries:
        try:
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def app_start_url(contract_path: Path, base_url: str) -> str:
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    runtime = contract.get("runtime") or {}
    start_url = runtime.get("start_url") or "/"
    return urljoin(base_url + "/", str(start_url).lstrip("/"))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_http(base_url: str, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url, timeout=2) as response:
                if response.status < 500:
                    return True
        except urllib.error.HTTPError as error:
            if error.code < 500:
                return True
        except Exception:
            time.sleep(0.5)
    return False


def render_markdown(aggregate: dict[str, Any]) -> str:
    lines = [
        "# Backend-Backed Target Apps",
        "",
        f"Batch root: `{aggregate['batch_root']}`",
        "",
        f"Generated: {aggregate['generated']} / {aggregate['total_tasks']}",
        f"Evaluated: {aggregate['evaluated']} / {aggregate['total_tasks']}",
        "",
        "## Tier x Model Group",
        "",
        "| Suite | Tier | Model Tier | Runs | Formal mean +/- sd | Stepwise mean +/- sd | Full pass |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in aggregate["tier_group_stats"]:
        lines.append(
            "| {suite} | {target_tier} | {model_tier} | {evaluated} | {formal_mean:.3f} +/- {formal_sd:.3f} | "
            "{stepwise_mean:.3f} +/- {stepwise_sd:.3f} | {full_pass}/{evaluated} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Static-Client Comparison Focus",
            "",
            "| Suite | Tier | Model | Backend n | Static n | Formal delta | Route/persistence failures | Service failures | Service scenario failures |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in aggregate["comparison"]["rows"]:
        if not row["backend_runs"] and not row["static_runs"]:
            continue
        lines.append(
            "| {suite} | {tier} | `{model}` | {backend_runs} | {static_runs} | {formal_delta_backend_minus_static:.3f} | "
            "{backend_route_persistence_failures}/{static_route_persistence_failures} | "
            "{backend_service_interaction_failures}/{static_service_interaction_failures} | "
            "{backend_service_scenario_failures}/{static_service_scenario_failures} |".format(**row)
        )
    return "\n".join(lines) + "\n"


def status_line(phase: str, record: dict[str, Any]) -> str:
    prefix = (
        f"[{phase}] suite={record['suite']} tier={record['target_tier']} group={record['model_tier']} "
        f"model={record['slug']} rep={record['rep']} status={record.get('status')}"
    )
    if phase == "evaluate" and record.get("formal_ratio") is not None:
        return (
            f"{prefix} scenarios={record.get('scenarios_passed')}/{record.get('scenarios_total')} "
            f"formal={record.get('formal_ratio'):.3f} stepwise={record.get('stepwise_ratio'):.3f} "
            f"contract={record.get('contract_ratio'):.3f}"
        )
    if record.get("returncode") not in (None, 0):
        return f"{prefix} returncode={record.get('returncode')}"
    return prefix


def failure_label(raw: Any) -> str:
    if raw is None:
        return "none"
    text = str(raw)
    lower = text.lower()
    if not text:
        return "unknown"
    if "invalid_state_hook" in lower or "state_hook" in lower or "observation" in lower:
        return "invalid observation surface"
    if "missing_component" in lower or "missing selector" in lower or "selector" in lower:
        return "missing interaction surface"
    if "timeout" in lower or "not visible" in lower or "disabled" in lower or "covered" in lower:
        return "unavailable control"
    if "browser_page" in lower or "route" in lower or "navigation" in lower or "reload" in lower:
        return "route / persistence drift"
    if "table" in lower or "rendered" in lower:
        return "rendered-projection mismatch"
    if "service" in lower or "network" in lower or "api" in lower:
        return "service interaction failure"
    if "state" in lower or "assertion" in lower or "delta" in lower:
        return "wrong state transition"
    if "crash" in lower or "exception" in lower or "error" in lower:
        return "runtime error"
    return text.replace("_", " ")


def ensure_results_path(path: Path) -> None:
    root = RESULTS_ROOT.resolve()
    resolved = path.resolve()
    if resolved != root and not resolved.is_relative_to(root):
        raise SystemExit(f"Refusing to write artifacts outside {root}: {resolved}")


def safe_get(mapping: Any, *path: str) -> Any:
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def mean(values: list[Any]) -> float:
    numbers = [float(value) for value in values if value not in (None, "")]
    return statistics.fmean(numbers) if numbers else 0.0


def stdev(values: list[Any]) -> float:
    numbers = [float(value) for value in values if value not in (None, "")]
    return statistics.stdev(numbers) if len(numbers) > 1 else 0.0


def top_counts(values: list[Any], limit: int = 3) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit])


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def empty_summary(key: tuple[str, str, str, str]) -> dict[str, Any]:
    return {
        "runs": 0,
        "formal_mean": 0.0,
        "stepwise_mean": 0.0,
        "full_pass": 0,
        "route_persistence_failures": 0,
        "service_interaction_failures": 0,
        "service_scenarios": 0,
        "service_scenario_failures": 0,
    }


def delta(left: float | None, right: float | None) -> float:
    return float(left or 0.0) - float(right or 0.0)


def write_json(path: Path, payload: Any) -> None:
    ensure_results_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    ensure_results_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_results_path(path)
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


def tail(text: str, limit: int = 2000) -> str:
    return text[-limit:] if len(text) > limit else text


if __name__ == "__main__":
    raise SystemExit(main())
