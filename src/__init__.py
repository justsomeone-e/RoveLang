# Rove public embedding API
from .api import (
    CompilationResult,
    CompilerDiagnostic,
    RoveCompiler,
    NyxCompiler,
    SourceArtifact,
    check_source,
    compile_source,
)
from .plugins import CompilerPlugin, PluginContext, PluginExecutionError
from .version import VERSION as __version__
from .ir import (
    IRModule,
    IRType,
    IRVerificationError,
    PassManager,
    PassPipelineResult,
    fingerprint,
    optimize_hir,
    to_data,
    to_json,
    verify_hir,
)

__all__ = [
    "CompilationResult",
    "CompilerDiagnostic",
    "RoveCompiler",
    "NyxCompiler",
    "SourceArtifact",
    "check_source",
    "compile_source",
    "CompilerPlugin",
    "PluginContext",
    "PluginExecutionError",
    "IRModule",
    "IRType",
    "IRVerificationError",
    "PassManager",
    "PassPipelineResult",
    "fingerprint",
    "optimize_hir",
    "to_data",
    "to_json",
    "verify_hir",
    "__version__",
]
