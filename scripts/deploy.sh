#!/bin/bash
# Delta Neutral Funding Rate Arbitrage Bot - Deployment Script
# Usage: ./deploy.sh [environment] [options]

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/docker"
COMPOSE_FILE="$DOCKER_DIR/docker-compose.yml"

# Default values
ENVIRONMENT="${1:-production}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BUILD_ONLY="${BUILD_ONLY:-false}"
SKIP_TESTS="${SKIP_TESTS:-false}"

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

check_dependencies() {
    log_info "Checking dependencies..."
    
    local deps=("docker" "docker-compose")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            log_error "$dep is required but not installed"
            exit 1
        fi
    done
    
    # Check Docker daemon
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    log_success "All dependencies available"
}

check_secrets() {
    log_info "Checking secrets configuration..."
    
    local secrets_dir="$PROJECT_DIR/secrets"
    local required_secrets=(
        "asgard_api_key.txt"
        "solana_private_key.txt"
        "hyperliquid_private_key.txt"
        "hyperliquid_wallet_address.txt"
    )
    
    local missing=()
    for secret in "${required_secrets[@]}"; do
        if [[ ! -f "$secrets_dir/$secret" ]]; then
            missing+=("$secret")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Missing secret files: ${missing[*]}"
        log_warn "Deployment may fail if environment variables are not set"
    else
        log_success "All required secrets found"
    fi
}

load_env() {
    log_info "Loading environment configuration..."
    
    local env_file="$PROJECT_DIR/.env"
    if [[ -f "$env_file" ]]; then
        # shellcheck source=/dev/null
        set -a
        source "$env_file"
        set +a
        log_success "Loaded environment from $env_file"
    else
        log_warn "No .env file found, relying on environment variables"
    fi
}

run_tests() {
    if [[ "$SKIP_TESTS" == "true" ]]; then
        log_warn "Skipping tests (SKIP_TESTS=true)"
        return 0
    fi
    
    log_info "Running tests..."
    
    cd "$PROJECT_DIR"
    
    if ! python -m pytest tests/ -q --tb=short; then
        log_error "Tests failed! Aborting deployment."
        exit 1
    fi
    
    log_success "All tests passed"
}

build_image() {
    log_info "Building Docker image (target: $ENVIRONMENT)..."
    
    local target="production"
    if [[ "$ENVIRONMENT" == "development" ]]; then
        target="development"
    fi
    
    cd "$PROJECT_DIR"
    
    docker build \
        --target "$target" \
        -t "delta-neutral-bot:$IMAGE_TAG" \
        -f "$DOCKER_DIR/Dockerfile" \
        --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
        .
    
    log_success "Image built successfully: delta-neutral-bot:$IMAGE_TAG"
}

deploy() {
    log_info "Deploying to $ENVIRONMENT environment..."
    
    cd "$DOCKER_DIR"
    
    # Pull latest images
    log_info "Pulling latest base images..."
    docker-compose -f "$COMPOSE_FILE" pull 2>/dev/null || true
    
    # Build and start services
    local profile=""
    if [[ "$ENVIRONMENT" == "development" ]]; then
        profile="--profile dev"
    elif [[ "$ENVIRONMENT" == "shadow" ]]; then
        profile="--profile shadow"
    fi
    
    # shellcheck disable=SC2086
    docker-compose -f "$COMPOSE_FILE" $profile up -d --build
    
    log_success "Deployment complete!"
}

health_check() {
    log_info "Running health check..."
    
    local retries=10
    local delay=5
    
    for ((i=1; i<=retries; i++)); do
        if docker-compose -f "$COMPOSE_FILE" ps | grep -q "healthy"; then
            log_success "Services are healthy"
            return 0
        fi
        
        log_info "Waiting for services to be healthy (attempt $i/$retries)..."
        sleep $delay
    done
    
    log_error "Health check failed after $retries attempts"
    log_info "Check logs with: docker-compose -f $COMPOSE_FILE logs"
    return 1
}

show_status() {
    log_info "Deployment Status:"
    echo ""
    docker-compose -f "$COMPOSE_FILE" ps
    echo ""
    
    log_info "Resource Usage:"
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | grep "delta-neutral" || true
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo "========================================"
    echo "  Delta Neutral Bot - Deployment Script"
    echo "  Environment: $ENVIRONMENT"
    echo "  Image Tag: $IMAGE_TAG"
    echo "========================================"
    echo ""
    
    # Pre-deployment checks
    check_dependencies
    check_secrets
    load_env
    
    # Run tests
    run_tests
    
    # Build image
    build_image
    
    # Exit if build-only mode
    if [[ "$BUILD_ONLY" == "true" ]]; then
        log_info "Build-only mode, skipping deployment"
        exit 0
    fi
    
    # Deploy
    deploy
    
    # Health check
    health_check
    
    # Show status
    show_status
    
    echo ""
    log_success "Deployment completed successfully!"
    echo ""
    echo "Useful commands:"
    echo "  View logs:   docker-compose -f $COMPOSE_FILE logs -f"
    echo "  Stop:        docker-compose -f $COMPOSE_FILE down"
    echo "  Restart:     docker-compose -f $COMPOSE_FILE restart"
}

# =============================================================================
# Script Entry Point
# =============================================================================

# Show help
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << EOF
Delta Neutral Bot Deployment Script

Usage: $0 [environment] [options]

Environments:
  production    Deploy production bot (default)
  development   Deploy development/testing environment
  shadow        Deploy shadow trading mode

Options (via environment variables):
  IMAGE_TAG=tag        Docker image tag (default: latest)
  BUILD_ONLY=true      Only build, don't deploy
  SKIP_TESTS=true      Skip running tests before deployment

Examples:
  $0                                    # Deploy production
  $0 development                        # Deploy development
  $0 shadow                             # Deploy shadow mode
  BUILD_ONLY=true $0                    # Build only
  SKIP_TESTS=true $0 production         # Skip tests

EOF
    exit 0
fi

# Handle arguments
case "${1:-production}" in
    production|development|shadow)
        main
        ;;
    *)
        log_error "Unknown environment: $1"
        echo "Valid environments: production, development, shadow"
        exit 1
        ;;
esac
