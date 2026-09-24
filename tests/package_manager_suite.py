import json
import os
import shutil
import sys
import tempfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.toolchain.manifest import (
    ChecksumMismatchError,
    DependencyCycleError,
    DependencyResolver,
    NyxLock,
    NyxManifest,
    OfflineCacheMissError,
    PackageError,
    PackageRegistry,
    SemVer,
    SemVerParseError,
    SemVerRange,
    VersionConflictError,
)


def run_package_manager_suite() -> bool:
    print("=" * 70)
    print("ROVE PACKAGE MANAGER (45-PKG) CONFORMANCE SUITE")
    print("=" * 70)

    # 1. SemVer parsing and comparisons
    v1_0_0 = SemVer.parse("1.0.0")
    v1_1_0 = SemVer.parse("1.1.0")
    v1_1_2 = SemVer.parse("1.1.2")
    v2_0_0 = SemVer.parse("2.0.0")
    v_alpha = SemVer.parse("1.0.0-alpha.1")

    assert v1_0_0 == SemVer(1, 0, 0)
    assert v1_0_0 < v1_1_0 < v1_1_2 < v2_0_0
    assert v_alpha < v1_0_0
    assert str(v1_1_2) == "1.1.2"
    assert str(v_alpha) == "1.0.0-alpha.1"

    for invalid in ("1", "1.0", "1.0.0.0", "vX.Y.Z", ""):
        try:
            SemVer.parse(invalid)
            raise AssertionError(f"SemVer accepted invalid string: '{invalid}'")
        except SemVerParseError:
            pass

    # 2. SemVer ranges
    caret = SemVerRange("^1.1.0")
    assert caret.matches(v1_1_0)
    assert caret.matches(v1_1_2)
    assert not caret.matches(v2_0_0)
    assert not caret.matches(v1_0_0)

    tilde = SemVerRange("~1.1.0")
    assert tilde.matches(v1_1_0)
    assert tilde.matches(v1_1_2)
    assert not tilde.matches(SemVer.parse("1.2.0"))

    compound = SemVerRange(">= 1.0.0, < 1.1.2")
    assert compound.matches(v1_0_0)
    assert compound.matches(v1_1_0)
    assert not compound.matches(v1_1_2)

    wildcard = SemVerRange("*")
    assert wildcard.matches(v1_0_0)
    assert wildcard.matches(v2_0_0)

    # 3. Registry & Dependency Resolver
    with tempfile.TemporaryDirectory(prefix="nyx_pkg_suite_") as suite_tmp:
        cache_dir = os.path.join(suite_tmp, "cache")
        registry = PackageRegistry(cache_dir=cache_dir)

        # Setup packages
        registry.publish_mock_package("utils", "1.0.0")
        registry.publish_mock_package("utils", "1.1.0")
        registry.publish_mock_package("utils", "1.2.0")

        registry.publish_mock_package("core", "1.0.0", dependencies={"utils": "^1.0.0"})
        registry.publish_mock_package("core", "1.2.0", dependencies={"utils": "^1.1.0"})
        registry.publish_mock_package("plugin_a", "0.1.0", dependencies={"utils": "~1.1.0"})

        # Normal resolution selecting latest compatible
        resolver = DependencyResolver(registry)
        resolved = resolver.resolve({"core": "^1.0.0", "plugin_a": "^0.1.0"})
        assert resolved["core"]["version"] == "1.2.0"
        assert resolved["plugin_a"]["version"] == "0.1.0"
        assert resolved["utils"]["version"] == "1.1.0"

        # 4. Version Conflict
        registry.publish_mock_package("incompat", "1.0.0", dependencies={"utils": ">= 2.0.0"})
        try:
            resolver.resolve({"core": "^1.0.0", "incompat": "1.0.0"})
            raise AssertionError("Resolver accepted incompatible version constraints")
        except VersionConflictError as err:
            assert "Version conflict" in str(err)

        # 5. Dependency Cycle
        registry.publish_mock_package("cycle_x", "1.0.0", dependencies={"cycle_y": "^1.0.0"})
        registry.publish_mock_package("cycle_y", "1.0.0", dependencies={"cycle_x": "^1.0.0"})
        try:
            resolver.resolve({"cycle_x": "^1.0.0"})
            raise AssertionError("Resolver accepted cyclical dependencies")
        except DependencyCycleError as err:
            assert "cycle detected" in str(err).lower()

        # 6. Offline Cache Hit & Miss
        offline_resolver = DependencyResolver(registry, offline=True)
        cached_res = offline_resolver.resolve({"core": "^1.0.0", "plugin_a": "^0.1.0"})
        assert cached_res["utils"]["version"] == "1.1.0"

        try:
            offline_resolver.resolve({"unknown_pkg": "^1.0.0"})
            raise AssertionError("Offline resolver did not report cache miss")
        except OfflineCacheMissError as err:
            assert "offline cache" in str(err).lower()

        # 7. Checksum Mismatch Detection
        core_cache_meta = os.path.join(cache_dir, "core", "1.2.0", "metadata.json")
        with open(core_cache_meta, "r+", encoding="utf-8") as handle:
            meta = json.load(handle)
            meta["files"]["src/lib.rove"] = "// TAMPERED PAYLOAD\n"
            handle.seek(0)
            json.dump(meta, handle)
            handle.truncate()

        try:
            offline_resolver.resolve({"core": "^1.0.0"})
            raise AssertionError("Resolver accepted tampered package cache")
        except ChecksumMismatchError as err:
            assert "Checksum mismatch" in str(err)

        # 8. Lockfile Determinism & Verification
        app_dir = os.path.join(suite_tmp, "app")
        os.makedirs(app_dir, exist_ok=True)
        manifest_path = os.path.join(app_dir, "nyx.toml")
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(
                '[package]\n'
                'name = "test_app"\n'
                'version = "0.1.0"\n'
                'edition = "2026"\n'
                'target = "cpp"\n\n'
                '[dependencies]\n'
                'utils = "1.0.0"\n'
            )

        manifest = NyxManifest(manifest_path)
        lock_path = os.path.join(app_dir, "nyx.lock")

        out1 = NyxLock.generate(manifest, lock_file=lock_path, registry=registry)
        with open(lock_path, "r", encoding="utf-8") as f:
            read1 = f.read()
        assert out1 == read1
        assert "lockfile_version = 1" in read1
        assert "[resolved_dependencies]" in read1
        assert 'utils = "1.0.0"' in read1
        assert "[packages.utils]" in read1

        out2 = NyxLock.generate(manifest, lock_file=lock_path, registry=registry)
        assert out1 == out2

        assert NyxLock.verify_lockfile(manifest, lock_file=lock_path)

    print("[PASS] SemVer parsing, caret/tilde ranges, cycle detection, version conflicts, offline cache, checksum validation, and deterministic lockfiles")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_package_manager_suite() else 1)
