from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from detoxbench.dashboard import DashboardConfig, build_dashboard_data, target_label
from detoxbench.core.yaml_loader import load_yaml


@dataclass(frozen=True)
class GalleryConfig:
    output: Path
    title: str
    targets_root: Path | None = None
    manifest: Path | None = None


def build_gallery(config: GalleryConfig) -> dict[str, Any]:
    data = build_gallery_data(config)
    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.output.write_text(render_gallery_html(data), encoding="utf-8")
    return {
        "output": str(config.output),
        "targets": len(data["targets"]),
    }


def build_gallery_data(config: GalleryConfig) -> dict[str, Any]:
    target_entries = discover_target_entries(config)
    targets = [summarize_target(entry, config.output.parent) for entry in target_entries]
    targets.sort(key=lambda target: target["label"].lower())
    return {
        "title": config.title,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "targets": targets,
    }


def discover_target_entries(config: GalleryConfig) -> list[dict[str, Path]]:
    entries: list[dict[str, Path]] = []
    if config.manifest:
        manifest_dir = config.manifest.resolve().parent
        raw = load_yaml(config.manifest)
        for item in raw.get("targets", []):
            if not isinstance(item, dict):
                continue
            target_dir = resolve_manifest_path(item["target_dir"], manifest_dir)
            dashboard = (
                resolve_manifest_path(item["dashboard"], manifest_dir)
                if item.get("dashboard")
                else default_dashboard(target_dir)
            )
            preview = (
                resolve_manifest_path(item["preview"], manifest_dir)
                if item.get("preview")
                else default_preview(target_dir)
            )
            entries.append(
                {
                    "target_dir": target_dir,
                    "dashboard": dashboard.resolve(),
                    "preview": preview.resolve(),
                }
            )
    if config.targets_root:
        for contract in sorted(config.targets_root.rglob("contract.dsl.yaml")):
            target_dir = contract.parent
            entries.append(
                {
                    "target_dir": target_dir.resolve(),
                    "dashboard": default_dashboard(target_dir),
                    "preview": default_preview(target_dir),
                }
            )
    return entries


def resolve_manifest_path(value: str | Path, manifest_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = manifest_dir / path
    return path.resolve()


def summarize_target(entry: dict[str, Path], asset_base_dir: Path) -> dict[str, Any]:
    target_dir = entry["target_dir"]
    dashboard_path = entry["dashboard"]
    preview_path = entry["preview"]
    runs_dir = default_runs_dir(target_dir)
    dashboard_data: dict[str, Any] | None = None
    if runs_dir.exists():
        dashboard_data = build_dashboard_data(
            DashboardConfig(
                target_dir=target_dir,
                runs_dir=runs_dir,
                output=dashboard_path,
                title=f"ConformWeb Dashboard: {target_dir.name}",
            )
        )

    runs = dashboard_data.get("runs", []) if dashboard_data else []
    scenarios = dashboard_data.get("scenarios", []) if dashboard_data else []
    subjects = dashboard_data.get("subjects", []) if dashboard_data else []
    failures = sum(run.get("failed_scenario_count", 0) for run in runs)
    best_score = max(
        (run.get("score", {}).get("formal", {}).get("ratio", 0.0) for run in runs),
        default=0.0,
    )
    reference = next((run for run in runs if run.get("subject") == "reference"), None)
    if reference is None:
        reference = next((run for run in runs if run.get("subject") == "reference_app"), None)
    reference_score = reference.get("score", {}).get("formal", {}).get("ratio") if reference else None
    return {
        "id": target_dir.name,
        "label": target_label(target_dir),
        "target_path": str(target_dir),
        "dashboard_ref": relative_ref(dashboard_path, asset_base_dir) if dashboard_path.exists() else None,
        "preview_ref": relative_ref(preview_path, asset_base_dir) if preview_path and preview_path.exists() else None,
        "scenario_count": len(scenarios),
        "subject_count": len(subjects),
        "run_count": len(runs),
        "failure_count": failures,
        "best_score": best_score,
        "reference_score": reference_score,
        "tiers": dashboard_data.get("tier_summary", {}) if dashboard_data else {},
    }


def default_dashboard(target_dir: Path) -> Path:
    return (target_dir / "reports" / "dashboard" / "index.html").resolve()


def default_runs_dir(target_dir: Path) -> Path:
    cohorts = target_dir / "cohorts"
    if cohorts.exists():
        return cohorts
    return target_dir / "artifacts" / "runs"


def default_preview(target_dir: Path) -> Path:
    candidates = [
        target_dir / "reports" / "dashboard" / "app-preview.png",
        target_dir / "reports" / "dashboard" / "preview.png",
        target_dir / "artifacts" / "dashboard" / "app-preview.png",
        target_dir / "artifacts" / "dashboard" / "preview.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def relative_ref(path: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base_dir.resolve())).as_posix()


def render_gallery_html(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return GALLERY_HTML.replace("__GALLERY_DATA__", payload)


GALLERY_HTML = r"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ConformWeb Gallery</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f5f2ed;
        --panel: #fffefb;
        --ink: #181512;
        --muted: #746b61;
        --line: #d9d0c4;
        --ok: #176a47;
        --bad: #aa3030;
        --accent: #234f8f;
        --shadow: 0 18px 48px rgba(42, 34, 25, 0.11);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        background: var(--bg);
        color: var(--ink);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      header {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: end;
        padding: 22px;
        border-bottom: 1px solid var(--line);
        background: rgba(255, 254, 251, 0.88);
        backdrop-filter: blur(10px);
        position: sticky;
        top: 0;
        z-index: 2;
      }
      h1, h2, p { margin-top: 0; }
      h1 { margin-bottom: 4px; font-size: 1.35rem; }
      .meta { color: var(--muted); font-size: 0.84rem; }
      .pill {
        display: inline-flex;
        align-items: center;
        min-height: 26px;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 0 10px;
        background: var(--panel);
        color: var(--muted);
        font-size: 0.8rem;
      }
      main {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
        gap: 16px;
        padding: 18px;
      }
      .card {
        display: grid;
        gap: 12px;
        border: 1px solid var(--line);
        border-radius: 8px;
        background: var(--panel);
        box-shadow: var(--shadow);
        overflow: hidden;
      }
      .preview {
        aspect-ratio: 16 / 10;
        background: #ece5dc;
        border-bottom: 1px solid var(--line);
        display: grid;
        place-items: center;
        overflow: hidden;
      }
      .preview img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }
      .body { display: grid; gap: 12px; padding: 14px; }
      .card h2 { margin-bottom: 3px; font-size: 1.05rem; }
      .metrics {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 8px;
      }
      .metric {
        border: 1px solid var(--line);
        border-radius: 8px;
        padding: 8px;
        background: #fbf8f2;
      }
      .metric strong { display: block; font-size: 1.05rem; }
      .metric span { display: block; color: var(--muted); font-size: 0.72rem; }
      .tiers { display: flex; flex-wrap: wrap; gap: 6px; }
      a.button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 36px;
        border: 1px solid var(--accent);
        border-radius: 7px;
        background: var(--accent);
        color: #fff;
        text-decoration: none;
        font-weight: 700;
      }
      .missing {
        color: var(--muted);
        font-size: 0.88rem;
      }
      @media (max-width: 760px) {
        header { display: grid; align-items: start; }
        main { grid-template-columns: 1fr; padding: 12px; }
      }
    </style>
  </head>
  <body>
    <header>
      <div>
        <h1 id="title"></h1>
        <div class="meta" id="generated"></div>
      </div>
      <div class="pill" id="count"></div>
    </header>
    <main id="cards"></main>
    <script id="gallery-data" type="application/json">__GALLERY_DATA__</script>
    <script>
      const data = JSON.parse(document.getElementById("gallery-data").textContent);
      const cards = document.getElementById("cards");
      const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
      const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`;
      document.getElementById("title").textContent = data.title;
      document.getElementById("generated").textContent = `Generated ${data.generated_at}`;
      document.getElementById("count").textContent = `${data.targets.length} targets`;
      cards.innerHTML = data.targets.map((target) => `
        <article class="card">
          <div class="preview">
            ${target.preview_ref ? `<img src="${esc(target.preview_ref)}" alt="${esc(target.label)} preview" />` : `<span class="missing">No preview</span>`}
          </div>
          <div class="body">
            <div>
              <h2>${esc(target.label)}</h2>
              <div class="meta">${esc(target.target_path)}</div>
            </div>
            <div class="metrics">
              ${metric(target.scenario_count, "scenarios")}
              ${metric(target.subject_count, "subjects")}
              ${metric(pct(target.best_score), "best score")}
              ${metric(target.failure_count, "failures")}
            </div>
            <div class="tiers">${Object.entries(target.tiers || {}).map(([tier, count]) => `<span class="pill">${esc(tier)} ${esc(count)}</span>`).join("")}</div>
            ${target.dashboard_ref ? `<a class="button" href="${esc(target.dashboard_ref)}">Open Dashboard</a>` : `<div class="missing">Dashboard has not been built yet.</div>`}
          </div>
        </article>
      `).join("");
      function metric(value, label) {
        return `<div class="metric"><strong>${esc(value)}</strong><span>${esc(label)}</span></div>`;
      }
    </script>
  </body>
</html>
"""
