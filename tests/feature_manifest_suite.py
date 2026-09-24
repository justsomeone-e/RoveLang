import inspect
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core import ast_nodes
from src.core.backend_capabilities import (
    BACKENDS,
    CAPABILITY_SCHEMA_VERSION,
    STDLIB_CONTRACTS,
)
from src.core.feature_manifest import load_feature_manifest, render_feature_matrix
from src.core.language_surface import (
    BUILTIN_NAMES,
    EXPERIMENTAL_KEYWORDS,
    RESERVED_KEYWORDS,
    STABLE_KEYWORDS,
    TYPE_NAMES,
)
from src.ir import model
from src.ir.builtins import BUILTINS, INTRINSICS
from src.ir.model import HIR_SCHEMA_VERSION


def _defined_classes(module: object, prefix: str, excluded: set[str]) -> set[str]:
    return {
        name
        for name, value in inspect.getmembers(module, inspect.isclass)
        if value.__module__ == module.__name__ and name.startswith(prefix) and name not in excluded
    }


def run_feature_manifest_suite() -> bool:
    print("=" * 70)
    print("NYX M0 CANONICAL FEATURE REGISTRY")
    print("=" * 70)

    manifest = load_feature_manifest()
    metadata = manifest["metadata"]
    language = manifest["language"]
    inventory = manifest["inventory"]

    assert metadata["language_version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert metadata["capability_schema_version"] == CAPABILITY_SCHEMA_VERSION
    assert metadata["hir_schema_version"] == HIR_SCHEMA_VERSION
    assert metadata["bundle_abi_version"] == 1
    assert metadata["lockfile_version"] == 1

    assert tuple(language["stable_keywords"]) == STABLE_KEYWORDS
    assert tuple(language["experimental_keywords"]) == EXPERIMENTAL_KEYWORDS
    assert tuple(language["reserved_keywords"]) == RESERVED_KEYWORDS
    assert tuple(language["types"]) == TYPE_NAMES
    assert set(language["builtins"]) == set(BUILTINS) == set(BUILTIN_NAMES)
    assert set(language["intrinsics"]) == set(INTRINSICS)
    assert tuple(inventory["type_forms"]) == (
        "named", "generic", "optional", "pointer", "function"
    )
    assert manifest["effect_model"]["unknown_calls"] == "effectful"

    diagnostic_codes: set[str] = set()
    for directory, patterns in ((ROOT / "src", ("*.py",)), (ROOT / "compiler", ("*.rove",))):
        for pattern in patterns:
            for source_path in directory.rglob(pattern):
                diagnostic_codes.update(
                    re.findall(
                        r"\b(?:E\d{4}|MIR[A-Z]?\d{4})\b",
                        source_path.read_text(encoding="utf-8"),
                    )
                )
    assert set(manifest["diagnostics"]["codes"]) == diagnostic_codes

    ast_class_names = _defined_classes(ast_nodes, "", {"ASTNode"})
    hir_class_names = _defined_classes(
        model,
        "IR",
        {"IRNode", "IRExpr", "IRStatement"},
    )
    assert set(inventory["ast_nodes"]) == ast_class_names
    assert set(inventory["hir_nodes"]) == hir_class_names

    manifest_backends = {entry["name"]: entry for entry in manifest["backends"]}
    assert set(manifest_backends) == set(BACKENDS)
    for name, spec in BACKENDS.items():
        declared = manifest_backends[name]
        assert declared["display_name"] == spec.display_name
        assert declared["family"] == spec.family
        assert declared["artifact"] == spec.artifact
        assert declared["maturity"] == spec.maturity
        assert tuple(declared["aliases"]) == spec.aliases
        assert set(declared["features"]) == set(spec.features)

    manifest_stdlib = {entry["module"]: entry for entry in manifest["stdlib"]}
    assert set(manifest_stdlib) == set(STDLIB_CONTRACTS)
    for name, contract in STDLIB_CONTRACTS.items():
        declared = manifest_stdlib[name]
        assert declared["maturity"] == contract.maturity
        assert set(declared["targets"]) == set(contract.targets)

    declared_features = {entry["id"] for entry in manifest["features"]}
    implemented_features = set().union(*(spec.features for spec in BACKENDS.values()))
    assert declared_features == implemented_features
    stable_features = {
        entry["id"] for entry in manifest["features"] if entry["maturity"] == "stable"
    }
    assert stable_features
    for entry in manifest["features"]:
        if entry["id"] in stable_features:
            assert entry["evidence"], f"Stable feature {entry['id']} has no conformance fixture"

    generated = render_feature_matrix(manifest)
    checked_in = (ROOT / "docs" / "generated" / "FEATURE_MATRIX.md").read_text(encoding="utf-8")
    assert checked_in == generated

    print(
        f"[PASS] {len(STABLE_KEYWORDS)} keywords, {len(ast_class_names)} AST nodes, "
        f"{len(hir_class_names)} HIR nodes, {len(diagnostic_codes)} diagnostics, "
        f"{len(declared_features)} features, "
        f"{len(BACKENDS)} backends, and {len(STDLIB_CONTRACTS)} stdlib contracts"
    )
    return True


if __name__ == "__main__":
    raise SystemExit(0 if run_feature_manifest_suite() else 1)
