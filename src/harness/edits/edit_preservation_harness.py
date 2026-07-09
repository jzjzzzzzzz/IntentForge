"""Edit preservation harness for IntentForge."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from harness.topology import inspect_shape, write_shape_inspection_report
from intentforge.editor.edit_intent_handler import apply_edit_request, write_edit_report
from intentforge.generator.cadquery_generator import build_l_bracket, build_wall_bracket, export_model
from intentforge.output_manager import create_run_context, feature_state_names, json_safe_paths
from intentforge.paths import project_root as _intentforge_project_root
from intentforge.parser import UnsupportedEditError, parse_edit_request, parse_prompt
from intentforge.schemas import ParameterTable
from intentforge.validator.geometry_validator import validate_l_bracket, validate_wall_bracket, write_validation_report

SUPPORTED_FAMILIES = {"wall_mounted_bracket", "l_bracket"}
FAILURE_TYPES = (
    "unexpected_rejection",
    "unexpected_acceptance",
    "parameter_not_changed",
    "parameter_not_preserved",
    "feature_state_mismatch",
    "validation_failure",
    "topology_failure",
    "cad_export_mismatch",
    "unexpected_exception",
)


def _project_root() -> Path:
    return _intentforge_project_root()


def _default_chain_path() -> Path:
    return Path(__file__).with_name("edit_chains.json")


def load_edit_chains(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load edit preservation chains from JSON and validate uniqueness."""

    chain_path = Path(path) if path is not None else _default_chain_path()
    with chain_path.open("r", encoding="utf-8") as handle:
        chains = json.load(handle)
    if not isinstance(chains, list):
        raise ValueError("edit chain file must contain a list of chains")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for chain in chains:
        if not isinstance(chain, dict):
            raise ValueError("each edit chain must be an object")
        for key in ("id", "object_type", "initial_prompt", "edits"):
            if key not in chain:
                raise ValueError(f"missing required chain field: {key}")
        chain_id = chain["id"]
        if not isinstance(chain_id, str) or not chain_id.strip():
            raise ValueError("chain id must be a non-empty string")
        if chain_id in seen:
            raise ValueError(f"duplicate chain id: {chain_id}")
        seen.add(chain_id)
        if chain["object_type"] not in SUPPORTED_FAMILIES:
            raise ValueError(f"unsupported edit chain family: {chain['object_type']}")
        if not isinstance(chain["initial_prompt"], str) or not chain["initial_prompt"].strip():
            raise ValueError(f"chain {chain_id} must include a non-empty initial_prompt")
        if not isinstance(chain["edits"], list) or not chain["edits"]:
            raise ValueError(f"chain {chain_id} must include a non-empty edits list")
        validated.append(chain)
    return validated


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _write_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dump(data), encoding="utf-8")
    return path


def _write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _build_model(parameter_table: ParameterTable) -> Any:
    if parameter_table.family == "l_bracket":
        return build_l_bracket(parameter_table)
    return build_wall_bracket(parameter_table)


def _validate_model(model: Any, parameter_table: ParameterTable) -> Any:
    if parameter_table.family == "l_bracket":
        return validate_l_bracket(model, parameter_table)
    return validate_wall_bracket(model, parameter_table)


def _step_dir(chain_dir: Path, step_index: int) -> Path:
    return chain_dir / f"step_{step_index:02d}"


def _canonical_names(items: list[dict[str, Any]], key: str = "canonical_parameter") -> set[str]:
    names: set[str] = set()
    for item in items:
        value = item.get(key) or item.get("parameter")
        if isinstance(value, str):
            names.add(value)
    return names


def _compare_feature_states(actual_active: list[str], actual_omitted: list[str], expected_active: list[str], expected_omitted: list[str]) -> bool:
    return set(actual_active) == set(expected_active) and set(actual_omitted) == set(expected_omitted)


def _topology_valid(topology_report: Any) -> bool:
    return bool(
        topology_report.bounding_box_dimensions_mm
        and topology_report.volume_mm3 is not None
        and topology_report.is_valid is not False
    )


def _volume_delta_ok(validation_report: Any) -> bool:
    records = validation_report.metadata.get("volume_delta_checks", [])
    return not any(record.get("status") == "fail" for record in records)


def _baseline_record(
    parameter_table: ParameterTable,
    prompt: str,
    model: Any,
    validation_report: Any,
    topology_report: Any,
) -> dict[str, Any]:
    active_features, omitted_features = feature_state_names(parameter_table)
    return {
        "prompt": prompt,
        "parameters": parameter_table.model_dump(mode="json"),
        "feature_flags": parameter_table.metadata.get("feature_flags", {}),
        "feature_plan": validation_report.metadata.get("feature_plan") if isinstance(validation_report.metadata, dict) else None,
        "validation_valid": validation_report.valid,
        "validation_summary": validation_report.summary,
        "topology": topology_report.model_dump(mode="json"),
        "active_features": active_features,
        "omitted_features": omitted_features,
    }


def _build_chain_baseline(chain: dict[str, Any]) -> tuple[ParameterTable, Any, Any, Any, dict[str, Any]]:
    parsed = parse_prompt(chain["initial_prompt"])
    if parsed.intent.family != chain["object_type"]:
        raise ValueError(
            f"chain {chain['id']} object_type mismatch: {chain['object_type']} vs parsed {parsed.intent.family}"
        )
    model = _build_model(parsed.parameter_table)
    validation_report = _validate_model(model, parsed.parameter_table)
    topology_report = inspect_shape(model, family=parsed.parameter_table.family)
    baseline = {
        "intent": parsed.intent.model_dump(mode="json"),
        "feature_plan": parsed.feature_plan.model_dump(mode="json"),
        "constraint_graph": parsed.constraint_graph.model_dump(mode="json"),
    }
    baseline.update(
        _baseline_record(
            parsed.parameter_table,
            chain["initial_prompt"],
            model,
            validation_report,
            topology_report,
        )
    )
    baseline["volume_delta_checks"] = validation_report.metadata.get("volume_delta_checks", [])
    return parsed.parameter_table, parsed.intent, parsed.feature_plan, parsed.constraint_graph, baseline


def _step_expectations(step: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str], bool]:
    return (
        step.get("expected_changed", []),
        step.get("expected_preserved", []),
        step.get("expected_active_features", []),
        step.get("expected_omitted_features", []),
        bool(step.get("expected_rejected", False)),
    )


def _step_result_template(step_index: int, text: str, expected_rejected: bool) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "text": text,
        "expected_rejected": expected_rejected,
        "parsed_edit": None,
        "accepted": False,
        "changed_parameters": [],
        "preserved_parameters": [],
        "active_features": [],
        "omitted_features": [],
        "validation_valid": None,
        "topology_valid": None,
        "topology": None,
        "volume_delta_checks": [],
        "cad_exported": False,
        "classification": "unexpected_exception",
        "failure_reason": "",
        "output_paths": {},
    }


def _compare_expected_accepted(step_result: dict[str, Any], expected_changed: list[str], expected_preserved: list[str], expected_active: list[str], expected_omitted: list[str], export_enabled: bool) -> tuple[bool, str, str]:
    changed_names = _canonical_names(step_result["changed_parameters"])
    preserved_names = {item["parameter"] for item in step_result["preserved_parameters"] if isinstance(item.get("parameter"), str)}
    if not set(expected_changed).issubset(changed_names):
        return False, "parameter_not_changed", f"missing changed parameters: {sorted(set(expected_changed) - changed_names)}"
    if not set(expected_preserved).issubset(preserved_names):
        return False, "parameter_not_preserved", f"missing preserved parameters: {sorted(set(expected_preserved) - preserved_names)}"
    if not _compare_feature_states(step_result["active_features"], step_result["omitted_features"], expected_active, expected_omitted):
        return False, "feature_state_mismatch", "feature state after edit did not match expectations"
    if step_result["validation_valid"] is not True:
        return False, "validation_failure", "regenerated edit did not validate"
    if not step_result["topology_valid"]:
        return False, "topology_failure", "topology inspection did not expose required metrics"
    if step_result["volume_delta_checks"] and any(record.get("status") == "fail" for record in step_result["volume_delta_checks"]):
        return False, "validation_failure", "volume delta checks failed"
    if export_enabled and not step_result["cad_exported"]:
        return False, "cad_export_mismatch", "expected CAD export for accepted edit"
    return True, "passed", ""


def _compare_expected_rejected(step_result: dict[str, Any], export_enabled: bool) -> tuple[bool, str, str]:
    if step_result["accepted"]:
        return False, "unexpected_acceptance", "edit was accepted but expected to be rejected"
    if step_result["changed_parameters"]:
        return False, "unexpected_acceptance", "rejected edit still reported parameter changes"
    if step_result["validation_valid"] not in {None, False}:
        return False, "unexpected_acceptance", "rejected edit should not validate"
    if step_result["cad_exported"]:
        return False, "cad_export_mismatch", "rejected edit exported CAD"
    if export_enabled and step_result["cad_exported"]:
        return False, "cad_export_mismatch", "rejected edit exported CAD"
    return True, "expected_rejection", ""


def run_edit_chain(
    chain: dict[str, Any],
    *,
    export_enabled: bool = True,
    chain_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one edit preservation chain."""

    result: dict[str, Any] = {
        "id": chain["id"],
        "object_type": chain["object_type"],
        "passed": False,
        "failure_type": "unexpected_exception",
        "failure_reason": "",
        "baseline": None,
        "steps": [],
        "step_count": 0,
        "passed_steps": 0,
        "failed_steps": 0,
    }

    try:
        current_table, _, _, _, baseline = _build_chain_baseline(chain)
    except Exception as exc:
        result["failure_reason"] = str(exc)
        return result

    result["baseline"] = baseline
    current_model = _build_model(current_table)
    current_active, current_omitted = feature_state_names(current_table)

    chain_failed = False
    chain_failure_type = "passed"
    chain_failure_reason = ""
    step_results: list[dict[str, Any]] = []

    if chain_dir is not None:
        chain_dir.mkdir(parents=True, exist_ok=True)
        _write_json(baseline, chain_dir / "baseline.json")

    for index, step in enumerate(chain["edits"], start=1):
        step_text = step["text"]
        expected_changed, expected_preserved, expected_active, expected_omitted, expected_rejected = _step_expectations(step)
        step_result = _step_result_template(index, step_text, expected_rejected)
        step_dir = _step_dir(chain_dir, index) if chain_dir is not None else None

        try:
            parsed_edit = parse_edit_request(
                step_text,
                existing_params=current_table,
                existing_feature_flags=current_table.metadata.get("feature_flags"),
            )
            step_result["parsed_edit"] = parsed_edit
        except UnsupportedEditError as exc:
            step_result["parsed_edit"] = {
                "edits": [],
                "preserve": [],
                "warnings": [str(exc)],
                "assumptions": [],
                "rejected": True,
                "error": str(exc),
            }
            step_result["active_features"] = current_active
            step_result["omitted_features"] = current_omitted
            if expected_rejected:
                step_result["accepted"] = False
                ok, failure_type, failure_reason = _compare_expected_rejected(step_result, export_enabled)
                if ok and not _compare_feature_states(
                    current_active,
                    current_omitted,
                    expected_active,
                    expected_omitted,
                ):
                    ok = False
                    failure_type = "feature_state_mismatch"
                    failure_reason = "rejected edit changed feature state unexpectedly"
                step_result["classification"], step_result["failure_reason"] = failure_type, failure_reason
                if not ok:
                    chain_failed = True
                    chain_failure_type = failure_type
                    chain_failure_reason = failure_reason
                step_results.append(step_result)
                if step_dir is not None:
                    _write_json(step_result["parsed_edit"], step_dir / "parsed_edit.json")
            else:
                step_result["classification"] = "unexpected_rejection"
                step_result["failure_reason"] = str(exc)
                chain_failed = True
                chain_failure_type = "unexpected_rejection"
                chain_failure_reason = str(exc)
                step_results.append(step_result)
            continue

        try:
            edit_report = apply_edit_request(current_table, parsed_edit, current_table.metadata.get("constraints"))
            step_result["accepted"] = bool(edit_report.accepted)
            step_result["changed_parameters"] = edit_report.changed_parameters
            step_result["preserved_parameters"] = edit_report.preserved_parameters
            if edit_report.accepted:
                updated_table = ParameterTable.model_validate(edit_report.metadata["updated_parameter_table"])
                current_table = updated_table
                current_model = _build_model(current_table)
                current_active, current_omitted = feature_state_names(current_table)
                step_result["active_features"] = current_active
                step_result["omitted_features"] = current_omitted
                validation_report = edit_report.validation_report or _validate_model(current_model, current_table)
                topology_report = inspect_shape(current_model, family=current_table.family)
                step_result["validation_valid"] = validation_report.valid
                step_result["topology"] = topology_report.model_dump(mode="json")
                step_result["topology_valid"] = _topology_valid(topology_report)
                step_result["volume_delta_checks"] = validation_report.metadata.get("volume_delta_checks", [])
                if chain_dir is not None:
                    _write_json(edit_report.model_dump(mode="json"), step_dir / "edit_report.json")
                    _write_json(validation_report.model_dump(mode="json"), step_dir / "validation_report.json")
                    write_shape_inspection_report(topology_report, step_dir / "topology_report.json")
                if export_enabled and step_dir is not None:
                    step_step = step_dir / f"{chain['id']}_step_{index:02d}.step"
                    step_stl = step_dir / f"{chain['id']}_step_{index:02d}.stl"
                    export_model(current_model, step_step, step_stl)
                    step_result["cad_exported"] = True
                    step_result["output_paths"] = {"step": str(step_step), "stl": str(step_stl)}
                else:
                    step_result["cad_exported"] = False
                ok, failure_type, failure_reason = _compare_expected_accepted(
                    step_result,
                    expected_changed,
                    expected_preserved,
                    expected_active,
                    expected_omitted,
                    export_enabled=export_enabled and step_dir is not None,
                )
                step_result["classification"] = failure_type
                step_result["failure_reason"] = failure_reason
                if not ok:
                    chain_failed = True
                    chain_failure_type = failure_type
                    chain_failure_reason = failure_reason
            else:
                step_result["active_features"] = current_active
                step_result["omitted_features"] = current_omitted
                if chain_dir is not None:
                    _write_json(edit_report.model_dump(mode="json"), step_dir / "edit_report.json")
                if expected_rejected:
                    ok, failure_type, failure_reason = _compare_expected_rejected(step_result, export_enabled)
                    step_result["classification"] = failure_type
                    step_result["failure_reason"] = failure_reason
                    if not ok:
                        chain_failed = True
                        chain_failure_type = failure_type
                        chain_failure_reason = failure_reason
                else:
                    step_result["classification"] = "unexpected_rejection"
                    step_result["failure_reason"] = "edit was rejected"
                    chain_failed = True
                    chain_failure_type = "unexpected_rejection"
                    chain_failure_reason = "edit was rejected"
        except Exception as exc:  # pragma: no cover - CAD/kernel failures vary
            step_result["classification"] = "unexpected_exception"
            step_result["failure_reason"] = str(exc)
            chain_failed = True
            chain_failure_type = "unexpected_exception"
            chain_failure_reason = str(exc)

        step_result["active_features"] = current_active
        step_result["omitted_features"] = current_omitted
        step_results.append(step_result)
        if chain_dir is not None:
            _write_json(step_result, step_dir / "step_result.json")

    result["steps"] = step_results
    result["step_count"] = len(step_results)
    result["passed_steps"] = sum(1 for step in step_results if step["classification"] in {"passed", "expected_rejection"})
    result["failed_steps"] = result["step_count"] - result["passed_steps"]
    result["passed"] = not chain_failed
    result["failure_type"] = chain_failure_type if chain_failed else "passed"
    result["failure_reason"] = chain_failure_reason
    return result


def _summary_text(report: dict[str, Any]) -> str:
    lines = [
        f"Edit preservation run: {report['run_id']}",
        f"Total chains: {report['total_chains']}",
        f"Passed chains: {report['passed_chains']}",
        f"Failed chains: {report['failed_chains']}",
        f"Total edit steps: {report['total_edit_steps']}",
        f"Passed steps: {report['passed_steps']}",
        f"Failed steps: {report['failed_steps']}",
        f"Edit preservation rate: {report['edit_preservation_rate']:.4f}",
        "Families:",
    ]
    for family, counts in report["families"].items():
        lines.append(f"  - {family}: passed {counts['passed']}, failed {counts['failed']}, total {counts['total']}")
    lines.append("Failure types:")
    for failure_type, count in report["failure_types"].items():
        lines.append(f"  - {failure_type}: {count}")
    if report["failed_chain_ids"]:
        lines.append("Failed chain IDs:")
        for chain_id, chain in zip(report["failed_chain_ids"], report["failed_chain_details"], strict=False):
            lines.append(f"  - {chain_id}: {chain['failure_type']} - {chain['failure_reason']}")
    else:
        lines.append("Failed chain IDs: none")
    return "\n".join(lines) + "\n"


def run_edit_preservation_harness(
    output_root: str | Path,
    *,
    max_chains: int | None = None,
    export_enabled: bool = True,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run the edit preservation harness across a deterministic chain set."""

    output_path = Path(output_root)
    harness_root = output_path / "harness"
    run_context = create_run_context("edit preservation harness", harness_root, "edit_preservation_runs")
    chains = load_edit_chains(config_path)
    if max_chains is not None:
        chains = chains[:max(0, max_chains)]

    chain_results: list[dict[str, Any]] = []
    for chain in chains:
        chain_dir = run_context.run_dir / "chains" / chain["id"]
        result = run_edit_chain(chain, export_enabled=export_enabled, chain_dir=chain_dir)
        chain_results.append(result)

    passed_chains = [chain for chain in chain_results if chain["passed"]]
    failed_chains = [chain for chain in chain_results if not chain["passed"]]
    total_edit_steps = sum(chain["step_count"] for chain in chain_results)
    passed_steps = sum(chain["passed_steps"] for chain in chain_results)
    failed_steps = total_edit_steps - passed_steps
    families: dict[str, dict[str, int]] = {}
    for family in ("wall_mounted_bracket", "l_bracket"):
        family_chains = [chain for chain in chain_results if chain["object_type"] == family]
        families[family] = {
            "total": len(family_chains),
            "passed": sum(1 for chain in family_chains if chain["passed"]),
            "failed": sum(1 for chain in family_chains if not chain["passed"]),
        }

    failure_counts = Counter()
    for chain in chain_results:
        for step in chain["steps"]:
            if step["classification"] in FAILURE_TYPES:
                failure_counts[step["classification"]] += 1
    for chain in failed_chains:
        if chain["failure_type"] in FAILURE_TYPES and not any(
            step["classification"] == chain["failure_type"] for step in chain["steps"]
        ):
            failure_counts[chain["failure_type"]] += 1

    failure_types = {failure_type: failure_counts.get(failure_type, 0) for failure_type in FAILURE_TYPES}
    report: dict[str, Any] = {
        "run_id": run_context.run_id,
        "total_chains": len(chain_results),
        "passed_chains": len(passed_chains),
        "failed_chains": len(failed_chains),
        "total_edit_steps": total_edit_steps,
        "passed_steps": passed_steps,
        "failed_steps": failed_steps,
        "edit_preservation_rate": passed_steps / total_edit_steps if total_edit_steps else 0.0,
        "families": families,
        "failure_types": failure_types,
        "export_enabled": export_enabled,
        "chains": chain_results,
        "passed_chain_details": passed_chains,
        "failed_chain_details": failed_chains,
        "passed_chain_ids": [chain["id"] for chain in passed_chains],
        "failed_chain_ids": [chain["id"] for chain in failed_chains],
    }

    latest_report_path = harness_root / "edit_preservation_report.json"
    latest_summary_path = harness_root / "edit_preservation_summary.txt"
    persistent_report_path = run_context.run_dir / "edit_preservation_report.json"
    persistent_summary_path = run_context.run_dir / "edit_preservation_summary.txt"
    passed_chains_path = run_context.run_dir / "passed_chains.json"
    failed_chains_path = run_context.run_dir / "failed_chains.json"
    output_paths = {
        "latest_report": latest_report_path,
        "latest_summary": latest_summary_path,
        "persistent_report": persistent_report_path,
        "persistent_summary": persistent_summary_path,
        "passed_chains": passed_chains_path,
        "failed_chains": failed_chains_path,
    }
    report["output_paths"] = json_safe_paths(output_paths)

    summary = _summary_text(report)
    _write_json(report, latest_report_path)
    _write_text(summary, latest_summary_path)
    _write_json(report, persistent_report_path)
    _write_text(summary, persistent_summary_path)
    _write_json(passed_chains, passed_chains_path)
    _write_json(failed_chains, failed_chains_path)

    return {
        **report,
        "report_path": str(latest_report_path),
        "summary_path": str(latest_summary_path),
        "persistent_output_dir": str(run_context.run_dir),
        "summary": summary,
    }
