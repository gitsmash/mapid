#!/bin/bash

# Mapid Service Management Script
# Usage: ./mapid.sh {start|stop|restart|status|logs|health}

set -e

# Configuration
SERVICE_NAME="mapid"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${APP_DIR}/.${SERVICE_NAME}.pid"
LOG_FILE="${APP_DIR}/logs/${SERVICE_NAME}.log"
ERROR_LOG_FILE="${APP_DIR}/logs/${SERVICE_NAME}_error.log"
VENV_DIR="${APP_DIR}/.venv"
PYTHON_CMD="uv run python"
APP_FILE="app.py"
HOST="0.0.0.0"
PORT="8000"
HEALTH_CHECK_URL="http://localhost:${PORT}/"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create logs directory if it doesn't exist
mkdir -p "${APP_DIR}/logs"

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# Function to check if service is running
is_running() {
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            # PID file exists but process is not running, clean up
            rm -f "$PID_FILE"
            return 1
        fi
    else
        return 1
    fi
}

# Function to get service PID
get_pid() {
    if [[ -f "$PID_FILE" ]]; then
        cat "$PID_FILE"
    else
        echo ""
    fi
}

# Function to start the service
start_service() {
    if is_running; then
        print_status "$YELLOW" "⚠️  ${SERVICE_NAME} is already running (PID: $(get_pid))"
        return 1
    fi

    print_status "$BLUE" "🚀 Starting ${SERVICE_NAME}..."
    
    # Check if .env file exists
    if [[ ! -f "${APP_DIR}/.env" ]]; then
        print_status "$RED" "❌ .env file not found. Please copy .env.example to .env and configure it."
        return 1
    fi
    
    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        print_status "$RED" "❌ uv is not installed. Please install uv first."
        print_status "$BLUE" "💡 Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        return 1
    fi
    
    # Ensure virtual environment exists
    if [[ ! -d "$VENV_DIR" ]]; then
        print_status "$BLUE" "🔧 Creating virtual environment..."
        cd "$APP_DIR"
        uv venv
        if [[ ! -d "$VENV_DIR" ]]; then
            print_status "$RED" "❌ Failed to create virtual environment"
            return 1
        fi
    fi
    
    # Ensure dependencies are installed in venv
    print_status "$BLUE" "📦 Ensuring dependencies are installed..."
    cd "$APP_DIR"
    
    # Create lockfile if it doesn't exist
    if [[ ! -f "uv.lock" ]]; then
        print_status "$BLUE" "🔧 Creating missing lockfile..."
        uv lock
        if [[ ! -f "uv.lock" ]]; then
            print_status "$RED" "❌ Failed to create lockfile"
            return 1
        fi
    fi
    
    # Sync dependencies
    uv sync --frozen
    
    # Start the service in background
    cd "$APP_DIR"
    
    # Export environment variables from .env file
    if [[ -f .env ]]; then
        export $(grep -v '^#' .env | xargs)
    fi
    
    # Start the Flask application
    nohup $PYTHON_CMD "$APP_FILE" > "$LOG_FILE" 2> "$ERROR_LOG_FILE" &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    
    # Wait a moment and check if the process started successfully
    sleep 2
    if is_running; then
        print_status "$GREEN" "✅ ${SERVICE_NAME} started successfully (PID: $pid)"
        print_status "$BLUE" "🌐 Service available at: http://localhost:${PORT}"
        print_status "$BLUE" "📝 Logs: ${LOG_FILE}"
        print_status "$BLUE" "❌ Errors: ${ERROR_LOG_FILE}"
        return 0
    else
        print_status "$RED" "❌ Failed to start ${SERVICE_NAME}"
        if [[ -f "$ERROR_LOG_FILE" ]]; then
            print_status "$RED" "Error details:"
            tail -n 10 "$ERROR_LOG_FILE"
        fi
        return 1
    fi
}

# Function to stop the service
stop_service() {
    if ! is_running; then
        print_status "$YELLOW" "⚠️  ${SERVICE_NAME} is not running"
        return 1
    fi

    local pid=$(get_pid)
    print_status "$BLUE" "🛑 Stopping ${SERVICE_NAME} (PID: $pid)..."
    
    # Try graceful shutdown first
    kill "$pid" 2>/dev/null
    
    # Wait for graceful shutdown
    local count=0
    while is_running && [[ $count -lt 10 ]]; do
        sleep 1
        ((count++))
    done
    
    # Force kill if still running
    if is_running; then
        print_status "$YELLOW" "⚠️  Graceful shutdown failed, forcing termination..."
        kill -9 "$pid" 2>/dev/null
        sleep 1
    fi
    
    # Clean up PID file
    rm -f "$PID_FILE"
    
    if ! is_running; then
        print_status "$GREEN" "✅ ${SERVICE_NAME} stopped successfully"
        return 0
    else
        print_status "$RED" "❌ Failed to stop ${SERVICE_NAME}"
        return 1
    fi
}

# Function to restart the service
restart_service() {
    print_status "$BLUE" "🔄 Restarting ${SERVICE_NAME}..."
    stop_service
    sleep 2
    start_service
}

# Function to show service status
show_status() {
    if is_running; then
        local pid=$(get_pid)
        local uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs)
        local memory=$(ps -o rss= -p "$pid" 2>/dev/null | xargs)
        local cpu=$(ps -o %cpu= -p "$pid" 2>/dev/null | xargs)
        
        print_status "$GREEN" "✅ ${SERVICE_NAME} is running"
        echo "   PID: $pid"
        echo "   Uptime: $uptime"
        echo "   Memory: ${memory}KB"
        echo "   CPU: ${cpu}%"
        echo "   URL: http://localhost:${PORT}"
        echo "   Log file: $LOG_FILE"
        echo "   Error log: $ERROR_LOG_FILE"
    else
        print_status "$RED" "❌ ${SERVICE_NAME} is not running"
    fi
}

# Function to show logs
show_logs() {
    local lines=${2:-50}
    local log_type=${1:-"all"}
    
    case $log_type in
        "error"|"errors")
            if [[ -f "$ERROR_LOG_FILE" ]]; then
                print_status "$BLUE" "📋 Last $lines lines of error log:"
                tail -n "$lines" "$ERROR_LOG_FILE"
            else
                print_status "$YELLOW" "⚠️  Error log file not found"
            fi
            ;;
        "main"|"app")
            if [[ -f "$LOG_FILE" ]]; then
                print_status "$BLUE" "📋 Last $lines lines of application log:"
                tail -n "$lines" "$LOG_FILE"
            else
                print_status "$YELLOW" "⚠️  Application log file not found"
            fi
            ;;
        "all"|*)
            if [[ -f "$LOG_FILE" ]]; then
                print_status "$BLUE" "📋 Last $lines lines of application log:"
                tail -n "$lines" "$LOG_FILE"
                echo ""
            fi
            if [[ -f "$ERROR_LOG_FILE" ]] && [[ -s "$ERROR_LOG_FILE" ]]; then
                print_status "$BLUE" "📋 Last $lines lines of error log:"
                tail -n "$lines" "$ERROR_LOG_FILE"
            fi
            ;;
    esac
}

# Function to follow logs in real-time
follow_logs() {
    local log_type=${1:-"all"}
    
    print_status "$BLUE" "📋 Following logs... (Press Ctrl+C to stop)"
    
    case $log_type in
        "error"|"errors")
            if [[ -f "$ERROR_LOG_FILE" ]]; then
                tail -f "$ERROR_LOG_FILE"
            else
                print_status "$YELLOW" "⚠️  Error log file not found"
            fi
            ;;
        "main"|"app")
            if [[ -f "$LOG_FILE" ]]; then
                tail -f "$LOG_FILE"
            else
                print_status "$YELLOW" "⚠️  Application log file not found"
            fi
            ;;
        "all"|*)
            if [[ -f "$LOG_FILE" ]] && [[ -f "$ERROR_LOG_FILE" ]]; then
                tail -f "$LOG_FILE" "$ERROR_LOG_FILE"
            elif [[ -f "$LOG_FILE" ]]; then
                tail -f "$LOG_FILE"
            elif [[ -f "$ERROR_LOG_FILE" ]]; then
                tail -f "$ERROR_LOG_FILE"
            else
                print_status "$YELLOW" "⚠️  No log files found"
            fi
            ;;
    esac
}

# Function to check service health
health_check() {
    if ! is_running; then
        print_status "$RED" "❌ Service is not running"
        return 1
    fi
    
    print_status "$BLUE" "🏥 Checking service health..."
    
    # Check if port is listening (try multiple methods for compatibility)
    port_listening=false
    
    # Try lsof (works on macOS)
    if command -v lsof &> /dev/null; then
        if lsof -i ":${PORT}" > /dev/null 2>&1; then
            port_listening=true
        fi
    fi
    
    # Try netstat if lsof didn't work
    if [ "$port_listening" = false ] && command -v netstat &> /dev/null; then
        if netstat -ln 2>/dev/null | grep ":${PORT} " > /dev/null; then
            port_listening=true
        fi
    fi
    
    # Try ss if neither worked
    if [ "$port_listening" = false ] && command -v ss &> /dev/null; then
        if ss -ln 2>/dev/null | grep ":${PORT} " > /dev/null; then
            port_listening=true
        fi
    fi
    
    if [ "$port_listening" = false ]; then
        print_status "$RED" "❌ Service is not listening on port ${PORT}"
        return 1
    fi
    
    # Check HTTP response
    if command -v curl &> /dev/null; then
        local http_status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$HEALTH_CHECK_URL" 2>/dev/null || echo "000")
        if [[ "$http_status" == "200" ]]; then
            print_status "$GREEN" "✅ Service is healthy (HTTP $http_status)"
            return 0
        else
            print_status "$RED" "❌ Service health check failed (HTTP $http_status)"
            return 1
        fi
    else
        print_status "$GREEN" "✅ Service is running and listening on port ${PORT}"
        print_status "$YELLOW" "⚠️  Install curl for full health checks"
        return 0
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 {start|stop|restart|status|logs|follow|health}"
    echo ""
    echo "Commands:"
    echo "  start          Start the ${SERVICE_NAME} service"
    echo "  stop           Stop the ${SERVICE_NAME} service"
    echo "  restart        Restart the ${SERVICE_NAME} service"
    echo "  status         Show service status and information"
    echo "  logs [type]    Show recent logs (types: all, main, error) [default: all]"
    echo "  follow [type]  Follow logs in real-time [default: all]"
    echo "  health         Check service health"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start the service"
    echo "  $0 logs error              # Show error logs"
    echo "  $0 follow main             # Follow application logs"
    echo ""
}

# Main script logic
case "${1:-}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "${2:-all}" "${3:-50}"
        ;;
    follow)
        follow_logs "${2:-all}"
        ;;
    health)
        health_check
        ;;
    *)
        show_usage
        exit 1
        ;;
esac

exit $?