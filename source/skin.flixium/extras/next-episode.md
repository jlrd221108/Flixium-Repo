# Next episode

Local Kodi-library TV episodes show **Watch Credits / ▶ Next Episode** buttons
at the bottom right. A white fill moves from left to right over 10 seconds,
then plays the next episode. Clicking Next Episode plays immediately.
Watch Credits or Back cancels autoplay for this episode. Pause/buffering freezes
the countdown; seeking cancels it.
The next available regular episode is chosen in season/episode order, including
across seasons; specials and another entry for the same combined video file are
excluded. A missing next file leaves the current episode playing.

Timing uses, in order:

1. An optional sidecar timestamp for the video.
2. A current chapter named Credits, End Credits, Closing Credits or Outro,
   in the second half of playback. Opening credits are excluded.
3. A near-end fallback, initially 60 seconds. Short files use at most their last 10%.

For `Episode.mkv`, an optional `Episode.flixium.json` contains:

```json
{"credits_start": 2521.5}
```

The timestamp is seconds from the start of that exact file. There is no automatic
visual credits detection. Chapter names come from Kodi's
[Player.ChapterName](https://kodi.wiki/view/InfoLabel).

Configure the button and fallback in **Skin Settings → On screen display**.
Set the fallback to Off to require a credits timestamp or named credits chapter.

While Flixium handles local-library episodes, it temporarily disables the
installed Up Next prompt and restores its previous enabled state afterwards.
If Up Next was already disabled, it stays disabled. A journal restores an
interrupted temporary change when Flixium's Home screen next loads.

Plugin playback and direct HTTP streams are excluded. This feature does not
change Kodi's own playlist/autoplay preferences.
