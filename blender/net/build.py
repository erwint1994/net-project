"""Build the net's parts for one LOD from the shared geometry: handle section(s), head (spreader block, sockets,
ferrules, arms, tip caps, cord) and net bag (bag, seams, sleeves over the arms and cord, scooping blendshape).

Objects per LOD (k = 0, 1, 2), each with its origin at its assembly point:
  LOD{k}_Handle                      one-piece handle, origin at the butt cap (0, 0, 0)
  LOD{k}_HandleLower / _HandleUpper  two-piece handle; the upper section's origin is the joint
  LOD{k}_Head                        opaque head hardware, origin at the spreader pivot
  LOD{k}_NetBag                      alpha-clipped netting + seam tape, origin at the spreader pivot
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

from .meshkit import MeshBuilder, lathe, tube

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from studio.bagshape import BagShape  # noqa: E402
from studio.geometry import BUTT_CAP_WALL_M, SPREADER_BOSS_RADIUS_M, TIP_CAP_WALL_M, NetGeometry  # noqa: E402

SHAPE_KEY = "Scooping"
LYING_KEY = "Lying"
SHAPE_KEYS = (SHAPE_KEY, LYING_KEY)
CAP_LEN = 0.026
INSERT_LEN = 0.03
THREAD_LEN = 0.016
THREAD_R = 0.0048
BOSS_LEN = 0.034
FERRULE_LEN = 0.036


class Net:
    """Geometry plus both bag poses for one config."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.geo = NetGeometry(cfg)
        self.bag = BagShape(self.geo, cfg["bag"], cfg["seed"], "deployed")
        self.scoop = BagShape(self.geo, cfg["bag"], cfg["seed"], "scooping")
        self.lying = BagShape(self.geo, cfg["bag"], cfg["seed"], "lying")

    def part_names(self):
        return [s["name"] for s in self.geo.handle_sections()] + ["Head", "NetBag"]

    def origins(self):
        g = self.geo
        o = {"Head": g.pivot, "NetBag": g.pivot}
        for s in g.handle_sections():
            o[s["name"]] = (0.0, s["from_m"], 0.0)
        return o


def _rings(lod, lo, hi):
    return [lo, hi, hi][lod] if lod else lo


# ------------------------------------------------------------------ handle

def build_handle_section(net, section, lod, mb):
    g = net.geo
    sides = net.cfg["quality"]["lod_tube_sides"][lod]
    Y = Vector((0, 1, 0))
    y0, y1 = section["from_m"], section["to_m"]
    r = g.handle_radius
    top_section = abs(y1 - g.handle_len) < 1e-9
    if y0 == 0.0:
        r0 = r(0) + BUTT_CAP_WALL_M
        prof = [(0.0, 0.0), (0.0, r0 * 0.55), (0.003, r0 * 0.92), (0.008, r0), (CAP_LEN - 0.003, r0), (CAP_LEN, r(CAP_LEN) + 0.0004)]
        if lod == 2:
            prof = [(0.0, 0.0), (0.0, r0 * 0.7), (0.006, r0), (CAP_LEN, r0)]
        lathe(mb, (0, 0, 0), Y, prof, sides, "NT_Rubber")
        gs, ge = g.grip_start, g.grip_start + g.grip_len
        gs = max(gs, CAP_LEN - 0.002)
        gr = [r(gs) + 0.0006, r(gs + 0.01) + 0.0032, r(ge - 0.01) + 0.0032, r(ge) + 0.0006]
        tube(mb, [(0, gs, 0), (0, gs + 0.01, 0), (0, ge - 0.01, 0), (0, ge, 0)], gr, sides, "NT_Grip", caps=(False, False))
        carbon_from = CAP_LEN - 0.002
    else:
        # Spigot: slides into the lower section (hidden when assembled, visible when taken apart).
        rs = r(y0) - 0.0016
        tube(mb, [(0, y0 - section["spigot_m"], 0), (0, y0 + 0.004, 0)], rs, sides, "NT_Carbon", caps=(True, False))
        ring = r(y0) + 0.0012
        lathe(mb, (0, y0, 0), Y, [(0.0, rs), (0.0, ring - 0.0006), (0.002, ring), (0.018, ring), (0.022, r(y0 + 0.022) + 0.0002)],
              sides, "NT_Fitting")
        carbon_from = y0 + 0.02
    carbon_to = y1 - (INSERT_LEN - 0.002 if top_section else FERRULE_LEN - 0.002)
    ys = [carbon_from, carbon_to] if lod else [carbon_from, (carbon_from + carbon_to) / 2, carbon_to]
    tube(mb, [(0, y, 0) for y in ys], [r(y) for y in ys], sides, "NT_Carbon", caps=(False, False))
    if top_section:
        ri = r(y1) + 0.001
        lathe(mb, (0, y1 - INSERT_LEN, 0), Y,
              [(0.0, r(y1 - INSERT_LEN) + 0.0002), (0.003, ri), (INSERT_LEN - 0.002, ri), (INSERT_LEN, ri - 0.0015),
               (INSERT_LEN, THREAD_R), (INSERT_LEN + THREAD_LEN, THREAD_R), (INSERT_LEN + THREAD_LEN + 0.0015, 0.0)],
              max(4, sides), "NT_Fitting")
    else:
        # Ferrule collar at the top of the lower section, open where the upper section's spigot goes in.
        rf = r(y1) + 0.0018
        rs = r(y1) - 0.0016 + 0.0004
        lathe(mb, (0, y1 - FERRULE_LEN, 0), Y,
              [(0.0, r(y1 - FERRULE_LEN) + 0.0002), (0.003, rf), (FERRULE_LEN - 0.002, rf), (FERRULE_LEN, rf - 0.0008),
               (FERRULE_LEN, rs), (FERRULE_LEN - 0.05, rs)], sides, "NT_Fitting")


# ------------------------------------------------------------------ head

def _superellipse_block(mb, centre, half_w, half_l, half_h, sides, mat, power=3.0):
    """Rounded moulded block: superellipse plan, softened top and bottom edges."""
    levels = [(-1.0, 0.82), (-0.86, 0.95), (-0.55, 1.0), (0.55, 1.0), (0.86, 0.95), (1.0, 0.82)]
    rings = []
    for z, s in levels:
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides
            c, sn = math.cos(a), math.sin(a)
            x = half_w * s * math.copysign(abs(c) ** (2 / power), c)
            y = half_l * s * math.copysign(abs(sn) ** (2 / power), sn)
            ring.append(mb.vert((centre[0] + x, centre[1] + y, centre[2] + z * half_h)))
        rings.append(ring)
    per = 2 * (half_w + half_l) * 1.1
    for i in range(len(rings) - 1):
        for k in range(sides):
            k1 = (k + 1) % sides
            v0, v1 = levels[i][0] * half_h, levels[i + 1][0] * half_h
            u0, u1 = per * k / sides, per * (k + 1) / sides
            mb.face((rings[i][k], rings[i][k1], rings[i + 1][k1], rings[i + 1][k]), ((u0, v0), (u1, v0), (u1, v1), (u0, v1)), mat)
    for ring, z, flip in ((rings[0], -half_h, True), (rings[-1], half_h, False)):
        c = mb.vert((centre[0], centre[1], centre[2] + z))
        for k in range(sides):
            k1 = (k + 1) % sides
            a, b = mb.verts[ring[k]], mb.verts[ring[k1]]
            uv = [(a[0], a[1]), (b[0], b[1]), (centre[0], centre[1])]
            if flip:
                mb.face((ring[k1], ring[k], c), [uv[1], uv[0], uv[2]], mat)
            else:
                mb.face((ring[k], ring[k1], c), uv, mat)


def build_head(net, lod, mb):
    g = net.geo
    q = net.cfg["quality"]
    sides = q["lod_tube_sides"][lod]
    arm_sides = max(4, sides - 4 if lod == 0 else sides - 2)
    P = Vector(g.pivot)
    Y = Vector((0, 1, 0))
    # Rear boss: the threaded socket the handle screws into.
    rb = SPREADER_BOSS_RADIUS_M
    lathe(mb, (0, g.handle_len, 0), Y,
          [(0.0, THREAD_R + 0.0004), (0.0, rb - 0.0015), (0.0015, rb), (BOSS_LEN, rb)], max(6, sides), "NT_Plastic")
    # Block body round the pivot.
    _superellipse_block(mb, (0.0, P.y + 0.003, 0.0), 0.034, 0.026, 0.014, max(10, sides * 2), "NT_Plastic")
    rs = g.arm_r0 + 0.0042
    s_in = 0.022 / g.L
    for side in (1, -1):
        d = Vector(g.socket_direction(side))
        # Socket sleeve and its ferrule ring where the arm goes in.
        lathe(mb, P + d * 0.012, d, [(0.0, rs), (g.socket_len - 0.012 - 0.011, rs)], max(6, sides), "NT_Plastic")
        rf = rs + 0.0009
        lathe(mb, P + d * (g.socket_len - 0.012), d,
              [(0.0, rs - 0.0003), (0.0015, rf), (0.010, rf), (0.012, rf - 0.0012), (0.012, g.arm_r0 + 0.0004)],
              max(6, sides), "NT_Fitting")
        # Arm: tapered carbon along the bowed centre line, from inside the socket to inside the tip cap.
        count = [28, 10, 5][lod]
        s_end = 1 - 0.022 / g.L
        ss = [s_in + (s_end - s_in) * k / (count - 1) for k in range(count)]
        tube(mb, [g.arm_point(side, s) for s in ss], [g.arm_radius(s) for s in ss], arm_sides, "NT_Carbon", caps=(False, False))
        # Tip cap: plastic end with the cord running through it.
        corner = Vector(g.corner_right if side > 0 else g.corner_left)
        t = (corner - Vector(g.arm_point(side, 1 - 0.01 / g.L))).normalized()
        rc = g.arm_r1 + TIP_CAP_WALL_M
        prof = [(-0.032, g.arm_r1 + 0.0004), (-0.029, rc), (0.002, rc), (0.006, rc * 0.8), (0.008, 0.0)]
        if lod == 2:
            prof = [(-0.032, rc), (0.004, rc), (0.008, 0.0)]
        lathe(mb, corner, t, prof, max(6, sides), "NT_Plastic")
    # Cord between the tip caps.
    cl, cr = Vector(g.corner_left), Vector(g.corner_right)
    tube(mb, [cl, cr], g.cord_r, max(4, sides // 2 + 2), "NT_Cord", caps=(False, False))


# ------------------------------------------------------------------ net bag

def _orient(mb, start, end, outward):
    score = 0.0
    for k in range(start, end):
        pts = [Vector(mb.verts[i]) for i in mb.faces[k]]
        n = Vector((0, 0, 0))
        for a in range(len(pts)):
            n += pts[a].cross(pts[(a + 1) % len(pts)])
        c = sum(pts, Vector()) / len(pts)
        score += n.dot(outward(c))
    if score < 0:
        for k in range(start, end):
            mb.faces[k] = tuple(reversed(mb.faces[k]))
            mb.uvs[k] = list(reversed(mb.uvs[k]))


def build_bag(net, lod, mb):
    g, bag, scoop, lying = net.geo, net.bag, net.scoop, net.lying
    q, bc = net.cfg["quality"], net.cfg["bag"]
    n_rim, rows = q["lod_rim_segments"][lod], q["lod_bag_rows"][lod]
    us = bag.rim.sample_u(n_rim)
    grid = bag.grid(us, rows)
    grid_s = scoop.grid(us, rows)
    grid_l = lying.grid(us, rows)
    ids = [[mb.vert(grid[i][j], (grid_s[i][j], grid_l[i][j])) for j in range(n_rim)] for i in range(rows)]
    bottom = mb.vert(bag.bottom_point(), (scoop.bottom_point(), lying.bottom_point()))
    # UVs in metres from the deployed pose: u along each row, v down each column.
    U = []
    for i in range(rows):
        row = [Vector(p) for p in grid[i]]
        acc = [0.0]
        for j in range(n_rim):
            acc.append(acc[-1] + (row[(j + 1) % n_rim] - row[j]).length)
        U.append(acc)
    V = [[0.0] * n_rim]
    for i in range(1, rows):
        V.append([V[-1][j] + (Vector(grid[i][j]) - Vector(grid[i - 1][j])).length for j in range(n_rim)])
    start = len(mb.faces)
    for i in range(rows - 1):
        for j in range(n_rim):
            j1 = (j + 1) % n_rim
            mb.face((ids[i][j], ids[i][j1], ids[i + 1][j1], ids[i + 1][j]),
                    ((U[i][j], -V[i][j]), (U[i][j + 1], -V[i][j1]), (U[i + 1][j + 1], -V[i + 1][j1]), (U[i + 1][j], -V[i + 1][j])),
                    "NT_Net")
    last = rows - 1
    bp = Vector(bag.bottom_point())
    for j in range(n_rim):
        j1 = (j + 1) % n_rim
        vb = max(V[last][j], V[last][j1]) + (Vector(grid[last][j]) - bp).length
        mb.face((ids[last][j], ids[last][j1], bottom),
                ((U[last][j], -V[last][j]), (U[last][j + 1], -V[last][j1]), ((U[last][j] + U[last][j + 1]) / 2, -vb)), "NT_Net")
    cx, cy = bag.centre
    _orient(mb, start, len(mb.faces), lambda c: Vector((c.x - cx, c.y - cy, min(0.0, c.z + bag.depth * 0.8))))

    # Seam tape down the back, behind the spreader, where the bag's panel is sewn closed.
    seams = [] if not bc["seams"] else [[0.0], [0.0], []][lod]
    width, lift = 0.007, 0.0008
    steps = rows * 2
    for u in seams:
        start = len(mb.faces)
        prev = None
        v = 0.0
        for k in range(steps):
            t = k / steps * (rows - 1) / rows
            pair = []
            for shape in (bag, scoop, lying):
                p, n = Vector(shape.point(u, t)), Vector(shape.normal(u, t))
                tu = (Vector(shape.point(u + 1e-3, t)) - Vector(shape.point(u - 1e-3, t))).normalized()
                pair.append((p + n * lift - tu * width / 2, p + n * lift + tu * width / 2))
            a = mb.vert(pair[0][0], (pair[1][0], pair[2][0]))
            b = mb.vert(pair[0][1], (pair[1][1], pair[2][1]))
            if prev:
                v_prev = v
                v += (Vector(mb.verts[a]) - Vector(mb.verts[prev[0]])).length
                mb.face((prev[0], prev[1], b, a), ((0, -v_prev), (width, -v_prev), (width, -v), (0, -v)), "NT_Binding")
            prev = (a, b)
        _orient(mb, start, len(mb.faces), lambda c: Vector((c.x - cx, c.y - cy, min(0.0, c.z + bag.depth * 0.8))))

    # The netting's edge wrapped over the arms and the cord (static in both poses).
    if bc["arm_sleeve"] and lod < 2:
        sides = [10, 6][lod]
        count = [24, 10][lod]
        s0, s1 = g.arm_start_s(), 1 - 0.03 / g.L
        for side in (1, -1):
            ss = [s0 + (s1 - s0) * k / (count - 1) for k in range(count)]
            tube(mb, [g.arm_point(side, s) for s in ss], [g.arm_radius(s) + 0.0012 for s in ss], sides, "NT_Net",
                 caps=(False, False))
        cl, cr = Vector(g.corner_left), Vector(g.corner_right)
        d = (cr - cl).normalized()
        tube(mb, [cl + d * 0.034, cr - d * 0.034], g.cord_r + 0.0011, max(5, sides - 2), "NT_Net", caps=(False, False))


def unwrap_bag(obj, n_rim, rows):
    """Re-lay the bag body's UVs with Blender's minimum-stretch unwrap, cut down the back seam (under the seam tape),
    scaled so the median twine bar keeps its real length. A sack can't be flattened without distortion: rows that
    simply follow the rim shear and drift by up to 4x near the bottom, this keeps 90 % of the edges within -10/+35 %.
    The seam tape and the sleeves keep their own UVs."""
    bag_faces = n_rim * rows
    seam = {i * n_rim for i in range(rows)} | {n_rim * rows}
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.select = f.index < bag_faces
    for e in bm.edges:
        e.seam = all(v.index in seam for v in e.verts)
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.uv.unwrap(method="MINIMUM_STRETCH", margin=0.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    me = obj.data
    uv = me.uv_layers.active.data
    ratios = []
    for p in me.polygons[:bag_faces]:
        li = list(p.loop_indices)
        for k in range(len(li)):
            a, b = p.vertices[k], p.vertices[(k + 1) % len(li)]
            d = (me.vertices[a].co - me.vertices[b].co).length
            if d > 1e-5:
                ratios.append((uv[li[(k + 1) % len(li)]].uv - uv[li[k]].uv).length / d)
    ratios.sort()
    scale = 1.0 / ratios[len(ratios) // 2]
    for p in me.polygons[:bag_faces]:
        for li in p.loop_indices:
            uv[li].uv = uv[li].uv * scale
    for e in me.edges:
        e.use_seam = False


# ------------------------------------------------------------------ assembly

def build_lod(net, lod, mats, collection, root):
    objs = []
    origins = net.origins()
    for section in net.geo.handle_sections():
        mb = MeshBuilder()
        build_handle_section(net, section, lod, mb)
        objs.append(mb.to_object(f"LOD{lod}_{section['name']}", mats, collection, origins[section["name"]]))
    mb = MeshBuilder()
    build_head(net, lod, mb)
    objs.append(mb.to_object(f"LOD{lod}_Head", mats, collection, origins["Head"]))
    mb = MeshBuilder()
    build_bag(net, lod, mb)
    bag = mb.to_object(f"LOD{lod}_NetBag", mats, collection, origins["NetBag"], shape_keys=SHAPE_KEYS, sharp_angle_deg=80)
    unwrap_bag(bag, net.cfg["quality"]["lod_rim_segments"][lod], net.cfg["quality"]["lod_bag_rows"][lod])
    objs.append(bag)
    for o in objs:
        o.parent = root
    return objs


def add_markers(net, collection, root):
    markers = dict(net.geo.markers())
    markers["Marker_BagBottom"] = net.bag.bottom_point()
    markers["Marker_BagBottomScooping"] = net.scoop.bottom_point()
    out = []
    for name, p in markers.items():
        e = bpy.data.objects.new(name, None)
        e.empty_display_type = "PLAIN_AXES"
        e.empty_display_size = 0.05
        e.location = p
        collection.objects.link(e)
        e.parent = root
        out.append(e)
    return out


def build_all(cfg, mats, collection, lods=(0, 1, 2)):
    net = Net(cfg)
    root = bpy.data.objects.new(f"Net_{cfg['id']}", None)
    root.empty_display_size = 0.2
    collection.objects.link(root)
    built = {k: build_lod(net, k, mats, collection, root) for k in lods}
    markers = add_markers(net, collection, root)
    bpy.context.view_layer.update()
    return net, root, built, markers


def set_pose(objs, weight, key=SHAPE_KEY):
    """Blendshape weight 0..1 on every bag: Scooping (0 = deployed, empty) or Lying (flat on the ground)."""
    for o in objs:
        keys = o.data.shape_keys
        if keys and key in keys.key_blocks:
            keys.key_blocks[key].value = weight
