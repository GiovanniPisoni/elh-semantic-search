<#
.SYNOPSIS
    Development helper script for the ELH RAG project on Windows.

.DESCRIPTION
    PowerShell equivalent of the Makefile. Gives the same commands to
    Windows developers without requiring `make` to be installed.

.EXAMPLE
    .\dev.ps1 help
    .\dev.ps1 install-dev
    .\dev.ps1 test
    .\dev.ps1 app
#>

param(
    [Parameter(Position = 0)]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host ""
    Write-Host "ELH Semantic Search - available commands" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  .\dev.ps1 install       " -NoNewline -ForegroundColor Yellow
    Write-Host "Install runtime + dev dependencies"
    Write-Host "  .\dev.ps1 test          " -NoNewline -ForegroundColor Yellow
    Write-Host "Run the test suite"
    Write-Host "  .\dev.ps1 test-cov      " -NoNewline -ForegroundColor Yellow
    Write-Host "Run tests with coverage report"
    Write-Host "  .\dev.ps1 lint          " -NoNewline -ForegroundColor Yellow
    Write-Host "Lint the codebase with ruff"
    Write-Host "  .\dev.ps1 format        " -NoNewline -ForegroundColor Yellow
    Write-Host "Auto-format the codebase with ruff"
    Write-Host "  .\dev.ps1 index         " -NoNewline -ForegroundColor Yellow
    Write-Host "Index reviews into Pinecone"
    Write-Host "  .\dev.ps1 index-reset   " -NoNewline -ForegroundColor Yellow
    Write-Host "Wipe the index and rebuild from scratch"
    Write-Host "  .\dev.ps1 app           " -NoNewline -ForegroundColor Yellow
    Write-Host "Launch the Streamlit app"
    Write-Host "  .\dev.ps1 clean         " -NoNewline -ForegroundColor Yellow
    Write-Host "Remove caches and build artifacts"
    Write-Host ""
}

switch ($Command.ToLower()) {
    "help" {
        Show-Help
    }
    "install" {
        pip install -r requirements.txt
        pip install -e .
    }
    "test" {
        pytest
    }
    "test-cov" {
        pytest --cov=elh_rag --cov-report=term-missing --cov-report=html
    }
    "lint" {
        ruff check src tests scripts
    }
    "format" {
        ruff format src tests scripts
        ruff check --fix src tests scripts
    }
    "index" {
        python -m scripts.run_indexer
    }
    "index-reset" {
        python -m scripts.run_indexer --reset
    }
    "app" {
        streamlit run src/elh_rag/ui/app.py --server.fileWatcherType none
    }
    "clean" {
        $paths = @(".pytest_cache", ".mypy_cache", ".ruff_cache", "htmlcov", ".coverage")
        foreach ($p in $paths) {
            if (Test-Path $p) {
                Remove-Item -Recurse -Force $p
                Write-Host "Removed $p"
            }
        }
        Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item -Recurse -Force $_.FullName
            }
        Get-ChildItem -Path . -Recurse -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item -Recurse -Force $_.FullName
            }
        Write-Host "Clean complete." -ForegroundColor Green
    }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
