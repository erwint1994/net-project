"""Find Blender and run the generator in the background, streaming its log."""
import json
import os
import shutil
import subprocess
from pathlib import Path

from .config import ROOT

OUTPUT = ROOT / "output"
SCRIPT = ROOT / "blender" / "run_net.py"
SIBLING_BIVVY = ROOT.parent / "bivvy-project" / "_vendor"


def blender_candidates():
    """Where Blender is looked for, in order, with a label for each."""
    out = []
    env = os.environ.get("NET_BLENDER")
    if env:
        out.append(("NET_BLENDER", Path(env)))
    # The sibling Bivvy Studio's portable Blender, used read-only (never modified or updated from here).
    out += [("sibling bivvy-project portable Blender", p) for p in sorted(SIBLING_BIVVY.glob("blender-*/blender.exe"), reverse=True)]
    out += [("this project's portable Blender (_vendor)", p) for p in sorted((ROOT / "_vendor").glob("blender-*/blender.exe"), reverse=True)]
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    out += [("installed Blender", p) for p in sorted(pf.glob("Blender*/blender.exe"), reverse=True)]
    found = shutil.which("blender")
    if found:
        out.append(("blender on PATH", Path(found)))
    return out


def find_blender():
    """(path, label) of the first Blender that exists, or (None, reason)."""
    env = os.environ.get("NET_BLENDER")
    for label, path in blender_candidates():
        if path.is_file():
            return path, label
        if label == "NET_BLENDER":
            return None, f"NET_BLENDER is set to {env}, but there is no file there"
    return None, "Blender not found: set NET_BLENDER, keep ..\\bivvy-project\\_vendor, or run setup_blender.ps1"


def _blender():
    path, label = find_blender()
    if path is None:
        raise FileNotFoundError(label)
    return path, label


def _stream(cmd, log_path, on_line):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", creationflags=flags)
        for line in proc.stdout:
            log.write(line)
            line = line.rstrip()
            # Blender prints render progress per sample; keep the log readable.
            if line and not line.startswith(("Fra:", "Saved:", " Time:", "Info: Saved")):
                on_line(line)
        return proc.wait()


def run(cfg, quick=False, state="deployed", on_line=print):
    """Write the resolved config, run Blender, return (exit code, output folder)."""
    blender, label = _blender()
    on_line(f"[studio] Blender: {blender} ({label})")
    out = OUTPUT / cfg["id"]
    out.mkdir(parents=True, exist_ok=True)
    resolved = out / "resolved_config.json"
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    cmd = [str(blender), "-b", "--factory-startup", "--python-exit-code", "2", "--python", str(SCRIPT), "--",
           "--config", str(resolved), "--out", str(out), "--cache", str(OUTPUT / "_texture_cache")]
    if quick:
        cmd += ["--quick", "--state", state]
    log_path = out / ("build_log_quick.txt" if quick else "build_log.txt")
    return _stream(cmd, log_path, on_line), out
