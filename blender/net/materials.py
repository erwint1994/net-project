"""PBR texture maps drawn with numpy (tileable, seeded, physically sized) and the Blender materials that use them.

Every material gets BaseColor (RGBA; the netting's alpha is its hole mask), Normal (tangent space, OpenGL / Unity
convention), Roughness (for Blender and glTF) and MaskMap (R metallic, G occlusion = 1, A smoothness: what URP's
_MetallicGlossMap and HDRP's mask map read). UVs are in metres, so each material's tile_m is its texture's real size.

Materials:
  NT_Carbon   matte twill carbon (handle, arms)       NT_Fitting  black anodised aluminium (ferrules, inserts)
  NT_Plastic  glass-filled nylon (spreader, tip caps) NT_Grip     textured rubber grip
  NT_Rubber   smooth rubber butt cap                  NT_Cord     braided rim cord
  NT_Binding  woven seam / rim tape                   NT_Net      alpha-clipped knotless (or knotted) netting
"""
import hashlib
import json
import math
import os

import bpy
import numpy as np

LIBRARY_VERSION = 5
NET = "NT_Net"
OPAQUE = ["NT_Carbon", "NT_Fitting", "NT_Plastic", "NT_Grip", "NT_Rubber", "NT_Cord", "NT_Binding"]


def hex_srgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float32), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def net_tile(bag_cfg, res):
    """Holes per tile edge and the tile size (m), so a strand is at least ~10 pixels wide and the tile repeats."""
    pitch = (bag_cfg["hole_mm"] + bag_cfg["strand_mm"]) / 1000.0
    diag = math.sqrt(2) if bag_cfg["hole_orientation"] == "diamond" else 1.0
    n = int(res * bag_cfg["strand_mm"] / 1000.0 / (10 * pitch * diag))
    n = max(2, min(8, n))
    return n, n * pitch * diag


# ------------------------------------------------------------------ helpers

class Canvas:
    def __init__(self, res, tile_m, seed):
        self.res = res
        self.tile = tile_m
        self.rng = np.random.default_rng(seed)
        c = (np.arange(res, dtype=np.float32) + 0.5) / res * tile_m
        # Row index = v (Blender stores images bottom-up, so row 0 is v = 0), column index = u.
        self.u, self.v = np.meshgrid(c, c)
        self.px = tile_m / res

    def noise(self, cycles, aniso=(1.0, 1.0)):
        """Tileable smooth noise in [-1, 1]: white noise low-passed in the frequency domain. cycles = feature count per tile."""
        w = self.rng.standard_normal((self.res, self.res)).astype(np.float32)
        fy = np.fft.fftfreq(self.res)[:, None] * self.res
        fx = np.fft.fftfreq(self.res)[None, :] * self.res
        g = np.exp(-((fx * aniso[0]) ** 2 + (fy * aniso[1]) ** 2) / (2 * cycles ** 2))
        n = np.real(np.fft.ifft2(np.fft.fft2(w) * g))
        return n / (np.abs(n).max() + 1e-9)

    def normal_from_height(self, h, strength=1.0):
        """Tangent-space normal map (OpenGL: green = +v) from a height field in metres."""
        dhdu = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) / (2 * self.px)
        dhdv = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) / (2 * self.px)
        n = np.stack([-dhdu * strength, -dhdv * strength, np.ones_like(h)], axis=-1)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        return n * 0.5 + 0.5


def _tri(x):
    """Triangle wave, 0 at integers, 1 at half-integers."""
    return 1 - np.abs(2 * (x - np.floor(x)) - 1)


def _rgba(rgb, alpha=None):
    a = np.ones(rgb.shape[:2], np.float32) if alpha is None else alpha
    return np.concatenate([rgb, a[..., None]], axis=-1)


def _colour(base_srgb, shade):
    """base colour (sRGB) times a brightness field, in linear light, back to sRGB."""
    return linear_to_srgb(srgb_to_linear(base_srgb)[None, None, :] * shade[..., None])


# ------------------------------------------------------------------ recipes: (base rgba, height m, roughness, metal)

def recipe_carbon(cv, p):
    tow = cv.tile / 8
    x, y = cv.u / tow, cv.v / tow
    ix, iy = np.floor(x), np.floor(y)
    warp_on_top = ((ix + iy) % 4) < 2
    cross = np.where(warp_on_top, x - ix, y - iy)
    along = np.where(warp_on_top, y, x)
    prof = np.sqrt(np.clip(1 - (2 * cross - 1) ** 2, 0, 1))
    fibres = 1 + 0.05 * np.sin(2 * np.pi * 22 * cross)
    h = 0.00012 * prof * (0.85 + 0.15 * np.cos(np.pi * (along % 2 - 1)))
    shade = np.where(warp_on_top, 0.82, 1.18) * fibres * (0.85 + 0.15 * prof) * (1 + 0.04 * cv.noise(6))
    rough = np.clip(p["carbon_roughness"] + 0.05 * (1 - prof) + 0.03 * cv.noise(10), 0.05, 1)
    return _rgba(_colour(p["carbon"], shade)), h, rough, np.zeros_like(h), 2.0


def recipe_fitting(cv, p):
    brushed = cv.noise(60, aniso=(0.04, 1.0))
    h = 0.000004 * brushed
    shade = 1 + 0.08 * brushed + 0.05 * cv.noise(4)
    rough = np.clip(0.36 + 0.05 * brushed + 0.04 * cv.noise(5), 0.05, 1)
    return _rgba(_colour(p["fitting"], shade)), h, rough, np.ones_like(h), 1.0


def recipe_plastic(cv, p):
    stipple = cv.noise(90)
    h = 0.00001 * stipple
    shade = 1 + 0.05 * cv.noise(5) + 0.03 * stipple
    rough = np.clip(0.62 + 0.06 * stipple, 0.05, 1)
    return _rgba(_colour(p["plastic"], shade)), h, rough, np.zeros_like(h), 1.0


def recipe_grip(cv, p):
    if p["grip_pattern"] == "ribbed":
        k = cv.v / (cv.tile / 10)
        prof = _tri(k)
        h = 0.0005 * np.clip(prof * 1.6, 0, 1)
    else:
        # Knurled pyramids: tileable because the tile holds a whole number of diamonds along both diagonals.
        k = 12
        a = (cv.u + cv.v) / cv.tile * k
        b = (cv.u - cv.v) / cv.tile * k
        prof = np.minimum(_tri(a), _tri(b))
        h = 0.0004 * np.clip(prof * 1.8, 0, 1)
    wear = cv.noise(5)
    shade = (0.75 + 0.35 * np.clip(h / h.max(), 0, 1)) * (1 + 0.06 * wear)
    rough = np.clip(0.86 - 0.12 * np.clip(h / h.max(), 0, 1) + 0.04 * wear, 0.05, 1)
    return _rgba(_colour(p["grip"], shade)), h, rough, np.zeros_like(h), 1.5


def recipe_rubber(cv, p):
    n = cv.noise(40)
    h = 0.00001 * n
    shade = 1 + 0.05 * cv.noise(4)
    rough = np.clip(0.8 + 0.04 * n, 0.05, 1)
    return _rgba(_colour(p["grip"], shade)), h, rough, np.zeros_like(h), 1.0


def recipe_cord(cv, p):
    k = 8
    a = (cv.u / cv.tile + cv.v / cv.tile) * k
    b = (cv.u / cv.tile - cv.v / cv.tile) * k
    over = ((np.floor(a) + np.floor(b)) % 2) < 1
    prof = np.where(over, np.sin(np.pi * (a % 1)), np.sin(np.pi * (b % 1)))
    h = 0.0004 * np.clip(prof, 0, 1)
    shade = (0.7 + 0.45 * np.clip(prof, 0, 1)) * (1 + 0.05 * cv.noise(6))
    rough = np.clip(0.84 - 0.1 * prof, 0.05, 1)
    return _rgba(_colour(p["cord"], shade)), h, rough, np.zeros_like(h), 1.5


def recipe_binding(cv, p):
    k = 40
    w = np.sin(2 * np.pi * cv.u / cv.tile * k) * np.sin(2 * np.pi * cv.v / cv.tile * k)
    h = 0.00006 * w
    shade = (1 + 0.08 * w) * (1 + 0.05 * cv.noise(4))
    rough = np.clip(0.9 + 0.03 * w, 0.05, 1)
    return _rgba(_colour(p["binding"], shade)), h, rough, np.zeros_like(h), 1.0


def recipe_net(cv, p):
    """Netting: two families of round twine strands, alpha 1 on the twine and 0 in the holes."""
    pitch = (p["hole_mm"] + p["strand_mm"]) / 1000.0
    w = p["strand_mm"] / 1000.0
    if p["hole_orientation"] == "diamond":
        a = (cv.u + cv.v) / math.sqrt(2)
        b = (cv.u - cv.v) / math.sqrt(2)
    else:
        a, b = cv.u, cv.v
    fa = (a / pitch + 0.5) % 1 - 0.5
    fb = (b / pitch + 0.5) % 1 - 0.5
    da, db = np.abs(fa) * pitch, np.abs(fb) * pitch
    half = w / 2
    cov = lambda d, r: np.clip((r - d) / cv.px + 0.5, 0, 1)  # noqa: E731 - antialiased coverage of a band of half-width r
    knot_r = w * (1.0 if p["knot"] == "knotted" else 0.62)
    rk = np.sqrt(da ** 2 + db ** 2)
    alpha = np.maximum(np.maximum(cov(da, half), cov(db, half)), cov(rk, knot_r))
    # Twisted twine: slanted striations along each strand.
    sa = np.sin(2 * np.pi * (b / (w * 1.7) + fa * pitch / w * 0.9))
    sb = np.sin(2 * np.pi * (a / (w * 1.7) + fb * pitch / w * 0.9))
    ha = np.sqrt(np.clip(1 - (da / half) ** 2, 0, 1)) * half * (1 + 0.12 * sa)
    hb = np.sqrt(np.clip(1 - (db / half) ** 2, 0, 1)) * half * (1 + 0.12 * sb)
    # Over / under at each crossing, alternating like a real net.
    parity = (np.round(a / pitch) + np.round(b / pitch)) % 2
    ha = ha + np.where(parity == 0, 0.25 * half, 0.0) * (ha > 0)
    hb = hb + np.where(parity == 1, 0.25 * half, 0.0) * (hb > 0)
    hk = np.sqrt(np.clip(1 - (rk / knot_r) ** 2, 0, 1)) * knot_r * (1.1 if p["knot"] == "knotted" else 0.6)
    h = np.maximum(np.maximum(ha, hb), hk)
    on_a = ha >= hb
    stripe = np.where(on_a, sa, sb)
    crossing = np.clip(1 - rk / (pitch * 0.35), 0, 1)
    shade = (0.82 + 0.25 * np.clip(h / (half * 1.25), 0, 1)) * (1 + 0.07 * stripe) * (1 - 0.18 * crossing ** 2)
    shade *= 1 + 0.06 * cv.noise(3)
    rough = np.clip(p["net_roughness"] + 0.05 * (1 - np.clip(h / half, 0, 1)) + 0.03 * stripe, 0.05, 1)
    return _rgba(_colour(p["net"], shade), alpha.astype(np.float32)), h, rough, np.zeros_like(h), 1.0


def material_specs(p, res):
    """name -> (recipe, tile_m)."""
    _, net_tile_m = net_tile(p, res)
    return {
        "NT_Carbon": (recipe_carbon, 0.024),
        "NT_Fitting": (recipe_fitting, 0.06),
        "NT_Plastic": (recipe_plastic, 0.05),
        "NT_Grip": (recipe_grip, 0.03),
        "NT_Rubber": (recipe_rubber, 0.05),
        "NT_Cord": (recipe_cord, 0.02),
        "NT_Binding": (recipe_binding, 0.03),
        NET: (recipe_net, net_tile_m),
    }


def material_params(cfg):
    m, b = cfg["material"], cfg["bag"]
    return {
        "net": hex_srgb(m["net_hex"]).tolist(), "carbon": hex_srgb(m["carbon_hex"]).tolist(),
        "grip": hex_srgb(m["grip_hex"]).tolist(), "cord": hex_srgb(m["cord_hex"]).tolist(),
        "fitting": hex_srgb(m["fitting_hex"]).tolist(), "plastic": hex_srgb(m["fitting_hex"]).tolist(),
        "binding": hex_srgb(m["binding_hex"]).tolist(),
        "carbon_roughness": m["carbon_roughness"], "net_roughness": m["net_roughness"],
        "hole_mm": b["hole_mm"], "strand_mm": b["strand_mm"], "hole_orientation": b["hole_orientation"],
        "knot": b["knot"], "grip_pattern": cfg["handle"]["grip_pattern"],
    }


# ------------------------------------------------------------------ files

def _save_png(name, arr, path, colourspace):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=False)
    img.colorspace_settings.name = colourspace
    img.alpha_mode = "STRAIGHT"
    img.pixels.foreach_set(np.ascontiguousarray(arr, dtype=np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def mip_coverage(alpha, cutoff):
    """Share of texels that pass the alpha test at each mip level (box-filtered, no coverage preservation)."""
    out = []
    a = alpha.astype(np.float64)
    while a.shape[0] >= 1:
        out.append(round(float((a > cutoff).mean()), 4))
        if a.shape[0] == 1:
            break
        a = 0.25 * (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2])
    return out


def build_library(cfg, cache_root, log):
    """Draw every material's maps once per parameter set (cached). Returns ({name: info}, folder)."""
    p = material_params(cfg)
    res = cfg["quality"]["texture_resolution"]
    seed = cfg["seed"]
    key = hashlib.sha1(json.dumps([LIBRARY_VERSION, p, res, seed], sort_keys=True).encode()).hexdigest()[:12]
    folder = os.path.join(cache_root, key)
    info_path = os.path.join(folder, "library.json")
    if os.path.exists(info_path):
        log(f"textures: cached in {folder}")
        with open(info_path, encoding="utf-8") as f:
            return json.load(f), folder
    os.makedirs(folder, exist_ok=True)
    library = {}
    for i, (name, (recipe, tile)) in enumerate(material_specs(p, res).items()):
        cv = Canvas(res, tile, seed * 101 + i)
        rgba, height, rough, metal, strength = recipe(cv, p)
        normal = cv.normal_from_height(height, strength)
        mask = np.zeros((res, res, 4), np.float32)
        mask[..., 0] = metal
        mask[..., 1] = 1.0
        mask[..., 3] = 1.0 - rough
        files = {k: f"{name}_{s}.png" for k, s in (("base", "BaseColor"), ("normal", "Normal"),
                                                    ("roughness", "Roughness"), ("mask", "MaskMap"))}
        _save_png(name + "_BaseColor", rgba, os.path.join(folder, files["base"]), "sRGB")
        _save_png(name + "_Normal", _rgba(normal.astype(np.float32)), os.path.join(folder, files["normal"]), "Non-Color")
        rmap = np.repeat(rough[..., None], 3, axis=-1).astype(np.float32)
        _save_png(name + "_Roughness", _rgba(rmap), os.path.join(folder, files["roughness"]), "Non-Color")
        _save_png(name + "_MaskMap", mask, os.path.join(folder, files["mask"]), "Non-Color")
        entry = {"files": files, "tile_m": [tile, tile], "metallic": round(float(metal.mean()), 3),
                 "smoothness": round(float(1 - rough.mean()), 3), "smoothness_max": round(float(1 - rough.min()), 3)}
        if name == NET:
            n, _ = net_tile(p, res)
            cutoff = cfg["material"]["alpha_cutoff"]
            entry["net"] = {"holes_per_tile": n, "coverage": round(float((rgba[..., 3] > cutoff).mean()), 4),
                            "mip_coverage_plain": mip_coverage(rgba[..., 3], cutoff),
                            "strand_px": round(p["strand_mm"] / 1000 / cv.px, 1),
                            "pitch_px": round((p["hole_mm"] + p["strand_mm"]) / 1000 / cv.px, 1)}
        library[name] = entry
        log(f"textures: {name} ({res}px, tile {tile * 1000:.1f} mm)")
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(library, f, indent=2)
    return library, folder


# ------------------------------------------------------------------ Blender materials

def wet_values(cfg, wetness):
    """Base colour multiplier and smoothness multiplier for a wetness 0..1 (the same numbers go to Unity)."""
    m = cfg["material"]
    tint = 1 - (1 - m["wet_base_tint"]) * wetness
    return tint, 1 + m["wet_smoothness_gain"] * wetness


def preview_materials(cfg, library, folder, wetness=None, suffix="", clip=True):
    """Blender materials using the maps as Unity will. wetness None = the preset's.

    clip=True: hard alpha clip at the cutoff (exported to the GLB as alphaMode MASK).
    clip=False: for preview renders: the raw alpha goes to Eevee's dithered transparency, so netting thinner than a pixel
    keeps its average coverage, as Unity's coverage-preserving mips with alpha-to-coverage do. A plain clip on
    box-filtered mips makes distant netting vanish, which is not what the game shows."""
    w = cfg["material"]["wetness"] if wetness is None else wetness
    tint, smooth_mul = wet_values(cfg, w)
    cutoff = cfg["material"]["alpha_cutoff"]
    mats = {}
    for name, info in library.items():
        mat = bpy.data.materials.new(name + suffix)
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        tx, ty = info["tile_m"]
        mp.inputs["Scale"].default_value = (1.0 / tx, 1.0 / ty, 1.0)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])

        def image(kind, colourspace):
            node = nt.nodes.new("ShaderNodeTexImage")
            img = bpy.data.images.load(os.path.join(folder, info["files"][kind]), check_existing=True)
            img.colorspace_settings.name = colourspace
            node.image = img
            nt.links.new(mp.outputs[0], node.inputs["Vector"])
            return node

        base = image("base", "sRGB")
        if abs(tint - 1) > 1e-4:
            mul = nt.nodes.new("ShaderNodeMix")
            mul.data_type = "RGBA"
            mul.blend_type = "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            nt.links.new(base.outputs["Color"], mul.inputs[6])
            mul.inputs[7].default_value = (tint, tint, tint, 1.0)
            nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
        rough = image("roughness", "Non-Color")
        # The same cap as in Unity (export.SMOOTHNESS_CAP): wet never pushes a material past mirror smoothness.
        mul = min(smooth_mul, max(1.0, 0.92 / max(info["smoothness_max"], 1e-3)))
        if abs(mul - 1) > 1e-4:
            # roughness = 1 - smoothness * multiplier (as Unity's smoothness scale does)
            inv = nt.nodes.new("ShaderNodeMath")
            inv.operation = "MULTIPLY_ADD"
            nt.links.new(rough.outputs["Color"], inv.inputs[0])
            inv.inputs[1].default_value = mul
            inv.inputs[2].default_value = 1 - mul
            inv.use_clamp = True
            nt.links.new(inv.outputs[0], bsdf.inputs["Roughness"])
        else:
            nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(image("mask", "Non-Color").outputs["Color"], sep.inputs[0])
        nt.links.new(sep.outputs[0], bsdf.inputs["Metallic"])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(image("normal", "Non-Color").outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
        if name == NET:
            # Alpha clip: 1 where alpha > cutoff, else 0 (the glTF exporter reads this as alphaMode MASK).
            if clip:
                node = nt.nodes.new("ShaderNodeMath")
                node.operation = "GREATER_THAN"
                node.inputs[1].default_value = cutoff
                nt.links.new(base.outputs["Alpha"], node.inputs[0])
                nt.links.new(node.outputs[0], bsdf.inputs["Alpha"])
            else:
                nt.links.new(base.outputs["Alpha"], bsdf.inputs["Alpha"])
            mat.use_backface_culling = False
            for attr, value in (("surface_render_method", "DITHERED"), ("use_transparent_shadow", True),
                                ("blend_method", "CLIP"), ("alpha_threshold", cutoff)):
                try:
                    setattr(mat, attr, value)
                except (AttributeError, TypeError):
                    pass
        mats[name] = mat
    return mats
