"""Presets: load, merge (defaults <- preset), validate, save. Plain Python, no Blender needed.

validate() runs before Blender is ever launched: finite numbers, sane ranges (clamped, with a note), head geometry,
handle joints and safe ids. Hard problems (a non-number, an unsafe id, an unknown option) raise ConfigError.
"""
import copy
import json
import math
import re
from pathlib import Path

from .geometry import NetGeometry, inches_to_m

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
PRESETS = ROOT / "presets"

ID_RE = re.compile(r"[a-z][a-z0-9_]{0,47}")
RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")

# Sane ranges. Values outside are clamped and reported, so a typo can't make a 6 m handle.
LIMITS = {
    ("head", "arm_length_in"): (30, 60),
    ("head", "opening_angle_deg"): (60, 120),
    ("head", "arm_bow_m"): (0.0, 0.06),
    ("head", "arm_base_diameter_mm"): (6, 20),
    ("head", "arm_tip_diameter_mm"): (4, 16),
    ("head", "cord_diameter_mm"): (2, 10),
    ("head", "pivot_from_handle_top_m"): (0.02, 0.1),
    ("head", "socket_length_m"): (0.03, 0.12),
    ("handle", "length_m"): (1.0, 2.5),
    ("handle", "spigot_overlap_m"): (0.06, 0.25),
    ("handle", "butt_diameter_mm"): (18, 36),
    ("handle", "top_diameter_mm"): (14, 32),
    ("handle", "grip_start_m"): (0.0, 0.2),
    ("handle", "grip_length_m"): (0.1, 0.6),
    ("handle", "front_grip_from_butt_m"): (0.5, 2.3),
    ("bag", "depth_m"): (0.4, 1.4),
    ("bag", "bulge"): (0.0, 0.3),
    ("bag", "fold_m"): (0.0, 0.04),
    ("bag", "round_end"): (0.2, 1.0),
    ("bag", "hole_mm"): (3, 25),
    ("bag", "strand_mm"): (0.5, 3.0),
    ("material", "wetness"): (0.0, 1.0),
    ("material", "carbon_roughness"): (0.2, 0.9),
    ("material", "net_roughness"): (0.4, 1.0),
    ("material", "alpha_cutoff"): (0.2, 0.8),
    ("material", "wet_base_tint"): (0.4, 1.0),
    ("material", "wet_smoothness_gain"): (0.0, 2.0),
}
CHOICES = {
    ("handle", "sections"): (1, 2),
    ("handle", "grip_pattern"): ("diamond", "ribbed"),
    ("bag", "hole_orientation"): ("diamond", "square"),
    ("bag", "knot"): ("knotless", "knotted"),
    ("quality", "texture_resolution"): (1024, 2048),
}
COLOURS = ["net_hex", "carbon_hex", "grip_hex", "cord_hex", "fitting_hex", "binding_hex"]


class ConfigError(ValueError):
    pass


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def defaults():
    return load_json(CONFIG / "defaults.json")


def list_presets():
    return sorted(p.stem for p in PRESETS.glob("*.json"))


def load_preset(name):
    if not is_safe_id(name):
        raise ConfigError(f"preset name '{name}' is not a safe id (lower case letters, digits, _)")
    path = PRESETS / f"{name}.json"
    if not path.exists():
        raise ConfigError(f"no preset '{name}' (have: {', '.join(list_presets())})")
    return load_json(path)


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    if not s or not s[0].isalpha():
        s = "net_" + s
    return s[:48].rstrip("_")


def is_safe_id(text):
    return isinstance(text, str) and bool(ID_RE.fullmatch(text)) and text not in RESERVED


def resolve(preset):
    """Full config for Blender: defaults, then the preset's own values. Returns (cfg, notes); raises ConfigError."""
    cfg = deep_merge(defaults(), preset)
    raw_id = cfg.get("id") or slug(cfg.get("name", "net"))
    if not is_safe_id(raw_id):
        raise ConfigError(f"id '{raw_id}' is not safe: use lower case letters, digits and _ (start with a letter, "
                          "at most 48), e.g. '{}'".format(slug(raw_id)))
    cfg["id"] = raw_id
    notes = validate(cfg)
    return cfg, notes


def _number(cfg, group, key):
    v = cfg[group][key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{group}.{key} must be a number, got {v!r}")
    if not math.isfinite(v):
        raise ConfigError(f"{group}.{key} must be finite, got {v!r}")
    return float(v)


def validate(cfg):
    """Check and clamp cfg in place. Returns notes about what was changed; raises ConfigError on hard problems."""
    notes = []
    for group in ("head", "handle", "bag", "material", "quality", "render", "export"):
        if not isinstance(cfg.get(group), dict):
            raise ConfigError(f"'{group}' section missing")
    for (group, key), (lo, hi) in LIMITS.items():
        v = _number(cfg, group, key)
        if not lo <= v <= hi:
            cfg[group][key] = min(hi, max(lo, v))
            notes.append(f"{group}.{key} {v} is outside {lo}-{hi}; using {cfg[group][key]}")
    for (group, key), allowed in CHOICES.items():
        if cfg[group][key] not in allowed:
            raise ConfigError(f"{group}.{key} must be one of {', '.join(map(str, allowed))}, got {cfg[group][key]!r}")
    for k in COLOURS:
        if not isinstance(cfg["material"][k], str) or not HEX_RE.fullmatch(cfg["material"][k]):
            raise ConfigError(f"material.{k} must be a colour like #2d3324, got {cfg['material'][k]!r}")
    try:
        seed = int(cfg["seed"])
    except (TypeError, ValueError):
        raise ConfigError(f"seed must be a whole number, got {cfg['seed']!r}") from None
    cfg["seed"] = seed
    off = cfg["bag"]["bottom_offset_m"]
    if not (isinstance(off, list) and len(off) == 2 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in off)):
        raise ConfigError(f"bag.bottom_offset_m must be [x, y] in metres, got {off!r}")
    for i in range(2):
        if abs(off[i]) > 0.25:
            notes.append(f"bag.bottom_offset_m[{i}] {off[i]} clamped to +-0.25 m")
            off[i] = math.copysign(0.25, off[i])
    for k in ("triangle_ceilings", "lod_rim_segments", "lod_bag_rows", "lod_tube_sides"):
        v = cfg["quality"][k]
        if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, int) and x > 0 for x in v)):
            raise ConfigError(f"quality.{k} must be three positive whole numbers (LOD0, LOD1, LOD2), got {v!r}")
        if not v[0] >= v[1] >= v[2]:
            raise ConfigError(f"quality.{k} must not grow from LOD0 to LOD2, got {v}")
    if min(cfg["quality"]["lod_tube_sides"]) < 3 or min(cfg["quality"]["lod_bag_rows"]) < 3:
        raise ConfigError("quality: at least 3 tube sides and 3 bag rows per LOD")

    h, hd, b = cfg["head"], cfg["handle"], cfg["bag"]
    if h["arm_tip_diameter_mm"] > h["arm_base_diameter_mm"]:
        h["arm_tip_diameter_mm"] = h["arm_base_diameter_mm"]
        notes.append("arm tip can't be thicker than its base; using the base diameter")
    if hd["top_diameter_mm"] > hd["butt_diameter_mm"]:
        hd["top_diameter_mm"] = hd["butt_diameter_mm"]
        notes.append("handle top can't be thicker than the butt; using the butt diameter")
    if b["strand_mm"] >= b["hole_mm"] * 0.6:
        b["strand_mm"] = round(b["hole_mm"] * 0.3, 2)
        notes.append(f"netting strand must be much thinner than the hole; using {b['strand_mm']} mm")

    # Handle joints.
    length = hd["length_m"]
    joint = hd.get("joint_from_butt_m")
    if hd["sections"] == 2:
        if joint in (None, ""):
            joint = round(length / 2, 4)
        elif isinstance(joint, bool) or not isinstance(joint, (int, float)) or not math.isfinite(joint):
            raise ConfigError(f"handle.joint_from_butt_m must be a number or null, got {joint!r}")
        if not 0.3 * length <= joint <= 0.7 * length:
            raise ConfigError(f"handle.joint_from_butt_m {joint} m must lie in the middle 40 % of the "
                              f"{length} m handle ({0.3 * length:.2f}-{0.7 * length:.2f} m)")
        hd["joint_from_butt_m"] = float(joint)
        shortest = min(joint, length - joint)
        if hd["spigot_overlap_m"] > shortest * 0.4:
            hd["spigot_overlap_m"] = round(shortest * 0.4, 3)
            notes.append(f"spigot can't reach that far into a {shortest:.2f} m section; using {hd['spigot_overlap_m']} m")
        if hd["grip_start_m"] + hd["grip_length_m"] > joint - 0.05:
            raise ConfigError("the rear grip runs over the handle joint; shorten handle.grip_length_m")
    else:
        hd["joint_from_butt_m"] = None
    grip_end = hd["grip_start_m"] + hd["grip_length_m"]
    if not grip_end + 0.1 <= hd["front_grip_from_butt_m"] <= length - 0.1:
        fixed = round(min(length - 0.1, max(grip_end + 0.1, hd["front_grip_from_butt_m"])), 3)
        notes.append(f"front grip {hd['front_grip_from_butt_m']} m must be between the rear grip and the top; using {fixed} m")
        hd["front_grip_from_butt_m"] = fixed

    # Head geometry: a real triangle with the arms clear of each other at the spreader.
    geo = NetGeometry(cfg)
    gap = 2 * geo.socket_len * math.sin(geo.half) - 2 * geo.arm_r0
    if gap < 0.01:
        raise ConfigError(f"the arms touch at the spreader ({gap * 1000:.0f} mm apart); widen the opening angle "
                          "or lengthen head.socket_length_m")
    if b["depth_m"] > geo.mouth_width * 0.95:
        notes.append(f"bag depth {b['depth_m']} m is deeper than the mouth is wide ({geo.mouth_width:.2f} m): "
                     "unusually deep for a carp net")
    return notes


def describe(cfg):
    """Source, proposed and derived dimensions, labelled, for the manifest and the window."""
    geo = NetGeometry(cfg)
    return {
        "source": {
            "arm_length_in": geo.arm_length_in,
            "arm_length_m": inches_to_m(geo.arm_length_in),
            "definition": "inches are each arm's length, spreader pivot to front corner (straight line), not mouth width",
        },
        "proposed": {
            "note": "artistic proportions for gameplay fit, not manufacturer data",
            "opening_angle_deg": cfg["head"]["opening_angle_deg"],
            "handle_length_m": geo.handle_len,
            "handle_sections": geo.sections,
            "handle_joint_from_butt_m": cfg["handle"]["joint_from_butt_m"],
            "bag_depth_m": geo.bag_depth,
            "arm_bow_m": geo.arm_bow,
        },
        "derived": {
            "mouth_width_m": round(geo.mouth_width, 4),
            "mouth_depth_m": round(geo.mouth_depth, 4),
            "mouth_area_m2": round(abs(geo.mouth_area()), 4),
            "arm_arc_length_m": round(geo.arm_arc_length(), 4),
            "socket_angle_deg": round(math.degrees(geo.socket_angle()), 2),
            "overall_length_m": round(geo.overall_length, 4),
            "spreader_pivot_from_butt_m": round(geo.pivot[1], 4),
        },
    }


def save_preset(name, preset):
    """Save only what differs from the defaults, so presets stay short. Returns the path."""
    name = slug(name)
    if not is_safe_id(name):
        raise ConfigError(f"can't save a preset called '{name}'")
    diff = _diff(defaults(), preset)
    diff["id"] = name
    diff["name"] = preset.get("name", name)
    path = PRESETS / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(diff, f, indent=2)
        f.write("\n")
    return path


def _diff(base, cur):
    out = {}
    for k, v in cur.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            sub = _diff(base[k], v)
            if sub:
                out[k] = sub
        elif base.get(k) != v:
            out[k] = v
    return out
