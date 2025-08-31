#!/bin/bash

# 🧹 Waze AI Project Cleanup Script
# =================================

set -e  # Exit on any error

echo "🧹 Starting Waze AI Project Cleanup..."
echo "====================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to safely remove files
safe_remove() {
    if [ -e "$1" ]; then
        rm -rf "$1"
        print_success "Removed: $1"
    else
        print_status "Not found: $1"
    fi
}

# Function to safely remove files with confirmation
safe_remove_with_confirm() {
    if [ -e "$1" ]; then
        echo -n "Remove $1? (y/N): "
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            rm -rf "$1"
            print_success "Removed: $1"
        else
            print_status "Skipped: $1"
        fi
    else
        print_status "Not found: $1"
    fi
}

# Clean Python cache files
print_status "Cleaning Python cache files..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true
print_success "Python cache files cleaned"

# Clean Streamlit cache
print_status "Cleaning Streamlit cache..."
safe_remove ~/.streamlit/cache
print_success "Streamlit cache cleaned"

# Clean temporary files
print_status "Cleaning temporary files..."
safe_remove .DS_Store
safe_remove *.tmp
safe_remove *.log
safe_remove *.bak
print_success "Temporary files cleaned"

# Clean test artifacts
print_status "Cleaning test artifacts..."
safe_remove .pytest_cache
safe_remove .coverage
safe_remove htmlcov
safe_remove .mypy_cache
print_success "Test artifacts cleaned"

# Clean IDE files
print_status "Cleaning IDE files..."
safe_remove .vscode
safe_remove .idea
safe_remove *.swp
safe_remove *.swo
print_success "IDE files cleaned"

# Clean deployment artifacts
print_status "Cleaning deployment artifacts..."
safe_remove DEPLOYMENT_INFO.md
print_success "Deployment artifacts cleaned"

# Clean backup files (with confirmation)
print_status "Checking backup files..."
if [ -d "backups" ] && [ "$(ls -A backups)" ]; then
    echo "Backup files found in backups/ directory:"
    ls -la backups/
    echo ""
    safe_remove_with_confirm "backups"
else
    print_status "No backup files found"
fi

# Clean old documentation files
print_status "Checking for old documentation files..."
if [ -f "README_UPDATE_SUMMARY.md" ]; then
    print_warning "Found old documentation file: README_UPDATE_SUMMARY.md"
    safe_remove_with_confirm "README_UPDATE_SUMMARY.md"
fi

# Clean virtual environment (with confirmation)
print_status "Checking virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment found:"
    du -sh venv/
    echo ""
    safe_remove_with_confirm "venv"
    print_warning "You may need to recreate the virtual environment"
    print_warning "Run: python3 -m venv venv"
    print_warning "Then: source venv/bin/activate && pip install -r requirements.txt"
else
    print_status "No virtual environment found"
fi

# Clean unused static files
print_status "Checking static files..."
if [ -d "static/css" ] && [ ! "$(ls -A static/css)" ]; then
    safe_remove "static/css"
    print_success "Removed empty CSS directory"
fi

if [ -d "static/images" ] && [ ! "$(ls -A static/images)" ]; then
    safe_remove "static/images"
    print_success "Removed empty images directory"
fi

# Clean unused directories
print_status "Checking for empty directories..."
find . -type d -empty -delete 2>/dev/null || true
print_success "Empty directories cleaned"

# Show disk usage
print_status "Current disk usage:"
du -sh . 2>/dev/null || true

print_success "Cleanup completed successfully!"
echo ""
echo "🎉 Project cleaned up!"
echo ""
echo "Next steps:"
echo "1. If you removed venv, recreate it: python3 -m venv venv"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Install dependencies: pip install -r requirements.txt"
echo "4. Run tests: python tests/test_traffic_integration.py"
echo "5. Start the app: streamlit run app.py"
