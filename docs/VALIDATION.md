# Release validation — 1.0.0

Prepared on 2026-10-24 for Kodi 21 Omega.

## Repository and packages

- Eight index entries: repository, skin, helper and five native variants.
- Simulated Kodi platform filtering on Windows x64 and Android ARM64, ARMv7, x86 and x86-64. Every supported platform resolves one visualizer and the complete skin/helper/native dependency graph.
- Checked every published ZIP's CRC, SHA-256, identity, version, archive paths, metadata assets and XML/Python syntax.
- Inspected packaged Windows PE and Android ELF machine types against the declared platforms.
- Checked repository/asset HTTPS URLs, SHA-256 configuration, deterministic compressed metadata and bootstrap ZIP consistency. Package checksum sidecars use LF endings for Kodi's checksum parser.
- Checked source presence and common access-token/private-key patterns in text payloads. This is a focused secret-pattern check, not a complete security audit.

`python tools/validate_repository.py` repeats metadata validation in GitHub Actions. Pass `--packages dist/v1.0.0` for the full local asset checks.

## Renderer evidence and limits

The preceding native port checks passed 47 lyric tests, six visualizer integration tests and five OSD layout tests. The GLES geometry test exercised fill slabs, colour states, disabled effects, Simple mode and interlude visibility. Both background/lyric ES100 programs compiled and linked in highp and mediump variants using Windows OpenGL's ES2 compatibility.

All four Android libraries cross-compiled with NDK r27d, exported the Kodi entry point and were checked for the expected ELF architecture, system-library dependencies and 16 KiB load alignment. Windows D3D11 shader checks and local Kodi native-ownership/playback checks preceded this repository release.

**Android device playback and Android GPU-driver behaviour remain unverified.** Shader compilation on Windows is not a substitute for testing on Android. The full legacy skin test suite was not rerun for this packaging-only publication. Package/index validation does not constitute a complete feature or security audit.
