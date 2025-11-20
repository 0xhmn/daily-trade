# Backend Code Quality Tools

.PHONY: format lint check install-dev clean help

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install-dev:  ## Install development dependencies
	pip install "black>=23.12.0" "flake8>=6.1.0" "mypy>=1.7.1" "isort>=5.13.2" "autoflake>=2.2.1" "pre-commit>=3.6.0"
	pre-commit install

format:  ## Auto-fix: Remove unused imports, sort imports, and format code
	@echo "🧹 Removing unused imports and variables..."
	autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive backend/ scripts/
	@echo "📦 Sorting imports..."
	isort backend/ scripts/
	@echo "🎨 Formatting code with black..."
	black backend/ scripts/
	@echo "✅ Formatting complete!"

lint:  ## Run linters (flake8 and mypy)
	@echo "🔍 Running flake8..."
	flake8 backend/ scripts/ || true
	@echo ""
	@echo "🔍 Running mypy..."
	mypy backend/ scripts/ || true

check:  ## Run all pre-commit checks
	@echo "🔍 Running all pre-commit checks..."
	pre-commit run --all-files

fix:  ## Format code and run checks
	@$(MAKE) format
	@echo ""
	@$(MAKE) check

clean:  ## Clean cache and temporary files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned cache files!"
