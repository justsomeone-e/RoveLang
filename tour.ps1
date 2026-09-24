# Tour of Rove PowerShell Launcher
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$python = (Get-Command py, python, python3 -ErrorAction SilentlyContinue | Select-Object -First 1).Source

if (-not $python -and $env:LOCALAPPDATA) {
    foreach ($ver in @("Python312", "Python311", "Python310")) {
        $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\$ver\python.exe"
        if (Test-Path -LiteralPath $candidate) {
            $python = $candidate
            break
        }
    }
}

if (-not $python) {
    Write-Error "Python 3.10+ is required to launch Tour of Rove. Please install Python or add it to PATH."
    exit 1
}

$tourScript = Join-Path $PSScriptRoot "tour\tour.py"
if ($args.Count -eq 0) {
    & $python $tourScript core
} else {
    & $python $tourScript @args
}
exit $LASTEXITCODE
