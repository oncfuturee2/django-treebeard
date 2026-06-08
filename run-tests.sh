#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

VALID_DBS="sqlite postgres mysql mssql"
VALID_PYS="310 314 current"
VALID_DJS="52 60"

DB=""
PY=""
DJ=""
COVERAGE=0
START_DB=0
STOP_DB=0
PYTEST_ARGS=()

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [PYTEST_ARGS...]

Run django-treebeard tests via tox with multi-database support.

Options:
  -d, --db DB        Database type: sqlite, postgres, mysql, mssql, all (default: all)
  -p, --python PY    Python version: 310, 314, current (default: current)
  -j, --django DJ    Django version: 52, 60, all (default: all)
  -c, --coverage     Enable coverage fail-under check (like CI does for postgres)
  --start-db         Start database containers before running tests
  --stop-db          Stop database containers after running tests
  -h, --help         Show this help message

Environment:
  Database connection variables are loaded from ${ENV_FILE}
  and exported for tox passenv. You can override them by
  setting them in the shell before running this script.

Examples:
  $(basename "$0") --db sqlite --django 52
  $(basename "$0") --db postgres --python 314 --django 60 --coverage
  $(basename "$0") --db mysql --start-db
  $(basename "$0") --db all --python current --django all
  $(basename "$0") --db postgres --django 52 -- --cov-fail-under 96
EOF
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

validate_choice() {
    local value="$1" valid_choices="$2" label="$3"
    for c in $valid_choices; do
        if [ "$value" = "$c" ]; then
            return 0
        fi
    done
    die "Invalid $label '$value'. Valid choices: $valid_choices"
}

load_env() {
    if [ -f "$ENV_FILE" ]; then
        set -a
        source "$ENV_FILE"
        set +a
    else
        echo "WARNING: ${ENV_FILE} not found. Using existing environment variables." >&2
    fi
    export DATABASE_HOST DATABASE_USER_POSTGRES DATABASE_USER_MYSQL \
           DATABASE_PASSWORD DATABASE_PORT_POSTGRES DATABASE_PORT_MYSQL \
           DATABASE_PORT_MSSQL
}

start_db() {
    local services=()
    if [ -n "${DB}" ] && [ "${DB}" != "all" ]; then
        case "${DB}" in
            postgres) services=(postgres) ;;
            mysql)    services=(mysql) ;;
            mssql)    services=(mssql) ;;
        esac
    else
        services=(postgres mysql mssql)
    fi

    if [ ${#services[@]} -eq 0 ]; then
        echo "No database containers needed for SQLite."
        return 0
    fi

    echo "Starting database containers: ${services[*]}"
    docker compose -f "${SCRIPT_DIR}/docker-compose.yml" up -d "${services[@]}"

    echo "Waiting for containers to become healthy..."
    for svc in "${services[@]}"; do
        echo "  Waiting for ${svc}..."
        local max_attempts=30
        local attempt=0
        while [ $attempt -lt $max_attempts ]; do
            local health
            health=$(docker compose -f "${SCRIPT_DIR}/docker-compose.yml" \
                         ps --format json "$svc" 2>/dev/null \
                         | grep -o '"Health":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
            if [ "$health" = "healthy" ]; then
                echo "  ${svc} is healthy."
                break
            fi
            attempt=$((attempt + 1))
            sleep 2
        done
        if [ $attempt -ge $max_attempts ]; then
            echo "WARNING: ${svc} did not become healthy within timeout." >&2
        fi
    done
}

stop_db() {
    echo "Stopping database containers..."
    docker compose -f "${SCRIPT_DIR}/docker-compose.yml" down
}

build_tox_env() {
    local py="$1" dj="$2" db="$3"
    local py_part
    if [ "$py" = "current" ]; then
        py_part="py"
    else
        py_part="py${py}"
    fi
    echo "${py_part}-dj${dj}-${db}"
}

is_valid_combo() {
    local py="$1" dj="$2"
    if [ "$py" = "310" ] && [ "$dj" = "60" ]; then
        return 1
    fi
    return 0
}

run_tox_env() {
    local tox_env="$1"
    shift
    local extra_args=("$@")

    echo ""
    echo "=========================================="
    echo "  Running: tox -e ${tox_env} ${extra_args[*]}"
    echo "=========================================="
    tox -e "$tox_env" "${extra_args[@]}"
}

main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -d|--db)
                [ $# -lt 2 ] && die "Option $1 requires an argument"
                DB="$2"
                shift 2
                ;;
            -p|--python)
                [ $# -lt 2 ] && die "Option $1 requires an argument"
                PY="$2"
                shift 2
                ;;
            -j|--django)
                [ $# -lt 2 ] && die "Option $1 requires an argument"
                DJ="$2"
                shift 2
                ;;
            -c|--coverage)
                COVERAGE=1
                shift
                ;;
            --start-db)
                START_DB=1
                shift
                ;;
            --stop-db)
                STOP_DB=1
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            --)
                shift
                PYTEST_ARGS=("$@")
                break
                ;;
            -*)
                die "Unknown option: $1"
                ;;
            *)
                PYTEST_ARGS=("$@")
                break
                ;;
        esac
    done

    : "${DB:=all}"
    : "${PY:=current}"
    : "${DJ:=all}"

    if [ "$DB" != "all" ]; then
        validate_choice "$DB" "$VALID_DBS" "database"
    fi
    if [ "$PY" != "all" ]; then
        validate_choice "$PY" "$VALID_PYS current" "python version"
    fi
    if [ "$DJ" != "all" ]; then
        validate_choice "$DJ" "$VALID_DJS" "django version"
    fi

    load_env

    if [ "$START_DB" -eq 1 ]; then
        start_db
    fi

    local dbs=()
    if [ "$DB" = "all" ]; then
        dbs=(sqlite postgres mysql mssql)
    else
        dbs=("$DB")
    fi

    local pys=()
    if [ "$PY" = "all" ]; then
        pys=(310 314)
    else
        pys=("$PY")
    fi

    local djs=()
    if [ "$DJ" = "all" ]; then
        djs=(52 60)
    else
        djs=("$DJ")
    fi

    local failed=()
    local succeeded=()

    for db in "${dbs[@]}"; do
        for py in "${pys[@]}"; do
            for dj in "${djs[@]}"; do
                if ! is_valid_combo "$py" "$dj"; then
                    echo ""
                    echo "Skipping py${py}-dj${dj}-${db}: Python 3.10 is incompatible with Django 6.0"
                    continue
                fi

                local tox_env
                tox_env=$(build_tox_env "$py" "$dj" "$db")

                local extra_args=("${PYTEST_ARGS[@]}")
                if [ "$COVERAGE" -eq 1 ] && [ "$db" = "postgres" ]; then
                    extra_args+=(--cov-fail-under 96)
                fi

                if run_tox_env "$tox_env" "${extra_args[@]}"; then
                    succeeded+=("$tox_env")
                else
                    failed+=("$tox_env")
                fi
            done
        done
    done

    echo ""
    echo "=========================================="
    echo "  Test Summary"
    echo "=========================================="
    if [ ${#succeeded[@]} -gt 0 ]; then
        echo "  PASSED:"
        for env in "${succeeded[@]}"; do
            echo "    ✓ $env"
        done
    fi
    if [ ${#failed[@]} -gt 0 ]; then
        echo "  FAILED:"
        for env in "${failed[@]}"; do
            echo "    ✗ $env"
        done
    fi

    if [ "$STOP_DB" -eq 1 ]; then
        stop_db
    fi

    if [ ${#failed[@]} -gt 0 ]; then
        exit 1
    fi
}

main "$@"
