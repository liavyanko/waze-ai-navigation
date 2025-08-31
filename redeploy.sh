#!/bin/bash

# Waze AI Project - Redeployment Script
# This script handles redeployment of the Streamlit application

set -e  # Exit on any error

echo "🚀 Starting redeployment process..."

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

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    print_error "app.py not found. Please run this script from the project root directory."
    exit 1
fi

# Function to check if virtual environment exists
check_venv() {
    if [ ! -d "venv" ]; then
        print_warning "Virtual environment not found. Creating one..."
        python3 -m venv venv
        print_success "Virtual environment created"
    fi
}

# Function to activate virtual environment
activate_venv() {
    print_status "Activating virtual environment..."
    source venv/bin/activate
    print_success "Virtual environment activated"
}

# Function to install/upgrade dependencies
install_dependencies() {
    print_status "Installing/upgrading dependencies..."
    
    # Check if requirements.txt exists, if not create one
    if [ ! -f "requirements.txt" ]; then
        print_warning "requirements.txt not found. Creating one with common dependencies..."
        cat > requirements.txt << EOF
streamlit>=1.28.0
requests>=2.31.0
folium>=0.14.0
streamlit-folium>=0.13.0
numpy>=1.24.0
pandas>=2.0.0
scikit-learn>=1.3.0
EOF
        print_success "requirements.txt created"
    fi
    
    pip install --upgrade pip
    pip install -r requirements.txt
    print_success "Dependencies installed/upgraded"
}

# Function to clean cache
clean_cache() {
    print_status "Cleaning cache files..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    print_success "Cache cleaned"
}

# Function to run tests
run_tests() {
    if [ -f "test_core.py" ]; then
        print_status "Running tests..."
        python test_core.py
        print_success "Tests completed"
    else
        print_warning "No test file found, skipping tests"
    fi
}

# Function to start the application
start_app() {
    print_status "Starting Streamlit application..."
    print_status "The app will be available at: http://localhost:8501"
    print_status "Press Ctrl+C to stop the application"
    
    # Check if port 8501 is available, if not use 8502
    if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_warning "Port 8501 is in use, using port 8502"
        streamlit run app.py --server.port 8502
    else
        streamlit run app.py --server.port 8501
    fi
}

# Function to deploy to Streamlit Cloud (if configured)
deploy_to_cloud() {
    if command -v streamlit &> /dev/null; then
        print_status "Checking for Streamlit Cloud deployment..."
        if [ -f ".streamlit/config.toml" ]; then
            print_status "Found Streamlit config, you can deploy to Streamlit Cloud using:"
            echo "   git add . && git commit -m 'Update app' && git push"
        else
            print_warning "No Streamlit Cloud config found. To deploy to Streamlit Cloud:"
            echo "   1. Push your code to GitHub"
            echo "   2. Connect your repo at https://share.streamlit.io/"
        fi
    fi
}

# Main deployment process
main() {
    print_status "Starting deployment process..."
    
    # Check and setup virtual environment
    check_venv
    activate_venv
    
    # Install dependencies
    install_dependencies
    
    # Clean cache
    clean_cache
    
    # Run tests
    run_tests
    
    print_success "Deployment preparation completed!"
    echo ""
    echo "Options:"
    echo "  1. Start local development server (recommended for testing)"
    echo "  2. Deploy to Streamlit Cloud (if configured)"
    echo "  3. Exit"
    echo ""
    
    read -p "Choose an option (1-3): " choice
    
    case $choice in
        1)
            start_app
            ;;
        2)
            deploy_to_cloud
            ;;
        3)
            print_status "Exiting..."
            exit 0
            ;;
        *)
            print_error "Invalid option. Exiting..."
            exit 1
            ;;
    esac
}

# Handle script interruption
trap 'print_warning "Script interrupted. Exiting..."; exit 1' INT TERM

# Run main function
main "$@"
