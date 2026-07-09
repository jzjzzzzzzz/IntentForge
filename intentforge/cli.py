"""Command-line entry point for IntentForge."""

from argparse import ArgumentParser
import importlib
import importlib.util
import json
import platform
from pathlib import Path
import sys

import yaml

from harness.topology import (
    build_volume_delta_report,
    inspect_shape,
    write_shape_inspection_report,
    write_volume_delta_report,
)
from harness.adversarial import run_adversarial_harness
from harness.sweeps import run_parametric_sweep
from harness.edits import run_edit_preservation_harness
from intentforge.editor.edit_intent_handler import apply_edit_request, write_edit_report
from intentforge.generator.cadquery_generator import (
    CadQueryUnavailableError,
    build_l_bracket,
    build_wall_bracket,
    export_model,
)
from intentforge.llm import (
    LLMProviderUnavailableError,
    MockLLMProvider,
    load_provider_from_env,
    translate_edit_apply,
    translate_edit_to_request,
    translate_prompt_to_build,
    translate_prompt_to_intent,
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
from harness.orchestrator import run_technical_harness

SUPPORTED_MODEL_FAMILIES = ["wall_mounted_bracket", "l_bracket"]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_bracket_parameters() -> ParameterTable:
    params_path = _project_root() / "examples" / "bracket_params.yaml"
    with params_path.open("r", encoding="utf-8") as params_file:
        data = yaml.safe_load(params_file)
    return ParameterTable.model_validate(data)


def _load_l_bracket_parameters() -> ParameterTable:
    params_path = _project_root() / "examples" / "l_bracket_params.yaml"
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


def _parse_build_command(prompt_parts: list[str], dry_run: bool = False) -> int:
    prompt = " ".join(prompt_parts)
    result = parse_build_workflow(prompt, _project_root() / "output", dry_run=dry_run)
    if not result["ok"] and "validation_valid" not in result:
        print(f"Request ID: {result['request_id']}")
        print(f"Operation: {result['operation']}")
        print(f"Dry run: {str(result.get('dry_run', dry_run)).lower()}")
        print(result.get("message", "parse-build failed"))
        if result.get("error"):
            print(f"Error type: {result['error']['error_type']}")
            print(f"Suggested action: {result['error']['suggested_action']}")
        return 1
    print("Parsed prompt.")
    print(f"Request ID: {result['request_id']}")
    print(f"Run ID: {result['run_id']}")
    print(f"Dry run: {str(result['dry_run']).lower()}")
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
    print("Built parsed model.")
    print(f"CAD exported: {str(result['cad_exported']).lower()}")
    if result["cad_exported"]:
        print(f"Latest STEP: {latest_paths['step']}")
        print(f"Latest STL:  {latest_paths['stl']}")
    else:
        print("Latest STEP: not exported in dry run")
        print("Latest STL:  not exported in dry run")
    print(f"Latest validation report: {latest_paths['validation_report']}")
    if result["cad_exported"]:
        print(f"Persistent STEP: {persistent_paths['step']}")
        print(f"Persistent STL:  {persistent_paths['stl']}")
    else:
        print("Persistent STEP: not exported in dry run")
        print("Persistent STL:  not exported in dry run")
    print(f"Persistent validation report: {persistent_paths['validation_report']}")
    print(f"Persistent output dir: {result['persistent_output_dir']}")
    print(f"Validation valid: {str(result['validation_valid']).lower()}")
    return 0 if result["validation_valid"] else 1


def _load_llm_provider_for_cli(mock_provider: bool):
    if mock_provider:
        return MockLLMProvider()
    try:
        return load_provider_from_env()
    except LLMProviderUnavailableError:
        raise


def _print_tool_error(result: dict) -> None:
    print(f"Request ID: {result.get('request_id')}")
    print(f"Operation: {result.get('operation')}")
    print(f"OK: {str(result.get('ok')).lower()}")
    error = result.get("error") or {}
    print(f"Error type: {error.get('error_type') or result.get('error_type')}")
    print(f"Message: {error.get('message') or result.get('message')}")
    if error.get("suggested_action"):
        print(f"Suggested action: {error['suggested_action']}")


def _llm_parse_command(prompt_parts: list[str], mock_provider: bool = False) -> int:
    prompt = " ".join(prompt_parts)
    provider = _load_llm_provider_for_cli(mock_provider)
    result = translate_prompt_to_intent(prompt, provider)
    output_root = _project_root() / "output"
    if not result["ok"]:
        _print_tool_error(result)
        return 1
    latest_path = output_root / "llm_parsed_intent.json"
    metadata_path = output_root / "llm_parse_metadata.json"
    _write_json_data(result, latest_path)
    _write_json_data(
        {
            "request_id": result["request_id"],
            "operation": result["operation"],
            "object_type": result["object_type"],
            "normalized_prompt": result["normalized_prompt"],
            "warnings": result["warnings"],
        },
        metadata_path,
    )
    print("LLM intent translation completed.")
    print(f"Request ID: {result['request_id']}")
    print(f"Object type: {result['object_type']}")
    print(f"Operation: {result['operation']}")
    print(f"Normalized prompt: {result['normalized_prompt']}")
    print(f"LLM parsed intent: {latest_path}")
    print(f"LLM metadata: {metadata_path}")
    return 0


def _llm_parse_build_command(prompt_parts: list[str], mock_provider: bool = False, dry_run: bool = False) -> int:
    prompt = " ".join(prompt_parts)
    provider = _load_llm_provider_for_cli(mock_provider)
    result = translate_prompt_to_build(prompt, provider, _project_root() / "output", dry_run=dry_run)
    if not result["ok"] and "validation_valid" not in result:
        _print_tool_error(result)
        return 1
    print("LLM parse-build completed.")
    print(f"Request ID: {result['request_id']}")
    print(f"Run ID: {result['run_id']}")
    print(f"Object type: {result['object_type']}")
    print(f"Dry run: {str(result['dry_run']).lower()}")
    print(f"CAD exported: {str(result.get('cad_exported', False)).lower()}")
    print(f"Validation valid: {str(result.get('validation_valid')).lower()}")
    print(f"Persistent output dir: {result.get('persistent_output_dir')}")
    if result.get("latest_outputs"):
        print("Latest outputs:")
        for name, path in result["latest_outputs"].items():
            print(f"  - {name}: {path}")
    return 0 if result.get("validation_valid") else 1


def _llm_object_type(value: str) -> str:
    if value == "bracket":
        return "wall_mounted_bracket"
    return value


def _llm_edit_parse_command(object_type: str, edit_parts: list[str], mock_provider: bool = False) -> int:
    edit_text = " ".join(edit_parts)
    provider = _load_llm_provider_for_cli(mock_provider)
    normalized_object_type = _llm_object_type(object_type)
    result = translate_edit_to_request(edit_text, normalized_object_type, provider)
    output_root = _project_root() / "output"
    if not result["ok"]:
        _print_tool_error(result)
        return 1
    latest_path = output_root / "llm_parsed_edit.json"
    metadata_path = output_root / "llm_edit_parse_metadata.json"
    _write_json_data(result, latest_path)
    _write_json_data(
        {
            "request_id": result["request_id"],
            "operation": result["operation"],
            "object_type": result["object_type"],
            "normalized_edit_text": result["normalized_edit_text"],
            "warnings": result["warnings"],
        },
        metadata_path,
    )
    print("LLM edit translation completed.")
    print(f"Request ID: {result['request_id']}")
    print(f"Object type: {result['object_type']}")
    print(f"Operation: {result['operation']}")
    print(f"Normalized edit: {result['normalized_edit_text']}")
    print(f"LLM parsed edit: {latest_path}")
    print(f"LLM metadata: {metadata_path}")
    return 0


def _llm_edit_apply_command(object_type: str, edit_parts: list[str], mock_provider: bool = False, dry_run: bool = False) -> int:
    edit_text = " ".join(edit_parts)
    provider = _load_llm_provider_for_cli(mock_provider)
    normalized_object_type = _llm_object_type(object_type)
    result = translate_edit_apply(
        edit_text,
        normalized_object_type,
        provider,
        _project_root() / "output",
        dry_run=dry_run,
    )
    if not result["ok"] and "accepted" not in result:
        _print_tool_error(result)
        return 1
    print("LLM edit apply completed.")
    print(f"Request ID: {result['request_id']}")
    print(f"Run ID: {result.get('run_id')}")
    print(f"Object type: {result.get('object_type')}")
    print(f"Accepted: {str(result.get('accepted')).lower()}")
    print(f"Dry run: {str(result.get('dry_run', dry_run)).lower()}")
    print(f"CAD exported: {str(result.get('cad_exported', False)).lower()}")
    if result.get("validation_valid") is not None:
        print(f"Validation valid: {str(result['validation_valid']).lower()}")
    if not result.get("accepted", False):
        print(result.get("message", "Edit was rejected."))
        return 1
    print(f"Persistent output dir: {result.get('persistent_output_dir')}")
    return 0 if result.get("validation_valid", True) else 1


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


def _edit_parse_apply_command(example: str, prompt_parts: list[str], dry_run: bool = False) -> int:
    edit_text = " ".join(prompt_parts)
    result = edit_parse_apply_workflow(example, edit_text, _project_root() / "output", dry_run=dry_run)
    if "edit_request" not in result:
        print(f"Request ID: {result['request_id']}")
        print(f"Operation: {result['operation']}")
        print(f"Dry run: {str(result.get('dry_run', dry_run)).lower()}")
        print(result.get("message", "edit-parse-apply failed"))
        if result.get("error"):
            print(f"Error type: {result['error']['error_type']}")
            print(f"Suggested action: {result['error']['suggested_action']}")
        return 1
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
        cad_exported=result["cad_exported"],
    )
    print(f"Request ID: {result['request_id']}")
    print(f"Dry run: {str(result['dry_run']).lower()}")
    print(f"Latest edit report: {latest_paths['edit_report']}")
    print(f"Latest updated params: {latest_paths['updated_params']}")
    if result["cad_exported"]:
        print(f"Latest edited STEP: {latest_paths['step']}")
        print(f"Latest edited STL:  {latest_paths['stl']}")
    else:
        print("Latest edited STEP: not exported in dry run")
        print("Latest edited STL:  not exported in dry run")
    print(f"Latest validation report: {latest_paths['validation_report']}")
    print(f"Persistent edit report: {persistent_paths['edit_report']}")
    print(f"Persistent updated params: {persistent_paths['updated_params']}")
    if result["cad_exported"]:
        print(f"Persistent edited STEP: {persistent_paths['step']}")
        print(f"Persistent edited STL:  {persistent_paths['stl']}")
    else:
        print("Persistent edited STEP: not exported in dry run")
        print("Persistent edited STL:  not exported in dry run")
    print(f"Persistent validation report: {persistent_paths['validation_report']}")
    return 0 if result["validation_valid"] else 1


def _build_example_model(example: str = "bracket") -> int:
    result = build_example_workflow(example, _project_root() / "output")
    if not result["ok"]:
        print(result.get("message", f"Failed to build {example} example."))
        return 1
    print(f"Built {result['parameters']['family']} example.")
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


def _validate_example_model(example: str = "bracket") -> int:
    result = validate_example_workflow(example, _project_root() / "output")
    if not result["ok"] and "valid" not in result:
        print(result.get("message", f"Failed to validate {example} example."))
        return 1
    print(f"Validated {example} example.")
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


def _format_status(ok: bool, warning: bool = False) -> str:
    if ok:
        return "ok"
    return "warning" if warning else "fail"


def _package_installed(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _cadquery_required_message(command: str) -> str:
    return (
        f"CadQuery is required to run `{command}` because it builds and validates real CAD models. "
        "Install it with: python -m pip install -e '.[cad]'"
    )


def _check_output_writable(output_dir: Path) -> tuple[bool, str]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe_path = output_dir / ".intentforge_doctor_write_test"
        probe_path.write_text("ok\n", encoding="utf-8")
        probe_path.unlink()
    except OSError as exc:
        return False, str(exc)
    return True, str(output_dir)


def _doctor_command() -> int:
    project_root = _project_root()
    core_checks: list[tuple[str, bool, str]] = []
    optional_checks: list[tuple[str, bool, str]] = []

    python_ok = sys.version_info >= (3, 10)
    core_checks.append(
        (
            "Python version",
            python_ok,
            f"{platform.python_version()} (requires >= 3.10)",
        )
    )

    try:
        module = importlib.import_module("intentforge")
        import_ok = True
        import_detail = f"imported from {Path(module.__file__).parent}"
    except Exception as exc:  # pragma: no cover - difficult to trigger without breaking import
        import_ok = False
        import_detail = str(exc)
    core_checks.append(("intentforge import", import_ok, import_detail))

    examples_dir = project_root / "examples"
    benchmark_dir = project_root / "benchmark"
    core_checks.append(("examples directory", examples_dir.is_dir(), str(examples_dir)))
    core_checks.append(("benchmark directory", benchmark_dir.is_dir(), str(benchmark_dir)))

    output_ok, output_detail = _check_output_writable(project_root / "output")
    core_checks.append(("output directory writable", output_ok, output_detail))

    optional_checks.append(
        (
            "CadQuery",
            _package_installed("cadquery"),
            "installed" if _package_installed("cadquery") else "missing; CAD export commands require the cad extra",
        )
    )
    optional_checks.append(
        (
            "pytest",
            _package_installed("pytest"),
            "installed" if _package_installed("pytest") else "missing; install the dev extra to run tests",
        )
    )
    optional_checks.append(
        (
            "MCP package",
            _package_installed("mcp"),
            "installed" if _package_installed("mcp") else "missing; MCP support is optional",
        )
    )

    print("IntentForge doctor")
    print("Core checks:")
    for name, ok, detail in core_checks:
        print(f"  [{_format_status(ok)}] {name}: {detail}")

    print("Optional packages:")
    for name, ok, detail in optional_checks:
        print(f"  [{_format_status(ok, warning=True)}] {name}: {detail}")

    print("Supported model families:")
    for family in SUPPORTED_MODEL_FAMILIES:
        print(f"  - {family}")
    print("Harness commands:")
    print("  - inspect-shape")
    print("  - volume-delta")
    print("  - sweep")
    print("  - edit-harness")
    print("  - adversarial-harness")
    print("  - technical-harness")

    core_ok = all(ok for _, ok, _ in core_checks)
    print(f"Doctor result: {'core checks passed' if core_ok else 'core checks failed'}")
    return 0 if core_ok else 1


def _print_metric(name: str, value: object, unit: str = "") -> None:
    suffix = f" {unit}" if unit and value is not None else ""
    print(f"{name}: {value if value is not None else 'unavailable'}{suffix}")


def _inspect_shape_command(family: str) -> int:
    if family == "wall_mounted_bracket":
        parameter_table = _load_bracket_parameters()
        model = build_wall_bracket(parameter_table)
    elif family == "l_bracket":
        parameter_table = _load_l_bracket_parameters()
        model = build_l_bracket(parameter_table)
    else:
        print(f"Unsupported shape family: {family}")
        return 1

    report = inspect_shape(model, family=parameter_table.family)
    report_path = _project_root() / "output" / "harness" / "topology_report.json"
    write_shape_inspection_report(report, report_path)

    print(f"Inspected shape: {parameter_table.family}")
    bbox = report.bounding_box_dimensions_mm or {}
    if bbox:
        print(f"Bounding box: x={bbox.get('x')} mm, y={bbox.get('y')} mm, z={bbox.get('z')} mm")
    else:
        print("Bounding box: unavailable")
    _print_metric("Volume", report.volume_mm3, "mm^3")
    _print_metric("Solid count", report.solid_count)
    _print_metric("Face count", report.face_count)
    _print_metric("Edge count", report.edge_count)
    _print_metric("Vertex count", report.vertex_count)
    print(f"Shape valid: {report.is_valid if report.is_valid is not None else 'unavailable'}")
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"  - {warning.metric}: {warning.message}")
    else:
        print("Warnings: none")
    print(f"Topology report: {report_path}")
    return 0


def _example_parameter_table_for_family(family: str) -> ParameterTable:
    if family == "wall_mounted_bracket":
        return _load_bracket_parameters()
    if family == "l_bracket":
        return _load_l_bracket_parameters()
    raise ValueError(f"Unsupported model family: {family}")


def _build_example_model_for_table(parameter_table: ParameterTable):
    if parameter_table.family == "l_bracket":
        return build_l_bracket(parameter_table)
    return build_wall_bracket(parameter_table)


def _volume_delta_command(family: str) -> int:
    parameter_table = _example_parameter_table_for_family(family)
    model = _build_example_model_for_table(parameter_table)
    active_features, omitted_features = feature_state_names(parameter_table)

    harness_root = _project_root() / "output" / "harness"
    run_context = create_run_context(f"volume-delta {family}", harness_root, "volume_delta_runs")
    latest_report_path = harness_root / "volume_delta_report.json"
    persistent_report_path = run_context.run_dir / "volume_delta_report.json"
    output_paths = {
        "latest_report": latest_report_path,
        "persistent_report": persistent_report_path,
    }
    report = build_volume_delta_report(
        parameter_table,
        model,
        run_id=run_context.run_id,
        active_features=active_features,
        omitted_features=omitted_features,
        output_paths=json_safe_paths(output_paths),
    )
    write_volume_delta_report(report, latest_report_path)
    write_volume_delta_report(report, persistent_report_path)

    print(f"Volume delta run: {run_context.run_id}")
    print(f"Object type: {parameter_table.family}")
    print(f"Active features: {', '.join(active_features) if active_features else 'none'}")
    print(f"Feature model volume: {report['feature_volume_mm3']} mm^3")
    print("Checks:")
    if not report["checks"]:
        print("  - none")
    for check in report["checks"]:
        print(
            f"  - {check['id']}: status={check['status']}, "
            f"expected={check['expected_delta_mm3']}, actual={check['actual_delta_mm3']}, "
            f"baseline={check['baseline_volume_mm3']}"
        )
        if check["warnings"]:
            for warning in check["warnings"]:
                print(f"    warning: {warning}")
    print(f"Passed: {str(report['passed']).lower()}")
    print(f"Latest report: {latest_report_path}")
    print(f"Persistent report: {persistent_report_path}")
    return 0 if report["passed"] else 1


def _sweep_command(max_cases_per_family: int, no_export: bool) -> int:
    result = run_parametric_sweep(
        _project_root() / "output",
        max_cases_per_family=max_cases_per_family,
        export_enabled=not no_export,
    )
    print(f"Sweep run: {result['run_id']}")
    print(f"Total cases: {result['total_cases']}")
    print(f"Passed: {result['passed']}")
    print(f"Failed: {result['failed']}")
    print(f"Pass rate: {result['pass_rate']:.4f}")
    print("Families:")
    for family, counts in result["families"].items():
        print(f"  - {family}: passed {counts['passed']}, failed {counts['failed']}, total {counts['total']}")
    print("Failure types:")
    for failure_type, count in result["failure_types"].items():
        print(f"  - {failure_type}: {count}")
    print(f"Report path: {result['report_path']}")
    print(f"Summary path: {result['summary_path']}")
    print(f"Persistent output dir: {result['persistent_output_dir']}")
    failed_ids = [case["id"] for case in result["failed_cases"]]
    print(f"Failed case IDs: {', '.join(failed_ids) if failed_ids else 'none'}")
    return 0 if result["failed"] == 0 else 1


def _edit_harness_command(max_chains: int | None, no_export: bool) -> int:
    if not _package_installed("cadquery"):
        print(_cadquery_required_message("edit-harness"))
        return 1
    result = run_edit_preservation_harness(
        _project_root() / "output",
        max_chains=max_chains,
        export_enabled=not no_export,
    )
    print(f"Edit preservation run: {result['run_id']}")
    print(f"Total chains: {result['total_chains']}")
    print(f"Passed chains: {result['passed_chains']}")
    print(f"Failed chains: {result['failed_chains']}")
    print(f"Total edit steps: {result['total_edit_steps']}")
    print(f"Edit preservation rate: {result['edit_preservation_rate']:.4f}")
    print("Families:")
    for family, counts in result["families"].items():
        print(f"  - {family}: passed {counts['passed']}, failed {counts['failed']}, total {counts['total']}")
    print("Failure types:")
    for failure_type, count in result["failure_types"].items():
        print(f"  - {failure_type}: {count}")
    print(f"Report path: {result['report_path']}")
    print(f"Summary path: {result['summary_path']}")
    print(f"Persistent output dir: {result['persistent_output_dir']}")
    failed_ids = result.get("failed_chain_ids", [])
    print(f"Failed chain IDs: {', '.join(failed_ids) if failed_ids else 'none'}")
    return 0 if not failed_ids else 1


def _adversarial_harness_command(max_cases: int | None) -> int:
    result = run_adversarial_harness(
        _project_root() / "output",
        max_cases=max_cases,
    )
    print(f"Adversarial rejection run: {result['run_id']}")
    print(f"Total cases: {result['total_cases']}")
    print(f"Passed: {result['passed']}")
    print(f"Failed: {result['failed']}")
    print(f"Rejection success rate: {result['rejection_success_rate']:.4f}")
    print("Categories:")
    for category, counts in result["categories"].items():
        print(f"  - {category}: passed {counts['passed']}, failed {counts['failed']}, total {counts['total']}")
    print("Failure types:")
    for failure_type, count in result["failure_types"].items():
        print(f"  - {failure_type}: {count}")
    print(f"Report path: {result['report_path']}")
    print(f"Summary path: {result['summary_path']}")
    print(f"Persistent output dir: {result['persistent_output_dir']}")
    failed_ids = [case["id"] for case in result["failed_cases"]]
    print(f"Failed case IDs: {', '.join(failed_ids) if failed_ids else 'none'}")
    return 0 if result["failed"] == 0 else 1


def _technical_harness_command(quick: bool, include_demo: bool) -> int:
    if not _package_installed("cadquery"):
        print(_cadquery_required_message("technical-harness"))
        return 1
    result = run_technical_harness(
        _project_root() / "output",
        quick=quick,
        include_demo=include_demo,
    )
    metrics = result["metrics"]
    print(f"Technical harness run: {result['run_id']}")
    print(f"Overall passed: {str(result['overall_passed']).lower()}")
    print(f"Quality gates passed: {str(result['quality_gates_passed']).lower()}")
    print(f"Benchmark pass rate: {metrics['benchmark_pass_rate']:.4f}")
    print(f"Sweep pass rate: {metrics['sweep_pass_rate']:.4f}")
    print(f"Edit preservation rate: {metrics['edit_preservation_rate']:.4f}")
    print(f"Adversarial rejection success rate: {metrics['adversarial_rejection_success_rate']:.4f}")
    if result["failed_gates"]:
        print("Failed gates:")
        for gate in result["failed_gates"]:
            print(
                f"  - {gate['gate']}: actual {gate['actual']} "
                f"must be {gate['operator']} {gate['expected']}"
            )
    else:
        print("Failed gates: none")
    print(f"Report path: {result['output_paths']['latest_report']}")
    print(f"Summary path: {result['output_paths']['latest_summary']}")
    print(f"Persistent output dir: {result['persistent_output_dir']}")
    return 0 if result["overall_passed"] else 1


def _serve_command(host: str, port: int, token: str | None) -> int:
    """Start the IntentForge HTTP API server (delegates to intentforge.api.server)."""

    from intentforge.api.server import serve
    return serve(host=host, port=port, token=token)


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="intentforge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_example = subparsers.add_parser(
        "build-example",
        help="Build a bundled example model.",
    )
    build_example.add_argument(
        "example",
        choices=["bracket", "l_bracket"],
        help="Example model to build.",
    )

    validate_example = subparsers.add_parser(
        "validate-example",
        help="Validate a bundled example model.",
    )
    validate_example.add_argument(
        "example",
        choices=["bracket", "l_bracket"],
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
    parse_build.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse, build in memory, and validate without exporting STEP/STL files.",
    )

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
        choices=["bracket", "l_bracket"],
        help="Example model to edit.",
    )
    edit_parse_apply.add_argument("edit_text", nargs="+", help="Edit request text to parse and apply.")
    edit_parse_apply.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse, apply in memory, and validate without exporting edited STEP/STL files.",
    )

    llm_parse = subparsers.add_parser(
        "llm-parse",
        help="Use an optional LLM provider to translate a prompt into guarded IntentForge intent JSON.",
    )
    llm_parse.add_argument("prompt", nargs="+", help="Prompt text to translate.")
    llm_parse.add_argument(
        "--mock-provider",
        action="store_true",
        help="Use the deterministic mock LLM provider.",
    )

    llm_parse_build = subparsers.add_parser(
        "llm-parse-build",
        help="LLM-translate a prompt, guard the schema, then build through the deterministic CAD core.",
    )
    llm_parse_build.add_argument("prompt", nargs="+", help="Prompt text to translate and build.")
    llm_parse_build.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate feasibility without exporting STEP/STL files.",
    )
    llm_parse_build.add_argument(
        "--mock-provider",
        action="store_true",
        help="Use the deterministic mock LLM provider.",
    )

    llm_edit_parse = subparsers.add_parser(
        "llm-edit-parse",
        help="Use an optional LLM provider to translate edit text into guarded edit JSON.",
    )
    llm_edit_parse.add_argument(
        "object_type",
        choices=["wall_mounted_bracket", "bracket", "l_bracket"],
        help="Supported target object type.",
    )
    llm_edit_parse.add_argument("edit_text", nargs="+", help="Edit text to translate.")
    llm_edit_parse.add_argument(
        "--mock-provider",
        action="store_true",
        help="Use the deterministic mock LLM provider.",
    )

    llm_edit_apply = subparsers.add_parser(
        "llm-edit-apply",
        help="LLM-translate an edit, guard it, then apply through the deterministic CAD core.",
    )
    llm_edit_apply.add_argument(
        "object_type",
        choices=["wall_mounted_bracket", "bracket", "l_bracket"],
        help="Supported target object type.",
    )
    llm_edit_apply.add_argument("edit_text", nargs="+", help="Edit text to translate and apply.")
    llm_edit_apply.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the edit without exporting STEP/STL files.",
    )
    llm_edit_apply.add_argument(
        "--mock-provider",
        action="store_true",
        help="Use the deterministic mock LLM provider.",
    )

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

    subparsers.add_parser(
        "doctor",
        help="Check local IntentForge development environment health.",
    )

    inspect_shape_parser = subparsers.add_parser(
        "inspect-shape",
        help="Inspect topology metrics for a bundled example model.",
    )
    inspect_shape_parser.add_argument(
        "family",
        choices=["wall_mounted_bracket", "l_bracket"],
        help="Supported model family to build and inspect.",
    )

    volume_delta = subparsers.add_parser(
        "volume-delta",
        help="Run approximate volume delta checks for a bundled example model.",
    )
    volume_delta.add_argument(
        "family",
        choices=["wall_mounted_bracket", "l_bracket"],
        help="Supported model family to compare.",
    )

    sweep = subparsers.add_parser(
        "sweep",
        help="Run the deterministic parametric sweep harness.",
    )
    sweep.add_argument(
        "--max-cases-per-family",
        type=int,
        default=50,
        help="Maximum sampled cases per supported family.",
    )
    sweep.add_argument(
        "--no-export",
        action="store_true",
        help="Skip STEP/STL export for sweep cases.",
    )

    edit_harness = subparsers.add_parser(
        "edit-harness",
        help="Run the edit preservation harness.",
    )
    edit_harness.add_argument(
        "--max-chains",
        type=int,
        default=None,
        help="Maximum number of edit chains to run.",
    )
    edit_harness.add_argument(
        "--no-export",
        action="store_true",
        help="Skip STEP/STL export for edit chains.",
    )

    adversarial_harness = subparsers.add_parser(
        "adversarial-harness",
        help="Run adversarial rejection checks.",
    )
    adversarial_harness.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Maximum number of adversarial cases to run.",
    )

    technical_harness = subparsers.add_parser(
        "technical-harness",
        help="Run the unified technical harness and quality gates.",
    )
    technical_harness.add_argument(
        "--quick",
        action="store_true",
        help="Run a reduced sweep while still exercising all harness sections.",
    )
    technical_harness.add_argument(
        "--include-demo",
        action="store_true",
        help="Include the release demo workflow in the technical harness.",
    )

    interactive_parser = subparsers.add_parser(
        "interactive",
        help="Start the interactive IntentForge terminal client (Claude Code-like experience).",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the IntentForge HTTP API server (requires fastapi + uvicorn).",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1).",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Bind port (default: 8765).",
    )
    serve_parser.add_argument(
        "--token",
        default=None,
        help="API bearer token. If not set, reads INTENTFORGE_API_TOKEN env var. "
        "If neither is set, auth is disabled.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the IntentForge CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "build-example":
            return _build_example_model(args.example)
        if args.command == "validate-example":
            return _validate_example_model(args.example)
        if args.command == "edit-example" and args.example == "bracket":
            return _edit_example_bracket(args.edit_json)
        if args.command == "parse":
            return _parse_command(args.prompt)
        if args.command == "parse-build":
            return _parse_build_command(args.prompt, args.dry_run)
        if args.command == "edit-parse":
            return _edit_parse_command(args.edit_text)
        if args.command == "edit-parse-apply":
            return _edit_parse_apply_command(args.example, args.edit_text, args.dry_run)
        if args.command == "llm-parse":
            return _llm_parse_command(args.prompt, args.mock_provider)
        if args.command == "llm-parse-build":
            return _llm_parse_build_command(args.prompt, args.mock_provider, args.dry_run)
        if args.command == "llm-edit-parse":
            return _llm_edit_parse_command(args.object_type, args.edit_text, args.mock_provider)
        if args.command == "llm-edit-apply":
            return _llm_edit_apply_command(args.object_type, args.edit_text, args.mock_provider, args.dry_run)
        if args.command == "benchmark":
            if not _package_installed("cadquery"):
                print(_cadquery_required_message("benchmark"))
                return 1
            result = run_benchmark(args.output_root or (_project_root() / "output"))
            print(result["summary"], end="")
            print(f"Report path: {result['report_path']}")
            print(f"Failed case IDs: {', '.join(case['id'] for case in result['failed_cases']) if result['failed_cases'] else 'none'}")
            return 0 if result["failed"] == 0 else 1
        if args.command == "demo":
            return _demo_command(args.output_root)
        if args.command == "doctor":
            return _doctor_command()
        if args.command == "inspect-shape":
            return _inspect_shape_command(args.family)
        if args.command == "volume-delta":
            return _volume_delta_command(args.family)
        if args.command == "sweep":
            return _sweep_command(args.max_cases_per_family, args.no_export)
        if args.command == "edit-harness":
            return _edit_harness_command(args.max_chains, args.no_export)
        if args.command == "adversarial-harness":
            return _adversarial_harness_command(args.max_cases)
        if args.command == "technical-harness":
            return _technical_harness_command(args.quick, args.include_demo)
        if args.command == "interactive":
            from intentforge.client.repl import run_interactive
            run_interactive()
            return 0
        if args.command == "serve":
            return _serve_command(args.host, args.port, args.token)
    except CadQueryUnavailableError as exc:
        parser.exit(1, f"{exc}\n")
    except LLMProviderUnavailableError as exc:
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
