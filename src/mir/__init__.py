"""Experimental Nyx MIR infrastructure.

MIR is not part of the default compilation route. Importing this package does
not redirect any existing Typed HIR backend.
"""

from .builder import MIRFunctionBuilder
from .abi import (
    ABIProfile,
    ABIValue,
    BUNDLE_ABI_V1_VERSION,
    BUNDLE_ABI_V2_DRAFT_VERSION,
    BUNDLE_ABI_V2_STATUS,
    CAdapterContract,
    FunctionABI,
    abi_profile,
    check_c_adapter,
    classify_function_abi,
)
from .interpreter import MIRExecutionResult, MIRInterpreter, MIRTrap
from .codegen_c17 import emit_legalized_c17
from .codegen_cpp import MIRCodegenError, emit_legalized_cpp
from .codegen_javascript import emit_legalized_javascript
from .codegen_llvm import emit_legalized_llvm
from .codegen_python import emit_legalized_python
from .codegen_rust import emit_legalized_rust
from .codegen_wasm import emit_legalized_wasm, emit_legalized_wat, lower_legalized_wasm
from .legalization import (
    MIR_BACKEND_MIGRATION_ORDER,
    MIR_BACKEND_PROFILES,
    MIR_LEGALIZATION_SCHEMA_VERSION,
    MIRBackendProfile,
    MIRLegalizationError,
    MIRLegalizationIssue,
    collect_legalization_issues,
    legalize_mir,
    mir_backend_manifest,
    resolve_mir_backend_profile,
)
from .layout import (
    FieldLayout,
    HOSTED_X64,
    LayoutEngine,
    MIRLayoutError,
    NATIVE_X64,
    TARGET_DATA_LAYOUTS,
    TargetDataLayout,
    TypeLayout,
    VariantLayout,
    WASM32,
    data_layout_for_target,
)
from .lowering import MIRLoweringError, lower_hir_skeleton, lower_hir_to_mir
from .model import *
from .passes import MIRPass, MIRPassManager, MIRPassRecord, MIRPassResult
from .printer import print_mir
from .serialization import fingerprint, from_data, from_json, to_data, to_json
from .effects import MIR_EFFECT_ORDER, VALID_MIR_EFFECTS, infer_module_effects
from .coroutines import elaborate_coroutine, elaborate_coroutines
from .types import MIRType, from_hir_type
from .verifier import (
    MIRVerificationError,
    MIRVerificationIssue,
    collect_mir_issues,
    verify_mir,
)

__all__ = [name for name in globals() if not name.startswith("_")]
