#!/usr/bin/env python3
"""Build a compact, provenance-tracked ConformWeb poster asset pack."""

from __future__ import annotations

import csv
import hashlib
import shutil
import textwrap
import zipfile
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "reports" / "conformweb_visualizations"
OUT = REPORT_ROOT / "poster_asset_pack_20260929_current756"
ZIP_PATH = REPORT_ROOT / f"{OUT.name}.zip"

FONT_REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")

FAMILY_ROWS = REPORT_ROOT / "figures" / "review" / "representative_rows"
FAILURE_PANELS = REPORT_ROOT / "figures" / "review" / "failure_evidence_columns"
COVERAGE_CSV = REPORT_ROOT / "tables" / "private_reference_coverage.csv"
AUDIT_CSV = REPORT_ROOT / "tables" / "private_admissibility_audit.csv"

HOMEFIX_RUN = (
    ROOT
    / "targets/web/homefix_hub/tier_c/cohorts/T/20260514_homefix_cd_recalibrated2_f_10x"
    / "runs/claude_sonnet46/r08/20260514-120945-96a346d8"
)
HOMEFIX_SCENARIO = HOMEFIX_RUN / "screenshots/private_06_full_quality_invoice_path"

READY = OUT / "ready_to_use"
ALTERNATIVES = OUT / "alternatives"
SOURCE_SCREENS = OUT / "source_screens"
DATA = OUT / "data"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size=size)


def draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font_obj, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=font_obj)
    width = box[2] - box[0]
    draw.text((xy[0] - width / 2, xy[1]), text, font=font_obj, fill=fill)


def wrap(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(text, width=width, break_long_words=False))


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def current_coverage_rows() -> tuple[list[dict[str, int | str]], dict[str, int]]:
    totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with COVERAGE_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            # Exclude the Clinical A git fallback so the figure matches the
            # current frozen target tree: 288 public + 468 private = 756.
            if row["contract_source"] != "local" or row["private_source"] != "local":
                continue
            category = row["category"]
            totals[category]["declared"] += int(row["declared_in_public_contract"])
            totals[category]["shared"] += int(row["private_seen_in_public_examples"])
            totals[category]["private_only"] += int(row["private_only_but_declared"])
            totals[category]["undeclared"] += int(row["private_undeclared"])

    order = ["Actions", "State / observation paths", "Routes/pages", "Rendered tables", "Events"]
    rows: list[dict[str, int | str]] = []
    for category in order:
        values = totals[category]
        declared = values["declared"]
        not_private = declared - values["shared"] - values["private_only"]
        rows.append(
            {
                "category": category,
                "declared": declared,
                "shared": values["shared"],
                "private_only": values["private_only"],
                "not_private": not_private,
                "undeclared": values["undeclared"],
            }
        )

    audit = {
        "private_files": 0,
        "private_scenarios": 0,
        "private_steps": 0,
        "compiled_checks": 0,
        "compile_errors": 0,
    }
    with AUDIT_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["contract_source"] != "local" or row["private_source"] != "local":
                continue
            audit["private_files"] += 1
            audit["private_scenarios"] += int(row["private_scenarios"])
            audit["private_steps"] += int(row["private_steps"])
            audit["compiled_checks"] += int(row["compiled_checks"])
            if row["compile_ok"] != "True":
                audit["compile_errors"] += 1
    return rows, audit


def build_coverage_figure(rows: list[dict[str, int | str]], audit: dict[str, int]) -> Path:
    width, height = 3000, 1580
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    ink = "#202124"
    muted = "#5F6368"
    grid = "#E5E7EB"
    shared_color = "#F9AB00"
    private_color = "#35B9C4"
    unused_color = "#DADCE0"

    draw.text((140, 90), "Hidden tests stay within the public contract", font=font(78, bold=True), fill=ink)
    draw.text(
        (140, 190),
        "Private scenario references are either shared with public examples or private-only but publicly declared.",
        font=font(38),
        fill=muted,
    )

    legend_y = 300
    legend = [
        (shared_color, "Used in public + private scenarios"),
        (private_color, "Private-only, declared in public contract"),
        (unused_color, "Declared, not referenced by private scenarios"),
    ]
    legend_x = 730
    for color, label in legend:
        draw.rounded_rectangle((legend_x, legend_y, legend_x + 60, legend_y + 36), radius=5, fill=color)
        draw.text((legend_x + 78, legend_y - 2), label, font=font(30, bold=True), fill=ink)
        legend_x += 690

    chart_left, chart_right = 650, 2830
    chart_top, row_gap = 430, 190
    bar_height = 92
    labels = {
        "State / observation paths": "State paths",
        "Routes/pages": "Routes",
    }

    for index, row in enumerate(rows):
        y = chart_top + index * row_gap
        category = labels.get(str(row["category"]), str(row["category"]))
        draw.text((100, y + 20), category, font=font(42, bold=True), fill=ink)
        declared = int(row["declared"])
        segments = [
            (int(row["shared"]), shared_color, ink),
            (int(row["private_only"]), private_color, "white"),
            (int(row["not_private"]), unused_color, ink),
        ]
        x = chart_left
        for value, color, text_color in segments:
            segment_width = (chart_right - chart_left) * value / declared if declared else 0
            if segment_width > 0:
                draw.rectangle((x, y, x + segment_width, y + bar_height), fill=color)
                if segment_width >= 90:
                    draw_centered(draw, (int(x + segment_width / 2), y + 22), str(value), font(38, bold=True), text_color)
            x += segment_width
        draw.text((chart_right + 25, y + 25), f"n={declared}", font=font(28), fill=muted)
        draw.line((chart_left, y + bar_height + 36, chart_right, y + bar_height + 36), fill=grid, width=2)

    footer_y = 1400
    summary = (
        f"Current frozen tree: {audit['private_files']} private files | "
        f"{audit['private_scenarios']} private scenarios | {audit['private_steps']:,} steps | "
        f"{audit['compiled_checks']:,} compiled preconditions/checks | "
        f"{audit['compile_errors']} compile errors"
    )
    draw.text((140, footer_y), summary, font=font(34, bold=True), fill=ink)
    draw.text(
        (140, footer_y + 58),
        "Scope: current targets/web only (288 public + 468 private = 756 scenarios); no Clinical A fallback.",
        font=font(30),
        fill=muted,
    )

    output = READY / "02_public_contract_private_scenario_coverage_current756.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)
    return output


def build_journey_figure() -> tuple[Path, list[tuple[Path, Path]]]:
    stages = [
        (
            "1. Select service",
            "/#/jobs",
            "select_leak_button.click",
            "selected_service_id, selected_service_name",
            "004-after.png",
        ),
        (
            "2. Approve quote",
            "/#/booking",
            "approve_homeowner_button.click",
            "quote_amount, quote_status, homeowner_approval_status",
            "012-after.png",
        ),
        (
            "3. Dispatch visit",
            "/#/dispatch",
            "dispatch_visit_button.click",
            "assigned_technician, parts_rows, dispatch_status",
            "022-after.png",
        ),
        (
            "4. Pass QA + invoice",
            "/#/quality",
            "issue_invoice_button.click",
            "permit_rows, qa_status, invoice_status, invoice_total",
            "032-after.png",
        ),
    ]

    width, height = 3600, 1260
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    ink = "#17213B"
    muted = "#5F6368"
    blue = "#2563EB"
    green = "#0F9D78"
    border = "#D1D5DB"

    draw.text((80, 55), "One hidden journey, entirely on the public behavioral surface", font=font(70, bold=True), fill=ink)
    draw.text(
        (80, 145),
        "Actual browser frames from a passing HomeFix Tier C private scenario",
        font=font(36),
        fill=muted,
    )

    margin = 80
    gap = 55
    panel_width = (width - 2 * margin - 3 * gap) // 4
    screenshot_height = 565
    screenshot_top = 300
    copies: list[tuple[Path, Path]] = []

    for index, (title, route, action, paths, filename) in enumerate(stages):
        x = margin + index * (panel_width + gap)
        source = HOMEFIX_SCENARIO / filename
        target = SOURCE_SCREENS / f"homefix_tier_c_{index + 1}_{filename}"
        copies.append((source, target))
        with Image.open(source) as raw:
            frame = ImageOps.fit(raw.convert("RGB"), (panel_width, screenshot_height), method=Image.Resampling.LANCZOS)
        canvas.paste(frame, (x, screenshot_top))
        draw.rectangle((x, screenshot_top, x + panel_width, screenshot_top + screenshot_height), outline=border, width=3)

        draw.text((x, 225), title, font=font(36, bold=True), fill=ink)
        draw.text((x, screenshot_top + screenshot_height + 30), route, font=font(32, bold=True), fill=blue)
        draw.text((x, screenshot_top + screenshot_height + 77), wrap(action, 34), font=font(27, bold=True), fill=ink)
        draw.text((x, screenshot_top + screenshot_height + 122), wrap(paths, 42), font=font(25), fill=green)

        if index < len(stages) - 1:
            arrow_x = x + panel_width + 10
            arrow_y = screenshot_top + screenshot_height // 2
            draw.line((arrow_x, arrow_y, arrow_x + 30, arrow_y), fill=ink, width=8)
            draw.polygon(
                [(arrow_x + 30, arrow_y - 18), (arrow_x + 55, arrow_y), (arrow_x + 30, arrow_y + 18)],
                fill=ink,
            )

    footer = "Private scenario steps -> declared public components/actions -> contract-defined state checks"
    draw.text((80, 1160), footer, font=font(34, bold=True), fill=ink)
    draw.text((80, 1205), "Scenario: private_06_full_quality_invoice_path (32 compiled steps, passed)", font=font(28), fill=muted)

    output = READY / "03_homefix_private_journey_actual_screens.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, optimize=True)
    return output, copies


def write_coverage_csv(rows: list[dict[str, int | str]]) -> Path:
    path = DATA / "coverage_current756.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_readme(audit: dict[str, int]) -> None:
    text = f"""# ConformWeb Poster Asset Pack (Current Frozen 756)

This pack contains poster-ready actual browser screens and contract/private-scenario provenance figures.

## Ready-to-use assets

1. `ready_to_use/01_campus_family_complexity_a_to_d.png`
   Actual target-reference screens for one family across Tier A-D. Suggested overlay: state paths 27 -> 44 -> 64 -> 84; pages 3 -> 4 -> 5 -> 6; roles 2 -> 4 -> 5 -> 6.
2. `ready_to_use/02_public_contract_private_scenario_coverage_current756.png`
   Recomputed for the current frozen target tree only: 288 public + 468 private = 756 scenarios. Clinical A fallback is excluded.
3. `ready_to_use/03_homefix_private_journey_actual_screens.png`
   Four actual browser frames from a passing hidden scenario, aligned to public routes, actions, and state paths.
4. `ready_to_use/04_private_step_public_declaration_witness.png`
   Step-by-step mapping from a private journey to public declarations and compiled checks.
5. `ready_to_use/05_failure_before_after_example.png`
   Actual before/after failure evidence with expected/observed annotations.

## Audit scope

- Private files: {audit['private_files']}
- Private scenarios: {audit['private_scenarios']}
- Private steps: {audit['private_steps']}
- Compiled preconditions/checks: {audit['compiled_checks']}
- Compile errors: {audit['compile_errors']}

Correct poster claim: `Refs(private scenarios) subset-of Declarations(public contract)`. There is no separate private contract. Public scenario examples are not exhaustive, and candidate generation does not receive either public or private scenario files.

## Additional choices

- `alternatives/family_rows/`: all six A-D family composites.
- `alternatives/failure_evidence/`: all 39 retained annotated failure panels.
- `source_screens/`: the four unannotated HomeFix frames used in the journey panel.
- `data/coverage_current756.csv`: counts behind the recomputed coverage figure.
- `manifest.csv`: SHA-256, byte size, and source/provenance note for every packaged file.

## Primary provenance

- `targets/web/homefix_hub/tier_c/contract.dsl.yaml`
- `targets/web/homefix_hub/tier_c/scenarios.private.dsl.yaml`
- `{HOMEFIX_RUN.relative_to(ROOT)}/summary.json`
- `reports/conformweb_visualizations/tables/private_reference_coverage.csv`
- `reports/conformweb_visualizations/tables/private_admissibility_audit.csv`
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest() -> None:
    rows = []
    for path in sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "manifest.csv"):
        relative = path.relative_to(OUT)
        if "source_screens" in relative.parts:
            note = "Raw browser frame from a passing retained HomeFix Tier C private journey"
        elif "failure_evidence" in relative.parts or path.name.startswith("05_failure"):
            note = "Annotated retained run failure evidence"
        elif "family_rows" in relative.parts or path.name.startswith("01_campus"):
            note = "A-D family screen composite from retained target/reference assets"
        elif path.name.startswith("02_public") or path.name == "coverage_current756.csv":
            note = "Recomputed from current local contract/private rows; Clinical A fallback excluded"
        elif path.name.startswith("03_homefix"):
            note = "Generated from four passing retained browser frames and public contract labels"
        elif path.name.startswith("04_private"):
            note = "Private-step to public-declaration witness for HomeFix Tier C"
        else:
            note = "Pack documentation"
        rows.append(
            {
                "path": str(relative),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "note": note,
            }
        )
    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "bytes", "sha256", "note"])
        writer.writeheader()
        writer.writerows(rows)


def build_zip() -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in OUT.rglob("*") if p.is_file()):
            archive.write(path, arcname=str(Path(OUT.name) / path.relative_to(OUT)))


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    READY.mkdir(parents=True)
    (ALTERNATIVES / "family_rows").mkdir(parents=True)
    (ALTERNATIVES / "failure_evidence").mkdir(parents=True)
    SOURCE_SCREENS.mkdir(parents=True)
    DATA.mkdir(parents=True)

    copy_file(
        FAMILY_ROWS / "04_campus_registrar_command.png",
        READY / "01_campus_family_complexity_a_to_d.png",
    )
    copy_file(
        REPORT_ROOT / "archive/private_admissibility_extras/appendix_private_contract_witness.png",
        READY / "04_private_step_public_declaration_witness.png",
    )
    copy_file(
        FAILURE_PANELS / "38_homefix_hub_tier_d_route_persistence_drift.png",
        READY / "05_failure_before_after_example.png",
    )

    for source in sorted(FAMILY_ROWS.glob("*.png")):
        copy_file(source, ALTERNATIVES / "family_rows" / source.name)
    for source in sorted(FAILURE_PANELS.glob("*.png")):
        copy_file(source, ALTERNATIVES / "failure_evidence" / source.name)

    coverage_rows, audit = current_coverage_rows()
    build_coverage_figure(coverage_rows, audit)
    _, screen_copies = build_journey_figure()
    for source, destination in screen_copies:
        copy_file(source, destination)
    write_coverage_csv(coverage_rows)
    write_readme(audit)
    write_manifest()
    build_zip()

    print(OUT)
    print(ZIP_PATH)


if __name__ == "__main__":
    main()
