#!/bin/bash
# Build Tessera.app on your Mac.
# Requirements: Xcode Command Line Tools (xcode-select --install) and CMake (brew install cmake).
set -euo pipefail
cd "$(dirname "$0")/.."
command -v cmake >/dev/null || { echo "CMake not found: brew install cmake"; exit 1; }
xcode-select -p >/dev/null 2>&1 || { echo "Xcode Command Line Tools not found: xcode-select --install"; exit 1; }
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j "$(sysctl -n hw.ncpu)"
build/TesseraTests_artefacts/Release/TesseraTests
APP=build/Tessera_artefacts/Release/Tessera.app
codesign --force --deep --sign - "$APP"
echo
echo "Built: $(pwd)/$APP"
echo "Run:   open \"$(pwd)/$APP\"   (or drag it into /Applications)"
