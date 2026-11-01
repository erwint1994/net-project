"""The hanging net bag as a closed-form surface, in plain Python (the build frame of geometry.py).

point(u, t): u runs once round the rim (0..1, by arc length, starting at the back centre behind the spreader and
going out along the right arm first), t runs from the rim (0) to the bottom (1). The rim row is exactly the
attachment line under the arms and cord, so the bag is attached continuously. Going down, the walls leave the rim
vertically (as a bag hangs under its own weight), bulge a little, round off from the triangle towards a circle and
close in a rounded bottom at depth D below the mouth plane. Soft vertical folds come from a seeded sum of sines
(integer frequencies, so they wrap round the loop), fading to nothing at the rim and at the bottom.

This is a pose, not a simulation: no cloth, water drag or load. The scooping pose uses the same function with
other parameters (deeper, bottom drawn back towards the handle, fuller, fewer folds), so the two share topology
and the rim never moves between them.
"""
import math
import random

from .geometry import _len, _lerp, _sub, NetGeometry

SLEEVE_CLEARANCE_M = 0.0015

# What changes from the deployed (empty) pose to the scooping pose. Multipliers on the preset's bag values, plus the
# bottom's shift towards the handle as a fraction of the mouth depth.
SCOOP = {"depth_scale": 1.12, "bulge_add": 0.14, "fold_scale": 0.35, "round_end_scale": 0.7, "bottom_back_frac": 0.16}


def smoothstep(lo, hi, x):
    t = min(1.0, max(0.0, (x - lo) / (hi - lo)))
    return t * t * (3 - 2 * t)


class RimLoop:
    """The attachment line as one dense closed polyline with its four segments marked (back, right arm, cord, left arm)."""

    def __init__(self, geo: NetGeometry, per_segment=160):
        s0 = geo.arm_start_s()

        def arm(side, s):
            p = geo.arm_point(side, s)
            return (p[0], p[1], -(geo.arm_radius(s) + SLEEVE_CLEARANCE_M))

        r_start, l_start = arm(1, s0), arm(-1, s0)
        cr = (geo.corner_right[0], geo.corner_right[1], -(geo.cord_r + SLEEVE_CLEARANCE_M))
        cl = (geo.corner_left[0], geo.corner_left[1], -(geo.cord_r + SLEEVE_CLEARANCE_M))
        r_end, l_end = arm(1, 1.0), arm(-1, 1.0)
        back_mid = _lerp(l_start, r_start, 0.5)
        n = per_segment
        segs = [
            ("back_right", [_lerp(back_mid, r_start, k / n) for k in range(n + 1)]),
            ("right_arm", [arm(1, s0 + (1 - s0) * k / n) for k in range(n + 1)]),
            # A short drop from under the arm to under the cord at the corner (the arm is thicker than the cord).
            ("corner_right", [r_end, cr]),
            ("cord", [_lerp(cr, cl, k / n) for k in range(n + 1)]),
            ("corner_left", [cl, l_end]),
            ("left_arm", [arm(-1, 1 - (1 - s0) * k / n) for k in range(n + 1)]),
            ("back_left", [_lerp(l_start, back_mid, k / n) for k in range(n + 1)]),
        ]
        self.segments = []
        self.points = []
        for name, pts in segs:
            start = len(self.points)
            self.points.extend(pts[:-1])
            self.segments.append((name, start, len(self.points)))
        self.cum = [0.0]
        loop = self.points + [self.points[0]]
        for i in range(len(loop) - 1):
            self.cum.append(self.cum[-1] + _len(_sub(loop[i + 1], loop[i])))
        self.length = self.cum[-1]

    def u_of_index(self, i):
        return self.cum[i] / self.length

    def at(self, u):
        """Rim point at loop fraction u (wraps)."""
        u = u % 1.0
        target = u * self.length
        lo, hi = 0, len(self.cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= target:
                lo = mid
            else:
                hi = mid
        loop = self.points + [self.points[0]]
        seg = self.cum[lo + 1] - self.cum[lo]
        t = 0.0 if seg < 1e-12 else (target - self.cum[lo]) / seg
        return _lerp(loop[lo], loop[lo + 1], t)

    def sample_u(self, count, min_per_segment=1):
        """count u values round the loop, spread by length within each segment, every segment start included exactly
        (so the corners are vertices). Returns sorted u values in [0, 1)."""
        lengths = [self.cum[e] - self.cum[s] for _, s, e in self.segments]
        total = sum(lengths)
        alloc = [max(min_per_segment, round(count * l / total)) for l in lengths]
        # Fix rounding on the longest segment.
        alloc[lengths.index(max(lengths))] += count - sum(alloc)
        us = []
        for (_, s, e), n in zip(self.segments, alloc):
            a, b = self.cum[s] / self.length, self.cum[e] / self.length
            us.extend(a + (b - a) * k / n for k in range(n))
        return us

    def u_of_segment_mid(self, name):
        for n, s, e in self.segments:
            if n == name:
                return 0.5 * (self.cum[s] + self.cum[e]) / self.length
        raise KeyError(name)


class BagShape:
    def __init__(self, geo: NetGeometry, bag_cfg, seed, pose="deployed"):
        self.geo = geo
        self.rim = RimLoop(geo)
        self.pose = pose
        b = bag_cfg
        self.depth = float(b["depth_m"])
        self.bulge = float(b["bulge"])
        self.folds = float(b["fold_m"])
        self.round_end = float(b["round_end"])
        cx, cy = geo.mouth_centroid()[:2]
        self.centre = (cx, cy)
        bx, by = float(b["bottom_offset_m"][0]), float(b["bottom_offset_m"][1])
        if pose == "scooping":
            self.depth *= SCOOP["depth_scale"]
            self.bulge += SCOOP["bulge_add"]
            self.folds *= SCOOP["fold_scale"]
            self.round_end *= SCOOP["round_end_scale"]
            by -= SCOOP["bottom_back_frac"] * geo.mouth_depth
        elif pose != "deployed":
            raise ValueError(f"unknown pose '{pose}'")
        self.bottom = (cx + bx, cy + by)
        self.r_eq = math.sqrt(abs(geo.mouth_area()) / math.pi)
        rng = random.Random(int(seed))
        # Fold waves: integer frequencies so they wrap round the rim. Same seed for both poses (same folds, scaled).
        self.waves = [(rng.randint(5, 13), rng.uniform(0.4, 1.0), rng.uniform(0, 2 * math.pi)) for _ in range(5)]
        norm = sum(a for _, a, _ in self.waves)
        self.waves = [(f, a / norm, p) for f, a, p in self.waves]

    def _fold(self, u):
        return sum(a * math.sin(2 * math.pi * f * u + p) for f, a, p in self.waves)

    def point(self, u, t):
        r = self.rim.at(u)
        if t <= 0.0:
            return r
        cx, cy = self.centre
        if t >= 1.0:
            return (self.bottom[0], self.bottom[1], -self.depth)
        phi = t * math.pi / 2
        h, zf = math.cos(phi), math.sin(phi)
        dx, dy = r[0] - cx, r[1] - cy
        rnd = smoothstep(0.0, self.round_end, t)
        # Rounding off: towards a circle of the mouth's area, with the columns spread evenly round it by u (the rim's
        # own directions bunch up along the long arms, which leaves slivers in the small rings near the bottom).
        a_even = -math.pi / 2 + 2 * math.pi * u
        a_rim = a_even + (math.atan2(dy, dx) - a_even + math.pi) % (2 * math.pi) - math.pi
        a = a_rim + (a_even - a_rim) * rnd
        vx = dx * (1 - rnd) + self.r_eq * math.cos(a) * rnd
        vy = dy * (1 - rnd) + self.r_eq * math.sin(a) * rnd
        k = h * (1 + self.bulge * math.sin(math.pi * t))
        vx, vy = vx * k, vy * k
        radial = math.hypot(vx, vy) or 1e-9
        ux, uy = vx / radial, vy / radial
        fade = (t ** 0.6) * (1 - t) ** 0.7
        radial += self.folds * fade * self._fold(u)
        # The centre of each ring drifts from the mouth's centroid to the bottom point as the bag narrows.
        ox = cx + (self.bottom[0] - cx) * (1 - h)
        oy = cy + (self.bottom[1] - cy) * (1 - h)
        z = r[2] * (1 - zf) - self.depth * zf
        z += 0.5 * self.folds * t * (1 - t) * self._fold(u + 0.37)
        return (ox + ux * radial, oy + uy * radial, z)

    def bottom_point(self):
        return (self.bottom[0], self.bottom[1], -self.depth)

    def normal(self, u, t, eps=1e-3):
        """Outward surface normal (finite differences)."""
        a, b = self.point(u - eps, t), self.point(u + eps, t)
        c, d = self.point(u, max(0.0, t - eps)), self.point(u, min(1.0, t + eps))
        du = _sub(b, a)
        dt = _sub(d, c)
        n = (du[1] * dt[2] - du[2] * dt[1], du[2] * dt[0] - du[0] * dt[2], du[0] * dt[1] - du[1] * dt[0])
        ln = _len(n) or 1e-9
        n = (n[0] / ln, n[1] / ln, n[2] / ln)
        # Point away from the bag's axis.
        p = self.point(u, t)
        cx, cy = self.centre
        if n[0] * (p[0] - cx) + n[1] * (p[1] - cy) < 0:
            n = (-n[0], -n[1], -n[2])
        return n

    def grid(self, us, rows):
        """Points for rows 0..rows-1 at t = i / rows (row 0 is the rim); the bottom point closes it (t = 1)."""
        return [[self.point(u, i / rows) for u in us] for i in range(rows)]
