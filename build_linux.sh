#!/usr/bin/env bash
# Build Posziona for Linux.
#
# Two output formats are supported:
#   1. Standalone onefile binary  (default) — no FUSE needed, runs anywhere
#   2. AppImage                    — bundles libfuse2, also runs anywhere
#
# Prerequisites:
#   - Python 3 with venv (Python 3.8+)
#   - pip install -r requirements.txt pyinstaller
#   - For AppImage: pip install appimage-builder (requires apt/dpkg-deb)
#
# Usage:
#   bash build_linux.sh              # Build standalone binary
#   bash build_linux.sh --appimage   # Build AppImage (bundles libfuse2)
#
# Output:
#   dist/posziona                — standalone binary (~110MB)
#   out/Party.POS-x86_64.AppImage  — AppImage (when --appimage is used)
#
# Note: The previous AppImage approach required FUSE (libfuse.so.2) which
# is not available on all distributions. Now libfuse2 is bundled inside
# the AppImage via appimage-builder's apt.include, so the host system
# does NOT need libfuse2 installed at all.

set -e

APP_NAME="Posziona"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPIMAGE_MODE=false

if [ "$1" = "--appimage" ]; then
  APPIMAGE_MODE=true
fi

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

BINARY_PATH="dist/posziona"
if [ -f "$BINARY_PATH" ]; then
  chmod +x "$BINARY_PATH"
  echo ""
  echo "=== Binary build successful! ==="
  echo "Binary: $(realpath $BINARY_PATH)"
  echo "Size: $(du -h $BINARY_PATH | cut -f1)"
  echo ""
  echo "Test it with:"
  echo "  ./dist/posziona --mode server"
  echo "  ./dist/posziona --mode client --server-url http://127.0.0.1:5000/"
else
  echo "ERROR: Binary not found at expected location!"
  exit 1
fi

# Optionally build AppImage
if [ "$APPIMAGE_MODE" = true ]; then
  echo ""
  echo "=== Building AppImage ==="

  # Check for appimage-builder
  if ! venv/bin/pip show appimage-builder >/dev/null 2>&1; then
    echo "Installing appimage-builder..."
    pip install appimage-builder
  fi

  # appimage-builder requires apt/dpkg-deb (Ubuntu/Debian only)
  if ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "WARNING: dpkg-deb not found. AppImage builds require an apt-based system (Ubuntu/Debian)."
    echo "         The standalone binary above is ready to use."
    exit 0
  fi

  venv/bin/appimage-builder --recipe AppImageBuilder.yml --skip-tests

  if ls out/*.AppImage 1>/dev/null 2>&1; then
    echo ""
    echo "=== AppImage build successful! ==="
    echo "AppImage: $(realpath out/*.AppImage)"
    echo "Size: $(du -h out/*.AppImage | cut -f1)"
    echo ""
    echo "Test it with:"
    echo "  ./out/Party.POS-x86_64.AppImage --mode server"
  else
    echo "ERROR: AppImage not found at expected location!"
    exit 1
  fi
fi
