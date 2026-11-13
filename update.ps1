param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$StageDir,
    [Parameter(Mandatory=$true)][int]$WaitPid,
    [switch]$SkipLaunch
)
Add-Type -AssemblyName System.Windows.Forms
$ErrorActionPreference = 'Stop'
$install = [IO.Path]::GetFullPath($InstallDir)
$stage = [IO.Path]::GetFullPath($StageDir)
$source = Join-Path $stage 'GeoPairAnnotator'
$names = @('GeoPairAnnotator.exe','_internal','README.md','LICENSE','THIRD_PARTY_NOTICES.md','docs','third_party','examples','version.json','release_manifest.json','update.ps1')
$names += @(Get-ChildItem -LiteralPath $source -File -Filter 'RELEASE_NOTES_v*.md' | Where-Object { $_.Name -match '^RELEASE_NOTES_v[0-9]+\.[0-9]+\.[0-9]+\.md$' } | Select-Object -ExpandProperty Name)
$backup = Join-Path $stage 'backup'
$failed = Join-Path $stage 'failed'
try {
    if (!(Test-Path -LiteralPath (Join-Path $install 'GeoPairAnnotator.exe')) -or
        !(Test-Path -LiteralPath (Join-Path $source 'GeoPairAnnotator.exe')) -or
        !(Test-Path -LiteralPath (Join-Path $source 'release_manifest.json')) -or
        $install.TrimEnd('\') -eq $source.TrimEnd('\')) {
        throw 'Invalid installation directory or update package.'
    }
    try { Wait-Process -Id $WaitPid -Timeout 60 -ErrorAction Stop } catch {
        if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { throw 'The old program is still running; no files were replaced.' }
    }
    try {
        New-Item -ItemType Directory -Path $backup -Force | Out-Null
        foreach ($name in $names) {
            $old = Join-Path $install $name
            if (Test-Path -LiteralPath $old) { Move-Item -LiteralPath $old -Destination $backup -ErrorAction Stop }
        }
        foreach ($name in $names) {
            $new = Join-Path $source $name
            if (Test-Path -LiteralPath $new) { Move-Item -LiteralPath $new -Destination $install -ErrorAction Stop }
        }
    } catch {
        New-Item -ItemType Directory -Path $failed -Force | Out-Null
        foreach ($name in $names) {
            $partial = Join-Path $install $name
            if (Test-Path -LiteralPath $partial) { Move-Item -LiteralPath $partial -Destination $failed -ErrorAction SilentlyContinue }
            $old = Join-Path $backup $name
            if (Test-Path -LiteralPath $old) { Move-Item -LiteralPath $old -Destination $install -ErrorAction SilentlyContinue }
        }
        throw
    }
    if (!$SkipLaunch) { Start-Process -FilePath (Join-Path $install 'GeoPairAnnotator.exe') -WorkingDirectory $install }
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    $message = 'GeoPair Annotator update failed: ' + $_.Exception.Message
    [System.Windows.Forms.MessageBox]::Show($message, 'Update failed') | Out-Null
    exit 1
}
