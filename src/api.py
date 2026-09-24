"""Stable, side-effect-free embedding API for the Rove compiler frontend.

The CLI, language server, build systems, and editor plugins can all consume the
same parse/check/emit pipeline without redirecting stdout or catching
``SystemExit``.
"""

from dataclasses import dataclass, fields, is_dataclass
import os
import re
from typing import Iterable, Optional, Tuple

from src.codegen import UniversalCodeGen
from src.codegen.hir_cpp import CppEmissionError, emit_cpp
from src.codegen.hir_javascript import JavaScriptEmissionError, emit_javascript
from src.codegen.hir_python import PythonEmissionError, emit_python
from src.codegen.hir_rust import RustEmissionError, emit_rust
from src.codegen.wasm_ir import BundleCompileError
from src.codegen.c17_scalar import C17EmissionError
from src.codegen.llvm_scalar import LLVMEmissionError
from src.core.ast_nodes import ProgramNode
from src.core.backend_capabilities import BACKENDS, normalize_backend_name, resolve_backend
from src.core.diagnostics import DiagnosticEmitter, DiagnosticError
from src.core.module_loader import ModuleLoader
from src.core.type_checker import TypeChecker
from src.ir import (
    IRLoweringError,
    IRAwait,
    IRCall,
    IREnum,
    IRFunction,
    IRModule,
    IRSpawn,
    IRResultPropagate,
    IRThrow,
    IRYield,
    IRTryCatch,
    IRVerificationError,
    PassRecord,
    fingerprint,
    lower_to_hir,
    optimize_hir,
    verify_hir,
)
from src.plugins import CompilerPlugin, PluginContext, PluginExecutionError


_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_HIR_AUTHORITATIVE_TARGETS = frozenset(("cpp", "js", "python", "rust", "wasm", "c", "llvm"))


class BackendCapabilityError(RuntimeError):
    """Raised before emission when a target cannot preserve HIR semantics."""


def _contains_hir_node(value: object, node_types: tuple[type, ...]) -> bool:
    if isinstance(value, node_types):
        return True
    if isinstance(value, tuple):
        return any(_contains_hir_node(item, node_types) for item in value)
    if is_dataclass(value):
        return any(
            _contains_hir_node(getattr(value, field.name), node_types)
            for field in fields(value)
        )
    return False


def _contains_async_function(value: object) -> bool:
    if isinstance(value, IRFunction) and value.is_async:
        return True
    if isinstance(value, tuple):
        return any(_contains_async_function(item) for item in value)
    if is_dataclass(value):
        return any(
            _contains_async_function(getattr(value, field.name))
            for field in fields(value)
        )
    return False


def _contains_hir_call_symbol(value: object, symbols: frozenset[str]) -> bool:
    if isinstance(value, IRCall) and value.callee_symbol in symbols:
        return True
    if isinstance(value, tuple):
        return any(_contains_hir_call_symbol(item, symbols) for item in value)
    if is_dataclass(value):
        return any(
            _contains_hir_call_symbol(getattr(value, field.name), symbols)
            for field in fields(value)
        )
    return False


def _contains_payload_enum(value: object) -> bool:
    if isinstance(value, IREnum) and any(member.is_variant for member in value.members):
        return True
    if isinstance(value, tuple):
        return any(_contains_payload_enum(item) for item in value)
    if is_dataclass(value):
        return any(
            _contains_payload_enum(getattr(value, field.name))
            for field in fields(value)
        )
    return False


def _feature_hint(feature: str) -> str:
    targets = [name for name, spec in BACKENDS.items() if feature in spec.features]
    return "supported targets: " + ", ".join(targets)


def backend_feature_requirements(hir: IRModule) -> tuple[str, ...]:
    """Return special semantic capabilities required by checked Typed HIR."""
    required: set[str] = set()
    if _contains_payload_enum(hir):
        required.add("payload_enums")
    if _contains_hir_node(hir, (IRResultPropagate,)):
        required.add("result_propagation")
    if _contains_hir_node(hir, (IRYield,)):
        required.add("iterator_yield")
    if _contains_hir_call_symbol(
        hir, frozenset(("builtin::map", "builtin::filter", "builtin::fold"))
    ):
        required.add("collection_combinators")
    if _contains_hir_node(hir, (IRThrow, IRTryCatch)):
        required.add("exceptions")
    if _contains_hir_node(hir, (IRAwait,)) or _contains_async_function(hir):
        required.add("async_tasks")
    if _contains_hir_node(hir, (IRSpawn,)):
        required.add("spawn")
    if _contains_hir_call_symbol(hir, frozenset(("builtin::channel",))):
        required.add("channels")
    return tuple(sorted(required))


def _validate_backend_features(hir: IRModule) -> None:
    backend = resolve_backend(hir.target)
    if backend is None:
        return
    required = frozenset(backend_feature_requirements(hir))
    if "payload_enums" in required and "payload_enums" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support payload enum semantics yet; "
            + _feature_hint("payload_enums")
        )
    if "result_propagation" in required and "result_propagation" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support Result propagation semantics yet; "
            + _feature_hint("result_propagation")
        )
    if "iterator_yield" in required and "iterator_yield" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support lazy Iterator<T>/yield semantics yet; "
            + _feature_hint("iterator_yield")
        )
    if "collection_combinators" in required and "collection_combinators" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support collection combinators yet; "
            + _feature_hint("collection_combinators")
        )
    if "exceptions" in required and "exceptions" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support Rove exception semantics "
            f"(try/catch/throw); {_feature_hint('exceptions')}"
        )
    if "async_tasks" in required and "async_tasks" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support Rove Task<T> semantics "
            f"(async/await); {_feature_hint('async_tasks')}"
        )
    if "spawn" in required and "spawn" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support Rove spawn semantics; "
            + _feature_hint("spawn")
        )
    if "channels" in required and "channels" not in backend.features:
        raise BackendCapabilityError(
            f"target '{backend.name}' does not support Rove channel semantics; "
            + _feature_hint("channels")
        )
@dataclass(frozen=True)
class CompilerDiagnostic:
    severity: str
    code: str
    message: str
    path: str
    line: int
    column: int
    length: int = 1
    expected: str = ""
    found: str = ""
    help: str = ""
    note: str = ""
    searched: Tuple[str, ...] = ()
    rendered: str = ""

    @classmethod
    def from_error(cls, error: DiagnosticError) -> "CompilerDiagnostic":
        return cls(
            severity="error",
            code=error.code,
            message=error.title,
            path=error.filepath,
            line=error.line,
            column=error.col,
            length=error.length,
            expected=error.expected,
            found=error.found,
            help=error.help_msg,
            note=error.note,
            searched=tuple(error.searched),
            rendered=_ANSI_ESCAPE.sub("", error.formatted_msg).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "length": self.length,
            "expected": self.expected,
            "found": self.found,
            "help": self.help,
            "note": self.note,
            "searched": list(self.searched),
        }


@dataclass(frozen=True)
class SourceArtifact:
    target: str
    kind: str
    extension: str
    media_type: str
    content: str

    def to_dict(self, include_content: bool = True) -> dict:
        result = {
            "target": self.target,
            "kind": self.kind,
            "extension": self.extension,
            "media_type": self.media_type,
        }
        if include_content:
            result["content"] = self.content
        return result


@dataclass(frozen=True)
class CompilationResult:
    success: bool
    target: str
    diagnostics: Tuple[CompilerDiagnostic, ...] = ()
    artifact: Optional[SourceArtifact] = None
    ast: Optional[ProgramNode] = None
    hir: Optional[IRModule] = None
    optimization_records: Tuple[PassRecord, ...] = ()

    def to_dict(self, include_content: bool = True) -> dict:
        hir_metadata = None
        if self.hir is not None:
            hir_metadata = {
                "schema_version": self.hir.schema_version,
                "fingerprint": fingerprint(self.hir),
            }
        return {
            "success": self.success,
            "target": self.target,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "artifact": self.artifact.to_dict(include_content) if self.artifact else None,
            "hir": hir_metadata,
            "passes": [
                {
                    "name": record.name,
                    "changed": record.changed,
                    "before_fingerprint": record.before_fingerprint,
                    "after_fingerprint": record.after_fingerprint,
                }
                for record in self.optimization_records
            ],
        }


class RoveCompiler:
    """Reusable compiler session with no process exits and no console output."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        plugins: Iterable[CompilerPlugin] = (),
    ):
        self.base_dir = os.path.abspath(base_dir or os.getcwd())
        self.plugins = tuple(plugins)
        plugin_names = [plugin.name for plugin in self.plugins]
        if len(plugin_names) != len(set(plugin_names)):
            raise ValueError("Compiler plugin names must be unique within a session")

    def check_source(
        self,
        source: str,
        *,
        filename: str = "<memory>",
        target: Optional[str] = None,
    ) -> CompilationResult:
        resolved_target = normalize_backend_name(target)
        active_target = resolved_target
        try:
            with DiagnosticEmitter.scoped(exit_on_error=False, emit_output=False):
                loader = ModuleLoader(base_dir=self.base_dir, target=target)
                ast = loader.load_program(filename, source)
                active_target = ast.target
                context = PluginContext(filename, self.base_dir, ast.target, source)
                self._run_ast_hook("after_parse", context, ast)
                TypeChecker(ast, filename, source).check()
                self._run_ast_hook("after_check", context, ast)
                hir = lower_to_hir(ast, filename)
                verify_hir(hir)
                self._run_hir_observer("after_lower", context, hir)
                hir = self._run_hir_transforms(context, hir)
                optimized = optimize_hir(hir)
                hir = optimized.module
                self._run_hir_observer("after_optimize", context, hir)
            return CompilationResult(
                success=True,
                target=ast.target,
                ast=ast,
                hir=hir,
                optimization_records=optimized.records,
            )
        except DiagnosticError as error:
            return CompilationResult(
                success=False,
                target=active_target,
                diagnostics=(CompilerDiagnostic.from_error(error),),
            )
        except (IRLoweringError, IRVerificationError) as error:
            return self._hir_failure(error, filename, active_target)
        except PluginExecutionError as error:
            return self._plugin_failure(error, filename, active_target)

    def compile_source(
        self,
        source: str,
        *,
        target: Optional[str] = None,
        filename: str = "<memory>",
    ) -> CompilationResult:
        checked = self.check_source(source, filename=filename, target=target)
        if not checked.success or checked.ast is None or checked.hir is None:
            return checked

        try:
            artifact = self._emit(checked.ast, checked.hir)
            context = PluginContext(filename, self.base_dir, checked.target, source)
            for plugin in self.plugins:
                try:
                    transformed = plugin.transform_artifact(context, artifact)
                except Exception as cause:
                    raise PluginExecutionError(plugin.name, "transform_artifact", cause) from cause
                if not isinstance(transformed, SourceArtifact):
                    cause = TypeError("transform_artifact must return SourceArtifact")
                    raise PluginExecutionError(plugin.name, "transform_artifact", cause)
                artifact = transformed
        except PluginExecutionError as error:
            return self._plugin_failure(error, filename, checked.target)
        except (
            BackendCapabilityError,
            BundleCompileError,
            C17EmissionError,
            CppEmissionError,
            JavaScriptEmissionError,
            LLVMEmissionError,
            PythonEmissionError,
            RustEmissionError,
        ) as error:
            return self._backend_failure(error, filename, checked.target)
        return CompilationResult(
            success=True,
            target=checked.target,
            artifact=artifact,
            ast=checked.ast,
            hir=checked.hir,
            optimization_records=checked.optimization_records,
        )

    def _run_ast_hook(
        self,
        hook_name: str,
        context: PluginContext,
        ast: ProgramNode,
    ) -> None:
        for plugin in self.plugins:
            try:
                getattr(plugin, hook_name)(context, ast)
            except Exception as cause:
                raise PluginExecutionError(plugin.name, hook_name, cause) from cause

    def _run_hir_observer(
        self,
        hook_name: str,
        context: PluginContext,
        hir: IRModule,
    ) -> None:
        for plugin in self.plugins:
            before = fingerprint(hir)
            try:
                getattr(plugin, hook_name)(context, hir)
            except Exception as cause:
                raise PluginExecutionError(plugin.name, hook_name, cause) from cause
            if fingerprint(hir) != before:
                cause = TypeError(f"{hook_name} must not mutate immutable HIR; use transform_hir")
                raise PluginExecutionError(plugin.name, hook_name, cause)

    def _run_hir_transforms(self, context: PluginContext, hir: IRModule) -> IRModule:
        current = hir
        for plugin in self.plugins:
            before = fingerprint(current)
            try:
                transformed = plugin.transform_hir(context, current)
                if not isinstance(transformed, IRModule):
                    raise TypeError("transform_hir must return IRModule")
                if transformed.target != current.target:
                    raise ValueError("transform_hir cannot change the compilation target")
                if transformed.source_name != current.source_name:
                    raise ValueError("transform_hir cannot change the module source identity")
                if transformed.schema_version != current.schema_version:
                    raise ValueError("transform_hir cannot change the HIR schema version")
                verify_hir(transformed)
                after = fingerprint(transformed)
                if after != before and context.target not in _HIR_AUTHORITATIVE_TARGETS:
                    raise ValueError(
                        f"target '{context.target}' is not HIR-authoritative yet; "
                        "semantic transform_hir changes require the typed_hir_v1 capability"
                    )
            except Exception as cause:
                raise PluginExecutionError(plugin.name, "transform_hir", cause) from cause
            current = transformed
        return current

    @staticmethod
    def _plugin_failure(
        error: PluginExecutionError,
        filename: str,
        target: str,
    ) -> CompilationResult:
        message = f"Compiler Plugin Failure: '{error.plugin_name}' ({error.hook})"
        diagnostic = CompilerDiagnostic(
            severity="error",
            code="E9001",
            message=message,
            path=filename,
            line=1,
            column=1,
            help="Disable or update the failing trusted compiler plugin.",
            note=str(error.cause),
            rendered=f"error[E9001]: {message}\n  --> {filename}:1:1\n  = note: {error.cause}",
        )
        return CompilationResult(success=False, target=target, diagnostics=(diagnostic,))

    @staticmethod
    def _hir_failure(
        error: IRLoweringError | IRVerificationError,
        filename: str,
        target: str,
    ) -> CompilationResult:
        if isinstance(error, IRLoweringError):
            issues = (("HIRL0001", error.message, error.span),)
        else:
            issues = tuple((issue.code, issue.message, issue.span) for issue in error.issues)
        diagnostics = tuple(
            CompilerDiagnostic(
                severity="error",
                code=code,
                message=message,
                path=span.source or filename,
                line=span.line,
                column=span.column,
                length=span.length,
                help="Fix the source construct before backend emission.",
                rendered=(
                    f"error[{code}]: {message}\n"
                    f"  --> {span.source or filename}:{span.line}:{span.column}"
                ),
            )
            for code, message, span in issues
        )
        return CompilationResult(success=False, target=target, diagnostics=diagnostics)

    @staticmethod
    def _backend_failure(error: Exception, filename: str, target: str) -> CompilationResult:
        message = f"Backend emission failed for target '{target}'"
        diagnostic = CompilerDiagnostic(
            severity="error",
            code="E3001",
            message=message,
            path=filename,
            line=1,
            column=1,
            help="Use a construct supported by the selected backend or choose another target.",
            note=str(error),
            rendered=f"error[E3001]: {message}\n  --> {filename}:1:1\n  = note: {error}",
        )
        return CompilationResult(success=False, target=target, diagnostics=(diagnostic,))

    def check_file(self, path: str, *, target: Optional[str] = None) -> CompilationResult:
        source_path = os.path.abspath(path)
        with open(source_path, "r", encoding="utf-8-sig") as handle:
            source = handle.read()
        return self.check_source(source, filename=source_path, target=target)

    def compile_file(self, path: str, *, target: Optional[str] = None) -> CompilationResult:
        source_path = os.path.abspath(path)
        with open(source_path, "r", encoding="utf-8-sig") as handle:
            source = handle.read()
        return self.compile_source(source, filename=source_path, target=target)

    @staticmethod
    def _emit(ast: ProgramNode, hir: IRModule) -> SourceArtifact:
        target = ast.target
        _validate_backend_features(hir)
        codegen = UniversalCodeGen(ast)

        if target == "cpp":
            return SourceArtifact(target, "cpp20", ".cpp", "text/x-c++src", emit_cpp(hir))
        if target == "asm":
            return SourceArtifact(target, "cpp20", ".cpp", "text/x-c++src", codegen.gen_cpp())
        if target == "js":
            return SourceArtifact(target, "javascript", ".js", "text/javascript", emit_javascript(hir))
        if target == "python":
            return SourceArtifact(target, "python", ".py", "text/x-python", emit_python(hir))
        if target == "rust":
            return SourceArtifact(target, "rust", ".rs", "text/x-rustsrc", emit_rust(hir))
        if target == "react":
            return SourceArtifact(target, "react-tsx", ".tsx", "text/tsx", codegen.gen_react())
        if target == "wasm":
            from src.codegen.wasm_ir import BundleLowerer

            source_basename = os.path.splitext(os.path.basename(hir.source_name))[0]
            module_name = source_basename if source_basename and not source_basename.startswith("<") else "rove_module"
            wat = BundleLowerer(hir, module_name).lower().to_wat()
            return SourceArtifact(target, "webassembly-text", ".wat", "application/wasm-text", wat)
        if target == "c":
            from src.codegen.c17_scalar import emit_c17

            return SourceArtifact(target, "c17", ".c", "text/x-csrc", emit_c17(hir))
        if target == "llvm":
            from src.codegen.llvm_scalar import emit_llvm

            return SourceArtifact(target, "llvm-ir", ".ll", "text/x-llvm", emit_llvm(hir))

        raise ValueError(f"No source emitter registered for target '{target}'")


def check_source(
    source: str,
    *,
    filename: str = "<memory>",
    target: Optional[str] = None,
    base_dir: Optional[str] = None,
    plugins: Iterable[CompilerPlugin] = (),
) -> CompilationResult:
    return RoveCompiler(base_dir, plugins).check_source(source, filename=filename, target=target)


def compile_source(
    source: str,
    *,
    target: Optional[str] = None,
    filename: str = "<memory>",
    base_dir: Optional[str] = None,
    plugins: Iterable[CompilerPlugin] = (),
) -> CompilationResult:
    return RoveCompiler(base_dir, plugins).compile_source(source, target=target, filename=filename)


# Rove is the public product name from v6 onward.  Keep the original class as
# an API alias so existing integrations can migrate without a flag day.
NyxCompiler = RoveCompiler
