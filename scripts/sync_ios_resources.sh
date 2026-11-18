#!/usr/bin/env bash
# Copy the built library and the runtime prompt into the iOS bundle resources.
# Run after `python -m pipeline.build_library`, then rebuild the app in Xcode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/ios/AposurviveOffline/Resources"

for f in "$ROOT/build/library.sqlite" "$ROOT/build/library_manifest.json" "$ROOT/training/prompts/runtime_system.txt"; do
  [[ -f "$f" ]] || { echo "missing: $f (build the library first)"; exit 1; }
done

mkdir -p "$DEST"
cp "$ROOT/build/library.sqlite" "$ROOT/build/library_manifest.json" "$DEST/"
cp "$ROOT/training/prompts/runtime_system.txt" "$DEST/"
echo "Synced to $DEST:"
ls -lh "$DEST" | sed 1d
