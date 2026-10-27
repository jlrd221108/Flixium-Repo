"""Check the real downloadable skin, including every committed skin layout."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile
import xml.etree.ElementTree as E

ROOT = Path(__file__).resolve().parents[1]

def validate(data, record):
    assert hashlib.sha256(data).hexdigest() == record['sha256'], 'Skin SHA256 mismatch'
    assert len(data) == record['bytes'], 'Skin size mismatch'
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None, 'Corrupt skin ZIP'
        names = set(archive.namelist())
        addon = E.fromstring(archive.read('skin.flixium/addon.xml'))
        assert addon.get('version') == record['version']
        for res in addon.findall("./extension[@point='xbmc.gui.skin']/res"):
            folder = 'skin.flixium/' + res.get('folder') + '/'
            for file in ('Home.xml', 'Font.xml', 'Includes.xml', 'Startup.xml'):
                assert folder + file in names, 'Missing required skin file: ' + folder + file
        layouts = list((ROOT / 'source/skin.flixium/xml').glob('*.xml'))
        assert layouts, 'Missing committed layout source'
        for file in layouts:
            name = 'skin.flixium/xml/' + file.name
            assert name in names, 'Missing layout: ' + name
            content = archive.read(name)
            # Git can normalise line endings on Windows.
            assert content.replace(b'\r\n', b'\n') == file.read_bytes().replace(b'\r\n', b'\n'), 'Layout differs: ' + name
        count = 0
        for name in names:
            if not name.endswith('.xml'): continue
            tree = E.fromstring(archive.read(name)); count += 1
            for include in tree.findall('.//include[@file]'):
                path = str(Path(name).parent.as_posix()) + '/' + include.get('file')
                assert path in names, 'Missing include: ' + path
        print(f"Skin {record['version']}: {len(layouts)} layouts present; {count} XML files parse; includes and required entry files resolve")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('zip', nargs='?', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'package-manifest.json').read_text())
    record = next(r for r in manifest['packages'] if r.get('id') == 'skin.flixium')
    data = args.zip.read_bytes() if args.zip else urllib.request.urlopen('https://github.com/jlrd221108/Flixium-Repo/releases/download/' + record['path'], timeout=90).read()
    validate(data, record)
