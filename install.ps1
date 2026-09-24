# Rove native-first Windows installer
$ErrorActionPreference = "Stop"

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "Installing Rove native toolchain..." -ForegroundColor Cyan
Write-Host "===================================================================" -ForegroundColor Cyan

$InstallDir = if ($env:ROVE_INSTALL_DIR) {
    [System.IO.Path]::GetFullPath($env:ROVE_INSTALL_DIR)
} elseif ($env:NYX_INSTALL_DIR) {
    [System.IO.Path]::GetFullPath($env:NYX_INSTALL_DIR)
} else {
    Join-Path $HOME ".rove"
}
$BinDir = Join-Path $InstallDir "bin"
$SrcDir = Join-Path $InstallDir "src"
$CompilerDir = Join-Path $InstallDir "compiler"
$ExtensionDir = Join-Path $InstallDir "vscode-extension"
$NativeExe = Join-Path $BinDir "rovec.exe"
$Repository = "justsomeone-e/RoveLang"
$ReleaseTag = if ($env:ROVE_RELEASE_TAG) { $env:ROVE_RELEASE_TAG } else { $env:NYX_RELEASE_TAG }
$NativeCompilerPath = if ($env:ROVE_NATIVE_COMPILER_PATH) { $env:ROVE_NATIVE_COMPILER_PATH } else { $env:NYX_NATIVE_COMPILER_PATH }
$SkipPathUpdate = if ($env:ROVE_SKIP_PATH_UPDATE) { $env:ROVE_SKIP_PATH_UPDATE } else { $env:NYX_SKIP_PATH_UPDATE }
$SkipEditorInstall = if ($env:ROVE_SKIP_EDITOR_INSTALL) { $env:ROVE_SKIP_EDITOR_INSTALL } else { $env:NYX_SKIP_EDITOR_INSTALL }
$ExpectedVersion = $null
if ($PSScriptRoot -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot "VERSION") -PathType Leaf)) {
    $ExpectedVersion = (Get-Content -LiteralPath (Join-Path $PSScriptRoot "VERSION") -Raw).Trim()
}

function Find-RovePython {
    foreach ($name in @("python", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $commandPath = @($command.Path, $command.Definition, $command.Source) |
                Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
                Select-Object -First 1
            if (-not $commandPath) { continue }
            try {
                & $commandPath -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
                if ($LASTEXITCODE -eq 0) { return $commandPath }
            } catch {
                continue
            }
        }
    }
    return $null
}

function Test-RoveNativeCompiler([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $versionOutput = (& $Path --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or (-not $versionOutput.StartsWith("rovec ") -and -not $versionOutput.StartsWith("nyxc "))) { return $false }
        if ($ExpectedVersion) {
            return $versionOutput.StartsWith("rovec $ExpectedVersion ") -or $versionOutput.StartsWith("nyxc $ExpectedVersion ")
        }
        return $true
    } catch {
        return $false
    }
}

function Get-RoveRelease {
    try {
        $headers = @{
            Accept = "application/vnd.github+json"
            "X-GitHub-Api-Version" = "2022-11-28"
        }
        if ($ReleaseTag) {
            $tag = [uri]::EscapeDataString($ReleaseTag)
            return Invoke-RestMethod -Uri "https://api.github.com/repos/$Repository/releases/tags/$tag" -Headers $headers
        }
        return $null
    } catch {
        Write-Host "[!] Release metadata unavailable; source bootstrap remains available." -ForegroundColor Yellow
        return $null
    }
}

New-Item -ItemType Directory -Path $BinDir, $SrcDir, $CompilerDir -Force | Out-Null

$CurrentRoot = $PSScriptRoot
$HasLocalSource = $CurrentRoot -and (Test-Path -LiteralPath (Join-Path $CurrentRoot "src") -PathType Container)
$Release = if ($HasLocalSource -or -not $ReleaseTag) { $null } else { Get-RoveRelease }
$SourceRoot = if ($HasLocalSource) { $CurrentRoot } else { $null }
$TempRoot = $null

try {
    if (-not $SourceRoot) {
        $TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("rove_install_" + [guid]::NewGuid().ToString("N"))
        $TempArchive = Join-Path $TempRoot "rove-source.zip"
        $TempExtract = Join-Path $TempRoot "source"
        New-Item -ItemType Directory -Path $TempExtract -Force | Out-Null
        $SourceUrl = if ($Release -and $Release.zipball_url) {
            [string]$Release.zipball_url
        } else {
            "https://github.com/$Repository/archive/refs/heads/main.zip"
        }
        try {
            Write-Host "[*] Downloading Rove sources..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri $SourceUrl -OutFile $TempArchive -UseBasicParsing
            Expand-Archive -LiteralPath $TempArchive -DestinationPath $TempExtract -Force
            $SourceRoot = Get-ChildItem -LiteralPath $TempExtract -Directory |
                Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "src") -PathType Container } |
                Select-Object -First 1 -ExpandProperty FullName
            if (-not $SourceRoot) {
                throw "Downloaded archive did not contain a Rove source root with src/."
            }
        } catch {
            Write-Host "[!] Source download or extraction failed: $($_.Exception.Message)" -ForegroundColor Yellow
            Write-Host "[!] Native core installation can still continue from a release binary." -ForegroundColor Yellow
        }
    }

    if ($SourceRoot) {
        $sourceVersionPath = Join-Path $SourceRoot "VERSION"
        if (Test-Path -LiteralPath $sourceVersionPath -PathType Leaf) {
            $ExpectedVersion = (Get-Content -LiteralPath $sourceVersionPath -Raw).Trim()
        }
        Write-Host "[*] Installing source and compiler support files..." -ForegroundColor Cyan
        Copy-Item -Path (Join-Path $SourceRoot "src\*") -Destination $SrcDir -Recurse -Force
        foreach ($legalFileName in @("VERSION", "LICENSE")) {
            $legalFile = Join-Path $SourceRoot $legalFileName
            if (Test-Path -LiteralPath $legalFile -PathType Leaf) {
                Copy-Item -LiteralPath $legalFile -Destination (Join-Path $InstallDir $legalFileName) -Force
            }
        }
        if (Test-Path -LiteralPath (Join-Path $SourceRoot "compiler") -PathType Container) {
            Copy-Item -Path (Join-Path $SourceRoot "compiler\*") -Destination $CompilerDir -Recurse -Force
        }
        if (Test-Path -LiteralPath (Join-Path $SourceRoot "vscode-extension") -PathType Container) {
            New-Item -ItemType Directory -Path $ExtensionDir -Force | Out-Null
            $ExtensionSource = Join-Path $SourceRoot "vscode-extension"
            foreach ($fileName in @(
                "package.json", "package-lock.json", "extension.js", "server_options.js",
                "rove_commands.js", "language-configuration.json", "language-surface.json",
                "README.md", "CHANGELOG.md", "LICENSE"
            )) {
                $sourceFile = Join-Path $ExtensionSource $fileName
                if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
                    Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $ExtensionDir $fileName) -Force
                }
            }
            foreach ($directoryName in @("images", "snippets", "syntaxes")) {
                $sourceDirectory = Join-Path $ExtensionSource $directoryName
                if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
                    $destinationDirectory = Join-Path $ExtensionDir $directoryName
                    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
                    Copy-Item -Path (Join-Path $sourceDirectory "*") -Destination $destinationDirectory -Recurse -Force
                }
            }
        }
    }

    $NativeInstalled = $false
    if ($NativeCompilerPath) {
        $OverridePath = [System.IO.Path]::GetFullPath($NativeCompilerPath)
        if (-not (Test-RoveNativeCompiler $OverridePath)) {
            throw "ROVE_NATIVE_COMPILER_PATH does not point to a working rovec executable: $OverridePath"
        }
        Copy-Item -LiteralPath $OverridePath -Destination $NativeExe -Force
        $NativeInstalled = $true
        Write-Host "[OK] Installed native compiler from ROVE_NATIVE_COMPILER_PATH." -ForegroundColor Green
    }

    if (-not $NativeInstalled -and $HasLocalSource) {
        foreach ($candidate in @(
            (Join-Path $CurrentRoot "build\self_host\rovec.exe"),
            (Join-Path $CurrentRoot "build\self_host\nyxc.exe"),
            (Join-Path $CurrentRoot "bin\rovec.exe"),
            (Join-Path $CurrentRoot "bin\nyxc.exe")
        )) {
            if (Test-RoveNativeCompiler $candidate) {
                Copy-Item -LiteralPath $candidate -Destination $NativeExe -Force
                $NativeInstalled = $true
                Write-Host "[OK] Installed existing local native compiler." -ForegroundColor Green
                break
            }
        }
    }

    if (-not $NativeInstalled -and $Release) {
        $runtimeArchitecture = [string][System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
        if (-not $runtimeArchitecture) {
            $runtimeArchitecture = [string]$env:PROCESSOR_ARCHITECTURE
        }
        $architecture = $runtimeArchitecture.ToLowerInvariant()
        $assetArchitecture = switch ($architecture) {
            { $_ -in @("x64", "amd64") } { "x86_64"; break }
            "arm64" { "arm64" }
            default { $null }
        }
        if ($assetArchitecture) {
            $assetNames = @(
                "rovec-windows-$assetArchitecture.exe",
                "nyxc-windows-$assetArchitecture.exe"
            )
            $asset = $Release.assets | Where-Object { $_.name -in $assetNames } |
                Sort-Object { [Array]::IndexOf($assetNames, $_.name) } | Select-Object -First 1
            if ($asset) {
                $assetName = [string]$asset.name
                $TempNative = Join-Path $TempRoot $assetName
                Write-Host "[*] Downloading native compiler $assetName..." -ForegroundColor Cyan
                Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $TempNative -UseBasicParsing
                if ($asset.digest -and ([string]$asset.digest).StartsWith("sha256:")) {
                    $expected = ([string]$asset.digest).Substring(7).ToLowerInvariant()
                    $actual = (Get-FileHash -LiteralPath $TempNative -Algorithm SHA256).Hash.ToLowerInvariant()
                    if ($actual -ne $expected) { throw "Native compiler SHA-256 verification failed." }
                }
                Copy-Item -LiteralPath $TempNative -Destination $NativeExe -Force
                $NativeInstalled = Test-RoveNativeCompiler $NativeExe
                if ($NativeInstalled) {
                    Write-Host "[OK] Installed verified native release compiler." -ForegroundColor Green
                }
            }
        }
    }

    $PythonExe = Find-RovePython
    $SrcCli = Join-Path $SrcDir "cli.py"
    if (-not $NativeInstalled -and (Test-RoveNativeCompiler $NativeExe)) {
        $NativeInstalled = $true
        Write-Host "[OK] Reusing installed native compiler." -ForegroundColor Green
    }
    if (-not $NativeInstalled) {
        if (-not $PythonExe -or -not (Test-Path -LiteralPath $SrcCli -PathType Leaf)) {
            throw "No prebuilt rovec is available for this platform. Python 3.10+ and a C++20 compiler are required for the source-bootstrap fallback."
        }
        Write-Host "[*] No matching prebuilt binary; bootstrapping native rovec from source..." -ForegroundColor Cyan
        Push-Location $InstallDir
        try {
            & $PythonExe $SrcCli self-host build -o $NativeExe
            if ($LASTEXITCODE -ne 0) { throw "Native compiler source bootstrap failed." }
        } finally {
            Pop-Location
        }
        $NativeInstalled = Test-RoveNativeCompiler $NativeExe
        if (-not $NativeInstalled) { throw "Bootstrapped native compiler failed validation." }
        Write-Host "[OK] Native rovec bootstrap completed." -ForegroundColor Green
    }

    $NativeLiteral = $NativeExe.Replace("'", "''")
    $CliLiteral = $SrcCli.Replace("'", "''")
    $PythonLiteral = if ($PythonExe) { $PythonExe.Replace("'", "''") } else { "" }
    $Ps1Content = @'
$native = '__ROVE_NATIVE__'
$pythonCli = '__ROVE_CLI__'
$preferredPython = '__ROVE_PYTHON__'
$nativeCommands = @('check', 'compile', 'emit-cpp', 'version', '--version', '-v')
if ($args.Count -gt 0 -and $nativeCommands -contains $args[0]) {
    & $native @args
    exit $LASTEXITCODE
}
if ($preferredPython -and (Test-Path -LiteralPath $preferredPython -PathType Leaf) -and (Test-Path -LiteralPath $pythonCli -PathType Leaf)) {
    & $preferredPython $pythonCli @args
    exit $LASTEXITCODE
}
$python = Get-Command python, python3 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($python -and (Test-Path -LiteralPath $pythonCli -PathType Leaf)) {
    & $python.Source $pythonCli @args
    exit $LASTEXITCODE
}
if ($args.Count -eq 0) {
    & $native --help
    exit $LASTEXITCODE
}
Write-Error "This command still uses the optional Python orchestration layer. Install Python 3.10+, or use rovec check/compile/emit-cpp."
exit 2
'@
    $Ps1Content = $Ps1Content.Replace("__ROVE_NATIVE__", $NativeLiteral).Replace("__ROVE_CLI__", $CliLiteral).Replace("__ROVE_PYTHON__", $PythonLiteral)
    foreach ($name in @("rove.ps1", "nyx.ps1")) {
        Set-Content -LiteralPath (Join-Path $BinDir $name) -Value $Ps1Content -Encoding UTF8
    }

    $BatchNative = $NativeExe.Replace("%", "%%")
    $BatchCli = $SrcCli.Replace("%", "%%")
    $BatchPython = if ($PythonExe) { $PythonExe.Replace("%", "%%") } else { "" }
    $BatContent = @"
@echo off
setlocal
set "ROVE_NATIVE=$BatchNative"
set "ROVE_PYCLI=$BatchCli"
set "ROVE_PYTHON=$BatchPython"
if "%~1"=="check" goto rove_native
if "%~1"=="compile" goto rove_native
if "%~1"=="emit-cpp" goto rove_native
if "%~1"=="version" goto rove_native
if "%~1"=="--version" goto rove_native
if "%~1"=="-v" goto rove_native
if exist "%ROVE_PYTHON%" (
    "%ROVE_PYTHON%" "%ROVE_PYCLI%" %*
    exit /b %errorlevel%
)
where python >nul 2>nul
if not errorlevel 1 (
    python "%ROVE_PYCLI%" %*
    exit /b %errorlevel%
)
where python3 >nul 2>nul
if not errorlevel 1 (
    python3 "%ROVE_PYCLI%" %*
    exit /b %errorlevel%
)
if "%~1"=="" (
    "%ROVE_NATIVE%" --help
    exit /b %errorlevel%
)
echo This command still uses the optional Python orchestration layer. Install Python 3.10+, or use rovec check/compile/emit-cpp. 1>&2
exit /b 2
:rove_native
"%ROVE_NATIVE%" %*
exit /b %errorlevel%
"@
    foreach ($name in @("rove.bat", "rove.cmd", "nyx.bat", "nyx.cmd")) {
        Set-Content -LiteralPath (Join-Path $BinDir $name) -Value $BatContent -Encoding ASCII
    }

    $ShContent = @'
#!/usr/bin/env bash
set -euo pipefail
wrapper_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
install_dir="$(dirname -- "$wrapper_dir")"
native="$wrapper_dir/rovec.exe"
python_cli="$install_dir/src/cli.py"
case "${1:-}" in
    check|compile|emit-cpp|version|--version|-v) exec "$native" "$@" ;;
esac
if command -v python3 >/dev/null 2>&1 && [ -f "$python_cli" ]; then
    exec python3 "$python_cli" "$@"
fi
if command -v python >/dev/null 2>&1 && [ -f "$python_cli" ]; then
    exec python "$python_cli" "$@"
fi
if [ "$#" -eq 0 ]; then
    exec "$native" --help
fi
echo "This command still uses the optional Python orchestration layer. Install Python 3.10+, or use rovec check/compile/emit-cpp." >&2
exit 2
'@
    Set-Content -LiteralPath (Join-Path $BinDir "rove") -Value $ShContent -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $BinDir "nyx") -Value $ShContent -Encoding ASCII

    if ($SkipPathUpdate -ne "1") {
        $UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
        if (-not $UserPath) { $UserPath = "" }
        $PathEntries = @($UserPath -split ";" | Where-Object {
            $_ -and -not $_.Equals($BinDir, [System.StringComparison]::OrdinalIgnoreCase)
        })
        $UpdatedPath = (@($BinDir) + $PathEntries) -join ";"
        if ($UpdatedPath -ne $UserPath) {
            [Environment]::SetEnvironmentVariable("Path", $UpdatedPath, "User")
            Write-Host "[OK] Prioritized $BinDir in User PATH." -ForegroundColor Green
        }
        $ProcessPathEntries = @($env:Path -split ";" | Where-Object {
            $_ -and -not $_.Equals($BinDir, [System.StringComparison]::OrdinalIgnoreCase)
        })
        $env:Path = (@($BinDir) + $ProcessPathEntries) -join ";"
    } else {
        Write-Host "[*] PATH update skipped (ROVE_SKIP_PATH_UPDATE=1)." -ForegroundColor Yellow
    }

    $VsCodeExtDir = Join-Path $HOME ".vscode\extensions\rove-lang-support"
    if ($SkipEditorInstall -ne "1" -and (Test-Path -LiteralPath $ExtensionDir -PathType Container)) {
        # Prefer npm.cmd or npm.exe over npm.ps1 to avoid PowerShell script execution policy restrictions
        $NpmCandidate = Get-Command "npm.cmd", "npm.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $NpmCandidate) {
            $NpmCandidate = Get-Command "npm" -ErrorAction SilentlyContinue
        }
        $NpmPath = if ($NpmCandidate) {
            @($NpmCandidate.Path, $NpmCandidate.Source, $NpmCandidate.Definition) |
                Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
                Select-Object -First 1
        } else {
            $null
        }
        if ($NpmPath) {
            Push-Location $ExtensionDir
            try {
                if ([System.IO.Path]::GetExtension($NpmPath) -ieq ".ps1") {
                    cmd.exe /c npm ci --omit=dev --ignore-scripts | Out-Null
                } else {
                    & $NpmPath ci --omit=dev --ignore-scripts | Out-Null
                }
                if ($LASTEXITCODE -eq 0) {
                    New-Item -ItemType Directory -Path $VsCodeExtDir -Force | Out-Null
                    Copy-Item -Path (Join-Path $ExtensionDir "*") -Destination $VsCodeExtDir -Recurse -Force
                    Write-Host "[OK] Synced Rove VS Code extension to $VsCodeExtDir" -ForegroundColor Green
                } else {
                    Write-Host "[!] npm ci failed; VS Code extension installation skipped." -ForegroundColor Yellow
                }
            } catch {
                Write-Host "[!] VS Code extension installation skipped ($($_.Exception.Message))." -ForegroundColor Yellow
            } finally {
                Pop-Location
            }
        } else {
            Write-Host "[!] npm not found; VS Code extension installation skipped." -ForegroundColor Yellow
        }
    }

    if (-not (Test-RoveNativeCompiler $NativeExe)) { throw "Installed native compiler failed final validation." }
    Copy-Item -LiteralPath $NativeExe -Destination (Join-Path $BinDir "nyxc.exe") -Force
    Write-Host "[OK] Native compiler validation passed." -ForegroundColor Green
} finally {
    if ($TempRoot -and (Test-Path -LiteralPath $TempRoot)) {
        $ResolvedTemp = [System.IO.Path]::GetFullPath($TempRoot)
        $TempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
        if ($ResolvedTemp.StartsWith($TempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $ResolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Write-Host "===================================================================" -ForegroundColor Cyan
Write-Host "[OK] Rove installed successfully at $InstallDir" -ForegroundColor Green
Write-Host "     Native core: rovec --help (legacy alias: nyxc)" -ForegroundColor Green
Write-Host "     Unified CLI: rove --help (legacy alias: nyx)" -ForegroundColor Green
Write-Host "===================================================================" -ForegroundColor Cyan
