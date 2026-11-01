"""Automated checks on the built net and on its exports. Every check is recorded as ok / warn / fail."""
import json
import math
import os
import struct
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from studio.geometry import inches_to_m, point_in_polygon_xy, polygon_area_xy  # noqa: E402

SHAPE_KEY = "Scooping"
LYING_KEY = "Lying"


class Report:
    def __init__(self):
        self.checks = []
        self.stats = {}

    def add(self, name, ok, detail, level="fail"):
        self.checks.append({"check": name, "status": "ok" if ok else level, "detail": detail})
        return ok

    def info(self, name, detail):
        self.checks.append({"check": name, "status": "info", "detail": detail})

    @property
    def failed(self):
        return [c for c in self.checks if c["status"] == "fail"]

    def as_dict(self):
        return {"passed": not self.failed, "checks": self.checks, "stats": self.stats}


def tri_count(obj):
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def world_verts(obj, key=None):
    """World positions of a mesh's vertices, from the basis or from a shape key."""
    mw = obj.matrix_world
    if key is not None:
        return [mw @ k.co for k in obj.data.shape_keys.key_blocks[key].data]
    return [mw @ v.co for v in obj.data.vertices]


def bounds(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


def mesh_hygiene(rep, obj):
    me = obj.data
    name = obj.name
    fixed = me.validate(verbose=False)
    rep.add(f"{name}: mesh data valid", not fixed, "Blender had to repair the mesh" if fixed else "clean")
    used = set()
    for p in me.polygons:
        used.update(p.vertices)
    loose = len(me.vertices) - len(used)
    rep.add(f"{name}: no loose vertices", loose == 0, f"{loose} loose")
    tiny = sum(1 for p in me.polygons if p.area < 1e-10)
    rep.add(f"{name}: no zero-area faces", tiny == 0, f"{tiny} of {len(me.polygons)}")
    bad = sum(1 for v in me.vertices if not all(math.isfinite(c) for c in v.co))
    rep.add(f"{name}: finite coordinates", bad == 0, f"{bad} bad")
    rep.add(f"{name}: has UVs", len(me.uv_layers) > 0, ", ".join(uv.name for uv in me.uv_layers) or "none")
    empty = [k for k, m in enumerate(me.materials) if m is None]
    rep.add(f"{name}: materials assigned", len(me.materials) > 0 and not empty,
            ", ".join(m.name for m in me.materials if m) or "none")


def _by_part(objs, part):
    return next((o for o in objs if o.name.split("_", 1)[1] == part), None)


def _faces_of(obj, material):
    names = [m.name for m in obj.data.materials]
    if material not in names:
        return []
    k = names.index(material)
    return [p for p in obj.data.polygons if p.material_index == k]


def _symmetry(obj):
    """Largest distance from a vertex mirrored across X to the nearest vertex (m)."""
    vs = world_verts(obj)
    kd = KDTree(len(vs))
    for i, v in enumerate(vs):
        kd.insert(v, i)
    kd.balance()
    return max(kd.find(Vector((-v.x, v.y, v.z)))[2] for v in vs)


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (a + ab * t - p).length


def validate_model(cfg, net, lods, markers, library, rep):
    g = net.geo
    q, bc = cfg["quality"], cfg["bag"]
    ceilings = q["triangle_ceilings"]
    for lod, objs in lods.items():
        for o in objs:
            mesh_hygiene(rep, o)
        rep.stats[f"LOD{lod}_triangles"] = sum(tri_count(o) for o in objs)
    tris = [rep.stats[f"LOD{k}_triangles"] for k in sorted(lods)]
    for k, t in enumerate(tris):
        rep.add(f"LOD{k} triangle ceiling", t <= ceilings[k], f"{t} (ceiling {ceilings[k]})")
    if len(tris) == 3:
        rep.add("LOD1 is lighter than LOD0", tris[1] < tris[0] * 0.7, f"{tris[1]} vs {tris[0]}")
        rep.add("LOD2 is lighter than LOD1", tris[2] < tris[1] * 0.7, f"{tris[2]} vs {tris[1]}")

    # ---- dimensions
    L = inches_to_m(cfg["head"]["arm_length_in"])
    for side, c in (("right", g.corner_right), ("left", g.corner_left)):
        d = (Vector(c) - Vector(g.pivot)).length
        rep.add(f"{side} arm: pivot to corner = {cfg['head']['arm_length_in']} in", abs(d - L) < 5e-4,
                f"{d:.4f} m (want {L:.4f} m)")
    w = (Vector(g.corner_right) - Vector(g.corner_left)).length
    rep.add("mouth width = 2 L sin(opening / 2)", abs(w - g.mouth_width) < 5e-4, f"{w:.4f} m")
    lods0 = lods[0]
    handle_objs = [o for o in lods0 if "Handle" in o.name]
    lo, hi = bounds(handle_objs)
    rep.add("butt cap at the origin", abs(lo.y) < 1e-3, f"rear end at y = {lo.y * 1000:.1f} mm")
    rep.add("handle on the +Y axis", abs(lo.x + hi.x) < 1e-3 and abs(lo.z + hi.z) < 1e-3,
            f"x {lo.x:.4f}..{hi.x:.4f}, z {lo.z:.4f}..{hi.z:.4f}")
    shoulder = max(v.y for o in handle_objs for v in world_verts(o) if math.hypot(v.x, v.z) > 0.0049 + 1e-4)
    rep.add("handle length (butt end to the threaded insert's face)", abs(shoulder - g.handle_len) < 1e-3,
            f"{shoulder:.4f} m (preset {g.handle_len} m)")
    head = _by_part(lods0, "Head")
    hlo, hhi = bounds([head])
    gap = hlo.y - shoulder
    rep.add("handle meets the spreader block (no gap, no overlap)", abs(gap) < 1e-3, f"{gap * 1000:+.2f} mm")
    rep.stats["LOD0_overall_length_m"] = round(hhi.y - lo.y, 4)

    # ---- symmetry and joins
    asym = _symmetry(head)
    rep.add("head is symmetric (arms, sockets, caps, cord)", asym < 5e-4, f"worst {asym * 1000:.2f} mm")
    socket_mouth = g.socket_len
    arm_in = 0.022
    rep.add("arms sit in their sockets", socket_mouth - arm_in >= 0.03,
            f"{(socket_mouth - arm_in) * 1000:.0f} mm inside the socket")
    hv = world_verts(head)
    for side, c in (("right", g.corner_right), ("left", g.corner_left)):
        near = min((v - Vector(c)).length for v in hv)
        rep.add(f"{side} tip cap encloses the corner", near < g.arm_r1 + 0.004, f"nearest cap surface {near * 1000:.1f} mm")
    if g.sections == 2:
        lower, upper = _by_part(lods0, "HandleLower"), _by_part(lods0, "HandleUpper")
        top_lower = max(v.y for v in world_verts(lower))
        outer_upper = min(v.y for v in world_verts(upper) if math.hypot(v.x, v.z) > g.handle_radius(g.joint) - 0.0005)
        rep.add("two-piece: sections meet at the joint", abs(top_lower - g.joint) < 1e-3 and abs(outer_upper - g.joint) < 1e-3,
                f"lower ends {top_lower:.4f} m, upper starts {outer_upper:.4f} m, joint {g.joint:.4f} m")
        spig = min(v.y for v in world_verts(upper))
        rep.add("two-piece: spigot inserted into the lower section", abs((g.joint - spig) - g.spigot) < 1e-3,
                f"{(g.joint - spig) * 1000:.0f} mm")
        spig_r = max(math.hypot(v.x, v.z) for v in world_verts(upper) if v.y < g.joint - 0.002)
        tube_r = min(math.hypot(v.x, v.z) for p in _faces_of(lower, "NT_Carbon") for v in
                     (lower.matrix_world @ lower.data.vertices[i].co for i in p.vertices) if v.y > g.joint - g.spigot - 0.01)
        rep.add("two-piece: spigot hidden inside the lower tube", spig_r < tube_r - 0.0005,
                f"spigot {spig_r * 2000:.1f} mm inside a {tube_r * 2000:.1f} mm tube")
    # Tube normals point out of the handle.
    # (end caps face along the axis and are left out)
    carbon = [p for o in handle_objs for p in _faces_of(o, "NT_Carbon") if abs(p.normal.y) < 0.9]
    out = 0
    for p in carbon:
        c = p.center
        out += Vector((c.x, 0, c.z)).dot(p.normal) > 0
    rep.add("handle surfaces face outwards", out >= 0.98 * len(carbon), f"{out} of {len(carbon)}")

    # ---- bag: rim, drape, poses, UVs, per LOD
    poly = g.mouth_polygon(96)
    for lod, objs in sorted(lods.items()):
        bag = _by_part(objs, "NetBag")
        n_rim, rows = q["lod_rim_segments"][lod], q["lod_bag_rows"][lod]
        n_grid = n_rim * rows + 1
        base = world_verts(bag)[:n_grid]
        keys = bag.data.shape_keys
        has_key = keys is not None and SHAPE_KEY in keys.key_blocks
        rep.add(f"LOD{lod} bag has the '{SHAPE_KEY}' blendshape", has_key, "present" if has_key else "missing")
        weights = {k.name: k.value for k in keys.key_blocks[1:]} if keys else {}
        rep.add(f"LOD{lod} bag rests in the deployed pose (blendshape weights 0)", all(w == 0 for w in weights.values()),
                ", ".join(f"{n} {w:g}" for n, w in weights.items()))
        scoop = world_verts(bag, SHAPE_KEY)[:n_grid] if has_key else base
        has_lying = keys is not None and LYING_KEY in keys.key_blocks
        rep.add(f"LOD{lod} bag has the '{LYING_KEY}' blendshape", has_lying, "present" if has_lying else "missing")
        if has_lying:
            lying = world_verts(bag, LYING_KEY)
            ground = g.lying_ground_z()
            moved_l = max((a - b).length for a, b in zip(base[:n_rim], lying[:n_rim]))
            rep.add(f"LOD{lod} rim stays attached in the lying pose", moved_l < 1e-5, f"moves {moved_l * 1000:.3f} mm")
            low = min(v.z for v in lying)
            high = max(v.z for v in lying[:n_grid])
            rep.add(f"LOD{lod} lying bag rests on the ground, not through it", low >= ground - 1e-4 and high - ground < 0.06,
                    f"{(low - ground) * 1000:.1f}-{(high - ground) * 1000:.1f} mm above the ground under the net")
            reach = max(math.hypot(v.x - net.bag.centre[0], v.y - net.bag.centre[1]) for v in lying[:n_grid])
            rep.add(f"LOD{lod} lying bag stays by the frame", reach < max(math.hypot(p[0] - net.bag.centre[0], p[1] - net.bag.centre[1])
                                                                          for p in poly) + 0.1, f"{reach:.3f} m from the mouth centre")
        rim, rim_s = base[:n_rim], scoop[:n_rim]
        # Rim attachment: every rim vertex hangs just under an arm or the cord, the loop has no gaps, both poses agree.
        arms = [[Vector(p) for p in g.arm_polyline(s, 80)] for s in (1, -1)]
        cord = (Vector(g.corner_left), Vector(g.corner_right))
        # The short back edge across the front of the spreader, between the socket exits.
        back = (Vector(g.arm_point(-1, g.arm_start_s())), Vector(g.arm_point(1, g.arm_start_s())))
        worst = 0.0
        for v in rim:
            d = min(min(_seg_dist(v, a[i], a[i + 1]) for i in range(len(a) - 1)) for a in arms)
            d = min(d, _seg_dist(v, *cord))
            d = min(d, _seg_dist(v, *back))
            worst = max(worst, d)
        rep.add(f"LOD{lod} bag rim hangs on the arms and cord", worst < g.arm_r0 + 0.004,
                f"worst {worst * 1000:.1f} mm from the frame (arm radius {g.arm_r0 * 1000:.1f} mm)")
        step = max((rim[(i + 1) % n_rim] - rim[i]).length for i in range(n_rim))
        limit = 2.5 * net.bag.rim.length / n_rim
        rep.add(f"LOD{lod} bag rim is continuous", step < limit, f"longest rim edge {step * 1000:.0f} mm (limit {limit * 1000:.0f})")
        moved = max((a - b).length for a, b in zip(rim, rim_s))
        rep.add(f"LOD{lod} rim stays attached in the scooping pose", moved < 1e-5, f"moves {moved * 1000:.3f} mm")
        # Drape.
        top = max(v.z for v in base)
        rep.add(f"LOD{lod} bag stays below the mouth plane", top <= 1e-4, f"highest {top * 1000:.1f} mm")
        lowest = min(base, key=lambda v: v.z)
        lowest_s = min(scoop, key=lambda v: v.z)
        rep.add(f"LOD{lod} bag depth matches the preset", abs(-lowest.z - net.bag.depth) < 0.03 * net.bag.depth,
                f"{-lowest.z:.3f} m (preset {net.bag.depth} m)")
        rep.add(f"LOD{lod} scooping pose is deeper", -lowest_s.z > -lowest.z * 1.05,
                f"{-lowest_s.z:.3f} m vs {-lowest.z:.3f} m")
        mono = all(base[i * n_rim + j].z > base[(i + 1) * n_rim + j].z for i in range(rows - 1) for j in range(n_rim))
        rep.add(f"LOD{lod} bag hangs down without folding over (rows descend)", mono, "every column descends" if mono else "a column rises")
        simple = all(polygon_area_xy([tuple(base[i * n_rim + j]) for j in range(n_rim)]) > 0 for i in range(1, rows))
        simple_s = all(polygon_area_xy([tuple(scoop[i * n_rim + j]) for j in range(n_rim)]) > 0 for i in range(1, rows))
        rep.add(f"LOD{lod} bag rings stay open (no ring turns inside out)", simple and simple_s, "both poses")
        bm = Vector(net.bag.bottom_point())
        bms = Vector(net.scoop.bottom_point())
        rep.add(f"LOD{lod} bag bottom marker matches the mesh (both poses)",
                (lowest - bm).length < 0.03 and (lowest_s - bms).length < 0.03,
                f"deployed {(lowest - bm).length * 1000:.0f} mm, scooping {(lowest_s - bms).length * 1000:.0f} mm off")
        spread = max(math.hypot(v.x - net.bag.centre[0], v.y - net.bag.centre[1]) for v in base)
        far = max(math.hypot(p[0] - net.bag.centre[0], p[1] - net.bag.centre[1]) for p in poly)
        rep.add(f"LOD{lod} bag stays under the frame (no flare)", spread < far + 0.12, f"{spread:.3f} m vs rim {far:.3f} m")
        # Mouth open: straight down through the mouth centre the first thing hit is the bag's bottom.
        tree = BVHTree.FromObject(bag, bpy.context.evaluated_depsgraph_get())
        mc = Vector(g.mouth_centroid()) + Vector((0, 0, 0.2))
        mc_local = bag.matrix_world.inverted() @ mc
        hit = tree.ray_cast(mc_local, Vector((0, 0, -1)), 5.0)
        depth_hit = None if hit[0] is None else (bag.matrix_world @ hit[0]).z
        rep.add(f"LOD{lod} mouth is open (straight down hits the bag bottom)",
                depth_hit is not None and depth_hit < -0.75 * net.bag.depth,
                "nothing hit" if depth_hit is None else f"first hit at {depth_hit:.3f} m")
        if lod == 0:
            # Hole scale: twine bars keep their length (UV edge length = surface edge length), while the diamonds may
            # shear, as real netting does when it drapes. Area ratio is reported for information.
            edge, area = [], []
            uv = bag.data.uv_layers.active.data
            vs = bag.data.vertices
            for p in _faces_of(bag, "NT_Net"):
                if p.loop_total != 4 or p.area < 1e-7:
                    continue
                a = [uv[li].uv for li in p.loop_indices]
                c = [vs[vi].co for vi in p.vertices]
                for i in range(4):
                    d3 = (c[(i + 1) % 4] - c[i]).length
                    if d3 > 1e-5:
                        edge.append((a[(i + 1) % 4] - a[i]).length / d3)
                ua = abs(sum(a[i].x * a[(i + 1) % 4].y - a[(i + 1) % 4].x * a[i].y for i in range(4))) / 2
                area.append(ua / p.area)
            edge.sort()
            area.sort()
            med = edge[len(edge) // 2]
            p5, p95 = edge[len(edge) // 20], edge[len(edge) * 19 // 20]
            rep.add("netting UVs are in metres (holes keep their real size)", 0.95 < med < 1.05 and 0.8 < p5 and p95 < 1.45,
                    f"UV/surface edge length: median {med:.3f}, 5-95 % {p5:.3f}-{p95:.3f}")
            rep.info("netting shear (UV/surface area, 1 = square holes)",
                     f"median {area[len(area) // 2]:.2f}, 5-95 % {area[len(area) // 20]:.2f}-{area[len(area) * 19 // 20]:.2f}; "
                     "the diamonds shear towards the bottom as real netting does")
    # ---- hole scale and distance behaviour of the alpha
    info = library["NT_Net"]["net"]
    tile = library["NT_Net"]["tile_m"][0]
    pitch = (bc["hole_mm"] + bc["strand_mm"])
    rep.info("hole size", f"{bc['hole_mm']} mm clear opening, {bc['strand_mm']} mm twine, pitch {pitch:.1f} mm, "
             f"{info['holes_per_tile']} holes per {tile * 1000:.1f} mm tile")
    rep.add("twine is drawn wide enough to stay crisp up close", info["strand_px"] >= 8, f"{info['strand_px']} px per strand")
    cov = info["mip_coverage_plain"]
    rep.add("netting covers part of the bag, not all of it", 0.1 < info["coverage"] < 0.6, f"{info['coverage']:.0%} twine")
    lost = next((k for k, c in enumerate(cov) if c < 0.5 * info["coverage"]), None)
    rep.info("distant netting",
             f"a plain alpha test on box-filtered mips keeps {cov[:8]} of the texels per mip, so netting would vanish "
             f"from mip {lost}. In Unity: LOD0 (up to 2 m) clips against a coverage-keeping mip chain built by the "
             "importer; LOD1/LOD2 use an alpha-blended haze whose opacity is the twine's coverage (docs/NETTING_DISTANCE.md).")

    # ---- markers
    names = {e.name: e for e in markers}
    expected = list(g.markers()) + ["Marker_BagBottom", "Marker_BagBottomScooping"]
    missing = [n for n in expected if n not in names]
    rep.add("all markers present", not missing, "missing: " + ", ".join(missing) if missing else f"{len(expected)} markers")
    def at(n):
        return names[n].matrix_world.translation
    if not missing:
        rep.add("corner markers at the arm tips", (at("Marker_CornerRight") - Vector(g.corner_right)).length < 1e-4
                and (at("Marker_CornerLeft") - Vector(g.corner_left)).length < 1e-4, "exact")
        rep.add("left corner is on -X, right on +X", at("Marker_CornerLeft").x < 0 < at("Marker_CornerRight").x, "")
        rep.add("spreader marker inside the block", all(hlo[i] <= at("Marker_Spreader")[i] <= hhi[i] for i in range(3)), "")
        mc = at("Marker_MouthCentre")
        rep.add("mouth centre inside the mouth polygon", point_in_polygon_xy(mc, poly) and abs(mc.z) < 1e-6,
                f"({mc.x:.3f}, {mc.y:.3f}, {mc.z:.3f})")
        grips = all(abs(at(n).x) < 1e-6 and abs(at(n).z) < 1e-6 and 0 < at(n).y < g.handle_len
                    for n in ("Marker_GripRear", "Marker_GripFront"))
        rep.add("grip markers on the handle axis", grips, f"rear {at('Marker_GripRear').y:.3f} m, front {at('Marker_GripFront').y:.3f} m")
        if g.sections == 2:
            rep.add("joint marker at the section boundary", abs(at("Marker_HandleJoint").y - g.joint) < 1e-6, f"{g.joint:.3f} m")

    # ---- LODs keep the same shape
    lo0, hi0 = bounds(lods[0])
    for lod in sorted(lods):
        if lod == 0:
            continue
        lo1, hi1 = bounds(lods[lod])
        diff = max(max(abs(a - b) for a, b in zip(lo0, lo1)), max(abs(a - b) for a, b in zip(hi0, hi1)))
        rep.add(f"LOD{lod} keeps LOD0's size", diff < 0.025, f"bounds differ by {diff * 1000:.0f} mm")
    rep.stats["LOD0_size_m"] = [round(hi0.x - lo0.x, 3), round(hi0.y - lo0.y, 3), round(hi0.z - lo0.z, 3)]


def validate_fbx(path, expected, rep, preview_names):
    """Re-import the FBX into an empty file and compare it with what was exported."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    objs = {o.name: o for o in bpy.context.scene.objects}
    missing = [n for n in expected["objects"] if n not in objs]
    rep.add("FBX: every object came back", not missing, "all present" if not missing else "missing: " + ", ".join(missing))
    extra = [n for n in objs if n not in expected["objects"]]
    rep.add("FBX: nothing else in the file", not extra, "only the net" if not extra else "extra: " + ", ".join(extra))
    leaked = [n for n in objs if any(n.startswith(p) for p in preview_names)]
    rep.add("FBX: no preview proxies (hands, fish, set)", not leaked, "none" if not leaked else ", ".join(leaked))
    for name, exp in expected["objects"].items():
        o = objs.get(name)
        if o is None or o.type != "MESH":
            continue
        tris = tri_count(o)
        rep.add(f"FBX {name}: triangles", tris == exp["triangles"], f"{tris} (exported {exp['triangles']})")
        mats = sorted(m.name for m in o.data.materials if m)
        rep.add(f"FBX {name}: materials", mats == sorted(exp["materials"]), ", ".join(mats))
        rep.add(f"FBX {name}: UVs", len(o.data.uv_layers) > 0, f"{len(o.data.uv_layers)} UV layer(s)")
        if exp["shape_keys"]:
            keys = [k.name for k in o.data.shape_keys.key_blocks] if o.data.shape_keys else []
            rep.add(f"FBX {name}: blendshapes", SHAPE_KEY in keys and LYING_KEY in keys, ", ".join(keys) or "none")
        loc = o.matrix_world.translation
        rep.add(f"FBX {name}: origin", (loc - Vector(exp["location"])).length < 1e-4, f"{tuple(round(c, 4) for c in loc)}")
    worst = 0.0
    for name, p in expected["markers"].items():
        o = objs.get(name)
        if o is not None:
            worst = max(worst, (o.matrix_world.translation - Vector(p)).length)
    rep.add("FBX: markers where they were exported", worst < 1e-4, f"worst {worst * 1000:.3f} mm")


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, _, _ = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError("not a GLB file")
    length, kind = struct.unpack_from("<II", data, 12)
    return json.loads(data[20:20 + length].decode("utf-8"))


def validate_glb(path, cfg, rep, preview_names):
    doc = read_glb(path)
    mats = {m.get("name"): m for m in doc.get("materials", [])}
    net = mats.get("NT_Net", {})
    rep.add("GLB: netting is alpha-clipped (alphaMode MASK)", net.get("alphaMode") == "MASK",
            f"alphaMode {net.get('alphaMode')}, cutoff {net.get('alphaCutoff')}")
    cut = net.get("alphaCutoff", 0.5)
    rep.add("GLB: netting cutoff matches", abs(cut - cfg["material"]["alpha_cutoff"]) < 0.01, f"{cut}")
    rep.add("GLB: netting is double-sided", net.get("doubleSided") is True, f"{net.get('doubleSided')}")
    rep.add("GLB: textures embedded", len(doc.get("images", [])) >= 3, f"{len(doc.get('images', []))} images")
    morphs = [m.get("name") for m in doc.get("meshes", []) if any("targets" in p for p in m.get("primitives", []))]
    rep.add("GLB: bag carries the scooping morph target", bool(morphs), ", ".join(morphs) or "none")
    nodes = [n.get("name", "") for n in doc.get("nodes", [])]
    leaked = [n for n in nodes if any(n.startswith(p) for p in preview_names)]
    rep.add("GLB: no preview proxies", not leaked, "none" if not leaked else ", ".join(leaked))
    rep.add("GLB: markers included", sum(n.startswith("Marker_") for n in nodes) >= 9, f"{sum(n.startswith('Marker_') for n in nodes)} markers")
