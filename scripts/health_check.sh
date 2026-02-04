#!/bin/bash
# Delta Neutral Funding Rate Arbitrage Bot - Health Check Script
# Usage: ./health_check.sh [options]

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/docker"
COMPOSE_FILE="$DOCKER_DIR/docker-compose.yml"

# Health check settings
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-30}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
LOG_FILE="${PROJECT_DIR}/logs/health_check.log"

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
    local msg="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [INFO] $1"
    echo -e "${BLUE}${msg}${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

log_success() {
    local msg="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [SUCCESS] $1"
    echo -e "${GREEN}${msg}${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

log_warn() {
    local msg="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [WARN] $1"
    echo -e "${YELLOW}${msg}${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

log_error() {
    local msg="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] [ERROR] $1"
    echo -e "${RED}${msg}${NC}"
    echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

send_alert() {
    local message="$1"
    local severity="${2:-warning}"
    
    if [[ -n "$ALERT_WEBHOOK_URL" ]]; then
        curl -s -X POST \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"[$severity] Delta Neutral Bot: $message\",\"timestamp\":\"$(date -u +'%Y-%m-%dT%H:%M:%SZ')\"}" \
            "$ALERT_WEBHOOK_URL" &>/dev/null || true
    fi
}

# =============================================================================
# Health Check Functions
# =============================================================================

check_docker_service() {
    local service_name="${1:-bot}"
    
    log_info "Checking Docker service: $service_name"
    
    if ! docker-compose -f "$COMPOSE_FILE" ps "$service_name" | grep -q "Up"; then
        log_error "Service $service_name is not running"
        send_alert "Service $service_name is down" "critical"
        return 1
    fi
    
    local health_status
    health_status=$(docker-compose -f "$COMPOSE_FILE" ps "$service_name" | grep -o "(healthy)\|(unhealthy)\|(starting)" || echo "unknown")
    
    case "$health_status" in
        "(healthy)")
            log_success "Service $service_name is healthy"
            return 0
            ;;
        "(unhealthy)")
            log_error "Service $service_name is unhealthy"
            send_alert "Service $service_name is unhealthy" "critical"
            return 1
            ;;
        "(starting)")
            log_warn "Service $service_name is still starting"
            return 0
            ;;
        *)
            log_warn "Service $service_name health status: $health_status"
            return 0
            ;;
    esac
}

check_disk_space() {
    log_info "Checking disk space..."
    
    local usage
    usage=$(df -h "$PROJECT_DIR" | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [[ "$usage" -gt 90 ]]; then
        log_error "Disk usage is critical: ${usage}%"
        send_alert "Disk usage critical: ${usage}%" "critical"
        return 1
    elif [[ "$usage" -gt 80 ]]; then
        log_warn "Disk usage is high: ${usage}%"
        send_alert "Disk usage high: ${usage}%" "warning"
        return 0
    else
        log_success "Disk usage: ${usage}%"
        return 0
    fi
}

check_memory_usage() {
    log_info "Checking memory usage..."
    
    # Check if we're in a container
    if [[ -f /sys/fs/cgroup/memory/memory.usage_in_bytes ]]; then
        local usage_bytes limit_bytes usage_pct
        usage_bytes=$(cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || echo 0)
        limit_bytes=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || echo 1)
        usage_pct=$((usage_bytes * 100 / limit_bytes))
        
        if [[ "$usage_pct" -gt 90 ]]; then
            log_error "Memory usage is critical: ${usage_pct}%"
            send_alert "Memory usage critical: ${usage_pct}%" "critical"
            return 1
        elif [[ "$usage_pct" -gt 80 ]]; then
            log_warn "Memory usage is high: ${usage_pct}%"
            return 0
        else
            log_success "Memory usage: ${usage_pct}%"
            return 0
        fi
    else
        # Host memory check
        local mem_info
        mem_info=$(free | grep Mem)
        local total=$(echo "$mem_info" | awk '{print $2}')
        local used=$(echo "$mem_info" | awk '{print $3}')
        local usage_pct=$((used * 100 / total))
        
        if [[ "$usage_pct" -gt 90 ]]; then
            log_warn "System memory usage: ${usage_pct}%"
            return 0
        else
            log_success "System memory usage: ${usage_pct}%"
            return 0
        fi
    fi
}

check_log_errors() {
    log_info "Checking for recent errors in logs..."
    
    local log_dir="$PROJECT_DIR/logs"
    local error_count=0
    
    if [[ -d "$log_dir" ]]; then
        # Count errors in last 5 minutes
        error_count=$(find "$log_dir" -name "*.log" -mmin -5 -exec grep -i "error\|exception\|critical" {} + 2>/dev/null | wc -l || echo 0)
    fi
    
    if [[ "$error_count" -gt 10 ]]; then
        log_error "High error count in recent logs: $error_count errors"
        send_alert "High error count: $error_count errors in last 5 min" "warning"
        return 1
    elif [[ "$error_count" -gt 0 ]]; then
        log_warn "Found $error_count errors in recent logs"
        return 0
    else
        log_success "No recent errors found"
        return 0
    fi
}

check_state_db() {
    log_info "Checking state database..."
    
    local state_db="$PROJECT_DIR/data/state.db"
    
    if [[ -f "$state_db" ]]; then
        local db_size
        db_size=$(stat -f%z "$state_db" 2>/dev/null || stat -c%s "$state_db" 2>/dev/null || echo 0)
        
        if [[ "$db_size" -gt 1073741824 ]]; then  # 1GB
            log_warn "State database is large: $((db_size / 1024 / 1024))MB"
        else
            log_success "State database size: $((db_size / 1024))KB"
        fi
        return 0
    else
        log_warn "State database not found (may not be initialized yet)"
        return 0
    fi
}

check_bot_process() {
    log_info "Checking bot process..."
    
    local bot_pid
    bot_pid=$(pgrep -f "python.*src.main" || echo "")
    
    if [[ -n "$bot_pid" ]]; then
        log_success "Bot process running (PID: $bot_pid)"
        
        # Check CPU usage
        local cpu_usage
        cpu_usage=$(ps -p "$bot_pid" -o %cpu= 2>/dev/null || echo "0")
        log_info "Bot CPU usage: ${cpu_usage}%"
        
        return 0
    else
        log_warn "Bot process not found (may be running in Docker)"
        return 0
    fi
}

# =============================================================================
# Main Health Check
# =============================================================================
run_health_check() {
    local failed=0
    
    echo "========================================"
    echo "  Health Check - $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
    echo "========================================"
    echo ""
    
    # Create logs directory if needed
    mkdir -p "$PROJECT_DIR/logs"
    
    # Run all checks
    check_docker_service "bot" || ((failed++))
    check_disk_space || ((failed++))
    check_memory_usage || ((failed++))
    check_log_errors || ((failed++))
    check_state_db || ((failed++))
    check_bot_process || ((failed++))
    
    echo ""
    if [[ "$failed" -eq 0 ]]; then
        log_success "All health checks passed"
        return 0
    else
        log_error "$failed health check(s) failed"
        return 1
    fi
}

# =============================================================================
# Continuous Monitoring Mode
# =============================================================================
monitor_mode() {
    log_info "Starting continuous health monitoring (interval: ${HEALTH_CHECK_INTERVAL}s)"
    
    while true; do
        run_health_check
        sleep "$HEALTH_CHECK_INTERVAL"
    done
}

# =============================================================================
# Main
# =============================================================================
main() {
    local command="${1:-check}"
    
    case "$command" in
        check)
            run_health_check
            ;;
        monitor)
            monitor_mode
            ;;
        *)
            echo "Unknown command: $command"
            echo "Usage: $0 [check|monitor]"
            exit 1
            ;;
    esac
}

# Show help
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << EOF
Delta Neutral Bot Health Check Script

Usage: $0 [command] [options]

Commands:
  check     Run single health check (default)
  monitor   Run continuous monitoring

Environment Variables:
  HEALTH_CHECK_INTERVAL    Check interval in seconds (default: 30)
  ALERT_WEBHOOK_URL        Webhook URL for alerts (optional)

Checks performed:
  - Docker service status
  - Disk space
  - Memory usage
  - Recent log errors
  - State database
  - Bot process

Examples:
  $0                        # Run single check
  $0 monitor                # Continuous monitoring
  HEALTH_CHECK_INTERVAL=60 $0 monitor   # Check every 60 seconds

EOF
    exit 0
fi

main "$@"
