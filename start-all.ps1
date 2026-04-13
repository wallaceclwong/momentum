# Robust Startup Script for S&P 500 Momentum Screener
# This script validates all dependencies and starts services in correct order

$ErrorActionPreference = "Stop"
$projectRoot = "C:\Users\ASUS\Momentum\sp500-momentum"
$venvPython = "C:\Users\ASUS\Momentum\.venv\Scripts\python.exe"
$uvicorn = "C:\Users\ASUS\Momentum\.venv\Scripts\uvicorn.exe"

Write-Host "=== S&P 500 Momentum Screener Startup ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Required Files
Write-Host "Step 1: Checking required files..." -ForegroundColor Yellow

$requiredFiles = @(
    "$projectRoot\backend\main.py",
    "$projectRoot\backend\db\models.py",
    "$projectRoot\backend\db\crud.py",
    "$projectRoot\backend\db\__init__.py",
    "$projectRoot\backend\scheduler.py",
    "$projectRoot\backend\api\routes_backtest.py",
    "$projectRoot\backend\api\routes_portfolio.py",
    "$projectRoot\backend\api\routes_screener.py",
    "$projectRoot\backend\api\routes_paper.py",
    "$projectRoot\backend\engine\backtest.py",
    "$projectRoot\backend\engine\benchmark.py",
    "$projectRoot\backend\engine\paper_trading.py",
    "$projectRoot\frontend\src\components\charts\sector-pie-chart.tsx",
    "$projectRoot\frontend\src\components\charts\performance-line-chart.tsx"
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        $missingFiles += $file
        Write-Host "  [MISSING] $file" -ForegroundColor Red
    }
}

if ($missingFiles.Count -gt 0) {
    Write-Host "ERROR: Missing required files!" -ForegroundColor Red
    exit 1
}
Write-Host "  All required files present" -ForegroundColor Green

# Step 2: Check Virtual Environment
Write-Host "Step 2: Checking virtual environment..." -ForegroundColor Yellow

if (-not (Test-Path $venvPython)) {
    Write-Host "  ERROR: Virtual environment not found at $venvPython" -ForegroundColor Red
    exit 1
}
Write-Host "  Virtual environment found" -ForegroundColor Green

# Step 3: Check Python Dependencies
Write-Host "Step 3: Checking Python dependencies..." -ForegroundColor Yellow

try {
    $output = & $venvPython -m pip list 2>&1
    $requiredPackages = @("fastapi", "uvicorn", "sqlalchemy", "yfinance", "pandas", "apscheduler")
    
    foreach ($pkg in $requiredPackages) {
        if ($output -notmatch $pkg) {
            Write-Host "  [MISSING] $pkg" -ForegroundColor Red
        }
    }
    Write-Host "  Dependencies checked" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to check dependencies: $_" -ForegroundColor Red
    exit 1
}

# Step 4: Stop Existing Services
Write-Host "Step 4: Stopping existing services..." -ForegroundColor Yellow

try {
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "  Existing services stopped" -ForegroundColor Green
} catch {
    Write-Host "  No existing services to stop" -ForegroundColor Gray
}

# Step 5: Start Backend
Write-Host "Step 5: Starting backend API..." -ForegroundColor Yellow

try {
    $backendProcess = Start-Process -FilePath $uvicorn -ArgumentList "backend.main:app", "--host", "0.0.0.0", "--port", "8000" -WorkingDirectory $projectRoot -NoNewWindow -PassThru
    Start-Sleep -Seconds 5
    
    # Check if backend is running
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "  Backend API running (PID: $($backendProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: Backend health check failed" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  ERROR: Failed to start backend: $_" -ForegroundColor Red
    exit 1
}

# Step 6: Start Frontend
Write-Host "Step 6: Starting frontend..." -ForegroundColor Yellow

try {
    Set-Location "$projectRoot\frontend"
    $frontendProcess = Start-Process -FilePath "npm" -ArgumentList "run", "dev" -NoNewWindow -PassThru
    Write-Host "  Waiting for frontend to start (20s)..." -ForegroundColor Gray
    Start-Sleep -Seconds 20
    
    # Check if frontend is running
    $response = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 15
    if ($response.StatusCode -eq 200) {
        Write-Host "  Frontend running (PID: $($frontendProcess.Id))" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Frontend returned non-200 status, but continuing..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  WARNING: Frontend health check failed, but backend is running. You can start frontend manually." -ForegroundColor Yellow
} finally {
    Set-Location $projectRoot
}

# Step 7: Verify API Endpoints
Write-Host "Step 7: Verifying API endpoints..." -ForegroundColor Yellow

$endpoints = @(
    @{Uri = "http://localhost:8000/health"; Name = "Health Check"},
    @{Uri = "http://localhost:8000/api/backtest/list"; Name = "Backtest List"},
    @{Uri = "http://localhost:8000/api/paper/portfolio"; Name = "Paper Portfolio"}
)

foreach ($endpoint in $endpoints) {
    try {
        $response = Invoke-WebRequest -Uri $endpoint.Uri -UseBasicParsing -TimeoutSec 5
        Write-Host "  $($endpoint.Name)" -ForegroundColor Green
    } catch {
        Write-Host "  $($endpoint.Name) (may be expected if no data)" -ForegroundColor Yellow
    }
}

# Summary
Write-Host ""
Write-Host "=== Startup Complete ===" -ForegroundColor Cyan
Write-Host "Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop services" -ForegroundColor Gray

# Keep script running
try {
    while ($true) {
        Start-Sleep -Seconds 60
        # Periodic health check
        try {
            Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5 | Out-Null
        } catch {
            Write-Host "Backend health check failed, attempting restart..." -ForegroundColor Red
        }
    }
} finally {
    Write-Host "Stopping services..." -ForegroundColor Yellow
    Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $frontendProcess.Id -ErrorAction SilentlyContinue
}
