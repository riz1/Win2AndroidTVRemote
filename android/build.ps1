param([switch]$Setup)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$toolRoot = Join-Path $projectRoot 'build/android-tools'
if ($Setup) {
    & python (Join-Path $projectRoot 'tools/setup_android.py')
    if ($LASTEXITCODE -ne 0) { throw 'Toolchain download failed.' }
}
$javaExe = Get-ChildItem (Join-Path $toolRoot 'jdk') -Filter java.exe -Recurse | Select-Object -First 1
if (-not $javaExe) { throw 'Run ./build.ps1 -Setup first.' }
$env:JAVA_HOME = Split-Path (Split-Path $javaExe.FullName -Parent) -Parent
$env:ANDROID_HOME = Join-Path $toolRoot 'sdk'
$env:ANDROID_USER_HOME = Join-Path $toolRoot 'android-user'
# Ignore the machine's legacy Android preference path for this build process.
Remove-Item Env:ANDROID_SDK_HOME -ErrorAction SilentlyContinue
$env:GRADLE_USER_HOME = Join-Path $toolRoot 'gradle-cache'
$env:TVREMOTE_BUILD_PYTHON = (Get-Command python).Source
$env:PATH = "$env:JAVA_HOME/bin;$env:PATH"
New-Item -ItemType Directory -Force $env:ANDROID_HOME,$env:ANDROID_USER_HOME | Out-Null
$sdkManager = Join-Path $toolRoot 'sdk-tools/cmdline-tools/bin/sdkmanager.bat'
if (-not (Test-Path (Join-Path $env:ANDROID_HOME 'platforms/android-35/android.jar'))) {
    (1..30 | ForEach-Object { 'y' }) | & $sdkManager "--sdk_root=$env:ANDROID_HOME" --licenses
    if ($LASTEXITCODE -ne 0) { throw 'Android SDK license setup failed.' }
    & $sdkManager "--sdk_root=$env:ANDROID_HOME" 'platforms;android-35' 'build-tools;35.0.0' 'platform-tools'
    if ($LASTEXITCODE -ne 0) { throw 'Android SDK installation failed.' }
}
$sdkPath = $env:ANDROID_HOME.Replace('\','/')
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'local.properties') -Value "sdk.dir=$sdkPath" -Encoding ascii
$gradle = Join-Path $toolRoot 'gradle/gradle-8.11.1/bin/gradle.bat'
& $gradle -p $PSScriptRoot --no-daemon --console=plain --stacktrace assembleDebug
if ($LASTEXITCODE -ne 0) { throw 'Android build failed.' }
$destination = Join-Path $projectRoot 'dist/TV-Remote-Android.apk'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'app/build/outputs/apk/debug/app-debug.apk') -Destination $destination -Force
Write-Host "APK ready: $destination"
