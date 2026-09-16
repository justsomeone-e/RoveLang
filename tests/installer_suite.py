import json
import os
import shutil
import subprocess
import sys
import tempfile


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS_INSTALLER = os.path.join(ROOT_DIR, "install.ps1")
UNIX_INSTALLER = os.path.join(ROOT_DIR, "install.sh")
RELEASE_WORKFLOW = os.path.join(ROOT_DIR, ".github", "workflows", "release.yml")
RELEASE_PACKAGER = os.path.join(ROOT_DIR, "tools", "release_package.py")
CLI_PATH = os.path.join(ROOT_DIR, "src", "cli.py")

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.version import VERSION


def _wsl_path(path: str) -> str:
    drive, tail = os.path.splitdrive(os.path.abspath(path))
    if not drive:
        return path.replace("\\", "/")
    normalized_tail = tail.lstrip("\\/").replace("\\", "/")
    return f"/mnt/{drive[0].lower()}/{normalized_tail}"


def _run(command, *, cwd=ROOT_DIR, env=None, timeout=240):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _build_native_fixture(directory: str) -> str:
    executable = "nyxc.exe" if os.name == "nt" else "nyxc"
    output_path = os.path.join(directory, executable)
    build = _run(
        [sys.executable, CLI_PATH, "self-host", "build", "-o", output_path],
        timeout=300,
    )
    assert build.returncode == 0, build.stderr or build.stdout
    if os.name != "nt":
        os.chmod(output_path, 0o755)
    version = _run([output_path, "--version"])
    assert version.returncode == 0, version.stderr or version.stdout
    assert "native self-host" in version.stdout
    return output_path


def _exercise_stale_native_rejection() -> None:
    with tempfile.TemporaryDirectory(prefix="nyx_stale_native_") as directory:
        environment = os.environ.copy()
        environment["NYX_INSTALL_DIR"] = os.path.join(directory, "install")
        environment["NYX_SKIP_PATH_UPDATE"] = "1"
        environment["NYX_SKIP_EDITOR_INSTALL"] = "1"
        if os.name == "nt":
            fake_native = os.path.join(directory, "stale-nyxc.cmd")
            with open(fake_native, "w", encoding="ascii", newline="\r\n") as handle:
                handle.write("@echo off\necho Usage: nyxc ^<input.nyx^> ^<output.cpp^>\nexit /b 0\n")
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            assert powershell
            environment["NYX_NATIVE_COMPILER_PATH"] = fake_native
            rejected = _run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    WINDOWS_INSTALLER,
                ],
                env=environment,
            )
        else:
            fake_native = os.path.join(directory, "stale-nyxc")
            with open(fake_native, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("#!/usr/bin/env sh\necho 'Usage: nyxc <input.nyx> <output.cpp>'\nexit 0\n")
            os.chmod(fake_native, 0o755)
            environment["NYX_NATIVE_COMPILER_PATH"] = fake_native
            rejected = _run([shutil.which("bash") or "bash", UNIX_INSTALLER], env=environment)
        assert rejected.returncode != 0
        assert "does not point to a working nyxc" in (rejected.stderr + rejected.stdout)


def _exercise_install(install_dir: str, wrapper: str) -> None:
    native_name = "nyxc.exe" if os.name == "nt" else "nyxc"
    installed_native = os.path.join(install_dir, "bin", native_name)
    assert os.path.isfile(installed_native)
    assert os.path.isfile(os.path.join(install_dir, "src", "cli.py"))
    assert os.path.isfile(os.path.join(install_dir, "compiler", "parser.nyx"))
    assert os.path.isfile(os.path.join(install_dir, "VERSION"))
    assert os.path.isfile(os.path.join(install_dir, "LICENSE"))

    version = _run([wrapper, "--version"], cwd=install_dir)
    assert version.returncode == 0, version.stderr or version.stdout
    assert f"nyxc {VERSION} (native self-host)" in version.stdout

    version_alias = _run([wrapper, "version"], cwd=install_dir)
    assert version_alias.returncode == 0, version_alias.stderr or version_alias.stdout
    assert f"nyxc {VERSION} (native self-host)" in version_alias.stdout

    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
        {"jsonrpc": "2.0", "method": "exit", "params": {}},
    ]
    wire_input = b""
    for message in messages:
        body = json.dumps(message).encode("utf-8")
        wire_input += f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    lsp = subprocess.run(
        [wrapper, "lsp"],
        cwd=install_dir,
        input=wire_input,
        capture_output=True,
        timeout=30,
    )
    assert lsp.returncode == 0, lsp.stderr.decode("utf-8", errors="replace")
    assert b'"id": 1' in lsp.stdout and b'"hoverProvider": true' in lsp.stdout
    assert b'"id": 2' in lsp.stdout and b'"result": null' in lsp.stdout

    sample_path = os.path.join(install_dir, "native-installer-smoke.nyx")
    with open(sample_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("fn main() { print(42); }\n")
    checked = _run([wrapper, "check", sample_path], cwd=install_dir)
    assert checked.returncode == 0, checked.stderr or checked.stdout
    assert "NYX_CHECK_OK" in checked.stdout

    binary_path = os.path.join(
        install_dir, "native-installer-smoke.exe" if os.name == "nt" else "native-installer-smoke"
    )
    compiled = _run(
        [wrapper, "compile", sample_path, "-o", binary_path],
        cwd=install_dir,
    )
    assert compiled.returncode == 0, compiled.stderr or compiled.stdout
    assert "NYX_BUILD_OK" in compiled.stdout
    executed = _run([binary_path], cwd=install_dir)
    assert executed.returncode == 0, executed.stderr or executed.stdout
    assert executed.stdout.strip() == "42"

    top_level_path = os.path.join(install_dir, "top-level-cpp-smoke.nyx")
    with open(top_level_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('#target cpp\nprint("helloworld")\n')
    top_level_run = _run([wrapper, "run", top_level_path], cwd=install_dir)
    assert top_level_run.returncode == 0, top_level_run.stderr or top_level_run.stdout
    assert "helloworld" in top_level_run.stdout

    manifest = _run([wrapper, "targets", "--json"], cwd=install_dir)
    assert manifest.returncode == 0, manifest.stderr or manifest.stdout
    assert json.loads(manifest.stdout)["schema_version"] == 1


def _exercise_unix_editor_install(native_fixture: str) -> None:
    if os.name == "nt":
        return
    with tempfile.TemporaryDirectory(prefix="nyx_editor_install_") as directory:
        fake_home = os.path.join(directory, "home")
        fake_bin = os.path.join(directory, "bin")
        install_dir = os.path.join(directory, "install")
        os.makedirs(fake_home)
        os.makedirs(fake_bin)
        for command in ("code", "npm"):
            command_path = os.path.join(fake_bin, command)
            with open(command_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("#!/usr/bin/env sh\nexit 0\n")
            os.chmod(command_path, 0o755)

        environment = os.environ.copy()
        environment["HOME"] = fake_home
        environment["PATH"] = fake_bin + os.pathsep + environment.get("PATH", "")
        environment["NYX_INSTALL_DIR"] = install_dir
        environment["NYX_NATIVE_COMPILER_PATH"] = native_fixture
        environment["NYX_SKIP_PATH_UPDATE"] = "1"
        environment.pop("NYX_SKIP_EDITOR_INSTALL", None)
        install = _run([shutil.which("bash") or "bash", UNIX_INSTALLER], env=environment)
        assert install.returncode == 0, install.stderr or install.stdout

        extension_dir = os.path.join(fake_home, ".vscode", "extensions", "nyx-lang-support")
        assert os.path.isfile(os.path.join(extension_dir, "package.json"))
        assert os.path.isfile(os.path.join(extension_dir, "syntaxes", "nyx.tmLanguage.json"))
        assert "Installed Nyx editor support" in install.stdout


def run_installer_suite() -> bool:
    print("=" * 70)
    print("NYX NATIVE-FIRST PORTABLE INSTALLER CONTRACT")
    print("=" * 70)

    _exercise_stale_native_rejection()

    with tempfile.TemporaryDirectory(prefix="nyx_native_fixture_") as fixture_dir:
        native_fixture = _build_native_fixture(fixture_dir)

        if os.name == "nt":
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            assert powershell, "PowerShell is required for the Windows installer contract"
            with tempfile.TemporaryDirectory(prefix="nyx_install_contract_") as install_dir:
                environment = os.environ.copy()
                environment["NYX_INSTALL_DIR"] = install_dir
                environment["NYX_NATIVE_COMPILER_PATH"] = native_fixture
                environment["NYX_SKIP_PATH_UPDATE"] = "1"
                environment["NYX_SKIP_EDITOR_INSTALL"] = "1"
                install = _run(
                    [
                        powershell,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        WINDOWS_INSTALLER,
                    ],
                    env=environment,
                )
                assert install.returncode == 0, install.stderr or install.stdout
                wrapper = os.path.join(install_dir, "bin", "nyx.cmd")
                assert os.path.isfile(wrapper)
                _exercise_install(install_dir, wrapper)
        else:
            bash = shutil.which("bash")
            assert bash, "Bash is required for the Unix installer contract"
            with tempfile.TemporaryDirectory(prefix="nyx_install_contract_") as install_dir:
                environment = os.environ.copy()
                environment["NYX_INSTALL_DIR"] = install_dir
                environment["NYX_NATIVE_COMPILER_PATH"] = native_fixture
                environment["NYX_SKIP_PATH_UPDATE"] = "1"
                environment["NYX_SKIP_EDITOR_INSTALL"] = "1"
                install = _run([bash, UNIX_INSTALLER], env=environment)
                assert install.returncode == 0, install.stderr or install.stdout
                wrapper = os.path.join(install_dir, "bin", "nyx")
                assert os.path.isfile(wrapper)
                _exercise_install(install_dir, wrapper)
            _exercise_unix_editor_install(native_fixture)

    bash = shutil.which("bash")
    if bash:
        syntax = _run([bash, "-n", _wsl_path(UNIX_INSTALLER)])
        assert syntax.returncode == 0, syntax.stderr or syntax.stdout

    with open(UNIX_INSTALLER, "r", encoding="utf-8") as handle:
        unix_source = handle.read()
    assert 'cp -R "$SOURCE_ROOT/src/." "$SRC_DIR/"' in unix_source
    assert "for legal_file in VERSION LICENSE;" in unix_source
    assert 'exec "$native" "$@"' in unix_source
    assert '"nyxc $EXPECTED_VERSION "*' in unix_source
    assert 'node_modules' not in unix_source
    assert 'nyx_commands.js' in unix_source
    assert "NYX_NATIVE_COMPILER_PATH" in unix_source
    assert "sha256sum" in unix_source and "shasum" in unix_source
    assert "Python 3.10+ is required to run Nyx" not in unix_source
    assert "releases/latest" not in unix_source
    assert 'for command_name in nyx he' not in unix_source
    assert 'npm ci --omit=dev --ignore-scripts' in unix_source
    assert '.vscode/extensions/nyx-lang-support' in unix_source
    assert '.vscode-oss/extensions/nyx-lang-support' in unix_source
    assert 'sudo pacman -S --needed base-devel' in unix_source

    with open(WINDOWS_INSTALLER, "r", encoding="utf-8") as handle:
        windows_source = handle.read()
    assert "C:\\Users\\USER" not in windows_source
    assert "NYX_INSTALL_DIR" in windows_source
    assert "NYX_NATIVE_COMPILER_PATH" in windows_source
    assert "Get-FileHash" in windows_source
    assert 'StartsWith("nyxc $ExpectedVersion ")' in windows_source
    assert '@("VERSION", "LICENSE")' in windows_source
    assert "Prioritized $BinDir in User PATH" in windows_source
    assert "$nativeCommands" in windows_source
    assert '"nyx_commands.js"' in windows_source
    assert 'vscode-extension\\*' not in windows_source
    assert 'Get-Command "npm.cmd", "npm.exe"' in windows_source
    assert "$NpmCandidate.Path, $NpmCandidate.Source, $NpmCandidate.Definition" in windows_source
    assert "$NpmCandidate.Source.EndsWith" not in windows_source
    assert "$command.Path, $command.Definition, $command.Source" in windows_source
    assert "& $command.Source -c" not in windows_source
    assert "Downloaded archive did not contain a Nyx source root with src/." in windows_source
    assert 'cmd.exe /c npm ci --omit=dev --ignore-scripts' in windows_source
    assert "VS Code extension installation skipped" in windows_source
    assert "[string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture" in windows_source
    assert '[string]$env:PROCESSOR_ARCHITECTURE' in windows_source
    assert '$_ -in @("x64", "amd64")' in windows_source

    with open(RELEASE_WORKFLOW, "r", encoding="utf-8") as handle:
        release_source = handle.read()
    for asset in (
        "nyxc-windows-x86_64.exe",
        "nyxc-linux-x86_64",
        "nyxc-macos-x86_64",
        "nyxc-macos-arm64",
    ):
        assert asset in release_source
    assert "actions/upload-artifact@v4" in release_source
    assert "actions/download-artifact@v4" in release_source
    assert ".sha256" in release_source
    assert "tools/release_package.py" in release_source
    assert "SOURCE_DATE_EPOCH" in release_source
    assert "SHA256SUMS" in release_source
    assert "anchore/sbom-action@e22c389904149dbc22b58101806040fa8d37a610" in release_source
    assert "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6" in release_source
    assert "attestations: write" in release_source and "id-token: write" in release_source
    assert "npm run package" in release_source
    assert "nyx-language-support-${{ github.ref_name }}.vsix" in release_source
    assert "dist/*.vsix" in release_source
    assert os.path.isfile(RELEASE_PACKAGER)

    with open(CLI_PATH, "r", encoding="utf-8") as handle:
        cli_source = handle.read()
    assert "C:/Users/USER" not in cli_source
    assert "C:\\Users\\USER" not in cli_source
    assert "Rust stable MSVC" not in cli_source

    with open(os.path.join(ROOT_DIR, "vscode-extension", "extension.js"), "r", encoding="utf-8") as handle:
        extension_source = handle.read()
    assert "C:\\Users\\USER" not in extension_source
    with open(os.path.join(ROOT_DIR, "vscode-extension", "package.json"), "r", encoding="utf-8") as handle:
        extension_manifest = handle.read()
    assert "nyx.runCurrentFile" in extension_manifest

    with tempfile.TemporaryDirectory(prefix="nyx_scaffold_contract_") as scaffold_dir:
        scaffold = _run([sys.executable, CLI_PATH, "new", "portable_app"], cwd=scaffold_dir)
        assert scaffold.returncode == 0, scaffold.stderr or scaffold.stdout
        properties_path = os.path.join(
            scaffold_dir, "portable_app", ".vscode", "c_cpp_properties.json"
        )
        with open(properties_path, "r", encoding="utf-8") as handle:
            properties = json.load(handle)
        configuration = properties["configurations"][0]
        compiler_path = configuration.get("compilerPath")
        assert compiler_path is None or os.path.isfile(compiler_path)
        assert configuration["cppStandard"] == "c++20"

    print("[PASS] Native-first installers, release assets, and Python fallback are portable")
    return True


if __name__ == "__main__":
    sys.exit(0 if run_installer_suite() else 1)
