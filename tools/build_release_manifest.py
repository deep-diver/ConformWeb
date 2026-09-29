from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PACK_MANIFEST.csv"
CURRENT_RELEASE = "2026-09-29-usability-refresh"
FIELDS = ("archive_path", "source_path", "size_bytes", "sha256", "reason", "release")


def main() -> None:
    previous = load_previous_manifest()
    paths = release_paths()
    rows = []
    for relative in paths:
        path = ROOT / relative
        digest = sha256(path.read_bytes()).hexdigest()
        old = previous.get(relative)
        unchanged = old is not None and old["sha256"] == digest
        release = old["release"] if unchanged else CURRENT_RELEASE
        reason = old["reason"] if unchanged else classify(relative)
        rows.append(
            {
                "archive_path": relative,
                "source_path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": digest,
                "reason": reason,
                "release": release,
            }
        )

    with MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} entries to {MANIFEST}")


def load_previous_manifest() -> dict[str, dict[str, str]]:
    result = subprocess.run(
        ["git", "show", f"HEAD:{MANIFEST.name}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return {
            row["archive_path"]: row
            for row in csv.DictReader(StringIO(result.stdout))
        }
    if MANIFEST.is_file():
        with MANIFEST.open(encoding="utf-8", newline="") as handle:
            return {row["archive_path"]: row for row in csv.DictReader(handle)}
    return {}


def release_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        path
        for path in result.stdout.splitlines()
        if path and path != MANIFEST.name and (ROOT / path).is_file()
    )


def classify(path: str) -> str:
    if path.startswith("detoxbench/"):
        return "core ConformWeb evaluator/compiler source"
    if path.startswith("targets/web/"):
        return "released benchmark target artifact"
    if path.startswith("tests/"):
        return "evaluator/compiler regression tests"
    if path.startswith("tools/"):
        return "reproduction and release tooling"
    if path.startswith("docs/"):
        return "public protocol and usage documentation"
    if path.startswith("reports/") or path.startswith("tables/"):
        return "paper result, audit, or presentation artifact"
    if path.startswith("results_"):
        return "retained compact experiment artifact"
    if path.startswith("cohorts/"):
        return "top-level cohort configuration"
    if path.startswith(".github/"):
        return "continuous integration configuration"
    return "public release metadata and provenance"


if __name__ == "__main__":
    main()
