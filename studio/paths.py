"""Path safety for manifests and Unity exports: relative paths that stay inside their folder."""
from pathlib import Path, PurePosixPath, PureWindowsPath


def is_safe_relative(path):
    """True for a plain relative path ('Textures/x.png'): no drive, no root, no '..', no backslash tricks."""
    if not isinstance(path, str) or not path or "\x00" in path:
        return False
    if PureWindowsPath(path).drive or PureWindowsPath(path).root or PurePosixPath(path).is_absolute():
        return False
    parts = PurePosixPath(path.replace("\\", "/")).parts
    return all(p not in ("..", ".", "") for p in parts)


def inside(child, parent):
    """True if child resolves to parent or somewhere below it."""
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def manifest_problems(manifest, folder):
    """Every problem with a manifest's file list: unsafe paths, files that don't exist. Empty list = fine."""
    problems = []
    files = manifest.get("files", {})
    listed = [files.get("fbx")] + ([files["glb"]] if files.get("glb") else []) + list(files.get("textures", []))
    for m in manifest.get("materials", {}).values():
        listed += [m.get(k) for k in ("base_map", "normal_map", "mask_map", "roughness_map") if m.get(k)]
    for rel in listed:
        if not is_safe_relative(rel):
            problems.append(f"unsafe path in manifest: {rel!r}")
        elif not (Path(folder) / rel).is_file():
            problems.append(f"missing file: {rel}")
    return problems
