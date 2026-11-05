# Smoke test of a built portable bundle (run by .github/workflows/portable-windows.yml).
#
#  1. First start with --no-browser: initdb, migrations, demo seed, API, jobs, web server.
#  2. API health, login page, every listening port bound to 127.0.0.1 only.
#  3. Sign-in through the Next.js proxy, then Quality endpoints for ANIA-EXP (Construction) and
#     RUH-CCH (Logistics) answer 200.
#  4. HSE.exe --stop: the launcher exits, no bundled process is left, PostgreSQL shut down cleanly.
#  5. Second start on the same data folder: no re-seed, the same checks pass, stop again.
#  6. Hard kill of HSE.exe (what Windows does if cleanup on window close runs out of time): the
#     API, jobs and web server die with it; the next start recovers (stray database stopped,
#     crash recovery) and works.
param(
    [Parameter(Mandatory = $true)][string]$Bundle,
    [int]$FirstStartMinutes = 45
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$Bundle = (Resolve-Path $Bundle).Path
$Exe = Join-Path $Bundle "HSE.exe"
$Data = Join-Path $Bundle "data"
$Logs = Join-Path $Data "logs"
$Password = "Demo-Passw0rd!2026"
$ApiPort = 54330
$PgPort = 54329
$OutDir = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }

function Say($msg) { Write-Host "[smoke $(Get-Date -Format HH:mm:ss)] $msg" }

function Show-Logs {
    foreach ($f in Get-ChildItem -File $Logs -ErrorAction SilentlyContinue) {
        Write-Host "----- $($f.Name) (last 60 lines)"
        Get-Content $f.FullName -Tail 60
    }
}

function Fail($msg) {
    Write-Host "SMOKE TEST FAILED: $msg" -ForegroundColor Red
    foreach ($f in Get-ChildItem "$OutDir\launcher-*.out*" -ErrorAction SilentlyContinue) {
        Write-Host "----- $($f.Name)"; Get-Content $f.FullName
    }
    Show-Logs
    exit 1
}

function Start-Launcher([string]$Tag) {
    $out = Join-Path $OutDir "launcher-$Tag.out"
    $p = Start-Process -FilePath $Exe -ArgumentList "--no-browser" -WorkingDirectory $OutDir -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError "$out.err" -WindowStyle Hidden
    Say "started HSE.exe ($Tag), pid $($p.Id)"
    return @{ Process = $p; Out = $out }
}

function Wait-Running($L, [int]$Minutes) {
    $deadline = (Get-Date).AddMinutes($Minutes)
    $stateFile = Join-Path $Data "run\state.json"
    while ((Get-Date) -lt $deadline) {
        if ($L.Process.HasExited) { Fail "HSE.exe exited early with code $($L.Process.ExitCode)" }
        if (Test-Path $stateFile) {
            try { $st = Get-Content -Raw $stateFile | ConvertFrom-Json } catch { $st = $null }
            if ($st -and $st.status -eq "running" -and $st.pid -eq $L.Process.Id) { return $st.url }
        }
        Start-Sleep -Seconds 5
    }
    Fail "the platform was not running after $Minutes minutes"
}

function Get-Status([string]$Url, $Session = $null) {
    $args_ = @{ Uri = $Url; SkipHttpErrorCheck = $true; TimeoutSec = 120; MaximumRedirection = 0 }
    if ($Session) { $args_.WebSession = $Session }
    $r = Invoke-WebRequest @args_
    return $r
}

function Assert-200([string]$Url, $Session = $null) {
    $r = Get-Status $Url $Session
    if ($r.StatusCode -ne 200) { Fail "GET $Url answered $($r.StatusCode): $($r.Content)" }
    Say "200  GET $Url"
    return $r
}

function Test-QualityAs([string]$Web, [string]$Email, [string]$Project) {
    $s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $body = @{ email = $Email; password = $Password } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$Web/api/v1/auth/login" -Method Post -ContentType "application/json" `
        -Body $body -WebSession $s -SkipHttpErrorCheck -TimeoutSec 120
    if ($r.StatusCode -ne 200) { Fail "login $Email via the Next proxy answered $($r.StatusCode): $($r.Content)" }
    Say "200  POST $Web/api/v1/auth/login as $Email"
    $page = (Assert-200 "$Web/api/v1/projects?q=$Project" $s).Content | ConvertFrom-Json
    $p = @($page.items | Where-Object { $_.code -eq $Project })
    if ($p.Count -ne 1) { Fail "project $Project not visible to $Email" }
    $id = $p[0].id
    $home_ = (Assert-200 "$Web/api/v1/projects/$id/quality/home" $s).Content
    Say "     quality/home $Project`: $($home_.Substring(0, [Math]::Min(160, $home_.Length)))"
    $ncrs = (Assert-200 "$Web/api/v1/projects/$id/quality/ncrs" $s).Content | ConvertFrom-Json
    Say "     quality/ncrs $Project`: $($ncrs.total) NCRs"
}

function Test-Running([string]$Web) {
    $h = (Assert-200 "http://127.0.0.1:$ApiPort/api/v1/health").Content | ConvertFrom-Json
    if ($h.database -ne "ok") { Fail "API health reports database=$($h.database)" }
    Say "     API version $($h.version), database $($h.database)"
    Assert-200 "$Web/en/login" | Out-Null
    $webPort = ([uri]$Web).Port
    $listen = Get-NetTCPConnection -State Listen -LocalPort $PgPort, $ApiPort, $webPort -ErrorAction SilentlyContinue
    if (-not $listen) { Fail "no listening sockets found on $PgPort/$ApiPort/$webPort" }
    foreach ($c in $listen) {
        Say "     listening $($c.LocalAddress):$($c.LocalPort) (pid $($c.OwningProcess))"
        if ($c.LocalAddress -ne "127.0.0.1") { Fail "port $($c.LocalPort) is bound to $($c.LocalAddress), not 127.0.0.1" }
    }
    foreach ($port in $PgPort, $ApiPort, $webPort) {
        if (-not ($listen | Where-Object { $_.LocalPort -eq $port })) { Fail "nothing listens on 127.0.0.1:$port" }
    }
    Test-QualityAs $Web "hatem.shehri@example.com" "ANIA-EXP"
    Test-QualityAs $Web "reem.mutairi@example.com" "RUH-CCH"
}

function Get-BundleProcesses {
    @(Get-Process | Where-Object { $_.Path -and $_.Path.StartsWith($Bundle, [StringComparison]::OrdinalIgnoreCase) })
}

function Stop-Launcher($L) {
    Say "HSE.exe --stop"
    & $Exe --stop
    if ($LASTEXITCODE -ne 0) { Fail "HSE.exe --stop exited with $LASTEXITCODE" }
    if (-not $L.Process.WaitForExit(120000)) { Fail "the launcher did not exit within 2 minutes" }
    Say "launcher exited with code $($L.Process.ExitCode)"
    if ($L.Process.ExitCode -ne 0) { Fail "the launcher exit code was $($L.Process.ExitCode)" }
    $left = @()
    for ($i = 0; $i -lt 30; $i++) {
        $left = @(Get-BundleProcesses)
        if ($left.Count -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    if ($left.Count -ne 0) {
        $left | Format-Table Id, ProcessName, Path -AutoSize | Out-String | Write-Host
        Fail "$($left.Count) bundled process(es) still running after stop"
    }
    Say "no bundled process left (postgres, python, node)"
    if (Test-Path (Join-Path $Data "pgdata\postmaster.pid")) { Fail "postmaster.pid still present: PostgreSQL did not stop" }
    $pgLog = Get-Content -Raw (Join-Path $Logs "postgres.log")
    if ($pgLog -notmatch "database system is shut down\s*$") { Fail "postgres.log does not end with a clean shutdown" }
    Say "PostgreSQL shut down cleanly"
    foreach ($port in $PgPort, $ApiPort) {
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { Fail "port $port still in use after stop" }
    }
}

if (Test-Path $Data) { Fail "the bundle already has a data folder; run the smoke test on a clean copy" }
if ($Bundle -notmatch " ") { Say "warning: the bundle path has no space in it" }
Say "bundle: $Bundle"

# ---- first start
$t0 = Get-Date
$L1 = Start-Launcher "first"
$web = Wait-Running $L1 $FirstStartMinutes
Say ("first start ready in {0:N0} s at {1}" -f ((Get-Date) - $t0).TotalSeconds, $web)
Test-Running $web
foreach ($f in "config\secrets.env", "config\seeded", "pgdata\PG_VERSION", "logs\launcher.log", "logs\seed.log") {
    if (-not (Test-Path (Join-Path $Data $f))) { Fail "data\$f missing after the first start" }
}
$secrets = Get-Content (Join-Path $Data "config\secrets.env") | Where-Object { $_ -match "^[A-Z_]+=" }
if ($secrets.Count -lt 5 -or ($secrets -match "dev-only")) { Fail "secrets.env is incomplete or holds dev defaults" }
Say "secrets generated: $(($secrets | ForEach-Object { ($_ -split '=')[0] }) -join ', ')"
$seedStamp = (Get-Item (Join-Path $Logs "seed.log")).LastWriteTimeUtc
$seededMarker = Get-Content -Raw (Join-Path $Data "config\seeded")
Stop-Launcher $L1

# ---- second start: same data folder, no re-seed
$t1 = Get-Date
$L2 = Start-Launcher "second"
$web2 = Wait-Running $L2 15
Say ("second start ready in {0:N0} s at {1}" -f ((Get-Date) - $t1).TotalSeconds, $web2)
$out2 = Get-Content -Raw $L2.Out
if ($out2 -notmatch "Demo data already loaded") { Fail "the second start did not report skipping the seed" }
if ((Get-Item (Join-Path $Logs "seed.log")).LastWriteTimeUtc -ne $seedStamp) { Fail "seed.log changed: the demo data was loaded again" }
if ((Get-Content -Raw (Join-Path $Data "config\seeded")) -ne $seededMarker) { Fail "the seed marker changed" }
Say "second start reused the data folder (no re-seed)"
Test-Running $web2
Stop-Launcher $L2

# ---- hard kill, then a start that must recover
$L3 = Start-Launcher "killed"
Wait-Running $L3 15 | Out-Null
Say "Stop-Process -Force on HSE.exe (no clean-up by the launcher)"
Stop-Process -Id $L3.Process.Id -Force
$L3.Process.WaitForExit(30000) | Out-Null
$left = @()
for ($i = 0; $i -lt 30; $i++) {
    $left = @(Get-BundleProcesses | Where-Object { $_.ProcessName -ne "postgres" })
    if ($left.Count -eq 0) { break }
    Start-Sleep -Seconds 1
}
if ($left.Count -ne 0) {
    $left | Format-Table Id, ProcessName, Path -AutoSize | Out-String | Write-Host
    Fail "API / jobs / web server processes survived a hard kill of the launcher"
}
$pgLeft = @(Get-BundleProcesses).Count
Say "after the hard kill: API, jobs and web server gone; $pgLeft postgres process(es) left"
$t2 = Get-Date
$L4 = Start-Launcher "after-kill"
$web4 = Wait-Running $L4 15
Say ("start after the hard kill ready in {0:N0} s" -f ((Get-Date) - $t2).TotalSeconds)
Test-Running $web4
Stop-Launcher $L4

Write-Host "----- launcher output, first start"; Get-Content $L1.Out
Write-Host "----- launcher output, second start"; Get-Content $L2.Out
Write-Host "----- launcher output, start after the hard kill"; Get-Content $L4.Out
Write-Host "----- data\logs\launcher.log"; Get-Content (Join-Path $Logs "launcher.log")
Say "SMOKE TEST PASSED"
