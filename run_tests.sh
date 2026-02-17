#!/bin/bash
# AI-MON Frontend Test Runner
# Runs the complete test suite with coverage reporting

set -e

echo "=========================================="
echo "AI-MON Frontend Test Suite"
echo "=========================================="
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Installing dependencies..."
    pip install -r requirements.txt
fi

# Run tests with coverage
echo "🧪 Running tests..."
echo ""

pytest tests/ \
    -v \
    --cov=. \
    --cov-report=term-missing \
    --cov-report=html \
    --cov-report=xml \
    --tb=short \
    --durations=10

echo ""
echo "=========================================="
echo "✅ Test suite complete!"
echo ""
echo "📊 Coverage report generated:"
echo "   HTML: htmlcov/index.html"
echo "   XML:  coverage.xml"
echo "=========================================="
