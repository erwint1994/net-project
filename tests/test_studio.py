"""Plain-Python tests (no Blender): dimensions, head geometry, sections, bag drape, config, manifest and path safety.

  python -m unittest discover -s tests -v
"""
import copy
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from studio import config, unity_export
from studio.bagshape import BagShape
from studio.geometry import NetGeometry, inches_to_m, point_in_polygon_xy, polygon_area_xy, to_unity
from studio.paths import inside, is_safe_relative, manifest_problems

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"


def resolved(name, **over):
    p = config.load_preset(name)
    p = config.deep_merge(p, over)
    return config.resolve(p)[0]


class Dimensions(unittest.TestCase):
    def test_inches_convert_exactly(self):
        self.assertEqual(inches_to_m(42), 1.0668)
        self.assertEqual(inches_to_m(46), 1.1684)

    def test_arm_is_pivot_to_corner_not_mouth_width(self):
        for name, inch in (("net_42_one_piece", 42), ("net_46_two_piece", 46)):
            g = NetGeometry(resolved(name))
            for c in (g.corner_left, g.corner_right):
                self.assertAlmostEqual(math.dist(c, g.pivot), inch * 0.0254, places=6)
            self.assertAlmostEqual(g.mouth_width, 2 * inch * 0.0254 * math.sin(math.radians(45)), places=6)
            self.assertAlmostEqual(g.mouth_depth, inch * 0.0254 * math.cos(math.radians(45)), places=6)
            self.assertNotAlmostEqual(g.mouth_width, inch * 0.0254, places=2)

    def test_opening_angle_drives_mouth(self):
        narrow = NetGeometry(resolved("net_42_one_piece", head={"opening_angle_deg": 80}))
        wide = NetGeometry(resolved("net_42_one_piece", head={"opening_angle_deg": 100}))
        self.assertLess(narrow.mouth_width, wide.mouth_width)
        self.assertGreater(narrow.mouth_depth, wide.mouth_depth)

    def test_head_is_symmetric_and_bows_outwards(self):
        g = NetGeometry(resolved("net_42_one_piece"))
        for s in (0.1, 0.4, 0.8):
            r, l = g.arm_point(1, s), g.arm_point(-1, s)
            self.assertAlmostEqual(r[0], -l[0], places=9)
            self.assertAlmostEqual(r[1], l[1], places=9)
        mid = g.arm_point(1, 0.42)
        chord = tuple(g.pivot[i] + (g.corner_right[i] - g.pivot[i]) * 0.42 for i in range(3))
        self.assertGreater(mid[0] - chord[0], 0)  # bowed away from the centre line
        self.assertGreater(math.degrees(g.socket_angle()), 90)

    def test_describe_labels_source_proposed_and_derived(self):
        d = config.describe(resolved("net_46_one_piece"))
        self.assertEqual(d["source"]["arm_length_m"], 1.1684)
        self.assertIn("not mouth width", d["source"]["definition"])
        self.assertIn("not manufacturer data", d["proposed"]["note"])
        self.assertAlmostEqual(d["derived"]["mouth_width_m"], 1.6524, places=3)

    def test_unity_axes(self):
        self.assertEqual(to_unity((1.0, 2.0, 3.0)), (1.0, 3.0, 2.0))


class Sections(unittest.TestCase):
    def test_one_piece(self):
        s = NetGeometry(resolved("net_42_one_piece")).handle_sections()
        self.assertEqual([x["name"] for x in s], ["Handle"])
        self.assertEqual((s[0]["from_m"], s[0]["to_m"]), (0.0, 1.8))

    def test_two_piece_meets_at_the_joint(self):
        g = NetGeometry(resolved("net_42_two_piece"))
        lo, up = g.handle_sections()
        self.assertEqual(lo["to_m"], up["from_m"])
        self.assertAlmostEqual(lo["to_m"], 0.9)
        self.assertEqual(up["to_m"], 1.8)
        self.assertGreater(up["spigot_m"], 0)
        self.assertIn("Marker_HandleJoint", g.markers())

    def test_joint_outside_middle_is_rejected(self):
        with self.assertRaises(config.ConfigError):
            resolved("net_42_two_piece", handle={"joint_from_butt_m": 0.3})

    def test_grip_over_joint_is_rejected(self):
        with self.assertRaises(config.ConfigError):
            resolved("net_42_two_piece", handle={"grip_length_m": 0.6, "joint_from_butt_m": 0.6})


class Bag(unittest.TestCase):
    def setUp(self):
        self.cfg = resolved("net_42_one_piece")
        self.g = NetGeometry(self.cfg)
        self.bag = BagShape(self.g, self.cfg["bag"], self.cfg["seed"])
        self.scoop = BagShape(self.g, self.cfg["bag"], self.cfg["seed"], "scooping")

    def test_rim_row_is_the_rim_in_both_poses(self):
        for u in (0.0, 0.13, 0.5, 0.77):
            self.assertEqual(self.bag.point(u, 0.0), self.scoop.point(u, 0.0))
            self.assertLess(self.bag.point(u, 0.0)[2], 0)
            self.assertGreater(self.bag.point(u, 0.0)[2], -0.012)

    def test_corners_are_rim_vertices(self):
        us = self.bag.rim.sample_u(128)
        pts = [self.bag.point(u, 0) for u in us]
        for c in (self.g.corner_left, self.g.corner_right):
            self.assertLess(min(math.dist(p[:2], c[:2]) for p in pts), 1e-6)

    def test_depth_and_descent(self):
        us = self.bag.rim.sample_u(96)
        grid = self.bag.grid(us, 24)
        low = min(p[2] for row in grid for p in row)
        self.assertLess(abs(-low - self.cfg["bag"]["depth_m"]), 0.03)
        for j in range(len(us)):
            col = [grid[i][j][2] for i in range(24)]
            self.assertTrue(all(a > b for a, b in zip(col, col[1:])))
        self.assertEqual(self.bag.bottom_point()[2], -self.cfg["bag"]["depth_m"])

    def test_rings_stay_open_and_scoop_is_deeper(self):
        us = self.bag.rim.sample_u(96)
        for shape in (self.bag, self.scoop):
            for row in shape.grid(us, 24)[1:]:
                self.assertGreater(polygon_area_xy(row), 0)
        self.assertGreater(self.scoop.depth, self.bag.depth * 1.05)
        self.assertLess(self.scoop.bottom[1], self.bag.bottom[1])  # drawn back towards the handle

    def test_seeded(self):
        other = BagShape(self.g, self.cfg["bag"], self.cfg["seed"])
        self.assertEqual(self.bag.point(0.3, 0.5), other.point(0.3, 0.5))
        changed = BagShape(self.g, self.cfg["bag"], self.cfg["seed"] + 1)
        self.assertNotEqual(self.bag.point(0.3, 0.5), changed.point(0.3, 0.5))

    def test_mouth_polygon(self):
        poly = self.g.mouth_polygon(48)
        self.assertEqual(len(poly), 48)
        self.assertGreater(polygon_area_xy(poly), 0)  # counter-clockwise from above
        self.assertTrue(point_in_polygon_xy(self.g.mouth_centroid(), poly))
        self.assertFalse(point_in_polygon_xy((0.0, 0.5, 0.0), poly))


class Config(unittest.TestCase):
    def test_presets_resolve_cleanly(self):
        names = config.list_presets()
        for n in ("net_42_one_piece", "net_42_two_piece", "net_46_one_piece", "net_46_two_piece"):
            self.assertIn(n, names)
        for n in names:
            cfg, notes = config.resolve(config.load_preset(n))
            self.assertEqual(notes, [], n)

    def test_out_of_range_is_clamped_with_a_note(self):
        cfg, notes = config.resolve(config.deep_merge(config.load_preset("net_42_one_piece"), {"handle": {"length_m": 9}}))
        self.assertEqual(cfg["handle"]["length_m"], 2.5)
        self.assertTrue(any("length_m" in n for n in notes))

    def test_non_finite_and_wrong_types_are_errors(self):
        for bad in ({"head": {"arm_length_in": float("nan")}}, {"head": {"arm_length_in": float("inf")}},
                    {"bag": {"depth_m": "deep"}}, {"bag": {"knot": "granny"}}, {"material": {"net_hex": "green"}},
                    {"handle": {"sections": 3}}, {"seed": "x"}, {"quality": {"lod_bag_rows": [3, 6, 12]}}):
            with self.assertRaises(config.ConfigError, msg=str(bad)):
                config.resolve(config.deep_merge(config.load_preset("net_42_one_piece"), bad))

    def test_arms_touching_at_the_spreader_is_an_error(self):
        with self.assertRaises(config.ConfigError):
            resolved("net_42_one_piece", head={"opening_angle_deg": 60, "socket_length_m": 0.03, "arm_base_diameter_mm": 20})

    def test_safe_ids(self):
        for ok in ("net_42_one_piece", "a", "x1_y2"):
            self.assertTrue(config.is_safe_id(ok))
        for bad in ("../evil", "Net", "1net", "net-42", "con", "a" * 49, "", "net/x", "net 42", None):
            self.assertFalse(config.is_safe_id(bad), bad)
        with self.assertRaises(config.ConfigError):
            config.resolve({"id": "../../x"})
        with self.assertRaises(config.ConfigError):
            config.load_preset("../defaults")

    def test_save_preset_round_trip(self):
        cfg = resolved("net_46_two_piece", bag={"hole_mm": 9.0}, material={"net_hex": "#334422"})
        with tempfile.TemporaryDirectory() as tmp:
            old = config.PRESETS
            config.PRESETS = Path(tmp)
            try:
                path = config.save_preset("My Test Net!", copy.deepcopy(cfg))
                self.assertEqual(path.name, "my_test_net.json")
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("render", saved)  # only differences are stored
                again, _ = config.resolve(saved)
                self.assertEqual(again["bag"]["hole_mm"], 9.0)
                self.assertEqual(again["head"]["arm_length_in"], 46)
                self.assertEqual(again["handle"]["sections"], 2)
            finally:
                config.PRESETS = old


class Paths(unittest.TestCase):
    def test_safe_relative(self):
        for ok in ("net.fbx", "Textures/NT_Net_BaseColor.png"):
            self.assertTrue(is_safe_relative(ok))
        for bad in ("../x.fbx", "C:/x.fbx", "C:x.fbx", "/abs.fbx", "\\\\server\\x", "Textures/../../x", "", None, "a\x00b"):
            self.assertFalse(is_safe_relative(bad), bad)

    def test_inside(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(inside(Path(tmp) / "a" / "b", tmp))
            self.assertFalse(inside(Path(tmp) / ".." / "x", tmp))

    def test_manifest_problems_flags_unsafe_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "n.fbx").write_text("x")
            m = {"files": {"fbx": "n.fbx", "glb": None, "textures": ["../steal.png", "Textures/missing.png"]}}
            probs = manifest_problems(m, tmp)
            self.assertTrue(any("unsafe" in p for p in probs))
            self.assertTrue(any("missing" in p for p in probs))

    def test_unity_plan_stays_in_assets_netstudio(self):
        export = OUTPUT / "net_42_one_piece" / "export"
        if not (export / "net_manifest.json").exists():
            self.skipTest("generate net_42_one_piece first")
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(Path(tmp) / "Assets")
            os.makedirs(Path(tmp) / "ProjectSettings")
            dest, files = unity_export.plan(export, tmp, "net_42_one_piece")
            self.assertTrue(all(inside(d, dest) for _, d in files))
            self.assertTrue(any(d.parent.name == "Editor" for _, d in files))
            self.assertTrue(any(d.parent.name == "Runtime" for _, d in files))
            self.assertFalse(any(s.suffix == ".glb" for s, _ in files))
            with self.assertRaises(ValueError):
                unity_export.plan(export, tmp, "../evil")


class GeneratedOutput(unittest.TestCase):
    """Checks on generated files, skipped until the presets have been generated."""

    def test_manifests(self):
        found = 0
        for name in config.list_presets():
            export = OUTPUT / name / "export"
            mpath = export / "net_manifest.json"
            if not mpath.exists():
                continue
            found += 1
            m = json.loads(mpath.read_text(encoding="utf-8"))
            self.assertEqual(m["schema"], "carp-net-studio/1")
            self.assertEqual(m["id"], name)
            self.assertEqual(manifest_problems(m, export), [], name)
            self.assertEqual(m["units"], "metres")
            mk = m["markers"]
            self.assertEqual(mk["Marker_ButtCap"], [0.0, 0.0, 0.0])
            self.assertGreater(mk["Marker_Spreader"][2], 1.5)  # handle runs along +Z
            self.assertLess(mk["Marker_CornerLeft"][0], 0)
            self.assertGreater(mk["Marker_CornerRight"][0], 0)
            self.assertLess(mk["Marker_BagBottom"][1], -0.5)  # bag hangs towards -Y
            self.assertEqual(len(m["head"]["mouth_polygon"]), 48)
            self.assertEqual(m["head"]["mouth_plane"]["normal"], [0.0, 1.0, 0.0])
            for lod, ceiling in zip(m["lods"], m["triangle_ceilings"]):
                self.assertLessEqual(lod["triangles"], ceiling)
            self.assertEqual(m["pose"]["mechanism"], "blendshape")
            self.assertEqual(m["materials"]["NT_Net"]["alpha"]["mode"], "clip")
            self.assertFalse(m["pickup_proxy"]["enabled"])
            report = json.loads((OUTPUT / name / "validation_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["passed"], name)
            for f in ("three_quarter", "side", "top", "spreader", "bag_detail", "wet_dry", "scooping", "hand_scale",
                      "pose_transition", "distance_sheet", "lod_compare", "contact_sheet"):
                self.assertTrue((OUTPUT / name / "previews" / f"{f}.png").exists(), f"{name}: {f}")
        if not found:
            self.skipTest("no generated nets yet")


if __name__ == "__main__":
    unittest.main()
