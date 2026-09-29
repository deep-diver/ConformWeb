import json
from pathlib import Path

import pytest

from detoxbench.cohorts import cohort_fingerprint, load_cohort_manifest
from detoxbench.cli import build_parser, main
from detoxbench.core.models import AssertionResult, RunResult, ScenarioResult, StepResult
from detoxbench.dsl.compiler import DslCompileError
from detoxbench.dsl.scenario_sets import discover_scenario_paths, load_scenario_bundles
from detoxbench.known_bad import assess_known_bad_result, load_known_bad_fixtures
from detoxbench.target_inventory import discover_target_inventory, summarize_target_inventory
from tools.build_release_manifest import is_lfs_pointer


def test_split_scenario_bundles_are_discovered_and_filtered(tmp_path: Path) -> None:
    public = tmp_path / "scenarios.public.dsl.yaml"
    private = tmp_path / "scenarios.private.dsl.yaml"
    public.write_text(
        """
dsl_version: "2.0.0"
visibility: public
tier_weights: {smoke: 1}
scenarios:
  - id: public_smoke
    tier: smoke
    steps:
      - do: reset_button.click
""".lstrip(),
        encoding="utf-8",
    )
    private.write_text(
        """
dsl_version: "2.0.0"
visibility: private
tier_weights: {journey: 5}
scenarios:
  - id: private_journey
    tier: journey
    steps:
      - do: reset_button.click
""".lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "scenarios.dsl.yaml").write_text("dsl_version: '2.0.0'\nscenarios: []\n", encoding="utf-8")

    assert discover_scenario_paths(tmp_path, scenario_set="all") == [public, private]
    assert discover_scenario_paths(tmp_path, scenario_set="public") == [public]
    assert discover_scenario_paths(tmp_path, scenario_set="private") == [private]

    merged = load_scenario_bundles([public, private], scenario_set="all")
    assert [scenario["id"] for scenario in merged["scenarios"]] == [
        "public_smoke",
        "private_journey",
    ]
    assert [scenario["visibility"] for scenario in merged["scenarios"]] == [
        "public",
        "private",
    ]
    assert merged["tier_weights"] == {"smoke": 1.0, "journey": 5.0}

    private_only = load_scenario_bundles([public, private], scenario_set="private")
    assert [scenario["id"] for scenario in private_only["scenarios"]] == ["private_journey"]


def test_known_bad_manifest_and_assessment(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures" / "known_bad" / "wrong_delta"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
    manifest = tmp_path / "fixtures" / "known_bad" / "manifest.yaml"
    manifest.write_text(
        """
fixtures:
  - id: wrong_delta
    expected:
      passed: false
      min_failed_scenarios: 1
      failure_categories: [assertion_state_delta]
""".lstrip(),
        encoding="utf-8",
    )

    [fixture] = load_known_bad_fixtures(tmp_path)
    assert fixture.id == "wrong_delta"
    assert fixture.path == fixture_dir.resolve()
    assert fixture.allowed_failure_categories == ("assertion_state_delta",)

    run = RunResult(
        run_id="run",
        subject="known_bad_wrong_delta",
        output_dir=str(tmp_path),
        scenarios=[
            ScenarioResult(
                id="delta",
                passed=False,
                steps=[
                    StepResult(
                        scenario_id="delta",
                        step_index=1,
                        action="click",
                        component="increment_button",
                        before_state={"value": 0},
                        after_state={"value": 0},
                        before_screenshot="before.png",
                        after_screenshot="after.png",
                        assertions=[
                            AssertionResult(
                                type="state_delta",
                                passed=False,
                                message="value should change",
                                actual=0,
                                expected=2,
                            )
                        ],
                    )
                ],
            )
        ],
    )
    assessment = assess_known_bad_result(fixture, run)
    assert assessment.passed
    assert assessment.errors == ()


def test_invalid_scenario_visibility_is_rejected(tmp_path: Path) -> None:
    scenario_file = tmp_path / "scenarios.public.dsl.yaml"
    scenario_file.write_text(
        """
dsl_version: "2.0.0"
visibility: public
scenarios:
  - id: broken_visibility
    visibility: shared
    steps:
      - do: reset_button.click
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(DslCompileError, match="visibility must be public or private"):
        load_scenario_bundles([scenario_file], scenario_set="public")


def test_cohort_manifest_fingerprint_includes_contract_hash(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    contract = target / "contract.dsl.yaml"
    contract.write_text("dsl_version: '2.0.0'\napp: {id: demo}\n", encoding="utf-8")
    manifest = tmp_path / "cohort.yaml"
    manifest.write_text(
        """
version: "1"
name: demo-cohort
members:
  - id: gpt54_default
    model: gpt-5.4
targets:
  - target_dir: target
    contract: contract.dsl.yaml
""".lstrip(),
        encoding="utf-8",
    )

    cohort = load_cohort_manifest(manifest)
    fingerprint = cohort_fingerprint(cohort)

    assert fingerprint["name"] == "demo-cohort"
    assert fingerprint["member_count"] == 1
    assert fingerprint["target_count"] == 1
    assert fingerprint["targets"][0]["contract_sha256"]
    json.dumps(fingerprint)


def test_target_inventory_reports_runnable_scenario_sets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "targets" / "web"
    ready = root / "example_family" / "tier_a"
    public_only = root / "example_family" / "tier_b"
    unavailable = root / "example_family" / "tier_c"
    for target in (ready, public_only, unavailable):
        target.mkdir(parents=True)
    for target in (ready, public_only):
        (target / "contract.dsl.yaml").write_text("dsl_version: '1.0.0'\n", encoding="utf-8")
    (ready / "reference_app").mkdir()
    (ready / "scenarios.public.dsl.yaml").write_text(
        "dsl_version: '1.0.0'\nscenarios:\n  - id: public_one\n    steps: []\n",
        encoding="utf-8",
    )
    (ready / "scenarios.private.dsl.yaml").write_text(
        "dsl_version: '1.0.0'\nscenarios:\n  - id: private_one\n    steps: []\n  - id: private_two\n    steps: []\n",
        encoding="utf-8",
    )
    (public_only / "scenarios.public.dsl.yaml").write_text(
        "dsl_version: '1.0.0'\nscenarios:\n  - id: public_two\n    steps: []\n",
        encoding="utf-8",
    )

    inventory = discover_target_inventory(root)

    assert [item.status for item in inventory] == ["ready", "public-only", "unavailable"]
    assert inventory[0].to_dict()["available_scenario_sets"] == ["all", "public", "private"]
    assert inventory[1].to_dict()["available_scenario_sets"] == ["public"]
    assert summarize_target_inventory(inventory) == {
        "target_slots": 3,
        "status_counts": {"ready": 1, "public-only": 1, "unavailable": 1},
        "public_scenarios": 2,
        "private_scenarios": 2,
        "legacy_scenarios": 0,
        "scenario_total": 4,
    }

    assert main(["list-targets", "--targets-root", str(root), "--json"]) == 0
    released = json.loads(capsys.readouterr().out)
    assert released["summary"]["target_slots"] == 1
    assert [item["target"] for item in released["targets"]] == [
        "example_family/tier_a"
    ]

    assert main(
        [
            "list-targets",
            "--targets-root",
            str(root),
            "--include-partial",
            "--json",
        ]
    ) == 0
    discovered = json.loads(capsys.readouterr().out)
    assert discovered["summary"]["target_slots"] == 3


def test_evaluate_cli_accepts_failure_only_screenshots() -> None:
    args = build_parser().parse_args(
        [
            "evaluate-dsl",
            "--target",
            "targets/web/example/tier_a",
            "--static-dir",
            "candidate",
            "--screenshot-policy",
            "failures",
        ]
    )

    assert args.screenshot_policy == "failures"


def test_release_manifest_recognizes_lfs_pointer() -> None:
    assert is_lfs_pointer(
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:0123456789\n"
        b"size 42\n"
    )
    assert not is_lfs_pointer(b"scenario_id,passed\npublic_01,true\n")
