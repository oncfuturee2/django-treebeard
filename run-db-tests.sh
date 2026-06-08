#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_FILE="$ROOT_DIR/.env.test"
FALLBACK_ENV_FILE="$ROOT_DIR/.env.test.example"
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
ENV_FILE=""
DB=""
PYTHON_VERSION=""
DJANGO_VERSION=""
SKIP_COMPOSE=0
ENFORCE_POSTGRES_COVERAGE=1
TOX_ARGS=()
PYTEST_ARGS=()

usage() {
    cat <<EOF
Usage: $(basename "$0") --db <sqlite|postgres|mysql|mssql> --python <3.10|3.14> --django <5.2|6.0> [options] [-- <pytest args>]

Options:
  --db, -d              Database backend to test.
  --python, -p          Python version factor for tox.
  --django, -j          Django version factor for tox.
  --env-file, -e        Env file to load for docker-compose and tox.
  --skip-compose        Skip docker-compose startup.
  --no-postgres-cov     Do not append --cov-fail-under 96 for postgres runs.
  --tox-arg VALUE       Extra argument forwarded to tox. Repeatable.
  --help, -h            Show this help message.
EOF
}

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

pick_env_file() {
    if [[ -n "$ENV_FILE" ]]; then
        [[ -f "$ENV_FILE" ]] || fail "Env file not found: $ENV_FILE"
        printf '%s\n' "$ENV_FILE"
        return
    fi

    if [[ -f "$DEFAULT_ENV_FILE" ]]; then
        printf '%s\n' "$DEFAULT_ENV_FILE"
        return
    fi

    [[ -f "$FALLBACK_ENV_FILE" ]] || fail "Fallback env file not found: $FALLBACK_ENV_FILE"
    printf '%s\n' "$FALLBACK_ENV_FILE"
}

load_env_file() {
    local file_path="$1"
    set -a
    . "$file_path"
    set +a
}

normalize_db() {
    case "$1" in
        sqlite)
            printf 'sqlite\n'
            ;;
        postgres|postgresql|psql)
            printf 'postgres\n'
            ;;
        mysql)
            printf 'mysql\n'
            ;;
        mssql|sqlserver)
            printf 'mssql\n'
            ;;
        *)
            fail "Unsupported database: $1"
            ;;
    esac
}

python_factor() {
    case "$1" in
        3.10|310)
            printf 'py310\n'
            ;;
        3.14|314)
            printf 'py314\n'
            ;;
        *)
            fail "Unsupported Python version: $1"
            ;;
    esac
}

django_factor() {
    case "$1" in
        5.2|52)
            printf 'dj52\n'
            ;;
        6.0|60)
            printf 'dj60\n'
            ;;
        *)
            fail "Unsupported Django version: $1"
            ;;
    esac
}

validate_matrix() {
    case "$1:$2" in
        3.10:6.0|3.10:60|310:6.0|310:60)
            fail 'The CI matrix excludes Python 3.10 with Django 6.0'
            ;;
    esac
}

start_service() {
    local env_file="$1"
    local db="$2"
    local service=""

    case "$db" in
        sqlite)
            return
            ;;
        postgres)
            service="postgres"
            ;;
        mysql)
            service="mysql"
            ;;
        mssql)
            service="mssql"
            ;;
    esac

    docker compose --env-file "$env_file" -f "$COMPOSE_FILE" up -d --wait "$service"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db|-d)
            [[ $# -ge 2 ]] || fail "Missing value for $1"
            DB="$2"
            shift 2
            ;;
        --python|-p)
            [[ $# -ge 2 ]] || fail "Missing value for $1"
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --django|-j)
            [[ $# -ge 2 ]] || fail "Missing value for $1"
            DJANGO_VERSION="$2"
            shift 2
            ;;
        --env-file|-e)
            [[ $# -ge 2 ]] || fail "Missing value for $1"
            if [[ "$2" = /* ]]; then
                ENV_FILE="$2"
            else
                ENV_FILE="$ROOT_DIR/$2"
            fi
            shift 2
            ;;
        --skip-compose)
            SKIP_COMPOSE=1
            shift
            ;;
        --no-postgres-cov)
            ENFORCE_POSTGRES_COVERAGE=0
            shift
            ;;
        --tox-arg)
            [[ $# -ge 2 ]] || fail "Missing value for $1"
            TOX_ARGS+=("$2")
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            PYTEST_ARGS=("$@")
            break
            ;;
        *)
            fail "Unknown argument: $1"
            ;;
    esac
done

[[ -n "$DB" ]] || fail "--db is required"
[[ -n "$PYTHON_VERSION" ]] || fail "--python is required"
[[ -n "$DJANGO_VERSION" ]] || fail "--django is required"

validate_matrix "$PYTHON_VERSION" "$DJANGO_VERSION"
DB="$(normalize_db "$DB")"
PYTHON_FACTOR="$(python_factor "$PYTHON_VERSION")"
DJANGO_FACTOR="$(django_factor "$DJANGO_VERSION")"
SELECTED_ENV_FILE="$(pick_env_file)"

load_env_file "$SELECTED_ENV_FILE"

export DATABASE_HOST="${DATABASE_HOST:-127.0.0.1}"
export DATABASE_PASSWORD="${DATABASE_PASSWORD:-treebeard}"
export DATABASE_USER_POSTGRES="${DATABASE_USER_POSTGRES:-root}"
export DATABASE_PORT_POSTGRES="${DATABASE_PORT_POSTGRES:-5432}"
export DATABASE_USER_MYSQL="${DATABASE_USER_MYSQL:-root}"
export DATABASE_PORT_MYSQL="${DATABASE_PORT_MYSQL:-3306}"
export DATABASE_PORT_MSSQL="${DATABASE_PORT_MSSQL:-1433}"
export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-Password12!}"

if [[ "$SKIP_COMPOSE" -eq 0 ]]; then
    start_service "$SELECTED_ENV_FILE" "$DB"
fi

TOX_ENV="$PYTHON_FACTOR-$DJANGO_FACTOR-$DB"
CMD=(tox -e "$TOX_ENV")

if [[ ${#TOX_ARGS[@]} -gt 0 ]]; then
    CMD+=("${TOX_ARGS[@]}")
fi

EXTRA_PYTEST_ARGS=()
if [[ "$DB" == "postgres" && "$ENFORCE_POSTGRES_COVERAGE" -eq 1 ]]; then
    EXTRA_PYTEST_ARGS+=(--cov-fail-under 96)
fi
if [[ ${#PYTEST_ARGS[@]} -gt 0 ]]; then
    EXTRA_PYTEST_ARGS+=("${PYTEST_ARGS[@]}")
fi
if [[ ${#EXTRA_PYTEST_ARGS[@]} -gt 0 ]]; then
    CMD+=(-- "${EXTRA_PYTEST_ARGS[@]}")
fi

exec "${CMD[@]}"
