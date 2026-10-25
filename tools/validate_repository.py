"""Validate public metadata; optionally inspect every real ZIP before publishing."""
import argparse
import ast
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PLATFORMS={"windx","android-aarch64","android-armv7","android-i686","android-x86_64"}
ANDROID={"android-aarch64":(2,183),"android-armv7":(1,40),"android-i686":(1,3),"android-x86_64":(2,62)}
SECRET=re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def check(condition,message):
    if not condition:raise ValueError(message)


def metadata(addon):return addon.find("extension[@point='xbmc.addon.metadata']")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages",type=Path)
    args=parser.parse_args()
    report=json.loads((ROOT/"package-manifest.json").read_text())
    data=(ROOT/report["index"]).read_bytes();index=ET.fromstring(data)
    check(index.tag=="addons","Wrong index root")
    check(hashlib.sha256(data).hexdigest()==(ROOT/(report["index"]+".sha256")).read_text().strip(),"Index SHA256 mismatch")
    check(hashlib.md5(data,usedforsecurity=False).hexdigest()==(ROOT/(report["index"]+".md5")).read_text().strip(),"Index MD5 sidecar mismatch")
    compressed=(ROOT/(report["index"]+".gz")).read_bytes()
    check(gzip.decompress(compressed)==data,"Compressed index mismatch")
    check(hashlib.sha256(compressed).hexdigest()==(ROOT/(report["index"]+".gz.sha256")).read_text().strip(),"Gzip checksum mismatch")
    records={record["path"]:record for record in report["packages"] if "id" in record}
    check(len(index)==8 and len(records)==8,"Expected eight addon variants")
    for addon in index:
        meta=metadata(addon);path=meta.findtext("path")
        check(path in records,"Missing package record")
        record=records[path]
        check((addon.get("id"),addon.get("version"))==(record["id"],record["version"]),"Index identity mismatch")
        check(record["sha256"] and re.fullmatch(r"[0-9a-f]{64}",record["sha256"]),"Missing package checksum")
        for asset in meta.findall("./assets/*"):
            if asset.text:
                target=ROOT/"artwork"/PurePosixPath(path).parent/asset.text
                check(target.is_file(),"Missing artwork: "+str(target))
        for child in (meta.find("website"),meta.find("source")):
            check(child is not None and child.text.startswith("https://"),"Missing HTTPS project/source URL")
    # Same filtering order used by Kodi: incompatible platforms are discarded
    # before duplicate addon IDs are considered by dependency resolution.
    for platform in sorted(PLATFORMS):
        selected=[addon for addon in index if "all" in metadata(addon).findtext("platform").split() or platform in metadata(addon).findtext("platform").split()]
        counts=Counter(addon.get("id") for addon in selected)
        check(counts==Counter({"repository.flixium":1,"skin.flixium":1,"script.flixium.helper":1,"visualization.flixium":1}),"Ambiguous selection for "+platform)
        skin=next(addon for addon in selected if addon.get("id")=="skin.flixium")
        for dependency_id in ("script.flixium.helper","visualization.flixium"):
            dependency=skin.find(f"./requires/import[@addon='{dependency_id}']")
            target=next(addon for addon in selected if addon.get("id")==dependency_id)
            check(dependency is not None and tuple(map(int,target.get("version").split('.')))>=tuple(map(int,dependency.get("version").split('.'))),"Dependency mismatch")
        print(platform+": one matching visualizer and complete dependency graph")
    repo=ET.parse(ROOT/"repository.flixium/addon.xml").getroot()
    directory=repo.find("./extension[@point='xbmc.addon.repository']/dir")
    check(directory.get("minversion")=="21.0.0" and directory.get("maxversion")=="21.9.999","Missing Kodi ABI channel bounds")
    check(directory.find("checksum").get("verify")=="sha256" and directory.findtext("hashes")=="sha256","Weak repository verification")
    for name in ("info","checksum","datadir","artdir"):check(directory.findtext(name).startswith("https://"),"Non-HTTPS endpoint")
    icon=(ROOT/"repository.flixium/resources/icon.png").read_bytes()
    check(icon[:8]==b"\x89PNG\r\n\x1a\n" and struct.unpack_from(">II",icon,16)==(512,512),"Repository icon must be 512-square PNG")
    for file in (ROOT/"tools").glob("*.py"):ast.parse(file.read_text(),filename=str(file))
    if args.packages:
        for record in report["packages"]:
            file=args.packages/record["file"]
            check(file.stat().st_size==record["bytes"],"Incorrect asset length: "+file.name)
            with file.open("rb") as source:actual=hashlib.file_digest(source,"sha256").hexdigest()
            check(actual==record["sha256"],"Asset SHA256 mismatch: "+file.name)
            check((args.packages/(file.name+".sha256")).read_bytes()==actual.encode()+b"\n","Package checksum sidecar mismatch or unsafe CRLF line ending")
            with zipfile.ZipFile(file) as archive:
                check(archive.testzip() is None,"Corrupt archive: "+file.name)
                check(len(archive.namelist())==len(set(archive.namelist())),"Duplicate archive entries")
                for name in archive.namelist():
                    relative=PurePosixPath(name)
                    check(not relative.is_absolute() and ".." not in relative.parts and "\\" not in name and ":" not in name,"Unsafe ZIP path")
                    check(not any(part in {".git","__pycache__"} for part in relative.parts),"Private/cache file in package")
                    if Path(name).suffix.lower() in {".py",".xml",".json",".txt",".md",".h",".cpp"}:
                        content=archive.read(name);check(not SECRET.search(content),"Possible credential/private key: "+name)
                    if name.endswith(".py"):ast.parse(archive.read(name).decode("utf-8-sig"),filename=name)
                    if name.endswith(".xml"):ET.fromstring(archive.read(name))
                if "id" not in record:
                    check("skin.flixium/native/visualization.flixium/src/android/VisualizerGLES.cpp" in archive.namelist(),"Missing native source")
                    check("skin.flixium/tools/build_flixium_android.py" in archive.namelist(),"Missing Android build instructions/tooling")
                    continue
                addon=ET.fromstring(archive.read(record["id"]+"/addon.xml"))
                check(addon.get("version")==record["version"],"Package version mismatch")
                if record["id"]=="visualization.flixium":
                    platform=metadata(addon).findtext("platform")
                    check(platform==record["platform"],"Native platform mismatch")
                    extension=addon.find("extension[@point='xbmc.player.musicviz']")
                    if platform in ANDROID:
                        binary=archive.read(record["id"]+"/"+extension.get("library_android"))
                        check(binary[:4]==b"\x7fELF" and (binary[4],struct.unpack_from("<H",binary,18)[0])==ANDROID[platform],"Wrong native Android architecture")
                    else:
                        binary=archive.read(record["id"]+"/"+extension.get("library_windx"))
                        pe=struct.unpack_from("<I",binary,60)[0]
                        check(binary[:2]==b"MZ" and binary[pe:pe+4]==b"PE\0\0" and struct.unpack_from("<H",binary,pe+4)[0]==0x8664,"Wrong Windows architecture")
        print("All actual package/source ZIPs: integrity, hashes, paths, source, manifests, Python/XML and credential-pattern checks passed")
    installer=ROOT/"repository.flixium"/f"repository.flixium-{repo.get('version')}.zip"
    check(installer.read_bytes()==(ROOT/"docs"/installer.name).read_bytes(),"Bootstrap copies differ")
    with zipfile.ZipFile(installer) as archive:
        check(archive.read("repository.flixium/addon.xml")== (ROOT/"repository.flixium/addon.xml").read_bytes(),"Bootstrap manifest differs")
    print("Repository metadata, artwork, HTTPS/SHA256 and installer checks passed")


if __name__=="__main__":main()
