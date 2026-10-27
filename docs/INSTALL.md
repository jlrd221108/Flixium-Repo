# Install Flixium

Use Kodi 21 Omega on Windows x64 or a supported Android build. Keep Kodi's official repository enabled for `script.module.pil`.

## Repository ZIP

Download [repository.flixium-1.0.0.zip](https://github.com/jlrd221108/Flixium-Repo/releases/download/v1.1.24-repo-fix/repository.flixium-1.0.0.zip). In Kodi, enable Unknown sources under Settings → System → Add-ons, then open Add-ons → Install from zip file. Select the downloaded ZIP.

Open Install from repository → Flixium Repo → Look and feel → Skin → Flixium. Accept the dependencies and switch skin. The helper and matching visualizer install automatically; no architecture selection is needed.

## File Manager source

Add `https://jlrd221108.github.io/Flixium-Repo/` under Settings → File manager → Add source. Name it Flixium. Open Add-ons → Install from zip file → Flixium and select `repository.flixium-1.0.0.zip`. Then follow the repository instructions above.

## Music OSD

Play a track and enter music visualisation. Flixium selects its visualizer on first setup. Use Music OSD settings for the preferred lyrics source, lyric animation toggles and Background Settings. Local and online lyrics use the configured preference with fallback when no usable lyrics are found. Word and syllable effects depend on timestamps in the available lyrics.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Could not connect to repository | Verify internet access and the device clock, then check the repository for updates. HTTPS certificate checks must stay enabled. |
| Dependency unavailable | Use Kodi 21, keep the official Kodi repository enabled, and check that Flixium Repo is enabled. Only Windows x64 and the listed Android builds have native packages. |
| No new update | Check for repository updates. If previously installed from another private repository, select Flixium Repo under the add-on's Versions screen. |
| Manual visualizer ZIP rejected | The binary must match Kodi's process architecture, not just the device CPU. Prefer automatic repository installation. |
| Android graphics issue | Android device testing is pending. Report Kodi version, architecture, device/GPU and relevant logs. Try reduced background quality and individual effects while investigating. |
| Media library is empty | This repository supplies software and artwork; add your own media sources in Kodi. |

For a report, use the [issue template](https://github.com/jlrd221108/Flixium-Repo/issues/new/choose). Review logs for private URLs, credentials and personal paths before sharing them.
