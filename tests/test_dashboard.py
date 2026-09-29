import json
from pathlib import Path

from detoxbench.dashboard import DashboardConfig, build_dashboard_data, normalize_step


def test_normalize_step_accepts_omitted_screenshots(tmp_path: Path) -> None:
    step = {
        "scenario_id": "passing_step",
        "step_index": 1,
        "action": "snapshot",
        "component": None,
        "passed": True,
        "before_state": {"ready": True},
        "after_state": {"ready": True},
        "screenshots": {"before": None, "after": None},
        "assertions": [],
    }

    normalized = normalize_step(step, tmp_path, tmp_path)

    assert normalized["screenshots"] == {"before": None, "after": None}


def test_dashboard_data_groups_subjects_and_marks_defaults(tmp_path: Path) -> None:
    (tmp_path / "scenarios.dsl.yaml").write_text(
        """
dsl_version: "1.0.0"
scenarios:
  - id: scenario_one
    tier: behavior
    difficulty: d3_integrated
    description: scenario metadata description
    steps:
      - do: save_button.click
      - do: save_button.click
""".lstrip(),
        encoding="utf-8",
    )
    summary = {
        "run_id": "20260507-000000-abc123",
        "subject": "candidate_a",
        "passed": False,
        "output_dir": str(tmp_path / "runs" / "candidate_a" / "20260507-000000-abc123"),
        "score": {
            "formal": {"earned": 0.0, "possible": 1.0, "ratio": 0.0},
            "by_tier": {
                "behavior": {"earned": 0.0, "possible": 1.0, "passed": 0, "failed": 1, "total": 1, "ratio": 0.0}
            },
            "probe": {"passed": 0, "total": 0},
        },
        "scenarios": [
            {
                "id": "scenario_one",
                "tier": "behavior",
                "passed": False,
                "error": None,
                "steps": [
                    {
                        "scenario_id": "scenario_one",
                        "step_index": 1,
                        "action": "click",
                        "component": "button.save",
                        "passed": False,
                        "before_state": {"count": 1},
                        "after_state": {"count": 2},
                        "screenshots": {
                            "before": str(tmp_path / "runs" / "candidate_a" / "20260507-000000-abc123" / "screenshots" / "before.png"),
                            "after": str(tmp_path / "runs" / "candidate_a" / "20260507-000000-abc123" / "screenshots" / "after.png"),
                        },
                        "assertions": [
                            {
                                "type": "state_unchanged",
                                "passed": False,
                                "message": "count should not change",
                                "actual": 2,
                                "expected": 1,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    summary_path = tmp_path / "runs" / "candidate_a" / "20260507-000000-abc123" / "summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    older_summary = dict(summary, run_id="20260506-235959-old000", passed=True)
    older_path = tmp_path / "runs" / "candidate_a" / "20260506-235959-old000" / "summary.json"
    older_path.parent.mkdir(parents=True)
    older_path.write_text(json.dumps(older_summary), encoding="utf-8")

    data = build_dashboard_data(
        DashboardConfig(
            target_dir=tmp_path,
            runs_dir=tmp_path / "runs",
            output=tmp_path / "dashboard" / "index.html",
            title="Test Dashboard",
        )
    )

    assert data["subjects"][0]["name"] == "candidate_a"
    assert len(data["runs"]) == 1
    assert data["runs"][0]["run_id"] == "20260507-000000-abc123"
    assert data["target_label"] == tmp_path.name
    assert data["subjects"][0]["default_visible"] is True
    assert data["runs"][0]["failed_assertion_count"] == 1
    assert data["runs"][0]["failed_scenario_count"] == 1
    assert data["runs"][0]["score"]["formal"]["ratio"] == 0.0
    assert data["runs"][0]["score"]["stepwise"]["ratio"] == 0.0
    assert data["runs"][0]["score"]["contract"]["failures"] == 0
    assert data["runs"][0]["score"]["failure_breakdown"] == {"assertion_state_unchanged": 1}
    assert data["runs"][0]["first_failure"] == {
        "scenario_id": "scenario_one",
        "failure_category": "assertion_state_unchanged",
        "kind": "assertion",
        "step_index": 1,
        "action": "click",
        "component": "button.save",
        "assertion_type": "state_unchanged",
        "message": "count should not change",
        "actual": 2,
        "expected": 1,
    }
    assert data["runs"][0]["tier_stats"] == {
        "behavior": {"passed": 0, "failed": 1, "total": 1}
    }
    assert data["runs"][0]["difficulty_stats"] == {
        "d3_integrated": {"passed": 0, "failed": 1, "total": 1}
    }
    assert data["tier_summary"] == {"behavior": 1}
    assert data["difficulty_summary"] == {"d3_integrated": 1}
    scenario = data["runs"][0]["scenarios"][0]
    assert scenario["description"] == "scenario metadata description"
    assert scenario["difficulty"] == "d3_integrated"
    assert scenario["expected_step_count"] == 2
    assert scenario["completed_step_count"] == 1
    assert scenario["passed_step_count"] == 0
    assert scenario["passed_until_step"] == 0
    assert scenario["first_failed_step"] == 1
    assert scenario["progress_label"] == "0/2"
    assert scenario["first_failure"]["kind"] == "assertion"
    assert scenario["failure_category"] == "assertion_state_unchanged"
    assert data["runs"][0]["scenarios"][0]["steps"][0]["state_diff"] == [
        {"path": "count", "before": 1, "after": 2}
    ]


def test_dashboard_data_infers_error_step_progress(tmp_path: Path) -> None:
    (tmp_path / "scenarios.dsl.yaml").write_text(
        """
dsl_version: "1.0.0"
scenarios:
  - id: scenario_error
    tier: smoke
    steps:
      - do: snapshot
      - do: save_button.click
      - do: save_button.click
""".lstrip(),
        encoding="utf-8",
    )
    summary = {
        "run_id": "20260507-000000-abc123",
        "subject": "candidate_b",
        "passed": False,
        "output_dir": str(tmp_path / "runs" / "candidate_b" / "20260507-000000-abc123"),
        "scenarios": [
            {
                "id": "scenario_error",
                "tier": None,
                "passed": False,
                "error": "ReferenceError: getState is not defined",
                "steps": [],
            }
        ],
    }
    summary_path = tmp_path / "runs" / "candidate_b" / "20260507-000000-abc123" / "summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    data = build_dashboard_data(
        DashboardConfig(
            target_dir=tmp_path,
            runs_dir=tmp_path / "runs",
            output=tmp_path / "dashboard" / "index.html",
            title="Test Dashboard",
        )
    )

    scenario = data["runs"][0]["scenarios"][0]
    assert scenario["tier"] == "smoke"
    assert scenario["expected_step_count"] == 3
    assert scenario["completed_step_count"] == 0
    assert scenario["passed_until_step"] == 0
    assert scenario["first_failed_step"] == 1
    assert scenario["progress_label"] == "0/3"
    assert scenario["first_failure"] == {
        "kind": "scenario_error",
        "step_index": 1,
        "action": None,
        "component": None,
        "message": "ReferenceError: getState is not defined",
    }
    assert scenario["failure_category"] == "scenario_error"


def test_dashboard_data_discovers_nested_cohort_runs_and_rebases_screenshots(tmp_path: Path) -> None:
    (tmp_path / "scenarios.public.dsl.yaml").write_text(
        """
dsl_version: "1.0.0"
visibility: public
scenarios:
  - id: scenario_one
    tier: smoke
    steps:
      - do: save_button.click
""".lstrip(),
        encoding="utf-8",
    )
    run_dir = tmp_path / "cohorts" / "M" / "batch" / "runs" / "model" / "r01" / "20260512-run"
    screenshot_dir = run_dir / "screenshots" / "scenario_one"
    screenshot_dir.mkdir(parents=True)
    (screenshot_dir / "001-before.png").write_bytes(b"before")
    (screenshot_dir / "001-after.png").write_bytes(b"after")
    summary = {
        "run_id": "20260512-run",
        "subject": "nested_subject",
        "passed": True,
        "output_dir": "/old/root/runs/nested_subject/20260512-run",
        "scenarios": [
            {
                "id": "scenario_one",
                "passed": True,
                "steps": [
                    {
                        "scenario_id": "scenario_one",
                        "step_index": 1,
                        "action": "click",
                        "component": "button.save",
                        "passed": True,
                        "before_state": {},
                        "after_state": {},
                        "screenshots": {
                            "before": "/old/root/screenshots/scenario_one/001-before.png",
                            "after": "/old/root/screenshots/scenario_one/001-after.png",
                        },
                        "assertions": [],
                    }
                ],
            }
        ],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    data = build_dashboard_data(
        DashboardConfig(
            target_dir=tmp_path,
            runs_dir=tmp_path / "cohorts",
            output=tmp_path / "reports" / "dashboard" / "index.html",
            title="Nested Dashboard",
        )
    )

    assert data["runs"][0]["subject"] == "nested_subject"
    screenshots = data["runs"][0]["scenarios"][0]["steps"][0]["screenshots"]
    assert screenshots["before"].endswith("cohorts/M/batch/runs/model/r01/20260512-run/screenshots/scenario_one/001-before.png")
    assert screenshots["after"].endswith("cohorts/M/batch/runs/model/r01/20260512-run/screenshots/scenario_one/001-after.png")
