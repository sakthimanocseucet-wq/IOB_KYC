Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  IOB KYC System - Single Link Startup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $rootDir "backend"
$jarPath = Join-Path $backendDir "target\kyc-system-1.0.0.jar"

# ---- Stop any existing servers ----
Write-Host "[*] Stopping any existing servers..." -ForegroundColor Yellow
Get-Process -Name java -ErrorAction SilentlyContinue | Where-Object { $_.Path -notlike "*cursor*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# ---- Build JAR if missing ----
if (-not (Test-Path $jarPath)) {
    Write-Host "[*] JAR not found. Building backend (this may take a minute)..." -ForegroundColor Yellow
    Push-Location $backendDir
    $buildResult = mvn clean package -DskipTests -q 2>&1
    Pop-Location
    if (-not (Test-Path $jarPath)) {
        Write-Host "[ERROR] Build failed. JAR not created. Check Maven/Java installation." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Build successful!" -ForegroundColor Green
}

# ---- Start via batch file (handles spaces in paths) ----
Write-Host "[1/1] Starting Spring Boot Backend (port 8080 + Flask AI on 5001)..." -ForegroundColor Green
$batFile = Join-Path $rootDir "start-backend.bat"
Start-Process -FilePath $batFile -WindowStyle Minimized

# ---- Wait for server ----
Start-Sleep -Seconds 8
$maxWait = 60
$waited = 8
$backendReady = $false

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 2
    $waited += 2

    if (-not $backendReady) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8080/actuator/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                $backendReady = $true
                Write-Host "  Backend (8080) is ready!" -ForegroundColor Green
            }
        } catch {}
    }

    if ($backendReady) { break }
    Write-Host "  Waiting... ($waited s)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  All Systems Running!" -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:8080" -ForegroundColor White
Write-Host "  Backend:   http://localhost:8080/api" -ForegroundColor White
Write-Host "  AI/ML:     http://localhost:5001" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  >>> Open in browser: http://localhost:8080 <<<" -ForegroundColor Yellow
Write-Host ""

Start-Process "http://localhost:8080"
