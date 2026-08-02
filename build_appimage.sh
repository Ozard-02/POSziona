#!/usr/bin/env bash
# Build Party POS as a portable Linux binary.
#
# This script builds a single-file executable using PyInstaller's
# --onefile mode. The resulting binary only depends on basic system
# libraries (libc, libpthread, libdl, libz) that are present on virtually
# all Linux distributions.
#
# Prerequisites:
#   - Python 3 with venv (Python 3.8+)
#   - pip install -r requirements.txt pyinstaller
#
# Usage:
#   bash build_appimage.sh
#
# Output:
#   dist/party-pos  — single executable (~110MB)
#
# Note: The previous AppImage approach required FUSE (libfuse.so.2) which
# is not available on all distributions. The onefile binary approach is
# simpler and more portable.

set -e

APP_NAME="Party POS"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Building $APP_NAME ==="
echo "Working directory: $SCRIPT_DIR"

cd "$SCRIPT_DIR"

# Check for virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "No virtual environment found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Install dependencies
echo "=== Installing dependencies ==="
pip install -r requirements.txt
pip install pyinstaller

# Build with PyInstaller using the onefile spec
echo "=== Building binary ==="
pyinstaller build_onefile.spec --noconfirm

BINARY_PATH="dist/party-pos"
if [ -f "$BINARY_PATH" ]; then
    chmod +x "$BINARY_PATH"
    echo ""
    echo "=== Build successful! ==="
    echo "Binary: $(realpath $BINARY_PATH)"
    echo "Size: $(du -h $BINARY_PATH | cut -f1)"
    echo ""
    echo "Test it with:"
    echo "  ./dist/party-pos --mode server"
    echo "  ./dist/party-pos --mode client --server-url http://127.0.0.1:5000/"
else
    echo "ERROR: Binary not found at expected location!"
    exit 1
fi
