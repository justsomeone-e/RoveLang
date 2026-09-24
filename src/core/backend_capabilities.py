"""Canonical backend and standard-library capability contracts.

Every compiler entry point consumes this registry.  A target is therefore a
versioned contract instead of a collection of duplicated CLI aliases and
implicit code-generator behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple


CAPABILITY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BackendSpec:
    name: str
    display_name: str
    family: str
    artifact: str
    maturity: str
    aliases: Tuple[str, ...]
    features: FrozenSet[str]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "family": self.family,
            "artifact": self.artifact,
            "maturity": self.maturity,
            "aliases": list(self.aliases),
            "features": sorted(self.features),
            "stdlib_modules": sorted(stdlib_modules_for_target(self.name)),
        }


@dataclass(frozen=True)
class StdlibContract:
    module: str
    targets: FrozenSet[str]
    maturity: str = "stable"
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "targets": sorted(self.targets),
            "maturity": self.maturity,
            "note": self.note,
        }


CORE_FEATURES = frozenset({
    "arrays", "control_flow", "functions", "optionals", "pattern_match",
    "strings", "structs", "unicode",
})
CONCURRENCY_FEATURES = frozenset({"channels", "spawn"})
NATIVE_FEATURES = CORE_FEATURES | frozenset({
    "filesystem", "native_ffi", "native_linking", "sockets", "threads",
    "unsafe_memory",
}) | CONCURRENCY_FEATURES
DYNAMIC_FEATURES = CORE_FEATURES | frozenset({
    "encoding", "filesystem", "hash", "json_lite", "math", "time",
}) | CONCURRENCY_FEATURES
V4_NUMERIC_FEATURES = frozenset({
    "canonical_scalar_text", "float64_ieee", "int64_wrap",
})
HIR_V1_FEATURES = frozenset({"typed_hir_v1"})
BACKENDS: Dict[str, BackendSpec] = {
    "cpp": BackendSpec(
        "cpp", "C++20 Native", "native", "executable/library", "stable",
        ("c++", "native", "desktop"),
        NATIVE_FEATURES | V4_NUMERIC_FEATURES | HIR_V1_FEATURES | frozenset({"async_tasks", "collection_combinators", "exceptions", "iterator_yield", "payload_enums", "result_propagation"}),
    ),
    "asm": BackendSpec(
        "asm", "x86_64 Assembly", "native", "assembly", "beta",
        ("assembly",), NATIVE_FEATURES,
    ),
    "js": BackendSpec(
        "js", "Node.js ES2022", "hosted", "javascript", "stable",
        ("node", "nodejs"),
        DYNAMIC_FEATURES | V4_NUMERIC_FEATURES | HIR_V1_FEATURES | frozenset({"async_tasks", "collection_combinators", "exceptions", "iterator_yield", "payload_enums", "result_propagation"}),
    ),
    "python": BackendSpec(
        "python", "Python 3", "hosted", "python", "stable",
        ("py", "python3"),
        DYNAMIC_FEATURES | V4_NUMERIC_FEATURES | HIR_V1_FEATURES | frozenset({"async_tasks", "collection_combinators", "exceptions", "iterator_yield", "payload_enums", "result_propagation"}),
    ),
    "rust": BackendSpec(
        "rust", "Rust 2021", "native", "rust", "beta",
        ("rs",), CORE_FEATURES | HIR_V1_FEATURES | frozenset({"result_propagation", "unsafe_memory"}),
    ),
    "react": BackendSpec(
        "react", "React 19 TSX", "web", "tsx", "beta",
        ("tsx",), frozenset({"components", "react19", "tsx", "unicode"}),
    ),
    "wasm": BackendSpec(
        "wasm", "WebAssembly", "web", "wat/wasm", "beta",
        ("wat", "webassembly"), HIR_V1_FEATURES | frozenset({
            "array_mutation", "control_flow", "functions", "host_imports_v1", "numeric",
            "numeric_array_abi", "string_abi", "string_indexing", "unicode", "wasi_args",
            "wasi_environ", "wasi_filesystem", "wasi_preview1", "wasm32", "web_dom",
        }),
    ),
    "c": BackendSpec(
        "c", "C17 Native (Scalar Experimental)", "native", "c", "experimental",
        ("c17",),
        HIR_V1_FEATURES | V4_NUMERIC_FEATURES | frozenset({"control_flow", "functions", "scalar_c17"}),
    ),
    "llvm": BackendSpec(
        "llvm", "LLVM IR (Scalar + Aggregate Experimental)", "native", "ll", "experimental",
        ("ll",),
        HIR_V1_FEATURES | V4_NUMERIC_FEATURES | frozenset({"array_iteration", "control_flow", "functions", "scalar_arrays", "scalar_llvm", "scalar_structs"}),
    ),
}


_ALIASES: Dict[str, str] = {name: name for name in BACKENDS}
for _name, _backend in BACKENDS.items():
    for _alias in _backend.aliases:
        _ALIASES[_alias] = _name


CPP_HOSTS = frozenset({"cpp", "asm"})
PARITY_HOSTS = frozenset({"cpp", "asm", "js", "python"})
DYNAMIC_HOSTS = frozenset({"cpp", "asm", "js", "python", "rust"})
MEMORY_TARGETS = CPP_HOSTS

FOREIGN_ECOSYSTEM_TARGETS: Dict[str, FrozenSet[str]] = {
    "cpp": frozenset({"cpp"}),
    "js": frozenset({"js"}),
    "python": frozenset({"python"}),
}

PENDING_FOREIGN_ECOSYSTEMS = frozenset({"rust", "wasm"})


def foreign_import_targets(ecosystem: str) -> FrozenSet[str]:
    return FOREIGN_ECOSYSTEM_TARGETS.get(ecosystem.strip().lower(), frozenset())


STDLIB_CONTRACTS: Dict[str, StdlibContract] = {
    "encoding": StdlibContract("encoding", PARITY_HOSTS),
    "fs": StdlibContract("fs", PARITY_HOSTS),
    "hash": StdlibContract("hash", PARITY_HOSTS),
    "http": StdlibContract(
        "http", frozenset({"cpp"}), "experimental",
        "Hosted HTTP through a shell-free curl subprocess with bounded requests and responses.",
    ),
    "json_lite": StdlibContract(
        "json_lite", PARITY_HOSTS, "stable",
        "Flat top-level string/integer field extraction only; not a general JSON parser.",
    ),
    "json": StdlibContract("json", PARITY_HOSTS, "deprecated", "Use std/json_lite."),
    "math": StdlibContract("math", PARITY_HOSTS),
    "time": StdlibContract("time", PARITY_HOSTS),
    "path": StdlibContract("path", PARITY_HOSTS),
    "str": StdlibContract("str", DYNAMIC_HOSTS),
    "io": StdlibContract("io", frozenset({"cpp", "asm", "python"})),
    "env": StdlibContract("env", CPP_HOSTS),
    "net": StdlibContract("net", CPP_HOSTS),
    "os": StdlibContract("os", CPP_HOSTS),
    "platform": StdlibContract("platform", CPP_HOSTS),
    "process": StdlibContract("process", PARITY_HOSTS),
    "system": StdlibContract(
        "system", CPP_HOSTS, "experimental",
        "Hosted OS inspection through the native platform ABI.",
    ),
    "terminal": StdlibContract(
        "terminal", CPP_HOSTS, "experimental",
        "Terminal, cursor control, screen clearing, and keyboard input.",
    ),
    "thread": StdlibContract("thread", CPP_HOSTS),
    "memory": StdlibContract("memory", MEMORY_TARGETS),
    "web": StdlibContract(
        "web", frozenset({"wasm"}), "experimental",
        "Typed browser host handles and DOM/canvas operations through nyx_host_v1.",
    ),
}


def normalize_backend_name(name: Optional[str], default: str = "cpp") -> str:
    clean = (name or default).strip().lower()
    return _ALIASES.get(clean, clean)


def resolve_backend(name: Optional[str]) -> Optional[BackendSpec]:
    return BACKENDS.get(normalize_backend_name(name))


def get_stdlib_contract(module: str) -> Optional[StdlibContract]:
    clean = module.replace("\\", "/").strip("/")
    if clean.endswith(".rove"):
        clean = clean[:-4]
    return STDLIB_CONTRACTS.get(clean)


def stdlib_modules_for_target(target: str) -> FrozenSet[str]:
    canonical = normalize_backend_name(target)
    return frozenset(
        name for name, contract in STDLIB_CONTRACTS.items()
        if canonical in contract.targets
    )


def stdlib_module_from_import(import_path: str) -> Optional[str]:
    clean = import_path.replace("::", "/").replace("\\", "/").strip("/")
    parts = clean.split("/", 1)
    if len(parts) != 2 or parts[0] not in ("std", "native"):
        return None
    module = parts[1]
    if module.endswith(".rove"):
        module = module[:-4]
    return module


def capability_manifest() -> dict:
    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "backends": [BACKENDS[name].to_dict() for name in sorted(BACKENDS)],
        "stdlib": [STDLIB_CONTRACTS[name].to_dict() for name in sorted(STDLIB_CONTRACTS)],
    }
