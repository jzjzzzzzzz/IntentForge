"""Command-line entry point for IntentForge."""

from argparse import ArgumentParser
import json
from pathlib import Path

import yaml

from intentforge.editor.edit_intent_handler import apply_edit_request, write_edit_report
from intentforge.generator.cadquery_generator import (
    CadQueryUnavailableError,
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
from intentforge.validator.geometry_validator import validate_wall_bracket, write_validation_report
from intentforge.validator.intent_validator import validate_wall_bracket_intent
from intentforge.workflows import (
    build_example_workflow,
    edit_parse_apply_workflow,
    edit_parse_workflow,
    parse_build_workflow,
    parse_prompt_workflow,
    validate_example_workflow,
)
from benchmark.run_benchmark import run_benchmark
from intentforge.demo_runner import run_demo


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_bracket_parameters() -> ParameterTable:
    params_path = _project_root() / "examples" / "bracket_params.yaml"
    with params_path.open("r", encoding="utf-8") as params_file:
        data = yaml.safe_load(params_file)
    return ParameterTable.model_validate(data)


def _load_json_example(filename: str) -> dict:
    path = _project_root() / "examples" / filename
    with path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def _load_json_path(path: str | Path) -> dict:
    json_path = _resolve_project_path(path)
    with json_path.open("r", encoding="utf-8") as json_file:
        return json.load(json_file)


def _resolve_project_path(path: str | Path) -> Path:
    resolved_path = Path(path)
    if not resolved_path.is_absolute():
        resolved_path = _project_root() / resolved_path
    return resolved_path


def _load_bracket_intent() -> IntentSpec:
    return IntentSpec.model_validate(_load_json_example("bracket_intent.json"))


def _load_bracket_feature_plan() -> FeaturePlan:
    return FeaturePlan.model_validate(_load_json_example("bracket_feature_plan.json"))


def _load_bracket_constraints() -> ConstraintGraph:
    return ConstraintGraph.model_validate(_load_json_example("bracket_constraints.json"))


def _output_paths() -> tuple[Path, Path]:
    project_root = _project_root()
    return project_root / "output" / "bracket.step", project_root / "output" / "bracket.stl"


def _edited_output_paths() -> tuple[Path, Path]:
    project_root = _project_root()
    return project_root / "output" / "bracket_edited.step", project_root / "output" / "bracket_edited.stl"


def _persistent_validation_report_path() -> Path:
    return _project_root() / "output" / "validation_reports" / "bracket_validation_report.json"


def _edit_file_stem(edit_path: str | Path) -> str:
    return _resolve_project_path(edit_path).stem


def _persistent_edit_report_path(edit_file_stem: str) -> Path:
    return _project_root() / "output" / "edit_reports" / f"{edit_file_stem}_edit_report.json"


def _persistent_edited_output_paths(edit_file_stem: str) -> tuple[Path, Path]:
    output_dir = _project_root() / "output" / "edited_models"
    return output_dir / f"{edit_file_stem}_bracket.step", output_dir / f"{edit_file_stem}_bracket.stl"


def _write_parameter_table(parameter_table: ParameterTable, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(parameter_table.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return path


def _write_json_model(model, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_json_data(data: dict, path: Path) -> Path:
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


def _write_parsed_outputs(parsed, prompt: str, run_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    output_dir = _project_root() / "output"
    latest_paths = _parsed_output_paths(output_dir)
    compatibility_paths = _parsed_output_paths(output_dir / "parsed")
    persistent_paths = _parsed_run_output_paths(run_dir)

    for paths in (latest_paths, compatibility_paths, persistent_paths):
        _write_json_model(parsed.intent, paths["intent"])
        _write_parameter_table(parsed.parameter_table, paths["params"])
        _write_json_model(parsed.constraint_graph, paths["constraints"])
        _write_json_model(parsed.feature_plan, paths["feature_plan"])

    persistent_paths["prompt"].write_text(prompt + "\n", encoding="utf-8")
    return latest_paths, persistent_paths


def _print_parse_summary(
    parsed,
    run_id: str,
    latest_paths: dict[str, Path],
    persistent_paths: dict[str, Path],
    active_features: list[str],
    omitted_features: list[str],
) -> None:
    print("Parsed prompt.")
    print(f"Run ID: {run_id}")
    print(f"Object type: {parsed.intent.family}")
    print(f"Active features: {', '.join(active_features) if active_features else 'none'}")
    print(f"Omitted features: {', '.join(omitted_features) if omitted_features else 'none'}")
    print(f"Assumptions count: {len(parsed.intent.assumptions)}")
    print(f"Unknowns count: {len(parsed.intent.unknowns)}")
    print("Extracted parameters:")
    for parameter in parsed.parameter_table.parameters:
        unit = f" {parameter.unit}" if parameter.unit else ""
        print(f"  {parameter.name}: {parameter.value}{unit} ({parameter.source})")
    print("Assumptions:")
    for assumption in parsed.intent.assumptions:
        print(f"  - {assumption}")
    print("Unknowns:")
    for unknown in parsed.intent.unknowns:
        print(f"  - {unknown}")
    print("Warnings:")
    if parsed.warnings:
        for warning in parsed.warnings:
            print(f"  - {warning}")
    else:
        print("  - none")
    print(f"Latest parsed intent:       {latest_paths['intent']}")
    print(f"Latest parsed params:       {latest_paths['params']}")
    print(f"Latest parsed constraints:  {latest_paths['constraints']}")
    print(f"Latest parsed feature plan: {latest_paths['feature_plan']}")
    print(f"Persistent parsed dir:      {persistent_paths['intent'].parent}")
    print(f"Run metadata:               {persistent_paths['run_metadata']}")


def _parse_command(prompt_parts: list[str]) -> int:
    prompt = " ".join(prompt_parts)
    result = parse_prompt_workflow(prompt, _project_root() / "output", write_outputs=True)
    print("Parsed prompt.")
    print(f"Run ID: {result['run_id']}")
    print(f"Object type: {result['intent']['family']}")
    print(f"Active features: {', '.join(result['active_features']) if result['active_features'] else 'none'}")
    print(f"Omitted features: {', '.join(result['omitted_features']) if result['omitted_features'] else 'none'}")
    print(f"Assumptions count: {len(result['assumptions'])}")
    print(f"Unknowns count: {len(result['unknowns'])}")
    print("Extracted parameters:")
    for parameter in result["parameters"]["parameters"]:
        unit = f" {parameter['unit']}" if parameter.get("unit") else ""
        print(f"  {parameter['name']}: {parameter['value']}{unit} ({parameter['source']})")
    print("Assumptions:")
    for assumption in result["assumptions"]:
        print(f"  - {assumption}")
    print("Unknowns:")
    for unknown in result["unknowns"]:
        print(f"  - {unknown}")
    print("Warnings:")
    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  - {warning}")
    else:
        print("  - none")
    latest_paths = result["latest_outputs"]
    persistent_paths = result["persistent_outputs"]
    print(f"Latest parsed intent:       {latest_paths['intent']}")
    print(f"Latest parsed params:       {latest_paths['params']}")
    print(f"Latest parsed constraints:  {latest_paths['constraints']}")
    print(f"Latest parsed feature plan: {latest_paths['feature_plan']}")
    print(f"Persistent parsed dir:      {result['persistent_output_dir']}")
    print(f"Run metadata:               {persistent_paths['run_metadata']}")
    return 0


def _parse_build_command(prompt_parts: list[str]) -> int:
    prompt = " ".join(prompt_parts)
    result = parse_build_workflow(prompt, _project_root() / "output")
    print("Parsed prompt.")
    print(f"Run ID: {result['run_id']}")
    print(f"Object type: {result['intent']['family']}")
    print(f"Active features: {', '.join(result['active_features']) if result['active_features'] else 'none'}")
    print(f"Omitted features: {', '.join(result['omitted_features']) if result['omitted_features'] else 'none'}")
    print(f"Assumptions count: {len(result['assumptions'])}")
    print(f"Unknowns count: {len(result['unknowns'])}")
    print("Extracted parameters:")
    for parameter in result["parameters"]["parameters"]:
        unit = f" {parameter['unit']}" if parameter.get("unit") else ""
        print(f"  {parameter['name']}: {parameter['value']}{unit} ({parameter['source']})")
    print("Assumptions:")
    for assumption in result["assumptions"]:
        print(f"  - {assumption}")
    print("Unknowns:")
    for unknown in result["unknowns"]:
        print(f"  - {unknown}")
    print("Warnings:")
    if result["warnings"]:
        for warning in result["warnings"]:
            print(f"  - {warning}")
    else:
        print("  - none")
    latest_paths = result["latest_outputs"]
    persistent_paths = result["persistent_outputs"]
    print(f"Latest parsed intent:       {latest_paths['intent']}")
    print(f"Latest parsed params:       {latest_paths['params']}")
    print(f"Latest parsed constraints:  {latest_paths['constraints']}")
    print(f"Latest parsed feature plan: {latest_paths['feature_plan']}")
    print(f"Persistent parsed dir:      {result['persistent_output_dir']}")
    print(f"Run metadata:               {persistent_paths['run_metadata']}")
    print("Built parsed bracket.")
    print(f"Latest STEP: {latest_paths['step']}")
    print(f"Latest STL:  {latest_paths['stl']}")
    print(f"Latest validation report: {latest_paths['validation_report']}")
    print(f"Persistent STEP: {persistent_paths['step']}")
    print(f"Persistent STL:  {persistent_paths['stl']}")
    print(f"Persistent validation report: {persistent_paths['validation_report']}")
    print(f"Persistent output dir: {result['persistent_output_dir']}")
    print(f"Validation valid: {str(result['validation_valid']).lower()}")
    return 0 if result["validation_valid"] else 1


def _edit_parse_output_paths(run_dir: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    latest_paths = {
        "parsed_edit": _project_root() / "output" / "parsed_edit.json",
    }
    persistent_paths = {
        "parsed_edit": run_dir / "parsed_edit.json",
        "prompt": run_dir / "prompt.txt",
        "run_metadata": run_dir / "run_metadata.json",
    }
    return latest_paths, persistent_paths


def _write_edit_parse_outputs(
    parsed_edit: dict,
    edit_text: str,
    latest_paths: dict[str, Path],
    persistent_paths: dict[str, Path],
) -> None:
    _write_json_data(parsed_edit, latest_paths["parsed_edit"])
    _write_json_data(parsed_edit, persistent_paths["parsed_edit"])
    persistent_paths["prompt"].write_text(edit_text + "\n", encoding="utf-8")


def _edit_run_metadata(
    *,
    run_context,
    command_type: str,
    edit_text: str,
    parsed_edit: dict,
    output_paths: dict,
    accepted: bool | None = None,
    validation_valid: bool | None = None,
) -> dict:
    metadata = {
        "run_id": run_context.run_id,
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
    return metadata


def _print_edit_parse_summary(
    run_id: str,
    parsed_edit: dict,
    latest_paths: dict[str, Path],
    persistent_paths: dict[str, Path],
    accepted: bool | None = None,
    validation_valid: bool | None = None,
    cad_exported: bool = False,
) -> None:
    print(json.dumps(parsed_edit, indent=2, sort_keys=True))
    print("Parsed edit.")
    print(f"Run ID: {run_id}")
    print(f"Edits: {len(parsed_edit.get('edits', []))}")
    print(f"Preserve entries: {len(parsed_edit.get('preserve', []))}")
    print(f"Warnings: {len(parsed_edit.get('warnings', []))}")
    if accepted is not None:
        print(f"Accepted: {str(accepted).lower()}")
    if validation_valid is not None:
        print(f"Validation valid: {str(validation_valid).lower()}")
    print(f"CAD exported: {str(cad_exported).lower()}")
    print(f"Latest parsed edit: {latest_paths['parsed_edit']}")
    print(f"Persistent parsed edit: {persistent_paths['parsed_edit']}")
    print(f"Persistent output dir: {Path(persistent_paths['parsed_edit']).parent}")
    print(f"Run metadata: {persistent_paths['run_metadata']}")


def _parse_edit_text(edit_text: str, parameter_table: ParameterTable | None = None) -> tuple[dict, bool]:
    try:
        return parse_edit_request(
            edit_text,
            existing_params=parameter_table,
        ), True
    except UnsupportedEditError as exc:
        return {
            "edits": [],
            "preserve": [],
            "warnings": [str(exc)],
            "assumptions": [],
            "rejected": True,
            "error": str(exc),
        }, False


def _edit_parse_command(prompt_parts: list[str]) -> int:
    edit_text = " ".join(prompt_parts)
    result = edit_parse_workflow(edit_text, _project_root() / "output", write_outputs=True)
    parsed_edit = result["edit_request"]
    latest_paths = result["latest_outputs"]
    persistent_paths = result["persistent_outputs"]
    _print_edit_parse_summary(
        result["run_id"],
        parsed_edit,
        latest_paths,
        persistent_paths,
        accepted=result["ok"],
        cad_exported=False,
    )
    return 0 if result["ok"] else 1


def _edit_parse_apply_command(example: str, prompt_parts: list[str]) -> int:
    if example != "bracket":
        raise ValueError(f"unsupported example: {example}")

    edit_text = " ".join(prompt_parts)
    result = edit_parse_apply_workflow(example, edit_text, _project_root() / "output")
    parsed_edit = result["edit_request"]
    latest_paths = result["latest_outputs"]
    persistent_paths = result["persistent_outputs"]
    if not result["accepted"]:
        _print_edit_parse_summary(
            result["run_id"],
            parsed_edit,
            latest_paths,
            persistent_paths,
            accepted=False,
            cad_exported=False,
        )
        print("No CAD export occurred for this edit.")
        return 1

    _print_edit_parse_summary(
        result["run_id"],
        parsed_edit,
        latest_paths,
        persistent_paths,
        accepted=True,
        validation_valid=result["validation_valid"],
        cad_exported=True,
    )
    print(f"Latest edit report: {latest_paths['edit_report']}")
    print(f"Latest updated params: {latest_paths['updated_params']}")
    print(f"Latest edited STEP: {latest_paths['step']}")
    print(f"Latest edited STL:  {latest_paths['stl']}")
    print(f"Latest validation report: {latest_paths['validation_report']}")
    print(f"Persistent edit report: {persistent_paths['edit_report']}")
    print(f"Persistent updated params: {persistent_paths['updated_params']}")
    print(f"Persistent edited STEP: {persistent_paths['step']}")
    print(f"Persistent edited STL:  {persistent_paths['stl']}")
    print(f"Persistent validation report: {persistent_paths['validation_report']}")
    return 0 if result["validation_valid"] else 1


def _build_example_bracket() -> int:
    result = build_example_workflow("bracket", _project_root() / "output")
    if not result["ok"]:
        print(result.get("message", "Failed to build wall_mounted_bracket example."))
        return 1
    print("Built wall_mounted_bracket example.")
    print(f"STEP: {result['step_path']}")
    print(f"STL:  {result['stl_path']}")
    return 0


def _needs_export(step_path: Path, stl_path: Path) -> bool:
    return not (
        step_path.exists()
        and stl_path.exists()
        and step_path.stat().st_size > 0
        and stl_path.stat().st_size > 0
    )


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
        family="wall_mounted_bracket",
        checks=checks,
        summary=summary,
        metadata={
            "geometry_summary": geometry_report.summary,
            "intent_summary": intent_report.summary,
        },
    )


def _validate_example_bracket() -> int:
    result = validate_example_workflow("bracket", _project_root() / "output")
    if not result["ok"] and "valid" not in result:
        print(result.get("message", "Failed to validate wall_mounted_bracket example."))
        return 1
    print("Validated wall_mounted_bracket example.")
    print(f"Latest report:     {result['report_path']}")
    print(f"Persistent report: {result['persistent_report_path']}")
    print(f"Total checks:  {result['total_checks']}")
    print(f"Passed checks: {result['passed_checks']}")
    print(f"Failed checks: {result['failed_checks']}")
    print(f"Warnings:      {result['warnings']}")
    print(f"Final valid:   {str(result['valid']).lower()}")
    return 0 if result["valid"] else 1


def _print_edit_summary(
    report: ValidationReport | None,
    edit_file_path: Path,
    latest_edit_report_path: Path,
    persistent_edit_report_path: Path,
    edit_report,
    cad_exported: bool,
    latest_step_path: Path | None = None,
    latest_stl_path: Path | None = None,
    persistent_step_path: Path | None = None,
    persistent_stl_path: Path | None = None,
    updated_params_path: Path | None = None,
    validation_report_path: Path | None = None,
) -> None:
    changed = [
        f"{change['parameter']}: {change['old_value']} -> {change['new_value']}"
        for change in edit_report.changed_parameters
    ]
    validation_result = report.valid if report is not None else (
        edit_report.validation_report.valid if edit_report.validation_report is not None else False
    )
    print("Edited wall_mounted_bracket example.")
    print(f"Accepted: {str(edit_report.accepted).lower()}")
    print(f"Edit file: {edit_file_path}")
    print(f"Latest edit report:     {latest_edit_report_path}")
    print(f"Persistent edit report: {persistent_edit_report_path}")
    print(f"Changed parameters: {', '.join(changed) if changed else 'none'}")
    print(f"Preserved parameters count: {len(edit_report.preserved_parameters)}")
    print(
        "Failed constraints: "
        f"{'; '.join(edit_report.failed_constraints) if edit_report.failed_constraints else 'none'}"
    )
    print(f"Validation valid: {str(validation_result).lower() if edit_report.accepted else 'not run'}")
    print(f"CAD exported: {str(cad_exported).lower()}")
    if not cad_exported:
        print("No CAD export occurred for this edit.")
    if updated_params_path is not None:
        print(f"Updated params: {updated_params_path}")
    if latest_step_path is not None:
        print(f"Latest edited STEP: {latest_step_path}")
    if latest_stl_path is not None:
        print(f"Latest edited STL:  {latest_stl_path}")
    if persistent_step_path is not None:
        print(f"Persistent edited STEP: {persistent_step_path}")
    if persistent_stl_path is not None:
        print(f"Persistent edited STL:  {persistent_stl_path}")
    if validation_report_path is not None:
        print(f"Edited validation report: {validation_report_path}")


def _edit_example_bracket(edit_path: str) -> int:
    project_root = _project_root()
    parameter_table = _load_bracket_parameters()
    constraint_graph = _load_bracket_constraints()
    edit_file_path = _resolve_project_path(edit_path)
    edit_file_stem = _edit_file_stem(edit_path)
    edit_data = _load_json_path(edit_path)

    edit_report = apply_edit_request(parameter_table, edit_data, constraint_graph)
    latest_edit_report_path = project_root / "output" / "edit_report.json"
    persistent_edit_report_path = _persistent_edit_report_path(edit_file_stem)

    if not edit_report.accepted:
        edit_report = edit_report.model_copy(
            update={
                "metadata": {
                    **edit_report.metadata,
                    "command": f"edit-example bracket {edit_path}",
                    "edit_file_path": str(edit_file_path),
                    "latest_edit_report_path": str(latest_edit_report_path),
                    "persistent_edit_report_path": str(persistent_edit_report_path),
                    "cad_exported": False,
                }
            }
        )
        write_edit_report(edit_report, latest_edit_report_path)
        write_edit_report(edit_report, persistent_edit_report_path)
        _print_edit_summary(
            None,
            edit_file_path,
            latest_edit_report_path,
            persistent_edit_report_path,
            edit_report,
            cad_exported=False,
        )
        return 1

    updated_table_data = edit_report.metadata["updated_parameter_table"]
    updated_table = ParameterTable.model_validate(updated_table_data)
    updated_params_path = project_root / "output" / "updated_params.yaml"
    _write_parameter_table(updated_table, updated_params_path)

    model = build_wall_bracket(updated_table)
    latest_step_path, latest_stl_path = _edited_output_paths()
    persistent_step_path, persistent_stl_path = _persistent_edited_output_paths(edit_file_stem)
    export_model(model, latest_step_path, latest_stl_path)
    export_model(model, persistent_step_path, persistent_stl_path)

    validation_report = validate_wall_bracket(
        model,
        updated_table,
        output_paths={"step": latest_step_path, "stl": latest_stl_path},
    )
    validation_report_path = project_root / "output" / "edited_validation_report.json"
    write_validation_report(validation_report, validation_report_path)

    edit_report = edit_report.model_copy(
        update={
            "validation_report": validation_report,
            "validation_summary": validation_report.summary,
            "metadata": {
                **edit_report.metadata,
                "command": f"edit-example bracket {edit_path}",
                "edit_file_path": str(edit_file_path),
                "updated_params_path": str(updated_params_path),
                "latest_edit_report_path": str(latest_edit_report_path),
                "persistent_edit_report_path": str(persistent_edit_report_path),
                "latest_edited_step_path": str(latest_step_path),
                "latest_edited_stl_path": str(latest_stl_path),
                "persistent_edited_step_path": str(persistent_step_path),
                "persistent_edited_stl_path": str(persistent_stl_path),
                "edited_validation_report_path": str(validation_report_path),
                "cad_exported": True,
            },
        }
    )
    write_edit_report(edit_report, latest_edit_report_path)
    write_edit_report(edit_report, persistent_edit_report_path)

    _print_edit_summary(
        validation_report,
        edit_file_path,
        latest_edit_report_path,
        persistent_edit_report_path,
        edit_report,
        cad_exported=True,
        latest_step_path=latest_step_path,
        latest_stl_path=latest_stl_path,
        persistent_step_path=persistent_step_path,
        persistent_stl_path=persistent_stl_path,
        updated_params_path=updated_params_path,
        validation_report_path=validation_report_path,
    )
    return 0 if validation_report.valid else 1


def _demo_command(output_root: str | None = None) -> int:
    result = run_demo(output_root or (_project_root() / "output"))
    print(result["summary"], end="")
    print(f"Demo run ID: {result['run_id']}")
    print(f"Output directory: {result['output_dir']}")
    print(f"Demo report: {result['demo_report_path']}")
    print(f"Demo summary: {result['demo_summary_path']}")
    benchmark = result["benchmark"]
    print(
        "Benchmark summary: "
        f"{benchmark['passed']}/{benchmark['total_cases']} passed "
        f"({benchmark['pass_rate']:.4f})"
    )
    rejected = [
        step
        for step in result["steps"]
        if step.get("intentional_rejection")
    ]
    print(f"Rejected vague edit result: {'rejected as expected' if rejected and not rejected[0]['ok'] else 'unexpected'}")
    cad_outputs = []
    for step in result["steps"]:
        outputs = step.get("persistent_outputs") or {}
        if "step" in outputs:
            cad_outputs.append(outputs["step"])
        if "stl" in outputs:
            cad_outputs.append(outputs["stl"])
    print("Generated CAD outputs:")
    for path in cad_outputs:
        print(f"  - {path}")
    if not cad_outputs:
        print("  - none")
    return 0 if benchmark["failed"] == 0 else 1


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="intentforge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_example = subparsers.add_parser(
        "build-example",
        help="Build a bundled example model.",
    )
    build_example.add_argument(
        "example",
        choices=["bracket"],
        help="Example model to build.",
    )

    validate_example = subparsers.add_parser(
        "validate-example",
        help="Validate a bundled example model.",
    )
    validate_example.add_argument(
        "example",
        choices=["bracket"],
        help="Example model to validate.",
    )

    edit_example = subparsers.add_parser(
        "edit-example",
        help="Apply a structured edit to a bundled example model.",
    )
    edit_example.add_argument(
        "example",
        choices=["bracket"],
        help="Example model to edit.",
    )
    edit_example.add_argument(
        "edit_json",
        help="Path to a structured edit JSON file.",
    )

    parse = subparsers.add_parser(
        "parse",
        help="Parse a simple natural-language wall-mounted bracket prompt.",
    )
    parse.add_argument("prompt", nargs="+", help="Prompt text to parse.")

    parse_build = subparsers.add_parser(
        "parse-build",
        help="Parse a prompt, build the bracket, export CAD, and validate it.",
    )
    parse_build.add_argument("prompt", nargs="+", help="Prompt text to parse and build.")

    edit_parse = subparsers.add_parser(
        "edit-parse",
        help="Parse a simple natural-language bracket edit request.",
    )
    edit_parse.add_argument("edit_text", nargs="+", help="Edit request text to parse.")

    edit_parse_apply = subparsers.add_parser(
        "edit-parse-apply",
        help="Parse and apply a natural-language edit request to a bundled example.",
    )
    edit_parse_apply.add_argument(
        "example",
        choices=["bracket"],
        help="Example model to edit.",
    )
    edit_parse_apply.add_argument("edit_text", nargs="+", help="Edit request text to parse and apply.")

    benchmark = subparsers.add_parser(
        "benchmark",
        help="Run the deterministic IntentForge benchmark suite.",
    )
    benchmark.add_argument(
        "--output-root",
        default=None,
        help="Optional output root directory for benchmark artifacts.",
    )

    demo = subparsers.add_parser(
        "demo",
        help="Run the IntentForge release demo workflow.",
    )
    demo.add_argument(
        "--output-root",
        default=None,
        help="Optional output root directory for demo artifacts.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the IntentForge CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "build-example" and args.example == "bracket":
            return _build_example_bracket()
        if args.command == "validate-example" and args.example == "bracket":
            return _validate_example_bracket()
        if args.command == "edit-example" and args.example == "bracket":
            return _edit_example_bracket(args.edit_json)
        if args.command == "parse":
            return _parse_command(args.prompt)
        if args.command == "parse-build":
            return _parse_build_command(args.prompt)
        if args.command == "edit-parse":
            return _edit_parse_command(args.edit_text)
        if args.command == "edit-parse-apply":
            return _edit_parse_apply_command(args.example, args.edit_text)
        if args.command == "benchmark":
            result = run_benchmark(args.output_root or (_project_root() / "output"))
            print(result["summary"], end="")
            print(f"Report path: {result['report_path']}")
            print(f"Failed case IDs: {', '.join(case['id'] for case in result['failed_cases']) if result['failed_cases'] else 'none'}")
            return 0 if result["failed"] == 0 else 1
        if args.command == "demo":
            return _demo_command(args.output_root)
    except CadQueryUnavailableError as exc:
        parser.exit(1, f"{exc}\n")
    except UnsupportedObjectError as exc:
        parser.exit(1, f"{exc}\n")
    except OSError as exc:
        parser.exit(1, f"Could not read required file: {exc}\n")
    except json.JSONDecodeError as exc:
        parser.exit(1, f"Could not parse JSON file: {exc}\n")

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
