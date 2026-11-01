"""Blender entry point. Run by Net Studio (or by hand):

  blender -b --factory-startup --python run_net.py -- --config resolved.json --out <folder> [--quick] [--state ...]

Full run: draw the texture maps (cached), build LOD0-2 and the markers, validate, export FBX / GLB / textures /
manifest, save the .blend, render every preview, then re-import the FBX and read the GLB back to check them.
Writes validation_report.json and exits 1 if a check failed.
--quick: LOD0 only and one three-quarter render in the chosen --state (deployed, scooping, lying, wet, disassembled).
"""
import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from net import build, export, materials, scene, validate  # noqa: E402

PREVIEW_PREFIXES = ("Preview", "Cam_", "Ground", "Water", "Sun")


def log(msg):
    print(f"[net] {msg}", flush=True)


def swap_materials(objs, mats):
    for o in objs:
        for i, m in enumerate(o.data.materials):
            base = m.name.split(".")[0].replace("_Wet", "").replace("_Preview", "")
            o.data.materials[i] = mats[base]


def disassemble(net, objs, apart):
    """Move each part to its display layout (Unity positions converted back to the build frame); returns a restore list."""
    saved = [(o, o.location.copy()) for o in objs]
    for o in objs:
        part = o.name.split("_", 1)[1]
        x, y, z = apart[part]
        o.location = Vector((x, z, y))
    return saved


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--state", default="deployed", choices=["deployed", "scooping", "lying", "wet", "disassembled"])
    args = ap.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    out = os.path.abspath(args.out)
    prev = os.path.join(out, "previews")
    os.makedirs(prev, exist_ok=True)
    cache = args.cache or os.path.join(os.path.dirname(out), "_texture_cache")
    t0 = time.time()

    sc = scene.reset()
    library, tex_folder = materials.build_library(cfg, cache, log)
    mats = materials.preview_materials(cfg, library, tex_folder)
    model = scene.collection(sc, "Net")
    net, root, lods, markers = build.build_all(cfg, mats, model, lods=(0,) if args.quick else (0, 1, 2))
    log(f"build: {', '.join(f'LOD{k} {sum(validate.tri_count(o) for o in objs)} tris' for k, objs in lods.items())} "
        f"({time.time() - t0:.1f}s)")
    env = scene.environment(sc, cfg)
    pr = scene.props(sc, net)
    cams = scene.cameras(sc, net)

    if args.quick:
        scene.configure_eevee(sc, cfg, quick=True)
        swap_materials(lods[0], materials.preview_materials(cfg, library, tex_folder, suffix="_Preview", clip=False))
        if args.state == "scooping":
            build.set_pose(lods[0], 1.0)
            for o in pr["fish"]:
                o.hide_render = False
        elif args.state == "lying":
            build.set_pose(lods[0], 1.0, build.LYING_KEY)
            scene.ground_at(env, net.geo.lying_ground_z())
        elif args.state == "wet":
            swap_materials(lods[0], materials.preview_materials(cfg, library, tex_folder, wetness=1.0, suffix="_Wet", clip=False))
        elif args.state == "disassembled":
            disassemble(net, lods[0], export.display_states(net)["disassembled"])
        scene.render(sc, cams["three_quarter"], os.path.join(prev, f"quick_{args.state}.png"), log)
        return 0

    rep = validate.Report()
    for k in (1, 2):
        for o in lods[k]:
            o.hide_render = True
    validate.validate_model(cfg, net, lods, markers, library, rep)
    log(f"validate: model checks done ({time.time() - t0:.1f}s)")

    export_dir = os.path.join(out, "export")
    fbx, glb, expected, manifest = export.export_all(cfg, net, root, lods, markers, library, tex_folder, export_dir, log)
    blend = os.path.join(out, f"{cfg['id']}.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
    log(f"saved: {blend}")

    scene.configure_eevee(sc, cfg, quick=False)
    shown = materials.preview_materials(cfg, library, tex_folder, suffix="_Preview", clip=False)
    for k in (0, 1, 2):
        swap_materials(lods[k], shown)
    main_views = ["three_quarter", "side", "top", "front", "head", "spreader", "bag_detail", "under"]
    paths = {}
    for v in main_views:
        scene.backdrop(env, "sky" if v == "under" else "bank")
        paths[v] = scene.render(sc, cams[v], os.path.join(prev, f"{v}.png"), log)
    scene.backdrop(env, "bank")
    for o in pr["hands"]:
        o.hide_render = False
    paths["hand_scale"] = scene.render(sc, cams["hand_scale"], os.path.join(prev, "hand_scale.png"), log)
    paths["hands_whole"] = scene.render(sc, cams["three_quarter"], os.path.join(prev, "hands_whole.png"), log)
    for o in pr["hands"]:
        o.hide_render = True

    # Poses: scooping with the display-only fish, and the transition strip.
    build.set_pose(lods[0], 1.0)
    for o in pr["fish"]:
        o.hide_render = False
    paths["scooping"] = scene.render(sc, cams["three_quarter"], os.path.join(prev, "scooping.png"), log)
    for o in pr["fish"]:
        o.hide_render = True
    strip = []
    for w in (0.0, 0.5, 1.0):
        build.set_pose(lods[0], w)
        strip.append(scene.render(sc, cams["side"], os.path.join(prev, f"pose_{int(w * 100):03d}.png"), log))
    build.set_pose(lods[0], 0.0)
    scene.sheet(strip, os.path.join(prev, "pose_transition.png"), cols=3, scale=2)

    # Laid flat on the ground (the bank net by the pod).
    build.set_pose(lods[0], 1.0, build.LYING_KEY)
    scene.ground_at(env, net.geo.lying_ground_z())
    paths["lying"] = scene.render(sc, cams["three_quarter"], os.path.join(prev, "lying.png"), log)
    scene.render(sc, cams["head"], os.path.join(prev, "lying_head.png"), log)
    scene.ground_at(env, scene.GROUND_Z)
    build.set_pose(lods[0], 0.0, build.LYING_KEY)

    # Wet and dry: the same views, dry (the preset's wetness) then fully wet.
    wet = materials.preview_materials(cfg, library, tex_folder, wetness=1.0, suffix="_Wet", clip=False)
    dry_paths = [paths["bag_detail"], paths["head"]]
    swap_materials(lods[0], wet)
    wet_paths = [scene.render(sc, cams[v], os.path.join(prev, f"{v}_wet.png"), log) for v in ("bag_detail", "head")]
    swap_materials(lods[0], shown)
    scene.sheet([dry_paths[0], wet_paths[0], dry_paths[1], wet_paths[1]], os.path.join(prev, "wet_dry.png"), cols=2, scale=2)

    # Display-only disassembled layout.
    saved = disassemble(net, lods[0], export.display_states(net)["disassembled"])
    paths["disassembled"] = scene.render(sc, cams["three_quarter"], os.path.join(prev, "disassembled.png"), log)
    for o, loc in saved:
        o.location = loc

    # LODs side by side from the same camera.
    lod_paths = []
    for k in (0, 1, 2):
        for j in (0, 1, 2):
            for o in lods[j]:
                o.hide_render = j != k
        lod_paths.append(scene.render(sc, cams["head"], os.path.join(prev, f"lod{k}.png"), log))
    for j in (0, 1, 2):
        for o in lods[j]:
            o.hide_render = j != 0
    scene.sheet(lod_paths, os.path.join(prev, "lod_compare.png"), cols=3, scale=2)

    # Hole scale and readability at near, mid and far range against sky, water and bank.
    dist = []
    dcoll = scene.collection(sc, "DistanceCameras")
    for kind in ("sky", "water", "bank"):
        scene.backdrop(env, kind)
        for d in (0.7, 3.0, 12.0):
            cam = scene.distance_camera(dcoll, net, kind, d)
            dist.append(scene.render(sc, cam, os.path.join(prev, f"distance_{kind}_{d:g}m.png"), log, size=(640, 360)))
    scene.backdrop(env, "bank")
    scene.sheet(dist, os.path.join(prev, "distance_sheet.png"), cols=3)

    sheet_views = [paths[v] for v in ("three_quarter", "side", "top", "front", "head", "spreader", "bag_detail",
                                      "under", "hand_scale", "scooping", "disassembled", "lying")]
    scene.sheet(sheet_views, os.path.join(prev, "contact_sheet.png"), cols=4, scale=2)
    log(f"render: done ({time.time() - t0:.1f}s)")

    validate.validate_fbx(fbx, expected, rep, PREVIEW_PREFIXES)
    if glb:
        validate.validate_glb(glb, cfg, rep, PREVIEW_PREFIXES)
    rep.stats["seconds"] = round(time.time() - t0, 1)
    rep.stats["fbx"] = fbx
    rep.stats["glb"] = glb
    rep.stats["blend"] = blend
    report = rep.as_dict()
    with open(os.path.join(out, "validation_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    for c in report["checks"]:
        if c["status"] in ("fail", "warn"):
            log(f"{c['status'].upper()}: {c['check']} - {c['detail']}")
    ok = sum(c["status"] == "ok" for c in report["checks"])
    log(f"validation: {'PASSED' if report['passed'] else 'FAILED'} ({ok}/{len(report['checks'])} ok, "
        f"{len(report['checks']) - ok} warn/info/fail)")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        code = main()
    except Exception:  # noqa: BLE001 - report any crash to the caller with a non-zero exit
        traceback.print_exc()
        code = 2
    sys.stdout.flush()
    os._exit(code)
