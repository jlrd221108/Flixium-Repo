"""Generate Kodi's platform-filtered index and versioned GitHub Release assets."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PROJECT="https://github.com/jlrd221108/Flixium-Repo"
NATIVE_PLATFORMS={"windx","android-aarch64","android-armv7","android-i686","android-x86_64"}


def xml_bytes(element):
    ET.indent(element,space="  ")
    return ET.tostring(element,encoding="utf-8",xml_declaration=True)+b"\n"


def digest(path):
    with path.open("rb") as source:return hashlib.file_digest(source,"sha256").hexdigest()


def metadata(addon):
    return addon.find("extension[@point='xbmc.addon.metadata']")


def safe_relative(value):
    path=PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("Unsafe package path: "+value)
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages",type=Path,default=ROOT/"incoming")
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--release",required=True)
    args=parser.parse_args()
    if not args.release.startswith("v") or any(c not in "v0123456789.-" for c in args.release):raise ValueError("Use a version tag such as v1.0.0")
    release=args.release;dist=ROOT/"dist"/release;dist.mkdir(parents=True,exist_ok=True)
    repo=ROOT/"repository.flixium";repo_manifest=ET.parse(repo/"addon.xml").getroot()
    repo_filename=f"repository.flixium-{repo_manifest.get('version')}.zip"
    repo_zip=dist/repo_filename
    with zipfile.ZipFile(repo_zip,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for file in sorted(repo.rglob("*")):
            if file.is_file() and file.suffix!=".zip":archive.write(file,"repository.flixium/"+file.relative_to(repo).as_posix())
    packages=[repo_zip]
    for file in sorted(args.packages.glob("*.zip")):
        if file.resolve()==args.source.resolve():continue
        target=dist/file.name
        if file.resolve()!=target.resolve():shutil.copy2(file,target)
        packages.append(target)
    if len(packages)!=8:raise ValueError("Expected repository, skin, helper and five native packages")
    source_target=dist/args.source.name
    if args.source.resolve()!=source_target.resolve():shutil.copy2(args.source,source_target)
    source_hash=digest(source_target)
    source_url=f"{PROJECT}/releases/download/{release}/{source_target.name}"
    root=ET.Element("addons");records=[];seen=set()
    for package in packages:
        with zipfile.ZipFile(package) as archive:
            if archive.testzip() is not None:raise ValueError("Corrupt package: "+package.name)
            manifests=[name for name in archive.namelist() if name.count("/")==1 and name.endswith("/addon.xml")]
            if len(manifests)!=1:raise ValueError("Package needs one root addon.xml: "+package.name)
            addon=ET.fromstring(archive.read(manifests[0]));addon_id=addon.get("id");version=addon.get("version")
            if not addon_id or not version:raise ValueError("Missing identity")
            for name in archive.namelist():
                safe_relative(name)
                if name.split("/")[0]!=addon_id:raise ValueError("Incorrect ZIP root: "+name)
            original=metadata(addon)
            platform=original.findtext("platform",default="all")
            identity=(addon_id,version,platform)
            if identity in seen:raise ValueError("Duplicate package identity")
            seen.add(identity)
            entry=copy.deepcopy(addon);meta=metadata(entry)
            if addon_id=="skin.flixium":meta.find("platform").text=" ".join(sorted(NATIVE_PLATFORMS))
            for node in list(meta.findall("path")):meta.remove(node)
            ET.SubElement(meta,"path").text=f"{release}/{package.name}"
            for key,value in (("website",f"{PROJECT}"),("source",PROJECT if addon_id=="repository.flixium" else source_url)):
                element=meta.find(key)
                if element is None:element=ET.SubElement(meta,key)
                element.text=value
            assets=meta.find("assets")
            if assets is not None:
                for asset in assets:
                    if not asset.text:continue
                    relative=safe_relative(asset.text)
                    data=archive.read(addon_id+"/"+relative.as_posix())
                    target=ROOT/"artwork"/release/addon_id/relative
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                    asset.text=addon_id+"/"+relative.as_posix()
            root.append(entry)
            checksum=digest(package)
            (dist/(package.name+".sha256")).write_text(checksum+"\n",encoding="ascii",newline="\n")
            records.append({"file":package.name,"id":addon_id,"version":version,"platform":platform,
                            "path":f"{release}/{package.name}","bytes":package.stat().st_size,"sha256":checksum})
    native=[record for record in records if record["id"]=="visualization.flixium"]
    if {record["platform"] for record in native}!=NATIVE_PLATFORMS:raise ValueError("Missing or unexpected native architecture")
    records.append({"file":source_target.name,"kind":"source","path":f"{release}/{source_target.name}","bytes":source_target.stat().st_size,"sha256":source_hash})
    (dist/(source_target.name+".sha256")).write_text(source_hash+"\n",encoding="ascii",newline="\n")
    index=ROOT/"index/omega";index.mkdir(parents=True,exist_ok=True)
    data=xml_bytes(root)
    (index/"addons.xml").write_bytes(data)
    (index/"addons.xml.sha256").write_text(hashlib.sha256(data).hexdigest()+"\n",encoding="ascii",newline="\n")
    (index/"addons.xml.md5").write_text(hashlib.md5(data,usedforsecurity=False).hexdigest()+"\n",encoding="ascii",newline="\n")
    compressed=gzip.compress(data,mtime=0)
    (index/"addons.xml.gz").write_bytes(compressed)
    (index/"addons.xml.gz.sha256").write_text(hashlib.sha256(compressed).hexdigest()+"\n",encoding="ascii",newline="\n")
    manifest={"release":release,"index":"index/omega/addons.xml","packages":records}
    (ROOT/"package-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (dist/"package-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (dist/"SHA256SUMS.txt").write_text("".join(record["sha256"]+"  "+record["file"]+"\n" for record in records),encoding="ascii")
    shutil.copy2(repo_zip,repo/repo_filename)
    shutil.copy2(repo_zip,ROOT/"docs"/repo_filename)
    print(f"Built {len(root)} index entries; {len(records)} packages/source archives; release {release}")


if __name__=="__main__":main()
