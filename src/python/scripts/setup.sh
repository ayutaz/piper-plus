#!/usr/bin/env bash
set -eo pipefail

# Directory of *this* script
this_dir="$( cd "$( dirname "$0" )" && pwd )"

# Base directory of repo (src/python)
base_dir="$(realpath "${this_dir}/..")"

# Repository root
repo_root="$(realpath "${base_dir}/../..")"

# Path to virtual environment
: "${venv:=${base_dir}/.venv}"

# Python binary to use
: "${PYTHON=python3}"

python_version="$(${PYTHON} --version)"

# Create virtual environment
echo "Creating virtual environment at ${venv} (${python_version})"
rm -rf "${venv}"
"${PYTHON}" -m venv "${venv}"
source "${venv}/bin/activate"

# Install Python dependencies
echo 'Installing Python dependencies'
pip3 install --upgrade pip
pip3 install --upgrade wheel setuptools uv

uv pip install "${base_dir}[train]"

# -----------------------------------------------------------------------------

echo "OK"
