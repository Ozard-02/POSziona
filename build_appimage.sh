#!/usr/bin/env bash
# Build Party POS as a Linux AppImage.
#
# Prerequisites:
#   - Python 3 with venv (Python 3.8+)
#   - pip install -r requirements.txt pyinstaller
#   - System libraries for pywebview: libgtk-3-0, libwebkit2gtk-4.0-37 (or equivalent)
#   - appimagetool (auto-downloaded if not present)
#
# Usage:
#   chmod +x build_appimage.sh
#   ./build_appimage.sh
#
# Output: dist_appimage/PartyPOS-<version>-x86_64.AppImage
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="party-pos"
VERSION="0.1.0"
BUILD_DIR="$SCRIPT_DIR/dist_appimage"
APPDIR="$BUILD_DIR/${APP_NAME}.AppDir"

echo "=== Building Party POS AppImage ==="

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Check for system deps needed by pywebview on Linux
echo "=== Checking system dependencies ==="
MISSING_DEPS=0
for dep in libgtk-3-0 libwebkit2gtk-4.0-37; do
    if command -v dpkg &>/dev/null; then
        if ! dpkg -s "$dep" 2>/dev/null >/dev/null; then
            echo "WARNING: $dep not found. pywebview may not work without it."
            MISSING_DEPS=1
        fi
    elif command -v pacman &>/dev/null; then
        pkg=$(echo "$dep" | sed 's/-[0-9].*//')
        if ! pacman -Q "$pkg" &>/dev/null 2>&1; then
            echo "WARNING: $pkg not found. pywebview may not work without it."
            MISSING_DEPS=1
        fi
    else
        echo "WARNING: Cannot check for $dep (no dpkg or pacman found)."
    fi
done
if [ "$MISSING_DEPS" -eq 1 ]; then
    echo "Install missing dependencies with:"
    echo "  Debian/Ubuntu: sudo apt-get install -y libgtk-3-0 libwebkit2gtk-4.0-37"
    echo "  Arch:         sudo pacman -S gtk3 webkit2gtk"
    echo "Continuing anyway (build may fail without GUI support)..."
fi

# Build with PyInstaller using the spec file
# The spec file already has console=True; for GUI-only use, modify the spec or
# use --windowed flag (only when building from command line, not with spec file)
echo "=== Running PyInstaller ==="
pyinstaller build_exe.spec \
    --distpath="$BUILD_DIR/dist" \
    --workpath="$BUILD_DIR/build" \
    --noconfirm

# Verify the binary was built
if [ ! -f "$BUILD_DIR/dist/$APP_NAME" ]; then
    echo "ERROR: PyInstaller build failed — binary not found at $BUILD_DIR/dist/$APP_NAME"
    exit 1
fi

echo "=== PyInstaller build complete ==="
ls -lh "$BUILD_DIR/dist/$APP_NAME"

# Create AppDir structure
echo "=== Creating AppDir ==="
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy the built binary into the AppDir
cp "$BUILD_DIR/dist/$APP_NAME" "$APPDIR/usr/bin/$APP_NAME"
chmod +x "$APPDIR/usr/bin/$APP_NAME"

# Create desktop entry
cat > "$APPDIR/usr/share/applications/$APP_NAME.desktop" << 'DESKTOP_EOF'
[Desktop Entry]
Name=Party POS
Comment=Lightweight POS for parties and events
Exec=party-pos
Type=Application
Terminal=false
Categories=Office;Utility;
StartupNotify=true
DESKTOP_EOF

# Also copy to AppDir root — appimagetool looks for it there
cp "$APPDIR/usr/share/applications/$APP_NAME.desktop" "$APPDIR/$APP_NAME.desktop"

# Copy icon if available
if [ -f "app/ui/static/favicon.ico" ]; then
    if command -v convert &>/dev/null; then
        convert "app/ui/static/favicon.ico" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png" 2>/dev/null || true
    fi
    if [ ! -f "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png" ] && [ -f "app/ui/static/favicon-256.png" ]; then
        cp "app/ui/static/favicon-256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"
    fi
    echo "NOTE: Icon conversion may require ImageMagick (convert)."
fi

# Create AppRun (launches the binary inside AppDir)
cat > "$APPDIR/AppRun" << 'APPRUN_EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/party-pos" "$@"
APPRUN_EOF
chmod +x "$APPDIR/AppRun"

# Create app metadata
cat > "$APPDIR/AppImageMetadata" << METADATA_EOF
AppImageSignature=0
METADATA_EOF

# Create the AppImage using appimagetool
echo "=== Creating AppImage ==="

# Use appimagetool from PATH, from script dir, or download it
if command -v appimagetool &>/dev/null; then
    APPIMAGETOOL="appimagetool"
elif [ -f "/tmp/appimagetool.AppImage" ]; then
    APPIMAGETOOL="/tmp/appimagetool.AppImage"
elif [ -f "$SCRIPT_DIR/appimagetool" ]; then
    APPIMAGETOOL="$SCRIPT_DIR/appimagetool"
else
    echo "Downloading appimagetool..."
    APPIMAGETOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    curl -L -o "$BUILD_DIR/appimagetool" "$APPIMAGETOOL_URL"
    chmod +x "$BUILD_DIR/appimagetool"
    APPIMAGETOOL="$BUILD_DIR/appimagetool"
fi

APPIMAGE_OUTPUT="$BUILD_DIR/PartyPOS-$VERSION-x86_64.AppImage"
"$APPIMAGETOOL" --appdir="$APPDIR" "$APPIMAGE_OUTPUT"

echo ""
echo "=== Done! ==="
echo "AppImage created: $APPIMAGE_OUTPUT"
echo ""
echo "To run:"
echo "  chmod +x $APPIMAGE_OUTPUT"
echo "  $APPIMAGE_OUTPUT"
echo ""
echo "Or run in specific mode:"
echo "  $APPIMAGE_OUTPUT --mode server    # Server only (Flask, no window)"
echo "  $APPIMAGE_OUTPUT --mode client    # Client only (connect to existing server)"
echo "  $APPIMAGE_OUTPUT --mode all       # Server + client (default)"
echo ""
echo "To extract and inspect:"
echo "  $APPIMAGE_OUTPUT --appimage-extract"
