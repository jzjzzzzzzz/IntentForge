"""End-to-end nested validation and generation for registered assemblies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from intentforge.assemblies.audit import build_assembly_audit_package
from intentforge.assemblies.evaluator import evaluate_assembly, resolve_component_quantities
from intentforge.assemblies.factories import build_registered_assembly
from intentforge.assemblies.registry import get_assembly_registry
from intentforge.parser.registered_parser import parse_registered_intent
from intentforge.review.portability import canonical_json_bytes
from intentforge.schemas import ParameterTable, ValidationReport
from intentforge.topology import build_registered_model, validate_registered_geometry


def build_assembly_intent_workflow(
    payload: dict[str, Any],
    output_dir: str | Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Build one registered assembly without bypassing child validation."""

    assembly_family = str(payload.get("assembly_family") or "")
    manifest = get_assembly_registry().get(assembly_family)
    raw_components = payload.get("components")
    if not isinstance(raw_components, dict):
        raise ValueError("assembly payload requires a components mapping")
    tables: dict[str, ParameterTable] = {}
    feature_plans: dict[str, Any] = {}
    for definition in manifest.components:
        component_payload = raw_components.get(definition.component_id)
        if not isinstance(component_payload, dict):
            raise ValueError(f"assembly component is missing: {definition.component_id}")
        parsed = parse_registered_intent({
            "family": definition.topology_family,
            "parameters": component_payload.get("parameters", component_payload),
        })
        tables[definition.component_id] = parsed.parameter_table
        feature_plans[definition.component_id] = parsed.feature_plan
    quantities = resolve_component_quantities(manifest, tables)
    models: dict[str, Any] = {}
    child_validations: dict[str, list[ValidationReport]] = {}
    for definition in manifest.components:
        model = build_registered_model(tables[definition.component_id], feature_plans[definition.component_id])
        models[definition.component_id] = model
        child_validations[definition.component_id] = [
            validate_registered_geometry(model, tables[definition.component_id])
            for _ in range(quantities[definition.component_id])
        ]
    evaluation = evaluate_assembly(manifest, tables, child_validations)
    result: dict[str, Any] = {
        "ok": evaluation.passed,
        "assembly_family": manifest.assembly_family,
        "manifest_version": manifest.manifest_version,
        "component_quantities": quantities,
        "component_parameters": {key: value.model_dump(mode="json") for key, value in sorted(tables.items())},
        "evaluation": evaluation.model_dump(mode="json"),
        "cad_exported": False,
        "dry_run": dry_run,
    }
    if not evaluation.passed:
        result["error_type"] = "AssemblyValidationFailedError"
        result["message"] = "Nested component or assembly spatial validation failed."
        return result
    assembly, placements = build_registered_assembly(manifest.assembly_factory_id, tables, models)
    result["placements"] = placements
    if dry_run:
        return result
    try:
        import cadquery as cq
    except ImportError as exc:
        from intentforge.generator.cadquery_generator import CadQueryUnavailableError

        raise CadQueryUnavailableError('CadQuery is required to export assemblies. Install "intentforge[cad]".') from exc
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    assembly_step = root / "flange_bolted_joint.step"
    assembly.export(str(assembly_step), exportType="STEP")
    child_artifacts: dict[str, Path] = {}
    for placement in placements:
        instance_id = placement["instance_id"]
        component_id = placement["component_id"]
        path = root / "components" / f"{instance_id}.step"
        path.parent.mkdir(parents=True, exist_ok=True)
        cq.exporters.export(models[component_id], str(path))
        child_artifacts[instance_id] = path
    report_path = root / "assembly_evaluation.json"
    report_path.write_bytes(canonical_json_bytes(evaluation.model_dump(mode="json")))
    package = build_assembly_audit_package(
        manifest,
        evaluation,
        tables,
        placements,
        child_artifacts,
        assembly_step,
        root / "audit_package",
    )
    result.update({
        "cad_exported": True,
        "assembly_step_path": str(assembly_step),
        "assembly_evaluation_path": str(report_path),
        "child_artifact_paths": {key: str(value) for key, value in sorted(child_artifacts.items())},
        "audit_package": package,
        "nested_merkle_root": package["child_merkle_root"],
    })
    (root / "assembly_result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
