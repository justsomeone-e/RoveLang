"""Load and validate the canonical Rove compiler feature registry."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping
import tomllib


FEATURE_MANIFEST_SCHEMA_VERSION = 1
SEMANTIC_CLASSIFICATIONS = frozenset({
    "defined",
    "implementation-defined",
    "rejected",
    "trapped",
    "unsafe-only",
})
MATURITY_LEVELS = frozenset({"stable", "beta", "experimental"})
STAGE_STATUSES = frozenset({"stable", "beta", "experimental", "planned"})
FEATURE_STAGE_STATUSES = frozenset({
    "implemented",
    "partial",
    "experimental",
    "external",
    "rejected",
    "not-applicable",
})


def feature_manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / "compiler" / "features.toml"


@lru_cache(maxsize=1)
def load_feature_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest_path = Path(path) if path is not None else feature_manifest_path()
    with manifest_path.open("rb") as handle:
        manifest = tomllib.load(handle)
    validate_feature_manifest(manifest, manifest_path.parent.parent)
    return manifest


def validate_feature_manifest(manifest: Mapping[str, Any], root: Path) -> None:
    metadata = manifest.get("metadata", {})
    if metadata.get("schema_version") != FEATURE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            "compiler/features.toml requires schema_version "
            f"{FEATURE_MANIFEST_SCHEMA_VERSION}"
        )

    features = manifest.get("features", [])
    feature_ids = [entry.get("id") for entry in features]
    if any(not isinstance(feature_id, str) or not feature_id for feature_id in feature_ids):
        raise ValueError("Every feature requires a non-empty string id")
    if len(feature_ids) != len(set(feature_ids)):
        raise ValueError("Feature ids must be unique")

    known_features = set(feature_ids)
    for entry in features:
        if entry.get("maturity") not in MATURITY_LEVELS:
            raise ValueError(f"Invalid maturity for feature {entry['id']}")
        if entry.get("semantics") not in SEMANTIC_CLASSIFICATIONS:
            raise ValueError(f"Invalid semantic classification for feature {entry['id']}")
        failure = entry.get("failure")
        if failure is not None and failure not in SEMANTIC_CLASSIFICATIONS:
            raise ValueError(f"Invalid failure classification for feature {entry['id']}")
        evidence = entry.get("evidence", [])
        if not evidence:
            raise ValueError(f"Feature {entry['id']} requires named evidence")
        for relative_path in evidence:
            if not (root / relative_path).is_file():
                raise ValueError(
                    f"Feature {entry['id']} references missing evidence: {relative_path}"
                )

    backend_names: set[str] = set()
    for backend in manifest.get("backends", []):
        name = backend.get("name")
        if not isinstance(name, str) or not name or name in backend_names:
            raise ValueError("Backend names must be non-empty and unique")
        backend_names.add(name)
        if backend.get("maturity") not in MATURITY_LEVELS:
            raise ValueError(f"Invalid maturity for backend {name}")
        unknown = set(backend.get("features", [])) - known_features
        if unknown:
            raise ValueError(f"Backend {name} references unknown features: {sorted(unknown)}")

    if metadata.get("default_backend") not in backend_names:
        raise ValueError("default_backend must name a registered backend")

    stage_ids: set[str] = set()
    for stage in manifest.get("pipeline_stages", []):
        stage_id = stage.get("id")
        if not isinstance(stage_id, str) or not stage_id or stage_id in stage_ids:
            raise ValueError("Pipeline stage ids must be non-empty and unique")
        stage_ids.add(stage_id)
        if stage.get("status") not in STAGE_STATUSES:
            raise ValueError(f"Invalid status for pipeline stage {stage_id}")
        for relative_path in stage.get("evidence", []):
            if not (root / relative_path).is_file():
                raise ValueError(
                    f"Pipeline stage {stage_id} references missing evidence: {relative_path}"
                )

    required_stages = {"parser", "type_checker", "typed_hir", "runtime", "backends"}
    missing_stages = required_stages - stage_ids
    if missing_stages:
        raise ValueError(f"Missing required pipeline stages: {sorted(missing_stages)}")

    known_operations = set(manifest.get("language", {}).get("stable_keywords", []))
    known_operations.update(manifest.get("language", {}).get("builtins", []))
    for effect in manifest.get("effects", []):
        if effect.get("classification") not in SEMANTIC_CLASSIFICATIONS:
            raise ValueError(f"Invalid effect classification for {effect.get('id')}")
        unknown_operations = set(effect.get("operations", [])) - known_operations
        if unknown_operations:
            raise ValueError(
                f"Effect {effect.get('id')} references unknown operations: {sorted(unknown_operations)}"
            )

    profiled_features: set[str] = set()
    for profile_id, profile in manifest.get("feature_stage_profiles", {}).items():
        profile_features = set(profile.get("features", []))
        duplicate_features = profiled_features & profile_features
        if duplicate_features:
            raise ValueError(
                f"Feature stage profile {profile_id} repeats features: {sorted(duplicate_features)}"
            )
        unknown_features = profile_features - known_features
        if unknown_features:
            raise ValueError(
                f"Feature stage profile {profile_id} references unknown features: {sorted(unknown_features)}"
            )
        profiled_features.update(profile_features)
        for stage_name in ("parser", "checker", "hir", "runtime", "backend"):
            if profile.get(stage_name) not in FEATURE_STAGE_STATUSES:
                raise ValueError(f"Invalid {stage_name} status for feature profile {profile_id}")
    if profiled_features != known_features:
        raise ValueError(
            "Feature stage profiles must cover every feature exactly once; missing "
            f"{sorted(known_features - profiled_features)}"
        )


def render_feature_matrix(manifest: Mapping[str, Any] | None = None) -> str:
    data = manifest or load_feature_manifest()
    metadata = data["metadata"]
    feature_by_id = {entry["id"]: entry for entry in data["features"]}
    lines = [
        "# Rove compiler feature matrix",
        "",
        "<!-- Generated from compiler/features.toml; do not edit by hand. -->",
        "",
        f"- Registry schema: `{metadata['schema_version']}`",
        f"- Language version: `{metadata['language_version']}`",
        f"- Typed HIR schema: `{metadata['hir_schema_version']}`",
        f"- Bundle ABI: `{metadata['bundle_abi_version']}`",
        "",
        "## Frozen inventory",
        "",
        f"- {len(data['language']['stable_keywords'])} stable keywords",
        f"- {len(data['inventory']['ast_nodes'])} AST node kinds",
        f"- {len(data['inventory']['hir_nodes'])} Typed HIR node kinds",
        f"- {len(data['diagnostics']['codes'])} diagnostic codes",
        f"- {len(data['language']['builtins'])} builtins and {len(data['language']['intrinsics'])} intrinsics",
        "",
        "## Backends",
        "",
        "| Backend | Maturity | Family | Artifact | Features |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for backend in sorted(data["backends"], key=lambda entry: entry["name"]):
        lines.append(
            f"| `{backend['name']}` | {backend['maturity']} | {backend['family']} | "
            f"{backend['artifact']} | {len(backend['features'])} |"
        )

    lines.extend([
        "",
        "## Compiler pipeline",
        "",
        "| Stage | Status | Authority | Evidence |",
        "| --- | --- | --- | --- |",
    ])
    for stage in data["pipeline_stages"]:
        evidence = "<br>".join(f"`{path}`" for path in stage["evidence"])
        lines.append(
            f"| `{stage['id']}` | {stage['status']} | `{stage['authority']}` | {evidence} |"
        )

    lines.extend([
        "",
        "## Feature contracts",
        "",
        "| Feature | Maturity | Semantics | Backends | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ])
    backend_map = {
        feature_id: sorted(
            backend["name"]
            for backend in data["backends"]
            if feature_id in backend["features"]
        )
        for feature_id in feature_by_id
    }
    stage_profile_map = {
        feature_id: profile
        for profile in data["feature_stage_profiles"].values()
        for feature_id in profile["features"]
    }
    for feature_id in sorted(feature_by_id):
        feature = feature_by_id[feature_id]
        evidence = "<br>".join(f"`{path}`" for path in feature["evidence"])
        targets = ", ".join(f"`{name}`" for name in backend_map[feature_id]) or "none"
        semantics = feature["semantics"]
        if feature.get("failure"):
            semantics += f"; failure: {feature['failure']}"
        lines.append(
            f"| `{feature_id}` | {feature['maturity']} | {semantics} | "
            f"{targets} | {evidence} |"
        )
    lines.extend([
        "",
        "## Per-feature pipeline status",
        "",
        "| Feature | Parser | Checker | HIR | Runtime | Backend |",
        "| --- | --- | --- | --- | --- | --- |",
    ])
    for feature_id in sorted(feature_by_id):
        profile = stage_profile_map[feature_id]
        lines.append(
            f"| `{feature_id}` | {profile['parser']} | {profile['checker']} | "
            f"{profile['hir']} | {profile['runtime']} | {profile['backend']} |"
        )
    lines.extend([
        "",
        "## Standard library contracts",
        "",
        "| Module | Maturity | Targets |",
        "| --- | --- | --- |",
    ])
    for module in sorted(data["stdlib"], key=lambda entry: entry["module"]):
        targets = ", ".join(f"`{name}`" for name in module["targets"])
        lines.append(f"| `std/{module['module']}` | {module['maturity']} | {targets} |")
    lines.append("")
    return "\n".join(lines)
