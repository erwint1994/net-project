"""Command line for Net Studio.

  python -m studio.cli list
  python -m studio.cli check <preset>                      validate a preset without Blender
  python -m studio.cli generate <preset> [--quick] [--state deployed|scooping|lying|wet|disassembled]
  python -m studio.cli all [--quick]                       every preset in presets/
  python -m studio.cli blender                             which Blender would be used
  python -m studio.cli export-unity <preset> <unity project> [--yes]
"""
import argparse
import json
import sys

from . import config, runner, unity_export


def _load(preset):
    return config.load_json(preset) if preset.endswith(".json") else config.load_preset(preset)


def _generate(name, quick, state):
    cfg, notes = config.resolve(_load(name))
    for n in notes:
        print("note:", n)
    code, out = runner.run(cfg, quick=quick, state=state)
    print(f"output: {out}")
    report = out / "validation_report.json"
    if not quick and report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        print(f"validation ({name}):", "PASSED" if data["passed"] else "FAILED")
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(prog="net")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list presets")
    sub.add_parser("blender", help="show which Blender would be used")
    c = sub.add_parser("check", help="validate a preset (no Blender)")
    c.add_argument("preset")
    g = sub.add_parser("generate", help="build, validate, render and export a preset")
    g.add_argument("preset", help="preset name (see 'list') or a path to a preset .json")
    g.add_argument("--quick", action="store_true", help="LOD0 and one preview only")
    g.add_argument("--state", default="deployed", choices=["deployed", "scooping", "lying", "wet", "disassembled"])
    a = sub.add_parser("all", help="generate every preset")
    a.add_argument("--quick", action="store_true")
    e = sub.add_parser("export-unity", help="copy a generated net into a Unity project (Assets/NetStudio only)")
    e.add_argument("preset")
    e.add_argument("project")
    e.add_argument("--yes", action="store_true", help="copy without asking")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "list":
            for p in config.list_presets():
                print(p)
            return 0
        if args.cmd == "blender":
            for label, path in runner.blender_candidates():
                print(f"{'found  ' if path.is_file() else 'missing'} {label}: {path}")
            path, label = runner.find_blender()
            print("using:", path or "-", f"({label})")
            return 0 if path else 1
        if args.cmd == "check":
            cfg, notes = config.resolve(_load(args.preset))
            for n in notes:
                print("note:", n)
            print(json.dumps(config.describe(cfg), indent=2))
            print("OK")
            return 0
        if args.cmd == "generate":
            return _generate(args.preset, args.quick, args.state)
        if args.cmd == "all":
            codes = [_generate(p, args.quick, "deployed") for p in config.list_presets()]
            return max(codes) if codes else 1
        if args.cmd == "export-unity":
            cfg, _ = config.resolve(_load(args.preset))
            dest, files = unity_export.plan(runner.OUTPUT / cfg["id"] / "export", args.project, cfg["id"])
            print(f"Will copy {len(files)} files into {dest}:")
            for s, d in files:
                print(f"  {d.relative_to(dest)}")
            if not args.yes and input("Copy? [y/N] ").strip().lower() != "y":
                print("nothing copied")
                return 1
            print(f"copied {unity_export.copy(files)} files. In Unity: Tools > Net Studio > Rebuild All Net Prefabs")
            return 0
    except (config.ConfigError, ValueError, FileNotFoundError) as exc:
        print("error:", exc)
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
