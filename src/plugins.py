"""Explicit in-process extension points for trusted Rove compiler plugins."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.api import SourceArtifact
    from src.core.ast_nodes import ProgramNode
    from src.ir.model import IRModule


@dataclass(frozen=True)
class PluginContext:
    filename: str
    base_dir: str
    target: str
    source: str


class CompilerPlugin:
    """Base class for explicitly registered, trusted compiler plugins.

    Hooks run in registration order. HIR observer hooks receive immutable IR.
    Semantic HIR changes must be returned from ``transform_hir`` and are
    accepted only by backends that declare HIR authoritative.
    """

    name = "compiler-plugin"

    def after_parse(self, context: PluginContext, ast: "ProgramNode") -> None:
        pass

    def after_check(self, context: PluginContext, ast: "ProgramNode") -> None:
        pass

    def after_lower(self, context: PluginContext, hir: "IRModule") -> None:
        pass

    def transform_hir(self, context: PluginContext, hir: "IRModule") -> "IRModule":
        return hir

    def after_optimize(self, context: PluginContext, hir: "IRModule") -> None:
        pass

    def transform_artifact(
        self,
        context: PluginContext,
        artifact: "SourceArtifact",
    ) -> "SourceArtifact":
        return artifact


class PluginExecutionError(Exception):
    def __init__(self, plugin_name: str, hook: str, cause: Exception):
        self.plugin_name = plugin_name
        self.hook = hook
        self.cause = cause
        super().__init__(f"Compiler plugin '{plugin_name}' failed in {hook}: {cause}")
