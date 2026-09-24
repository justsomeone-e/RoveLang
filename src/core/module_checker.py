"""Module-boundary-preserving semantic checking for loaded Rove programs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .ast_nodes import (
    EnumDefNode,
    ExternFnDeclNode,
    FunctionDefNode,
    ImportNode,
    ProgramNode,
    StructDefNode,
    TraitDefNode,
    TypeAliasNode,
    VarDeclNode,
)
from .identities import ModuleId
from .module_loader import LoadedProgramGraph
from .type_checker import TypeChecker


_INTERFACE_DECLARATIONS = (
    FunctionDefNode,
    StructDefNode,
    TraitDefNode,
    TypeAliasNode,
    EnumDefNode,
    ExternFnDeclNode,
    VarDeclNode,
)


@dataclass(frozen=True, slots=True)
class CheckedModule:
    module_id: ModuleId
    checker: TypeChecker


@dataclass(frozen=True, slots=True)
class CheckedProgramGraph:
    root: ModuleId
    modules: tuple[CheckedModule, ...]

    def checker(self, module_id: ModuleId) -> TypeChecker:
        for checked in self.modules:
            if checked.module_id == module_id:
                return checked.checker
        raise KeyError(module_id)


def _interface_declarations(
    loaded: LoadedProgramGraph,
    importer: ModuleId,
    imported: ModuleId,
) -> list[object]:
    allowed = loaded.graph.imported_symbols(importer, imported)
    declarations: list[object] = []
    for statement in loaded.module(imported).statements:
        if not isinstance(statement, _INTERFACE_DECLARATIONS):
            continue
        name = getattr(statement, "name", "")
        if allowed is not None and name not in allowed:
            continue
        declaration = deepcopy(statement)
        declaration._interface_only = True
        declarations.append(declaration)
    return declarations


def check_program_graph(loaded: LoadedProgramGraph) -> CheckedProgramGraph:
    """Check every module against local declarations and direct imports only.

    Imported declaration copies participate in signature registration but their
    bodies are not checked in the importer. The original AST for each module is
    checked once in dependency order, retaining inferred types for later HIR
    lowering through the compatibility linker.
    """
    checked: list[CheckedModule] = []
    records = loaded.graph.modules
    for module_id in loaded.graph.initialization_order(loaded.root):
        program = loaded.module(module_id)
        interface: list[object] = []
        for imported in loaded.graph.direct_imports(module_id):
            interface.extend(_interface_declarations(loaded, module_id, imported))
        local_statements = [
            statement
            for statement in program.statements
            if not (isinstance(statement, ImportNode) and statement.ecosystem is None)
        ]
        view = ProgramNode(program.target, interface + local_statements)
        record = records[module_id]
        checker = TypeChecker(view, record.filepath, loaded.source(module_id))
        checker.check()
        checked.append(CheckedModule(module_id, checker))
    return CheckedProgramGraph(loaded.root, tuple(checked))
