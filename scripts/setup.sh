#!/bin/bash
# Delta Neutral Funding Rate Arbitrage Bot - Environment Setup Script
# Usage: ./setup.sh [options]

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_VERSION="3.11"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# Setup Functions
# =============================================================================

check_system() {
    log_info "Checking system requirements..."
    
    # Check OS
    local os
    os=$(uname -s)
    log_info "Detected OS: $os"
    
    # Check Python
    if command -v python3 &> /dev/null; then
        local python_version
        python_version=$(python3 --version 2>&1 | awk '{print $2}')
        log_info "Python version: $python_version"
        
        # Check if version is >= 3.9
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
            log_success "Python version is compatible (>= 3.9)"
        else
            log_error "Python 3.9 or higher is required"
            exit 1
        fi
    else
        log_error "Python 3 is not installed"
        exit 1
    fi
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 is not installed"
        exit 1
    fi
    
    # Check git
    if ! command -v git &> /dev/null; then
        log_warn "Git is not installed (recommended for version control)"
    fi
    
    log_success "System check passed"
}

setup_directories() {
    log_info "Setting up directory structure..."
    
    local dirs=(
        "$PROJECT_DIR/data"
        "$PROJECT_DIR/logs"
        "$PROJECT_DIR/secrets"
        "$PROJECT_DIR/secrets/archive"
    )
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            log_info "Created directory: $dir"
        fi
    done
    
    # Set secure permissions for secrets directory
    chmod 700 "$PROJECT_DIR/secrets"
    
    log_success "Directory structure ready"
}

setup_venv() {
    log_info "Setting up Python virtual environment..."
    
    cd "$PROJECT_DIR"
    
    if [[ -d ".venv" ]]; then
        log_warn "Virtual environment already exists"
        read -rp "Recreate? [y/N] " response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            rm -rf .venv
        else
            log_info "Using existing virtual environment"
            return 0
        fi
    fi
    
    # Create virtual environment
    python3 -m venv .venv
    log_success "Created virtual environment"
    
    # Activate and install dependencies
    # shellcheck source=/dev/null
    source .venv/bin/activate
    
    log_info "Upgrading pip..."
    pip install --upgrade pip setuptools wheel
    
    log_info "Installing dependencies..."
    pip install -r requirements.txt
    
    log_success "Dependencies installed"
}

setup_secrets() {
    log_info "Setting up secrets directory..."
    
    local secrets_dir="$PROJECT_DIR/secrets"
    local example_secrets=(
        "asgard_api_key.txt"
        "solana_private_key.txt"
        "hyperliquid_private_key.txt"
        "hyperliquid_wallet_address.txt"
        "admin_api_key.txt"
        "arbitrum_rpc_url.txt"
    )
    
    # Create example files
    for secret in "${example_secrets[@]}"; do
        local example_file="$secrets_dir/$secret.example"
        if [[ ! -f "$example_file" ]]; then
            echo "# Place your $secret here" > "$example_file"
            log_info "Created example file: $example_file"
        fi
    done
    
    # Create README
    local readme="$secrets_dir/README.md"
    if [[ ! -f "$readme" ]]; then
        cat > "$readme" << 'EOF'
# Secrets Directory

This directory contains sensitive configuration files.

**IMPORTANT:** Files in this directory are git-ignored. Never commit secrets!

## Required Secrets

1. `asgard_api_key.txt` - Asgard Finance API key
2. `solana_private_key.txt` - Solana wallet private key (ed25519)
3. `hyperliquid_private_key.txt` - Hyperliquid wallet private key (secp256k1)
4. `hyperliquid_wallet_address.txt` - Hyperliquid wallet address

## Optional Secrets

5. `admin_api_key.txt` - API key for pause/resume operations
6. `arbitrum_rpc_url.txt` - Custom Arbitrum RPC URL
7. `sentry_dsn.txt` - Sentry error tracking DSN

## Setup

Copy the example files and fill in your actual values:

```bash
cp asgard_api_key.txt.example asgard_api_key.txt
# Edit asgard_api_key.txt with your actual key
```

Or use environment variables instead (see .env.example).

## Security Best Practices

- Use hardware wallets for production
- Keep private keys separate (Solana vs Hyperliquid)
- Regularly rotate API keys
- Monitor access logs
- Use dedicated API keys for each deployment
EOF
        log_info "Created secrets README"
    fi
    
    # Check for actual secrets
    local missing=()
    for secret in "${example_secrets[@]:0:4}"; do
        if [[ ! -f "$secrets_dir/$secret" ]]; then
            missing+=("$secret")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Missing required secrets: ${missing[*]}"
        log_info "Copy from .example files and add your values"
    else
        log_success "All required secrets configured"
    fi
}

setup_env_file() {
    log_info "Setting up environment file..."
    
    local env_file="$PROJECT_DIR/.env"
    local env_example="$PROJECT_DIR/.env.example"
    
    if [[ -f "$env_file" ]]; then
        log_warn ".env file already exists"
        read -rp "Overwrite? [y/N] " response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            log_info "Keeping existing .env file"
            return 0
        fi
    fi
    
    if [[ -f "$env_example" ]]; then
        cp "$env_example" "$env_file"
        log_success "Created .env file from template"
        log_info "Please edit .env with your configuration"
    else
        # Create basic .env
        cat > "$env_file" << 'EOF'
# Delta Neutral Bot Environment Configuration

# Asgard API
ASGARD_API_KEY=
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Solana Wallet (ed25519)
SOLANA_PRIVATE_KEY=

# Hyperliquid (secp256k1)
HYPERLIQUID_WALLET_ADDRESS=
HYPERLIQUID_PRIVATE_KEY=

# Admin Controls
ADMIN_API_KEY=

# Optional: Custom Arbitrum RPC
ARBITRUM_RPC_URL=https://arb1.arbitrum.io/rpc

# Logging
LOG_LEVEL=INFO

# Bot Configuration
BOT_ENV=production
SHADOW_MODE=false
EOF
        log_success "Created default .env file"
    fi
}

check_docker() {
    log_info "Checking Docker installation..."
    
    if command -v docker &> /dev/null; then
        local docker_version
        docker_version=$(docker --version)
        log_success "Docker installed: $docker_version"
        
        if command -v docker-compose &> /dev/null; then
            local compose_version
            compose_version=$(docker-compose --version)
            log_success "Docker Compose installed: $compose_version"
        else
            log_warn "Docker Compose not found (optional for containerized deployment)"
        fi
    else
        log_warn "Docker not installed (optional for containerized deployment)"
        log_info "Install Docker: https://docs.docker.com/get-docker/"
    fi
}

run_validation() {
    log_info "Running validation tests..."
    
    cd "$PROJECT_DIR"
    
    # shellcheck source=/dev/null
    source .venv/bin/activate
    
    if python -m pytest tests/ -q --tb=short; then
        log_success "All tests passed"
    else
        log_error "Tests failed - please check the output above"
        return 1
    fi
}

print_summary() {
    echo ""
    echo "========================================"
    echo "  Setup Complete!"
    echo "========================================"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Configure your secrets:"
    echo "   cd $PROJECT_DIR/secrets"
    echo "   cp *.example <filename>"
    echo "   # Edit each file with your actual values"
    echo ""
    echo "2. Activate virtual environment:"
    echo "   source $PROJECT_DIR/.venv/bin/activate"
    echo ""
    echo "3. Run tests:"
    echo "   pytest tests/ -v"
    echo ""
    echo "4. Deploy with Docker:"
    echo "   $PROJECT_DIR/scripts/deploy.sh"
    echo ""
    echo "5. Or run locally:"
    echo "   python -m src.main"
    echo ""
    echo "Documentation:"
    echo "   README.md          - Project overview"
    echo "   tracker.md         - Implementation status"
    echo "   spec.md            - Technical specification"
    echo "   SECURITY.md        - Security guidelines"
    echo ""
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo "========================================"
    echo "  Delta Neutral Bot - Setup Script"
    echo "========================================"
    echo ""
    
    check_system
    setup_directories
    setup_venv
    setup_secrets
    setup_env_file
    check_docker
    
    # Ask before running tests
    echo ""
    read -rp "Run validation tests now? [Y/n] " response
    if [[ ! "$response" =~ ^[Nn]$ ]]; then
        run_validation
    fi
    
    print_summary
}

# Show help
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << EOF
Delta Neutral Bot Setup Script

Usage: $0 [options]

This script sets up the development environment for the Delta Neutral Bot.

Steps performed:
  1. Check system requirements (Python 3.9+)
  2. Create directory structure
  3. Setup Python virtual environment
  4. Install dependencies
  5. Setup secrets directory with examples
  6. Create .env configuration file
  7. Check Docker installation
  8. Run validation tests (optional)

Options:
  -h, --help    Show this help message

Examples:
  $0            # Run full setup

EOF
    exit 0
fi

main "$@"
