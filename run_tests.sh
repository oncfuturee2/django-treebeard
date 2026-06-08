#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Run django-treebeard tests against different database backends using tox.

Options:
  -d, --db TYPE        Database type: sqlite, postgres, mysql, mssql, all
                       Can be a comma-separated list (e.g. "postgres,mysql")
                       Default: all

  -j, --django VER     Django version: 52, 60, all
                       Default: all

  -p, --python VER     Python version to use for tox: 3.10, 3.14
                       Uses the current Python interpreter by default

  --up                 Start required Docker service containers before testing
                       (waits for health checks to pass)

  --down               Stop Docker service containers after testing

  --extra-args ARGS    Extra arguments to pass through to pytest
                       (e.g. --extra-args="-x --no-header")

  --cov-fail-under N   Set --cov-fail-under threshold (default: none)
                       CI uses 96 for postgres coverage check

  -h, --help           Show this help message and exit

Environment:
  The script sources .env from the project root if it exists.
  Variables required by docker-compose and tox are set automatically.
  See .env for the full list of configurable database connection parameters.

Database-to-service mapping (for Docker):
  sqlite    → no Docker service needed (in-memory)
  postgres  → postgres service (port 5432, ltree extension auto-initialized)
  mysql     → mysql service (port 3306)
  mssql     → mssql service (port 1433, requires ODBC Driver 18 on host)

Examples:
  $0 --db sqlite
  $0 --db postgres --up
  $0 --db mysql --django 52 --up
  $0 --db postgres,mysql --django all --up
  $0 --db postgres --django 52 --up --cov-fail-under 96
  $0 --down
EOF
}

load_env() {
    if [ -f "$SCRIPT_DIR/.env" ]; then
        set -a
        source "$SCRIPT_DIR/.env"
        set +a
    fi
}

DB_TO_SERVICE() {
    case "$1" in
        postgres) echo "postgres" ;;
        mysql)    echo "mysql" ;;
        mssql)    echo "mssql" ;;
        *)        echo "" ;;
    esac
}

start_services() {
    local dbs="$1"
    local services=()
    local db

    IFS=',' read -ra DB_ARRAY <<< "$dbs"
    for db in "${DB_ARRAY[@]}"; do
        local svc
        svc=$(DB_TO_SERVICE "$db")
        if [ -n "$svc" ]; then
            services+=("$svc")
        fi
    done

    if [ ${#services[@]} -eq 0 ]; then
        log_info "No Docker services needed for the selected databases."
        return
    fi

    local unique_services=()
    local seen
    declare -A seen
    for svc in "${services[@]}"; do
        if [ -z "${seen[$svc]:-}" ]; then
            unique_services+=("$svc")
            seen[$svc]=1
        fi
    done

    log_step "Starting Docker services: ${unique_services[*]}"
    docker compose up -d --wait "${unique_services[@]}"
    log_info "All services are healthy and ready."
}

stop_services() {
    log_step "Stopping all Docker services..."
    docker compose down
    log_info "All services stopped."
}

run_tox() {
    local django_ver="$1"
    local db_type="$2"
    local extra_args="$3"
    local cov_fail="$4"
    local python_bin="$5"

    local tox_env="py-dj${django_ver}-${db_type}"
    local db_display="$db_type"

    log_step "Running: tox -e $tox_env"

    local cmd_args=("-e" "$tox_env")
    if [ -n "$extra_args" ] || [ -n "$cov_fail" ]; then
        cmd_args+=("--")
        [ -n "$extra_args" ] && cmd_args+=($extra_args)
        [ -n "$cov_fail" ] && cmd_args+=("--cov-fail-under=$cov_fail")
    fi

    if [ -n "$python_bin" ]; then
        "$python_bin" -m tox "${cmd_args[@]}"
    else
        tox "${cmd_args[@]}"
    fi
}

main() {
    local DB_TYPES="all"
    local DJANGO_VERSIONS="all"
    local PYTHON_BIN=""
    local DO_UP=false
    local DO_DOWN=false
    local EXTRA_ARGS=""
    local COV_FAIL_UNDER=""

    while [ $# -gt 0 ]; do
        case "$1" in
            -d|--db)
                DB_TYPES="$2"
                shift 2
                ;;
            -j|--django)
                DJANGO_VERSIONS="$2"
                shift 2
                ;;
            -p|--python)
                local pyver="$2"
                PYTHON_BIN="python${pyver}"
                if ! command -v "$PYTHON_BIN" &>/dev/null; then
                    log_error "Python $pyver not found: $PYTHON_BIN"
                    exit 1
                fi
                shift 2
                ;;
            --up)
                DO_UP=true
                shift
                ;;
            --down)
                DO_DOWN=true
                shift
                ;;
            --extra-args)
                EXTRA_ARGS="$2"
                shift 2
                ;;
            --cov-fail-under)
                COV_FAIL_UNDER="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    load_env

    if [ "$DB_TYPES" = "all" ]; then
        DB_TYPES="sqlite,postgres,mysql,mssql"
    fi

    if [ "$DJANGO_VERSIONS" = "all" ]; then
        DJANGO_VERSIONS="52,60"
    fi

    IFS=',' read -ra DJANGO_ARRAY <<< "$DJANGO_VERSIONS"
    IFS=',' read -ra DB_ARRAY <<< "$DB_TYPES"

    local valid_dbs=("sqlite" "postgres" "mysql" "mssql")
    local valid_djs=("52" "60")

    for db in "${DB_ARRAY[@]}"; do
        local found=false
        for v in "${valid_dbs[@]}"; do
            [ "$db" = "$v" ] && found=true && break
        done
        if [ "$found" = false ]; then
            log_error "Invalid database type: $db (valid: ${valid_dbs[*]})"
            exit 1
        fi
    done

    for dj in "${DJANGO_ARRAY[@]}"; do
        local found=false
        for v in "${valid_djs[@]}"; do
            [ "$dj" = "$v" ] && found=true && break
        done
        if [ "$found" = false ]; then
            log_error "Invalid Django version: $dj (valid: ${valid_djs[*]})"
            exit 1
        fi
    done

    if [ "$DO_UP" = true ]; then
        start_services "$DB_TYPES"
    fi

    local exit_code=0

    for dj in "${DJANGO_ARRAY[@]}"; do
        for db in "${DB_ARRAY[@]}"; do
            echo ""
            log_info "=== Testing: Django $dj + $db ==="
            if ! run_tox "$dj" "$db" "$EXTRA_ARGS" "$COV_FAIL_UNDER" "$PYTHON_BIN"; then
                log_error "Tests failed: Django $dj + $db"
                exit_code=1
            fi
        done
    done

    if [ "$DO_DOWN" = true ]; then
        stop_services
    fi

    if [ "$exit_code" -eq 0 ]; then
        echo ""
        log_info "All test combinations passed!"
    else
        echo ""
        log_error "Some test combinations failed."
    fi

    exit $exit_code
}

main "$@"