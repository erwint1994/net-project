"""FBX (Unity: all LODs, the scooping blendshape, markers), GLB (LOD0, textured, morph target), textures and the
manifest the Unity importer reads (export/net_manifest.json). Only the net's own hierarchy is selected, so preview
proxies (hands, fish), the set and the cameras never reach a file.

Axes: the build frame (X right, Y forward, Z up) goes out with axis_up=Y, axis_forward=-Z and baked space
transforms, which Unity reads (bakeAxisConversion) as X right, +Y up, +Z forward. The Unity import test checks it
against the manifest's markers.
"""
import datetime
import json
import os
import shutil
import sys

import bpy

from .build import LYING_KEY, SHAPE_KEY
from .materials import NET, wet_values
from .validate import tri_count

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from studio.config import describe  # noqa: E402
from studio.geometry import to_unity  # noqa: E402

SCHEMA = "carp-net-studio/1"
# Where each LOD hands over, in metres from the camera at a 60 deg vertical FOV: LOD0 -> LOD1 at 2 m, LOD1 -> LOD2 at
# 19 m, culled at 280 m. The importer turns these into LODGroup heights, and NetStudioNet cancels QualitySettings.lodBias
# (2 on the game's PC High), so the clipped close-up netting is only used where its holes are resolved.
LOD_SWITCH_M = [2.0, 19.0, 280.0]
LOD_REFERENCE_FOV_DEG = 60.0
# Netting per LOD. Close up: alpha clip (crisp holes, depth-correct, clipped shadows). From LOD1 on: alpha-blended haze
# whose opacity is the twine's coverage. Measured in Unity (docs/NETTING_DISTANCE.md): every alpha-clip mip chain either
# vanishes (plain mips, 1 % at 3 m), turns solid (Unity's coverage preservation, 90 %) or thins out (quantile mips,
# 11-15 %) past ~3 m. The blended bags cast no shadow: URP would draw a blended bag's shadow solid.
LOD_NETTING = ["clip", "blend", "blend"]
LOD_BAG_SHADOWS = [True, False, False]
# URP smoothness: the mask map holds the dry smoothness; wetness multiplies it (capped below this).
SMOOTHNESS_CAP = 0.92


def _r(p, nd=5):
    return [round(float(c), nd) for c in p]


def _u(p):
    return _r(to_unity(p))


def _select(objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def display_states(net):
    """Assembly transforms (Unity local positions of each part's origin) and a clearly separate disassembled display
    layout: handle sections side by side, head unscrewed and laid beyond them. Display only; not a gameplay state."""
    g = net.geo
    sections = g.handle_sections()
    assembled = {s["name"]: _u((0, s["from_m"], 0)) for s in sections}
    assembled["Head"] = assembled["NetBag"] = _u(g.pivot)
    apart = {}
    top = 0.0
    for k, s in enumerate(sections):
        x = 0.08 * k
        apart[s["name"]] = _u((x, s["spigot_m"], 0.0))
        top = max(top, s["spigot_m"] + s["to_m"] - s["from_m"])
    head_at = (0.0, top + 0.3, 0.0)
    apart["Head"] = apart["NetBag"] = _u(head_at)
    return {"assembled": assembled, "disassembled": apart}


def export_all(cfg, net, root, lods, markers, library, tex_folder, out_dir, log):
    os.makedirs(out_dir, exist_ok=True)
    tex_out = os.path.join(out_dir, "Textures")
    os.makedirs(tex_out, exist_ok=True)
    slug = cfg["id"]
    used = sorted({m.name for objs in lods.values() for o in objs for m in o.data.materials if m})
    m = cfg["material"]
    tint, smooth_wet = wet_values(cfg, 1.0)
    materials = {}
    for name in used:
        info = library[name]
        files = {}
        for kind in ("base", "normal", "mask", "roughness"):
            shutil.copy2(os.path.join(tex_folder, info["files"][kind]), os.path.join(tex_out, info["files"][kind]))
            files[kind] = "Textures/" + info["files"][kind]
        tx, ty = info["tile_m"]
        entry = {"base_map": files["base"], "normal_map": files["normal"], "mask_map": files["mask"],
                 "roughness_map": files["roughness"], "tiling": [round(1.0 / tx, 4), round(1.0 / ty, 4)],
                 "tile_m": [tx, ty], "metallic": info["metallic"], "smoothness": info["smoothness"],
                 "smoothness_max": info["smoothness_max"],
                 "wet": {"base_tint_at_full": round(tint, 4), "smoothness_scale_at_full": round(smooth_wet, 4),
                         "smoothness_scale_cap": round(max(1.0, SMOOTHNESS_CAP / max(info["smoothness_max"], 1e-3)), 4)},
                 "alpha": None}
        if name == NET:
            entry["alpha"] = {"mode": "clip", "cutoff": m["alpha_cutoff"], "double_sided": True,
                              "alpha_to_coverage": False, "mip_chain": "coverage-keeping (built by the Unity importer)",
                              "far_lods": "alpha-blended haze, plain mips (see lods[].netting)",
                              "cast_shadows": "clipped at LOD0 only", **info["net"]}
        materials[name] = entry

    every = [root] + [o for objs in lods.values() for o in objs] + markers
    fbx = os.path.join(out_dir, f"{slug}.fbx")
    _select(every)
    bpy.ops.export_scene.fbx(
        filepath=fbx, use_selection=True, object_types={"MESH", "EMPTY"},
        apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS", global_scale=1.0,
        axis_forward="-Z", axis_up="Y", bake_space_transform=True,
        mesh_smooth_type="OFF", use_tspace=True, use_mesh_modifiers=False,
        add_leaf_bones=False, path_mode="STRIP", embed_textures=False, use_custom_props=False,
        bake_anim=False)
    log(f"export: {fbx}")

    glb = None
    if cfg["export"]["glb"]:
        glb = os.path.join(out_dir, f"{slug}_LOD0.glb")
        _select([root] + lods[0] + markers)
        bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_yup=True,
                                  export_apply=False, export_materials="EXPORT", export_morph=True,
                                  export_animations=False)
        log(f"export: {glb}")

    expected = {"objects": {}, "markers": {}}
    for o in every:
        if o.type == "MESH":
            keys = [k.name for k in o.data.shape_keys.key_blocks] if o.data.shape_keys else []
            expected["objects"][o.name] = {"triangles": tri_count(o), "materials": [x.name for x in o.data.materials if x],
                                           "shape_keys": keys, "location": list(o.location)}
        else:
            expected["objects"][o.name] = {}
    for e in markers:
        expected["markers"][e.name] = list(e.location)

    g = net.geo
    dims = describe(cfg)
    mk = {e.name: _u(e.location) for e in markers}
    poly = [_u(p) for p in g.mouth_polygon(48)]
    sections = []
    states = display_states(net)
    for s in g.handle_sections():
        sections.append({"name": s["name"], "from_m": s["from_m"], "to_m": s["to_m"], "spigot_m": s["spigot_m"],
                         "objects": [f"LOD{k}_{s['name']}" for k in sorted(lods)],
                         "assembled_position": states["assembled"][s["name"]],
                         "disassembled_position": states["disassembled"][s["name"]]})
    tris = {f"LOD{k}": sum(tri_count(o) for o in objs) for k, objs in lods.items()}
    pickup = None
    if cfg["export"]["pickup_proxy"]:
        y0, y1 = g.grip_start, g.front_grip + 0.2
        pickup = {"enabled": True, "type": "capsule", "centre": _u((0, (y0 + y1) / 2, 0)), "direction": "Z",
                  "height_m": round(y1 - y0, 4), "radius_m": round(g.handle_r0 + 0.012, 4)}
    manifest = {
        "schema": SCHEMA,
        "id": slug,
        "name": cfg["name"],
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "files": {"fbx": os.path.basename(fbx), "glb": os.path.basename(glb) if glb else None,
                  "textures": sorted("Textures/" + f for f in os.listdir(tex_out))},
        "units": "metres",
        "axes": {"frame": "Unity: X right, +Y up, +Z forward",
                 "origin": "butt cap centre (rear end of the handle)",
                 "handle": "along +Z from the origin to the spreader",
                 "mouth": "forward of the spreader along +Z, opening towards +Y in the neutral deployed pose; "
                          "bag hangs towards -Y",
                 "glb": "glTF standard: +Y up, the mouth faces -Z (Blender's default glTF conversion)"},
        "root": root.name,
        "dimensions": dims,
        "head": {
            "triangle": {"spreader": mk["Marker_Spreader"], "corner_right": mk["Marker_CornerRight"],
                         "corner_left": mk["Marker_CornerLeft"]},
            "mouth_polygon": poly,
            "mouth_polygon_note": "bag opening along the arms and cord, 48 points, clockwise seen from +Y (Unity), "
                                  "first point where the right arm leaves the spreader",
            "mouth_plane": {"point": mk["Marker_MouthCentre"], "normal": [0.0, 1.0, 0.0]},
            "depth": {"deployed_m": round(net.bag.depth, 4), "scooping_m": round(net.scoop.depth, 4),
                      "bag_bottom_deployed": mk["Marker_BagBottom"], "bag_bottom_scooping": mk["Marker_BagBottomScooping"]},
        },
        "markers": mk,
        "sections": sections,
        "display_states": {"note": "disassembled is a display layout only, never a gameplay deployment; "
                                   "markers are valid for the assembled net",
                           **states},
        "pose": {"mechanism": "blendshape", "blendshape": SHAPE_KEY, "lying_blendshape": LYING_KEY,
                 "objects": [f"LOD{k}_NetBag" for k in sorted(lods)],
                 "states": {"deployed": {SHAPE_KEY: 0.0, LYING_KEY: 0.0}, "scooping": {SHAPE_KEY: 100.0, LYING_KEY: 0.0},
                            "lying": {SHAPE_KEY: 0.0, LYING_KEY: 100.0}},
                 "lying_ground_y": round(g.lying_ground_z(), 5),
                 "lying_note": "laid flat (net frame unturned, mouth facing +Y): put the ground at lying_ground_y, "
                               "under the spreader's rear boss and the butt cap",
                 "note": "display poses only: no cloth, water drag, load or capture simulation; the rim never moves"},
        "materials": materials,
        "net": {"hole_mm": cfg["bag"]["hole_mm"], "strand_mm": cfg["bag"]["strand_mm"],
                "pitch_mm": round(cfg["bag"]["hole_mm"] + cfg["bag"]["strand_mm"], 3),
                "hole_definition": "clear opening across a hole, strand edge to strand edge",
                "orientation": cfg["bag"]["hole_orientation"], "knot": cfg["bag"]["knot"],
                "tile_m": materials[NET]["tile_m"][0] if NET in materials else None},
        "wetness": {"default": m["wetness"], "note": "material parameters only (base tint, smoothness), no water simulation"},
        "lod_switch_m": LOD_SWITCH_M,
        "lod_reference_fov_deg": LOD_REFERENCE_FOV_DEG,
        "lods": [{"name": f"LOD{k}", "objects": [o.name for o in objs], "switch_m": LOD_SWITCH_M[k],
                  "triangles": tris[f"LOD{k}"], "netting": LOD_NETTING[k], "bag_casts_shadows": LOD_BAG_SHADOWS[k]}
                 for k, objs in sorted(lods.items())],
        "triangle_ceilings": cfg["quality"]["triangle_ceilings"],
        "pickup_proxy": pickup or {"enabled": False},
        "capture": {"note": "no capture logic and no bag collider: use the mouth polygon and plane for "
                            "fish-over-mouth tests; the render mesh is not a capture volume"},
    }
    # The same data as plain arrays for Unity's JsonUtility (it has no dictionaries).
    manifest["unity"] = {
        "lods": [{"name": f"LOD{k}", "objects": [o.name for o in objs], "switchMetres": LOD_SWITCH_M[k],
                  "bagCastsShadows": LOD_BAG_SHADOWS[k], "blendedNetting": LOD_NETTING[k] == "blend"}
                 for k, objs in sorted(lods.items())],
        "materials": [{"name": n, "baseMap": e["base_map"], "normalMap": e["normal_map"], "maskMap": e["mask_map"],
                       "tiling": e["tiling"], "metallic": e["metallic"], "smoothness": e["smoothness"],
                       "alphaClip": e["alpha"] is not None, "cutoff": e["alpha"]["cutoff"] if e["alpha"] else 0.0,
                       "doubleSided": e["alpha"] is not None,
                       "wetTint": e["wet"]["base_tint_at_full"], "wetSmoothness": e["wet"]["smoothness_scale_at_full"],
                       "smoothnessCap": e["wet"]["smoothness_scale_cap"],
                       "strandPx": e["alpha"]["strand_px"] if e["alpha"] else 0.0,
                       "pitchPx": e["alpha"]["pitch_px"] if e["alpha"] else 0.0}
                      for n, e in materials.items()],
        "markers": [{"name": n, "position": p} for n, p in mk.items()],
        "mouthPolygon": [{"name": str(i), "position": p} for i, p in enumerate(poly)],
        "mouthNormal": [0.0, 1.0, 0.0],
        "sections": [{"name": s["name"], "objects": s["objects"], "assembled": s["assembled_position"],
                      "disassembled": s["disassembled_position"]} for s in sections]
                    + [{"name": part, "objects": [f"LOD{k}_{part}" for k in sorted(lods)],
                        "assembled": states["assembled"][part], "disassembled": states["disassembled"][part]}
                       for part in ("Head", "NetBag")],
        "lodReferenceFov": LOD_REFERENCE_FOV_DEG,
        "blendshape": SHAPE_KEY,
        "lyingBlendshape": LYING_KEY,
        "lyingGroundY": round(g.lying_ground_z(), 5),
        "bagObjects": [f"LOD{k}_NetBag" for k in sorted(lods)],
        "defaultWetness": m["wetness"],
        "pickupEnabled": bool(pickup),
        "pickupCentre": pickup["centre"] if pickup else [0.0, 0.0, 0.0],
        "pickupHeight": pickup["height_m"] if pickup else 0.0,
        "pickupRadius": pickup["radius_m"] if pickup else 0.0,
    }
    path = os.path.join(out_dir, "net_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    log(f"export: {path}")
    return fbx, glb, expected, manifest
