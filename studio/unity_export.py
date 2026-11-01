"""Copy a generated net into a Unity project: only into Assets/NetStudio/, and only when asked.

  Assets/NetStudio/Editor/   the importer (editor-only assembly Carp.NetStudio.Editor)
  Assets/NetStudio/Runtime/  the small pose / marker component (assembly Carp.NetStudio)
  Assets/NetStudio/Nets/<id>/ FBX, textures, manifest (the importer builds the prefab here)
"""
import json
import shutil
from pathlib import Path

from .config import ROOT, is_safe_id
from .paths import inside, manifest_problems

UNITY_SRC = ROOT / "unity" / "NetStudio"


def guess_unity_project():
    for cand in (ROOT.parent / "carp" / "CarpFishingSimulator",):
        if is_unity_project(cand):
            return cand
    return None


def is_unity_project(path):
    p = Path(path)
    return (p / "Assets").is_dir() and (p / "ProjectSettings").is_dir()


def plan(export_dir, project, net_id):
    """(destination root, [(source, destination)]) — shown to the user before anything is copied."""
    if not is_safe_id(net_id):
        raise ValueError(f"unsafe net id {net_id!r}")
    if not is_unity_project(project):
        raise ValueError(f"{project} is not a Unity project (needs Assets\\ and ProjectSettings\\)")
    export_dir = Path(export_dir)
    manifest = json.loads((export_dir / "net_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("id") != net_id:
        raise ValueError(f"manifest id {manifest.get('id')!r} doesn't match {net_id!r}")
    problems = manifest_problems(manifest, export_dir)
    if problems:
        raise ValueError("export folder isn't complete: " + "; ".join(problems))
    dest = Path(project) / "Assets" / "NetStudio"
    files = [(p, dest / "Nets" / net_id / p.relative_to(export_dir))
             for p in export_dir.rglob("*") if p.is_file() and p.suffix.lower() != ".glb"]
    for sub in ("Editor", "Runtime"):
        files += [(p, dest / sub / p.name) for p in (UNITY_SRC / sub).iterdir() if p.is_file()]
    for _, d in files:
        if not inside(d, dest):
            raise ValueError(f"refusing to write outside {dest}: {d}")
    return dest, files


def copy(files):
    for src, dst in files:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return len(files)
