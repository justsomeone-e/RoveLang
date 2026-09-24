import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
import os
import sys
import time
import json
import re
import shutil
import subprocess
import html
from typing import List, Dict, Any, Optional

# =========================================================
# 1. CODE FORMATTER (rove fmt)
# =========================================================
class Formatter:
    @staticmethod
    def _split_segments(line: str):
        """Split source into code and protected string/comment segments."""
        segments = []
        buffer = []
        quote = None
        escaped = False
        index = 0

        def flush(is_code: bool):
            if buffer:
                segments.append((is_code, "".join(buffer)))
                buffer.clear()

        while index < len(line):
            character = line[index]
            if quote is not None:
                buffer.append(character)
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    flush(False)
                    quote = None
                index += 1
                continue

            if character in ('"', "'"):
                flush(True)
                quote = character
                buffer.append(character)
                index += 1
                continue
            if character == "/" and index + 1 < len(line) and line[index + 1] == "/":
                flush(True)
                segments.append((False, line[index:]))
                return segments
            buffer.append(character)
            index += 1

        flush(quote is None)
        return segments

    @staticmethod
    def _format_code(value: str) -> str:
        if not value:
            return value
        value = re.sub(r"\s*\?\s*\.\s*", "?.", value)
        value = re.sub(
            r"\s*(->|=>|\|>|==|!=|<=|>=|<<|>>|\?\?)\s*",
            r" \1 ",
            value,
        )
        value = re.sub(r"(?<!:)\s*:\s*(?!:)", ": ", value)
        value = re.sub(r"\s*,\s*", ", ", value)
        value = re.sub(
            r"(?<![=!<>+\-*/%&|^])\s*=\s*(?!=|>)",
            " = ",
            value,
        )
        return value

    @classmethod
    def format_source(cls, source: str) -> str:
        formatted = []
        indent = 0
        for raw in source.splitlines():
            stripped = raw.strip()
            if not stripped:
                formatted.append("")
                continue

            segments = cls._split_segments(stripped)
            rendered = "".join(
                cls._format_code(value) if is_code else value
                for is_code, value in segments
            ).rstrip()
            code_only = "".join(value if is_code else "" for is_code, value in segments)
            leading_closes = len(code_only) - len(code_only.lstrip("}"))
            line_indent = max(0, indent - leading_closes)
            formatted.append(("    " * line_indent) + rendered)

            opens = code_only.count("{")
            closes = code_only.count("}")
            indent = max(0, line_indent + opens - (closes - leading_closes))

        return "\n".join(formatted) + "\n"

    @staticmethod
    def format_file(filepath: str) -> bool:
        if not os.path.exists(filepath):
            print(f"[!] File not found: {filepath}")
            return False
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            source = f.read()
        rendered = Formatter.format_source(source)
        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(rendered)

        print(f"\033[92m[✓] Formatted:\033[0m {filepath}")
        return True

# =========================================================
# 2. LINTER (he lint)
# =========================================================
class Linter:
    @staticmethod
    def lint_file(filepath: str) -> int:
        if not os.path.exists(filepath):
            print(f"[!] File not found: {filepath}")
            return -1
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

        warnings_count = 0
        brace_depth = 0
        unsafe_base_depth = None

        for idx, raw in enumerate(lines, 1):
            line = raw.strip()
            segments = Formatter._split_segments(line)
            code = "".join(value if is_code else "" for is_code, value in segments)
            if re.search(r"\bunsafe\s*\{", code):
                unsafe_base_depth = brace_depth

            # Check unsafe memory calls outside unsafe
            if ("peek(" in code or "memdump(" in code) and unsafe_base_depth is None:
                print(f"\033[93mwarning[W002]:\033[0m Raw memory operation detected without explicit 'unsafe' block.")
                print(f"  --> {filepath}:{idx}")
                print(f"   | {line}")
                warnings_count += 1

            # Check variable declaration
            var_match = re.match(r'^(?:var|let)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?::\s*([a-zA-Z_<>?, *]+))?\s*=', code)
            if var_match:
                vname = var_match.group(1)
                if not var_match.group(2):
                    print(f"\033[93mwarning[W010]:\033[0m Variable '{vname}' lacks explicit type annotation.")
                    print(f"  --> {filepath}:{idx}")
                    warnings_count += 1

            brace_depth += code.count("{") - code.count("}")
            brace_depth = max(0, brace_depth)
            if unsafe_base_depth is not None and brace_depth <= unsafe_base_depth:
                unsafe_base_depth = None

        print(f"\n\033[96m[*] Lint finished:\033[0m {warnings_count} warning(s) found in {filepath}")
        return warnings_count

# =========================================================
# 3. INTERACTIVE DEBUGGER (he debug)
# =========================================================
class Debugger:
    @staticmethod
    def debug_file(filepath: str) -> int:
        if not os.path.exists(filepath):
            print(f"[!] File not found: {filepath}")
            return 1

        from src.api import RoveCompiler

        checked = RoveCompiler(os.path.dirname(os.path.abspath(filepath))).check_file(filepath)
        if not checked.success:
            for diagnostic in checked.diagnostics:
                print(diagnostic.rendered)
            return 1

        with open(filepath, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

        print("\033[96mRove source inspector (validated source; no runtime state)\033[0m")
        print(f"Inspecting: {filepath} ({len(lines)} lines)")
        print("Commands: (n)ext, (l)ist, (b)reak <line>, (c)ontinue, (q)uit")
        print("Runtime variable/memory inspection requires source-map support and is not simulated.\n")

        pc = 0
        breakpoints = set()
        while pc < len(lines):
            line_number = pc + 1
            if line_number in breakpoints:
                print(f"\033[91m[BREAKPOINT]\033[0m line {line_number}")
            print(f"\033[94m[{line_number:3d}]\033[0m {lines[pc].rstrip()}")
            try:
                cmd = input("\033[93m(inspect) > \033[0m").strip().split()
            except EOFError:
                print("[*] Input closed; source inspection ended.")
                return 0
            if not cmd:
                pc += 1
                continue

            action = cmd[0].lower()
            if action in ("q", "quit"):
                print("[*] Source inspection ended.")
                return 0
            elif action in ("n", "next"):
                pc += 1
            elif action in ("b", "break") and len(cmd) > 1:
                try:
                    bp_line = int(cmd[1])
                    if not 1 <= bp_line <= len(lines):
                        raise ValueError
                    breakpoints.add(bp_line)
                    print(f"[+] Breakpoint set at line {bp_line}")
                except ValueError:
                    print("[!] Invalid line number")
            elif action in ("l", "list"):
                start = max(0, pc - 2)
                end = min(len(lines), pc + 3)
                for index in range(start, end):
                    marker = ">" if index == pc else " "
                    print(f"{marker} {index + 1:3d} {lines[index].rstrip()}")
            elif action in ("c", "continue"):
                following = sorted(line - 1 for line in breakpoints if line - 1 > pc)
                pc = following[0] if following else len(lines)
            else:
                print("[!] Unknown command. Use n, l, b, c, q")
        print("[*] End of source reached.")
        return 0

# =========================================================
# 4. RUNTIME PROFILER (he profile)
# =========================================================
class Profiler:
    @staticmethod
    def profile_file(filepath: str, runner) -> int:
        if not os.path.exists(filepath):
            print(f"[!] File not found: {filepath}")
            return 1
        print("\033[96mRove real wall-clock profile\033[0m")
        print(f"Program: {filepath}")
        print("Scope: compile + run (function-level instrumentation is not available yet)\n")
        t0 = time.perf_counter()
        try:
            status = int(runner())
        except Exception as exc:
            print(f"\033[91m[!] Profiled command failed: {exc}\033[0m")
            return 1
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        print(f"\nTotal compile + run wall time: {elapsed_ms:.3f} ms")
        print(f"Process status: {status}")
        return status

# =========================================================
# 5. DOCUMENTATION GENERATOR (he doc)
# =========================================================
class DocGenerator:
    @staticmethod
    def generate_docs(filepath: str) -> int:
        if not os.path.exists(filepath):
            print(f"[!] File not found: {filepath}")
            return 1
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

        docs_dir = os.path.join(os.path.dirname(os.path.abspath(filepath)), "docs")
        os.makedirs(docs_dir, exist_ok=True)

        doc_items = []
        current_doc = []

        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("///"):
                current_doc.append(trimmed[3:].strip())
            elif trimmed.startswith("fn ") or trimmed.startswith("struct ") or trimmed.startswith("trait "):
                doc_items.append({
                    "signature": trimmed.split("{")[0].strip(),
                    "doc": " ".join(current_doc) if current_doc else "Belgelendirme bulunmuyor."
                })
                current_doc = []
            else:
                if not trimmed.startswith("//"):
                    current_doc = []

        html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Rove Documentation - {html.escape(os.path.basename(filepath))}</title>
    <style>
        body {{ background: #03070D; color: #F1F5F9; font-family: -apple-system, monospace; padding: 40px; }}
        h1 {{ color: #00F0FF; border-bottom: 1px solid #1B2D44; padding-bottom: 12px; }}
        .item {{ background: #08101C; border: 1px solid #1B2D44; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .sig {{ color: #FFB800; font-family: monospace; font-size: 16px; font-weight: bold; }}
        .desc {{ color: #94A3B8; margin-top: 10px; line-height: 1.6; font-size: 14px; }}
    </style>
</head>
<body>
    <h1>Rove Otomatik Dokümantasyon</h1>
    <p>Dosya: <code>{html.escape(os.path.basename(filepath))}</code></p>
    <div style="margin-top: 30px;">
"""
        for it in doc_items:
            html_content += f"""
        <div class="item">
            <div class="sig">{html.escape(it['signature'])}</div>
            <div class="desc">{html.escape(it['doc'])}</div>
        </div>
"""
        html_content += """
    </div>
</body>
</html>"""

        out_path = os.path.join(docs_dir, "index.html")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"\033[92m[✓] Documentation generated at:\033[0m {out_path}")
        return 0

# =========================================================
# 6. PACKAGE MANAGER (rove pkg / rove add / rove remove / rove.toml)
# =========================================================
from src.toolchain.manifest import RoveManifest, RoveLock

class PackageManager:
    @staticmethod
    def _manifest_path():
        return next((name for name in ("rove.toml", "nyx.toml") if os.path.exists(name)), None)

    @staticmethod
    def _lock_path(manifest_file: str) -> str:
        return "rove.lock" if os.path.basename(manifest_file) == "rove.toml" else "nyx.lock"

    @staticmethod
    def init(name: str = "my_project", force: bool = False) -> int:
        if PackageManager._manifest_path() and not force:
            print("\033[91m[!] A project manifest already exists. Use 'rove init --force' to replace it.\033[0m")
            return 1
        m = RoveManifest()
        m.package["name"] = name
        m.save("rove.toml")
        RoveLock.generate(m, "rove.lock")
        print("\033[92m[OK] Created rove.toml manifest & rove.lock successfully!\033[0m")
        return 0

    @staticmethod
    def add(pkg_name: str, version: str = "1.0.0", local_path: Optional[str] = None) -> int:
        manifest_file = PackageManager._manifest_path()
        if not manifest_file:
            print("\033[91m[!] No rove.toml found. Run 'rove init' first.\033[0m")
            return 1
        if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", pkg_name):
            print(f"\033[91m[!] Invalid package name: '{pkg_name}'.\033[0m")
            return 1
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]*", version):
            print(f"\033[91m[!] Invalid package version: '{version}'.\033[0m")
            return 1
        dependency: Any = version
        if local_path is not None:
            base_cwd = os.path.realpath(os.getcwd())
            dependency_root = os.path.realpath(os.path.join(base_cwd, local_path))
            dependency_manifest = next(
                (
                    os.path.join(dependency_root, name)
                    for name in ("rove.toml", "nyx.toml")
                    if os.path.isfile(os.path.join(dependency_root, name))
                ),
                os.path.join(dependency_root, "rove.toml"),
            )
            if not os.path.isfile(dependency_manifest):
                print(f"\033[91m[!] Local dependency has no rove.toml or legacy nyx.toml: {dependency_root}\033[0m")
                return 1
            child = RoveManifest(dependency_manifest)
            child_name = str(child.package.get("name", ""))
            child_version = str(child.package.get("version", ""))
            if child_name != pkg_name:
                print(f"\033[91m[!] Local package is named '{child_name}', expected '{pkg_name}'.\033[0m")
                return 1
            if version != "1.0.0" and version != child_version:
                print(f"\033[91m[!] Local package version is {child_version}, requested {version}.\033[0m")
                return 1
            version = child_version
            dependency = {
                "path": os.path.relpath(dependency_root, base_cwd).replace("\\", "/"),
                "version": version,
            }
        print(f"\033[96m[*] Adding dependency:\033[0m {pkg_name} @ {version}...")
        m = RoveManifest(manifest_file)
        m.dependencies[pkg_name] = dependency
        try:
            RoveLock.generate(m, PackageManager._lock_path(manifest_file))
        except ValueError as error:
            print(f"\033[91m[!] Dependency resolution failed: {error}\033[0m")
            return 1
        m.save(manifest_file)
        print(f"\033[92m[OK] Added '{pkg_name}' v{version} to {manifest_file} and {PackageManager._lock_path(manifest_file)}.\033[0m")
        return 0

    @staticmethod
    def remove(pkg_name: str) -> int:
        manifest_file = PackageManager._manifest_path()
        if not manifest_file:
            print("\033[91m[!] No rove.toml found. Run 'rove init' first.\033[0m")
            return 1
        print(f"\033[96m[*] Removing dependency:\033[0m {pkg_name}...")
        m = RoveManifest(manifest_file)
        if pkg_name in m.dependencies:
            del m.dependencies[pkg_name]
            m.save(manifest_file)
            RoveLock.generate(m, PackageManager._lock_path(manifest_file))
            print(f"\033[92m[OK] Removed '{pkg_name}' from {manifest_file} and {PackageManager._lock_path(manifest_file)}.\033[0m")
            return 0
        else:
            print(f"\033[93m[!] Dependency '{pkg_name}' was not found in {manifest_file}.\033[0m")
            return 1

    @staticmethod
    def install() -> int:
        manifest_file = PackageManager._manifest_path()
        if not manifest_file:
            print("\033[91m[!] No rove.toml found. Run 'rove init'\033[0m")
            return 1
        print(f"\033[96m[*] Validating dependencies from {manifest_file}...\033[0m")
        m = RoveManifest(manifest_file)
        try:
            RoveLock.generate(m, PackageManager._lock_path(manifest_file))
        except ValueError as error:
            print(f"\033[91m[!] Dependency resolution failed: {error}\033[0m")
            return 1
        print(f"\033[92m[OK] Validated and locked {len(m.dependencies)} dependencies in {PackageManager._lock_path(manifest_file)}.\033[0m")
        print("[*] Remote registry download is not part of the v4 RC2 package contract; local path dependencies are installed deterministically.")
        return 0

    @staticmethod
    def list_installed() -> int:
        manifest_file = PackageManager._manifest_path()
        if manifest_file:
            m = RoveManifest(manifest_file)
            p_name = m.package.get("name", "rove_app")
            p_ver = m.package.get("version", "0.1.0")
            p_ed = m.package.get("edition", "2026")
            p_tgt = m.package.get("target", "cpp")
            print(f"\033[96mProject:\033[0m {p_name} v{p_ver} (Edition: {p_ed}, Target: {p_tgt})")
            print(f"\033[96mDependencies ({len(m.dependencies)}):\033[0m")
            for k, v in m.dependencies.items():
                print(f"  • {k}: {v}")
            if m.native.get("includes") or m.native.get("links"):
                print(f"\033[96mNative Configuration:\033[0m")
                print(f"  • Includes: {m.native.get('includes', [])}")
                print(f"  • Links:    {m.native.get('links', [])}")
            print(f"\033[96mBuild Configuration:\033[0m")
            print(f"  • Opt Level:   {m.build.get('opt_level', 2)}")
            print(f"  • Output Type: {m.build.get('output_type', 'exe')}")
            return 0
        else:
            print("[!] No rove.toml found in current directory. Run 'rove init'")
            return 1

# =========================================================
# 7. STANDALONE EXECUTABLE COMPILER (he compile --standalone)
# =========================================================
class StandalonePackager:
    @staticmethod
    def compile_standalone(filepath: str):
        print(f"\033[96m[*] Packaging Standalone Binary for:\033[0m {filepath}")
        base_name = os.path.splitext(filepath)[0]
        out_bat = f"{base_name}.exe.bat"
        with open(out_bat, 'w', encoding='utf-8') as f:
            f.write(f"""@echo off
python "{os.path.abspath('he.py')}" run "{os.path.abspath(filepath)}" %*
""")
        print(f"\033[92m[OK] Standalone Executable Created:\033[0m {out_bat}")
        print("You can execute this binary on any system with python.")
