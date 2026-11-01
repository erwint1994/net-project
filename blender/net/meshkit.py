"""Mesh building blocks: faces with per-corner UVs and material names, optional extra positions per vertex (one per
blendshape: scooping, lying), and tubes along polylines.

Metres, build frame (X right, Y forward along the handle, Z up). UVs are in metres; each material sets its own
tiling, so netting, carbon and the grip all keep their real-world texture size.
"""
import math

import bpy
from mathutils import Vector


class MeshBuilder:
    def __init__(self):
        self.verts = []
        self.alt = []
        self.faces = []
        self.uvs = []
        self.mats = []

    def vert(self, p, alts=()):
        """alts: the vertex's position in each blendshape, in order (missing ones = the basis position)."""
        self.verts.append((p[0], p[1], p[2]))
        self.alt.append(tuple(tuple(a) for a in alts))
        return len(self.verts) - 1

    def face(self, idx, uvs, mat):
        self.faces.append(tuple(idx))
        self.uvs.append([(u[0], u[1]) for u in uvs])
        self.mats.append(mat)

    def extend(self, other):
        offset = len(self.verts)
        self.verts.extend(other.verts)
        self.alt.extend(other.alt)
        self.faces.extend(tuple(i + offset for i in f) for f in other.faces)
        self.uvs.extend(other.uvs)
        self.mats.extend(other.mats)

    def alt_positions(self, k):
        return [a[k] if k < len(a) else v for a, v in zip(self.alt, self.verts)]

    def triangle_count(self):
        return sum(len(f) - 2 for f in self.faces)

    def to_object(self, name, materials, collection, origin=(0.0, 0.0, 0.0), smooth=True, shape_keys=(),
                  sharp_angle_deg=50.0):
        """A mesh object whose origin sits at `origin` (vertices are stored relative to it).

        shape_keys: blendshape names, in the order of the vertices' extra positions."""
        o = Vector(origin)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(Vector(v) - o) for v in self.verts], [], self.faces)
        slots = []
        for m in self.mats:
            if m not in slots:
                slots.append(m)
        for m in slots:
            mesh.materials.append(materials[m])
        index = {m: slots.index(m) for m in slots}
        mesh.polygons.foreach_set("material_index", [index[m] for m in self.mats])
        uv = mesh.uv_layers.new(name="UVMap")
        uv.data.foreach_set("uv", [c for face in self.uvs for u in face for c in u])
        mesh.polygons.foreach_set("use_smooth", [smooth] * len(self.faces))
        mesh.validate(clean_customdata=False)
        if smooth:
            mesh.set_sharp_from_angle(angle=math.radians(sharp_angle_deg))
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        obj.location = o
        collection.objects.link(obj)
        if shape_keys:
            obj.shape_key_add(name="Basis", from_mix=False)
            for k, key_name in enumerate(shape_keys):
                key = obj.shape_key_add(name=key_name, from_mix=False)
                key.data.foreach_set("co", [c for a in self.alt_positions(k) for c in (Vector(a) - o)])
                # New keys start at full weight in Blender 5; the neutral (deployed) pose is every key at 0.
                key.value = 0.0
            mesh.update()
        return obj


def _frame(t, ref):
    """Two unit vectors perpendicular to tangent t (stable: built from a reference direction)."""
    side = t.cross(ref)
    if side.length < 1e-6:
        side = t.cross(Vector((1, 0, 0)) if abs(t.x) < 0.9 else Vector((0, 0, 1)))
    side.normalize()
    up = side.cross(t).normalized()
    return side, up


def tube(mb, pts, radii, sides, mat, caps=(True, True), ref=Vector((0, 0, 1)), v0=0.0, cap_dome=0.0):
    """A tube along pts with a radius per point. UV: u round the circumference, v along the length (metres).

    caps: close the start / end with a flat (or domed, cap_dome = height in m) fan."""
    n = len(pts)
    pts = [Vector(p) for p in pts]
    if isinstance(radii, (int, float)):
        radii = [radii] * n
    tangents = []
    for i in range(n):
        a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        tangents.append((b - a).normalized())
    rings = []
    v = v0
    for i in range(n):
        if i:
            v += (pts[i] - pts[i - 1]).length
        side, up = _frame(tangents[i], ref)
        ring = []
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            off = (side * math.cos(a) + up * math.sin(a)) * radii[i]
            ring.append((mb.vert(pts[i] + off) if k < sides else None, (2 * math.pi * radii[i] * k / sides, v)))
        ring[sides] = (ring[0][0], ring[sides][1])
        rings.append(ring)
    for i in range(n - 1):
        for k in range(sides):
            a, b = rings[i][k], rings[i][k + 1]
            c, d = rings[i + 1][k + 1], rings[i + 1][k]
            mb.face((a[0], d[0], c[0], b[0]), (a[1], d[1], c[1], b[1]), mat)
    for end, idx in ((0, 0), (1, n - 1)):
        if not caps[end]:
            continue
        t = tangents[idx] * (-1 if end == 0 else 1)
        centre = pts[idx] + t * cap_dome
        c = mb.vert(centre)
        ring = rings[idx]
        side, up = _frame(tangents[idx], ref)
        for k in range(sides):
            a, b = ring[k], ring[k + 1]
            ka, kb = 2 * math.pi * k / sides, 2 * math.pi * (k + 1) / sides
            r = radii[idx]
            uva = (r * math.cos(ka), r * math.sin(ka))
            uvb = (r * math.cos(kb), r * math.sin(kb))
            if end == 0:
                mb.face((a[0], b[0], c), (uva, uvb, (0.0, 0.0)), mat)
            else:
                mb.face((b[0], a[0], c), (uvb, uva, (0.0, 0.0)), mat)
    return rings


def lathe(mb, axis_origin, axis_dir, profile, sides, mat, ref=Vector((0, 0, 1))):
    """Surface of revolution: profile is [(distance along the axis, radius), ...]; radius 0 closes to a point."""
    o, d = Vector(axis_origin), Vector(axis_dir).normalized()
    side, up = _frame(d, ref)
    rows = []
    v = 0.0
    for i, (s, r) in enumerate(profile):
        if i:
            ps, pr = profile[i - 1]
            v += math.hypot(s - ps, r - pr)
        c = o + d * s
        if r <= 1e-7:
            vid = mb.vert(c)
            rows.append([(vid, (2 * math.pi * 0.01 * k / sides, v)) for k in range(sides + 1)])
            continue
        row = []
        for k in range(sides + 1):
            a = 2 * math.pi * k / sides
            vid = mb.vert(c + (side * math.cos(a) + up * math.sin(a)) * r) if k < sides else row[0][0]
            row.append((vid, (2 * math.pi * r * k / sides, v)))
        rows.append(row)
    for i in range(len(rows) - 1):
        for k in range(sides):
            a, b, c, e = rows[i][k], rows[i][k + 1], rows[i + 1][k + 1], rows[i + 1][k]
            ids = [a[0], e[0], c[0], b[0]]
            uvs = [a[1], e[1], c[1], b[1]]
            # Drop the repeated vertex where a row collapses to a point.
            keep = [j for j in range(4) if ids[j] not in ids[:j]]
            if len(keep) >= 3:
                mb.face([ids[j] for j in keep], [uvs[j] for j in keep], mat)
    return rows
