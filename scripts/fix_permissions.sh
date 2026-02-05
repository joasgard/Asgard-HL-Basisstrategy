#!/bin/bash
# Fix file permissions for security
# Run this after setup to ensure sensitive files are properly protected

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "Fixing File Permissions for Security"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to fix permissions
fix_permissions() {
    local file="$1"
    local perms="$2"
    
    if [ -e "$file" ]; then
        chmod "$perms" "$file"
        echo -e "${GREEN}✓${NC} Set permissions $perms on $file"
    else
        echo -e "${YELLOW}⚠${NC} File not found: $file"
    fi
}

# Fix database permissions
echo "Fixing database permissions..."
fix_permissions "$PROJECT_DIR/state.db" 600

# Create data directory if needed
if [ ! -d "$PROJECT_DIR/data" ]; then
    mkdir -p "$PROJECT_DIR/data"
    echo -e "${GREEN}✓${NC} Created data directory"
fi

# Fix data directory permissions
chmod 700 "$PROJECT_DIR/data"
echo -e "${GREEN}✓${NC} Set permissions 700 on data/"

# Fix secrets directory
echo ""
echo "Fixing secrets directory permissions..."

if [ -d "$PROJECT_DIR/secrets" ]; then
    # Directory itself
    chmod 700 "$PROJECT_DIR/secrets"
    echo -e "${GREEN}✓${NC} Set permissions 700 on secrets/"
    
    # All files in secrets (except examples and README)
    find "$PROJECT_DIR/secrets" -type f ! -name "*.example" ! -name "README.md" ! -name ".gitkeep" -exec chmod 600 {} \;
    echo -e "${GREEN}✓${NC} Set permissions 600 on secret files"
    
    # Example files should be readable
    find "$PROJECT_DIR/secrets" -type f -name "*.example" -exec chmod 644 {} \;
    echo -e "${GREEN}✓${NC} Set permissions 644 on example files"
else
    echo -e "${YELLOW}⚠${NC} Secrets directory not found, skipping"
fi

# Fix logs directory
if [ -d "$PROJECT_DIR/logs" ]; then
    chmod 755 "$PROJECT_DIR/logs"
    echo -e "${GREEN}✓${NC} Set permissions 755 on logs/"
fi

# Check for .env file
if [ -f "$PROJECT_DIR/.env" ]; then
    chmod 600 "$PROJECT_DIR/.env"
    echo -e "${GREEN}✓${NC} Set permissions 600 on .env"
fi

# Check for dashboard users file
if [ -f "$PROJECT_DIR/secrets/dashboard_users.json" ]; then
    chmod 600 "$PROJECT_DIR/secrets/dashboard_users.json"
    echo -e "${GREEN}✓${NC} Set permissions 600 on dashboard_users.json"
fi

echo ""
echo "=========================================="
echo "Permission Fix Complete"
echo "=========================================="
echo ""
echo "Current permissions:"
echo ""

# Show current state
cd "$PROJECT_DIR"

if [ -f "state.db" ]; then
    ls -la state.db
fi

if [ -d "secrets" ]; then
    ls -la secrets/ | head -20
fi

echo ""
echo "If you see any files with permissions that are too open"
echo "(e.g., 644 instead of 600), run this script again."
