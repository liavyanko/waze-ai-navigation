#!/bin/bash

# 🚀 Waze AI Project Deployment Script
# =====================================

set -e  # Exit on any error

echo "🚀 Starting Waze AI Project Deployment..."
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="waze_ai_project"
PYTHON_VERSION="3.13"
REQUIREMENTS_FILE="requirements.txt"
MAIN_APP="app.py"

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
if [ ! -f "$MAIN_APP" ]; then
    print_error "Main application file ($MAIN_APP) not found!"
    print_error "Please run this script from the project root directory."
    exit 1
fi

print_status "Checking Python version..."
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
if [[ "$python_version" != "$PYTHON_VERSION" ]]; then
    print_warning "Python version $python_version detected, expected $PYTHON_VERSION"
    print_warning "Continuing anyway, but issues may occur..."
else
    print_success "Python version $python_version confirmed"
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
print_status "Activating virtual environment..."
source venv/bin/activate
print_success "Virtual environment activated"

# Upgrade pip
print_status "Upgrading pip..."
pip install --upgrade pip
print_success "Pip upgraded"

# Install dependencies
print_status "Installing dependencies..."
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -r "$REQUIREMENTS_FILE"
    print_success "Dependencies installed"
else
    print_error "Requirements file ($REQUIREMENTS_FILE) not found!"
    exit 1
fi

# Check for environment variables
print_status "Checking environment variables..."
if [ -z "$TOMTOM_API_KEY" ] && [ -z "$HERE_API_KEY" ]; then
    print_warning "No traffic API keys found in environment variables"
    print_warning "The app will use mock traffic data"
    print_warning "To enable real traffic data, set:"
    print_warning "  export TOMTOM_API_KEY='your_key_here'"
    print_warning "  export HERE_API_KEY='your_key_here'"
else
    print_success "Traffic API keys found in environment"
fi

# Run tests
print_status "Running tests..."
if python tests/test_traffic_integration.py > /dev/null 2>&1; then
    print_success "Traffic integration tests passed"
else
    print_warning "Some tests failed, but continuing deployment..."
fi

# Check if Streamlit is installed
if ! command -v streamlit &> /dev/null; then
    print_error "Streamlit not found! Installing..."
    pip install streamlit
    print_success "Streamlit installed"
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_status "Creating .env file..."
    cat > .env << EOF
# Waze AI Project Environment Variables
# =====================================

# Traffic API Keys (optional)
# TOMTOM_API_KEY=your_tomtom_key_here
# HERE_API_KEY=your_here_key_here

# Application Settings
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_HEADLESS=true
EOF
    print_success ".env file created"
else
    print_status ".env file already exists"
fi

# Create deployment info
print_status "Creating deployment info..."
cat > DEPLOYMENT_INFO.md << EOF
# 🚀 Deployment Information

## Deployment Date
$(date)

## Environment
- Python Version: $(python --version)
- Streamlit Version: $(streamlit --version | head -n1)
- Project Directory: $(pwd)

## Configuration
- Main App: $MAIN_APP
- Requirements: $REQUIREMENTS_FILE
- Virtual Environment: venv/

## Traffic API Status
$(if [ -n "$TOMTOM_API_KEY" ]; then echo "- TomTom API: ✅ Configured"; else echo "- TomTom API: ❌ Not configured"; fi)
$(if [ -n "$HERE_API_KEY" ]; then echo "- HERE API: ✅ Configured"; else echo "- HERE API: ❌ Not configured"; fi)

## Next Steps
1. Run the application: \`streamlit run app.py\`
2. Open browser to: http://localhost:8501
3. Configure API keys in .env file if needed

## Troubleshooting
- Check logs for any errors
- Verify all dependencies are installed
- Ensure API keys are properly set
EOF
print_success "Deployment info created"

print_success "Deployment completed successfully!"
echo ""
echo "🎉 Ready to run the application!"
echo ""
echo "To start the app:"
echo "  streamlit run app.py"
echo ""
echo "To start with specific port:"
echo "  streamlit run app.py --server.port 8501"
echo ""
echo "To start in headless mode:"
echo "  streamlit run app.py --server.headless true"
echo ""
echo "📖 Check DEPLOYMENT_INFO.md for more details"
