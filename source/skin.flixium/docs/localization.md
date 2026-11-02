# Localisation

The English source catalogue is `language/resource.language.en_gb/strings.po`.
Existing language catalogues and their translated entries are preserved.

Skin XML uses `$LOCALIZE[id]`. Python interface code uses
`localization.localize(id)` through the standalone script bridge
`extras/flixium_localization.py`. String IDs stay within Kodi's skin range,
31000–31999. Internal settings keys, media types, commands, paths, font family
identifiers and user-entered names are not translated.

To translate a new message, copy its `msgctxt` and English `msgid` into the
appropriate language's `strings.po`, and put the translation in `msgstr`.
Keep `{}` placeholders, Kodi `$INFO` references, and formatting tags such as
`[CR]`, `[B]` and `[COLOR ...]` intact. Built-in widget titles resolve from the
current catalogue; custom playlist names remain as entered by the user.

English text is used by Kodi for messages without a translation in the selected
language. New language translations have not been invented or copied over
existing translated entries. Reload the skin after updating language catalogues;
restart Kodi when updating long-running Python services.
