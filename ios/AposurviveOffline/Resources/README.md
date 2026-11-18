# Bundled resources

Generated, not committed. Populate with:

    scripts/sync_ios_resources.sh

which copies:

- `library.sqlite` from `build/` (the offline survival library)
- `library_manifest.json` from `build/` (sha256 checked at launch)
- `runtime_system.txt` from `training/prompts/` (the exact system prompt used in training)
