"""Command-line entry point for IntentForge."""

from argparse import ArgumentParser
import importlib
import importlib.resources
import importlib.util
import json
import platform
from pathlib import Path
import sys

import yaml

from intentforge.assurance import (
    attach_assurance_predecessor,
    build_assurance_from_prompt,
    build_audit_package,
    compare_assurance_cases,
    inspect_audit_package,
    render_assurance_markdown,
    validate_assurance_case,
    validate_audit_package,
)
from intentforge.assurance.schema import AssuranceCase
from intentforge.review import (
    ReviewEvaluationError,
    ReviewPolicyError,
    compare_review_decisions,
    diff_review_decisions,
    diff_review_variants,
    evaluate_assurance_case,
    get_review_policy,
    load_review_decision,
    load_review_decision_source,
    load_review_policies,
    render_decision_provenance_markdown,
    render_multi_variant_diff_markdown,
    render_review_decision_markdown,
    render_review_diff_markdown,
    validate_review_decision,
    validate_review_policy_manifest,
    verify_decision_provenance,
    verify_offline_audit_package,
    store_audit_package,
    validate_cas_address,
    verify_audit_chain,
)

from harness.topology import (
    build_volume_delta_report,
    inspect_shape,
    recognize_features,
    write_feature_recognition_report,
    write_feature_recognition_summary,
    write_shape_inspection_report,
    write_volume_delta_report,
)
from harness.adversarial import run_adversarial_harness
from harness.sweeps import run_parametric_sweep
from harness.edits import run_edit_preservation_harness
from intentforge.editor.edit_intent_handler import apply_edit_request, write_edit_report
from intentforge.example_data import load_example_json, load_example_yaml
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
from intentforge.knowledge import (
    ALLOWED_CONFLICT_TYPES,
    ALLOWED_INTERACTION_TYPES,
    ALLOWED_PRIORITIES,
    RulePackRegistry,
    RuleRegistry,
    REASONING_ENGINE_VERSION,
    build_capability_matrix,
    build_all_evidence_bundles,
    build_design_metrics,
    build_coverage_report,
    build_engineering_reasoning_report,
    evaluate_parameter_table,
    filter_evidence_bundles,
    generate_design_rationale,
    generate_trust_report,
    load_evidence_definitions,
    load_rules,
    make_knowledge_report,
    render_engineering_reasoning_markdown,
    resolve_evidence,
    validate_capability_manifest,
    validate_evidence_manifest,
    validate_reasoning_metadata,
    validate_default_rule_packs,
    validate_rule_data,
    verify_evidence,
    write_engineering_reasoning_markdown,
    write_engineering_reasoning_report,
    write_knowledge_report,
)
from intentforge.knowledge.reasoning.benchmark import run_reasoning_benchmark
from intentforge.knowledge.reasoning.verification import run_reasoning_verification
from intentforge.output_manager import (
    build_run_metadata,
    create_parsed_run_context,
    create_run_context,
    feature_state_names,
    json_safe_paths,
    write_run_metadata,
)
from intentforge.paths import project_root
from intentforge.parser import UnsupportedEditError, UnsupportedObjectError, parse_edit_request, parse_prompt
from intentforge.reports.design_review import (
    generate_design_review_report,
    write_design_review_report,
    write_design_review_summary,
)
from intentforge.schemas import ConstraintGraph, FeaturePlan, IntentSpec, ParameterTable, ValidationReport
from intentforge.topology.registry import registered_family_ids
from intentforge.validator.geometry_validator import validate_geometry, validate_wall_bracket, write_validation_report
from intentforge.validator.intent_validator import validate_wall_bracket_intent
from intentforge.workflows import (
    build_example_workflow,
    edit_parse_apply_workflow,
    edit_parse_workflow,
    parse_build_workflow,
    parse_build_intent_workflow,
    parse_prompt_workflow,
    validate_example_workflow,
)
from benchmark.run_benchmark import run_benchmark
from intentforge.demo_runner import run_demo
from harness.orchestrator import run_technical_harness
from intentforge.redaction import (
    export_redacted_package,
    load_redaction_config,
    verify_redacted_audit_package,
    default_redaction_config,
)

SUPPORTED_MODEL_FAMILIES = list(registered_family_ids())


def _topology_command(args) -> int:
    from intentforge.topology.registry import get_topology_registry
    from intentforge.parser.registered_parser import build_registered_intent_json_schema

    registry = get_topology_registry()
    if args.topology_command == "list":
        payload = [
            {
                "family": item.topology_family,
                "version": item.manifest_version,
                "status": item.status,
                "parameters": len(item.controlled_parameters),
                "features": len(item.supported_features),
                "factory": item.geometry_factory_id,
            }
            for item in registry.all()
        ]
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("IntentForge Registered Topology Families")
            for item in payload:
                print(f"{item['family']} v{item['version']} ({item['status']})")
                print(f"  parameters: {item['parameters']}; features: {item['features']}; factory: {item['factory']}")
        return 0
    if args.topology_command == "validate":
        evidence_ids = {item.evidence_id for item in load_evidence_definitions()}
        rule_ids = {item.id for item in RuleRegistry.load().rules}
        errors: list[str] = []
        for manifest in registry.all():
            binding = manifest.capability_evidence_binding
            errors.extend(
                f"{manifest.topology_family}: unknown evidence {item}"
                for item in sorted(set(binding.evidence_catalog_ids + binding.applicable_evidence_ids) - evidence_ids)
            )
            errors.extend(
                f"{manifest.topology_family}: unknown rule {item}"
                for item in sorted(set(binding.rule_ids) - rule_ids)
            )
        print("IntentForge Topology Registry Validation")
        print("PASS" if not errors else "FAIL")
        print(f"Families checked: {registry.count()}")
        for error in errors:
            print(f"- {error}")
        return 0 if not errors else 1
    if args.topology_command == "schema":
        print(json.dumps(build_registered_intent_json_schema(args.family), indent=2, sort_keys=True))
        return 0
    if args.topology_command == "build-json":
        payload = json.loads(Path(args.intent_path).read_text(encoding="utf-8"))
        result = parse_build_intent_workflow(payload, args.output_root, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("IntentForge Registered Topology Build")
            print("PASS" if result.get("ok") else "FAIL")
            print(f"Family: {result.get('object_type')}")
            print(f"CAD exported: {str(result.get('cad_exported', False)).lower()}")
            print(f"Validation passed: {str(result.get('validation_valid', False)).lower()}")
            for artifact in result.get("artifacts", []):
                if artifact.get("path"):
                    print(f"- {artifact.get('kind')}: {artifact['path']}")
            if not result.get("ok"):
                print(f"Error: {(result.get('error') or {}).get('message', result.get('message', 'unknown error'))}")
        return 0 if result.get("ok") else 1
    raise ValueError(f"unsupported topology action: {args.topology_command}")


def _project_root() -> Path:
    return project_root()


def _load_bracket_parameters() -> ParameterTable:
    return ParameterTable.model_validate(load_example_yaml("bracket_params.yaml"))


def _load_l_bracket_parameters() -> ParameterTable:
    return ParameterTable.model_validate(load_example_yaml("l_bracket_params.yaml"))


def _load_json_example(filename: str) -> dict:
    return load_example_json(filename)


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


def _load_l_bracket_intent() -> IntentSpec:
    return IntentSpec.model_validate(_load_json_example("l_bracket_intent.json"))


def _load_l_bracket_feature_plan() -> FeaturePlan:
    return FeaturePlan.model_validate(_load_json_example("l_bracket_feature_plan.json"))


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
        "Install it with: python -m pip install \"intentforge[cad]\""
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

    try:
        benchmark_prompts = importlib.resources.files("benchmark").joinpath("prompts")
        benchmark_ok = benchmark_prompts.is_dir()
        benchmark_detail = str(benchmark_prompts)
    except Exception as exc:  # pragma: no cover - importlib.resources failures vary
        benchmark_ok = False
        benchmark_detail = str(exc)
    core_checks.append(("benchmark package data", benchmark_ok, benchmark_detail))

    examples_dir = project_root / "examples"
    examples_detail = str(examples_dir) if examples_dir.is_dir() else "not found (dev-only; not included in PyPI install)"
    optional_checks.append(("examples directory", examples_dir.is_dir(), examples_detail))

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


def _example_intent_for_family(family: str) -> IntentSpec:
    if family == "l_bracket":
        return _load_l_bracket_intent()
    if family == "wall_mounted_bracket":
        return _load_bracket_intent()
    raise ValueError(f"Unsupported model family: {family}")


def _example_feature_plan_for_family(family: str) -> FeaturePlan:
    if family == "l_bracket":
        return _load_l_bracket_feature_plan()
    if family == "wall_mounted_bracket":
        return _load_bracket_feature_plan()
    raise ValueError(f"Unsupported model family: {family}")


def _write_text_data(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _recognize_features_command(family: str, output: str | None = None, no_export: bool = False) -> int:
    del no_export
    parameter_table = _example_parameter_table_for_family(family)
    feature_plan = _example_feature_plan_for_family(family)
    model = _build_example_model_for_table(parameter_table)

    harness_root = _project_root() / "output" / "harness"
    run_context = create_run_context(f"feature-recognition {family}", harness_root, "feature_recognition_runs")
    latest_report_path = Path(output) if output else harness_root / "feature_recognition_report.json"
    if not latest_report_path.is_absolute():
        latest_report_path = _project_root() / latest_report_path
    latest_summary_path = harness_root / "feature_recognition_summary.txt"
    persistent_report_path = run_context.run_dir / "feature_recognition_report.json"
    persistent_summary_path = run_context.run_dir / "feature_recognition_summary.txt"

    report = recognize_features(model, parameter_table, feature_plan)
    report["run_id"] = run_context.run_id
    report["created_at"] = run_context.created_at.isoformat()
    report["output_paths"] = json_safe_paths(
        {
            "latest_report": latest_report_path,
            "latest_summary": latest_summary_path,
            "persistent_report": persistent_report_path,
            "persistent_summary": persistent_summary_path,
        }
    )
    write_feature_recognition_report(report, latest_report_path)
    write_feature_recognition_report(report, persistent_report_path)
    write_feature_recognition_summary(report, latest_summary_path)
    write_feature_recognition_summary(report, persistent_summary_path)

    print(f"Feature recognition run: {run_context.run_id}")
    print(f"Object type: {parameter_table.family}")
    print(f"Passed: {str(report['passed']).lower()}")
    print("Recognized features:")
    for name, result in report["recognized_features"].items():
        count = ""
        if "expected_count" in result or "recognized_count" in result:
            count = f", expected={result.get('expected_count')}, recognized={result.get('recognized_count')}"
        print(f"  - {name}: passed={str(result.get('passed')).lower()}, confidence={result.get('confidence')}{count}")
    print(f"Warnings: {len(report['warnings'])}")
    print(f"Latest report: {latest_report_path}")
    print(f"Latest summary: {latest_summary_path}")
    print(f"Persistent report: {persistent_report_path}")
    print(f"Persistent summary: {persistent_summary_path}")
    return 0 if report["passed"] else 1


def _design_review_command(
    family: str,
    include_knowledge: bool = False,
    write_knowledge_json: bool = False,
    include_reasoning: bool = False,
) -> int:
    include_knowledge = include_knowledge or write_knowledge_json or include_reasoning
    parameter_table = _example_parameter_table_for_family(family)
    intent = _example_intent_for_family(family)
    feature_plan = _example_feature_plan_for_family(family)
    model = _build_example_model_for_table(parameter_table)
    topology_report = inspect_shape(model, family=parameter_table.family)
    validation_report = validate_geometry(model, parameter_table)
    active_features, omitted_features = feature_state_names(parameter_table)
    volume_delta_report = build_volume_delta_report(
        parameter_table,
        model,
        active_features=active_features,
        omitted_features=omitted_features,
    )
    feature_recognition_report = recognize_features(model, parameter_table, feature_plan)

    output_root = _project_root() / "output"
    run_context = create_run_context(f"design-review {family}", output_root, "design_review_runs")
    latest_report_path = output_root / "design_review_report.json"
    latest_summary_path = output_root / "design_review_summary.md"
    persistent_report_path = run_context.run_dir / "design_review_report.json"
    persistent_summary_path = run_context.run_dir / "design_review_summary.md"
    latest_rationale_path = output_root / "design_knowledge_rationale.md"
    persistent_rationale_path = run_context.run_dir / "design_knowledge_rationale.md"
    latest_knowledge_report_path = output_root / "knowledge_report.json"
    persistent_knowledge_report_path = run_context.run_dir / "knowledge_report.json"
    latest_reasoning_report_path = output_root / "engineering_reasoning_report.json"
    persistent_reasoning_report_path = run_context.run_dir / "engineering_reasoning_report.json"
    latest_reasoning_markdown_path = output_root / "engineering_reasoning_report.md"
    persistent_reasoning_markdown_path = run_context.run_dir / "engineering_reasoning_report.md"
    artifacts = [
        {"kind": "design_review_report", "path": str(latest_report_path), "persistent": False, "object_type": family},
        {"kind": "design_review_summary", "path": str(latest_summary_path), "persistent": False, "object_type": family},
        {"kind": "design_review_report", "path": str(persistent_report_path), "persistent": True, "object_type": family},
        {"kind": "design_review_summary", "path": str(persistent_summary_path), "persistent": True, "object_type": family},
    ]
    knowledge_findings = []
    design_rationale = None
    knowledge_report = None
    reasoning_report = None
    reasoning_markdown = None
    if include_knowledge:
        knowledge_findings = evaluate_parameter_table(parameter_table, feature_plan)
        design_rationale = generate_design_rationale(knowledge_findings)
        knowledge_report = make_knowledge_report(knowledge_findings, rules_checked=len(load_rules()))
        artifacts.extend(
            [
                {
                    "kind": "design_knowledge_rationale",
                    "path": str(latest_rationale_path),
                    "persistent": False,
                    "object_type": family,
                },
                {
                    "kind": "design_knowledge_rationale",
                    "path": str(persistent_rationale_path),
                    "persistent": True,
                    "object_type": family,
                },
            ]
        )
        if write_knowledge_json:
            artifacts.extend(
                [
                    {
                        "kind": "knowledge_report",
                        "path": str(latest_knowledge_report_path),
                        "persistent": False,
                        "object_type": family,
                    },
                    {
                        "kind": "knowledge_report",
                        "path": str(persistent_knowledge_report_path),
                        "persistent": True,
                        "object_type": family,
                    },
                ]
            )
        if include_reasoning:
            metrics = build_design_metrics(parameter_table, feature_plan)
            reasoning_report = build_engineering_reasoning_report(
                model_family=parameter_table.family,
                knowledge_report=knowledge_report,
                rule_registry=RuleRegistry.load(),
                metrics=metrics,
                parameters={parameter.name: parameter.value for parameter in parameter_table.parameters},
                feature_recognition_report=feature_recognition_report,
            )
            reasoning_markdown = render_engineering_reasoning_markdown(reasoning_report)
            artifacts.extend(
                [
                    {
                        "kind": "engineering_reasoning_report",
                        "path": str(latest_reasoning_markdown_path),
                        "persistent": False,
                        "object_type": family,
                    },
                    {
                        "kind": "engineering_reasoning_report",
                        "path": str(persistent_reasoning_markdown_path),
                        "persistent": True,
                        "object_type": family,
                    },
                ]
            )
            if write_knowledge_json:
                artifacts.extend(
                    [
                        {
                            "kind": "engineering_reasoning_json",
                            "path": str(latest_reasoning_report_path),
                            "persistent": False,
                            "object_type": family,
                        },
                        {
                            "kind": "engineering_reasoning_json",
                            "path": str(persistent_reasoning_report_path),
                            "persistent": True,
                            "object_type": family,
                        },
                    ]
                )
    report = generate_design_review_report(
        intent_spec=intent,
        parameter_table=parameter_table,
        feature_plan=feature_plan,
        validation_report=validation_report,
        topology_report=topology_report,
        volume_delta_report=volume_delta_report,
        feature_recognition_report=feature_recognition_report,
        knowledge_findings=knowledge_findings,
        knowledge_report=knowledge_report.model_dump(mode="json") if knowledge_report is not None else None,
        design_rationale=design_rationale,
        reasoning_report=reasoning_report.model_dump(mode="json") if reasoning_report is not None else None,
        artifacts=artifacts,
        run_id=run_context.run_id,
    )
    report["output_paths"] = json_safe_paths(
        {
            "latest_report": latest_report_path,
            "latest_summary": latest_summary_path,
            "persistent_report": persistent_report_path,
            "persistent_summary": persistent_summary_path,
            "latest_rationale": latest_rationale_path if include_knowledge else None,
            "persistent_rationale": persistent_rationale_path if include_knowledge else None,
            "latest_knowledge_report": latest_knowledge_report_path if write_knowledge_json else None,
            "persistent_knowledge_report": persistent_knowledge_report_path if write_knowledge_json else None,
            "latest_reasoning_report": latest_reasoning_report_path if include_reasoning and write_knowledge_json else None,
            "persistent_reasoning_report": persistent_reasoning_report_path if include_reasoning and write_knowledge_json else None,
            "latest_reasoning_markdown": latest_reasoning_markdown_path if include_reasoning else None,
            "persistent_reasoning_markdown": persistent_reasoning_markdown_path if include_reasoning else None,
        }
    )
    write_design_review_report(report, latest_report_path)
    write_design_review_summary(report, latest_summary_path)
    write_design_review_report(report, persistent_report_path)
    write_design_review_summary(report, persistent_summary_path)
    if include_knowledge and design_rationale is not None:
        latest_rationale_path.write_text(design_rationale, encoding="utf-8")
        persistent_rationale_path.write_text(design_rationale, encoding="utf-8")
    if write_knowledge_json and knowledge_report is not None:
        write_knowledge_report(knowledge_report, latest_knowledge_report_path)
        write_knowledge_report(knowledge_report, persistent_knowledge_report_path)
    if include_reasoning and reasoning_report is not None:
        write_engineering_reasoning_markdown(reasoning_report, latest_reasoning_markdown_path)
        write_engineering_reasoning_markdown(reasoning_report, persistent_reasoning_markdown_path)
        if write_knowledge_json:
            write_engineering_reasoning_report(reasoning_report, latest_reasoning_report_path)
            write_engineering_reasoning_report(reasoning_report, persistent_reasoning_report_path)

    print(f"Design review run: {run_context.run_id}")
    print(f"Object type: {parameter_table.family}")
    print(f"Validation valid: {str(validation_report.valid).lower()}")
    print(f"Feature recognition passed: {str(feature_recognition_report['passed']).lower()}")
    if include_knowledge:
        failed_knowledge_findings = [finding for finding in knowledge_findings if not finding.passed]
        print(f"Knowledge findings: {len(knowledge_findings)} total, {len(failed_knowledge_findings)} advisory findings")
        print(f"Knowledge rationale: {latest_rationale_path}")
        print(f"Persistent knowledge rationale: {persistent_rationale_path}")
        if write_knowledge_json:
            print(f"Knowledge JSON report: {latest_knowledge_report_path}")
            print(f"Persistent knowledge JSON report: {persistent_knowledge_report_path}")
    if include_reasoning and reasoning_report is not None:
        print(f"Reasoning report: {latest_reasoning_markdown_path}")
        print(f"Persistent reasoning report: {persistent_reasoning_markdown_path}")
        print(f"Reasoning recommendations: {len(reasoning_report.recommendations)}")
        if write_knowledge_json:
            print(f"Reasoning JSON report: {latest_reasoning_report_path}")
            print(f"Persistent reasoning JSON report: {persistent_reasoning_report_path}")
    print(f"Warnings: {len(report['warnings'])}")
    print(f"Latest report: {latest_report_path}")
    print(f"Latest summary: {latest_summary_path}")
    print(f"Persistent report: {persistent_report_path}")
    print(f"Persistent summary: {persistent_summary_path}")
    return 0 if validation_report.valid and feature_recognition_report["passed"] else 1


def _print_coverage_report(report) -> None:
    print("Engineering Knowledge Coverage")
    print("PASS" if report.passed else "FAIL")
    print(f"Report ID: {report.report_id}")
    print(f"Declared capabilities: {report.declared_capability_count}")
    print(f"Supported: {report.supported_capability_count}")
    print(f"Partially supported: {report.partially_supported_capability_count}")
    print(f"Unsupported boundaries: {report.unsupported_capability_count}")
    print(f"Not applicable: {report.not_applicable_capability_count}")
    print(f"Active rules: {report.active_rule_count}")
    print(f"Mapped active rules: {report.mapped_active_rule_count}")
    print(f"Orphan active rules: {report.orphan_active_rule_count}")
    print(f"Implementation evidence completeness: {report.implementation_evidence_completeness:.4f}")
    print(f"Verification evidence completeness: {report.verification_evidence_completeness:.4f}")
    print("Families:")
    for family, counts in report.per_family.items():
        print(
            f"  - {family}: total {counts['total']}, supported {counts['supported']}, "
            f"partial {counts['partially_supported']}, unsupported {counts['unsupported']}"
        )
    if report.validation_errors:
        print("Coverage gaps:")
        for error in report.validation_errors:
            prefix = error.get("capability_id") or error.get("rule_id") or "manifest"
            print(f"  - {prefix}: {error.get('message')}")
    else:
        print("Coverage gaps: none")


def _print_capability_matrix(matrix) -> None:
    print("Engineering Capability Matrix")
    print(f"Matrix ID: {matrix.matrix_id}")
    print(f"Capabilities: {len(matrix.rows)}")
    print("Status counts:")
    for status, count in matrix.summary.get("by_status", {}).items():
        print(f"  - {status}: {count}")
    print("")
    for row in matrix.rows:
        print(row.capability_id)
        print(f"  family: {row.family}")
        print(f"  status: {row.status}")
        print(f"  stages: {', '.join(row.stages)}")
        print(f"  packs: {', '.join(row.knowledge_packs) if row.knowledge_packs else 'none'}")
        print(f"  rules: {', '.join(row.rule_ids) if row.rule_ids else 'none'}")
        print(f"  implementation evidence: {row.implementation_evidence_count}")
        print(f"  verification evidence: {row.verification_evidence_count}")
        if row.limitations:
            print(f"  limitations: {'; '.join(row.limitations)}")
        if row.rejection_behavior:
            print(f"  rejection: {row.rejection_behavior}")


def _print_evidence_list(definitions) -> None:
    print("Engineering Evidence Definitions")
    print(f"Total: {len(definitions)}")
    for definition in definitions:
        print("")
        print(definition.evidence_id)
        print(f"  type: {definition.evidence_type}")
        print(f"  role: {definition.role}")
        print(f"  reference: {definition.reference}")
        print(f"  family: {definition.family or 'cross-cutting'}")
        print(f"  stages: {', '.join(definition.stages) if definition.stages else 'none'}")
        print(f"  capabilities: {', '.join(definition.capability_ids) if definition.capability_ids else 'none'}")
        print(f"  required: {str(definition.required).lower()}")


def _print_evidence_resolution(report) -> None:
    print("Engineering Evidence Resolution")
    print(f"Report ID: {report.report_id}")
    print(f"Runtime verification: {str(report.runtime_verification).lower()}")
    print(f"Evidence checked: {report.evidence_count}")
    print(f"Verified: {report.summary.get('verified_evidence_count', 0)}")
    print(f"Failed: {report.summary.get('failed_evidence_count', 0)}")
    print(f"Unresolved: {report.summary.get('unresolved_evidence_count', 0)}")
    print(f"Unavailable: {report.summary.get('unavailable_evidence_count', 0)}")
    print(f"Stale: {report.summary.get('stale_evidence_count', 0)}")
    for observation in report.observations:
        if observation.status != "verified":
            print(f"- {observation.evidence_id}: {observation.status} ({observation.observed_result})")


def _print_evidence_bundles(bundles) -> None:
    print("Engineering Evidence Bundles")
    print(f"Bundles: {len(bundles)}")
    for bundle in bundles:
        print("")
        print(bundle.capability_id)
        print(f"  family: {bundle.family}")
        print(f"  capability status: {bundle.capability_status}")
        print(f"  bundle status: {bundle.bundle_status}")
        print(f"  completeness: {bundle.evidence_completeness:.4f}")
        print(f"  required evidence: {len(bundle.required_evidence_ids)}")
        print(f"  unresolved: {', '.join(bundle.unresolved_evidence_ids) if bundle.unresolved_evidence_ids else 'none'}")
        print(f"  failed: {', '.join(bundle.failed_evidence_ids) if bundle.failed_evidence_ids else 'none'}")


def _print_trust_report(report) -> None:
    print("Engineering Evidence Trust Report")
    print("PASS" if report.overall_trust_gate_passed else "FAIL")
    print(f"Report ID: {report.report_id}")
    print(f"Runtime verification: {str(report.summary.get('runtime_verification', False)).lower()}")
    print(f"Declared capabilities: {report.declared_capability_count}")
    print(f"Supported capabilities: {report.supported_capability_count}")
    print(f"Partially supported capabilities: {report.partially_supported_capability_count}")
    print(f"Unsupported boundaries: {report.unsupported_boundary_count}")
    print(f"Evidence definitions: {report.total_evidence_definition_count}")
    print(f"Required evidence: {report.required_evidence_count}")
    print(f"Verified evidence: {report.verified_evidence_count}")
    print(f"Failed evidence: {report.failed_evidence_count}")
    print(f"Unresolved evidence: {report.unresolved_evidence_count}")
    print(f"Unavailable evidence: {report.unavailable_evidence_count}")
    print(f"Stale evidence: {report.stale_evidence_count}")
    impl = report.implementation_evidence_completeness
    ver = report.verification_evidence_completeness
    boundary = report.boundary_evidence_completeness
    limitation = report.limitation_evidence_completeness
    print(
        "Implementation evidence completeness: "
        f"{impl['value']:.4f} ({impl['numerator']}/{impl['denominator']})"
    )
    print(
        "Verification evidence completeness: "
        f"{ver['value']:.4f} ({ver['numerator']}/{ver['denominator']})"
    )
    print(
        "Boundary evidence completeness: "
        f"{boundary['value']:.4f} ({boundary['numerator']}/{boundary['denominator']})"
    )
    print(
        "Limitation evidence completeness: "
        f"{limitation['value']:.4f} ({limitation['numerator']}/{limitation['denominator']})"
    )
    if report.validation_errors:
        print("Evidence gaps:")
        for error in report.validation_errors:
            prefix = error.get("evidence_id") or error.get("capability_id") or "manifest"
            print(f"  - {prefix}: {error.get('message')}")
    else:
        print("Evidence gaps: none")


def _knowledge_command(args) -> int:
    action = args.knowledge_command
    if action == "list":
        registry = RuleRegistry.load()
        categories = sorted({rule.category for rule in registry.rules})
        print("Engineering Knowledge Rules")
        print(f"Total: {registry.count()}")
        for category in categories:
            print(f"{category.title()}: {len(registry.get_by_category(category))}")
        return 0
    if action == "packs":
        registry = RulePackRegistry.load_default()
        print("Engineering Knowledge Rule Packs")
        print(f"Total packs: {registry.count_packs()}")
        print(f"Total active rules: {registry.count_rules()}")
        for pack in registry.all_packs():
            active_rule_count = len([rule for rule in pack.rules if rule.status == "active"])
            print("")
            print(pack.pack_id)
            print(f"version: {pack.pack_version}")
            print(f"category: {pack.category}")
            print(f"status: {pack.status}")
            print(f"families: {', '.join(pack.supported_model_families)}")
            print(f"rules: {active_rule_count}")
        return 0
    if action == "validate":
        result = validate_rule_data()
        print("Knowledge validation")
        print("PASS" if result["ok"] else "FAIL")
        print(f"{result['rules_checked']} rules checked")
        print(f"{len(result['errors'])} errors")
        for error in result["errors"]:
            rule = error.get("rule_id") or f"index {error.get('index')}"
            print(f"- {rule}: {error.get('message')}")
        return 0 if result["ok"] else 1
    if action == "packs-validate":
        result = validate_default_rule_packs()
        print("Knowledge rule pack validation")
        print("PASS" if result.passed else "FAIL")
        print(f"{result.packs_checked} packs checked")
        print(f"{result.rules_checked} rules checked")
        print(f"{len(result.errors)} errors")
        print(f"{len(result.warnings)} warnings")
        for error in result.errors:
            pack = error.get("pack_id") or "unknown pack"
            rule = f" {error.get('rule_id')}" if error.get("rule_id") else ""
            field = f" {error.get('field')}" if error.get("field") else ""
            print(f"- {pack}{rule}{field}: {error.get('message')}")
        for warning in result.warnings:
            pack = warning.get("pack_id") or "unknown pack"
            print(f"- warning {pack}: {warning.get('message')}")
        return 0 if result.passed else 1
    if action == "coverage":
        report = build_coverage_report()
        if getattr(args, "json", False):
            print(report.to_json(), end="")
        else:
            _print_coverage_report(report)
        return 0 if report.passed else 1
    if action == "coverage-validate" or action == "capability-validate":
        result = validate_capability_manifest()
        print("Engineering capability validation")
        print("PASS" if result.passed else "FAIL")
        print(f"{result.capabilities_checked} capabilities checked")
        print(f"{len(result.errors)} errors")
        print(f"{len(result.warnings)} warnings")
        print(f"Active rules: {result.summary.get('active_rule_count', 0)}")
        print(f"Mapped active rules: {result.summary.get('mapped_active_rule_count', 0)}")
        print(f"Orphan active rules: {result.summary.get('orphan_active_rule_count', 0)}")
        print(f"Unknown references: {result.summary.get('unknown_rule_reference_count', 0) + result.summary.get('unknown_pack_reference_count', 0) + result.summary.get('unknown_evidence_reference_count', 0)}")
        for error in result.errors:
            prefix = error.get("capability_id") or error.get("rule_id") or "manifest"
            print(f"- {prefix}: {error.get('message')}")
        return 0 if result.passed else 1
    if action == "capability-matrix":
        matrix = build_capability_matrix(
            family=getattr(args, "family", None),
            status=getattr(args, "status", None),
            stage=getattr(args, "stage", None),
            knowledge_pack=getattr(args, "knowledge_pack", None),
            rule_id=getattr(args, "rule_id", None),
        )
        if getattr(args, "json", False):
            print(matrix.to_json(), end="")
        else:
            _print_capability_matrix(matrix)
        return 0
    if action == "evidence-list":
        definitions = load_evidence_definitions()
        if getattr(args, "family", None):
            definitions = [
                definition
                for definition in definitions
                if definition.family == args.family or args.family in definition.provenance.get("families", [])
            ]
        if getattr(args, "evidence_type", None):
            definitions = [definition for definition in definitions if definition.evidence_type == args.evidence_type]
        if getattr(args, "role", None):
            definitions = [definition for definition in definitions if definition.role == args.role]
        definitions = sorted(definitions, key=lambda definition: definition.evidence_id)
        if getattr(args, "json", False):
            print(json.dumps([definition.model_dump(mode="json") for definition in definitions], indent=2, sort_keys=True) + "\n", end="")
        else:
            _print_evidence_list(definitions)
        return 0
    if action == "evidence-show":
        definitions = load_evidence_definitions()
        definition = next((item for item in definitions if item.evidence_id == args.evidence_id), None)
        if definition is None:
            print(f"Unknown evidence id: {args.evidence_id}", file=sys.stderr)
            return 1
        if getattr(args, "json", False):
            print(json.dumps(definition.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", end="")
        else:
            _print_evidence_list([definition])
        return 0
    if action == "evidence-validate":
        result = validate_evidence_manifest()
        print("Engineering evidence validation")
        print("PASS" if result.passed else "FAIL")
        print(f"{result.evidence_checked} evidence definitions checked")
        print(f"{len(result.errors)} errors")
        print(f"{len(result.warnings)} warnings")
        print(f"Unknown capabilities: {result.summary.get('unknown_capability_reference_count', 0)}")
        print(f"Unknown rules: {result.summary.get('unknown_rule_reference_count', 0)}")
        print(f"Unknown packs: {result.summary.get('unknown_pack_reference_count', 0)}")
        print(f"Orphan evidence: {result.summary.get('orphan_evidence_count', 0)}")
        for error in result.errors:
            prefix = error.get("evidence_id") or error.get("capability_id") or "manifest"
            print(f"- {prefix}: {error.get('message')}")
        return 0 if result.passed else 1
    if action == "evidence-resolve":
        report = resolve_evidence()
        if getattr(args, "json", False):
            print(report.to_json(), end="")
        else:
            _print_evidence_resolution(report)
        return 0 if report.summary.get("failed_evidence_count", 0) == 0 and report.summary.get("unresolved_evidence_count", 0) == 0 else 1
    if action == "evidence-bundles":
        bundles = build_all_evidence_bundles(
            family=getattr(args, "family", None),
            capability_id=getattr(args, "capability_id", None),
        )
        if getattr(args, "json", False):
            print(json.dumps([bundle.model_dump(mode="json") for bundle in bundles], indent=2, sort_keys=True) + "\n", end="")
        else:
            _print_evidence_bundles(bundles)
        return 0 if all(bundle.bundle_status in {"evidence_complete", "boundary_verified"} for bundle in bundles) else 1
    if action == "trust-report":
        report = generate_trust_report(runtime=getattr(args, "verify", False))
        if getattr(args, "json", False):
            print(report.to_json(), end="")
        else:
            _print_trust_report(report)
        return 0 if report.overall_trust_gate_passed else 1
    if action == "trust-validate":
        report = generate_trust_report()
        print("Engineering evidence trust validation")
        print("PASS" if report.overall_trust_gate_passed else "FAIL")
        print(f"Evidence definitions: {report.total_evidence_definition_count}")
        print(f"Supported incomplete bundles: {len(report.supported_capabilities_with_incomplete_evidence)}")
        print(f"Partial missing limitation evidence: {len(report.partially_supported_capabilities_missing_limitation_evidence)}")
        print(f"Unsupported missing rejection evidence: {len(report.unsupported_boundaries_missing_rejection_evidence)}")
        print(f"Unknown references: {report.unknown_capability_reference_count + report.unknown_rule_reference_count + report.unknown_pack_reference_count}")
        return 0 if report.overall_trust_gate_passed else 1
    if action == "reasoning-info":
        print("Engineering reasoning engine")
        print(f"Version: {REASONING_ENGINE_VERSION}")
        print("Behavior: deterministic, offline, rule-driven")
        print("Supported interaction types:")
        for interaction_type in ALLOWED_INTERACTION_TYPES:
            print(f"  - {interaction_type}")
        print("Supported conflict types:")
        for conflict_type in ALLOWED_CONFLICT_TYPES:
            print(f"  - {conflict_type}")
        print("Supported priority levels:")
        for priority in ALLOWED_PRIORITIES:
            print(f"  - {priority}")
        print("Safety: no LLM, network, CadQuery, eval, or exec dependency in the reasoning core.")
        return 0
    if action == "reasoning-validate":
        result = validate_reasoning_metadata()
        print("Engineering reasoning validation")
        print("PASS" if result["ok"] else "FAIL")
        print(f"{result['rules_checked']} rules checked")
        print(f"{len(result['metadata_errors'])} metadata errors")
        print(f"{result['interaction_links_validated']} interaction links validated")
        print(f"{result['tradeoff_definitions_validated']} trade-off definitions validated")
        for error in result["metadata_errors"]:
            rule = error.get("rule_id") or "unknown rule"
            field = f" {error.get('field')}" if error.get("field") else ""
            print(f"- {rule}{field}: {error.get('message')}")
        return 0 if result["ok"] else 1
    if action == "reasoning-verify":
        return _reasoning_verification_command(benchmark_mode=False)
    if action == "reasoning-benchmark":
        return _reasoning_verification_command(benchmark_mode=True)
    print(f"Unsupported knowledge action: {action}")
    return 1


def _reasoning_verification_summary(result: dict, *, title: str) -> str:
    failed_ids = [case["id"] for case in result["failed_cases"]]
    return "\n".join(
        [
            title,
            f"Run ID: {result['run_id']}",
            f"Total cases: {result['total_cases']}",
            f"Passed: {result['passed']}",
            f"Failed: {result['failed']}",
            f"Pass rate: {result['pass_rate']:.4f}",
            f"Contradictions: {result['contradiction_count']}",
            f"Applicability errors: {result['applicability_error_count']}",
            f"Nondeterministic reports: {result['nondeterministic_report_count']}",
            f"Report ID mismatches: {result['report_id_mismatch_count']}",
            f"Failed case IDs: {', '.join(failed_ids) if failed_ids else 'none'}",
            f"Report path: {result['report_path']}",
            f"Summary path: {result['summary_path']}",
            f"Persistent output dir: {result['persistent_output_dir']}",
            "",
        ]
    )


def _reasoning_verification_command(*, benchmark_mode: bool) -> int:
    harness_root = _project_root() / "output" / "harness"
    run_context = create_run_context(
        "reasoning benchmark" if benchmark_mode else "reasoning verification",
        harness_root,
        "reasoning_verification_runs",
    )
    latest_report_path = harness_root / (
        "reasoning_benchmark_report.json" if benchmark_mode else "reasoning_verification_report.json"
    )
    latest_summary_path = harness_root / (
        "reasoning_benchmark_summary.txt" if benchmark_mode else "reasoning_verification_summary.txt"
    )
    persistent_report_path = run_context.run_dir / latest_report_path.name
    persistent_summary_path = run_context.run_dir / latest_summary_path.name

    result = run_reasoning_benchmark() if benchmark_mode else run_reasoning_verification()
    result = {
        **result,
        "run_id": run_context.run_id,
        "created_at": run_context.created_at.isoformat(),
        "report_path": str(latest_report_path),
        "summary_path": str(latest_summary_path),
        "persistent_report_path": str(persistent_report_path),
        "persistent_summary_path": str(persistent_summary_path),
        "persistent_output_dir": str(run_context.run_dir),
    }
    title = "Engineering reasoning benchmark" if benchmark_mode else "Engineering reasoning verification"
    result["summary"] = _reasoning_verification_summary(result, title=title)
    _write_json_data(result, latest_report_path)
    _write_json_data(result, persistent_report_path)
    _write_text_data(result["summary"], latest_summary_path)
    _write_text_data(result["summary"], persistent_summary_path)

    print(result["summary"], end="")
    return 0 if result["failed"] == 0 else 1


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
    print(f"Feature recognition pass rate: {metrics.get('feature_recognition_pass_rate', 0.0):.4f}")
    print(f"Feature recognition warnings: {metrics.get('feature_recognition_warning_count', 0)}")
    print(f"Reasoning generation pass rate: {metrics.get('reasoning_generation_pass_rate', 0.0):.4f}")
    print(f"Unknown reasoning rule references: {metrics.get('unknown_rule_reference_count', 0)}")
    print(f"Recommendation contradictions: {metrics.get('recommendation_contradiction_count', 0)}")
    print(f"Recommendation applicability errors: {metrics.get('recommendation_applicability_error_count', 0)}")
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


def _load_assurance_case(path: str | Path) -> AssuranceCase:
    return AssuranceCase.model_validate_json(Path(path).read_text(encoding="utf-8"))


REVIEW_EXIT_CODES = {
    "accepted_within_declared_scope": 0,
    "accepted_with_conditions": 2,
    "accepted_with_exemption": 2,
    "manual_review_required": 3,
    "rejected_by_policy": 4,
    "unresolved": 5,
}


def _write_review_decision(decision, output: str | Path) -> tuple[Path, Path]:
    json_path = Path(output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(decision.to_json(), encoding="utf-8")
    markdown_path = json_path.with_suffix(".md")
    markdown_path.write_text(render_review_decision_markdown(decision), encoding="utf-8")
    return json_path, markdown_path


def _resolve_predecessor_hash(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = Path(value)
    if candidate.is_dir():
        verification = verify_offline_audit_package(candidate)
        if not verification.passed or verification.package_id is None:
            raise ValueError("predecessor package failed offline verification")
        return validate_cas_address(verification.package_id)
    return validate_cas_address(value)


def _print_review_decision(decision, *, as_json: bool, json_path: Path | None = None, markdown_path: Path | None = None) -> None:
    if as_json:
        print(decision.to_json(), end="")
        return
    print("IntentForge Engineering Review Decision")
    print(f"Decision ID: {decision.decision_id}")
    print(f"Policy: {decision.policy_id} v{decision.policy_version}")
    print(f"Subject: {decision.subject_type}")
    print(f"Decision: {decision.decision_status}")
    print(f"Checks: {decision.passed_check_count} passed, {decision.failed_check_count} failed, {decision.unresolved_check_count} unresolved")
    print(f"Conditions: {len(decision.conditions)}")
    if decision.subject_type == "safe_rejection" and decision.decision_status == "accepted_within_declared_scope":
        print("Safe rejection handling passed policy; the unsupported design remains rejected.")
    if json_path is not None: print(f"Decision path: {json_path}")
    if markdown_path is not None: print(f"Markdown path: {markdown_path}")


def _review_command(args) -> int:
    action = args.review_command
    if action == "policies":
        policies = load_review_policies()
        if args.json:
            print(json.dumps([item.model_dump(mode="json", serialize_as_any=True) for item in policies], indent=2, sort_keys=True))
        else:
            print("IntentForge Engineering Review Policies")
            print(f"Policies: {len(policies)}")
            for policy in policies:
                print(f"- {policy.policy_id} v{policy.policy_version}: {policy.subject_type}, {len(policy.checks)} checks")
        return 0
    if action == "policy-show":
        policy = get_review_policy(args.policy_id)
        print(policy.to_json() if args.json else (
            f"IntentForge Engineering Review Policy\n"
            f"Policy: {policy.policy_id}\nVersion: {policy.policy_version}\n"
            f"Subject: {policy.subject_type}\nScope: {policy.policy_scope}\n"
            f"Profiles: {', '.join(policy.required_assurance_profiles)}\nChecks: {len(policy.checks)}\n"
            f"Content ID: {policy.content_id}\n"
        ), end="")
        return 0
    if action == "policy-validate":
        result = validate_review_policy_manifest()
        print("Engineering review policy validation")
        print("PASS" if result.passed else "FAIL")
        print(f"Policies checked: {result.policies_checked}")
        print(f"Checks checked: {result.checks_checked}")
        print(f"Errors: {len(result.errors)}")
        for error in result.errors: print(f"- {error}")
        return 0 if result.passed else 1
    if action == "evaluate":
        case = _load_assurance_case(args.case_path)
        policy = get_review_policy(args.policy)
        package_result = validate_audit_package(args.package_path) if args.package_path else None
        decision = evaluate_assurance_case(policy, case, package_result)
        output = Path(args.output) if args.output else Path(args.case_path).parent / "review_decision.json"
        json_path, markdown_path = _write_review_decision(decision, output)
        _print_review_decision(decision, as_json=args.json, json_path=json_path, markdown_path=markdown_path)
        return REVIEW_EXIT_CODES[decision.decision_status]
    if action in {"validate", "show", "render"}:
        decision = load_review_decision(args.decision_path)
        if action == "validate":
            result = validate_review_decision(decision)
            print("Review decision validation")
            print("PASS" if result.passed else "FAIL")
            print(f"Decision ID: {decision.decision_id}")
            for error in result.errors: print(f"- {error}")
            return 0 if result.passed else 1
        if action == "show":
            print(decision.to_json() if args.json else render_review_decision_markdown(decision), end="")
            return 0
        output = Path(args.output) if args.output else Path(args.decision_path).with_suffix(".md")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_review_decision_markdown(decision), encoding="utf-8")
        print(f"Rendered review decision: {output}")
        return 0
    if action == "provenance":
        decision = load_review_decision_source(args.decision_source)
        verification = verify_decision_provenance(decision, perform_replay=args.verify)
        if args.json:
            payload = {
                "decision_id": decision.decision_id,
                "provenance": None if decision.decision_provenance is None else decision.decision_provenance.model_dump(mode="json"),
                "verification": verification.model_dump(mode="json"),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(render_decision_provenance_markdown(decision, verify=args.verify), end="")
        return 0 if verification.passed else 1
    if action == "verify-offline":
        verification = verify_offline_audit_package(args.package_path)
        if args.json:
            print(verification.to_json(), end="")
        else:
            print("IntentForge Offline Audit Package Verification")
            print("PASS" if verification.passed else "FAIL")
            print(f"Status: {verification.status}")
            print(f"Package ID: {verification.package_id}")
            print(f"Assurance case ID: {verification.assurance_case_id}")
            print(f"Review decision ID: {verification.decision_id}")
            print(f"Frozen rules: {verification.metrics.get('rule_snapshot_count', 0)}")
            print(f"Frozen capabilities: {verification.metrics.get('capability_snapshot_count', 0)}")
            print(f"Frozen evidence records: {verification.metrics.get('evidence_definition_count', 0)}")
            print(f"Policy catalog checks: {verification.metrics.get('policy_catalog_check_count', 0)}")
            print(f"Run claims: {verification.metrics.get('assurance_claim_count', 0)}")
            print(f"Portability violations: {verification.metrics.get('portability_violation_count', 0)}")
            for error in verification.errors:
                print(f"- {error}")
            print("Static verification does not re-run CAD generation or simulation.")
        return 0 if verification.passed else 1
    if action == "cas-check":
        verification = verify_offline_audit_package(args.package_path)
        passed = verification.passed and bool(verification.metrics.get("cas_content_address_verified"))
        payload = verification.to_dict()
        payload["cas_check_passed"] = passed
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("IntentForge Content-Addressed Package Check")
            print("PASS" if passed else "FAIL")
            print(f"Content address: {verification.package_id}")
            print(f"CAS objects: {verification.metrics.get('cas_object_count', 0)}")
            for error in verification.errors:
                print(f"- {error}")
        return 0 if passed else 1
    if action == "cas-store":
        result = store_audit_package(args.package_path, args.store_root)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print("IntentForge Content-Addressed Package Store")
            print("PASS" if result.passed else "FAIL")
            print(f"Content address: {result.content_address}")
            print(f"Storage path: {result.storage_path}")
            print(f"Reused existing: {str(result.reused_existing).lower()}")
            for error in result.errors:
                print(f"- {error}")
        return 0 if result.passed else 1
    if action == "chain-verify":
        result = verify_audit_chain(
            args.package_path,
            store_root=args.store_root,
            maximum_depth=args.maximum_depth,
        )
        if args.json:
            print(result.to_json(), end="")
        else:
            print("IntentForge Audit Package Chain Verification")
            print("PASS" if result.passed else "FAIL")
            print(f"Status: {result.status}")
            print(f"Head: {result.head_content_address}")
            print(f"Genesis: {result.genesis_content_address}")
            print(f"Chain length: {result.chain_length}")
            print(f"Chain content address: {result.chain_content_address}")
            for error in result.errors:
                print(f"- {error}")
        return 0 if result.passed else 1
    if action == "export-redacted":
        config = load_redaction_config(args.policy_config) if args.policy_config else default_redaction_config()
        predecessor = _resolve_predecessor_hash(args.predecessor) if args.predecessor else None
        result = export_redacted_package(
            args.package_path,
            args.output,
            config=config,
            predecessor_hash=predecessor,
        )
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("IntentForge Privacy-Preserving Audit Export")
            print("PASS" if result.get("passed") else "FAIL")
            print(f"Redacted package: {result.get('package_path')}")
            print(f"Original package ID: {result.get('original_package_id')}")
            print(f"Redacted package ID: {result.get('redacted_package_id')}")
            print(f"Total redactions: {result.get('redaction_count', 0)}")
            print(f"Files in redacted package: {result.get('file_count', 0)}")
            for error in result.get("errors", []):
                print(f"- {error}")
        return 0 if result.get("passed") else 1
    if action == "verify-redacted":
        result = verify_redacted_audit_package(args.package_path)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print("IntentForge Privacy-Preserving Audit Verification")
            print("PASS" if result.passed else "FAIL")
            print(f"Status: {result.status}")
            print(f"Original package ID: {result.original_package_id}")
            print(f"Redacted package ID: {result.redacted_package_id}")
            print(f"Total redactions: {result.metrics.get('total_redactions', 0)}")
            print(f"CAS objects: {result.metrics.get('redacted_cas_object_count', 0)}")
            print(f"Checksums validated: {result.metrics.get('checksum_validation_passed', False)}")
            for error in result.errors:
                print(f"- {error}")
        return 0 if result.passed else 1
    if action == "diff":
        baseline = load_review_decision_source(args.baseline)
        variants = [load_review_decision_source(item) for item in args.variants]
        if len(variants) == 1:
            result = diff_review_decisions(baseline, variants[0])
            serialized = result.to_json()
            markdown = render_review_diff_markdown(result)
        else:
            result = diff_review_variants(baseline, variants)
            serialized = result.to_json()
            markdown = render_multi_variant_diff_markdown(result)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(serialized if args.json else markdown, encoding="utf-8")
        if args.json:
            print(serialized, end="")
        else:
            print(markdown, end="")
            if args.output:
                print(f"Differential audit path: {args.output}")
        return 0
    if action == "compare":
        result = compare_review_decisions(load_review_decision(args.decision_a), load_review_decision(args.decision_b))
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Review decision comparison")
            print(f"Comparison ID: {result['comparison_id']}")
            print(f"Identical: {str(result['identical']).lower()}")
            print(f"Changed fields: {', '.join(result['changed_fields']) if result['changed_fields'] else 'none'}")
        return 0
    if action == "build-dossier":
        from intentforge.dossier import ReleaseDossierBuilder, write_dossier
        builder = ReleaseDossierBuilder(dossier_id=args.dossier_id)
        try:
            dossier = builder.build(args.package_paths)
        except ValueError as exc:
            if args.json:
                print(json.dumps({"passed": False, "error": str(exc)}, indent=2, sort_keys=True))
            else:
                print("IntentForge Release Dossier")
                print("FAIL")
                print(f"Error: {exc}")
            return 1
        summary = write_dossier(dossier, args.output)
        if args.json:
            payload = {
                "passed": True,
                "dossier_id": dossier.dossier_id,
                "root_hash": dossier.root_hash,
                "rollup_status": dossier.rollup.rollup_status,
                "leaf_count": dossier.merkle_tree.leaf_count,
                "blocked_count": dossier.rollup.blocked_count,
                "conditional_count": dossier.rollup.conditional_count,
                "approved_count": dossier.rollup.approved_count,
                "package_path": summary["package_path"],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("IntentForge Release Dossier")
            print("PASS")
            print(f"Dossier ID: {dossier.dossier_id}")
            print(f"Root hash: {dossier.root_hash}")
            print(f"Rollup status: {dossier.rollup.rollup_status}")
            print(f"Leaf count: {dossier.merkle_tree.leaf_count}")
            print(f"Blocked: {dossier.rollup.blocked_count}")
            print(f"Conditional: {dossier.rollup.conditional_count}")
            print(f"Approved: {dossier.rollup.approved_count}")
            print(f"Output: {summary['package_path']}")
        return 0
    if action == "verify-dossier":
        from intentforge.dossier import verify_release_dossier
        result = verify_release_dossier(args.dossier_path, max_children=args.max_children)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print("IntentForge Release Dossier Verification")
            print("PASS" if result.passed else "FAIL")
            print(f"Status: {result.status}")
            print(f"Dossier ID: {result.dossier_id}")
            print(f"Root hash: {result.root_hash}")
            print(f"Rollup status: {result.rollup_status}")
            print(f"Child count: {result.child_count}")
            print(f"Passed children: {result.passed_child_count}")
            print(f"Failed children: {result.failed_child_count}")
            for error in result.errors:
                print(f"- {error}")
        return 0 if result.passed else 1
    if action == "synthesize-remediation":
        from intentforge.remediation import synthesize_remediation_intent
        parameters_override = None
        if args.parameters:
            parameters_override = json.loads(Path(args.parameters).read_text(encoding="utf-8"))
        output_dir = Path(args.output) if args.output else None
        result = synthesize_remediation_intent(
            args.package_path, parameters_override=parameters_override, output_dir=output_dir,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print("IntentForge Auto-Remediation Synthesis")
            print("PASS" if result.passed else "FAIL")
            print(f"Status: {result.status}")
            print(f"Rationale: {result.rationale}")
            if result.delta is not None:
                print(f"Remediation ID: {result.delta.remediation_id}")
                print(f"Target family: {result.delta.target_family}")
                print(f"Parameter changes: {len(result.delta.parameter_changes)}")
                for change in result.delta.parameter_changes:
                    print(
                        f"  - {change.parameter}: "
                        f"{change.current_value:g} -> {change.proposed_value:g} "
                        f"(rule {change.rule_id})"
                    )
            if result.remediation_path is not None:
                print(f"Remediation Intent: {result.remediation_path}")
            for error in result.errors:
                print(f"- {error}")
        return 0 if result.passed else 1
    if action == "build-evaluate":
        policy_id = args.policy or {
            "static": "intentforge_static_review_v1",
            "standard": "intentforge_standard_design_review_v1",
            "full": "intentforge_full_design_review_v1",
        }[args.profile]
        policy = get_review_policy(policy_id)
        output_root = Path(args.output_root or (_project_root() / "output"))
        source_case = build_assurance_from_prompt(
            args.prompt, family=args.family, profile=args.profile, dry_run=args.dry_run,
            output_root=output_root,
        )
        predecessor = _resolve_predecessor_hash(args.predecessor)
        if (predecessor is not None or args.cas_store_root is not None) and policy.policy_scope != "assurance_case_and_audit_package":
            raise ValueError("predecessor tracking and CAS storage require an audit-package review policy")
        review_root = output_root / "review"
        review_root.mkdir(parents=True, exist_ok=True)
        package_result = None
        package_path = None
        if policy.policy_scope == "assurance_case_and_audit_package":
            package_path = review_root / "audit_package"
            base_package = build_audit_package(source_case, package_path)
            package_result = base_package["validation"]
        case = attach_assurance_predecessor(source_case, predecessor)
        case_path = review_root / "assurance_case.json"
        case_path.write_text(case.to_json(), encoding="utf-8")
        exemption_models = []
        evaluation = None
        if args.apply_exemption:
            from intentforge.review.exemption_engine import (
                load_exemption_manifest,
                match_exemptions,
            )
            for manifest_path in args.apply_exemption:
                exemption_models.append(load_exemption_manifest(manifest_path))
        decision = evaluate_assurance_case(
            policy, case, package_result, exemption_manifests=exemption_models,
        )
        if exemption_models:
            from intentforge.review.exemption_engine import match_exemptions
            evaluation = match_exemptions(decision, exemption_models, package_result=package_result)
        output = Path(args.output) if args.output else review_root / "review_decision.json"
        json_path, markdown_path = _write_review_decision(decision, output)
        if package_path is not None:
            build_audit_package(
                case,
                package_path,
                review_policy=policy,
                review_decision=decision,
                predecessor_hash_pointer=predecessor,
                exemption_manifests=exemption_models or None,
                exemption_evaluation=evaluation,
            )
        if evaluation is not None and not args.json:
            print(f"Applied exemptions: {len(evaluation.applied_references)}")
            for reference in evaluation.applied_references:
                print(f"  - {reference.exemption_id} -> {reference.matched_check_id}")
            if evaluation.unmatched_manifest_ids:
                print(f"Unmatched manifests: {', '.join(evaluation.unmatched_manifest_ids)}")
        _print_review_decision(decision, as_json=args.json, json_path=json_path, markdown_path=markdown_path)
        if package_path is not None and not args.json: print(f"Audit package: {package_path}")
        if package_path is not None and args.cas_store_root is not None:
            stored = store_audit_package(package_path, args.cas_store_root)
            if not stored.passed:
                raise ValueError("could not store audit package: " + "; ".join(stored.errors))
            if not args.json:
                print(f"CAS address: {stored.content_address}")
                print(f"CAS storage path: {stored.storage_path}")
        return REVIEW_EXIT_CODES[decision.decision_status]
    raise ValueError(f"unsupported review action: {action}")


def _assurance_command(args) -> int:
    action = args.assurance_command
    if action == "build":
        output_root = Path(args.output_root or (_project_root() / "output"))
        case = build_assurance_from_prompt(
            args.prompt, family=args.family, profile=args.profile, dry_run=args.dry_run,
            output_root=output_root,
        )
        assurance_root = output_root / "assurance"
        assurance_root.mkdir(parents=True, exist_ok=True)
        json_path = assurance_root / "assurance_case.json"
        markdown_path = assurance_root / "assurance_case.md"
        json_path.write_text(case.to_json(), encoding="utf-8")
        markdown_path.write_text(render_assurance_markdown(case), encoding="utf-8")
        if args.json:
            print(case.to_json(), end="")
        else:
            print("IntentForge Engineering Assurance Case")
            print(f"Case ID: {case.assurance_case_id}")
            print(f"Profile: {case.profile}")
            print(f"Family: {case.cad_family}")
            print(f"Status: {case.overall_assurance_status}")
            print(f"Claims: {len(case.claims)}")
            print(f"Case path: {json_path}")
            print(f"Markdown path: {markdown_path}")
        return 0 if validate_assurance_case(case).passed else 1
    if action in {"validate", "show", "render"}:
        case = _load_assurance_case(args.case_path)
        if action == "validate":
            result = validate_assurance_case(case)
            print("Assurance case validation")
            print("PASS" if result.passed else "FAIL")
            print(f"Case ID: {case.assurance_case_id}")
            for error in result.errors: print(f"- {error}")
            return 0 if result.passed else 1
        if action == "show":
            print(case.to_json() if args.json else render_assurance_markdown(case), end="")
            return 0
        markdown = render_assurance_markdown(case)
        output = Path(args.output) if args.output else Path(args.case_path).with_suffix(".md")
        output.write_text(markdown, encoding="utf-8")
        print(f"Rendered assurance report: {output}")
        return 0
    if action == "compare":
        result = compare_assurance_cases(_load_assurance_case(args.case_a), _load_assurance_case(args.case_b))
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Assurance case comparison")
            print(f"Comparison ID: {result['comparison_id']}")
            print(f"Identical: {str(result['identical']).lower()}")
            print(f"Changed fields: {', '.join(result['changed_fields']) if result['changed_fields'] else 'none'}")
        return 0
    if action == "package":
        case = _load_assurance_case(args.case_path)
        output = Path(args.output) if args.output else Path(args.case_path).parent / f"audit_package_{case.assurance_case_id}"
        if args.review_decision:
            review_decision = load_review_decision(args.review_decision)
            review_policy = get_review_policy(review_decision.policy_id)
            result = build_audit_package(case, output, review_policy=review_policy, review_decision=review_decision)
        else:
            result = build_audit_package(case, output)
        print("IntentForge Audit Package")
        print(f"Package ID: {result['package_id']}")
        print(f"Package path: {result['package_path']}")
        print(f"Files: {result['file_count']}")
        return 0 if result["validation"]["passed"] else 1
    if action in {"package-validate", "package-inspect"}:
        result = validate_audit_package(args.package_path) if action == "package-validate" else inspect_audit_package(args.package_path)
        passed = result.get("passed", result.get("validation", {}).get("passed", False))
        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Audit package validation" if action == "package-validate" else "Audit package inspection")
            print("PASS" if passed else "FAIL")
            validation = result if action == "package-validate" else result.get("validation", {})
            print(f"Package ID: {validation.get('package_id')}")
            for error in validation.get("errors", []): print(f"- {error}")
        return 0 if passed else 1
    raise ValueError(f"unsupported assurance action: {action}")


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="intentforge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    topology = subparsers.add_parser("topology", help="Inspect and build declaratively registered CAD topology families.")
    topology_subparsers = topology.add_subparsers(dest="topology_command", required=True)
    topology_list = topology_subparsers.add_parser("list", help="List packaged topology manifests.")
    topology_list.add_argument("--json", action="store_true")
    topology_subparsers.add_parser("validate", help="Validate topology adapters, evidence IDs, and rule bindings.")
    topology_schema = topology_subparsers.add_parser("schema", help="Render the structured intent schema for one family.")
    topology_schema.add_argument("family")
    topology_build = topology_subparsers.add_parser("build-json", help="Build and validate a topology from structured JSON intent.")
    topology_build.add_argument("intent_path")
    topology_build.add_argument("--output-root", default=None)
    topology_build.add_argument("--dry-run", action="store_true")
    topology_build.add_argument("--json", action="store_true")

    review = subparsers.add_parser("review", help="Evaluate assurance cases with deterministic engineering review policies.")
    review_subparsers = review.add_subparsers(dest="review_command", required=True)
    review_policies = review_subparsers.add_parser("policies", help="List packaged engineering review policies.")
    review_policies.add_argument("--json", action="store_true")
    review_policy_show = review_subparsers.add_parser("policy-show", help="Show one packaged review policy.")
    review_policy_show.add_argument("policy_id")
    review_policy_show.add_argument("--json", action="store_true")
    review_subparsers.add_parser("policy-validate", help="Validate the packaged review policy manifest.")
    review_evaluate = review_subparsers.add_parser("evaluate", help="Evaluate an existing assurance case.")
    review_evaluate.add_argument("case_path")
    review_evaluate.add_argument("--policy", required=True)
    review_evaluate.add_argument("--package", dest="package_path", default=None, help="Optional validated audit-package directory.")
    review_evaluate.add_argument("--json", action="store_true")
    review_evaluate.add_argument("--output", default=None)
    review_validate = review_subparsers.add_parser("validate", help="Validate a review decision JSON file.")
    review_validate.add_argument("decision_path")
    review_show = review_subparsers.add_parser("show", help="Show a review decision.")
    review_show.add_argument("decision_path")
    review_show.add_argument("--json", action="store_true")
    review_render = review_subparsers.add_parser("render", help="Render a review decision to Markdown.")
    review_render.add_argument("decision_path")
    review_render.add_argument("--output", default=None)
    review_provenance = review_subparsers.add_parser(
        "provenance", help="Inspect or replay deterministic review-decision provenance."
    )
    review_provenance.add_argument("decision_source", help="Review decision JSON or audit-package directory.")
    review_provenance.add_argument("--verify", action="store_true", help="Replay using only frozen provenance snapshots.")
    review_provenance.add_argument("--json", action="store_true")
    review_offline = review_subparsers.add_parser(
        "verify-offline",
        help="Verify a portable audit package using enclosed frozen snapshots only.",
    )
    review_offline.add_argument("package_path")
    review_offline.add_argument("--json", action="store_true")
    review_cas_check = review_subparsers.add_parser(
        "cas-check", help="Validate the full SHA-256 CAS envelope for a reviewed package."
    )
    review_cas_check.add_argument("package_path")
    review_cas_check.add_argument("--json", action="store_true")
    review_cas_store = review_subparsers.add_parser(
        "cas-store", help="Store a verified package under its immutable content address."
    )
    review_cas_store.add_argument("package_path")
    review_cas_store.add_argument("--store", dest="store_root", required=True)
    review_cas_store.add_argument("--json", action="store_true")
    review_chain = review_subparsers.add_parser(
        "chain-verify", help="Verify a package and its complete predecessor hash chain."
    )
    review_chain.add_argument("package_path")
    review_chain.add_argument("--store", dest="store_root", default=None)
    review_chain.add_argument("--maximum-depth", type=int, default=1000)
    review_chain.add_argument("--json", action="store_true")
    review_export_redacted = review_subparsers.add_parser(
        "export-redacted", help="Export a privacy-preserving redacted audit package."
    )
    review_export_redacted.add_argument("package_path", help="Source audit package directory to redact.")
    review_export_redacted.add_argument("--output", required=True, help="Output directory for the redacted package.")
    review_export_redacted.add_argument(
        "--policy-config", dest="policy_config", default=None,
        help="Optional YAML/JSON redaction configuration file.",
    )
    review_export_redacted.add_argument(
        "--predecessor", default=None,
        help="Optional predecessor sha256 address for lineage preservation.",
    )
    review_export_redacted.add_argument("--json", action="store_true")
    review_verify_redacted = review_subparsers.add_parser(
        "verify-redacted", help="Verify a redacted audit package without consulting live registries."
    )
    review_verify_redacted.add_argument("package_path", help="Redacted audit package directory to verify.")
    review_verify_redacted.add_argument("--json", action="store_true")
    review_diff = review_subparsers.add_parser(
        "diff", help="Compare one baseline with one or more review decision variants."
    )
    review_diff.add_argument("baseline", help="Baseline decision JSON or audit-package directory.")
    review_diff.add_argument("variants", nargs="+", help="One or more decision JSON files or audit-package directories.")
    review_diff.add_argument("--json", action="store_true")
    review_diff.add_argument("--output", default=None)
    review_compare = review_subparsers.add_parser("compare", help="Compare two review decisions.")
    review_compare.add_argument("decision_a")
    review_compare.add_argument("decision_b")
    review_compare.add_argument("--json", action="store_true")
    review_build = review_subparsers.add_parser("build-evaluate", help="Build assurance through the existing workflow and evaluate it.")
    review_build.add_argument("--profile", choices=["static", "standard", "full"], default="standard")
    review_build.add_argument("--family", choices=SUPPORTED_MODEL_FAMILIES, default="wall_mounted_bracket")
    review_build.add_argument("--prompt", default=None)
    review_build.add_argument("--policy", default=None)
    review_build.add_argument("--dry-run", action="store_true")
    review_build.add_argument("--json", action="store_true")
    review_build.add_argument("--output-root", default=None)
    review_build.add_argument("--output", default=None)
    review_build.add_argument(
        "--predecessor",
        default=None,
        help="Optional predecessor sha256 address or verified audit-package directory.",
    )
    review_build.add_argument(
        "--cas-store",
        dest="cas_store_root",
        default=None,
        help="Optional root where the finalized package is stored by content address.",
    )
    review_build.add_argument(
        "--apply-exemption",
        dest="apply_exemption",
        action="append",
        default=[],
        metavar="MANIFEST",
        help=(
            "Optional path to an exemption manifest JSON file. May be repeated. "
            "Any matching declaration elevates ``rejected_by_policy`` to "
            "``accepted_with_exemption`` and is content-addressed inside the audit package."
        ),
    )
    review_dossier = review_subparsers.add_parser(
        "build-dossier",
        help="Build a cryptographic Merkle-rooted release dossier from one or more audit packages.",
    )
    review_dossier.add_argument("package_paths", nargs="+", help="Audit package directories to aggregate.")
    review_dossier.add_argument("--output", required=True, help="Output directory for the dossier.")
    review_dossier.add_argument("--dossier-id", default=None, help="Optional dossier identifier override.")
    review_dossier.add_argument("--json", action="store_true")
    review_dossier_verify = review_subparsers.add_parser(
        "verify-dossier",
        help="Verify a release dossier using only its enclosed files.",
    )
    review_dossier_verify.add_argument("dossier_path", help="Dossier directory to verify.")
    review_dossier_verify.add_argument("--max-children", type=int, default=1000)
    review_dossier_verify.add_argument("--json", action="store_true")
    review_remediation = review_subparsers.add_parser(
        "synthesize-remediation",
        help="Analyze a rejected audit package and synthesize a deterministic Remediation_Intent.json.",
    )
    review_remediation.add_argument("package_path", help="Audit package directory whose parameters failed at least one knowledge rule.")
    review_remediation.add_argument("--output", default=None, help="Directory to write the Remediation_Intent.json (defaults to the package directory).")
    review_remediation.add_argument("--parameters", default=None, help="Optional path to a JSON parameter table override.")
    review_remediation.add_argument("--json", action="store_true")

    assurance = subparsers.add_parser("assurance", help="Build and inspect scoped engineering assurance records.")
    assurance_subparsers = assurance.add_subparsers(dest="assurance_command", required=True)
    assurance_build = assurance_subparsers.add_parser("build", help="Build an assurance case using the existing workflow.")
    assurance_build.add_argument("--profile", choices=["static", "standard", "full"], default="standard")
    assurance_build.add_argument("--family", choices=SUPPORTED_MODEL_FAMILIES, default="wall_mounted_bracket")
    assurance_build.add_argument("--prompt", default=None)
    assurance_build.add_argument("--dry-run", action="store_true")
    assurance_build.add_argument("--json", action="store_true")
    assurance_build.add_argument("--output-root", default=None)
    assurance_validate = assurance_subparsers.add_parser("validate", help="Validate an assurance case JSON file.")
    assurance_validate.add_argument("case_path")
    assurance_show = assurance_subparsers.add_parser("show", help="Show an assurance case.")
    assurance_show.add_argument("case_path")
    assurance_show.add_argument("--json", action="store_true")
    assurance_render = assurance_subparsers.add_parser("render", help="Render assurance Markdown.")
    assurance_render.add_argument("case_path")
    assurance_render.add_argument("--output", default=None)
    assurance_compare = assurance_subparsers.add_parser("compare", help="Compare two assurance cases.")
    assurance_compare.add_argument("case_a")
    assurance_compare.add_argument("case_b")
    assurance_compare.add_argument("--json", action="store_true")
    assurance_package = assurance_subparsers.add_parser("package", help="Create a portable audit package directory.")
    assurance_package.add_argument("case_path")
    assurance_package.add_argument("--output", default=None)
    assurance_package.add_argument("--review-decision", default=None)
    assurance_package_validate = assurance_subparsers.add_parser("package-validate", help="Validate an audit package.")
    assurance_package_validate.add_argument("package_path")
    assurance_package_inspect = assurance_subparsers.add_parser("package-inspect", help="Inspect an audit package.")
    assurance_package_inspect.add_argument("package_path")
    assurance_package_inspect.add_argument("--json", action="store_true")

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

    recognize_features_parser = subparsers.add_parser(
        "recognize-features",
        help="Recognize topology-level engineering features for a bundled example model.",
    )
    recognize_features_parser.add_argument(
        "family",
        choices=["wall_mounted_bracket", "l_bracket"],
        help="Supported model family to build and recognize.",
    )
    recognize_features_parser.add_argument(
        "--output",
        default=None,
        help="Optional latest feature recognition report path.",
    )
    recognize_features_parser.add_argument(
        "--no-export",
        action="store_true",
        help="Accepted for symmetry with harness commands; feature recognition does not export CAD.",
    )

    design_review = subparsers.add_parser(
        "design-review",
        help="Generate a design review report for a bundled example model.",
    )
    design_review.add_argument(
        "family",
        choices=["wall_mounted_bracket", "l_bracket"],
        help="Supported model family to review.",
    )
    design_review.add_argument(
        "--knowledge",
        action="store_true",
        help="Include engineering knowledge findings and rationale markdown.",
    )
    design_review.add_argument(
        "--json",
        action="store_true",
        help="Write a standalone engineering knowledge JSON report when knowledge is enabled.",
    )
    design_review.add_argument(
        "--reasoning",
        action="store_true",
        help="Include deterministic engineering reasoning; this enables knowledge evaluation automatically.",
    )

    knowledge = subparsers.add_parser(
        "knowledge",
        help="Inspect deterministic engineering knowledge rules.",
    )
    knowledge_subparsers = knowledge.add_subparsers(dest="knowledge_command", required=True)
    knowledge_subparsers.add_parser("list", help="List loaded engineering knowledge rules.")
    knowledge_subparsers.add_parser("validate", help="Validate engineering knowledge rule database integrity.")
    knowledge_subparsers.add_parser("packs", help="List loaded engineering knowledge rule packs.")
    knowledge_subparsers.add_parser("packs-validate", help="Validate engineering knowledge rule pack integrity.")
    coverage_parser = knowledge_subparsers.add_parser("coverage", help="Summarize engineering capability coverage.")
    coverage_parser.add_argument("--json", action="store_true", help="Print stable JSON coverage report.")
    knowledge_subparsers.add_parser("coverage-validate", help="Validate engineering capability coverage declarations.")
    matrix_parser = knowledge_subparsers.add_parser("capability-matrix", help="Print the engineering capability matrix.")
    matrix_parser.add_argument("--json", action="store_true", help="Print stable JSON capability matrix.")
    matrix_parser.add_argument("--family", choices=["wall_mounted_bracket", "l_bracket"], default=None)
    matrix_parser.add_argument(
        "--status",
        choices=["supported", "partially_supported", "unsupported", "not_applicable"],
        default=None,
    )
    matrix_parser.add_argument(
        "--stage",
        choices=[
            "parsing",
            "intent_schema",
            "knowledge",
            "constraint_compilation",
            "cad_generation",
            "geometry_validation",
            "topology_inspection",
            "feature_recognition",
            "engineering_reasoning",
            "golden_verification",
            "rejection",
        ],
        default=None,
    )
    matrix_parser.add_argument("--knowledge-pack", default=None, help="Filter by contributing knowledge pack ID.")
    matrix_parser.add_argument("--rule-id", default=None, help="Filter by contributing knowledge rule ID.")
    knowledge_subparsers.add_parser("capability-validate", help="Alias for coverage-validate.")
    evidence_list_parser = knowledge_subparsers.add_parser("evidence-list", help="List engineering evidence definitions.")
    evidence_list_parser.add_argument("--json", action="store_true", help="Print stable JSON evidence definitions.")
    evidence_list_parser.add_argument("--family", choices=["wall_mounted_bracket", "l_bracket"], default=None)
    evidence_list_parser.add_argument(
        "--type",
        dest="evidence_type",
        choices=[
            "rule_definition",
            "rule_pack",
            "parser_support",
            "intent_schema",
            "constraint_compiler",
            "cad_generator",
            "geometry_validator",
            "topology_inspector",
            "feature_recognizer",
            "knowledge_evaluator",
            "reasoning_case",
            "golden_case",
            "benchmark_case",
            "rejection_case",
            "regression_test",
            "technical_harness_gate",
            "documentation",
            "package_artifact",
        ],
        default=None,
    )
    evidence_list_parser.add_argument(
        "--role",
        choices=["implementation", "verification", "boundary", "limitation", "provenance", "packaging"],
        default=None,
    )
    evidence_show_parser = knowledge_subparsers.add_parser("evidence-show", help="Show one engineering evidence definition.")
    evidence_show_parser.add_argument("evidence_id")
    evidence_show_parser.add_argument("--json", action="store_true", help="Print stable JSON evidence definition.")
    knowledge_subparsers.add_parser("evidence-validate", help="Validate engineering evidence manifest integrity.")
    evidence_resolve_parser = knowledge_subparsers.add_parser("evidence-resolve", help="Resolve engineering evidence references.")
    evidence_resolve_parser.add_argument("--json", action="store_true", help="Print stable JSON evidence resolution report.")
    evidence_bundles_parser = knowledge_subparsers.add_parser("evidence-bundles", help="Print capability evidence bundles.")
    evidence_bundles_parser.add_argument("--json", action="store_true", help="Print stable JSON evidence bundles.")
    evidence_bundles_parser.add_argument("--family", choices=["wall_mounted_bracket", "l_bracket"], default=None)
    evidence_bundles_parser.add_argument("--capability", dest="capability_id", default=None)
    trust_report_parser = knowledge_subparsers.add_parser("trust-report", help="Print engineering evidence trust report.")
    trust_report_parser.add_argument("--json", action="store_true", help="Print stable JSON trust report.")
    trust_report_parser.add_argument("--verify", action="store_true", help="Run safe runtime verification where available.")
    knowledge_subparsers.add_parser("trust-validate", help="Validate engineering evidence trust gates.")
    knowledge_subparsers.add_parser("reasoning-info", help="Describe deterministic engineering reasoning support.")
    knowledge_subparsers.add_parser("reasoning-validate", help="Validate reasoning metadata in engineering rules.")
    knowledge_subparsers.add_parser("reasoning-verify", help="Run golden engineering reasoning verification cases.")
    knowledge_subparsers.add_parser("reasoning-benchmark", help="Run the standalone deterministic reasoning benchmark.")

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
        if args.command == "topology":
            return _topology_command(args)
        if args.command == "assurance":
            return _assurance_command(args)
        if args.command == "review":
            return _review_command(args)
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
        if args.command == "recognize-features":
            return _recognize_features_command(args.family, args.output, args.no_export)
        if args.command == "design-review":
            return _design_review_command(args.family, args.knowledge, args.json, args.reasoning)
        if args.command == "knowledge":
            return _knowledge_command(args)
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
    except (ReviewEvaluationError, ReviewPolicyError) as exc:
        print(f"Review error: {exc}")
        return 5
    except OSError as exc:
        parser.exit(1, f"Could not read required file: {exc}\n")
    except json.JSONDecodeError as exc:
        parser.exit(1, f"Could not parse JSON file: {exc}\n")
    except ValueError as exc:
        if args.command == "review":
            print(f"Review error: {exc}")
            return 5
        raise

    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
