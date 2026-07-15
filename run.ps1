<#
.SYNOPSIS
    One-click startup script for the Privacy-Preserving CDSS system.
    Starts all services and launches the Doctor Console.
#>

$root = "D:\9raya\memoire 2026\Privacy-Preserving-CDSS"
$venvActivate = "$root\backend\.venv\Scripts\Activate.ps1"

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  Privacy Preserving CDSS - Starting All Services" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path $venvActivate)) {
    Write-Host "❌ Virtual environment not found at: $venvActivate" -ForegroundColor Red
    Write-Host "Please create the virtual environment first:" -ForegroundColor Yellow
    Write-Host "  cd $root\backend" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor Yellow
    Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "  pip install -r ..\requirements.txt" -ForegroundColor Yellow
    pause
    exit 1
}

# Function to check if a service is running
function Test-ServiceRunning {
    param(
        [string]$Url,
        [int]$Timeout = 5
    )
    
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec $Timeout -UseBasicParsing
        return $true
    }
    catch {
        return $false
    }
}

# Function to wait for service to be ready
function Wait-ForService {
    param(
        [string]$Url,
        [string]$ServiceName,
        [int]$MaxAttempts = 30
    )
    
    Write-Host "  Waiting for $ServiceName to start..." -ForegroundColor Yellow
    
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        if (Test-ServiceRunning -Url $Url) {
            Write-Host "  ✓ $ServiceName is ready" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 1
    }
    
    Write-Host "  ⚠ $ServiceName did not start within $MaxAttempts seconds" -ForegroundColor Yellow
    return $false
}

# Start all services in separate PowerShell windows
Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host ""

# Service 1: Patient MCP (Port 8005)
Write-Host "  [1/6] Starting Patient MCP (Port 8005)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",
    "cd '$root'; .\backend\.venv\Scripts\Activate.ps1; uvicorn patient_mcp.app:app --reload --port 8005"

# Service 2: Rule Engine (Port 8004)
Write-Host "  [2/6] Starting Rule Engine (Port 8004)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",
    "cd '$root'; .\backend\.venv\Scripts\Activate.ps1; `$env:OLLAMA_HOST='http://127.0.0.1:11434'; uvicorn rule_engine.app:app --reload --port 8004"

# Service 3: Privacy MCP (Port 8003)
Write-Host "  [3/6] Starting Privacy MCP (Port 8003)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",
    "cd '$root'; .\backend\.venv\Scripts\Activate.ps1; uvicorn privacy_mcp.app:app --reload --port 8003"

# Service 4: Decision Engine (Port 8002)
Write-Host "  [4/6] Starting Decision Engine (Port 8002)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",
    "cd '$root'; .\backend\.venv\Scripts\Activate.ps1; uvicorn decision_engine.app:app --reload --port 8002"

# Service 5: Knowledge MCP (Port 8010)
Write-Host "  [5/6] Starting Knowledge MCP (Port 8010)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",
    "cd '$root'; .\backend\.venv\Scripts\Activate.ps1; `$env:OLLAMA_HOST='http://127.0.0.1:11434'; uvicorn knowledge_mcp.app:app --reload --port 8010"

# Service 6: LangGraph Coordinator (Port 8007)
Write-Host "  [6/6] Starting LangGraph Coordinator (Port 8007)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command",
    "cd '$root'; .\backend\.venv\Scripts\Activate.ps1; uvicorn langgraph_coordinator.app:app --reload --port 8007"

Write-Host ""
Write-Host "Waiting for services to initialize..." -ForegroundColor Yellow
Write-Host ""

# Wait for services to be ready
$services = @(
    @{Url = "http://127.0.0.1:8005/health"; Name = "Patient MCP"},
    @{Url = "http://127.0.0.1:8004/health"; Name = "Rule Engine"},
    @{Url = "http://127.0.0.1:8003/health"; Name = "Privacy MCP"},
    @{Url = "http://127.0.0.1:8002/health"; Name = "Decision Engine"},
    @{Url = "http://127.0.0.1:8010/health"; Name = "Knowledge MCP"},
    @{Url = "http://127.0.0.1:8007/health"; Name = "LangGraph Coordinator"}
)

$allReady = $true
foreach ($service in $services) {
    $ready = Wait-ForService -Url $service.Url -ServiceName $service.Name
    if (-not $ready) {
        $allReady = $false
    }
}

Write-Host ""

if ($allReady) {
    Write-Host "====================================================" -ForegroundColor Green
    Write-Host "  All services started successfully!" -ForegroundColor Green
    Write-Host "====================================================" -ForegroundColor Green
    Write-Host ""
    
    # Additional checks
    Write-Host "Checking dependencies..." -ForegroundColor Cyan
    
    # Check Ollama
    $ollamaRunning = $false
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 3
        $ollamaRunning = $true
        Write-Host "  ✓ Ollama is running" -ForegroundColor Green
        
        # Check if required models are available
        $models = $response.models | ForEach-Object { $_.name }
        if ($models -contains "llama3" -and $models -contains "nomic-embed-text") {
            Write-Host "  ✓ Required models (llama3, nomic-embed-text) found" -ForegroundColor Green
        }
        else {
            Write-Host "  ⚠ Missing models. Please run:" -ForegroundColor Yellow
            Write-Host "    ollama pull llama3" -ForegroundColor Yellow
            Write-Host "    ollama pull nomic-embed-text" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "  ⚠ Ollama is not running. Please start it with: ollama serve" -ForegroundColor Yellow
    }
    
    # Check ZKP engine
    $zkpEngine = "$root\zkp_engine\target\release\zkp_engine.exe"
    if (Test-Path $zkpEngine) {
        Write-Host "  ✓ ZKP Engine found" -ForegroundColor Green
    }
    else {
        Write-Host "  ⚠ ZKP Engine not found. Please build it with:" -ForegroundColor Yellow
        Write-Host "    cd $root\zkp_engine" -ForegroundColor Yellow
        Write-Host "    cargo build --release" -ForegroundColor Yellow
    }
    
    # Check ChromaDB
    $chromaDb = "$root\knowledge_mcp\chroma_db"
    if (Test-Path $chromaDb) {
        Write-Host "  ✓ ChromaDB vector database found" -ForegroundColor Green
    }
    else {
        Write-Host "  ⚠ ChromaDB not found. Please build it with:" -ForegroundColor Yellow
        Write-Host "    python $root\scripts\build_rag.py" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "====================================================" -ForegroundColor Cyan
    Write-Host "  Launching Doctor Console..." -ForegroundColor Cyan
    Write-Host "====================================================" -ForegroundColor Cyan
    Write-Host ""
    
    # Small delay to ensure all services are fully ready
    Start-Sleep -Seconds 2
    
    # Launch doctor console
    & python "$root\doctor_console.py"
}
else {
    Write-Host "====================================================" -ForegroundColor Red
    Write-Host "  Some services failed to start" -ForegroundColor Red
    Write-Host "====================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check the error messages in the service windows above." -ForegroundColor Yellow
    Write-Host ""
    pause
}