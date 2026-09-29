from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from detoxbench.dsl import load_dsl_yaml


@dataclass(frozen=True)
class TargetInventory:
    target: str
    family: str
    tier: str
    status: str
    contract: bool
    public_file: bool
    private_file: bool
    legacy_file: bool
    reference_app: bool
    public_scenarios: int
    private_scenarios: int
    legacy_scenarios: int
    errors: tuple[str, ...] = ()

    @property
    def scenario_total(self) -> int:
        return self.public_scenarios + self.private_scenarios + self.legacy_scenarios

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scenario_total"] = self.scenario_total
        payload["available_scenario_sets"] = available_scenario_sets(self)
        return payload


def discover_target_inventory(targets_root: Path) -> list[TargetInventory]:
    root = targets_root.resolve()
    target_dirs = sorted(
        path
        for path in root.glob("*/tier_*")
        if path.is_dir()
    )
    return [inspect_target(path, root=root) for path in target_dirs]


def inspect_target(target_dir: Path, *, root: Path | None = None) -> TargetInventory:
    target_dir = target_dir.resolve()
    root = root.resolve() if root else target_dir.parent.parent
    contract = target_dir / "contract.dsl.yaml"
    public = target_dir / "scenarios.public.dsl.yaml"
    private = target_dir / "scenarios.private.dsl.yaml"
    legacy = target_dir / "scenarios.dsl.yaml"
    reference_app = target_dir / "reference_app"

    errors: list[str] = []
    public_count = _scenario_count(public, errors)
    private_count = _scenario_count(private, errors)
    legacy_count = _scenario_count(legacy, errors)

    if errors:
        status = "invalid"
    elif not contract.is_file() or not (public.is_file() or private.is_file() or legacy.is_file()):
        status = "unavailable"
    elif reference_app.is_dir() and (legacy.is_file() or (public.is_file() and private.is_file())):
        status = "ready"
    elif public.is_file() and not private.is_file():
        status = "public-only"
    elif private.is_file() and not public.is_file():
        status = "private-only"
    else:
        status = "partial"

    try:
        target = str(target_dir.relative_to(root))
    except ValueError:
        target = str(target_dir)

    return TargetInventory(
        target=target,
        family=target_dir.parent.name,
        tier=target_dir.name.removeprefix("tier_").upper(),
        status=status,
        contract=contract.is_file(),
        public_file=public.is_file(),
        private_file=private.is_file(),
        legacy_file=legacy.is_file(),
        reference_app=reference_app.is_dir(),
        public_scenarios=public_count,
        private_scenarios=private_count,
        legacy_scenarios=legacy_count,
        errors=tuple(errors),
    )


def available_scenario_sets(inventory: TargetInventory) -> list[str]:
    if inventory.legacy_file:
        return ["all"]
    available = []
    if inventory.public_file:
        available.append("public")
    if inventory.private_file:
        available.append("private")
    if inventory.public_file and inventory.private_file:
        available.insert(0, "all")
    return available


def summarize_target_inventory(inventory: list[TargetInventory]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for item in inventory:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
    return {
        "target_slots": len(inventory),
        "status_counts": status_counts,
        "public_scenarios": sum(item.public_scenarios for item in inventory),
        "private_scenarios": sum(item.private_scenarios for item in inventory),
        "legacy_scenarios": sum(item.legacy_scenarios for item in inventory),
        "scenario_total": sum(item.scenario_total for item in inventory),
    }


def _scenario_count(path: Path, errors: list[str]) -> int:
    if not path.is_file():
        return 0
    try:
        raw = load_dsl_yaml(path)
    except Exception as exc:  # inventory should report malformed releases, not abort discovery
        errors.append(f"{path.name}: {exc}")
        return 0
    scenarios = raw.get("scenarios")
    if not isinstance(scenarios, list):
        errors.append(f"{path.name}: scenarios is not a list")
        return 0
    return len(scenarios)
