"""Shared IntentForge workflows for CLI and MCP wrappers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from intentforge.editor.edit_intent_handler import apply_edit_request, write_edit_report
from intentforge.contracts import apply_response_contract, ensure_request_id, error_response
from intentforge.features import feature_flags_for_parameter_table
from intentforge.generator.cadquery_generator import (
    CadQueryUnavailableError,
    build_l_bracket,
    build_wall_bracket,
    export_model,
)
from intentforge.output_manager import (
    build_run_metadata,
    create_parsed_run_context,
    create_run_context,
    feature_state_names,
    json_safe_paths,
    write_run_metadata,
)
from intentforge.parser import UnsupportedEditError, UnsupportedObjectError, parse_edit_request, parse_prompt
from intentforge.schemas import ConstraintGraph, FeaturePlan, IntentSpec, ParameterTable, ValidationReport
from intentforge.validator.geometry_validator import validate_l_bracket, validate_wall_bracket, write_validation_report
from intentforge.validator.intent_validator import validate_l_bracket_intent, validate_wall_bracket_intent

SUPPORTED_RUN_KINDS = {"parsed_runs", "edit_parse_runs"}


def project_root() -> Path:
    """Return the repository root for bundled examples and default output."""

    return Path(__file__).resolve().parents[1]


def default_output_root() -> Path:
    """Return the default output directory."""

    return project_root() / "output"


def _output_root(output_root: str | Path | None = None) -> Path:
    return Path(output_root) if output_root is not None else default_output_root()


def _examples_dir() -> Path:
    return project_root() / "examples"


def _load_bracket_parameters() -> ParameterTable:
    return ParameterTable.model_validate(
        yaml.safe_load((_examples_dir() / "bracket_params.yaml").read_text(encoding="utf-8"))
    )


def _load_l_bracket_parameters() -> ParameterTable:
    return ParameterTable.model_validate(
        yaml.safe_load((_examples_dir() / "l_bracket_params.yaml").read_text(encoding="utf-8"))
    )


def _load_json_example(filename: str) -> dict[str, Any]:
    return json.loads((_examples_dir() / filename).read_text(encoding="utf-8"))


def _load_bracket_intent() -> IntentSpec:
    return IntentSpec.model_validate(_load_json_example("bracket_intent.json"))


def _load_l_bracket_intent() -> IntentSpec:
    return IntentSpec.model_validate(_load_json_example("l_bracket_intent.json"))


def _load_bracket_feature_plan() -> FeaturePlan:
    return FeaturePlan.model_validate(_load_json_example("bracket_feature_plan.json"))


def _load_l_bracket_feature_plan() -> FeaturePlan:
    return FeaturePlan.model_validate(_load_json_example("l_bracket_feature_plan.json"))


def _load_bracket_constraints() -> ConstraintGraph:
    return ConstraintGraph.model_validate(_load_json_example("bracket_constraints.json"))


def _load_l_bracket_constraints() -> ConstraintGraph:
    return ConstraintGraph.model_validate(_load_json_example("l_bracket_constraints.json"))


def _example_bundle(target: str) -> tuple[ParameterTable, IntentSpec, FeaturePlan, ConstraintGraph]:
    if target == "bracket":
        return (
            _load_bracket_parameters(),
            _load_bracket_intent(),
            _load_bracket_feature_plan(),
            _load_bracket_constraints(),
        )
    if target == "l_bracket":
        return (
            _load_l_bracket_parameters(),
            _load_l_bracket_intent(),
            _load_l_bracket_feature_plan(),
            _load_l_bracket_constraints(),
        )
    raise ValueError(f"unsupported target: {target}")


def _build_model(parameter_table: ParameterTable, feature_plan: FeaturePlan | None = None) -> Any:
    if parameter_table.family == "l_bracket":
        return build_l_bracket(parameter_table, feature_plan)
    return build_wall_bracket(parameter_table)


def _validate_geometry(model: object, parameter_table: ParameterTable, output_paths: dict[str, Path] | None = None) -> ValidationReport:
    if parameter_table.family == "l_bracket":
        return validate_l_bracket(model, parameter_table, output_paths=output_paths)
    return validate_wall_bracket(model, parameter_table, output_paths=output_paths)


def _validate_intent(
    intent: IntentSpec,
    parameter_table: ParameterTable,
    feature_plan: FeaturePlan,
    constraint_graph: ConstraintGraph,
) -> ValidationReport:
    if intent.family == "l_bracket":
        return validate_l_bracket_intent(intent, parameter_table, feature_plan, constraint_graph)
    return validate_wall_bracket_intent(intent, parameter_table, feature_plan, constraint_graph)


def _parsed_cad_basename(family: str) -> str:
    return "parsed_l_bracket" if family == "l_bracket" else "parsed_bracket"


def _edited_cad_basename(family: str) -> str:
    return "l_bracket_edited" if family == "l_bracket" else "bracket_edited"


def _parsed_validation_report_name(family: str) -> str:
    return "parsed_l_bracket_validation_report.json" if family == "l_bracket" else "parsed_validation_report.json"


def _edited_validation_report_name(family: str) -> str:
    return "l_bracket_edited_validation_report.json" if family == "l_bracket" else "edited_validation_report.json"


def _write_parameter_table(parameter_table: ParameterTable, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(parameter_table.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return path


def _write_json_model(model: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_json_data(data: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _parsed_output_paths(base_dir: Path) -> dict[str, Path]:
    return {
        "intent": base_dir / "parsed_intent.json",
        "params": base_dir / "parsed_params.yaml",
        "constraints": base_dir / "parsed_constraints.json",
        "feature_plan": base_dir / "parsed_feature_plan.json",
    }


def _parsed_run_output_paths(run_dir: Path) -> dict[str, Path]:
    return {
        **_parsed_output_paths(run_dir),
        "prompt": run_dir / "prompt.txt",
        "run_metadata": run_dir / "run_metadata.json",
    }


def _write_parsed_outputs(parsed: Any, prompt: str, output_root: Path, run_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    latest_paths = _parsed_output_paths(output_root)
    compatibility_paths = _parsed_output_paths(output_root / "parsed")
    persistent_paths = _parsed_run_output_paths(run_dir)

    for paths in (latest_paths, compatibility_paths, persistent_paths):
        _write_json_model(parsed.intent, paths["intent"])
        _write_parameter_table(parsed.parameter_table, paths["params"])
        _write_json_model(parsed.constraint_graph, paths["constraints"])
        _write_json_model(parsed.feature_plan, paths["feature_plan"])

    persistent_paths["prompt"].write_text(prompt + "\n", encoding="utf-8")
    return latest_paths, persistent_paths


def _edit_parse_output_paths(output_root: Path, run_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    latest_paths = {"parsed_edit": output_root / "parsed_edit.json"}
    persistent_paths = {
        "parsed_edit": run_dir / "parsed_edit.json",
        "prompt": run_dir / "prompt.txt",
        "run_metadata": run_dir / "run_metadata.json",
    }
    return latest_paths, persistent_paths


def _write_edit_parse_outputs(
    parsed_edit: dict[str, Any],
    edit_text: str,
    latest_paths: dict[str, Path],
    persistent_paths: dict[str, Path],
) -> None:
    _write_json_data(parsed_edit, latest_paths["parsed_edit"])
    _write_json_data(parsed_edit, persistent_paths["parsed_edit"])
    persistent_paths["prompt"].write_text(edit_text + "\n", encoding="utf-8")


def _edit_run_metadata(
    *,
    run_context: Any,
    command_type: str,
    edit_text: str,
    parsed_edit: dict[str, Any],
    output_paths: dict[str, Any],
    request_id: str | None = None,
    accepted: bool | None = None,
    validation_valid: bool | None = None,
    object_type: str | None = None,
    active_features: list[str] | None = None,
    omitted_features: list[str] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "run_id": run_context.run_id,
        "request_id": request_id,
        "command_type": command_type,
        "original_edit_text": edit_text,
        "created_at": run_context.created_at.isoformat(),
        "parsed_edits": parsed_edit.get("edits", []),
        "preserve": parsed_edit.get("preserve", []),
        "assumptions": parsed_edit.get("assumptions", []),
        "warnings": parsed_edit.get("warnings", []),
        "output_paths": json_safe_paths(output_paths),
    }
    if accepted is not None:
        metadata["accepted"] = accepted
    if validation_valid is not None:
        metadata["validation_valid"] = validation_valid
    if object_type is not None:
        metadata["object_type"] = object_type
    if active_features is not None:
        metadata["active_features"] = active_features
    if omitted_features is not None:
        metadata["omitted_features"] = omitted_features
    return metadata


def _combine_reports(geometry_report: ValidationReport, intent_report: ValidationReport) -> ValidationReport:
    checks = [*geometry_report.checks, *intent_report.checks]
    failed_count = sum(1 for check in checks if check.status == "fail")
    warning_count = sum(1 for check in checks if check.status == "warning")
    passed_count = sum(1 for check in checks if check.status in {"pass", "warning"})
    summary = (
        f"Validation completed: {passed_count}/{len(checks)} checks passed, "
        f"{failed_count} failed, {warning_count} warnings."
    )
    return ValidationReport(
        family=geometry_report.family,
        checks=checks,
        summary=summary,
        metadata={
            "geometry_summary": geometry_report.summary,
            "intent_summary": intent_report.summary,
        },
    )


def _needs_export(step_path: Path, stl_path: Path) -> bool:
    return not (
        step_path.exists()
        and stl_path.exists()
        and step_path.stat().st_size > 0
        and stl_path.stat().st_size > 0
    )


def _paths_for_json(paths: dict[str, Any]) -> dict[str, Any]:
    return json_safe_paths(paths)


def parse_prompt_workflow(
    prompt: str,
    output_root: str | Path | None = None,
    *,
    write_outputs: bool = False,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Parse a CAD prompt and optionally write traceable parsed artifacts."""

    request_id = ensure_request_id(request_id)
    try:
        parsed = parse_prompt(prompt)
    except UnsupportedObjectError as exc:
        return error_response(
            operation="parse",
            request_id=request_id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            recoverable=True,
        )
    active_features, omitted_features = feature_state_names(parsed.parameter_table)
    result: dict[str, Any] = {
        "ok": True,
        "intent": parsed.intent.model_dump(mode="json"),
        "parameters": parsed.parameter_table.model_dump(mode="json"),
        "constraints": parsed.constraint_graph.model_dump(mode="json"),
        "feature_plan": parsed.feature_plan.model_dump(mode="json"),
        "warnings": parsed.warnings,
        "assumptions": parsed.intent.assumptions,
        "unknowns": parsed.intent.unknowns,
        "active_features": active_features,
        "omitted_features": omitted_features,
    }
    if not write_outputs:
        return apply_response_contract(
            result,
            operation="parse",
            request_id=request_id,
            object_type=parsed.intent.family,
        )

    out_root = _output_root(output_root)
    run_context = create_parsed_run_context(prompt, out_root)
    latest_paths, persistent_paths = _write_parsed_outputs(parsed, prompt, out_root, run_context.run_dir)
    metadata = build_run_metadata(
        run_context=run_context,
        command_type="parse",
        prompt=prompt,
        object_type=parsed.intent.family,
        active_features=active_features,
        omitted_features=omitted_features,
        warnings=parsed.warnings,
        output_paths={"latest": latest_paths, "persistent": persistent_paths},
    )
    metadata["request_id"] = request_id
    write_run_metadata(metadata, persistent_paths["run_metadata"])
    result.update(
        {
            "run_id": run_context.run_id,
            "latest_outputs": _paths_for_json(latest_paths),
            "persistent_outputs": _paths_for_json(persistent_paths),
            "persistent_output_dir": str(run_context.run_dir),
            "run_metadata": metadata,
        }
    )
    return apply_response_contract(
        result,
        operation="parse",
        request_id=request_id,
        object_type=parsed.intent.family,
    )


def parse_build_workflow(
    prompt: str,
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Parse a prompt, build CAD, export latest and persistent files, and validate."""

    request_id = ensure_request_id(request_id)
    out_root = _output_root(output_root)
    try:
        parsed = parse_prompt(prompt)
    except UnsupportedObjectError as exc:
        return error_response(
            operation="parse_build",
            request_id=request_id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            recoverable=True,
        )
    run_context = create_parsed_run_context(prompt, out_root)
    latest_paths, persistent_paths = _write_parsed_outputs(parsed, prompt, out_root, run_context.run_dir)
    active_features, omitted_features = feature_state_names(parsed.parameter_table)

    try:
        model = _build_model(parsed.parameter_table, parsed.feature_plan)
    except CadQueryUnavailableError as exc:
        return error_response(
            operation="parse_build",
            request_id=request_id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            recoverable=True,
            object_type=parsed.intent.family,
            run_id=run_context.run_id,
        )
    cad_basename = _parsed_cad_basename(parsed.parameter_table.family)
    step_path = out_root / f"{cad_basename}.step"
    stl_path = out_root / f"{cad_basename}.stl"
    persistent_step_path = run_context.run_dir / f"{cad_basename}.step"
    persistent_stl_path = run_context.run_dir / f"{cad_basename}.stl"
    planned_cad_paths = {
        "latest_step": step_path,
        "latest_stl": stl_path,
        "persistent_step": persistent_step_path,
        "persistent_stl": persistent_stl_path,
    }
    if not dry_run:
        export_model(model, step_path, stl_path)
        export_model(model, persistent_step_path, persistent_stl_path)
        latest_paths = {**latest_paths, "step": step_path, "stl": stl_path}
        persistent_paths = {**persistent_paths, "step": persistent_step_path, "stl": persistent_stl_path}

    validation_report = _validate_geometry(
        model,
        parsed.parameter_table,
        output_paths=None if dry_run else {"step": step_path, "stl": stl_path},
    )
    validation_filename = _parsed_validation_report_name(parsed.parameter_table.family)
    validation_path = out_root / validation_filename
    persistent_validation_path = run_context.run_dir / validation_filename
    shared_validation_path = out_root / "parsed_validation_report.json"
    latest_paths["validation_report"] = validation_path
    persistent_paths["validation_report"] = persistent_validation_path
    if validation_path != shared_validation_path:
        latest_paths["shared_validation_report"] = shared_validation_path
    validation_report = validation_report.model_copy(
        update={
            "metadata": {
                **validation_report.metadata,
                "command": "parse-build",
                "run_id": run_context.run_id,
                "request_id": request_id,
                "parsed_prompt": prompt,
                "dry_run": dry_run,
                "cad_exported": not dry_run,
                "planned_cad_paths": _paths_for_json(planned_cad_paths),
                "step_path": None if dry_run else str(step_path),
                "stl_path": None if dry_run else str(stl_path),
                "persistent_step_path": None if dry_run else str(persistent_step_path),
                "persistent_stl_path": None if dry_run else str(persistent_stl_path),
                "shared_validation_report_path": str(shared_validation_path),
                "persistent_validation_report_path": str(persistent_validation_path),
            }
        }
    )
    write_validation_report(validation_report, validation_path)
    if validation_path != shared_validation_path:
        write_validation_report(validation_report, shared_validation_path)
    write_validation_report(validation_report, persistent_validation_path)

    metadata = build_run_metadata(
        run_context=run_context,
        command_type="parse-build",
        prompt=prompt,
        object_type=parsed.intent.family,
        active_features=active_features,
        omitted_features=omitted_features,
        warnings=parsed.warnings,
        validation_valid=validation_report.valid,
        output_paths={"latest": latest_paths, "persistent": persistent_paths},
    )
    metadata["request_id"] = request_id
    metadata["dry_run"] = dry_run
    metadata["cad_exported"] = not dry_run
    metadata["planned_cad_paths"] = _paths_for_json(planned_cad_paths)
    write_run_metadata(metadata, persistent_paths["run_metadata"])

    result = {
        "ok": validation_report.valid,
        "run_id": run_context.run_id,
        "object_type": parsed.intent.family,
        "intent": parsed.intent.model_dump(mode="json"),
        "parameters": parsed.parameter_table.model_dump(mode="json"),
        "constraints": parsed.constraint_graph.model_dump(mode="json"),
        "feature_plan": parsed.feature_plan.model_dump(mode="json"),
        "warnings": parsed.warnings,
        "assumptions": parsed.intent.assumptions,
        "unknowns": parsed.intent.unknowns,
        "validation_valid": validation_report.valid,
        "validation_report": validation_report.model_dump(mode="json"),
        "cad_exported": not dry_run,
        "dry_run": dry_run,
        "latest_outputs": _paths_for_json(latest_paths),
        "persistent_outputs": _paths_for_json(persistent_paths),
        "planned_outputs": _paths_for_json(planned_cad_paths),
        "persistent_output_dir": str(run_context.run_dir),
        "active_features": active_features,
        "omitted_features": omitted_features,
        "run_metadata": metadata,
    }
    if not validation_report.valid:
        result["error_type"] = "ValidationFailedError"
        result["message"] = validation_report.summary
    return apply_response_contract(
        result,
        operation="parse_build",
        request_id=request_id,
        object_type=parsed.intent.family,
        validation_report=validation_report,
        dry_run=dry_run,
    )


def _parse_edit_text(edit_text: str, parameter_table: ParameterTable | None = None) -> tuple[dict[str, Any], bool]:
    try:
        return parse_edit_request(edit_text, existing_params=parameter_table), True
    except UnsupportedEditError as exc:
        return {
            "edits": [],
            "preserve": [],
            "warnings": [str(exc)],
            "assumptions": [],
            "rejected": True,
            "error": str(exc),
        }, False


def edit_parse_workflow(
    edit_text: str,
    output_root: str | Path | None = None,
    *,
    write_outputs: bool = False,
    parameter_table: ParameterTable | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Parse a natural-language edit and optionally write trace outputs."""

    request_id = ensure_request_id(request_id)
    parsed_edit, parsed_ok = _parse_edit_text(edit_text, parameter_table)
    result: dict[str, Any] = {
        "ok": parsed_ok,
        "edit_request": parsed_edit,
        "warnings": parsed_edit.get("warnings", []),
        "assumptions": parsed_edit.get("assumptions", []),
    }
    if not parsed_ok:
        result.update(
            {
                "error_type": "UnsupportedEditError",
                "message": parsed_edit.get("error", "Unsupported edit request."),
                "cad_exported": False,
            }
        )
    if not write_outputs:
        return apply_response_contract(
            result,
            operation="edit_parse",
            request_id=request_id,
        )

    out_root = _output_root(output_root)
    run_context = create_run_context(edit_text, out_root, "edit_parse_runs")
    latest_paths, persistent_paths = _edit_parse_output_paths(out_root, run_context.run_dir)
    _write_edit_parse_outputs(parsed_edit, edit_text, latest_paths, persistent_paths)
    metadata = _edit_run_metadata(
        run_context=run_context,
        command_type="edit-parse",
        edit_text=edit_text,
        parsed_edit=parsed_edit,
        request_id=request_id,
        accepted=parsed_ok,
        output_paths={"latest": latest_paths, "persistent": persistent_paths},
    )
    write_run_metadata(metadata, persistent_paths["run_metadata"])
    result.update(
        {
            "run_id": run_context.run_id,
            "latest_outputs": _paths_for_json(latest_paths),
            "persistent_outputs": _paths_for_json(persistent_paths),
            "persistent_output_dir": str(run_context.run_dir),
            "run_metadata": metadata,
        }
    )
    return apply_response_contract(
        result,
        operation="edit_parse",
        request_id=request_id,
    )


def edit_parse_apply_workflow(
    target: str,
    edit_text: str,
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Parse and apply a natural-language edit to the bundled bracket example."""

    request_id = ensure_request_id(request_id)
    if target not in {"bracket", "l_bracket"}:
        result = error_response(
            operation="edit_parse_apply",
            request_id=request_id,
            error_type="ValueError",
            message=f"unsupported target: {target}",
            recoverable=True,
        )
        result["accepted"] = False
        return result

    out_root = _output_root(output_root)
    parameter_table, _, _, constraint_graph = _example_bundle(target)
    original_active_features, original_omitted_features = feature_state_names(parameter_table)
    run_context = create_run_context(edit_text, out_root, "edit_parse_runs")
    latest_paths, persistent_paths = _edit_parse_output_paths(out_root, run_context.run_dir)

    parsed_edit, parsed_ok = _parse_edit_text(edit_text, parameter_table)
    _write_edit_parse_outputs(parsed_edit, edit_text, latest_paths, persistent_paths)
    if not parsed_ok:
        latest_edit_report_path = out_root / "edit_report.json"
        persistent_edit_report_path = run_context.run_dir / "edit_report.json"
        latest_paths["edit_report"] = latest_edit_report_path
        persistent_paths["edit_report"] = persistent_edit_report_path
        edit_report = {
            "family": parameter_table.family,
            "accepted": False,
            "changed_parameters": [],
            "preserved_parameters": [],
            "rejected_edits": [
                {
                    "edit_text": edit_text,
                    "reason": parsed_edit.get("error", "Unsupported edit request."),
                }
            ],
            "failed_constraints": [],
            "validation_summary": "Edit rejected before geometry regeneration.",
            "human_readable_explanation": parsed_edit.get("error", "Unsupported edit request."),
            "metadata": {
                "command": f"edit-parse-apply {target}",
                "run_id": run_context.run_id,
                "request_id": request_id,
                "original_edit_text": edit_text,
                "cad_exported": False,
                "dry_run": dry_run,
            },
        }
        _write_json_data(edit_report, latest_edit_report_path)
        _write_json_data(edit_report, persistent_edit_report_path)
        metadata = _edit_run_metadata(
            run_context=run_context,
            command_type="edit-parse-apply",
            edit_text=edit_text,
            parsed_edit=parsed_edit,
            request_id=request_id,
            accepted=False,
            object_type=parameter_table.family,
            active_features=original_active_features,
            omitted_features=original_omitted_features,
            output_paths={"latest": latest_paths, "persistent": persistent_paths},
        )
        write_run_metadata(metadata, persistent_paths["run_metadata"])
        result = {
            "ok": False,
            "accepted": False,
            "run_id": run_context.run_id,
            "object_type": parameter_table.family,
            "error_type": "UnsupportedEditError",
            "message": parsed_edit.get("error", "Unsupported edit request."),
            "edit_request": parsed_edit,
            "edit_report": edit_report,
            "cad_exported": False,
            "latest_outputs": _paths_for_json(latest_paths),
            "persistent_outputs": _paths_for_json(persistent_paths),
            "persistent_output_dir": str(run_context.run_dir),
            "run_metadata": metadata,
        }
        return apply_response_contract(
            result,
            operation="edit_parse_apply",
            request_id=request_id,
            object_type=parameter_table.family,
            dry_run=dry_run,
        )

    edit_report = apply_edit_request(parameter_table, parsed_edit, constraint_graph)
    latest_edit_report_path = out_root / "edit_report.json"
    persistent_edit_report_path = run_context.run_dir / "edit_report.json"
    latest_paths["edit_report"] = latest_edit_report_path
    persistent_paths["edit_report"] = persistent_edit_report_path

    if not edit_report.accepted:
        edit_report = edit_report.model_copy(
            update={
                "metadata": {
                    **edit_report.metadata,
                    "command": f"edit-parse-apply {target}",
                    "run_id": run_context.run_id,
                    "request_id": request_id,
                    "original_edit_text": edit_text,
                    "latest_edit_report_path": str(latest_edit_report_path),
                    "persistent_edit_report_path": str(persistent_edit_report_path),
                    "cad_exported": False,
                    "dry_run": dry_run,
                }
            }
        )
        write_edit_report(edit_report, latest_edit_report_path)
        write_edit_report(edit_report, persistent_edit_report_path)
        metadata = _edit_run_metadata(
            run_context=run_context,
            command_type="edit-parse-apply",
            edit_text=edit_text,
            parsed_edit=parsed_edit,
            request_id=request_id,
            accepted=False,
            object_type=parameter_table.family,
            active_features=original_active_features,
            omitted_features=original_omitted_features,
            output_paths={"latest": latest_paths, "persistent": persistent_paths},
        )
        write_run_metadata(metadata, persistent_paths["run_metadata"])
        result = {
            "ok": False,
            "accepted": False,
            "run_id": run_context.run_id,
            "object_type": parameter_table.family,
            "error_type": "EditRejected",
            "message": edit_report.human_readable_explanation,
            "edit_request": parsed_edit,
            "edit_report": edit_report.model_dump(mode="json"),
            "cad_exported": False,
            "latest_outputs": _paths_for_json(latest_paths),
            "persistent_outputs": _paths_for_json(persistent_paths),
            "persistent_output_dir": str(run_context.run_dir),
            "run_metadata": metadata,
        }
        return apply_response_contract(
            result,
            operation="edit_parse_apply",
            request_id=request_id,
            object_type=parameter_table.family,
            dry_run=dry_run,
        )

    updated_table = ParameterTable.model_validate(edit_report.metadata["updated_parameter_table"])
    latest_updated_params_path = out_root / "updated_params.yaml"
    persistent_updated_params_path = run_context.run_dir / "updated_params.yaml"
    latest_paths["updated_params"] = latest_updated_params_path
    persistent_paths["updated_params"] = persistent_updated_params_path
    _write_parameter_table(updated_table, latest_updated_params_path)
    _write_parameter_table(updated_table, persistent_updated_params_path)

    try:
        model = _build_model(updated_table)
    except CadQueryUnavailableError as exc:
        return error_response(
            operation="edit_parse_apply",
            request_id=request_id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            recoverable=True,
            object_type=updated_table.family,
            run_id=run_context.run_id,
        )
    cad_basename = _edited_cad_basename(updated_table.family)
    latest_step_path = out_root / f"{cad_basename}.step"
    latest_stl_path = out_root / f"{cad_basename}.stl"
    persistent_step_path = run_context.run_dir / f"{cad_basename}.step"
    persistent_stl_path = run_context.run_dir / f"{cad_basename}.stl"
    planned_cad_paths = {
        "latest_step": latest_step_path,
        "latest_stl": latest_stl_path,
        "persistent_step": persistent_step_path,
        "persistent_stl": persistent_stl_path,
    }
    if not dry_run:
        latest_paths["step"] = latest_step_path
        latest_paths["stl"] = latest_stl_path
        persistent_paths["step"] = persistent_step_path
        persistent_paths["stl"] = persistent_stl_path
        export_model(model, latest_step_path, latest_stl_path)
        export_model(model, persistent_step_path, persistent_stl_path)

    validation_report = _validate_geometry(
        model,
        updated_table,
        output_paths=None if dry_run else {"step": latest_step_path, "stl": latest_stl_path},
    )
    validation_filename = _edited_validation_report_name(updated_table.family)
    latest_validation_report_path = out_root / validation_filename
    persistent_validation_report_path = run_context.run_dir / validation_filename
    shared_validation_report_path = out_root / "edited_validation_report.json"
    latest_paths["validation_report"] = latest_validation_report_path
    persistent_paths["validation_report"] = persistent_validation_report_path
    if latest_validation_report_path != shared_validation_report_path:
        latest_paths["shared_validation_report"] = shared_validation_report_path
    write_validation_report(validation_report, latest_validation_report_path)
    if latest_validation_report_path != shared_validation_report_path:
        write_validation_report(validation_report, shared_validation_report_path)
    write_validation_report(validation_report, persistent_validation_report_path)

    edit_report = edit_report.model_copy(
        update={
            "validation_report": validation_report,
            "validation_summary": validation_report.summary,
            "metadata": {
                **edit_report.metadata,
                "command": f"edit-parse-apply {target}",
                "run_id": run_context.run_id,
                "request_id": request_id,
                "original_edit_text": edit_text,
                "latest_edit_report_path": str(latest_edit_report_path),
                "persistent_edit_report_path": str(persistent_edit_report_path),
                "updated_params_path": str(latest_updated_params_path),
                "persistent_updated_params_path": str(persistent_updated_params_path),
                "planned_cad_paths": _paths_for_json(planned_cad_paths),
                "latest_edited_step_path": None if dry_run else str(latest_step_path),
                "latest_edited_stl_path": None if dry_run else str(latest_stl_path),
                "persistent_edited_step_path": None if dry_run else str(persistent_step_path),
                "persistent_edited_stl_path": None if dry_run else str(persistent_stl_path),
                "edited_validation_report_path": str(latest_validation_report_path),
                "shared_edited_validation_report_path": str(shared_validation_report_path),
                "persistent_edited_validation_report_path": str(persistent_validation_report_path),
                "cad_exported": not dry_run,
                "dry_run": dry_run,
            },
        }
    )
    write_edit_report(edit_report, latest_edit_report_path)
    write_edit_report(edit_report, persistent_edit_report_path)

    updated_active_features, updated_omitted_features = feature_state_names(updated_table)
    metadata = _edit_run_metadata(
        run_context=run_context,
        command_type="edit-parse-apply",
        edit_text=edit_text,
        parsed_edit=parsed_edit,
        request_id=request_id,
        accepted=True,
        validation_valid=validation_report.valid,
        object_type=updated_table.family,
        active_features=updated_active_features,
        omitted_features=updated_omitted_features,
        output_paths={"latest": latest_paths, "persistent": persistent_paths},
    )
    metadata["dry_run"] = dry_run
    metadata["cad_exported"] = not dry_run
    metadata["planned_cad_paths"] = _paths_for_json(planned_cad_paths)
    write_run_metadata(metadata, persistent_paths["run_metadata"])
    result = {
        "ok": validation_report.valid,
        "accepted": True,
        "run_id": run_context.run_id,
        "object_type": updated_table.family,
        "validation_valid": validation_report.valid,
        "edit_request": parsed_edit,
        "edit_report": edit_report.model_dump(mode="json"),
        "validation_report": validation_report.model_dump(mode="json"),
        "cad_exported": not dry_run,
        "dry_run": dry_run,
        "latest_outputs": _paths_for_json(latest_paths),
        "persistent_outputs": _paths_for_json(persistent_paths),
        "planned_outputs": _paths_for_json(planned_cad_paths),
        "persistent_output_dir": str(run_context.run_dir),
        "run_metadata": metadata,
        "active_features": updated_active_features,
        "omitted_features": updated_omitted_features,
    }
    if not validation_report.valid:
        result["error_type"] = "ValidationFailedError"
        result["message"] = validation_report.summary
    return apply_response_contract(
        result,
        operation="edit_parse_apply",
        request_id=request_id,
        object_type=updated_table.family,
        validation_report=validation_report,
        dry_run=dry_run,
    )


def build_example_workflow(
    variant: str = "bracket",
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build the bundled bracket example and export latest STEP/STL files."""

    request_id = ensure_request_id(request_id)
    if variant not in {"bracket", "l_bracket"}:
        return error_response(
            operation="build_example",
            request_id=request_id,
            error_type="ValueError",
            message=f"unsupported variant: {variant}",
            recoverable=True,
        )

    out_root = _output_root(output_root)
    parameter_table, _, feature_plan, _ = _example_bundle(variant)
    try:
        model = _build_model(parameter_table, feature_plan)
    except CadQueryUnavailableError as exc:
        return error_response(
            operation="build_example",
            request_id=request_id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            recoverable=True,
            object_type=parameter_table.family,
        )
    basename = "l_bracket" if parameter_table.family == "l_bracket" else "bracket"
    step_path = out_root / f"{basename}.step"
    stl_path = out_root / f"{basename}.stl"
    export_model(model, step_path, stl_path)
    result = {
        "ok": True,
        "object_type": parameter_table.family,
        "step_path": str(step_path),
        "stl_path": str(stl_path),
        "parameters": parameter_table.model_dump(mode="json"),
        "cad_exported": True,
    }
    return apply_response_contract(
        result,
        operation="build_example",
        request_id=request_id,
        object_type=parameter_table.family,
    )


def validate_example_workflow(
    variant: str = "bracket",
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Validate the bundled bracket example and write latest and persistent reports."""

    request_id = ensure_request_id(request_id)
    if variant not in {"bracket", "l_bracket"}:
        return error_response(
            operation="validate_example",
            request_id=request_id,
            error_type="ValueError",
            message=f"unsupported variant: {variant}",
            recoverable=True,
        )

    out_root = _output_root(output_root)
    parameter_table, intent, feature_plan, constraint_graph = _example_bundle(variant)
    try:
        model = _build_model(parameter_table, feature_plan)
    except CadQueryUnavailableError as exc:
        return error_response(
            operation="validate_example",
            request_id=request_id,
            error_type=exc.__class__.__name__,
            message=str(exc),
            recoverable=True,
            object_type=parameter_table.family,
        )
    basename = "l_bracket" if parameter_table.family == "l_bracket" else "bracket"
    step_path = out_root / f"{basename}.step"
    stl_path = out_root / f"{basename}.stl"
    if _needs_export(step_path, stl_path):
        export_model(model, step_path, stl_path)

    geometry_report = _validate_geometry(
        model,
        parameter_table,
        output_paths={"step": step_path, "stl": stl_path},
    )
    intent_report = _validate_intent(intent, parameter_table, feature_plan, constraint_graph)
    combined_report = _combine_reports(geometry_report, intent_report)
    latest_report_path = out_root / "validation_report.json"
    persistent_report_path = out_root / "validation_reports" / f"{basename}_validation_report.json"
    combined_report = combined_report.model_copy(
        update={
            "metadata": {
                **combined_report.metadata,
                "command": f"validate-example {variant}",
                "request_id": request_id,
                "latest_report_path": str(latest_report_path),
                "persistent_report_path": str(persistent_report_path),
            }
        }
    )
    write_validation_report(combined_report, latest_report_path)
    write_validation_report(combined_report, persistent_report_path)
    total_checks = len(combined_report.checks)
    failed_checks = len(combined_report.failed_checks)
    warnings = len(combined_report.warnings)
    passed_checks = total_checks - failed_checks
    result = {
        "ok": combined_report.valid,
        "valid": combined_report.valid,
        "object_type": parameter_table.family,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "warnings": warnings,
        "report_path": str(latest_report_path),
        "persistent_report_path": str(persistent_report_path),
        "validation_report": combined_report.model_dump(mode="json"),
    }
    if not combined_report.valid:
        result["error_type"] = "ValidationFailedError"
        result["message"] = combined_report.summary
    return apply_response_contract(
        result,
        operation="validate_example",
        request_id=request_id,
        object_type=parameter_table.family,
        validation_report=combined_report,
    )


def list_recent_runs_workflow(
    kind: str,
    limit: int = 5,
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """List recent traceable run directories."""

    request_id = ensure_request_id(request_id)
    if kind not in SUPPORTED_RUN_KINDS:
        result = error_response(
            operation="list_recent_runs",
            request_id=request_id,
            error_type="ValueError",
            message=f"invalid run kind: {kind}",
            recoverable=True,
        )
        result["runs"] = []
        return result
    if limit <= 0:
        result = error_response(
            operation="list_recent_runs",
            request_id=request_id,
            error_type="ValueError",
            message="limit must be greater than zero",
            recoverable=True,
        )
        result["runs"] = []
        return result

    runs_dir = _output_root(output_root) / kind
    if not runs_dir.exists():
        return apply_response_contract(
            {"ok": True, "runs": []},
            operation="list_recent_runs",
            request_id=request_id,
            metadata={"kind": kind, "limit": limit},
        )

    runs: list[dict[str, Any]] = []
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
        metadata_path = run_dir / "run_metadata.json"
        metadata: dict[str, Any] = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                metadata = {"metadata_error": "run_metadata.json could not be parsed"}
        runs.append(
            {
                "run_id": run_dir.name,
                "path": str(run_dir),
                "created_at": metadata.get("created_at"),
                "command_type": metadata.get("command_type"),
            }
        )
        if len(runs) >= limit:
            break
    return apply_response_contract(
        {"ok": True, "runs": runs},
        operation="list_recent_runs",
        request_id=request_id,
        metadata={"kind": kind, "limit": limit},
    )


def get_run_metadata_workflow(
    kind: str,
    run_id: str,
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return metadata for one traceable output run."""

    request_id = ensure_request_id(request_id)
    if kind not in SUPPORTED_RUN_KINDS:
        return error_response(
            operation="get_run_metadata",
            request_id=request_id,
            error_type="ValueError",
            message=f"invalid run kind: {kind}",
            recoverable=True,
        )
    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        return error_response(
            operation="get_run_metadata",
            request_id=request_id,
            error_type="ValueError",
            message="run_id must be a single directory name",
            recoverable=True,
        )

    metadata_path = _output_root(output_root) / kind / run_id / "run_metadata.json"
    if not metadata_path.exists():
        return error_response(
            operation="get_run_metadata",
            request_id=request_id,
            error_type="FileNotFoundError",
            message=f"run metadata not found: {metadata_path}",
            recoverable=True,
        )

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return error_response(
            operation="get_run_metadata",
            request_id=request_id,
            error_type="JSONDecodeError",
            message=f"run metadata could not be parsed: {exc}",
            recoverable=True,
        )
    result = apply_response_contract(
        {"ok": True, "metadata": metadata},
        operation="get_run_metadata",
        request_id=request_id,
        metadata={"kind": kind, "run_id": run_id},
    )
    result["contract_metadata"] = result["metadata"]
    result["metadata"] = metadata
    return result
