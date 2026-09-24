#!/usr/bin/env bash
set -euo pipefail

echo "==================================================================="
echo "Installing Rove native toolchain..."
echo "==================================================================="

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
INSTALL_DIR="${ROVE_INSTALL_DIR:-${NYX_INSTALL_DIR:-$HOME/.rove}}"
BIN_DIR="$INSTALL_DIR/bin"
SRC_DIR="$INSTALL_DIR/src"
COMPILER_DIR="$INSTALL_DIR/compiler"
EXTENSION_DIR="$INSTALL_DIR/vscode-extension"
NATIVE_EXE="$BIN_DIR/rovec"
REPOSITORY="justsomeone-e/RoveLang"
RELEASE_TAG="${ROVE_RELEASE_TAG:-${NYX_RELEASE_TAG:-}}"
NATIVE_COMPILER_PATH="${ROVE_NATIVE_COMPILER_PATH:-${NYX_NATIVE_COMPILER_PATH:-}}"
SKIP_EDITOR_INSTALL="${ROVE_SKIP_EDITOR_INSTALL:-${NYX_SKIP_EDITOR_INSTALL:-0}}"
SKIP_PATH_UPDATE="${ROVE_SKIP_PATH_UPDATE:-${NYX_SKIP_PATH_UPDATE:-0}}"
TEMP_DIR=""
EXPECTED_VERSION=""
if [ -f "$SCRIPT_DIR/VERSION" ]; then
    EXPECTED_VERSION="$(tr -d '\r\n' < "$SCRIPT_DIR/VERSION")"
fi

cleanup() {
    if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
        temp_base="${TMPDIR:-/tmp}"
        case "$TEMP_DIR" in
            "$temp_base"/rove-install.*) rm -rf -- "$TEMP_DIR" ;;
            *) echo "[!] Refusing to remove unexpected temporary path: $TEMP_DIR" >&2 ;;
        esac
    fi
}
trap cleanup EXIT

download_file() {
    source_url="$1"
    destination="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 2 --connect-timeout 15 "$source_url" -o "$destination"
        return
    fi
    if command -v wget >/dev/null 2>&1; then
        wget -q --timeout=30 -O "$destination" "$source_url"
        return
    fi
    return 127
}

find_python() {
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
    elif command -v python >/dev/null 2>&1; then
        command -v python
    fi
}

validate_native() {
    candidate="$1"
    [ -f "$candidate" ] && [ -x "$candidate" ] || return 1
    version_output="$("$candidate" --version 2>&1)" || return 1
    if [ -n "$EXPECTED_VERSION" ]; then
        case "$version_output" in
            "rovec $EXPECTED_VERSION "*|"nyxc $EXPECTED_VERSION "*) return 0 ;;
            *) return 1 ;;
        esac
    fi
    case "$version_output" in
        "rovec "*|"nyxc "*) return 0 ;;
        *) return 1 ;;
    esac
}

platform_name=""
case "$(uname -s)" in
    Linux) platform_name="linux" ;;
    Darwin) platform_name="macos" ;;
    *) echo "[!] Unsupported native platform: $(uname -s)" >&2; exit 1 ;;
esac

architecture=""
case "$(uname -m)" in
    x86_64|amd64) architecture="x86_64" ;;
    arm64|aarch64) architecture="arm64" ;;
    *) echo "[!] Unsupported native architecture: $(uname -m)" >&2; exit 1 ;;
esac

PYTHON_BIN="$(find_python || true)"
SOURCE_ROOT=""
if [ -d "$SCRIPT_DIR/src" ]; then
    SOURCE_ROOT="$SCRIPT_DIR"
fi

mkdir -p "$BIN_DIR" "$SRC_DIR" "$COMPILER_DIR"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rove-install.XXXXXX")"

NATIVE_READY=0
if [ -n "$NATIVE_COMPILER_PATH" ]; then
    if ! validate_native "$NATIVE_COMPILER_PATH"; then
        echo "[!] ROVE_NATIVE_COMPILER_PATH does not point to a working rovec executable." >&2
        exit 1
    fi
    cp "$NATIVE_COMPILER_PATH" "$NATIVE_EXE"
    chmod +x "$NATIVE_EXE"
    NATIVE_READY=1
    echo "[OK] Installed native compiler from ROVE_NATIVE_COMPILER_PATH."
fi

if [ "$NATIVE_READY" -eq 0 ] && [ -n "$SOURCE_ROOT" ]; then
    for candidate in "$SOURCE_ROOT/build/self_host/rovec" "$SOURCE_ROOT/build/self_host/nyxc" "$SOURCE_ROOT/bin/rovec" "$SOURCE_ROOT/bin/nyxc"; do
        if validate_native "$candidate"; then
            cp "$candidate" "$NATIVE_EXE"
            chmod +x "$NATIVE_EXE"
            NATIVE_READY=1
            echo "[OK] Installed existing local native compiler."
            break
        fi
    done
fi

if [ "$NATIVE_READY" -eq 0 ] && [ -z "$SOURCE_ROOT" ] && [ -n "$RELEASE_TAG" ]; then
    if [ -n "$RELEASE_TAG" ]; then
        release_base="https://github.com/$REPOSITORY/releases/download/$RELEASE_TAG"
    fi
    for asset_name in "rovec-$platform_name-$architecture" "nyxc-$platform_name-$architecture"; do
      asset_path="$TEMP_DIR/$asset_name"
      checksum_path="$TEMP_DIR/$asset_name.sha256"
      echo "[*] Looking for native release asset $asset_name..."
      if download_file "$release_base/$asset_name" "$asset_path" && \
         download_file "$release_base/$asset_name.sha256" "$checksum_path"; then
        checksum_ok=0
        if command -v sha256sum >/dev/null 2>&1; then
            (cd "$TEMP_DIR" && sha256sum -c "$asset_name.sha256" >/dev/null) && checksum_ok=1
        elif command -v shasum >/dev/null 2>&1; then
            (cd "$TEMP_DIR" && shasum -a 256 -c "$asset_name.sha256" >/dev/null) && checksum_ok=1
        fi
        if [ "$checksum_ok" -eq 1 ]; then
            cp "$asset_path" "$NATIVE_EXE"
            chmod +x "$NATIVE_EXE"
            if validate_native "$NATIVE_EXE"; then
                NATIVE_READY=1
                echo "[OK] Installed SHA-256 verified native release compiler."
                break
            fi
        else
            echo "[!] Native release checksum verification failed; using source bootstrap if available." >&2
        fi
      fi
    done
fi

if [ "$NATIVE_READY" -eq 0 ] && [ -z "$SOURCE_ROOT" ] && [ -z "$RELEASE_TAG" ]; then
    echo "[*] No release tag selected; installing the current main development source."
fi

if [ -z "$SOURCE_ROOT" ] && { [ "$NATIVE_READY" -eq 0 ] || [ -n "$PYTHON_BIN" ]; }; then
    source_archive="$TEMP_DIR/rove-source.tar.gz"
    source_extract="$TEMP_DIR/source"
    mkdir -p "$source_extract"
    if [ -n "$RELEASE_TAG" ]; then
        source_url="https://github.com/$REPOSITORY/archive/refs/tags/$RELEASE_TAG.tar.gz"
    else
        source_url="https://github.com/$REPOSITORY/archive/refs/heads/main.tar.gz"
    fi
    echo "[*] Downloading Rove sources..."
    if download_file "$source_url" "$source_archive" && tar -xzf "$source_archive" -C "$source_extract"; then
        for candidate in "$source_extract"/*; do
            if [ -d "$candidate/src" ]; then
                SOURCE_ROOT="$candidate"
                break
            fi
        done
    else
        echo "[!] Source download failed; continuing only if the native core is already installed." >&2
    fi
fi

if [ -n "$SOURCE_ROOT" ]; then
    if [ -f "$SOURCE_ROOT/VERSION" ]; then
        EXPECTED_VERSION="$(tr -d '\r\n' < "$SOURCE_ROOT/VERSION")"
    fi
    echo "[*] Installing source and compiler support files..."
    cp -R "$SOURCE_ROOT/src/." "$SRC_DIR/"
    for legal_file in VERSION LICENSE; do
        if [ -f "$SOURCE_ROOT/$legal_file" ]; then
            cp "$SOURCE_ROOT/$legal_file" "$INSTALL_DIR/$legal_file"
        fi
    done
    if [ -d "$SOURCE_ROOT/compiler" ]; then
        cp -R "$SOURCE_ROOT/compiler/." "$COMPILER_DIR/"
    fi
    if [ -d "$SOURCE_ROOT/vscode-extension" ]; then
        mkdir -p "$EXTENSION_DIR"
        for extension_file in \
            package.json package-lock.json extension.js server_options.js rove_commands.js \
            language-configuration.json language-surface.json README.md CHANGELOG.md LICENSE
        do
            if [ -f "$SOURCE_ROOT/vscode-extension/$extension_file" ]; then
                cp "$SOURCE_ROOT/vscode-extension/$extension_file" "$EXTENSION_DIR/$extension_file"
            fi
        done
        for extension_directory in images snippets syntaxes; do
            if [ -d "$SOURCE_ROOT/vscode-extension/$extension_directory" ]; then
                mkdir -p "$EXTENSION_DIR/$extension_directory"
                cp -R "$SOURCE_ROOT/vscode-extension/$extension_directory/." \
                    "$EXTENSION_DIR/$extension_directory/"
            fi
        done
    fi
fi

if [ "$NATIVE_READY" -eq 0 ] && validate_native "$NATIVE_EXE"; then
    NATIVE_READY=1
    echo "[OK] Reusing installed native compiler."
fi

if [ "$NATIVE_READY" -eq 0 ]; then
    if [ -z "$PYTHON_BIN" ] || [ ! -f "$SRC_DIR/cli.py" ]; then
        echo "[!] No prebuilt rovec is available for this platform." >&2
        echo "    Python 3.10+ and a C++20 compiler are required for source bootstrap." >&2
        exit 1
    fi
    echo "[*] No matching prebuilt binary; bootstrapping native rovec from source..."
    (
        cd "$INSTALL_DIR"
        "$PYTHON_BIN" "$SRC_DIR/cli.py" self-host build -o "$NATIVE_EXE"
    )
    chmod +x "$NATIVE_EXE"
    if ! validate_native "$NATIVE_EXE"; then
        echo "[!] Bootstrapped native compiler failed validation." >&2
        exit 1
    fi
    NATIVE_READY=1
    echo "[OK] Native rovec bootstrap completed."
fi

for command_name in rove nyx; do
    wrapper="$BIN_DIR/$command_name"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'set -euo pipefail' \
        'wrapper_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"' \
        'install_dir="$(dirname -- "$wrapper_dir")"' \
        'native="$wrapper_dir/rovec"' \
        'python_cli="$install_dir/src/cli.py"' \
        'case "${1:-}" in' \
        '    check|compile|emit-cpp|version|--version|-v) exec "$native" "$@" ;;' \
        'esac' \
        'if command -v python3 >/dev/null 2>&1 && [ -f "$python_cli" ]; then' \
        '    exec python3 "$python_cli" "$@"' \
        'fi' \
        'if command -v python >/dev/null 2>&1 && [ -f "$python_cli" ]; then' \
        '    exec python "$python_cli" "$@"' \
        'fi' \
        'if [ "$#" -eq 0 ]; then exec "$native" --help; fi' \
        'echo "This command still uses the optional Python orchestration layer. Install Python 3.10+, or use rovec check/compile/emit-cpp." >&2' \
        'exit 2' > "$wrapper"
    chmod +x "$wrapper"
done

install_editor_extension() {
    if [ "$SKIP_EDITOR_INSTALL" = "1" ] || [ ! -d "$EXTENSION_DIR" ]; then
        return
    fi

    extension_runtime=0
    if command -v npm >/dev/null 2>&1; then
        if (cd "$EXTENSION_DIR" && npm ci --omit=dev --ignore-scripts >/dev/null 2>&1); then
            extension_runtime=1
        else
            echo "[!] npm could not install the Rove language-server client; syntax highlighting will still be installed." >&2
        fi
    else
        echo "[!] npm not found; installing Rove syntax highlighting without the language-server client." >&2
    fi

    editor_found=0
    sync_extension() {
        destination="$1"
        mkdir -p "$destination"
        cp -R "$EXTENSION_DIR/." "$destination/"
        editor_found=1
        echo "[OK] Installed Rove editor support at: $destination"
    }

    if command -v code >/dev/null 2>&1 || [ -d "$HOME/.vscode/extensions" ]; then
        sync_extension "$HOME/.vscode/extensions/rove-lang-support"
    fi
    if command -v code-insiders >/dev/null 2>&1 || [ -d "$HOME/.vscode-insiders/extensions" ]; then
        sync_extension "$HOME/.vscode-insiders/extensions/rove-lang-support"
    fi
    if command -v codium >/dev/null 2>&1 || [ -d "$HOME/.vscode-oss/extensions" ]; then
        sync_extension "$HOME/.vscode-oss/extensions/rove-lang-support"
    fi

    if [ "$editor_found" -eq 0 ]; then
        echo "[*] VS Code/VSCodium was not detected. Editor files remain at: $EXTENSION_DIR"
    elif [ "$extension_runtime" -eq 0 ]; then
        echo "[*] Rove highlighting is available; install Node.js/npm and rerun the installer to enable LSP features."
    fi
}

install_editor_extension

if command -v clang++ >/dev/null 2>&1 || command -v g++ >/dev/null 2>&1 || command -v c++ >/dev/null 2>&1; then
    echo "[OK] Host C++ compiler detected for '#target cpp'."
else
    echo "[!] No host C++20 compiler was found; 'rove run --target cpp' cannot link executables yet." >&2
    echo "    Arch: sudo pacman -S --needed base-devel" >&2
    echo "    Debian/Ubuntu: sudo apt install g++" >&2
    echo "    Then run: rove doctor" >&2
fi

if ! validate_native "$NATIVE_EXE"; then
    echo "[!] Installed native rovec failed final validation." >&2
    exit 1
fi

cp "$NATIVE_EXE" "$BIN_DIR/nyxc"
chmod +x "$BIN_DIR/rovec"

echo "[OK] Rove installed successfully at: $INSTALL_DIR"
echo "     Native core: rovec --help (legacy alias: nyxc)"
echo "     Unified CLI: rove --help (legacy alias: nyx)"
if [ "$SKIP_PATH_UPDATE" != "1" ]; then
    echo "Add this directory to PATH: $BIN_DIR"
fi
echo "==================================================================="
