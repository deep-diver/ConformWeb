#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "results_iterative_repair_public_feedback_ad_subset"

ROUND_LABELS = {0: "@1", 1: "@2", 2: "@3"}
TIERS = ["A", "B", "C", "D"]
SEEDS = list(range(1, 11))

FAMILIES = {
    "freshcart_market": {
        "label": "FreshCart Market",
        "roots": [
            RESULT_ROOT / "public_feedback_ad_20260709_openai",
            RESULT_ROOT / "public_feedback_ad_20260709_anthropic",
            RESULT_ROOT / "public_feedback_ad_20260709_google_retry",
        ],
    },
    "homefix_hub": {
        "label": "HomeFix Hub",
        "roots": [
            RESULT_ROOT / "public_feedback_ad_20260709_homefix_openai",
            RESULT_ROOT / "public_feedback_ad_20260709_homefix_anthropic",
            RESULT_ROOT / "public_feedback_ad_20260709_homefix_anthropic_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_homefix_anthropic_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_homefix_google",
        ],
    },
    "stayflow_concierge": {
        "label": "StayFlow Concierge",
        "roots": [
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_openai",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_openai_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_openai_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_openai_tail2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_bcd_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_b_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_cd_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_c_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_d_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_d_tail2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_b_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_c_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_d_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_b_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_d_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_c_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_d_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_b_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_d_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_b_final_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_c_final_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_final_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_d_final_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_d_final_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_b_final2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_c_final2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_final2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_d_final2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_d_final2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_c_final3_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_final3_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_d_final3_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_d_final3_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_final4_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_sonnet_d_final4_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_d_final4_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_final5_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_d_final5_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_anthropic_opus_c_final6_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_flashlite_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_flash_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_flash_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_flash_final_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_pro_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_pro_tail_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_pro_final_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_pro_final2_rescue",
            RESULT_ROOT / "public_feedback_ad_20260709_stayflow_google_tierd_pro_final3_rescue",
        ],
    },
}

MODELS = [
    ("M", "gpt54_nano", "GPT-5.4 nano"),
    ("M", "claude_haiku45", "Claude Haiku 4.5"),
    ("M", "gemini31_flash_lite", "Gemini 3.1 Flash Lite"),
    ("T", "gpt54_mini", "GPT-5.4 mini"),
    ("T", "claude_sonnet46", "Claude Sonnet 4.6"),
    ("T", "gemini_flash_latest", "Gemini 3.1 Flash"),
    ("F", "gpt54", "GPT-5.4"),
    ("F", "claude_opus46", "Claude Opus 4.6"),
    ("F", "gemini31_pro_preview", "Gemini 3.1 Pro Preview"),
]
MODEL_GROUP_LABEL = {"M": "Mini", "T": "Turbo", "F": "Frontier"}
MODEL_GROUP_BY_SLUG = {slug: group for group, slug, _ in MODELS}
MODEL_LABEL_BY_SLUG = {slug: label for _, slug, label in MODELS}


def main() -> int:
    records, diagnostics = load_records()
    expected_keys = [
        (family, tier, slug, seed, round_index)
        for family in FAMILIES
        for tier in TIERS
        for _, slug, _ in MODELS
        for seed in SEEDS
        for round_index in ROUND_LABELS
    ]
    missing_keys = [key for key in expected_keys if key not in records]
    unexpected_keys = [key for key in records if key not in set(expected_keys)]
    audit = audit_public_feedback()

    aggregate = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scenario_policy": {
            "repair_feedback": "public scenarios only",
            "reported_evaluation": "all scenarios, public plus private",
            "round_labels": {"round_0": "@1", "round_1": "@2", "round_2": "@3"},
        },
        "root_selection": {
            family: [str(path) for path in spec["roots"]]
            for family, spec in FAMILIES.items()
        },
        "excluded_roots": [
            str(RESULT_ROOT / "public_feedback_ad_20260709_google"),
        ],
        "expected_record_count": len(expected_keys),
        "included_record_count": len(records),
        "missing_record_count": len(missing_keys),
        "unexpected_record_count": len(unexpected_keys),
        "duplicate_record_count": len(diagnostics["duplicates"]),
        "diagnostics": {
            **diagnostics,
            "missing_records": [key_to_dict(key) for key in missing_keys[:200]],
            "missing_records_truncated": max(0, len(missing_keys) - 200),
            "unexpected_records": [key_to_dict(key) for key in unexpected_keys[:200]],
            "unexpected_records_truncated": max(0, len(unexpected_keys) - 200),
        },
        "public_feedback_audit": audit,
        "completion": completion_summary(records, expected_keys),
        "summaries": build_summaries(records),
    }

    write_json(RESULT_ROOT / "public_feedback_ad_20260709_aggregate.json", aggregate)
    write_text(RESULT_ROOT / "public_feedback_ad_20260709_report.md", render_markdown(aggregate))
    write_text(ROOT / "tables" / "public_feedback_ad_iterative_repair_table.tex", render_latex(aggregate))
    print(json.dumps({
        "aggregate": str(RESULT_ROOT / "public_feedback_ad_20260709_aggregate.json"),
        "report": str(RESULT_ROOT / "public_feedback_ad_20260709_report.md"),
        "table": str(ROOT / "tables" / "public_feedback_ad_iterative_repair_table.tex"),
        "included_record_count": len(records),
        "missing_record_count": len(missing_keys),
        "public_feedback_violations": audit["violation_count"],
    }, indent=2))
    return 0


def load_records() -> tuple[dict[tuple[str, str, str, int, int], dict[str, Any]], dict[str, Any]]:
    records: dict[tuple[str, str, str, int, int], dict[str, Any]] = {}
    duplicates: list[dict[str, Any]] = []
    scenario_set_violations: list[dict[str, Any]] = []
    decode_errors: list[dict[str, str]] = []
    for family, spec in FAMILIES.items():
        for root in spec["roots"]:
            for tier in TIERS:
                for _, slug, _ in MODELS:
                    for seed in SEEDS:
                        for round_index in ROUND_LABELS:
                            key = (family, tier, slug, seed, round_index)
                            path = root / "runs" / family / f"tier_{tier.lower()}" / slug / f"seed_{seed:02d}" / "records" / f"round_{round_index}.json"
                            if not path.is_file():
                                continue
                            try:
                                record = json.loads(path.read_text(encoding="utf-8"))
                            except json.JSONDecodeError as exc:
                                decode_errors.append({"path": str(path), "error": str(exc)})
                                continue
                            scenario_set = record.get("scenario_set")
                            if scenario_set not in (None, "all"):
                                scenario_set_violations.append({"path": str(path), "scenario_set": record.get("scenario_set")})
                            if key in records:
                                duplicates.append({
                                    "key": key_to_dict(key),
                                    "kept_path": records[key].get("_path"),
                                    "duplicate_path": str(path),
                                })
                                continue
                            record["_path"] = str(path)
                            records[key] = record
    return records, {
        "duplicates": duplicates,
        "scenario_set_violations": scenario_set_violations,
        "decode_errors": decode_errors,
    }


def audit_public_feedback() -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    patch_count = 0
    feedback_probe_count = 0
    for family, spec in FAMILIES.items():
        for root in spec["roots"]:
            task_roots = [
                root / "runs" / family / f"tier_{tier.lower()}" / slug / f"seed_{seed:02d}"
                for tier in TIERS
                for _, slug, _ in MODELS
                for seed in SEEDS
            ]
            for task_root in task_roots:
                for round_index in [1, 2]:
                    path = task_root / "apps" / f"round_{round_index}" / "patch_metadata.json"
                    if not path.is_file():
                        continue
                    patch_count += 1
                    try:
                        metadata = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as exc:
                        violations.append({"path": str(path), "type": "patch_metadata_json_error", "error": str(exc)})
                        continue
                    feedback = metadata.get("feedback") or {}
                    scenario_id = feedback.get("scenario_id")
                    scenario_set = feedback.get("scenario_set")
                    source_set = metadata.get("feedback_source_scenario_set")
                    if source_set != "public" or (scenario_set and scenario_set != "public") or (
                        scenario_id and not str(scenario_id).startswith("public_")
                    ):
                        violations.append({
                            "path": str(path),
                            "type": "non_public_patch_feedback",
                            "status": metadata.get("status"),
                            "feedback_source_scenario_set": source_set,
                            "feedback_scenario_set": scenario_set,
                            "feedback_scenario_id": scenario_id,
                        })
                for round_index in [0, 1]:
                    path = task_root / "records" / f"public_feedback_round_{round_index}.json"
                    if not path.is_file():
                        continue
                    feedback_probe_count += 1
                    try:
                        record = json.loads(path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as exc:
                        violations.append({"path": str(path), "type": "feedback_record_json_error", "error": str(exc)})
                        continue
                    feedback = record.get("failure_feedback") or {}
                    scenario_id = feedback.get("scenario_id")
                    scenario_set = record.get("scenario_set") or feedback.get("scenario_set")
                    if scenario_set != "public" or (scenario_id and not str(scenario_id).startswith("public_")):
                        violations.append({
                            "path": str(path),
                            "type": "non_public_feedback_probe",
                            "scenario_set": scenario_set,
                            "scenario_id": scenario_id,
                        })
    return {
        "patch_metadata_count": patch_count,
        "public_feedback_probe_count": feedback_probe_count,
        "violation_count": len(violations),
        "violations": violations[:200],
        "violations_truncated": max(0, len(violations) - 200),
    }


def build_summaries(records: dict[tuple[str, str, str, int, int], dict[str, Any]]) -> dict[str, Any]:
    summaries: dict[str, Any] = {
        "overall": {label: summarize(records, all_keys(round_index)) for round_index, label in ROUND_LABELS.items()},
        "by_tier": {},
        "by_family": {},
        "by_family_tier": {},
        "by_group": {},
        "by_model": {},
    }
    for tier in TIERS:
        summaries["by_tier"][tier] = {
            label: summarize(records, all_keys(round_index, tiers=[tier]))
            for round_index, label in ROUND_LABELS.items()
        }
    for family in FAMILIES:
        summaries["by_family"][family] = {
            label: summarize(records, all_keys(round_index, families=[family]))
            for round_index, label in ROUND_LABELS.items()
        }
        summaries["by_family_tier"][family] = {}
        for tier in TIERS:
            summaries["by_family_tier"][family][tier] = {
                label: summarize(records, all_keys(round_index, families=[family], tiers=[tier]))
                for round_index, label in ROUND_LABELS.items()
            }
    for group in ["M", "T", "F"]:
        slugs = [slug for model_group, slug, _ in MODELS if model_group == group]
        summaries["by_group"][group] = {
            label: summarize(records, all_keys(round_index, models=slugs))
            for round_index, label in ROUND_LABELS.items()
        }
    for group, slug, label_name in MODELS:
        model_block = {
            "group": group,
            "label": label_name,
            "rounds": {
                label: summarize(records, all_keys(round_index, models=[slug]))
                for round_index, label in ROUND_LABELS.items()
            },
            "tiers": {},
        }
        for tier in TIERS:
            model_block["tiers"][tier] = {
                label: summarize(records, all_keys(round_index, models=[slug], tiers=[tier]))
                for round_index, label in ROUND_LABELS.items()
            }
        summaries["by_model"][slug] = model_block
    return summaries


def all_keys(
    round_index: int,
    families: Iterable[str] | None = None,
    tiers: Iterable[str] | None = None,
    models: Iterable[str] | None = None,
    seeds: Iterable[int] | None = None,
) -> list[tuple[str, str, str, int, int]]:
    family_list = list(families) if families is not None else list(FAMILIES)
    tier_list = list(tiers) if tiers is not None else TIERS
    model_list = list(models) if models is not None else [slug for _, slug, _ in MODELS]
    seed_list = list(seeds) if seeds is not None else SEEDS
    return [
        (family, tier, slug, seed, round_index)
        for family in family_list
        for tier in tier_list
        for slug in model_list
        for seed in seed_list
    ]


def summarize(records: dict[tuple[str, str, str, int, int], dict[str, Any]], keys: list[tuple[str, str, str, int, int]]) -> dict[str, Any]:
    total = len(keys)
    present = [records.get(key) for key in keys]
    full_pass = sum(1 for record in present if record and record.get("full_pass") is True)
    scenario_sum = sum(score_ratio(record, "scenario_score") for record in present)
    step_sum = sum(score_ratio(record, "step_score") for record in present)
    recovered = sum(1 for record in present if record and record.get("recovered_from_previous_round") is True)
    statuses = Counter((record or {}).get("status", "missing") for record in present)
    return {
        "n": total,
        "present": sum(1 for record in present if record is not None),
        "full_pass": full_pass,
        "full_pass_ratio": full_pass / total if total else 0.0,
        "scenario_ratio_mean": scenario_sum / total if total else 0.0,
        "step_ratio_mean": step_sum / total if total else 0.0,
        "recovered": recovered,
        "statuses": dict(statuses),
    }


def completion_summary(records: dict[tuple[str, str, str, int, int], dict[str, Any]], expected_keys: list[tuple[str, str, str, int, int]]) -> dict[str, Any]:
    by_round = {}
    for round_index, label in ROUND_LABELS.items():
        keys = [key for key in expected_keys if key[-1] == round_index]
        by_round[label] = {
            "expected": len(keys),
            "present": sum(1 for key in keys if key in records),
            "missing": sum(1 for key in keys if key not in records),
        }
    by_family = {}
    for family in FAMILIES:
        by_family[family] = {}
        for round_index, label in ROUND_LABELS.items():
            keys = [key for key in expected_keys if key[0] == family and key[-1] == round_index]
            by_family[family][label] = {
                "expected": len(keys),
                "present": sum(1 for key in keys if key in records),
                "missing": sum(1 for key in keys if key not in records),
            }
    return {"by_round": by_round, "by_family": by_family}


def score_ratio(record: dict[str, Any] | None, key: str) -> float:
    if not record:
        return 0.0
    score = record.get(key)
    if not isinstance(score, dict):
        return 0.0
    value = score.get("ratio")
    return float(value) if value is not None else 0.0


def render_markdown(aggregate: dict[str, Any]) -> str:
    lines = [
        "# Public-Feedback Iterative Repair Report",
        "",
        "- Repair feedback source: public scenario execution only.",
        "- Reported evaluation: all scenarios, public plus private.",
        "- Round mapping: @1 = original blind app, @2 = first repair, @3 = second repair.",
        f"- Public-feedback audit violations: {aggregate['public_feedback_audit']['violation_count']}.",
        f"- Included records: {aggregate['included_record_count']}/{aggregate['expected_record_count']}.",
        "",
        "## Completion",
        "",
        "| Round | Present | Expected | Missing |",
        "|---|---:|---:|---:|",
    ]
    for label, row in aggregate["completion"]["by_round"].items():
        lines.append(f"| {label} | {row['present']} | {row['expected']} | {row['missing']} |")

    lines.extend([
        "",
        "## Overall Trend",
        "",
        "| Round | Full pass | S_scen | S_step | Recovered |",
        "|---|---:|---:|---:|---:|",
    ])
    for label, row in aggregate["summaries"]["overall"].items():
        lines.append(
            f"| {label} | {count_pct(row['full_pass'], row['n'])} | "
            f"{pct(row['scenario_ratio_mean'])} | {pct(row['step_ratio_mean'])} | {row['recovered']} |"
        )

    lines.extend([
        "",
        "## Target And Tier Trend",
        "",
        "| Target | Tier | Full pass @1 | Full pass @2 | Full pass @3 | S_scen @3 | S_step @3 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for family, spec in FAMILIES.items():
        for tier in TIERS:
            block = aggregate["summaries"]["by_family_tier"][family][tier]
            lines.append(
                f"| {spec['label']} | {tier} | "
                f"{count_pct(block['@1']['full_pass'], block['@1']['n'])} | "
                f"{count_pct(block['@2']['full_pass'], block['@2']['n'])} | "
                f"{count_pct(block['@3']['full_pass'], block['@3']['n'])} | "
                f"{pct(block['@3']['scenario_ratio_mean'])} | {pct(block['@3']['step_ratio_mean'])} |"
            )

    lines.extend([
        "",
        "## Model Trend",
        "",
        "| Group | Model | Full pass @1 | Full pass @2 | Full pass @3 | S_scen @3 | S_step @3 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for group, slug, label in MODELS:
        block = aggregate["summaries"]["by_model"][slug]["rounds"]
        lines.append(
            f"| {MODEL_GROUP_LABEL[group]} | {label} | "
            f"{count_pct(block['@1']['full_pass'], block['@1']['n'])} | "
            f"{count_pct(block['@2']['full_pass'], block['@2']['n'])} | "
            f"{count_pct(block['@3']['full_pass'], block['@3']['n'])} | "
            f"{pct(block['@3']['scenario_ratio_mean'])} | {pct(block['@3']['step_ratio_mean'])} |"
        )

    if aggregate["missing_record_count"] or aggregate["unexpected_record_count"] or aggregate["duplicate_record_count"]:
        lines.extend([
            "",
            "## Diagnostics",
            "",
            f"- Missing records: {aggregate['missing_record_count']}.",
            f"- Unexpected records: {aggregate['unexpected_record_count']}.",
            f"- Duplicate records ignored: {aggregate['duplicate_record_count']}.",
            f"- Scenario-set violations in included round records: {len(aggregate['diagnostics']['scenario_set_violations'])}.",
        ])
    return "\n".join(lines) + "\n"


def render_latex(aggregate: dict[str, Any]) -> str:
    lines = [
        r"\begin{table*}[!t]",
        r"\centering",
        r"\scriptsize",
        r"\caption{Public-feedback iterative repair results over the three retained A--D targets. Repair prompts use only public-scenario failure feedback; all reported metrics evaluate public and private scenarios together.}",
        r"\label{tab:public-feedback-iterative-repair}",
        r"\setlength{\tabcolsep}{2.5pt}",
        r"\renewcommand{\arraystretch}{1.18}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{@{}llccccccc@{}}",
        r"\toprule",
        r"Group & Model & Full pass & $S_{\mathrm{scen}}$ & $S_{\mathrm{step}}$ & Tier A & Tier B & Tier C & Tier D \\",
        r"\midrule[2pt]",
        r"\multicolumn{9}{@{}l}{\textit{Panel A: all-model aggregate, @1 original, @2/@3 public-feedback repairs}} \\",
    ]
    overall = aggregate["summaries"]["overall"]
    tier_blocks = aggregate["summaries"]["by_tier"]
    lines.append(
        "All & \\textbf{Complete aggregate} & "
        + latex_bold(metric_triplet_counts(overall))
        + " & "
        + latex_bold(metric_triplet_pct(overall, "scenario_ratio_mean"))
        + " & "
        + latex_bold(metric_triplet_pct(overall, "step_ratio_mean"))
        + " & "
        + " & ".join(latex_bold(metric_triplet_counts(tier_blocks[tier])) for tier in TIERS)
        + r" \\"
    )
    lines.extend([
        r"\midrule[2pt]",
        r"\multicolumn{9}{@{}l}{\textit{Panel B: model-level conformance after public-feedback repair}} \\",
    ])
    for group in ["M", "T", "F"]:
        group_label = MODEL_GROUP_LABEL[group]
        group_block = aggregate["summaries"]["by_group"][group]
        group_tiers = {
            tier: {
                label: summarize_from_model_set(aggregate, group, tier, label)
                for label in ROUND_LABELS.values()
            }
            for tier in TIERS
        }
        lines.append(
            f"\\textbf{{{latex_escape(group_label)}}} & \\textbf{{Group aggregate}} & "
            + latex_bold(metric_triplet_counts(group_block))
            + " & "
            + latex_bold(metric_triplet_pct(group_block, "scenario_ratio_mean"))
            + " & "
            + latex_bold(metric_triplet_pct(group_block, "step_ratio_mean"))
            + " & "
            + " & ".join(latex_bold(metric_triplet_counts(group_tiers[tier])) for tier in TIERS)
            + r" \\"
        )
        for model_group, slug, label in [row for row in MODELS if row[0] == group]:
            model_block = aggregate["summaries"]["by_model"][slug]
            lines.append(
                f"& {latex_escape(label)} & "
                + metric_triplet_counts(model_block["rounds"])
                + " & "
                + metric_triplet_pct(model_block["rounds"], "scenario_ratio_mean")
                + " & "
                + metric_triplet_pct(model_block["rounds"], "step_ratio_mean")
                + " & "
                + " & ".join(metric_triplet_counts(model_block["tiers"][tier]) for tier in TIERS)
                + r" \\"
            )
        if group != "F":
            lines.append(r"\midrule")
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}%",
        r"}",
        r"\end{table*}",
        "",
    ])
    return "\n".join(lines)


def summarize_from_model_set(aggregate: dict[str, Any], group: str, tier: str, round_label: str) -> dict[str, Any]:
    slugs = [slug for model_group, slug, _ in MODELS if model_group == group]
    rows = [aggregate["summaries"]["by_model"][slug]["tiers"][tier][round_label] for slug in slugs]
    n = sum(row["n"] for row in rows)
    full_pass = sum(row["full_pass"] for row in rows)
    scenario_weighted = sum(row["scenario_ratio_mean"] * row["n"] for row in rows)
    step_weighted = sum(row["step_ratio_mean"] * row["n"] for row in rows)
    return {
        "n": n,
        "present": sum(row["present"] for row in rows),
        "full_pass": full_pass,
        "full_pass_ratio": full_pass / n if n else 0.0,
        "scenario_ratio_mean": scenario_weighted / n if n else 0.0,
        "step_ratio_mean": step_weighted / n if n else 0.0,
        "recovered": sum(row["recovered"] for row in rows),
    }


def metric_triplet_counts(block: dict[str, dict[str, Any]]) -> str:
    return "; ".join(
        f"{label} {row['full_pass']}/{row['n']} ({pct_tex(row['full_pass_ratio'])})"
        for label, row in block.items()
    )


def metric_triplet_pct(block: dict[str, dict[str, Any]], key: str) -> str:
    return "; ".join(f"{label} {pct_tex(row[key])}" for label, row in block.items())


def latex_bold(value: str) -> str:
    return f"\\textbf{{{value}}}"


def count_pct(count: int, total: int) -> str:
    return f"{count}/{total} ({pct(count / total if total else 0.0)})"


def pct(value: float | None) -> str:
    return f"{(value or 0.0) * 100:.1f}%"


def pct_tex(value: float | None) -> str:
    return f"{(value or 0.0) * 100:.1f}\\%"


def latex_escape(value: str) -> str:
    return value.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")


def key_to_dict(key: tuple[str, str, str, int, int]) -> dict[str, Any]:
    family, tier, slug, seed, round_index = key
    return {
        "family": family,
        "tier": tier,
        "model_slug": slug,
        "seed": seed,
        "round": round_index,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
