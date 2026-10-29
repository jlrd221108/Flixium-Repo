# Release notes

## Skin 1.1.27 — 2026-10-29

- Publish current home widgets, My List and Flix layout refinements.
- Verify every runtime file against the ZIP and include all 122 skin layouts.
- Helper 1.0.45 and all native visualizer packages, paths and checksums remain unchanged.

## Skin 1.1.26 — 2026-10-27

- Fix the 1.1.25 package, which omitted the entire XML layout directory and could not load after a clean install.
- Restore all 122 layouts with the current localization, widgets and settings.
- Commit XML source and validate the actual downloadable package in CI.
- Helper 1.0.45 and all visualizers remain unchanged.

## Skin 1.1.25 / Helper 1.0.45 — 2026-10-27

- Publish current skin and helper runtime source and assets.
- Localise settings, setup, dialogs, widgets and library labels.
- Correct offline cached widget artwork, poster row sizing and hover markers.
- Preserve the existing Windows 1.1.2 and Android 1.2.0 visualizer assets and platform routing.
- Retain SHA-256 verification and update package metadata, artwork and download references.

## 1.0.0 — 2026-10-24

- Initial public Flixium repository for Kodi 21 Omega.
- Flixium 1.1.23 and Flixium Helper 1.0.44.
- Flixium Visualizer 1.1.2 for Windows x64, Android ARM64, ARMv7, x86 and x86-64.
- Automatic native architecture selection through Kodi's platform-filtered index.
- SHA-256 verification for repository metadata and downloadable packages.
- New Flixium Repo icon, branded installation page and maintenance documentation.
- Corresponding source, license notices and validation evidence accompany the release.

Android builds are cross-compiled and package-checked; on-device playback remains unverified. Windows native playback was checked locally. This release does not claim support for other Kodi major versions or platforms.
