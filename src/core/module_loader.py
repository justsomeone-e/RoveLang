import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Tuple

_root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from src.core.lexer import Lexer
from src.core.parser import Parser
from src.core.ast_nodes import (
    ProgramNode, ImportNode, FunctionDefNode, StructDefNode, TraitDefNode,
    ImplBlockNode, TypeAliasNode, ASTNode, EnumDefNode, ExternFnDeclNode,
    VarDeclNode, NativeIncludeNode, NativeLinkNode, NativeRawNode
)
from src.core.diagnostics import DiagnosticEmitter
from src.core.foreign_bindings import ForeignBindingRegistry
from src.core.identities import DefId, ModuleGraph, ModuleId
from src.core.backend_capabilities import (
    PENDING_FOREIGN_ECOSYSTEMS,
    foreign_import_targets,
    get_stdlib_contract,
    normalize_backend_name,
    resolve_backend,
    stdlib_module_from_import,
)
from src.toolchain.manifest import NyxLock


@dataclass(frozen=True, slots=True)
class LoadedProgramGraph:
    root: ModuleId
    graph: ModuleGraph
    modules: Tuple[Tuple[ModuleId, ProgramNode], ...]
    compatibility_program: ProgramNode
    sources: Tuple[Tuple[ModuleId, str], ...]

    def module(self, module_id: ModuleId) -> ProgramNode:
        for candidate, program in self.modules:
            if candidate == module_id:
                return program
        raise KeyError(module_id)

    def source(self, module_id: ModuleId) -> str:
        for candidate, source in self.sources:
            if candidate == module_id:
                return source
        raise KeyError(module_id)

class ModuleLoader:
    def __init__(
        self,
        base_dir: Optional[str] = None,
        target: Optional[str] = None,
        track_identities: bool = True,
    ):
        self.base_dir = base_dir or os.getcwd()
        self.stdlib_dir = os.path.join(_root_dir, "src", "stdlib")
        self.requested_target = target
        self.track_identities = track_identities
        self.target_name = ""
        self.loaded_modules: Dict[str, ProgramNode] = {}
        self.import_stack: List[str] = []
        self.symbol_origins: Dict[str, str] = {}
        self.symbol_definitions: Dict[str, DefId] = {}
        self.collected_declarations: List[ASTNode] = []
        self.module_programs: Dict[ModuleId, ProgramNode] = {}
        self.module_sources: Dict[ModuleId, str] = {}
        self.module_graph = ModuleGraph()
        self._foreign_bindings: Optional[ForeignBindingRegistry] = None
        self.package_roots = self._load_package_roots()

    def _load_package_roots(self) -> Dict[str, str]:
        current = os.path.realpath(self.base_dir)
        while True:
            lock_path = next(
                (
                    os.path.join(current, name)
                    for name in ("rove.lock", "nyx.lock")
                    if os.path.isfile(os.path.join(current, name))
                ),
                None,
            )
            if lock_path:
                roots: Dict[str, str] = {}
                for name, item in NyxLock.read_local_dependencies(lock_path).items():
                    path = item.get("path")
                    if path:
                        roots[name] = os.path.realpath(os.path.join(current, path))
                return roots
            parent = os.path.dirname(current)
            if parent == current:
                return {}
            current = parent

    def resolve_module_path(self, import_path: str, current_file: str) -> Tuple[Optional[str], List[str]]:
        """Resolves module path to an absolute filesystem path and returns all searched candidate paths."""
        searched = []
        
        # 1. Standard / Native Library: std/math, native/gpio, std/os
        if any(import_path.startswith(p) for p in ("std/", "std::", "native/", "native::")):
            submodule = import_path.replace("std::", "").replace("std/", "").replace("native::", "").replace("native/", "")
            for ext in (".rove", ".nyx", ""):
                base = submodule if submodule.endswith(ext) else submodule + ext
                cand = os.path.join(self.stdlib_dir, base)
                if cand not in searched: searched.append(cand)
                if os.path.exists(cand):
                    return cand, searched
            return None, searched

        # 2. Deterministically locked local package import: physics/vector
        normalized_import = import_path.replace("::", "/").replace("\\", "/").strip("/")
        package_name, _, package_module = normalized_import.partition("/")
        package_root = self.package_roots.get(package_name)
        if package_root:
            package_source = os.path.join(package_root, "src")
            bases = []
            if package_module:
                bases.append(os.path.join(package_source, package_module))
                bases.append(os.path.join(package_root, package_module))
            else:
                bases.extend((os.path.join(package_source, "lib"), os.path.join(package_source, "main")))
            for base in bases:
                candidates = (
                    [base]
                    if base.endswith((".rove", ".nyx"))
                    else [
                        base + ".rove",
                        os.path.join(base, "index.rove"),
                        base + ".nyx",
                        os.path.join(base, "index.nyx"),
                    ]
                )
                for candidate in candidates:
                    if candidate not in searched:
                        searched.append(candidate)
                    if os.path.isfile(candidate):
                        return candidate, searched
            return None, searched

        # 3. Local relative import: ./utils, ../math, helper.rove
        curr_dir = os.path.dirname(os.path.abspath(current_file)) if current_file and current_file != "<memory>" else self.base_dir
        cand1 = os.path.normpath(os.path.join(curr_dir, import_path))
        for ext in (".rove", ".nyx", ""):
            cand_f = cand1 if cand1.endswith(ext) else cand1 + ext
            if cand_f not in searched: searched.append(cand_f)
            if os.path.exists(cand_f):
                return cand_f, searched
        for idx in ("index.rove", "index.nyx"):
            cand_idx = os.path.join(cand1, idx)
            if cand_idx not in searched: searched.append(cand_idx)
            if os.path.exists(cand_idx):
                return cand_idx, searched
            
        return None, searched

    def load_program(self, root_filepath: str, source: Optional[str] = None) -> ProgramNode:
        """Loads root program and transitively resolves all imported modules."""
        abs_root = os.path.abspath(root_filepath) if root_filepath != "<memory>" else "<memory>"
        self.loaded_modules = {}
        self.import_stack = [abs_root]
        self.symbol_origins = {}
        self.symbol_definitions = {}
        self.collected_declarations = []
        self.module_programs = {}
        self.module_sources = {}
        self.module_graph = ModuleGraph()
        
        if source is None:
            with open(abs_root, "r", encoding="utf-8-sig") as f:
                source = f.read()

        tokens = Lexer(source, root_filepath).tokenize()
        root_ast = Parser(tokens, source, root_filepath).parse()

        self.target_name = normalize_backend_name(self.requested_target or root_ast.target)
        backend = resolve_backend(self.target_name)
        if backend is None:
            DiagnosticEmitter.emit_error(
                root_filepath, source, 1, 1,
                "E1401", f"Unknown Compilation Target: '{self.target_name}'",
                length=max(1, len(self.target_name)),
                help_msg="Run 'rove targets' to inspect canonical target names and aliases."
            )
        root_ast.target = self.target_name
        root_module_ast = ProgramNode(root_ast.target, list(root_ast.statements))
        
        root_stmts: List[ASTNode] = []

        # Process imports in root program
        for stmt in root_ast.statements:
            if isinstance(stmt, ImportNode):
                self._process_import(stmt, abs_root, source)
            else:
                root_stmts.append(stmt)

        self._register_module(abs_root, source, root_ast)
        self.module_programs[self._module_id_for_path(abs_root)] = root_module_ast
        self.module_sources[self._module_id_for_path(abs_root)] = source
                
        # Merge all collected imported declarations before root statements
        root_ast.statements = self.collected_declarations + root_stmts
        return root_ast

    def load_program_graph(
        self,
        root_filepath: str,
        source: Optional[str] = None,
    ) -> LoadedProgramGraph:
        """Load modules while retaining boundaries beside the legacy flat AST."""
        compatibility = self.load_program(root_filepath, source)
        root_path = os.path.abspath(root_filepath) if root_filepath != "<memory>" else "<memory>"
        return LoadedProgramGraph(
            self._module_id_for_path(root_path),
            self.module_graph,
            tuple(sorted(self.module_programs.items(), key=lambda item: item[0].stable_key())),
            compatibility,
            tuple(sorted(self.module_sources.items(), key=lambda item: item[0].stable_key())),
        )

    def _process_import(self, imp: ImportNode, parent_file: str, parent_source: str):
        if imp.ecosystem is not None:
            if imp.ecosystem in PENDING_FOREIGN_ECOSYSTEMS:
                DiagnosticEmitter.emit_error(
                    parent_file, parent_source, imp.line, imp.col,
                    "E1413", f"Foreign Ecosystem Integration Not Available Yet: '{imp.ecosystem}'",
                    note="The syntax is reserved, but package resolution and ABI lowering are not implemented.",
                    help_msg="Use cpp, js, or python foreign imports in this release.",
                )
                return
            supported = foreign_import_targets(imp.ecosystem)
            if not supported:
                DiagnosticEmitter.emit_error(
                    parent_file, parent_source, imp.line, imp.col,
                    "E1410", f"Unknown Foreign Ecosystem: '{imp.ecosystem}'",
                    help_msg="Use cpp, js, or python. Rust and wasm syntax is reserved for a later integration.",
                )
                return
            if self.target_name not in supported:
                DiagnosticEmitter.emit_error(
                    parent_file, parent_source, imp.line, imp.col,
                    "E1411", f"Foreign Import Unsupported on Target: '{imp.ecosystem}'",
                    note=f"'{imp.ecosystem}' imports support: {', '.join(sorted(supported))}.",
                    help_msg="Compile for the matching backend or provide a portable Rove adapter.",
                )
                return
            if imp.ecosystem == "cpp" and not imp.source:
                DiagnosticEmitter.emit_error(
                    parent_file, parent_source, imp.line, imp.col,
                    "E1412", "C++ Foreign Import Requires a Header",
                    help_msg='Use: import cpp "std::filesystem" from "<filesystem>" as fs',
                )
                return
            try:
                if self._foreign_bindings is None:
                    self._foreign_bindings = ForeignBindingRegistry.load(self.base_dir)
                imp.binding = self._foreign_bindings.resolve(imp.ecosystem, imp.path)
            except ValueError as error:
                DiagnosticEmitter.emit_error(
                    parent_file, parent_source, imp.line, imp.col,
                    "E1420", "Invalid Foreign Binding Manifest",
                    note=str(error),
                    help_msg=(
                        "Fix or remove rove.bindings.json before compiling the project "
                        "(legacy nyx.bindings.json is also recognized)."
                    ),
                )
                return
            self.collected_declarations.append(imp)
            return

        target_path, searched = self.resolve_module_path(imp.path, parent_file)
        if not target_path:
            DiagnosticEmitter.emit_error(
                parent_file, parent_source, imp.line, imp.col,
                "E1301", f"Module Not Found: '{imp.path}'",
                length=len(imp.path) + 2,
                searched=searched,
                help_msg="Verify file location and spelling."
            )
            return

        if self.track_identities:
            self.module_graph.add_import(
                self._module_id_for_path(parent_file),
                self._module_id_for_path(target_path),
                imp.symbols if imp.symbols else None,
            )

        stdlib_module = stdlib_module_from_import(imp.path)
        if stdlib_module is not None:
            contract = get_stdlib_contract(stdlib_module)
            if contract is None:
                DiagnosticEmitter.emit_error(
                    parent_file, parent_source, imp.line, imp.col,
                    "E1402", f"Missing Standard Library Target Contract: '{stdlib_module}'",
                    length=len(imp.path) + 2,
                    help_msg="Add the module to the versioned backend capability registry."
                )
                return
            if self.target_name not in contract.targets:
                supported = ", ".join(sorted(contract.targets))
                DiagnosticEmitter.emit_error(
                    parent_file, parent_source, imp.line, imp.col,
                    "E1400", f"Standard Library Module Unsupported on Target: '{imp.path}'",
                    length=len(imp.path) + 2,
                    note=f"'{stdlib_module}' supports: {supported}.",
                    help_msg=f"Choose a supported target or replace '{imp.path}' with a portable module."
                )
                return
        # Circular import check
        if target_path in self.import_stack:
            cycle = " -> ".join(self.import_stack + [target_path])
            DiagnosticEmitter.emit_error(
                parent_file, parent_source, imp.line, imp.col,
                "E1300", "Circular Module Import Detected",
                length=len(imp.path) + 2,
                help_msg=f"Break the circular dependency cycle: {cycle}"
            )
            return

        # If module already parsed and cached, we still verify symbols
        if target_path in self.loaded_modules:
            module_ast = self.loaded_modules[target_path]
        else:
            self.import_stack.append(target_path)
            with open(target_path, "r", encoding="utf-8-sig") as f:
                mod_src = f.read()
                
            tokens = Lexer(mod_src, target_path).tokenize()
            module_ast = Parser(tokens, mod_src, target_path).parse()
            
            # Transitively resolve nested imports first (Topological Ordering)
            for s in module_ast.statements:
                if isinstance(s, ImportNode):
                    self._process_import(s, target_path, mod_src)

            self._register_module(target_path, mod_src, module_ast)
            self.module_programs[self._module_id_for_path(target_path)] = module_ast
            self.module_sources[self._module_id_for_path(target_path)] = mod_src
                    
            self.loaded_modules[target_path] = module_ast
            self.import_stack.pop()

        # Collect exported declarations and native directives from this module
        for s in module_ast.statements:
            if isinstance(s, (NativeIncludeNode, NativeLinkNode, NativeRawNode)):
                s._origin_module = target_path
                s._origin_import = imp.path
                self.collected_declarations.append(s)
                continue

            if isinstance(s, ImplBlockNode):
                if imp.symbols and s.target_type not in imp.symbols:
                    continue
                self.collected_declarations.append(s)
                continue

            if isinstance(s, (FunctionDefNode, StructDefNode, TraitDefNode, TypeAliasNode, EnumDefNode, ExternFnDeclNode, VarDeclNode)):
                sym_name = getattr(s, "name", None)
                if not sym_name:
                    continue

                # Selective import filter: import { abs_val } from "std/math"
                if imp.symbols and sym_name not in imp.symbols:
                    continue

                origin = getattr(s, "_origin_module", target_path)
                s._origin_module = origin
                definition_id = self.module_graph.resolve_export(
                    self._module_id_for_path(origin), sym_name
                ) if self.track_identities else None

                # Ambiguous symbol collision check
                existing_definition = self.symbol_definitions.get(sym_name)
                is_distinct_definition = (
                    definition_id is not None
                    and existing_definition is not None
                    and definition_id != existing_definition
                )
                if sym_name in self.symbol_origins and (
                    is_distinct_definition
                    or (definition_id is None and self.symbol_origins[sym_name] != origin)
                ):
                    prev_origin = self.symbol_origins[sym_name]
                    DiagnosticEmitter.emit_error(
                        parent_file, parent_source, imp.line, imp.col,
                        "E1302", f"Ambiguous Symbol Collision: '{sym_name}'",
                        length=len(imp.path) + 2,
                        note=f"'{sym_name}' is exported by both '{os.path.basename(prev_origin)}' and '{os.path.basename(origin)}'.",
                        help_msg="Use selective import: import { specific_symbol } from \"...\" to resolve ambiguity."
                    )
                elif sym_name not in self.symbol_origins:
                    self.symbol_origins[sym_name] = origin
                    if definition_id is not None:
                        self.symbol_definitions[sym_name] = definition_id
                    self.collected_declarations.append(s)

    def _module_id_for_path(self, filepath: str) -> ModuleId:
        if filepath == "<memory>":
            return ModuleId("memory", "main")
        resolved = os.path.realpath(filepath)
        roots = [("std", os.path.realpath(self.stdlib_dir))]
        roots.extend(
            (name, os.path.realpath(root)) for name, root in self.package_roots.items()
        )
        roots.append(("root", os.path.realpath(self.base_dir)))
        for package, root in roots:
            try:
                if os.path.commonpath((resolved, root)) != root:
                    continue
            except ValueError:
                continue
            relative = os.path.relpath(resolved, root).replace("\\", "/")
            if relative.endswith(".rove"):
                relative = relative[:-4]
            return ModuleId(package, relative)
        return ModuleId("external", os.path.basename(resolved).removesuffix(".rove"))

    def _register_module(self, filepath: str, source: str, program: ProgramNode) -> None:
        if not self.track_identities:
            return
        self.module_graph.register_module(
            self._module_id_for_path(filepath),
            filepath,
            source,
            (
                (self._declaration_name(statement), signature)
                for statement in program.statements
                if (signature := self._public_signature(statement)) is not None
            ),
        )

    @staticmethod
    def _declaration_name(value: ASTNode) -> str:
        return str(getattr(value, "name", type(value).__name__))

    @staticmethod
    def _type_signature(value: object) -> str:
        return str(value) if value is not None else "any"

    def _function_signature(self, value: FunctionDefNode) -> str:
        params = ",".join(
            self._type_signature(param.type_annot) for param in value.params
        )
        generics = ",".join(value.generic_params)
        return (
            f"fn:{value.name}<{generics}>({params})->"
            f"{self._type_signature(value.return_type)}:async={int(value.is_async)}"
        )

    def _public_signature(self, value: ASTNode) -> Optional[str]:
        if isinstance(value, FunctionDefNode):
            return self._function_signature(value)
        if isinstance(value, StructDefNode):
            fields = ",".join(
                f"{field.name}:{self._type_signature(field.type_annot)}"
                for field in value.fields
            )
            return f"struct:{value.name}<{','.join(value.generic_params)}>({fields})"
        if isinstance(value, TraitDefNode):
            methods = ";".join(self._function_signature(method) for method in value.methods)
            return f"trait:{value.name}({methods})"
        if isinstance(value, TypeAliasNode):
            return f"type:{value.name}={self._type_signature(value.actual_type)}"
        if isinstance(value, EnumDefNode):
            members = ",".join(
                f"{member.name}({','.join(self._type_signature(item) for item in member.payload_types)})"
                for member in value.members
            )
            return f"enum:{value.name}<{','.join(value.generic_params)}>({members})"
        if isinstance(value, ExternFnDeclNode):
            params = ",".join(
                self._type_signature(param.type_annot) for param in value.params
            )
            return (
                f"extern:{value.abi}:{value.name}({params})->"
                f"{self._type_signature(value.return_type)}:varargs={int(value.is_varargs)}"
            )
        if isinstance(value, VarDeclNode):
            return f"global:{value.name}:{self._type_signature(value.type_annot)}"
        return None
