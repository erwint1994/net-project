"""Preview set: sky, sun, a grass bank and a water plane, display-only hand and fish proxies, cameras, Eevee renders
and image sheets. Nothing in this module is ever exported: the proxies live in the PreviewProps collection and
the exporters only select the net's own hierarchy (the FBX round trip checks that).

The net stays in its neutral frame (handle along +Y at Z = 0, bag hanging to -Z), so the set is built round it.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

GROUND_Z = -1.3
WATER_Z = -1.35


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    return sc


def collection(scene, name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


def _set(obj, attr, value):
    try:
        setattr(obj, attr, value)
    except (AttributeError, TypeError, ValueError):
        pass


def _plane(name, coll, size, z, mat):
    mesh = bpy.data.meshes.new(name)
    s = size
    mesh.from_pydata([(-s, -s, z), (s, -s, z), (s, s, z), (-s, s, z)], [], [(0, 1, 2, 3)])
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return obj


def _grass():
    mat = bpy.data.materials.new("PreviewGrass")
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 0.7
    n1.inputs["Detail"].default_value = 6
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.05, 0.065, 0.02, 1)
    ramp.color_ramp.elements[1].color = (0.13, 0.13, 0.05, 1)
    nt.links.new(n1.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.95
    n2 = nt.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 120
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs[0], bsdf.inputs["Normal"])
    return mat


def _water():
    mat = bpy.data.materials.new("PreviewWater")
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.012, 0.02, 0.014, 1)
    bsdf.inputs["Roughness"].default_value = 0.06
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3.0
    n.inputs["Detail"].default_value = 4
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs[0], bsdf.inputs["Normal"])
    return mat


def _flat(name, rgb, rough=0.6):
    mat = bpy.data.materials.new(name)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    return mat


def environment(scene, cfg):
    r = cfg["render"]
    env = collection(scene, "Environment")
    world = bpy.data.worlds.new("Outdoor")
    scene.world = world
    nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    for kind in ("MULTIPLE_SCATTERING", "SINGLE_SCATTERING", "HOSEK_WILKIE"):
        try:
            sky.sky_type = kind
            break
        except TypeError:
            continue
    _set(sky, "sun_elevation", math.radians(r["sun_elevation_deg"]))
    _set(sky, "sun_rotation", math.radians(r["sun_azimuth_deg"]))
    _set(sky, "sun_disc", False)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = r["sky_strength"]
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])

    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = r["sun_strength"]
    sun_data.angle = math.radians(1.0)
    sun_data.color = (1.0, 0.96, 0.9)
    sun = bpy.data.objects.new("Sun", sun_data)
    el, az = math.radians(r["sun_elevation_deg"]), math.radians(r["sun_azimuth_deg"])
    d = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    env.objects.link(sun)
    ground = _plane("Ground", env, 60.0, GROUND_Z, _grass())
    water = _plane("Water", env, 80.0, WATER_Z, _water())
    water.hide_render = True
    return {"ground": ground, "water": water}


def ground_at(env, z):
    """Move the grass to height z (the lying pose rests the net on it)."""
    env["ground"].location.z = z - GROUND_Z


def backdrop(env, kind):
    """bank: grass under the net; water: water under it; sky: neither (the camera looks up)."""
    env["ground"].hide_render = kind != "bank"
    env["water"].hide_render = kind != "water"


# ------------------------------------------------------------------ proxies (display only)

def _ellipsoid(name, coll, centre, radii, mat, rot=None, segs=24, rings=12):
    mesh = bpy.data.meshes.new(name)
    verts, faces = [], []
    for i in range(rings + 1):
        th = math.pi * i / rings
        for k in range(segs):
            ph = 2 * math.pi * k / segs
            verts.append((radii[0] * math.cos(th), radii[1] * math.sin(th) * math.cos(ph), radii[2] * math.sin(th) * math.sin(ph)))
    for i in range(rings):
        for k in range(segs):
            a, b = i * segs + k, i * segs + (k + 1) % segs
            faces.append((a, b, b + segs, a + segs))
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.polygons.foreach_set("use_smooth", [True] * len(faces))
    obj = bpy.data.objects.new(name, mesh)
    obj.location = centre
    if rot is not None:
        obj.rotation_euler = rot
    coll.objects.link(obj)
    return obj


def hand_proxy(coll, net, y, name, skin):
    """A closed adult hand round the handle at y (palm ~85 mm wide): four curled fingers, thumb and palm."""
    g = net.geo
    r = g.handle_radius(y)
    objs = []
    fr = 0.0095
    for i in range(4):
        fy = y + (i - 1.5) * 0.021
        mesh = bpy.data.meshes.new(f"{name}_Finger{i}")
        verts, faces = [], []
        steps, segs = 10, 8
        ring_r = r + fr
        for s in range(steps + 1):
            a = math.radians(-40 + 250 * s / steps)
            c = Vector((ring_r * math.cos(a), fy, ring_r * math.sin(a)))
            t = Vector((-math.sin(a), 0, math.cos(a)))
            n1 = Vector((math.cos(a), 0, math.sin(a)))
            n2 = t.cross(n1)
            for k in range(segs):
                ph = 2 * math.pi * k / segs
                verts.append(tuple(c + (n1 * math.cos(ph) + n2 * math.sin(ph)) * fr * (0.85 if i == 3 else 1)))
        for s in range(steps):
            for k in range(segs):
                a, b = s * segs + k, s * segs + (k + 1) % segs
                faces.append((a, b, b + segs, a + segs))
        mesh.from_pydata(verts, [], faces)
        mesh.materials.append(skin)
        mesh.polygons.foreach_set("use_smooth", [True] * len(faces))
        o = bpy.data.objects.new(mesh.name, mesh)
        coll.objects.link(o)
        objs.append(o)
    objs.append(_ellipsoid(f"{name}_Palm", coll, (-(r + 0.018), y, 0.01), (0.045, 0.028, 0.05), skin, rot=(0, 0, math.pi / 2)))
    objs.append(_ellipsoid(f"{name}_Thumb", coll, (-(r + 0.004), y + 0.045, r + 0.006), (0.03, 0.011, 0.011), skin,
                           rot=(0, math.radians(-20), math.pi / 2)))
    objs.append(_ellipsoid(f"{name}_Wrist", coll, (-(r + 0.04), y - 0.01, -0.03), (0.06, 0.03, 0.035), skin,
                           rot=(0, math.radians(30), math.radians(10))))
    return objs


def fish_proxy(coll, net):
    """A ~70 cm common carp shape lying in the scooping bag (display only)."""
    bronze = _flat("PreviewFish", (0.16, 0.09, 0.03), 0.4)
    b = Vector(net.scoop.bottom_point())
    # Lying across the bag's bottom, nose towards the cord, inside the netting.
    body = _ellipsoid("PreviewFish_Body", coll, (b.x, b.y + 0.04, b.z + 0.2), (0.27, 0.06, 0.095), bronze,
                      rot=(0, math.radians(-10), math.radians(90)))
    tail = _ellipsoid("PreviewFish_Tail", coll, (b.x, b.y - 0.25, b.z + 0.24), (0.07, 0.012, 0.07), bronze,
                      rot=(0, 0, math.radians(90)))
    return [body, tail]


def props(scene, net):
    coll = collection(scene, "PreviewProps")
    skin = _flat("PreviewSkin", (0.32, 0.17, 0.11), 0.55)
    g = net.geo
    hands = hand_proxy(coll, net, g.markers()["Marker_GripRear"][1], "PreviewHandRear", skin)
    hands += hand_proxy(coll, net, g.front_grip, "PreviewHandFront", skin)
    fish = fish_proxy(coll, net)
    for o in hands + fish:
        o.hide_render = True
    return {"collection": coll, "hands": hands, "fish": fish}


# ------------------------------------------------------------------ cameras

def _camera(coll, name, loc, target, lens=35.0, ortho=None):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = 0.01
    data.clip_end = 300
    if ortho:
        data.type = "ORTHO"
        data.ortho_scale = ortho
    cam = bpy.data.objects.new(name, data)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(cam)
    return cam


def cameras(scene, net):
    g = net.geo
    coll = collection(scene, "Cameras")
    L = g.overall_length
    mid = Vector((0, L * 0.5, -0.25))
    head = Vector((0, g.pivot[1] + g.mouth_depth * 0.5, -0.3))
    P = Vector(g.pivot)
    bag_side = Vector(net.bag.point(0.33, 0.45))
    grip = Vector(g.markers()["Marker_GripRear"])
    cams = {
        "three_quarter": _camera(coll, "Cam_ThreeQuarter", (2.3, L * 0.5 - 2.6, 1.3), mid, lens=32),
        "side": _camera(coll, "Cam_Side", (6.0, L * 0.5, -0.3), (0, L * 0.5, -0.3), ortho=L * 1.12),
        "top": _camera(coll, "Cam_Top", (0, L * 0.5, 6.0), (0, L * 0.5, 0), ortho=L * 1.12),
        "front": _camera(coll, "Cam_Front", (0.0, L + 2.6, 0.35), head, lens=40),
        "head": _camera(coll, "Cam_Head", (1.5, g.pivot[1] - 0.7, 1.2), head, lens=40),
        "spreader": _camera(coll, "Cam_Spreader", (0.22, P.y - 0.2, 0.17), (0, P.y + 0.02, 0), lens=50),
        "bag_detail": _camera(coll, "Cam_BagDetail", tuple(bag_side + Vector((0.32, -0.15, 0.08))), tuple(bag_side), lens=50),
        "hand_scale": _camera(coll, "Cam_HandScale", (0.45, grip.y + 0.25, 0.28), (0, grip.y + 0.12, 0), lens=40),
        "under": _camera(coll, "Cam_Under", (0.6, head.y - 0.4, -2.2), head + Vector((0, 0, -0.2)), lens=35),
    }
    # Top view turned so the net runs left to right across the wide frame.
    cams["top"].rotation_euler = (0.0, 0.0, math.pi / 2)
    return cams


def distance_camera(coll, net, backdrop_kind, distance):
    """A camera `distance` m from the bag's side, looking at it against the sky, the water or the bank."""
    target = Vector(net.bag.point(0.3, 0.35))
    if backdrop_kind == "sky":
        d = Vector((0.45, -0.25, -1.0)).normalized()
    elif backdrop_kind == "water":
        d = Vector((0.4, -0.3, 0.85)).normalized()
    else:
        d = Vector((0.75, -0.35, 0.45)).normalized()
    return _camera(coll, f"Cam_{backdrop_kind}_{distance}", tuple(target + d * distance), tuple(target), lens=50)


def configure_eevee(scene, cfg, quick):
    r = cfg["render"]
    scene.render.engine = "BLENDER_EEVEE"
    ee = scene.eevee
    _set(ee, "taa_render_samples", r["quick_samples"] if quick else r["samples"])
    _set(ee, "use_raytracing", True)
    _set(ee, "use_shadows", True)
    _set(ee, "shadow_ray_count", 2)
    _set(ee, "shadow_step_count", 8)
    _set(ee, "shadow_resolution_scale", 1.0)
    w, h = r["quick_resolution"] if quick else r["resolution"]
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    _set(scene.view_settings, "view_transform", "AgX")
    _set(scene.view_settings, "exposure", r["exposure"])


def render(scene, cam, path, log, size=None):
    if size:
        old = (scene.render.resolution_x, scene.render.resolution_y)
        scene.render.resolution_x, scene.render.resolution_y = size
    scene.camera = cam
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    if size:
        scene.render.resolution_x, scene.render.resolution_y = old
    log(f"render: {os.path.basename(path)}")
    return path


# ------------------------------------------------------------------ sheets

def _load(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)


def sheet(paths, out_path, cols=3, scale=1, pad=6):
    """Images in a grid (row 0 at the top). All tiles are cropped to the first image's size."""
    tiles = [_load(p)[::scale, ::scale] for p in paths]
    th, tw = tiles[0].shape[:2]
    rows = math.ceil(len(tiles) / cols)
    out = np.full((rows * (th + pad) + pad, cols * (tw + pad) + pad, 4), 0.1, dtype=np.float32)
    out[..., 3] = 1
    for k, t in enumerate(tiles):
        r, c = divmod(k, cols)
        y0 = out.shape[0] - (r + 1) * (th + pad)
        x0 = pad + c * (tw + pad)
        hh, ww = min(th, t.shape[0]), min(tw, t.shape[1])
        out[y0 + th - hh:y0 + th, x0:x0 + ww] = t[t.shape[0] - hh:, :ww]
    img = bpy.data.images.new("Sheet", out.shape[1], out.shape[0], alpha=False)
    img.pixels.foreach_set(out.ravel())
    img.filepath_raw = out_path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return out_path


def net_pixel_share(path, background_path=None):
    """Share of pixels that differ from the background render (how much of the frame the net covers)."""
    a = _load(path)[..., :3]
    if background_path is None:
        return None
    b = _load(background_path)[..., :3]
    return float((np.abs(a - b).max(axis=-1) > 0.02).mean())


def place(objs, offset):
    m = Matrix.Translation(Vector(offset))
    for o in objs:
        o.matrix_world = m @ o.matrix_world
