# Download a release from GitHub onto a Windows workstation, ready to send on
# with WinSCP.
#
#   powershell -ExecutionPolicy Bypass -File fetch-release.ps1 -Tag 20260821-62ad749
#
# This is the middle hop. The deployment host cannot reach GitHub, so the
# artifact is downloaded here and pushed up with WinSCP; the host only ever runs
# load-images.sh. Use the shell version (fetch-release.sh) instead when the host
# itself has GitHub access.
#
# Re-running is safe and is the way to recover a failed download: any file whose
# hash already matches is skipped, so only what is missing or corrupt is fetched
# again.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [string]$Repo = "surya2478/ai-stlc-platform",
    [string]$OutDir = "",
    [int]$Retries = 4
)

$ErrorActionPreference = "Stop"

# Corporate proxies frequently reject the SChannel default in Windows
# PowerShell 5.1, which surfaces as "could not create SSL/TLS secure channel"
# rather than as anything about protocol versions.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Invoke-WebRequest renders a progress bar per chunk, which on a 400 MB file
# costs far more time than the transfer itself.
$ProgressPreference = "SilentlyContinue"

if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path (Get-Location) $Tag }
$base = "https://github.com/$Repo/releases/download/$Tag"

if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
Write-Host "==> $Tag"
Write-Host "==> into $OutDir"

function Get-Asset {
    param([string]$Name, [string]$ExpectedHash)

    $dest = Join-Path $OutDir $Name

    if ((Test-Path $dest) -and $ExpectedHash) {
        $have = (Get-FileHash -Path $dest -Algorithm SHA256).Hash
        if ($have -eq $ExpectedHash) {
            Write-Host ("    skip     {0} (already verified)" -f $Name)
            return $true
        }
    }

    for ($i = 1; $i -le $Retries; $i++) {
        try {
            Invoke-WebRequest -Uri "$base/$Name" -OutFile $dest -UseBasicParsing
            if (-not $ExpectedHash) {
                Write-Host ("    ok       {0}" -f $Name)
                return $true
            }
            $have = (Get-FileHash -Path $dest -Algorithm SHA256).Hash
            if ($have -eq $ExpectedHash) {
                Write-Host ("    ok       {0}" -f $Name)
                return $true
            }
            Write-Host ("    bad hash {0} (attempt {1})" -f $Name, $i)
        } catch {
            Write-Host ("    failed   {0} (attempt {1}): {2}" -f $Name, $i, $_.Exception.Message)
        }
        Start-Sleep -Seconds 3
    }
    return $false
}

# SHA256SUMS names every part and carries its hash, so it decides both what to
# download and whether it arrived intact.
Write-Host "==> metadata"
foreach ($f in @("SHA256SUMS", "ARCHIVE.sha256", "MANIFEST.txt", "load-images.sh", "docker-compose.pinned.yml")) {
    if (-not (Get-Asset -Name $f -ExpectedHash $null)) {
        throw "Could not download $f. If this is a TLS or proxy error, GitHub may be blocked from this machine."
    }
}

$sums = @{}
foreach ($line in Get-Content (Join-Path $OutDir "SHA256SUMS")) {
    if ($line -match '^([0-9a-fA-F]{64})\s+\*?(.+)$') {
        $sums[$Matches[2].Trim()] = $Matches[1].ToUpper()
    }
}
if ($sums.Count -eq 0) { throw "SHA256SUMS parsed to nothing - the download is not what was expected." }

Write-Host ("==> {0} parts" -f $sums.Count)
$failed = @()
foreach ($name in ($sums.Keys | Sort-Object)) {
    if (-not (Get-Asset -Name $name -ExpectedHash $sums[$name])) { $failed += $name }
}

Write-Host ""
if ($failed.Count -gt 0) {
    Write-Host "!! these did not verify:"
    $failed | ForEach-Object { Write-Host ("     {0}" -f $_) }
    Write-Host "!! re-run this script - verified files are skipped, so only these are retried."
    exit 1
}

Write-Host "==> all files present and verified"
Write-Host ""
Write-Host "Next, with WinSCP (binary transfer mode), upload the whole folder"
Write-Host ""
Write-Host ("     {0}" -f $OutDir)
Write-Host ""
Write-Host "to a staging directory on dx12348, then run there:"
Write-Host ""
Write-Host ("     cd <staging>/{0} && chmod +x load-images.sh && ./load-images.sh" -f $Tag)
