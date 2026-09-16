"""Stable internal compiler identities and the non-flattened module graph."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Iterable, Mapping
from urllib.parse import quote


def _digest(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _component(value: str) -> str:
    return quote(value.replace("\\", "/"), safe="/._-")


@dataclass(frozen=True, slots=True)
class SourceId:
    digest: str

    @classmethod
    def from_text(cls, source: str) -> "SourceId":
        return cls(hashlib.sha256(source.encode("utf-8")).hexdigest())

    def stable_key(self) -> str:
        return f"source:sha256:{self.digest}"


@dataclass(frozen=True, slots=True)
class ModuleId:
    package: str
    path: str

    def __post_init__(self) -> None:
        normalized = self.path.replace("\\", "/").strip("/") or "<root>"
        object.__setattr__(self, "path", normalized)

    def stable_key(self) -> str:
        return f"module:{_component(self.package)}:{_component(self.path)}"


@dataclass(frozen=True, slots=True)
class NodeId:
    source: SourceId
    ordinal: int

    def stable_key(self) -> str:
        return f"node:{self.source.digest}:{self.ordinal}"


@dataclass(frozen=True, slots=True, eq=False)
class DefId:
    module: ModuleId
    local_index: int
    path_hash: str = ""

    @classmethod
    def from_path(
        cls,
        module: ModuleId,
        local_index: int,
        path: str,
    ) -> "DefId":
        """Build a stable definition identity independent of declaration order."""
        return cls(
            module,
            local_index,
            _digest({"module": module.stable_key(), "definition": path}),
        )

    def _identity(self) -> tuple[ModuleId, str | int]:
        return (self.module, self.path_hash or self.local_index)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DefId) and self._identity() == other._identity()

    def __hash__(self) -> int:
        return hash(self._identity())

    def stable_key(self) -> str:
        if self.path_hash:
            return f"def:{self.module.stable_key()}:path:{self.path_hash}"
        return f"def:{self.module.stable_key()}:{self.local_index}"


@dataclass(frozen=True, slots=True)
class SymbolId:
    owner: DefId
    local_index: int | None = None

    def stable_key(self) -> str:
        suffix = "definition" if self.local_index is None else f"local:{self.local_index}"
        return f"symbol:{self.owner.stable_key()}:{suffix}"


@dataclass(frozen=True, slots=True)
class TypeId:
    digest: str

    def stable_key(self) -> str:
        return f"type:sha256:{self.digest}"


@dataclass(frozen=True, slots=True)
class InstanceId:
    definition: DefId
    arguments: tuple[TypeId, ...] = ()
    substitutions: tuple[tuple[str, TypeId], ...] = ()

    def stable_key(self) -> str:
        payload = {
            "definition": self.definition.stable_key(),
            "arguments": [item.stable_key() for item in self.arguments],
            "substitutions": [
                [name, value.stable_key()] for name, value in self.substitutions
            ],
        }
        return f"instance:sha256:{_digest(payload)}"


class TypeInterner:
    def __init__(self) -> None:
        self._types: dict[str, TypeId] = {}

    def intern(self, value: object) -> TypeId:
        canonical = value.canonical() if hasattr(value, "canonical") else str(value)
        return self._types.setdefault(canonical, TypeId(_digest({"type": canonical})))


@dataclass(frozen=True, slots=True)
class ModuleRecord:
    module_id: ModuleId
    source_id: SourceId
    filepath: str
    definitions: tuple[DefId, ...]
    exports: tuple[tuple[str, DefId], ...]
    public_signatures: tuple[str, ...]
    interface_fingerprint: str
    implementation_fingerprint: str
    imports: tuple[ModuleId, ...] = ()


class AmbiguousDefinitionError(LookupError):
    def __init__(self, module_id: ModuleId, name: str, candidates: tuple[DefId, ...]):
        self.module_id = module_id
        self.name = name
        self.candidates = candidates
        super().__init__(
            f"Ambiguous definition '{name}' in {module_id.stable_key()}: "
            + ", ".join(item.stable_key() for item in candidates)
        )


class ModuleGraph:
    """Retains module boundaries while legacy compilation may still flatten ASTs."""

    def __init__(self) -> None:
        self._records: dict[ModuleId, ModuleRecord] = {}
        self._imports: dict[ModuleId, set[ModuleId]] = {}
        self._import_filters: dict[tuple[ModuleId, ModuleId], frozenset[str] | None] = {}
        self.types = TypeInterner()

    def register_module(
        self,
        module_id: ModuleId,
        filepath: str,
        source: str,
        public_items: Iterable[tuple[str, str]],
    ) -> ModuleRecord:
        items = tuple(sorted(public_items, key=lambda item: (item[0], item[1])))
        signatures = tuple(signature for _name, signature in items)
        source_id = SourceId.from_text(source)
        definitions = tuple(
            DefId.from_path(module_id, index, name)
            for index, (name, _signature) in enumerate(items)
        )
        exports = tuple(
            (name, definitions[index]) for index, (name, _signature) in enumerate(items)
        )
        record = ModuleRecord(
            module_id,
            source_id,
            filepath,
            definitions,
            exports,
            signatures,
            _digest({"module": module_id.stable_key(), "interface": signatures}),
            source_id.digest,
        )
        self._records[module_id] = record
        return self.record(module_id)

    def add_import(
        self,
        importer: ModuleId,
        imported: ModuleId,
        symbols: Iterable[str] | None = None,
    ) -> None:
        self._imports.setdefault(importer, set()).add(imported)
        requested = None if symbols is None else frozenset(symbols)
        key = (importer, imported)
        previous = self._import_filters.get(key)
        if key not in self._import_filters:
            self._import_filters[key] = requested
        elif previous is None or requested is None:
            self._import_filters[key] = None
        else:
            self._import_filters[key] = previous | requested

    def record(self, module_id: ModuleId) -> ModuleRecord:
        record = self._records[module_id]
        imports = tuple(sorted(self._imports.get(module_id, ()), key=ModuleId.stable_key))
        return replace(record, imports=imports)

    @property
    def modules(self) -> Mapping[ModuleId, ModuleRecord]:
        return {module_id: self.record(module_id) for module_id in self._records}

    def direct_imports(self, module_id: ModuleId) -> tuple[ModuleId, ...]:
        """Return only imports named by this module, never transitive imports."""
        return tuple(sorted(self._imports.get(module_id, ()), key=ModuleId.stable_key))

    def imported_symbols(
        self,
        importer: ModuleId,
        imported: ModuleId,
    ) -> frozenset[str] | None:
        """Return a selective-import filter, or ``None`` for all exports."""
        return self._import_filters.get((importer, imported))

    def node_id(self, module_id: ModuleId, ordinal: int) -> NodeId:
        return NodeId(self._records[module_id].source_id, ordinal)

    def resolve_export(self, module_id: ModuleId, name: str) -> DefId | None:
        record = self._records.get(module_id)
        if record is None:
            return None
        return next(
            (definition for exported_name, definition in record.exports if exported_name == name),
            None,
        )

    def visible_definitions(self, module_id: ModuleId, name: str) -> tuple[DefId, ...]:
        local = self.resolve_export(module_id, name)
        if local is not None:
            return (local,)
        candidates: set[DefId] = set()
        for imported in self._imports.get(module_id, ()):
            allowed = self._import_filters.get((module_id, imported))
            if allowed is not None and name not in allowed:
                continue
            definition = self.resolve_export(imported, name)
            if definition is not None:
                candidates.add(definition)
        return tuple(sorted(candidates, key=DefId.stable_key))

    def resolve_visible(self, module_id: ModuleId, name: str) -> DefId | None:
        candidates = self.visible_definitions(module_id, name)
        if len(candidates) > 1:
            raise AmbiguousDefinitionError(module_id, name, candidates)
        return candidates[0] if candidates else None

    def dependants(self, module_id: ModuleId) -> tuple[ModuleId, ...]:
        reverse: dict[ModuleId, set[ModuleId]] = {}
        for importer, imports in self._imports.items():
            for imported in imports:
                reverse.setdefault(imported, set()).add(importer)
        found: set[ModuleId] = set()
        pending = list(reverse.get(module_id, ()))
        while pending:
            dependant = pending.pop()
            if dependant in found:
                continue
            found.add(dependant)
            pending.extend(reverse.get(dependant, ()))
        return tuple(sorted(found, key=ModuleId.stable_key))

    def initialization_order(self, root: ModuleId) -> tuple[ModuleId, ...]:
        """Return a deterministic dependency-first module initialization order."""
        ordered: list[ModuleId] = []
        visiting: list[ModuleId] = []
        visited: set[ModuleId] = set()

        def visit(module_id: ModuleId) -> None:
            if module_id in visited:
                return
            if module_id in visiting:
                start = visiting.index(module_id)
                cycle = visiting[start:] + [module_id]
                rendered = " -> ".join(item.stable_key() for item in cycle)
                raise ValueError(f"Module initialization cycle: {rendered}")
            if module_id not in self._records:
                raise KeyError(module_id)
            visiting.append(module_id)
            for dependency in sorted(self._imports.get(module_id, ()), key=ModuleId.stable_key):
                visit(dependency)
            visiting.pop()
            visited.add(module_id)
            ordered.append(module_id)

        visit(root)
        return tuple(ordered)

    def invalidated_since(self, previous: "ModuleGraph") -> tuple[ModuleId, ...]:
        """Return minimal module invalidation from implementation/interface drift."""
        invalidated: set[ModuleId] = set()
        module_ids = set(self._records) | set(previous._records)
        for module_id in module_ids:
            current = self._records.get(module_id)
            old = previous._records.get(module_id)
            if current is not None and old is not None:
                if current.implementation_fingerprint == old.implementation_fingerprint:
                    continue
                invalidated.add(module_id)
                if current.interface_fingerprint == old.interface_fingerprint:
                    continue
            else:
                invalidated.add(module_id)
            invalidated.update(self.dependants(module_id))
            invalidated.update(previous.dependants(module_id))
        return tuple(sorted(invalidated, key=ModuleId.stable_key))

    def instance_id(
        self,
        definition: DefId,
        arguments: Iterable[object] = (),
        substitutions: Mapping[str, object] | None = None,
    ) -> InstanceId:
        argument_ids = tuple(self.types.intern(item) for item in arguments)
        substitution_ids = tuple(sorted(
            ((name, self.types.intern(value)) for name, value in (substitutions or {}).items()),
            key=lambda item: item[0],
        ))
        return InstanceId(definition, argument_ids, substitution_ids)
