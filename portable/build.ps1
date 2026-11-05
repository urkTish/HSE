# Builds the portable Windows edition (portable/README.md) into one folder:
#
#   HSE.exe                launcher (portable/launcher, Go)
#   runtime\pgsql\         PostgreSQL 16 (EDB Windows binaries: bin, lib, share only)
#   runtime\python\        CPython (uv-managed, relocatable) with the backend's locked dependencies
#   runtime\node\node.exe  Node.js
#   app\backend\           backend code and Alembic migrations
#   app\web\               Next.js standalone server (built with NEXT_OUTPUT=standalone)
#
# Run on Windows from the repository root, with uv, Node/npm and Go on PATH (see
# .github/workflows/portable-windows.yml). Third-party downloads are pinned and checksum-verified.
param(
    [string]$OutDir = "dist\HSE-Platform-Windows",
    [string]$WorkDir = "$env:RUNNER_TEMP\hse-portable-build",
    [string]$PgVersion = $env:PG_VERSION,       # e.g. 16.14-1 (EDB build)
    [string]$PgSha256 = $env:PG_SHA256,
    [string]$NodeVersion = $env:NODE_VERSION,   # e.g. 22.23.4
    [string]$NodeSha256 = $env:NODE_SHA256,     # of node-v<ver>-win-x64.zip (nodejs.org SHASUMS256.txt)
    [string]$PythonVersion = $env:PYTHON_VERSION,
    [int]$ApiPort = 54330,                      # baked into the web build's /api rewrite; HSE.exe default
    [string]$BundleVersion = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$Repo = (Resolve-Path ".").Path
if (-not (Test-Path (Join-Path $Repo "backend\alembic.ini"))) { throw "Run from the repository root." }
foreach ($v in "PgVersion", "PgSha256", "NodeVersion", "NodeSha256", "PythonVersion") {
    if (-not (Get-Variable $v -ValueOnly)) { throw "Missing -$v (or the matching environment variable)." }
}
if (-not $BundleVersion) {
    $BundleVersion = (Get-Date -Format "yyyy.MM.dd") + "-" + (git rev-parse --short HEAD).Trim()
}

function Step($msg) { Write-Host ""; Write-Host "==== $msg" -ForegroundColor Cyan }

function Get-Verified([string]$Url, [string]$Path, [string]$Sha256) {
    if (-not (Test-Path $Path)) {
        Write-Host "Downloading $Url"
        Invoke-WebRequest -Uri $Url -OutFile $Path -MaximumRetryCount 5 -RetryIntervalSec 10
    }
    $got = (Get-FileHash -Algorithm SHA256 $Path).Hash.ToLowerInvariant()
    if ($got -ne $Sha256.ToLowerInvariant()) {
        throw "Checksum mismatch for $Url`n  expected $Sha256`n  got      $got"
    }
    Write-Host ("sha256 ok: {0}  {1} ({2:N1} MB)" -f $got, (Split-Path $Path -Leaf), ((Get-Item $Path).Length / 1MB))
}

function Remove-IfExists([string[]]$Paths) {
    foreach ($p in $Paths) { if (Test-Path $p) { Remove-Item -Recurse -Force $p } }
}

function Get-DirSizeMB([string]$Path) {
    $sum = (Get-ChildItem -Recurse -File -Force $Path | Measure-Object -Property Length -Sum).Sum
    [math]::Round($sum / 1MB, 1)
}

Remove-IfExists $OutDir
New-Item -ItemType Directory -Force $OutDir, $WorkDir | Out-Null
$Out = (Resolve-Path $OutDir).Path
$Work = (Resolve-Path $WorkDir).Path
$Dl = Join-Path $Work "downloads"
New-Item -ItemType Directory -Force $Dl, "$Out\runtime", "$Out\app" | Out-Null

# ------------------------------------------------------------------ PostgreSQL 16
Step "PostgreSQL $PgVersion (EDB Windows x64 binaries)"
$pgZip = Join-Path $Dl "postgresql-$PgVersion-windows-x64-binaries.zip"
Get-Verified "https://get.enterprisedb.com/postgresql/postgresql-$PgVersion-windows-x64-binaries.zip" $pgZip $PgSha256
$pgTmp = Join-Path $Work "pg"
Remove-IfExists $pgTmp
New-Item -ItemType Directory $pgTmp | Out-Null
tar -xf $pgZip -C $pgTmp pgsql/bin pgsql/lib pgsql/share
$pgOut = "$Out\runtime\pgsql"
New-Item -ItemType Directory $pgOut | Out-Null
foreach ($d in "bin", "lib", "share") { Move-Item "$pgTmp\pgsql\$d" "$pgOut\$d" }
# Not needed to run a server: import/static libraries, debug symbols, StackBuilder, documentation.
Get-ChildItem -Recurse -File $pgOut -Include *.lib, *.a, *.pdb | Remove-Item -Force
Remove-IfExists "$pgOut\bin\stackbuilder.exe", "$pgOut\share\doc", "$pgOut\share\man"
# The EDB binaries need the Visual C++ runtime; ship it next to them (app-local) if the zip does not.
foreach ($dll in "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll") {
    if (-not (Test-Path "$pgOut\bin\$dll") -and (Test-Path "$env:SystemRoot\System32\$dll")) {
        Copy-Item "$env:SystemRoot\System32\$dll" "$pgOut\bin\$dll"
        Write-Host "added $dll (app-local Visual C++ runtime)"
    }
}
& "$pgOut\bin\postgres.exe" --version

# ------------------------------------------------------------------ Node.js
Step "Node.js $NodeVersion"
$nodeName = "node-v$NodeVersion-win-x64"
$nodeZip = Join-Path $Dl "$nodeName.zip"
Get-Verified "https://nodejs.org/dist/v$NodeVersion/$nodeName.zip" $nodeZip $NodeSha256
$nodeTmp = Join-Path $Work "node"
Remove-IfExists $nodeTmp
New-Item -ItemType Directory $nodeTmp | Out-Null
tar -xf $nodeZip -C $nodeTmp "$nodeName/node.exe" "$nodeName/LICENSE"
New-Item -ItemType Directory "$Out\runtime\node" | Out-Null
Move-Item "$nodeTmp\$nodeName\node.exe", "$nodeTmp\$nodeName\LICENSE" "$Out\runtime\node\"
& "$Out\runtime\node\node.exe" --version

# ------------------------------------------------------------------ Python + backend dependencies
Step "Python $PythonVersion (uv-managed CPython, checksums verified by uv) and the backend dependencies"
$pyTmp = Join-Path $Work "python"
Remove-IfExists $pyTmp
uv python install $PythonVersion --install-dir $pyTmp --no-bin --no-registry
$pyDir = Get-ChildItem $pyTmp -Directory | Where-Object { $_.Name -like "cpython-$PythonVersion-windows-x86_64*" } | Select-Object -First 1
if (-not $pyDir) { Get-ChildItem $pyTmp; throw "uv did not install CPython $PythonVersion" }
$pyOut = "$Out\runtime\python"
Copy-Item -Recurse $pyDir.FullName $pyOut
$py = "$pyOut\python.exe"
$req = Join-Path $Work "requirements.txt"
uv export --project backend --frozen --no-dev --no-emit-project --output-file $req | Out-Null
uv pip install --python $py --break-system-packages --link-mode copy --require-hashes -r $req
# Not needed at run time: headers and import libraries, Tcl/Tk and IDLE, the test suite, pip shims.
Remove-IfExists "$pyOut\include", "$pyOut\libs", "$pyOut\tcl", "$pyOut\Scripts", `
    "$pyOut\Lib\test", "$pyOut\Lib\idlelib", "$pyOut\Lib\tkinter", "$pyOut\Lib\turtledemo", `
    "$pyOut\Lib\ensurepip", "$pyOut\DLLs\_tkinter.pyd", "$pyOut\DLLs\tcl86t.dll", "$pyOut\DLLs\tk86t.dll"
& $py -c "import sys, fastapi, psycopg, sqlalchemy, uvicorn, alembic; print(sys.version); print('psycopg', psycopg.__version__, psycopg.pq.__impl__)"

# ------------------------------------------------------------------ backend code
Step "Backend code and migrations"
$beOut = "$Out\app\backend"
New-Item -ItemType Directory $beOut | Out-Null
Copy-Item -Recurse "backend\app", "backend\alembic" $beOut
Copy-Item "backend\alembic.ini", "backend\pyproject.toml" $beOut
Get-ChildItem -Recurse -Directory -Force $beOut -Filter "__pycache__" | Remove-Item -Recurse -Force

# Bytecode compiled once here (hash-checked, so the zip's file times do not matter) for a fast start.
Step "Compiling Python bytecode"
$PSNativeCommandUseErrorActionPreference = $false
& $py -m compileall -q -f -j 0 --invalidation-mode unchecked-hash "$pyOut\Lib" "$beOut\app" "$beOut\alembic" | Out-Null
Write-Host "compileall exit code $LASTEXITCODE (a few unparsable files inside third-party packages are expected)"
$PSNativeCommandUseErrorActionPreference = $true
& $py -c "import sys; sys.path.insert(0, r'$beOut'); import app.main; print('app.main imports OK')"

# ------------------------------------------------------------------ frontend (Next.js standalone)
Step "Frontend (Next.js standalone build, API at http://127.0.0.1:$ApiPort)"
Push-Location frontend
try {
    $env:NEXT_OUTPUT = "standalone"
    $env:BACKEND_URL = "http://127.0.0.1:$ApiPort"
    $env:NEXT_TELEMETRY_DISABLED = "1"
    npm ci --no-audit --no-fund
    npm run build
} finally {
    Remove-Item Env:NEXT_OUTPUT, Env:BACKEND_URL -ErrorAction SilentlyContinue
    Pop-Location
}
$standalone = "frontend\.next\standalone"
$server = Get-ChildItem -Recurse -File $standalone -Filter server.js |
    Where-Object { $_.FullName -notmatch "\\node_modules\\" } | Sort-Object { $_.FullName.Length } | Select-Object -First 1
if (-not $server) { throw "No server.js in $standalone (is output: standalone on?)" }
$webOut = "$Out\app\web"
Copy-Item -Recurse $server.Directory.FullName $webOut
# server.js may sit in a sub-folder when Next picks a wider tracing root; keep its node_modules.
if ($server.Directory.FullName -ne (Resolve-Path $standalone).Path -and (Test-Path "$standalone\node_modules") -and -not (Test-Path "$webOut\node_modules")) {
    Copy-Item -Recurse "$standalone\node_modules" "$webOut\node_modules"
}
New-Item -ItemType Directory -Force "$webOut\.next" | Out-Null
Copy-Item -Recurse "frontend\.next\static" "$webOut\.next\static"
if (Test-Path "frontend\public") { Copy-Item -Recurse "frontend\public" "$webOut\public" }
Remove-IfExists "$webOut\.env", "$webOut\.env.local"
$baked = Select-String -Path "$webOut\.next\routes-manifest.json" -Pattern "127.0.0.1:$ApiPort" -SimpleMatch -Quiet
if (-not $baked) { throw "The /api rewrite does not point at 127.0.0.1:$ApiPort" }

# ------------------------------------------------------------------ launcher and documents
Step "Launcher HSE.exe ($BundleVersion)"
Push-Location portable\launcher
try {
    $env:CGO_ENABLED = "0"
    go build -trimpath -ldflags "-s -w -X main.version=$BundleVersion" -o "$Out\HSE.exe" .
} finally { Pop-Location }
Copy-Item "portable\README.md" "$Out\READ ME FIRST.txt"
Copy-Item "portable\THIRD-PARTY-NOTICES.txt" "$Out\THIRD-PARTY-NOTICES.txt"
Set-Content -Path "$Out\runtime\VERSION.txt" -Value @(
    "HSE portable bundle $BundleVersion"
    "PostgreSQL $PgVersion (EDB binaries), Node.js $NodeVersion, CPython $PythonVersion"
)

# ------------------------------------------------------------------ report
Step "Bundle summary"
$longest = Get-ChildItem -Recurse -Force $Out | ForEach-Object { $_.FullName.Substring($Out.Length).Length } |
    Measure-Object -Maximum
Write-Host ("Longest path inside the bundle: {0} characters (Windows limit 260 including the folder it is unzipped to)" -f $longest.Maximum)
foreach ($d in "runtime\pgsql", "runtime\python", "runtime\node", "app\backend", "app\web") {
    Write-Host ("{0,-16} {1,8} MB" -f $d, (Get-DirSizeMB "$Out\$d"))
}
Write-Host ("{0,-16} {1,8} MB, {2} files" -f "total", (Get-DirSizeMB $Out), (Get-ChildItem -Recurse -File -Force $Out).Count)
