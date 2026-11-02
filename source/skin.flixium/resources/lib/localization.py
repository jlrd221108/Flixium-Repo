"""Kodi skin string lookup; standalone tools read the same English PO catalogue."""
import ast
from functools import lru_cache
from pathlib import Path
import re


@lru_cache(maxsize=1)
def source_strings():
    result = {}
    path = Path(__file__).resolve().parents[2] / 'language/resource.language.en_gb/strings.po'
    for block in path.read_text(encoding='utf-8-sig').split('\n\n'):
        context = re.search(r'msgctxt "#(\d+)"', block)
        message = re.search(r'^msgid (".*")(?:\n".*")*', block, re.M)
        if context and message:
            parts = message[0].splitlines()
            result[int(context[1])] = ''.join(ast.literal_eval(p[6:] if i == 0 else p)
                                             for i, p in enumerate(parts))
    return result


def localize(ident):
    try:
        import xbmc
    except ImportError:
        xbmc = None
    reader = getattr(xbmc, 'getLocalizedString', None)
    if reader is not None:
        return reader(ident)
    # Pure configuration modules are also used by validation tools and tests.
    return source_strings()[ident]
