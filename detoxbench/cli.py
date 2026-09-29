from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from detoxbench import __version__
from detoxbench.cohorts import cohort_fingerprint
from detoxbench.cohorts import load_cohort_manifest
from detoxbench.dashboard import DashboardConfig, build_dashboard
from detoxbench.gallery import GalleryConfig, build_gallery
from detoxbench.known_bad import assess_known_bad_result
from detoxbench.known_bad import load_known_bad_fixtures
from detoxbench.target_inventory import discover_target_inventory
from detoxbench.target_inventory import summarize_target_inventory
from detoxbench.dsl import compile_dsl_to_web_suite, load_dsl_yaml
from detoxbench.dsl.scenario_sets import discover_scenario_paths
from detoxbench.dsl.scenario_sets import load_scenario_bundles
from detoxbench.web.evaluator import WebEvaluationConfig, WebEvaluator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="conformweb",
        description="Run ConformWeb contract-grounded behavioral evaluations.",
    )
    parser.add_argument("--version", action="version", version=f"ConformWeb {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_targets = subparsers.add_parser(
        "list-targets",
        help="List released benchmark targets and their runnable scenario sets.",
    )
    list_targets.add_argument(
        "--targets-root",
        type=Path,
        default=Path("targets/web"),
        help="Directory containing family/tier target directories.",
    )
    list_targets.add_argument("--json", action="store_true")

    validate_target = subparsers.add_parser(
        "validate-target",
        help="Compile a target without launching a browser.",
    )
    validate_target.add_argument("--target", type=Path, required=True)
    validate_target.add_argument(
        "--scenario-set",
        choices=["all", "public", "private"],
        default="all",
    )

    evaluate_dsl = subparsers.add_parser(
        "evaluate-dsl",
        help="Compile a DSL target and evaluate it with the web runner.",
    )
    evaluate_dsl.add_argument(
        "--target",
        type=Path,
        help="Target directory containing contract.dsl.yaml and scenarios.dsl.yaml.",
    )
    evaluate_dsl.add_argument("--contract-dsl", type=Path, help="Path to contract.dsl.yaml.")
    evaluate_dsl.add_argument(
        "--scenarios-dsl",
        type=Path,
        action="append",
        help="Path to a scenario DSL file. May be supplied more than once.",
    )
    evaluate_dsl.add_argument(
        "--scenario-set",
        choices=["all", "public", "private"],
        default="all",
        help="Scenario visibility to run when split public/private files are present.",
    )
    candidate = evaluate_dsl.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--app-url", help="Existing app URL.")
    candidate.add_argument("--static-dir", type=Path, help="Directory to serve.")
    evaluate_dsl.add_argument("--output", type=Path, help="Directory for run logs and screenshots.")
    evaluate_dsl.add_argument("--run-subject", help="Human-readable subject for this run.")
    evaluate_dsl.add_argument("--headless", action="store_true", default=True)
    evaluate_dsl.add_argument("--headed", action="store_true")
    evaluate_dsl.add_argument("--slow-mo", type=int, default=0)
    evaluate_dsl.add_argument("--action-timeout", type=int, default=5000)
    evaluate_dsl.add_argument(
        "--screenshot-policy",
        choices=["all", "failures", "none"],
        default="all",
        help="Screenshots to retain. Paper reproduction uses all.",
    )
    evaluate_dsl.add_argument("--json", action="store_true")

    known_bad = subparsers.add_parser(
        "known-bad",
        help="Evaluate known-bad fixtures and verify that they fail as expected.",
    )
    known_bad.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Target directory containing contract.dsl.yaml and known-bad fixtures.",
    )
    known_bad.add_argument(
        "--scenario-set",
        choices=["all", "public", "private"],
        default="all",
        help="Scenario visibility to run when split public/private files are present.",
    )
    known_bad.add_argument("--headless", action="store_true", default=True)
    known_bad.add_argument("--headed", action="store_true")
    known_bad.add_argument("--slow-mo", type=int, default=0)
    known_bad.add_argument("--action-timeout", type=int, default=5000)
    known_bad.add_argument("--json", action="store_true")

    cohort_info = subparsers.add_parser(
        "cohort-info",
        help="Validate a model cohort manifest and print reproducibility fingerprints.",
    )
    cohort_info.add_argument("--manifest", type=Path, required=True)

    dashboard = subparsers.add_parser(
        "dashboard",
        help="Build a static HTML dashboard for ConformWeb run artifacts.",
    )
    dashboard.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Target directory containing contract DSL and cohort run artifacts.",
    )
    dashboard.add_argument(
        "--runs-dir",
        type=Path,
        help="Run artifact root. Defaults to <target>/cohorts when present, otherwise <target>/artifacts/runs.",
    )
    dashboard.add_argument(
        "--output",
        type=Path,
        help="Output HTML file. Defaults to <target>/reports/dashboard/index.html.",
    )
    dashboard.add_argument(
        "--title",
        help="Dashboard title.",
    )

    gallery = subparsers.add_parser(
        "gallery",
        help="Build a static suite gallery across ConformWeb targets.",
    )
    gallery.add_argument(
        "--targets-root",
        type=Path,
        help="Directory containing target folders. Defaults to targets/web when no manifest is supplied.",
    )
    gallery.add_argument(
        "--manifest",
        type=Path,
        help="Optional YAML manifest for cross-worktree target dashboards.",
    )
    gallery.add_argument(
        "--output",
        type=Path,
        help="Output HTML file. Defaults to reports/gallery/index.html.",
    )
    gallery.add_argument("--title", help="Gallery title.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list-targets":
        return list_targets_command(args)
    if args.command == "validate-target":
        return validate_target_command(args)
    if args.command == "evaluate-dsl":
        return evaluate_dsl_command(args)
    if args.command == "known-bad":
        return known_bad_command(args)
    if args.command == "cohort-info":
        return cohort_info_command(args)
    if args.command == "dashboard":
        return dashboard_command(args)
    if args.command == "gallery":
        return gallery_command(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def list_targets_command(args: argparse.Namespace) -> int:
    targets_root = args.targets_root.resolve()
    inventory = discover_target_inventory(targets_root)
    summary = summarize_target_inventory(inventory)
    if args.json:
        print(
            json.dumps(
                {
                    "targets_root": str(targets_root),
                    "summary": summary,
                    "targets": [item.to_dict() for item in inventory],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    headers = ("TARGET", "STATUS", "PUBLIC", "PRIVATE", "TOTAL", "REFERENCE")
    rows = [
        (
            item.target,
            item.status,
            str(item.public_scenarios),
            str(item.private_scenarios),
            str(item.scenario_total),
            "yes" if item.reference_app else "no",
        )
        for item in inventory
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        if rows
        else len(headers[index])
        for index in range(len(headers))
    ]
    print("  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
    print()
    print(
        "Summary: "
        f"{summary['target_slots']} slots, "
        f"{summary['status_counts'].get('ready', 0)} ready, "
        f"{summary['status_counts'].get('public-only', 0)} public-only, "
        f"{summary['status_counts'].get('unavailable', 0)} unavailable; "
        f"{summary['public_scenarios']} public + "
        f"{summary['private_scenarios']} private = "
        f"{summary['scenario_total']} scenarios"
    )
    return 0


def validate_target_command(args: argparse.Namespace) -> int:
    target_dir = args.target.resolve()
    contract_path = target_dir / "contract.dsl.yaml"
    scenario_paths = discover_scenario_paths(target_dir, scenario_set=args.scenario_set)
    if not contract_path.is_file():
        raise SystemExit(f"Missing contract: {contract_path}")
    if not scenario_paths:
        raise SystemExit(
            f"No {args.scenario_set!r} scenario files available under {target_dir}"
        )

    raw_contract = load_dsl_yaml(contract_path)
    scenarios_dsl = load_scenario_bundles(scenario_paths, scenario_set=args.scenario_set)
    _, scenarios = compile_dsl_to_web_suite(raw_contract, scenarios_dsl)
    raw_scenarios = scenarios_dsl["scenarios"]
    scoring = sum(1 for scenario in raw_scenarios if scenario.get("kind", "scoring") == "scoring")
    probes = sum(1 for scenario in raw_scenarios if scenario.get("kind", "scoring") == "probe")
    payload = {
        "valid": True,
        "target": str(target_dir),
        "app_id": raw_contract.get("app", {}).get("id"),
        "dsl_version": raw_contract.get("dsl_version"),
        "scenario_set": args.scenario_set,
        "scenario_sources": [str(path.resolve()) for path in scenario_paths],
        "scenarios": len(scenarios.scenarios),
        "scoring_scenarios": scoring,
        "probe_scenarios": probes,
        "compiled_steps": sum(len(scenario.get("steps", [])) for scenario in scenarios.scenarios),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def dashboard_command(args: argparse.Namespace) -> int:
    target_dir = args.target.resolve()
    runs_dir = (args.runs_dir or default_runs_dir(target_dir)).resolve()
    output = (args.output or target_dir / "reports" / "dashboard" / "index.html").resolve()
    title = args.title or f"ConformWeb Dashboard: {target_dir.name}"

    result = build_dashboard(
        DashboardConfig(
            target_dir=target_dir,
            runs_dir=runs_dir,
            output=output,
            title=title,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def evaluate_dsl_command(args: argparse.Namespace) -> int:
    target_dir = args.target.resolve() if args.target else None
    contract_path = args.contract_dsl
    scenario_paths = list(args.scenarios_dsl or [])
    if target_dir:
        contract_path = contract_path or target_dir / "contract.dsl.yaml"
        if not scenario_paths:
            scenario_paths = discover_scenario_paths(target_dir, scenario_set=args.scenario_set)
    if not contract_path or not scenario_paths:
        raise SystemExit("--target or both --contract-dsl and --scenarios-dsl are required")

    contract_path = contract_path.resolve()
    scenario_paths = [path.resolve() for path in scenario_paths]
    scenarios_dsl = load_scenario_bundles(scenario_paths, scenario_set=args.scenario_set)
    contract, scenarios = compile_dsl_to_web_suite(
        load_dsl_yaml(contract_path),
        scenarios_dsl,
    )

    static_dir = args.static_dir.resolve() if args.static_dir else None
    output_dir = args.output
    run_subject = args.run_subject
    if not run_subject:
        if static_dir:
            run_subject = safe_subject(static_dir.name)
        elif args.app_url:
            run_subject = "app_url"
        else:
            run_subject = "reference"
    run_subject = safe_subject(run_subject)

    if not output_dir:
        base = target_dir or contract_path.parent
        output_dir = base / "cohorts" / "manual" / "runs" / run_subject
    output_dir = output_dir.resolve()

    config = WebEvaluationConfig(
        app_url=args.app_url,
        static_dir=static_dir,
        output_dir=output_dir,
        run_subject=run_subject,
        headless=not args.headed,
        slow_mo_ms=args.slow_mo,
        action_timeout_ms=args.action_timeout,
        screenshot_policy=args.screenshot_policy,
    )
    result = WebEvaluator(contract, scenarios, config).run()
    payload = result.to_dict() if args.json else compact_result(result.to_dict())
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


def known_bad_command(args: argparse.Namespace) -> int:
    target_dir = args.target.resolve()
    fixtures = load_known_bad_fixtures(target_dir)
    if not fixtures:
        raise SystemExit(f"No known-bad fixtures found under {target_dir / 'fixtures' / 'known_bad'}")

    contract_path = target_dir / "contract.dsl.yaml"
    scenario_paths = discover_scenario_paths(target_dir, scenario_set=args.scenario_set)
    scenarios_dsl = load_scenario_bundles(scenario_paths, scenario_set=args.scenario_set)
    contract, scenarios = compile_dsl_to_web_suite(
        load_dsl_yaml(contract_path),
        scenarios_dsl,
    )

    assessments = []
    for fixture in fixtures:
        config = WebEvaluationConfig(
            app_url=None,
            static_dir=fixture.path,
            output_dir=target_dir / "artifacts" / "runs" / f"known_bad_{fixture.id}",
            run_subject=safe_subject(f"known_bad_{fixture.id}"),
            headless=not args.headed,
            slow_mo_ms=args.slow_mo,
            action_timeout_ms=args.action_timeout,
        )
        run = WebEvaluator(contract, scenarios, config).run()
        assessments.append(assess_known_bad_result(fixture, run))

    payload = {
        "target": str(target_dir),
        "scenario_set": args.scenario_set,
        "passed": all(assessment.passed for assessment in assessments),
        "fixtures": [assessment.to_dict() for assessment in assessments],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


def cohort_info_command(args: argparse.Namespace) -> int:
    manifest = load_cohort_manifest(args.manifest)
    print(json.dumps(cohort_fingerprint(manifest), ensure_ascii=False, indent=2))
    return 0


def compact_result(result: dict) -> dict:
    scenarios = []
    for scenario in result["scenarios"]:
        completed_steps = scenario.get("completed_step_count", len(scenario["steps"]))
        expected_steps = scenario.get("expected_step_count", len(scenario["steps"]))
        passed_steps = scenario.get(
            "passed_step_count",
            sum(1 for step in scenario["steps"] if step.get("passed")),
        )
        passed_until_step = scenario.get("passed_until_step")
        if passed_until_step is None:
            passed_until_step = expected_steps if scenario["passed"] else passed_steps
        failed_assertions = []
        for step in scenario["steps"]:
            for assertion in step["assertions"]:
                if not assertion["passed"]:
                    failed_assertions.append(
                        {
                            "step_index": step["step_index"],
                            "action": step["action"],
                            "component": step["component"],
                            "assertion": assertion,
                        }
                    )
        scenarios.append(
            {
                "id": scenario["id"],
                "tier": scenario.get("tier"),
                "difficulty": scenario.get("difficulty"),
                "kind": scenario.get("kind"),
                "weight": scenario.get("weight"),
                "passed": scenario["passed"],
                "score": scenario.get("score"),
                "step_progress": f"{passed_until_step}/{expected_steps}",
                "completed_steps": completed_steps,
                "expected_steps": expected_steps,
                "passed_steps": passed_steps,
                "passed_until_step": passed_until_step,
                "first_failed_step": scenario.get("first_failed_step"),
                "first_failure": scenario.get("first_failure"),
                "failure_category": scenario.get("failure_category"),
                "error": scenario["error"],
                "failed_assertions": failed_assertions,
            }
        )

    return {
        "run_id": result["run_id"],
        "subject": result.get("subject"),
        "passed": result["passed"],
        "output_dir": result["output_dir"],
        "score": result.get("score"),
        "scenarios": scenarios,
    }


def gallery_command(args: argparse.Namespace) -> int:
    targets_root = args.targets_root
    manifest = args.manifest.resolve() if args.manifest else None
    if not targets_root and not manifest:
        targets_root = Path("targets/web")
    if targets_root:
        targets_root = targets_root.resolve()
    output = (args.output or Path("reports/gallery/index.html")).resolve()
    title = args.title or "ConformWeb Target Gallery"
    result = build_gallery(
        GalleryConfig(
            output=output,
            title=title,
            targets_root=targets_root,
            manifest=manifest,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def default_runs_dir(target_dir: Path) -> Path:
    cohorts = target_dir / "cohorts"
    if cohorts.exists():
        return cohorts
    return target_dir / "artifacts" / "runs"


def safe_subject(value: str) -> str:
    subject = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return subject.strip("._-") or "manual"
