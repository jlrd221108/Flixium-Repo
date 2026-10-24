# Contributing

For installation, rendering or dependency issues, open a report with the Kodi version, operating system, architecture, addon versions and steps to reproduce. Screenshots and a short relevant log excerpt help; remove private URLs and credentials.

Repository changes should include regenerated indexes/checksums where needed and pass `python tools/validate_repository.py`. Use a branch and pull request for changes to the release tooling. Package changes need a new add-on version and corresponding source; do not silently replace released binaries. Device-test native changes on the intended platform before describing them as playback-verified.

See docs/DEVELOPMENT.md for the release process and docs/LICENSES.md for licensing boundaries. Keep changes focused, preserve upstream notices and describe the validation actually performed.
