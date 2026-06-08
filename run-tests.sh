#!/bin/bash

set -e

# Default values
DB_TYPES=("sqlite" "postgres" "mysql" "mssql")
PYTHON_VERSIONS=("310" "314")
DJANGO_VERSIONS=("52" "60")

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --db)
            DB_TYPES=("${2}")
            shift; shift
            ;;
        --python)
            PYTHON_VERSIONS=("${2}")
            shift; shift
            ;;
        --django)
            DJANGO_VERSIONS=("${2}")
            shift; shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --db DB_TYPE     Database type (sqlite, postgres, mysql, mssql) [default: all]"
            echo "  --python PY_VER  Python version (310, 314) [default: all]"
            echo "  --django DJ_VER  Django version (52, 60) [default: all]"
            echo "  --help           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                          # Run all tests"
            echo "  $0 --db postgres            # Run PostgreSQL tests with all Python/Django versions"
            echo "  $0 --db postgres --python 314 --django 60  # Run specific combination"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Function to check if a Python version is compatible with a Django version
is_compatible() {
    local py_ver=$1
    local dj_ver=$2
    if [[ "$py_ver" == "310" && "$dj_ver" == "60" ]]; then
        return 1  # Not compatible
    fi
    return 0  # Compatible
}

# Run tests
for db in "${DB_TYPES[@]}"; do
    for py in "${PYTHON_VERSIONS[@]}"; do
        for dj in "${DJANGO_VERSIONS[@]}"; do
            if is_compatible "$py" "$dj"; then
                echo "Running tests for py${py}-dj${dj}-${db}..."
                tox -e "py${py}-dj${dj}-${db}"
            else
                echo "Skipping incompatible combination: py${py}-dj${dj}"
            fi
        done
    done
done
