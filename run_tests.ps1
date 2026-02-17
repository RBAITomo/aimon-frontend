# AI-MON Frontend Test Runner (PowerShell)
# Runs the complete test suite with coverage reporting

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "AI-MON Frontend Test Suite" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if pytest is installed
try {
    python -m pytest --version | Out-Null
} catch {
    Write-Host "❌ pytest not found. Installing dependencies..." -ForegroundColor Yellow
    pip install -r requirements.txt
}

# Run tests with coverage
Write-Host "🧪 Running tests..." -ForegroundColor Green
Write-Host ""

python -m pytest tests/ `
    -v `
    --cov=. `
    --cov-report=term-missing `
    --cov-report=html `
    --cov-report=xml `
    --tb=short `
    --durations=10

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "✅ Test suite complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Coverage report generated:" -ForegroundColor Cyan
    Write-Host "   HTML: htmlcov/index.html" -ForegroundColor White
    Write-Host "   XML:  coverage.xml" -ForegroundColor White
    Write-Host "==========================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "❌ Tests failed!" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
    exit 1
}
