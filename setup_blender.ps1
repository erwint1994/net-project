# Downloads the official portable Blender 5.2.3 into _vendor\ (no installer, no admin rights) and checks its SHA-256.
# Only needed when neither NET_BLENDER nor the sibling ..\bivvy-project\_vendor Blender is available.
$ErrorActionPreference = "Stop"
$version = "5.2.3"
$series = "5.2"
$root = $PSScriptRoot
$vendor = Join-Path $root "_vendor"
$target = Join-Path $vendor "blender-$version-windows-x64"
if (Test-Path (Join-Path $target "blender.exe")) { Write-Host "Blender $version is already set up in $target"; exit 0 }
$download = Join-Path $vendor "download"
New-Item -ItemType Directory -Force $download | Out-Null
$base = "https://download.blender.org/release/Blender$series"
$zip = Join-Path $download "blender-$version-windows-x64.zip"
Write-Host "Downloading Blender $version (about 400 MB) from download.blender.org ..."
Invoke-WebRequest "$base/blender-$version.sha256" -OutFile (Join-Path $download "blender-$version.sha256") -UseBasicParsing
$ProgressPreference = "SilentlyContinue"
Invoke-WebRequest "$base/blender-$version-windows-x64.zip" -OutFile $zip -UseBasicParsing
$expected = (Select-String -Path (Join-Path $download "blender-$version.sha256") -Pattern "windows-x64.zip").Line.Split(" ")[0]
$actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expected) { Remove-Item $zip; throw "Checksum mismatch: expected $expected, got $actual. The download was deleted; try again." }
Write-Host "Checksum OK. Unpacking ..."
Expand-Archive $zip -DestinationPath $vendor -Force
Remove-Item $zip
& (Join-Path $target "blender.exe") -b --factory-startup --python-expr "import bpy; print('Blender', bpy.app.version_string, 'works')"
Write-Host "Done: $target"
