import hashlib
import json
import os
import re
import sys
from typing import Dict, List, Any, Optional, Tuple, Set


def _canonical_dependency_path(value: Any) -> str:
    """Serialize local dependency paths independently of the host OS."""
    return str(value).replace("\\", "/")


class RoveManifest:
    def __init__(self, filepath: Optional[str] = None):
        self.filepath = filepath
        self.package: Dict[str, Any] = {
            "name": "rove_app",
            "version": "0.1.0",
            "edition": "2026",
            "target": "cpp",
            "entry": "src/main.rove",
            "author": "",
            "license": "MIT",
            "description": ""
        }
        self.dependencies: Dict[str, Any] = {}
        self.native: Dict[str, Any] = {
            "includes": [],
            "links": [],
            "cflags": [],
            "ldflags": []
        }
        self.build: Dict[str, Any] = {
            "opt_level": 2,
            "output_type": "exe",
            "output_name": ""
        }
        if filepath and os.path.exists(filepath):
            self.load(filepath)

    def load(self, filepath: str):
        self.filepath = filepath
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self._parse(lines)

    def _parse(self, lines: List[str]):
        current_section = "package"
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip().lower()
                continue

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                parsed_val = self._parse_val(val)

                if current_section == "package":
                    self.package[key] = parsed_val
                elif current_section == "dependencies":
                    if isinstance(parsed_val, dict) and "path" in parsed_val:
                        parsed_val["path"] = _canonical_dependency_path(parsed_val["path"])
                    self.dependencies[key] = parsed_val
                elif current_section == "native":
                    self.native[key] = parsed_val
                elif current_section == "build":
                    self.build[key] = parsed_val

    def _parse_val(self, val: str) -> Any:
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        if val.lower() == "true":
            return True
        if val.lower() == "false":
            return False
        if val.startswith("[") and val.endswith("]"):
            items = val[1:-1].split(",")
            res = []
            for item in items:
                item = item.strip()
                if item:
                    res.append(self._parse_val(item))
            return res
        if val.startswith("{") and val.endswith("}"):
            res_dict = {}
            pairs = val[1:-1].split(",")
            for pair in pairs:
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    res_dict[k.strip()] = self._parse_val(v.strip())
            return res_dict
        try:
            if "." in val:
                return float(val)
            return int(val)
        except ValueError:
            return val

    def save(self, filepath: Optional[str] = None):
        target = filepath or self.filepath or "rove.toml"
        p_name = self.package.get("name", "rove_app")
        p_ver = self.package.get("version", "0.1.0")
        p_ed = self.package.get("edition", "2026")
        p_targ = self.package.get("target", "cpp")
        p_entry = self.package.get("entry", "src/main.rove")

        lines = [
            "[package]",
            f'name = "{p_name}"',
            f'version = "{p_ver}"',
            f'edition = "{p_ed}"',
            f'target = "{p_targ}"',
            f'entry = "{p_entry}"'
        ]
        if self.package.get("description"):
            lines.append(f'description = "{self.package["description"]}"')
        if self.package.get("license"):
            lines.append(f'license = "{self.package["license"]}"')

        lines.append("\n[dependencies]")
        for k, v in sorted(self.dependencies.items()):
            if isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, dict):
                ps = []
                for dk, dv in sorted(v.items()):
                    if dk == "path":
                        dv = _canonical_dependency_path(dv)
                    if isinstance(dv, str):
                        ps.append(f'{dk} = "{dv}"')
                    else:
                        ps.append(f'{dk} = {dv}')
                lines.append(f'{k} = {{ {", ".join(ps)} }}')

        lines.append("\n[native]")
        incs = ", ".join(f'"{i}"' for i in self.native.get("includes", []))
        links = ", ".join(f'"{l}"' for l in self.native.get("links", []))
        lines.append(f'includes = [{incs}]')
        lines.append(f'links = [{links}]')

        lines.append("\n[build]")
        lines.append(f'opt_level = {self.build.get("opt_level", 2)}')
        lines.append(f'output_type = "{self.build.get("output_type", "exe")}"')
        if self.build.get("output_name"):
            lines.append(f'output_name = "{self.build["output_name"]}"')

        with open(target, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


class PackageError(Exception):
    pass


class SemVerParseError(PackageError):
    pass


class DependencyCycleError(PackageError):
    pass


class VersionConflictError(PackageError):
    pass


class ChecksumMismatchError(PackageError):
    pass


class OfflineCacheMissError(PackageError):
    pass


class SemVer:
    _REGEX = re.compile(
        r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
        r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
    )

    def __init__(self, major: int, minor: int, patch: int, prerelease: str = ""):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease

    @classmethod
    def parse(cls, text: str) -> "SemVer":
        cleaned = text.strip()
        match = cls._REGEX.match(cleaned)
        if not match:
            raise SemVerParseError(f"Invalid SemVer string: '{text}'")
        groups = match.groupdict()
        return cls(
            int(groups["major"]),
            int(groups["minor"]),
            int(groups["patch"]),
            groups["prerelease"] or ""
        )

    def tuple_key(self) -> Tuple[int, int, int, int, str]:
        has_prerelease = 0 if self.prerelease else 1
        return (self.major, self.minor, self.patch, has_prerelease, self.prerelease)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return False
        return self.tuple_key() == other.tuple_key()

    def __lt__(self, other: "SemVer") -> bool:
        return self.tuple_key() < other.tuple_key()

    def __le__(self, other: "SemVer") -> bool:
        return self == other or self < other

    def __gt__(self, other: "SemVer") -> bool:
        return not (self <= other)

    def __ge__(self, other: "SemVer") -> bool:
        return not (self < other)

    def __str__(self) -> str:
        res = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            res += f"-{self.prerelease}"
        return res

    def __repr__(self) -> str:
        return f"SemVer({self})"


class SemVerRange:
    """Matches SemVer versions against range expressions."""
    def __init__(self, raw: str):
        self.raw = raw.strip()
        self.predicates: List[Tuple[str, SemVer]] = []
        self._parse()

    def _parse(self) -> None:
        expr = self.raw
        if not expr or expr == "*":
            return

        tokens = re.findall(r"(\^|~|>=|<=|>|<|==|=)?\s*([0-9A-Za-z.-]+|\*)", expr)
        if not tokens:
            raise SemVerParseError(f"Invalid SemVer range: '{self.raw}'")

        for op, ver_str in tokens:
            op = op or "=="
            if ver_str == "*":
                continue
            base = SemVer.parse(ver_str)
            if op in ("=", "=="):
                self.predicates.append(("==", base))
            elif op == "^":
                self.predicates.append((">=", base))
                if base.major > 0:
                    upper = SemVer(base.major + 1, 0, 0)
                elif base.minor > 0:
                    upper = SemVer(0, base.minor + 1, 0)
                else:
                    upper = SemVer(0, 0, base.patch + 1)
                self.predicates.append(("<", upper))
            elif op == "~":
                self.predicates.append((">=", base))
                self.predicates.append(("<", SemVer(base.major, base.minor + 1, 0)))
            elif op in (">=", "<=", ">", "<"):
                self.predicates.append((op, base))

    def matches(self, version: SemVer) -> bool:
        for op, target in self.predicates:
            if op == ">=" and not (version >= target):
                return False
            if op == "<=" and not (version <= target):
                return False
            if op == ">" and not (version > target):
                return False
            if op == "<" and not (version < target):
                return False
            if op == "==" and not (version == target):
                return False
        return True

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"SemVerRange({self.raw!r})"


class PackageRegistry:
    """Simulates or interfaces with remote registry and local offline cache."""
    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.expanduser("~/.rove/cache/packages")
        self._mock_remote: Dict[str, Dict[str, Any]] = {}

    def publish_mock_package(
        self,
        name: str,
        version: str,
        dependencies: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, str]] = None,
    ) -> str:
        """Helper for tests and simulation."""
        files = files or {"src/lib.rove": f"// package {name} v{version}\n"}
        dependencies = dependencies or {}
        digest = hashlib.sha256()
        for fname in sorted(files.keys()):
            digest.update(fname.encode("utf-8"))
            digest.update(b"\0")
            digest.update(files[fname].encode("utf-8"))
            digest.update(b"\0")
        checksum = "sha256:" + digest.hexdigest()

        pkg_info = self._mock_remote.setdefault(name, {"name": name, "versions": {}})
        pkg_info["versions"][version] = {
            "version": version,
            "checksum": checksum,
            "dependencies": dependencies,
            "files": files,
        }
        return checksum

    def get_package_versions(self, name: str, offline: bool = False) -> List[SemVer]:
        versions: List[SemVer] = []
        if offline:
            pkg_cache = os.path.join(self.cache_dir, name)
            if os.path.isdir(pkg_cache):
                for ver_name in os.listdir(pkg_cache):
                    try:
                        versions.append(SemVer.parse(ver_name))
                    except SemVerParseError:
                        pass
            if not versions:
                raise OfflineCacheMissError(
                    f"Package '{name}' not found in offline cache ({self.cache_dir})"
                )
            return sorted(versions)

        if name not in self._mock_remote:
            raise PackageError(f"Package '{name}' not found in registry")
        for ver_str in self._mock_remote[name]["versions"].keys():
            versions.append(SemVer.parse(ver_str))
        return sorted(versions)

    def fetch_package(self, name: str, version: str, offline: bool = False) -> Dict[str, Any]:
        cache_entry = os.path.join(self.cache_dir, name, version)
        cache_meta = os.path.join(cache_entry, "metadata.json")

        if os.path.isfile(cache_meta):
            with open(cache_meta, "r", encoding="utf-8") as f:
                cached = json.load(f)
            calc_digest = hashlib.sha256()
            for fname in sorted(cached.get("files", {}).keys()):
                calc_digest.update(fname.encode("utf-8"))
                calc_digest.update(b"\0")
                calc_digest.update(cached["files"][fname].encode("utf-8"))
                calc_digest.update(b"\0")
            calc_checksum = "sha256:" + calc_digest.hexdigest()
            if calc_checksum != cached["checksum"]:
                raise ChecksumMismatchError(
                    f"Checksum mismatch for cached '{name}@{version}': expected {cached['checksum']}, got {calc_checksum}"
                )
            return cached

        if offline:
            raise OfflineCacheMissError(f"Package '{name}@{version}' not found in offline cache")

        if name not in self._mock_remote or version not in self._mock_remote[name]["versions"]:
            raise PackageError(f"Version '{version}' of '{name}' not found in registry")

        data = self._mock_remote[name]["versions"][version]
        calc_digest = hashlib.sha256()
        for fname in sorted(data.get("files", {}).keys()):
            calc_digest.update(fname.encode("utf-8"))
            calc_digest.update(b"\0")
            calc_digest.update(data["files"][fname].encode("utf-8"))
            calc_digest.update(b"\0")
        calc_checksum = "sha256:" + calc_digest.hexdigest()
        if calc_checksum != data["checksum"]:
            raise ChecksumMismatchError(
                f"Checksum mismatch for '{name}@{version}': expected {data['checksum']}, got {calc_checksum}"
            )

        os.makedirs(cache_entry, exist_ok=True)
        with open(cache_meta, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return data


class DependencyResolver:
    """Deterministic SemVer constraint solver with cycle and conflict detection."""
    def __init__(self, registry: PackageRegistry, offline: bool = False):
        self.registry = registry
        self.offline = offline

    def resolve(self, root_dependencies: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        constraints: Dict[str, List[Tuple[str, SemVerRange]]] = {}
        for dep, range_str in root_dependencies.items():
            constraints.setdefault(dep, []).append(("root", SemVerRange(range_str)))

        resolved: Dict[str, Dict[str, Any]] = {}
        queue = sorted(root_dependencies.keys())

        def check_cycles(pkg: str, active_path: List[str], current_deps: Dict[str, Dict[str, Any]]) -> None:
            if pkg in active_path:
                cycle_str = " -> ".join(active_path + [pkg])
                raise DependencyCycleError(f"Dependency cycle detected: {cycle_str}")
            if pkg not in current_deps:
                return
            for subdep in sorted(current_deps[pkg].get("dependencies", {}).keys()):
                check_cycles(subdep, active_path + [pkg], current_deps)

        resolved_versions: Dict[str, SemVer] = {}

        while queue:
            pkg = queue.pop(0)
            avail_versions = self.registry.get_package_versions(pkg, offline=self.offline)
            pkg_constraints = constraints[pkg]
            matching = [
                v for v in avail_versions
                if all(c[1].matches(v) for c in pkg_constraints)
            ]
            if not matching:
                req_strs = [f"{c[0]} requires {c[1]}" for c in pkg_constraints]
                raise VersionConflictError(
                    f"Version conflict for package '{pkg}': no version satisfies constraints ({', '.join(req_strs)})"
                )

            best_version = matching[-1]
            if pkg in resolved_versions and resolved_versions[pkg] == best_version:
                continue

            resolved_versions[pkg] = best_version
            pkg_data = self.registry.fetch_package(pkg, str(best_version), offline=self.offline)
            resolved[pkg] = {
                "version": str(best_version),
                "checksum": pkg_data["checksum"],
                "dependencies": pkg_data.get("dependencies", {}),
            }

            for sub_name, sub_range_str in sorted(pkg_data.get("dependencies", {}).items()):
                constraints.setdefault(sub_name, []).append((f"{pkg}@{best_version}", SemVerRange(sub_range_str)))
                if sub_name not in queue:
                    queue.append(sub_name)

        for root_pkg in sorted(root_dependencies.keys()):
            check_cycles(root_pkg, [], resolved)

        return resolved


class RoveLock:
    @staticmethod
    def _hash_package(root: str) -> str:
        digest = hashlib.sha256()
        excluded = {".git", "build", "dist", "target", "__pycache__", "node_modules"}
        for current, directories, filenames in os.walk(root):
            directories[:] = sorted(item for item in directories if item not in excluded)
            for filename in sorted(filenames):
                if filename not in {"rove.toml", "nyx.toml"} and not filename.endswith((".rove", ".nyx")):
                    continue
                path = os.path.join(current, filename)
                relative = os.path.relpath(path, root).replace("\\", "/")
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                with open(path, "rb") as handle:
                    digest.update(handle.read())
                digest.update(b"\0")
        return "sha256:" + digest.hexdigest()

    @staticmethod
    def resolve_local_dependencies(manifest: RoveManifest) -> Dict[str, Dict[str, str]]:
        project_root = os.path.realpath(os.path.dirname(os.path.abspath(manifest.filepath or "rove.toml")))
        resolved: Dict[str, Dict[str, str]] = {}

        def visit(name: str, spec: Any, owner_root: str, stack: List[str]) -> None:
            if not isinstance(spec, dict) or "path" not in spec:
                return
            dependency_root = os.path.realpath(os.path.join(owner_root, str(spec["path"])))
            dependency_manifest_path = next(
                (
                    os.path.join(dependency_root, filename)
                    for filename in ("rove.toml", "nyx.toml")
                    if os.path.isfile(os.path.join(dependency_root, filename))
                ),
                None,
            )
            if dependency_manifest_path is None:
                raise ValueError(
                    f"Local dependency '{name}' has no rove.toml or legacy nyx.toml at {dependency_root}"
                )
            if dependency_root in stack:
                cycle = " -> ".join(stack + [dependency_root])
                raise ValueError(f"Local dependency cycle detected: {cycle}")
            child = RoveManifest(dependency_manifest_path)
            child_name = str(child.package.get("name", ""))
            child_version = str(child.package.get("version", ""))
            if child_name and child_name != name:
                raise ValueError(
                    f"Local dependency key '{name}' does not match package name '{child_name}'"
                )
            required_version = str(spec.get("version", child_version))
            if required_version and required_version != child_version:
                raise ValueError(
                    f"Local dependency '{name}' requires {required_version}, found {child_version}"
                )
            existing = resolved.get(name)
            if existing and os.path.realpath(os.path.join(project_root, existing["path"])) != dependency_root:
                raise ValueError(f"Local dependency '{name}' resolves to multiple paths")
            resolved[name] = {
                "version": child_version,
                "path": os.path.relpath(dependency_root, project_root).replace("\\", "/"),
                "checksum": RoveLock._hash_package(dependency_root),
            }
            for child_name_key, child_spec in sorted(child.dependencies.items()):
                visit(child_name_key, child_spec, dependency_root, stack + [dependency_root])

        for dependency_name, dependency_spec in sorted(manifest.dependencies.items()):
            visit(dependency_name, dependency_spec, project_root, [project_root])
        return resolved

    @staticmethod
    def resolve_dependencies(
        manifest: RoveManifest,
        registry: Optional[PackageRegistry] = None,
        offline: bool = False,
    ) -> Dict[str, Any]:
        """Resolve both local path dependencies and remote registry packages."""
        local_deps = RoveLock.resolve_local_dependencies(manifest)
        remote_reqs: Dict[str, str] = {}
        for name, spec in sorted(manifest.dependencies.items()):
            if name in local_deps:
                continue
            if isinstance(spec, str):
                remote_reqs[name] = spec
            elif isinstance(spec, dict) and "version" in spec and "path" not in spec:
                remote_reqs[name] = str(spec["version"])

        resolved_remote: Dict[str, Dict[str, Any]] = {}
        if remote_reqs and registry is not None:
            resolver = DependencyResolver(registry, offline=offline)
            resolved_remote = resolver.resolve(remote_reqs)

        return {
            "local": local_deps,
            "packages": resolved_remote,
        }

    @staticmethod
    def generate(
        manifest: RoveManifest,
        lock_file: str = "rove.lock",
        registry: Optional[PackageRegistry] = None,
        offline: bool = False,
    ) -> str:
        v = manifest.package.get("version", "0.1.0")
        t = manifest.package.get("target", "cpp")
        resolution = RoveLock.resolve_dependencies(manifest, registry=registry, offline=offline)
        local_dependencies = resolution["local"]
        resolved_packages = resolution["packages"]

        lines = [
            "# Auto-generated lockfile for Rove package manager",
            "# Manual modifications will be overwritten",
            'lockfile_version = 1',
            f'manifest_version = "{v}"',
            f'target = "{t}"',
            ""
        ]
        lines.append("[resolved_dependencies]")
        for dep, item in sorted(local_dependencies.items()):
            lines.append(f'{dep} = "{item["version"]}"')
        for dep, item in sorted(resolved_packages.items()):
            lines.append(f'{dep} = "{item["version"]}"')
        for dep, ver in sorted(manifest.dependencies.items()):
            if dep not in local_dependencies and dep not in resolved_packages:
                if isinstance(ver, str):
                    lines.append(f'{dep} = "{ver}"')
                elif isinstance(ver, dict):
                    lines.append(f'{dep} = "{ver.get("version", "unknown")}"')

        if resolved_packages:
            for dep, item in sorted(resolved_packages.items()):
                lines.extend(("", f"[packages.{dep}]"))
                lines.append(f'version = "{item["version"]}"')
                lines.append('source = "registry"')
                lines.append(f'checksum = "{item["checksum"]}"')
                if item.get("dependencies"):
                    sub_deps = ", ".join(f'{k} = "{v}"' for k, v in sorted(item["dependencies"].items()))
                    lines.append(f'dependencies = {{ {sub_deps} }}')
                else:
                    lines.append('dependencies = {}')

        if local_dependencies:
            lines.extend(("", "[local_dependencies]"))
            for dep, item in sorted(local_dependencies.items()):
                lines.append(
                    f'{dep} = {{ checksum = "{item["checksum"]}", path = "{item["path"]}", '
                    f'version = "{item["version"]}" }}'
                )

        output = "\n".join(lines) + "\n"
        with open(lock_file, "w", encoding="utf-8") as f:
            f.write(output)
        return output

    @staticmethod
    def verify_lockfile(
        manifest: RoveManifest,
        lock_file: str = "rove.lock",
    ) -> bool:
        if not os.path.isfile(lock_file):
            return False
        local_deps = RoveLock.read_local_dependencies(lock_file)
        project_root = os.path.dirname(os.path.abspath(manifest.filepath or "rove.toml"))
        for name, item in local_deps.items():
            path = os.path.join(project_root, item["path"])
            if not os.path.isdir(path):
                return False
            actual_checksum = RoveLock._hash_package(path)
            if actual_checksum != item.get("checksum"):
                raise ChecksumMismatchError(
                    f"Checksum mismatch for local dependency '{name}': expected {item.get('checksum')}, got {actual_checksum}"
                )
        return True

    @staticmethod
    def read_local_dependencies(lock_file: str) -> Dict[str, Dict[str, str]]:
        if not os.path.isfile(lock_file):
            return {}
        parser = RoveManifest()
        section = ""
        resolved: Dict[str, Dict[str, str]] = {}
        with open(lock_file, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip().lower()
                    continue
                if section == "local_dependencies" and "=" in line:
                    name, value = line.split("=", 1)
                    parsed = parser._parse_val(value.strip())
                    if isinstance(parsed, dict):
                        resolved[name.strip()] = {str(k): str(v) for k, v in parsed.items()}
        return resolved


# Rove is the public name from v6 onward.  The Nyx names remain import aliases
# for source compatibility with v5 integrations and lockfiles.
NyxManifest = RoveManifest
NyxLock = RoveLock
Manifest = RoveManifest
