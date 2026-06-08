#!/bin/bash
set -e

# Default values
DB="sqlite"
PYTHON_VERSION="3.10"
DJANGO_VERSION="5.2"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -d, --db <db>            Database to test (sqlite, postgres, mysql, mssql). Default: $DB"
    echo "  -p, --python <version>   Python version (e.g., 3.10, 3.14). Default: $PYTHON_VERSION"
    echo "  -j, --django <version>   Django version (e.g., 5.2, 6.0). Default: $DJANGO_VERSION"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -d postgres -p 3.10 -j 5.2"
    echo "  $0 --db mysql --python 3.14 --django 6.0"
    exit 1
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -d|--db) DB="$2"; shift ;;
        -p|--python) PYTHON_VERSION="$2"; shift ;;
        -j|--django) DJANGO_VERSION="$2"; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown parameter passed: $1"; usage ;;
    esac
    shift
done

# Format Python version for tox (e.g. 3.10 -> 310)
PY_ENV="py${PYTHON_VERSION//./}"

# Format Django version for tox (e.g. 5.2 -> 52)
DJ_ENV="dj${DJANGO_VERSION//./}"

TOX_ENV="${PY_ENV}-${DJ_ENV}-${DB}"

echo "========================================================="
echo "Running tests for tox environment: $TOX_ENV"
echo "========================================================="

# Export environment variables for local testing
export DATABASE_USER_POSTGRES="root"
export DATABASE_PASSWORD="treebeard"
export DATABASE_HOST="127.0.0.1"
export DATABASE_PORT_POSTGRES="5432"
export DATABASE_USER_MYSQL="root"
export DATABASE_PORT_MYSQL="3306"
export DATABASE_PORT_MSSQL="1433"

# Run tox
tox -e "$TOX_ENV"
