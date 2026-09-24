import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_PATH = os.path.join(ROOT_DIR, "src", "cli.py")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.toolchain.manifest import RoveManifest


def _run(cwd: str, *arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, CLI_PATH, *arguments],
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _output(process: subprocess.CompletedProcess) -> str:
    return (process.stdout + process.stderr).replace("\r\n", "\n")


def run_toolchain_cli_suite() -> bool:
    print("=" * 70)
    print("ROVE TOOLCHAIN CLI REAL-BEHAVIOR CONTRACT")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="rove_toolchain_cli_") as directory:
        root = Path(directory)

        assert _run(directory, "pkg").returncode == 1
        assert _run(directory, "add", "telemetry", "@2.3.4").returncode == 1

        initialized = _run(directory, "init", "cli-contract")
        assert initialized.returncode == 0, _output(initialized)
        assert (root / "rove.toml").is_file() and (root / "rove.lock").is_file()
        assert _run(directory, "init", "overwrite-attempt").returncode == 1

        added = _run(directory, "add", "telemetry", "@2.3.4")
        assert added.returncode == 0, _output(added)
        manifest = RoveManifest(str(root / "rove.toml"))
        assert manifest.dependencies == {"telemetry": "2.3.4"}
        assert 'telemetry = "2.3.4"' in (root / "rove.lock").read_text(encoding="utf-8")

        listed = _run(directory, "pkg")
        assert listed.returncode == 0, _output(listed)
        assert "telemetry: 2.3.4" in _output(listed)

        installed = _run(directory, "install")
        assert installed.returncode == 0, _output(installed)
        assert "Validated and locked 1 dependencies" in _output(installed)
        assert "Remote registry download is not part" in _output(installed)

        removed = _run(directory, "remove", "telemetry")
        assert removed.returncode == 0, _output(removed)
        assert RoveManifest(str(root / "rove.toml")).dependencies == {}
        assert _run(directory, "remove", "telemetry").returncode == 1

        workspace = root / "local-workspace"
        application = workspace / "application"
        physics = workspace / "physics"
        application.mkdir(parents=True)
        physics.mkdir(parents=True)
        assert _run(str(physics), "init", "physics").returncode == 0
        physics_manifest = RoveManifest(str(physics / "rove.toml"))
        physics_manifest.package["version"] = "0.3.0"
        physics_manifest.save(str(physics / "rove.toml"))
        (physics / "src").mkdir()
        (physics / "src" / "math.rove").write_text(
            "fn local_answer() -> int { return 42 }\n", encoding="utf-8"
        )

        assert _run(str(application), "init", "application").returncode == 0
        (application / "src").mkdir()
        application_source = application / "src" / "main.rove"
        application_source.write_text(
            'import "physics/math"\nfn main() { print(local_answer()) }\n',
            encoding="utf-8",
        )
        local_added = _run(str(application), "add", "physics", "--path", "../physics")
        assert local_added.returncode == 0, _output(local_added)
        local_manifest = RoveManifest(str(application / "rove.toml"))
        assert local_manifest.dependencies["physics"] == {
            "path": "../physics",
            "version": "0.3.0",
        }, repr(local_manifest.dependencies["physics"])
        windows_style_manifest = RoveManifest()
        windows_style_manifest._parse(
            ['[dependencies]\n', r'physics = { path = "..\physics", version = "0.3.0" }']
        )
        assert windows_style_manifest.dependencies["physics"]["path"] == "../physics", repr(
            windows_style_manifest.dependencies["physics"]
        )
        first_lock = (application / "rove.lock").read_text(encoding="utf-8")
        assert "[local_dependencies]" in first_lock
        assert 'path = "../physics"' in first_lock
        assert "sha256:" in first_lock
        local_checked = _run(str(application), "check", str(application_source), "--target", "python")
        assert local_checked.returncode == 0, _output(local_checked)

        local_installed = _run(str(application), "install")
        assert local_installed.returncode == 0, _output(local_installed)
        assert (application / "rove.lock").read_text(encoding="utf-8") == first_lock

        (physics / "src" / "math.rove").write_text(
            "fn local_answer() -> int { return 43 }\n", encoding="utf-8"
        )
        assert _run(str(application), "install").returncode == 0
        second_lock = (application / "rove.lock").read_text(encoding="utf-8")
        assert second_lock != first_lock, "local dependency source changes must update the lock checksum"

        physics_manifest = RoveManifest(str(physics / "rove.toml"))
        physics_manifest.dependencies["application"] = {"path": "../application", "version": "0.1.0"}
        physics_manifest.save(str(physics / "rove.toml"))
        cycle = _run(str(application), "install")
        assert cycle.returncode == 1
        assert "cycle detected" in _output(cycle)

        source_path = root / "format_contract.rove"
        source_path.write_text(
            'import cpp "std::filesystem" from "<filesystem>" as fs\n'
            'fn main(){\n'
            'var url="https://rove.dev/a?x=1"// preserve a=b and { braces }\n'
            'if true{\n'
            'print(url)\n'
            'print(fs.current_path().string())\n'
            '}\n'
            '}\n',
            encoding="utf-8",
        )
        original = source_path.read_text(encoding="utf-8")
        formatted = _run(directory, "fmt", str(source_path))
        assert formatted.returncode == 0, _output(formatted)
        first_format = source_path.read_text(encoding="utf-8")
        assert first_format != original
        assert '"https://rove.dev/a?x=1"' in first_format
        assert 'import cpp "std::filesystem" from "<filesystem>" as fs' in first_format
        assert "// preserve a=b and { braces }" in first_format
        assert "    var url = " in first_format and "        print(url)" in first_format
        second_format = _run(directory, "fmt", str(source_path))
        assert second_format.returncode == 0, _output(second_format)
        assert source_path.read_text(encoding="utf-8") == first_format
        checked = _run(directory, "check", str(source_path))
        assert checked.returncode == 0, _output(checked)

        lint_path = root / "lint_contract.rove"
        lint_path.write_text(
            "var value = 1\n"
            "unsafe {\n"
            "    var address = addr(value)\n"
            "    print(peek(address))\n"
            "}\n",
            encoding="utf-8",
        )
        linted = _run(directory, "lint", str(lint_path))
        assert linted.returncode == 0, _output(linted)
        assert "warning[W010]" in _output(linted)
        assert "warning[W002]" not in _output(linted)

        doc_path = root / "documented.rove"
        doc_path.write_text(
            "/// Return <value> & keep it safe.\n"
            "fn documented(value: int) -> int { return value }\n",
            encoding="utf-8",
        )
        documented = _run(directory, "doc", str(doc_path))
        assert documented.returncode == 0, _output(documented)
        html = (root / "docs" / "index.html").read_text(encoding="utf-8")
        assert "Return &lt;value&gt; &amp; keep it safe." in html

        profile_path = root / "profile_contract.rove"
        profile_path.write_text('print("PROFILE_REAL_OUTPUT")\n', encoding="utf-8")
        profiled = _run(directory, "profile", str(profile_path), "--target", "python")
        assert profiled.returncode == 0, _output(profiled)
        profile_output = _output(profiled)
        assert "PROFILE_REAL_OUTPUT" in profile_output
        assert "Total compile + run wall time:" in profile_output
        assert "radar_dsp_scan" not in profile_output

        inspected = _run(directory, "debug", str(profile_path), input_text="q\n")
        assert inspected.returncode == 0, _output(inspected)
        inspect_output = _output(inspected)
        assert "source inspector" in inspect_output
        assert "no runtime state" in inspect_output
        assert "Umut" not in inspect_output and "0x00007FFD" not in inspect_output

        for command in ("fmt", "lint", "doc", "profile", "debug"):
            missing = _run(directory, command, str(root / "missing.rove"))
            assert missing.returncode == 1, (command, _output(missing))

        build_dir = root / "build"
        build_dir.mkdir(exist_ok=True)
        (build_dir / "artifact.tmp").write_text("temporary", encoding="utf-8")
        cleaned = _run(directory, "clean")
        assert cleaned.returncode == 0, _output(cleaned)
        assert not build_dir.exists()

    print(
        "[PASS] fmt/lint/debug/profile/doc and manifest/lock package commands "
        "have real effects, honest output, idempotence, and failure exit codes"
    )
    return True


if __name__ == "__main__":
    sys.exit(0 if run_toolchain_cli_suite() else 1)
