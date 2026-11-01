# Tests the Unity importer in a throwaway project (_unitytest\), never in the game project.
#   .\tools\test_unity_import.ps1 [-Net net_42_one_piece] [-Pipeline urp|builtin] [-Unity <Unity.exe>] [-Shots <folder>]
# URP runs also log how much of the bag the twine covers at 0.8-25 m for each mip / alpha-to-coverage setting.
# Generate (full) the net first. Exit code 0 = all Unity checks passed; the log is _unitytest\<net>_<pipeline>.log.
param(
    [string]$Net = "net_42_one_piece",
    [ValidateSet("urp", "builtin")][string]$Pipeline = "urp",
    [string]$Unity = "C:\repos\carp\6000.4.10f1\Editor\Unity.exe",
    [string]$Shots = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$proj = Join-Path $root "_unitytest"
$export = Join-Path $root "output\$Net\export"
if (-not (Test-Path (Join-Path $export "net_manifest.json"))) { throw "No export at $export - run generate.bat $Net first." }
if (-not (Test-Path $Unity)) { throw "Unity not found at $Unity - pass -Unity <path to Unity.exe>." }
if (-not (Test-Path (Join-Path $proj "ProjectSettings"))) {
    Write-Host "Creating the test project (a few minutes, once) ..."
    Start-Process $Unity -ArgumentList @("-batchmode", "-createProject", "`"$proj`"", "-logFile", "`"$proj-create.log`"", "-quit") -Wait
    $manifest = Join-Path $proj "Packages\manifest.json"
    $json = Get-Content $manifest -Raw | ConvertFrom-Json
    $json.dependencies | Add-Member -NotePropertyName "com.unity.render-pipelines.universal" -NotePropertyValue "17.4.0" -Force
    # UTF-8 without a BOM: Unity's package manager rejects a BOM (Windows PowerShell 5.1 writes one with -Encoding utf8).
    [IO.File]::WriteAllText($manifest, ($json | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding $false))
}
# Fresh copies of the importer, runtime and test; the previous import is removed so every run starts clean.
Remove-Item (Join-Path $proj "Assets\NetStudio") -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Join-Path $proj "Assets\NetStudio\Editor"), (Join-Path $proj "Assets\NetStudio\Runtime"), (Join-Path $proj "Assets\NetTest\Editor") | Out-Null
Copy-Item (Join-Path $root "unity\NetStudio\Editor\*") (Join-Path $proj "Assets\NetStudio\Editor") -Force
Copy-Item (Join-Path $root "unity\NetStudio\Runtime\*") (Join-Path $proj "Assets\NetStudio\Runtime") -Force
Copy-Item (Join-Path $root "unity\Tests\NetImportTest.cs") (Join-Path $proj "Assets\NetTest\Editor") -Force
Remove-Item (Join-Path $proj "Assets\TestURP*.asset*") -Force -ErrorAction SilentlyContinue
$log = Join-Path $proj "${Net}_$Pipeline.log"
$unityArgs = @("-batchmode", "-projectPath", "`"$proj`"", "-executeMethod", "NetImportTest.Run",
    "-netExport", "`"$export`"", "-pipeline", $Pipeline, "-logFile", "`"$log`"")
if ($Shots) { New-Item -ItemType Directory -Force $Shots | Out-Null; $unityArgs += @("-shots", "`"$((Resolve-Path $Shots).Path)`"") }
$p = Start-Process $Unity -ArgumentList $unityArgs -Wait -PassThru
Select-String -Path $log -Pattern "\[NetTest\]|\[NetStudio\]|error CS|Exception" | ForEach-Object { $_.Line }
exit $p.ExitCode
