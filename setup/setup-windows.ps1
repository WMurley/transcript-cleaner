# Transcript Cleaner setup for Windows. Started by "Setup Transcript Cleaner (Windows).cmd".
#
# Everything goes inside this folder: a private copy of uv (the tool that fetches Python), its own Python,
# the app's packages and the name model. Nothing is added to PATH or the registry, no admin rights are
# needed, and deleting this folder removes all of it. About 800 MB is downloaded, once.
# Safe to run again: finished steps are skipped.

# -NoPrompt and -NoShortcut are for unattended test runs (a test copy must not replace the real desktop shortcut).
param([switch]$NoPrompt, [switch]$NoShortcut)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # PowerShell's progress bar makes downloads many times slower
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$UvVersion = "0.12.23"   # pinned: a settled release, not the newest
$PythonVersion = "3.13"
$Lock = Join-Path $PSScriptRoot "..\requirements.lock"   # every package, the name model included, pinned to a checked file hash

$App = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $App ".tools"
$Log = Join-Path $App "setup.log"
$Py = Join-Path $App ".venv\Scripts\python.exe"
$step = "starting"

# uv keeps everything it fetches inside .tools and never touches PATH or the registry
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
$env:UV_CACHE_DIR = Join-Path $Tools "cache"
$env:UV_PYTHON_BIN_DIR = Join-Path $Tools "bin"
$env:UV_PYTHON_INSTALL_BIN = "0"
$env:UV_PYTHON_INSTALL_REGISTRY = "0"
$env:UV_MANAGED_PYTHON = "1"

function Say($text) { Write-Host $text; Add-Content -Path $Log -Value ("{0}  {1}" -f (Get-Date -Format s), $text) -Encoding UTF8 }
function Run($exe, [string[]]$arguments) {
    # uv and Python print progress on stderr; in Windows PowerShell 5.1 that must not count as a failure.
    # Success is judged by the exit code instead.
    Add-Content -Path $Log -Value ("> {0} {1}" -f $exe, ($arguments -join " ")) -Encoding UTF8
    $saved = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    # one encoding for the whole log (Tee-Object would switch to UTF-16 partway through in PowerShell 5.1)
    try { & $exe @arguments 2>&1 | ForEach-Object { $line = "$_"; Write-Host $line; Add-Content -Path $Log -Value $line -Encoding UTF8 }; $code = $LASTEXITCODE }
    finally { $ErrorActionPreference = $saved }
    if ($code -ne 0) { throw "$([IO.Path]::GetFileName($exe)) stopped with code $code" }
}
function Fetch($url, $out) {
    # curl.exe ships with Windows 10 (1803+) and 11. It's preferred: GitHub release downloads can refuse
    # PowerShell's own downloader (seen as 403 Forbidden), and curl is faster.
    $curl = Join-Path $env:SystemRoot "System32\curl.exe"
    if (Test-Path $curl) {
        Add-Content -Path $Log -Value "> curl $url" -Encoding UTF8
        $saved = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try { & $curl -fsSL --retry 3 --retry-delay 2 -o $out $url 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $Log -Encoding UTF8; $code = $LASTEXITCODE }
        finally { $ErrorActionPreference = $saved }
        if ($code -ne 0) { throw "couldn't download $([IO.Path]::GetFileName($out)) (curl code $code). Check the internet connection" }
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out
    }
}
function Works($exe, [string[]]$arguments) {
    $saved = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $exe @arguments 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) } finally { $ErrorActionPreference = $saved }
}

try {
    Set-Content -Path $Log -Value "Transcript Cleaner setup log (no transcripts or client details are ever written here)" -Encoding UTF8
    Write-Host ""
    Write-Host "  Transcript Cleaner setup" -ForegroundColor Cyan
    Write-Host "  Downloads about 800 MB once, into this folder only. It takes 5 to 15 minutes."
    Write-Host "  Apart from a shortcut on your desktop, nothing else on this computer is changed, and no admin rights are needed."
    Write-Host ""

    $step = "getting uv"
    $uv = Join-Path $Tools "uv.exe"
    if (-not (Test-Path $uv)) {
        $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "aarch64" } else { "x86_64" }
        $asset = "uv-$arch-pc-windows-msvc.zip"
        $base = "https://github.com/astral-sh/uv/releases/download/$UvVersion"
        New-Item -ItemType Directory -Force -Path $Tools | Out-Null
        $zip = Join-Path $Tools $asset
        Say "1 of 4  Downloading uv $UvVersion (about 20 MB)..."
        Fetch "$base/$asset" $zip
        Fetch "$base/$asset.sha256" "$zip.sha256"
        $expected = ((Get-Content -Raw "$zip.sha256").Trim() -split "\s+")[0].ToLower()
        Remove-Item "$zip.sha256" -Force
        $actual = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLower()
        if ($expected -ne $actual) { Remove-Item $zip -Force; throw "the uv download didn't match its published checksum, so it was deleted" }
        Expand-Archive -Path $zip -DestinationPath $Tools -Force
        Remove-Item $zip -Force
        $found = Get-ChildItem -Path $Tools -Recurse -Filter uv.exe | Select-Object -First 1
        if ($found.FullName -ne $uv) { Move-Item -Force $found.FullName $uv }
    } else { Say "1 of 4  uv is already here." }

    $step = "setting up Python"
    $ready = $false
    if (Test-Path $Py) { $ready = Works $Py @("-c", "import presidio_analyzer, spacy, webview; spacy.load('en_core_web_lg')") }
    if ($ready) {
        Say "2 and 3 of 4  Python and the checked packages are already installed."
    } else {
        if (-not (Test-Path $Py)) {
            Say "2 of 4  Getting Python $PythonVersion for this app..."
            Run $uv @("venv", (Join-Path $App ".venv"), "--python", $PythonVersion)
        } else { Say "2 of 4  Python is already here." }
        $step = "installing packages"
        Say "3 of 4  Installing the checked packages, including the 400 MB name model (the slow part)..."
        # --require-hashes: any file that doesn't match the hash in requirements.lock is refused
        Run $uv @("pip", "install", "--python", $Py, "--require-hashes", "-r", $Lock)
    }

    $step = "checking the install"
    Say "4 of 4  Checking everything works..."
    Run $Py @("-c", "import presidio_analyzer, spacy, webview; spacy.load('en_core_web_lg'); print('Name model and app window load.')")
    if (-not $NoShortcut) {
        Push-Location $App
        $saved = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try { $msg = & $Py -c "import app; print(app.make_shortcut())" 2>&1 | ForEach-Object { "$_" } } finally { Pop-Location; $ErrorActionPreference = $saved }
        Say ("Desktop shortcut: {0}" -f ($msg | Out-String).Trim())
    }

    Write-Host ""
    Write-Host "  All set. Open Transcript Cleaner from the shortcut on your desktop." -ForegroundColor Green
    Write-Host ""
    $open = if ($NoPrompt) { "n" } else { Read-Host "  Open it now? (Y/n)" }
    if ($open -notmatch "^[nN]") { Start-Process -FilePath "wscript.exe" -ArgumentList ('"{0}"' -f (Join-Path $App "Open Transcript Cleaner.vbs")) }
    exit 0
}
catch {
    Say ("Setup stopped while {0}: {1}" -f $step, $_.Exception.Message)
    Write-Host ""
    Write-Host "  Setup didn't finish (it stopped while $step)." -ForegroundColor Yellow
    Write-Host "  Nothing outside this folder was changed. Running setup again picks up where it stopped."
    Write-Host "  If it keeps stopping, give setup.log (in this folder) to your AI agent or whoever shared this app with you."
    Write-Host "  It has no transcripts or client details in it."
    Write-Host ""
    if (-not $NoPrompt) { Read-Host "  Press Enter to close" | Out-Null }
    exit 1
}
