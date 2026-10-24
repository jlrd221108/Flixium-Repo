# Repository maintenance

## Layout and distribution

- `repository.flixium/`: source for the repository add-on and its bootstrap ZIP.
- `index/omega/`: generated `addons.xml`, SHA-256 and MD5 compatibility sidecars, plus a deterministic gzip copy.
- `artwork/<release>/<addon-id>/`: assets copied from the actual packages.
- `package-manifest.json`: package identities, platform declarations, sizes, filenames and SHA-256 values.
- `tools/`: standard-library Python build/validation tools. Large binaries and source archives are release assets, not Git objects.
- `docs/`: GitHub Pages installation source and documentation.

Each native manifest retains `visualization.flixium`, version 1.1.2, and declares exactly one platform: `windx`, `android-aarch64`, `android-armv7`, `android-i686` or `android-x86_64`. Kodi filters the index by platform before resolving dependencies. Index-only `<path>` elements point at versioned GitHub Release assets; they do not rename the add-on or alter its package manifest. The skin has one visualizer dependency.

The index restricts skin availability to the native platforms we ship. The repository feed is gated to Kodi 21. Do not remove either restriction without compatible binaries and ABI verification.

## Build a release

1. Build and verify the skin, helper and all five native packages. Version changes belong in their real manifests; never replace an already published package with different bytes under the same add-on version.
2. Prepare an `incoming/` directory containing the skin ZIP, helper ZIP and five architecture-named visualizer ZIPs. Build a corresponding-source ZIP with the runtime sources, native sources, build instructions, relevant build tools, fonts and license notices. It must match the binaries being distributed.
3. Update release notes/version tables and the repository add-on version if its configuration changes. Regenerate the installer when its version or configuration changes.
4. Run `python tools/build_repository.py --packages incoming --source incoming/flixium-source-vX.Y.Z.zip --release vX.Y.Z`.
5. Run `python tools/validate_repository.py --packages dist/vX.Y.Z`. Inspect generated platform selection, checksums, assets and dependencies before publishing.
6. Create a draft GitHub Release for the new tag and upload **all** files from `dist/vX.Y.Z`, including package `.zip.sha256` sidecars and corresponding source. Publish it before making the new index available to clients.
7. Commit the generated index, artwork, manifest and installer to `main`. Enable or retain GitHub Pages from `main:/docs`. Verify the public feed checksum, bootstrap ZIP, release asset hashes and five simulated platform selections.

Updates can mix package versions; old release assets must remain available. Keep historical artwork paths used by retained release indexes. The validator and CI do not compile native code and cannot replace device playback testing.

## Source and native builds

The first release includes [flixium-source-v1.0.0.zip](https://github.com/jlrd221108/Flixium-Repo/releases/download/v1.0.0/flixium-source-v1.0.0.zip). It contains the skin and helper runtime source trees, native visualizer source, font/license files and build scripts. See `skin.flixium/native/visualization.flixium/README.md` inside it for Windows and Android builds. Android uses NDK r27d and matching Kodi Omega headers. Source for the repository tooling is this Git repository.

## Official references

- [Kodi repository structure and checksums](https://kodi.wiki/view/Add-on_repositories)
- [Addon manifests and dependencies](https://kodi.wiki/view/Addon.xml)
- [Kodi 21 platform filtering and repository paths](https://github.com/xbmc/xbmc/blob/Omega/xbmc/addons/addoninfo/AddonInfoBuilder.cpp)
- [Repository index parsing](https://github.com/xbmc/xbmc/blob/Omega/xbmc/addons/AddonManager.cpp)
- [Package checksum resolution](https://github.com/xbmc/xbmc/blob/Omega/xbmc/addons/Repository.cpp)
