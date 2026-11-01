"""Landing net geometry in plain Python: no Blender, no numpy. Blender and the tests both use it.

Frame (the build frame, Blender): metres, X right, Y forward along the handle, Z up. The butt cap centre is the
origin, the handle runs along +Y, the spreader pivot sits on the handle axis and the mouth opens forward from it,
flat in the plane Z = 0 (neutral deployed pose), with the bag hanging towards -Z.
Unity frame (the export): X right, +Y up, +Z forward. to_unity() converts; the Unity import test checks it.
"""
import math

INCH_M = 0.0254
# Hardware sizes the shared maths needs too (blender/net/build.py builds them).
SPREADER_BOSS_RADIUS_M = 0.0155
BUTT_CAP_WALL_M = 0.0022
TIP_CAP_WALL_M = 0.0028


def inches_to_m(inches):
    """Exact: 42 in = 1.0668 m, 46 in = 1.1684 m."""
    return round(float(inches) * INCH_M, 6)


def to_unity(p):
    """Build frame (X right, Y forward, Z up) to Unity (X right, Y up, Z forward)."""
    return (p[0], p[2], p[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def polyline_length(pts):
    return sum(_len(_sub(pts[i + 1], pts[i])) for i in range(len(pts) - 1))


def polygon_area_xy(pts):
    """Shoelace area of a closed polygon in the XY plane (positive when counter-clockwise from above)."""
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]
        a += x0 * y1 - x1 * y0
    return 0.5 * a


def polygon_centroid_xy(pts):
    a = polygon_area_xy(pts)
    cx = cy = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]
        c = x0 * y1 - x1 * y0
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    return (cx / (6 * a), cy / (6 * a))


def point_in_polygon_xy(p, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class NetGeometry:
    """Every dimension of one net, derived from a resolved config. Lengths in metres, angles in radians."""

    # Arm bow shape: f(s) = s (1 - s) (2 - s), normalised to 1 at its peak (s = 1 - 1/sqrt(3)). Curves more near the
    # socket, like an arm bent by the cord's pull at its tip.
    _BOW_PEAK = (1 - 1 / math.sqrt(3)) * (1 / math.sqrt(3)) * (1 + 1 / math.sqrt(3))

    def __init__(self, cfg):
        h, hd, b = cfg["head"], cfg["handle"], cfg["bag"]
        self.arm_length_in = float(h["arm_length_in"])
        self.L = inches_to_m(self.arm_length_in)
        self.opening = math.radians(float(h["opening_angle_deg"]))
        self.half = self.opening / 2
        self.arm_bow = float(h["arm_bow_m"])
        self.arm_r0 = float(h["arm_base_diameter_mm"]) / 2000
        self.arm_r1 = float(h["arm_tip_diameter_mm"]) / 2000
        self.cord_r = float(h["cord_diameter_mm"]) / 2000
        self.pivot_offset = float(h["pivot_from_handle_top_m"])
        self.socket_len = float(h["socket_length_m"])

        self.handle_len = float(hd["length_m"])
        self.sections = int(hd["sections"])
        self.handle_r0 = float(hd["butt_diameter_mm"]) / 2000
        self.handle_r1 = float(hd["top_diameter_mm"]) / 2000
        joint = hd.get("joint_from_butt_m")
        self.joint = float(joint) if joint not in (None, "") else self.handle_len / 2
        self.spigot = float(hd["spigot_overlap_m"])
        self.grip_start = float(hd["grip_start_m"])
        self.grip_len = float(hd["grip_length_m"])
        self.front_grip = float(hd["front_grip_from_butt_m"])

        self.bag_depth = float(b["depth_m"])

        self.pivot = (0.0, self.handle_len + self.pivot_offset, 0.0)
        s, c = math.sin(self.half), math.cos(self.half)
        self.dir_right = (s, c, 0.0)
        self.dir_left = (-s, c, 0.0)
        # Outward normals in the mouth plane, away from the centre line.
        self.out_right = (c, -s, 0.0)
        self.out_left = (-c, -s, 0.0)
        self.corner_right = _add(self.pivot, _mul(self.dir_right, self.L))
        self.corner_left = _add(self.pivot, _mul(self.dir_left, self.L))

    # ------------------------------------------------------------ head

    @property
    def mouth_width(self):
        """Corner to corner (the cord's span): 2 L sin(opening / 2)."""
        return 2 * self.L * math.sin(self.half)

    @property
    def mouth_depth(self):
        """Spreader pivot to the cord line: L cos(opening / 2)."""
        return self.L * math.cos(self.half)

    @property
    def overall_length(self):
        return self.pivot[1] + self.mouth_depth

    def bow(self, s):
        return self.arm_bow * s * (1 - s) * (2 - s) / self._BOW_PEAK

    def arm_point(self, side, s):
        """Arm centre line, s in [0, 1] from the spreader pivot to the front corner. side = +1 right, -1 left."""
        d, n = (self.dir_right, self.out_right) if side > 0 else (self.dir_left, self.out_left)
        return _add(_add(self.pivot, _mul(d, self.L * s)), _mul(n, self.bow(s)))

    def arm_radius(self, s):
        return self.arm_r0 + (self.arm_r1 - self.arm_r0) * s

    def arm_polyline(self, side, count=64):
        return [self.arm_point(side, k / (count - 1)) for k in range(count)]

    def arm_arc_length(self):
        return polyline_length(self.arm_polyline(1, 400))

    def socket_direction(self, side):
        """Tangent of the arm where it leaves the spreader (the socket's axis)."""
        a, b = self.arm_point(side, 0.0), self.arm_point(side, 1e-4)
        d = _sub(b, a)
        return _mul(d, 1 / _len(d))

    def socket_angle(self):
        """Angle between the two sockets (slightly wider than the chord angle because the arms bow)."""
        r, l = self.socket_direction(1), self.socket_direction(-1)
        return math.acos(max(-1.0, min(1.0, r[0] * l[0] + r[1] * l[1])))

    def arm_start_s(self):
        """Where the arm leaves its socket, as a fraction of the arm."""
        return self.socket_len / self.L

    def head_triangle(self):
        """Spreader pivot, right corner, left corner (counter-clockwise from above)."""
        return [self.pivot, self.corner_right, self.corner_left]

    def rim_segments(self):
        """The bag's attachment line as three open polylines (back to front): right arm, cord, left arm.

        It starts where the right arm leaves its socket, runs out to the corner, across the cord and back down the left
        arm to its socket. The short back edge across the spreader closes the loop.
        """
        s0 = self.arm_start_s()
        right = [self.arm_point(1, s0 + (1 - s0) * k / 63) for k in range(64)]
        left = [self.arm_point(-1, 1 - (1 - s0) * k / 63) for k in range(64)]
        cord = [self.corner_right, self.corner_left]
        back = [left[-1], right[0]]
        return {"right_arm": right, "cord": cord, "left_arm": left, "back": back}

    def mouth_polygon(self, count=48):
        """The bag's opening in the mouth plane (Z = 0), counter-clockwise from above, `count` points."""
        segs = self.rim_segments()
        loop = segs["right_arm"] + segs["cord"][1:] + segs["left_arm"][1:]
        return resample_closed(loop, count)

    def mouth_centroid(self):
        poly = self.mouth_polygon(96)
        cx, cy = polygon_centroid_xy(poly)
        return (cx, cy, 0.0)

    def mouth_area(self):
        return polygon_area_xy(self.mouth_polygon(96))

    # ------------------------------------------------------------ handle

    def handle_radius(self, y):
        t = min(1.0, max(0.0, y / self.handle_len))
        return self.handle_r0 + (self.handle_r1 - self.handle_r0) * t

    def handle_sections(self):
        """Explicit handle sections, butt first. Each: name, from/to along the handle (m), spigot length below `from`."""
        if self.sections == 1:
            return [{"name": "Handle", "from_m": 0.0, "to_m": self.handle_len, "spigot_m": 0.0}]
        return [{"name": "HandleLower", "from_m": 0.0, "to_m": self.joint, "spigot_m": 0.0},
                {"name": "HandleUpper", "from_m": self.joint, "to_m": self.handle_len, "spigot_m": self.spigot}]

    def lying_ground_z(self):
        """Where the ground is (build frame Z) when the net lies flat on it: under its thickest part, the spreader's rear
        boss, the rubber butt cap or a tip cap, whichever reaches lowest."""
        return -max(SPREADER_BOSS_RADIUS_M, self.handle_r0 + BUTT_CAP_WALL_M, self.arm_r1 + TIP_CAP_WALL_M)

    def markers(self):
        """Named points in the build frame. All poses and LODs share them (the bag bottom has one per pose)."""
        m = {
            "Marker_ButtCap": (0.0, 0.0, 0.0),
            "Marker_GripRear": (0.0, self.grip_start + self.grip_len / 2, 0.0),
            "Marker_GripFront": (0.0, self.front_grip, 0.0),
            "Marker_HandleTop": (0.0, self.handle_len, 0.0),
            "Marker_Spreader": self.pivot,
            "Marker_MouthCentre": self.mouth_centroid(),
            "Marker_CornerLeft": self.corner_left,
            "Marker_CornerRight": self.corner_right,
        }
        if self.sections == 2:
            m["Marker_HandleJoint"] = (0.0, self.joint, 0.0)
        return m


def resample_closed(loop, count):
    """count points spaced evenly by arc length round a closed loop (first point kept)."""
    pts = list(loop) + [loop[0]]
    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + _len(_sub(pts[i + 1], pts[i])))
    total = cum[-1]
    out = []
    k = 0
    for c in range(count):
        target = total * c / count
        while k < len(cum) - 2 and cum[k + 1] < target:
            k += 1
        seg = cum[k + 1] - cum[k]
        t = 0.0 if seg < 1e-12 else (target - cum[k]) / seg
        out.append(_lerp(pts[k], pts[k + 1], t))
    return out


def resample_open(pts, count):
    """count points spaced evenly by arc length along an open polyline, both ends kept."""
    cum = [0.0]
    for i in range(len(pts) - 1):
        cum.append(cum[-1] + _len(_sub(pts[i + 1], pts[i])))
    total = cum[-1]
    out = []
    k = 0
    for c in range(count):
        target = total * c / (count - 1)
        while k < len(cum) - 2 and cum[k + 1] < target:
            k += 1
        seg = cum[k + 1] - cum[k]
        t = 0.0 if seg < 1e-12 else min(1.0, (target - cum[k]) / seg)
        out.append(_lerp(pts[k], pts[k + 1], t))
    return out
