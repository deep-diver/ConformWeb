from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Component:
    id: str
    selector: str
    type: str = "generic"
    actions: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Contract:
    id: str
    name: str
    version: str
    target: str
    runtime: dict[str, Any]
    components: dict[str, Component]
    constraints: list[dict[str, Any]]
    raw: dict[str, Any]

    @property
    def state_expression(self) -> str:
        web = self.runtime.get("web", {})
        expression = web.get("state_expression")
        if not expression:
            raise ValueError("contract.runtime.web.state_expression is required")
        return expression

    @property
    def start_path(self) -> str:
        return str(self.runtime.get("web", {}).get("start_url", "/"))

    def resolve_static_dir(self, base_dir: Path) -> Path | None:
        static_dir = self.runtime.get("web", {}).get("static_dir")
        if not static_dir:
            return None
        path = Path(static_dir)
        if not path.is_absolute():
            path = base_dir / path
        return path.resolve()


@dataclass(frozen=True)
class ScenarioSet:
    version: str
    scenarios: list[dict[str, Any]]
    raw: dict[str, Any]
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssertionResult:
    type: str
    passed: bool
    message: str
    actual: Any = None
    expected: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "passed": self.passed,
            "message": self.message,
            "actual": self.actual,
            "expected": self.expected,
        }


@dataclass
class StepResult:
    scenario_id: str
    step_index: int
    action: str
    component: str | None
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    before_screenshot: str | None
    after_screenshot: str | None
    assertions: list[AssertionResult]
    actor: str | None = None

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.assertions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "step_index": self.step_index,
            "action": self.action,
            "component": self.component,
            "actor": self.actor,
            "passed": self.passed,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "screenshots": {
                "before": self.before_screenshot,
                "after": self.after_screenshot,
            },
            "assertions": [result.to_dict() for result in self.assertions],
        }


@dataclass
class ScenarioResult:
    id: str
    passed: bool
    steps: list[StepResult]
    error: str | None = None
    tier: str | None = None
    kind: str = "scoring"
    weight: float = 1.0
    visibility: str = "private"
    difficulty: str | None = None
    contract_refs: list[str] = field(default_factory=list)
    description: str | None = None
    expected_step_count: int | None = None
    error_step_index: int | None = None
    source: str | None = None

    @property
    def total_step_count(self) -> int:
        return self.expected_step_count or max(
            len(self.steps),
            self.error_step_index or 0,
        )

    @property
    def passed_step_count(self) -> int:
        return sum(1 for step in self.steps if step.passed)

    @property
    def first_failure(self) -> dict[str, Any] | None:
        for step in self.steps:
            for assertion in step.assertions:
                if not assertion.passed:
                    return {
                        "kind": "assertion",
                        "step_index": step.step_index,
                        "action": step.action,
                        "component": step.component,
                        "assertion_type": assertion.type,
                        "message": assertion.message,
                        "actual": assertion.actual,
                        "expected": assertion.expected,
                    }
            if not step.passed:
                return {
                    "kind": "step",
                    "step_index": step.step_index,
                    "action": step.action,
                    "component": step.component,
                    "message": "Step failed without a failed assertion.",
                }
        if self.error:
            step_index = self.error_step_index or len(self.steps) + 1
            return {
                "kind": "scenario_error",
                "step_index": step_index,
                "action": None,
                "component": None,
                "message": self.error,
            }
        return None

    @property
    def first_failed_step(self) -> int | None:
        failure = self.first_failure
        if not failure:
            return None
        return int(failure["step_index"])

    @property
    def failure_category(self) -> str | None:
        failure = self.first_failure
        if not failure:
            return None
        return classify_failure(failure)

    @property
    def passed_until_step(self) -> int:
        first_failed_step = self.first_failed_step
        if first_failed_step is not None:
            return max(0, first_failed_step - 1)
        if self.passed:
            return self.total_step_count
        return self.passed_step_count

    def to_dict(self) -> dict[str, Any]:
        scenario_score = self.weight if self.kind == "scoring" and self.passed else 0.0
        return {
            "id": self.id,
            "tier": self.tier,
            "kind": self.kind,
            "weight": self.weight,
            "visibility": self.visibility,
            "difficulty": self.difficulty,
            "contract_refs": self.contract_refs,
            "description": self.description,
            "passed": self.passed,
            "error": self.error,
            "source": self.source,
            "score": {
                "earned": scenario_score,
                "possible": self.weight if self.kind == "scoring" else 0.0,
                "ratio": 1.0 if self.kind == "scoring" and self.passed else 0.0,
                "included": self.kind == "scoring",
            },
            "expected_step_count": self.total_step_count,
            "completed_step_count": len(self.steps),
            "passed_step_count": self.passed_step_count,
            "passed_until_step": self.passed_until_step,
            "first_failed_step": self.first_failed_step,
            "first_failure": self.first_failure,
            "failure_category": self.failure_category,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class RunResult:
    run_id: str
    output_dir: str
    scenarios: list[ScenarioResult]
    subject: str | None = None

    @property
    def passed(self) -> bool:
        scoring = [scenario for scenario in self.scenarios if scenario.kind == "scoring"]
        return bool(scoring) and all(scenario.passed for scenario in scoring)

    @property
    def score(self) -> dict[str, Any]:
        return compute_run_score(self.scenarios)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "subject": self.subject,
            "passed": self.passed,
            "output_dir": self.output_dir,
            "score": self.score,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }


def compute_run_score(scenarios: list[ScenarioResult]) -> dict[str, Any]:
    formal_possible = 0.0
    formal_earned = 0.0
    stepwise_possible = 0.0
    stepwise_earned = 0.0
    by_tier: dict[str, dict[str, float | int]] = {}
    by_capability: dict[str, dict[str, float | int]] = {}
    by_difficulty: dict[str, dict[str, float | int]] = {}
    failure_breakdown: dict[str, int] = {}
    contract_failure_breakdown: dict[str, int] = {}
    contract_failure_count = 0
    scoring_count = 0
    probe_total = 0
    probe_passed = 0

    for scenario in scenarios:
        tier = scenario.tier or "unclassified"
        difficulty = scenario.difficulty or "unclassified"
        if scenario.kind == "probe":
            probe_total += 1
            if scenario.passed:
                probe_passed += 1
            continue

        scoring_count += 1
        weight = float(scenario.weight)
        step_ratio = _scenario_step_ratio(scenario)
        step_earned = weight * step_ratio
        formal_possible += weight
        stepwise_possible += weight
        stepwise_earned += step_earned
        if scenario.passed:
            formal_earned += weight
        failure_category = scenario.failure_category
        if failure_category:
            failure_breakdown[failure_category] = failure_breakdown.get(failure_category, 0) + 1
            if _is_contract_failure(failure_category):
                contract_failure_count += 1
                contract_failure_breakdown[failure_category] = (
                    contract_failure_breakdown.get(failure_category, 0) + 1
                )
        tier_row = by_tier.setdefault(
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
        tier_row["possible"] = float(tier_row["possible"]) + weight
        tier_row["earned"] = float(tier_row["earned"]) + (weight if scenario.passed else 0.0)
        tier_row["step_possible"] = float(tier_row["step_possible"]) + weight
        tier_row["step_earned"] = float(tier_row["step_earned"]) + step_earned
        tier_row["total"] = int(tier_row["total"]) + 1
        if scenario.passed:
            tier_row["passed"] = int(tier_row["passed"]) + 1
        else:
            tier_row["failed"] = int(tier_row["failed"]) + 1
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
        difficulty_row["possible"] = float(difficulty_row["possible"]) + weight
        difficulty_row["earned"] = float(difficulty_row["earned"]) + (
            weight if scenario.passed else 0.0
        )
        difficulty_row["step_possible"] = float(difficulty_row["step_possible"]) + weight
        difficulty_row["step_earned"] = float(difficulty_row["step_earned"]) + step_earned
        difficulty_row["total"] = int(difficulty_row["total"]) + 1
        if scenario.passed:
            difficulty_row["passed"] = int(difficulty_row["passed"]) + 1
        else:
            difficulty_row["failed"] = int(difficulty_row["failed"]) + 1
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
        capability_row["scenario_possible"] = float(capability_row["scenario_possible"]) + weight
        capability_row["scenario_earned"] = float(capability_row["scenario_earned"]) + (
            weight if scenario.passed else 0.0
        )
        capability_row["step_possible"] = float(capability_row["step_possible"]) + weight
        capability_row["step_earned"] = float(capability_row["step_earned"]) + step_earned
        capability_row["total"] = int(capability_row["total"]) + 1
        if scenario.passed:
            capability_row["passed"] = int(capability_row["passed"]) + 1
        else:
            capability_row["failed"] = int(capability_row["failed"]) + 1

    for row in by_tier.values():
        possible = float(row["possible"])
        row["ratio"] = float(row["earned"]) / possible if possible else 0.0
        step_possible = float(row["step_possible"])
        row["step_ratio"] = float(row["step_earned"]) / step_possible if step_possible else 0.0

    for row in by_difficulty.values():
        possible = float(row["possible"])
        row["ratio"] = float(row["earned"]) / possible if possible else 0.0
        step_possible = float(row["step_possible"])
        row["step_ratio"] = float(row["step_earned"]) / step_possible if step_possible else 0.0

    for row in by_capability.values():
        scenario_possible = float(row["scenario_possible"])
        step_possible = float(row["step_possible"])
        row["scenario_ratio"] = (
            float(row["scenario_earned"]) / scenario_possible if scenario_possible else 0.0
        )
        row["step_ratio"] = float(row["step_earned"]) / step_possible if step_possible else 0.0

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
        "probe": {
            "passed": probe_passed,
            "total": probe_total,
        },
    }


def _scenario_step_ratio(scenario: ScenarioResult) -> float:
    if scenario.passed:
        return 1.0
    total = scenario.total_step_count
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, scenario.passed_until_step / total))


def _is_contract_failure(category: str) -> bool:
    return category in {
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


def classify_failure(failure: dict[str, Any]) -> str:
    kind = str(failure.get("kind") or "")
    message = str(failure.get("message") or "")
    assertion_type = str(failure.get("assertion_type") or "")

    if kind == "assertion":
        return f"assertion_{assertion_type}" if assertion_type else "assertion"
    if "Cannot read properties of undefined (reading 'getState')" in message:
        return "missing_state_hook"
    if "state_expression must return an object/dict" in message:
        return "invalid_state_hook"
    if "element is not enabled" in message:
        return "action_unavailable"
    if "intercepts pointer events" in message:
        return "action_unavailable"
    if "waiting for locator" in message:
        return "missing_component"
    if "Unknown component" in message:
        return "unknown_component"
    if "is not declared for component" in message:
        return "undeclared_action"
    if "Unsupported action" in message:
        return "unsupported_action"
    if "Page.screenshot" in message:
        return "screenshot_timeout"
    if "TimeoutError" in message:
        return "interaction_timeout"
    if "Page.evaluate" in message:
        return "state_expression_error"
    return kind or "scenario_error"
