from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from detoxbench.core.models import classify_failure
from detoxbench.core.yaml_loader import load_yaml
from detoxbench.dsl.scenario_sets import discover_scenario_paths
from detoxbench.dsl.scenario_sets import infer_visibility


@dataclass(frozen=True)
class DashboardConfig:
    target_dir: Path
    runs_dir: Path
    output: Path
    title: str


CONTRACT_FAILURE_CATEGORIES = {
    "missing_state_hook",
    "invalid_state_hook",
    "missing_component",
    "unknown_component",
    "undeclared_action",
    "unsupported_action",
    "action_unavailable",
    "interaction_timeout",
    "screenshot_timeout",
    "assertion_browser_page_equals",
}


def build_dashboard(config: DashboardConfig) -> dict[str, Any]:
    data = build_dashboard_data(config)
    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.output.write_text(render_dashboard_html(data), encoding="utf-8")
    return {
        "output": str(config.output),
        "runs": len(data["runs"]),
        "subjects": len(data["subjects"]),
        "scenarios": len(data["scenarios"]),
    }


def build_dashboard_data(config: DashboardConfig) -> dict[str, Any]:
    scenario_metadata = load_scenario_metadata(dashboard_scenario_paths(config.target_dir))
    summaries = discover_summary_paths(config.runs_dir)
    runs = [
        normalize_run(summary_path, config.output.parent, scenario_metadata)
        for summary_path in summaries
    ]
    runs.sort(key=lambda run: (run["subject"], run["run_id"]))
    runs = latest_runs_by_subject(runs)

    subjects: dict[str, list[dict[str, Any]]] = {}
    scenarios: dict[str, dict[str, Any]] = {}
    for run in runs:
        subjects.setdefault(run["subject"], []).append(run)
        for scenario in run["scenarios"]:
            scenario_id = scenario["id"]
            scenarios.setdefault(
                scenario_id,
                {
                    "id": scenario_id,
                    "description": scenario.get("description"),
                    "tier": scenario.get("tier", "unclassified"),
                    "difficulty": scenario.get("difficulty", "unclassified"),
                    "kind": scenario.get("kind", "scoring"),
                    "weight": scenario.get("weight", 1.0),
                    "visibility": scenario.get("visibility", "private"),
                    "step_count": scenario.get("expected_step_count"),
                },
            )

    subject_rows = []
    for subject, subject_runs in subjects.items():
        latest = max(subject_runs, key=lambda run: run["run_id"])
        subject_rows.append(
            {
                "name": subject,
                "default_run_id": latest["run_id"],
                "default_visible": default_visible_subject(subject),
                "runs": [
                    {
                        "run_id": run["run_id"],
                        "passed": run["passed"],
                        "scenario_count": run["scenario_count"],
                        "step_count": run["step_count"],
                        "failed_scenario_count": run["failed_scenario_count"],
                        "failed_assertion_count": run["failed_assertion_count"],
                        "first_failure": run["first_failure"],
                        "score": run["score"],
                        "tier_stats": run["tier_stats"],
                        "difficulty_stats": run["difficulty_stats"],
                    }
                    for run in subject_runs
                ],
            }
        )

    subject_rows.sort(key=lambda subject: subject["name"])
    scenario_rows = sorted(scenarios.values(), key=lambda scenario: scenario["id"])

    return {
        "title": config.title,
        "target": config.target_dir.name,
        "target_label": target_label(config.target_dir),
        "target_path": str(config.target_dir),
        "runs_dir": str(config.runs_dir),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "subjects": subject_rows,
        "scenarios": scenario_rows,
        "tier_summary": tier_summary(scenario_rows),
        "difficulty_summary": difficulty_summary(scenario_rows),
        "runs": runs,
    }


def discover_summary_paths(runs_dir: Path) -> list[Path]:
    if not runs_dir.exists():
        return []
    return sorted(runs_dir.rglob("summary.json"))


def load_scenario_metadata(paths: list[Path] | Path) -> dict[str, dict[str, Any]]:
    if isinstance(paths, Path):
        paths = [paths]
    metadata = {}
    for path in paths:
        if not path.exists():
            continue
        try:
            raw = load_yaml(path)
        except Exception:  # noqa: BLE001 - dashboard should still render old artifacts.
            continue
        visibility = infer_visibility(raw, path)
        for scenario in raw.get("scenarios", []):
            if not isinstance(scenario, dict) or "id" not in scenario:
                continue
            metadata[str(scenario["id"])] = {
                "description": scenario.get("description"),
                "tier": scenario.get("tier", "unclassified"),
                "difficulty": scenario.get("difficulty", "unclassified"),
                "kind": scenario.get("kind", "scoring"),
                "weight": scenario.get("weight", 1.0),
                "visibility": scenario.get("visibility", visibility),
                "contract_refs": list(scenario.get("contract_refs", [])),
                "source": str(path),
                "step_count": len(scenario.get("steps", [])),
            }
    return metadata


def dashboard_scenario_paths(target_dir: Path) -> list[Path]:
    return discover_scenario_paths(target_dir, scenario_set="all")


def latest_runs_by_subject(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        subject = run["subject"]
        if subject not in latest or run["run_id"] > latest[subject]["run_id"]:
            latest[subject] = run
    return sorted(latest.values(), key=lambda run: run["subject"])


def normalize_run(
    summary_path: Path,
    asset_base_dir: Path,
    scenario_metadata: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    raw = json.loads(summary_path.read_text(encoding="utf-8"))
    run_dir = summary_path.parent
    subject = raw.get("subject") or run_dir.parent.name
    scenarios = [
        normalize_scenario(scenario, asset_base_dir, scenario_metadata, run_dir)
        for scenario in raw["scenarios"]
    ]
    failed_assertion_count = sum(
        1
        for scenario in scenarios
        for step in scenario["steps"]
        for assertion in step["assertions"]
        if not assertion["passed"]
    )
    step_count = sum(len(scenario["steps"]) for scenario in scenarios)
    failed_scenario_count = sum(1 for scenario in scenarios if not scenario["passed"])
    return {
        "subject": str(subject),
        "run_id": str(raw["run_id"]),
        "passed": bool(raw["passed"]),
        "score": normalize_score(raw.get("score"), scenarios),
        "output_dir": str(run_dir),
        "summary_path": str(summary_path),
        "summary_ref": relative_ref(summary_path, asset_base_dir),
        "scenario_count": len(scenarios),
        "step_count": step_count,
        "failed_scenario_count": failed_scenario_count,
        "failed_assertion_count": failed_assertion_count,
        "first_failure": run_first_failure(scenarios),
        "tier_stats": run_tier_stats(scenarios),
        "difficulty_stats": run_difficulty_stats(scenarios),
        "scenarios": scenarios,
    }


def target_label(target_dir: Path) -> str:
    contract_path = target_dir / "contract.dsl.yaml"
    if contract_path.exists():
        try:
            contract = load_yaml(contract_path)
        except Exception:  # noqa: BLE001 - dashboard should still render if metadata is partial.
            return target_dir.name
        if "app" in contract and isinstance(contract["app"], dict):
            return str(contract["app"].get("name") or contract["app"].get("id") or target_dir.name)
    return target_dir.name


def normalize_scenario(
    scenario: dict[str, Any],
    asset_base_dir: Path,
    scenario_metadata: dict[str, dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any]:
    metadata = scenario_metadata.get(str(scenario["id"]), {})
    steps = [normalize_step(step, asset_base_dir, run_dir) for step in scenario["steps"]]
    expected_step_count = (
        int_or_none(scenario.get("expected_step_count"))
        or int_or_none(metadata.get("step_count"))
        or max(len(steps), int_or_none(scenario.get("error_step_index")) or 0)
    )
    completed_step_count = int_or_none(scenario.get("completed_step_count")) or len(steps)
    passed_step_count = int_or_none(scenario.get("passed_step_count"))
    if passed_step_count is None:
        passed_step_count = sum(1 for step in steps if step["passed"])
    first_failure = scenario.get("first_failure") or infer_first_failure(scenario, steps)
    first_failed_step = int_or_none(scenario.get("first_failed_step"))
    if first_failed_step is None and first_failure:
        first_failed_step = int_or_none(first_failure.get("step_index"))
    passed_until_step = int_or_none(scenario.get("passed_until_step"))
    if passed_until_step is None:
        if first_failed_step is not None:
            passed_until_step = max(0, first_failed_step - 1)
        elif bool(scenario["passed"]):
            passed_until_step = expected_step_count
        else:
            passed_until_step = passed_step_count
    failure_category = scenario.get("failure_category")
    if not failure_category and first_failure:
        failure_category = classify_failure(first_failure)
    return {
        "id": scenario["id"],
        "tier": scenario.get("tier") or metadata.get("tier") or "unclassified",
        "difficulty": scenario.get("difficulty") or metadata.get("difficulty") or "unclassified",
        "kind": scenario.get("kind") or metadata.get("kind") or "scoring",
        "weight": scenario.get("weight") or metadata.get("weight") or 1.0,
        "visibility": scenario.get("visibility") or metadata.get("visibility") or "private",
        "contract_refs": scenario.get("contract_refs") or metadata.get("contract_refs") or [],
        "source": scenario.get("source") or metadata.get("source"),
        "score": scenario.get("score") or fallback_scenario_score(scenario, metadata),
        "description": scenario.get("description") or metadata.get("description"),
        "passed": bool(scenario["passed"]),
        "error": scenario.get("error"),
        "expected_step_count": expected_step_count,
        "completed_step_count": completed_step_count,
        "passed_step_count": passed_step_count,
        "passed_until_step": passed_until_step,
        "first_failed_step": first_failed_step,
        "first_failure": first_failure,
        "failure_category": failure_category,
        "progress_label": f"{passed_until_step}/{expected_step_count}",
        "steps": steps,
        "failed_assertion_count": sum(
            1
            for step in steps
            for assertion in step["assertions"]
            if not assertion["passed"]
        ),
    }


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def infer_first_failure(
    scenario: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for step in steps:
        for assertion in step["assertions"]:
            if not assertion["passed"]:
                return {
                    "kind": "assertion",
                    "step_index": step["step_index"],
                    "action": step["action"],
                    "component": step.get("component"),
                    "assertion_type": assertion.get("type"),
                    "message": assertion.get("message"),
                    "actual": assertion.get("actual"),
                    "expected": assertion.get("expected"),
                }
        if not step["passed"]:
            return {
                "kind": "step",
                "step_index": step["step_index"],
                "action": step["action"],
                "component": step.get("component"),
                "message": "Step failed without a failed assertion.",
            }
    if scenario.get("error"):
        return {
            "kind": "scenario_error",
            "step_index": int_or_none(scenario.get("error_step_index")) or len(steps) + 1,
            "action": None,
            "component": None,
            "message": scenario["error"],
        }
    return None


def run_first_failure(scenarios: list[dict[str, Any]]) -> dict[str, Any] | None:
    for scenario in scenarios:
        if scenario["passed"]:
            continue
        first_failure = scenario.get("first_failure")
        if first_failure:
            return {
                "scenario_id": scenario["id"],
                "failure_category": scenario.get("failure_category"),
                **first_failure,
            }
    return None


def tier_summary(scenarios: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for scenario in scenarios:
        tier = str(scenario.get("tier") or "unclassified")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def difficulty_summary(scenarios: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for scenario in scenarios:
        difficulty = str(scenario.get("difficulty") or "unclassified")
        counts[difficulty] = counts.get(difficulty, 0) + 1
    return counts


def run_tier_stats(scenarios: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for scenario in scenarios:
        tier = str(scenario.get("tier") or "unclassified")
        row = stats.setdefault(tier, {"passed": 0, "failed": 0, "total": 0})
        row["total"] += 1
        if scenario["passed"]:
            row["passed"] += 1
        else:
            row["failed"] += 1
    return stats


def run_difficulty_stats(scenarios: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for scenario in scenarios:
        difficulty = str(scenario.get("difficulty") or "unclassified")
        row = stats.setdefault(difficulty, {"passed": 0, "failed": 0, "total": 0})
        row["total"] += 1
        if scenario["passed"]:
            row["passed"] += 1
        else:
            row["failed"] += 1
    return stats


def fallback_scenario_score(
    scenario: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    kind = scenario.get("kind") or metadata.get("kind") or "scoring"
    weight = float(scenario.get("weight") or metadata.get("weight") or 1.0)
    earned = weight if kind == "scoring" and scenario.get("passed") else 0.0
    return {
        "earned": earned,
        "possible": weight if kind == "scoring" else 0.0,
        "ratio": 1.0 if earned else 0.0,
        "included": kind == "scoring",
    }


def fallback_score(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    formal_possible = 0.0
    formal_earned = 0.0
    stepwise_possible = 0.0
    stepwise_earned = 0.0
    by_tier: dict[str, dict[str, Any]] = {}
    by_capability: dict[str, dict[str, Any]] = {}
    by_difficulty: dict[str, dict[str, Any]] = {}
    failure_breakdown: dict[str, int] = {}
    contract_failure_breakdown: dict[str, int] = {}
    contract_failure_count = 0
    scoring_count = 0
    probe_total = 0
    probe_passed = 0
    for scenario in scenarios:
        if scenario.get("kind", "scoring") == "probe":
            probe_total += 1
            if scenario.get("passed"):
                probe_passed += 1
            continue
        scoring_count += 1
        weight = float(scenario.get("weight") or 1.0)
        step_ratio = scenario_step_ratio(scenario)
        step_earned = weight * step_ratio
        formal_possible += weight
        stepwise_possible += weight
        stepwise_earned += step_earned
        if scenario.get("passed"):
            formal_earned += weight
        failure_category = scenario.get("failure_category")
        if failure_category:
            failure_breakdown[failure_category] = failure_breakdown.get(failure_category, 0) + 1
            if failure_category in CONTRACT_FAILURE_CATEGORIES:
                contract_failure_count += 1
                contract_failure_breakdown[failure_category] = (
                    contract_failure_breakdown.get(failure_category, 0) + 1
                )
        tier = scenario.get("tier") or "unclassified"
        difficulty = scenario.get("difficulty") or "unclassified"
        row = by_tier.setdefault(
            tier,
            {
                "earned": 0.0,
                "possible": 0.0,
                "step_earned": 0.0,
                "step_possible": 0.0,
                "passed": 0,
                "failed": 0,
                "total": 0,
            },
        )
        row["possible"] += weight
        row["earned"] += weight if scenario.get("passed") else 0.0
        row["step_possible"] += weight
        row["step_earned"] += step_earned
        row["total"] += 1
        row["passed" if scenario.get("passed") else "failed"] += 1
        difficulty_row = by_difficulty.setdefault(
            difficulty,
            {
                "earned": 0.0,
                "possible": 0.0,
                "step_earned": 0.0,
                "step_possible": 0.0,
                "passed": 0,
                "failed": 0,
                "total": 0,
            },
        )
        difficulty_row["possible"] += weight
        difficulty_row["earned"] += weight if scenario.get("passed") else 0.0
        difficulty_row["step_possible"] += weight
        difficulty_row["step_earned"] += step_earned
        difficulty_row["total"] += 1
        difficulty_row["passed" if scenario.get("passed") else "failed"] += 1
        capability_row = by_capability.setdefault(
            tier,
            {
                "scenario_earned": 0.0,
                "scenario_possible": 0.0,
                "step_earned": 0.0,
                "step_possible": 0.0,
                "passed": 0,
                "failed": 0,
                "total": 0,
            },
        )
        capability_row["scenario_possible"] += weight
        capability_row["scenario_earned"] += weight if scenario.get("passed") else 0.0
        capability_row["step_possible"] += weight
        capability_row["step_earned"] += step_earned
        capability_row["total"] += 1
        capability_row["passed" if scenario.get("passed") else "failed"] += 1
    for row in by_tier.values():
        row["ratio"] = row["earned"] / row["possible"] if row["possible"] else 0.0
        row["step_ratio"] = (
            row["step_earned"] / row["step_possible"] if row["step_possible"] else 0.0
        )
    for row in by_difficulty.values():
        row["ratio"] = row["earned"] / row["possible"] if row["possible"] else 0.0
        row["step_ratio"] = (
            row["step_earned"] / row["step_possible"] if row["step_possible"] else 0.0
        )
    for row in by_capability.values():
        row["scenario_ratio"] = (
            row["scenario_earned"] / row["scenario_possible"]
            if row["scenario_possible"]
            else 0.0
        )
        row["step_ratio"] = (
            row["step_earned"] / row["step_possible"] if row["step_possible"] else 0.0
        )
    return {
        "formal": {
            "earned": formal_earned,
            "possible": formal_possible,
            "ratio": formal_earned / formal_possible if formal_possible else 0.0,
        },
        "stepwise": {
            "earned": stepwise_earned,
            "possible": stepwise_possible,
            "ratio": stepwise_earned / stepwise_possible if stepwise_possible else 0.0,
        },
        "by_tier": by_tier,
        "by_difficulty": by_difficulty,
        "by_capability": by_capability,
        "contract": {
            "earned": max(0, scoring_count - contract_failure_count),
            "possible": scoring_count,
            "ratio": (
                (scoring_count - contract_failure_count) / scoring_count
                if scoring_count
                else 0.0
            ),
            "failures": contract_failure_count,
            "failure_breakdown": contract_failure_breakdown,
        },
        "failure_breakdown": failure_breakdown,
        "probe": {"passed": probe_passed, "total": probe_total},
    }


def normalize_score(
    raw_score: Any,
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    score = fallback_score(scenarios)
    if not isinstance(raw_score, dict):
        return score
    for key, value in raw_score.items():
        if key not in score:
            score[key] = value
    return score


def scenario_step_ratio(scenario: dict[str, Any]) -> float:
    if scenario.get("passed"):
        return 1.0
    total = int_or_none(scenario.get("expected_step_count")) or 0
    if total <= 0:
        return 0.0
    passed_until = int_or_none(scenario.get("passed_until_step")) or 0
    return max(0.0, min(1.0, passed_until / total))


def normalize_step(step: dict[str, Any], asset_base_dir: Path, run_dir: Path) -> dict[str, Any]:
    before_state = step.get("before_state", {})
    after_state = step.get("after_state", {})
    screenshots = step.get("screenshots", {})
    assertions = step.get("assertions", [])
    before_screenshot = normalize_screenshot_ref(
        screenshots.get("before"), asset_base_dir, run_dir
    )
    after_screenshot = normalize_screenshot_ref(
        screenshots.get("after"), asset_base_dir, run_dir
    )
    return {
        "scenario_id": step["scenario_id"],
        "step_index": step["step_index"],
        "action": step["action"],
        "component": step.get("component"),
        "passed": bool(step["passed"]),
        "before_state": before_state,
        "after_state": after_state,
        "state_diff": diff_states(before_state, after_state),
        "screenshots": {
            "before": before_screenshot,
            "after": after_screenshot,
        },
        "assertions": assertions,
    }


def normalize_screenshot_ref(value: Any, asset_base_dir: Path, run_dir: Path) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    screenshot = resolve_run_artifact(Path(value), run_dir)
    return relative_ref(screenshot, asset_base_dir)


def resolve_run_artifact(path: Path, run_dir: Path) -> Path:
    if path.exists():
        return path
    parts = path.parts
    if "screenshots" in parts:
        index = parts.index("screenshots")
        candidate = run_dir.joinpath(*parts[index:])
        if candidate.exists():
            return candidate
    return path


def diff_states(before: Any, after: Any) -> list[dict[str, Any]]:
    before_flat = flatten_state(before)
    after_flat = flatten_state(after)
    paths = sorted(set(before_flat) | set(after_flat))
    changes = []
    for path in paths:
        before_value = before_flat.get(path, {"__missing__": True})
        after_value = after_flat.get(path, {"__missing__": True})
        if before_value != after_value:
            changes.append(
                {
                    "path": path,
                    "before": before_value,
                    "after": after_value,
                }
            )
    return changes


def flatten_state(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        if not value:
            return {prefix or "$": {}}
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten_state(child, child_prefix))
        return result
    if isinstance(value, list):
        if not value:
            return {prefix or "$": []}
        result = {}
        for index, child in enumerate(value):
            child_prefix = f"{prefix}.{index}" if prefix else str(index)
            result.update(flatten_state(child, child_prefix))
        return result
    return {prefix or "$": value}


def relative_ref(path: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()


def default_visible_subject(subject: str) -> bool:
    lowered = subject.lower()
    return not any(token in lowered for token in ["diagnostic", "probe", "known_bad"])


def render_dashboard_html(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    template_path = Path(__file__).with_name("dashboard_template.html")
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
        return template.replace("__DASHBOARD_DATA__", payload)
    return DASHBOARD_HTML.replace("__DASHBOARD_DATA__", payload)


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ConformWeb Dashboard</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f4f5f7;
        --surface: #ffffff;
        --surface-2: #eef1f4;
        --text: #171a1f;
        --muted: #66707c;
        --line: #d6dbe1;
        --ok: #177245;
        --bad: #b72f2f;
        --warn: #9a6500;
        --accent: #1f5f8b;
        --shadow: 0 10px 28px rgba(24, 31, 38, 0.08);
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family:
          Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
          "Segoe UI", sans-serif;
      }

      button,
      select,
      input {
        font: inherit;
      }

      button,
      select {
        border: 1px solid var(--line);
        border-radius: 6px;
        background: var(--surface);
        color: var(--text);
      }

      button {
        min-height: 34px;
        padding: 0 10px;
        cursor: pointer;
      }

      button.active {
        border-color: var(--accent);
        background: var(--accent);
        color: #fff;
      }

      header {
        position: sticky;
        top: 0;
        z-index: 3;
        border-bottom: 1px solid var(--line);
        background: rgba(244, 245, 247, 0.94);
        backdrop-filter: blur(8px);
      }

      .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 18px;
        padding: 14px 18px;
      }

      h1,
      h2,
      h3,
      p {
        margin-top: 0;
      }

      h1 {
        margin-bottom: 2px;
        font-size: 1.15rem;
      }

      h2 {
        margin-bottom: 10px;
        font-size: 1rem;
      }

      h3 {
        margin-bottom: 8px;
        font-size: 0.95rem;
      }

      .meta {
        color: var(--muted);
        font-size: 0.82rem;
      }

      .stats {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }

      .pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        min-height: 24px;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 0 9px;
        background: var(--surface);
        color: var(--muted);
        font-size: 0.8rem;
        white-space: nowrap;
      }

      .pill.ok {
        border-color: rgba(23, 114, 69, 0.25);
        color: var(--ok);
      }

      .pill.bad {
        border-color: rgba(183, 47, 47, 0.25);
        color: var(--bad);
      }

      main {
        display: grid;
        grid-template-columns: 300px minmax(0, 1fr);
        min-height: calc(100vh - 64px);
      }

      aside {
        border-right: 1px solid var(--line);
        background: var(--surface);
        padding: 16px;
      }

      .content {
        min-width: 0;
        padding: 16px;
      }

      .section {
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--surface);
        box-shadow: var(--shadow);
      }

      .section + .section {
        margin-top: 16px;
      }

      .section-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        min-height: 48px;
        border-bottom: 1px solid var(--line);
        padding: 12px;
      }

      .section-body {
        padding: 12px;
      }

      .subject {
        display: grid;
        gap: 8px;
        padding: 10px 0;
        border-bottom: 1px solid var(--line);
      }

      .subject:last-child {
        border-bottom: 0;
      }

      .subject-row {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr);
        gap: 8px;
        align-items: center;
      }

      .subject label {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 0.9rem;
      }

      .subject select {
        width: 100%;
        min-height: 32px;
        padding: 0 8px;
        font-size: 0.82rem;
      }

      .matrix-wrap {
        overflow: auto;
      }

      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.86rem;
      }

      th,
      td {
        border-bottom: 1px solid var(--line);
        padding: 8px;
        text-align: left;
        vertical-align: top;
      }

      th {
        position: sticky;
        top: 0;
        background: var(--surface-2);
        color: var(--muted);
        font-weight: 700;
      }

      tr.scenario-row {
        cursor: pointer;
      }

      tr.scenario-row.active {
        background: #e8f1f6;
      }

      .cell-pass,
      .cell-fail,
      .cell-missing {
        display: grid;
        gap: 3px;
        min-width: 120px;
      }

      .cell-pass strong {
        color: var(--ok);
      }

      .cell-fail strong {
        color: var(--bad);
      }

      .cell-missing strong {
        color: var(--muted);
      }

      .compare-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
        gap: 12px;
      }

      .run-column {
        min-width: 0;
        border: 1px solid var(--line);
        border-radius: 8px;
        overflow: hidden;
      }

      .run-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        border-bottom: 1px solid var(--line);
        background: var(--surface-2);
        padding: 10px;
      }

      .steps {
        display: grid;
        gap: 12px;
        padding: 10px;
      }

      .step {
        border: 1px solid var(--line);
        border-radius: 8px;
        overflow: hidden;
      }

      .step-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        border-bottom: 1px solid var(--line);
        padding: 8px 10px;
      }

      .step-body {
        display: grid;
        gap: 10px;
        padding: 10px;
      }

      .shots {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }

      figure {
        margin: 0;
        min-width: 0;
      }

      figcaption {
        margin-bottom: 4px;
        color: var(--muted);
        font-size: 0.76rem;
        font-weight: 700;
        text-transform: uppercase;
      }

      img {
        display: block;
        width: 100%;
        max-height: 320px;
        object-fit: contain;
        border: 1px solid var(--line);
        border-radius: 6px;
        background: #fff;
      }

      .assertions {
        display: grid;
        gap: 6px;
      }

      .assertion {
        border-left: 3px solid var(--ok);
        background: #f7faf8;
        padding: 7px 8px;
        font-size: 0.8rem;
      }

      .assertion.failed {
        border-left-color: var(--bad);
        background: #fff7f7;
      }

      details {
        border: 1px solid var(--line);
        border-radius: 6px;
        background: #fafbfc;
      }

      summary {
        cursor: pointer;
        padding: 8px;
        color: var(--muted);
        font-size: 0.82rem;
        font-weight: 700;
      }

      pre {
        max-height: 260px;
        margin: 0;
        overflow: auto;
        border-top: 1px solid var(--line);
        padding: 8px;
        font-size: 0.76rem;
        line-height: 1.4;
        white-space: pre-wrap;
      }

      .empty {
        color: var(--muted);
        padding: 24px;
        text-align: center;
      }

      @media (max-width: 920px) {
        main {
          grid-template-columns: 1fr;
        }

        aside {
          border-right: 0;
          border-bottom: 1px solid var(--line);
        }
      }
    </style>
  </head>
  <body>
    <header>
      <div class="topbar">
        <div>
          <h1 id="title">ConformWeb Dashboard</h1>
          <div class="meta" id="subtitle"></div>
        </div>
        <div class="stats" id="stats"></div>
      </div>
    </header>
    <main>
      <aside>
        <div class="section">
          <div class="section-head">
            <h2>Runs</h2>
            <button id="toggleAll" type="button">All</button>
          </div>
          <div class="section-body" id="subjects"></div>
        </div>
      </aside>
      <div class="content">
        <section class="section">
          <div class="section-head">
            <h2>Scenario Matrix</h2>
            <div class="meta" id="matrixMeta"></div>
          </div>
          <div class="section-body matrix-wrap" id="matrix"></div>
        </section>
        <section class="section">
          <div class="section-head">
            <h2 id="selectedScenarioTitle">Scenario Detail</h2>
            <div class="meta" id="selectedScenarioMeta"></div>
          </div>
          <div class="section-body" id="detail"></div>
        </section>
      </div>
    </main>

    <script id="dashboard-data" type="application/json">__DASHBOARD_DATA__</script>
    <script>
      const data = JSON.parse(document.getElementById("dashboard-data").textContent);
      const bySubjectRun = new Map();
      const byScenarioMeta = new Map();
      const state = {
        visibleSubjects: new Set(),
        selectedRuns: new Map(),
        selectedScenario: null,
      };

      for (const run of data.runs) {
        bySubjectRun.set(run.subject + "::" + run.run_id, run);
      }

      for (const scenario of data.scenarios) {
        byScenarioMeta.set(scenario.id, scenario);
      }

      for (const subject of data.subjects) {
        state.selectedRuns.set(subject.name, subject.default_run_id);
        if (subject.default_visible) {
          state.visibleSubjects.add(subject.name);
        }
      }

      function runFor(subject) {
        return bySubjectRun.get(subject + "::" + state.selectedRuns.get(subject));
      }

      function activeRuns() {
        return [...state.visibleSubjects].map(runFor).filter(Boolean);
      }

      function scenarioFor(run, scenarioId) {
        return run.scenarios.find((scenario) => scenario.id === scenarioId);
      }

      function scenarioIds() {
        const ids = new Set();
        for (const run of activeRuns()) {
          for (const scenario of run.scenarios) {
            ids.add(scenario.id);
          }
        }
        return [...ids].sort();
      }

      function escapeHtml(value) {
        return String(value ?? "")
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;")
          .replaceAll("'", "&#039;");
      }

      function statusPill(passed) {
        return `<span class="pill ${passed ? "ok" : "bad"}">${passed ? "PASS" : "FAIL"}</span>`;
      }

      function renderShell() {
        document.getElementById("title").textContent = data.title;
        document.getElementById("subtitle").textContent =
          `${data.target_path} | generated ${data.generated_at}`;
        document.getElementById("stats").innerHTML = [
          `<span class="pill">${data.runs.length} runs</span>`,
          `<span class="pill">${data.subjects.length} subjects</span>`,
          `<span class="pill">${data.scenarios.length} scenarios</span>`,
        ].join("");
      }

      function renderSubjects() {
        const html = data.subjects.map((subject) => {
          const checked = state.visibleSubjects.has(subject.name) ? "checked" : "";
          const options = subject.runs.map((run) => {
            const selected = run.run_id === state.selectedRuns.get(subject.name) ? "selected" : "";
            const label = `${run.run_id} ${run.passed ? "PASS" : "FAIL"}`;
            return `<option value="${escapeHtml(run.run_id)}" ${selected}>${escapeHtml(label)}</option>`;
          }).join("");
          return `
            <div class="subject">
              <div class="subject-row">
                <input type="checkbox" data-subject-toggle="${escapeHtml(subject.name)}" ${checked} />
                <label title="${escapeHtml(subject.name)}">${escapeHtml(subject.name)}</label>
              </div>
              <select data-subject-run="${escapeHtml(subject.name)}">${options}</select>
            </div>
          `;
        }).join("");
        document.getElementById("subjects").innerHTML = html || `<div class="empty">No runs found.</div>`;

        document.querySelectorAll("[data-subject-toggle]").forEach((input) => {
          input.addEventListener("change", () => {
            const subject = input.getAttribute("data-subject-toggle");
            if (input.checked) {
              state.visibleSubjects.add(subject);
            } else {
              state.visibleSubjects.delete(subject);
            }
            render();
          });
        });

        document.querySelectorAll("[data-subject-run]").forEach((select) => {
          select.addEventListener("change", () => {
            const subject = select.getAttribute("data-subject-run");
            state.selectedRuns.set(subject, select.value);
            render();
          });
        });

        document.getElementById("toggleAll").onclick = () => {
          const allVisible = state.visibleSubjects.size === data.subjects.length;
          state.visibleSubjects = new Set(allVisible ? [] : data.subjects.map((subject) => subject.name));
          render();
        };
      }

      function renderMatrix() {
        const runs = activeRuns();
        const ids = scenarioIds();
        if (!state.selectedScenario || !ids.includes(state.selectedScenario)) {
          state.selectedScenario = ids[0] || null;
        }
        document.getElementById("matrixMeta").textContent = `${runs.length} visible runs`;
        if (!runs.length) {
          document.getElementById("matrix").innerHTML = `<div class="empty">Select at least one run.</div>`;
          return;
        }
        const head = `
          <tr>
            <th>Scenario</th>
            ${runs.map((run) => `<th>${escapeHtml(run.subject)}<br><span class="meta">${escapeHtml(run.run_id)}</span></th>`).join("")}
          </tr>
        `;
        const rows = ids.map((id) => {
          const active = id === state.selectedScenario ? "active" : "";
          const meta = byScenarioMeta.get(id) || {};
          const cells = runs.map((run) => {
            const scenario = scenarioFor(run, id);
            if (!scenario) {
              return `<td><div class="cell-missing"><strong>missing</strong></div></td>`;
            }
            const cls = scenario.passed ? "cell-pass" : "cell-fail";
            return `
              <td>
                <div class="${cls}">
                  <strong>${scenario.passed ? "PASS" : "FAIL"}</strong>
                  <span>${scenario.steps.length} steps</span>
                  <span>${scenario.failed_assertion_count} failed assertions</span>
                </div>
              </td>
            `;
          }).join("");
          return `
            <tr class="scenario-row ${active}" data-scenario="${escapeHtml(id)}">
              <td>
                <strong>${escapeHtml(id)}</strong>
                <div class="meta">${escapeHtml(meta.difficulty || "unclassified")} | ${escapeHtml(meta.tier || "unclassified")}</div>
              </td>
              ${cells}
            </tr>
          `;
        }).join("");
        document.getElementById("matrix").innerHTML = `<table><thead>${head}</thead><tbody>${rows}</tbody></table>`;
        document.querySelectorAll("[data-scenario]").forEach((row) => {
          row.addEventListener("click", () => {
            state.selectedScenario = row.getAttribute("data-scenario");
            render();
          });
        });
      }

      function renderDetail() {
        const scenarioId = state.selectedScenario;
        const runs = activeRuns();
        const meta = byScenarioMeta.get(scenarioId) || {};
        document.getElementById("selectedScenarioTitle").textContent = scenarioId || "Scenario Detail";
        document.getElementById("selectedScenarioMeta").textContent = scenarioId
          ? `${meta.difficulty || "unclassified"} | ${meta.tier || "unclassified"} | before/after screenshots and state diffs`
          : "";
        if (!scenarioId || !runs.length) {
          document.getElementById("detail").innerHTML = `<div class="empty">No scenario selected.</div>`;
          return;
        }
        const columns = runs.map((run) => renderRunScenario(run, scenarioFor(run, scenarioId))).join("");
        document.getElementById("detail").innerHTML = `<div class="compare-grid">${columns}</div>`;
      }

      function renderRunScenario(run, scenario) {
        if (!scenario) {
          return `
            <div class="run-column">
              <div class="run-title"><strong>${escapeHtml(run.subject)}</strong><span class="pill">missing</span></div>
              <div class="empty">This run does not include the selected scenario.</div>
            </div>
          `;
        }
        const steps = scenario.steps.map(renderStep).join("");
        return `
          <div class="run-column">
            <div class="run-title">
              <div>
                <strong>${escapeHtml(run.subject)}</strong>
                <div class="meta">${escapeHtml(run.run_id)}</div>
              </div>
              ${statusPill(scenario.passed)}
            </div>
            <div class="steps">${steps}</div>
          </div>
        `;
      }

      function renderStep(step) {
        const assertions = step.assertions.length
          ? step.assertions.map((assertion) => `
              <div class="assertion ${assertion.passed ? "" : "failed"}">
                <strong>${escapeHtml(assertion.type)} ${assertion.passed ? "PASS" : "FAIL"}</strong>
                <div>${escapeHtml(assertion.message)}</div>
                ${assertion.passed ? "" : `<pre>${escapeHtml(JSON.stringify({ actual: assertion.actual, expected: assertion.expected }, null, 2))}</pre>`}
              </div>
            `).join("")
          : `<div class="meta">No assertions on this step.</div>`;
        return `
          <div class="step">
            <div class="step-head">
              <div>
                <strong>#${step.step_index} ${escapeHtml(step.action)}</strong>
                <div class="meta">${escapeHtml(step.component || "no component")}</div>
              </div>
              ${statusPill(step.passed)}
            </div>
            <div class="step-body">
              <div class="shots">
                ${step.screenshots.before ? `
                  <figure>
                    <figcaption>Before</figcaption>
                    <img src="${escapeHtml(step.screenshots.before)}" alt="before screenshot" loading="lazy" />
                  </figure>
                ` : ""}
                ${step.screenshots.after ? `
                  <figure>
                    <figcaption>After</figcaption>
                    <img src="${escapeHtml(step.screenshots.after)}" alt="after screenshot" loading="lazy" />
                  </figure>
                ` : ""}
              </div>
              <div class="assertions">${assertions}</div>
              <details>
                <summary>State diff (${step.state_diff.length})</summary>
                <pre>${escapeHtml(JSON.stringify(step.state_diff, null, 2))}</pre>
              </details>
              <details>
                <summary>After state</summary>
                <pre>${escapeHtml(JSON.stringify(step.after_state, null, 2))}</pre>
              </details>
            </div>
          </div>
        `;
      }

      function render() {
        renderShell();
        renderSubjects();
        renderMatrix();
        renderDetail();
      }

      render();
    </script>
  </body>
</html>
"""
