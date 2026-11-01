# Carp Landing Net Studio

Generates realistic triangular carp landing nets as real 3D models for the Carp Fishing Simulator (Unity 6, URP).
Pick a preset, change sizes, netting and colours, press **Generate**. You get a validated FBX with three LODs, a
scooping blendshape, explicit mouth and grip markers, PBR textures with see-through netting, preview renders and a
Unity importer that turns it into a prefab.

You never have to open Blender. It runs hidden in the background.

First release: **42-inch and 46-inch triangle nets, each with a one-piece or two-piece handle**. All four are built from
the same parts. They're original and unbranded. The proportions are proposed and labelled as such, not taken from
any manufacturer. Compact folding nets come later (see [docs/STATUS.md](docs/STATUS.md)).

**What "42 inch" means here:** each arm's length, from the spreader pivot to the front corner (42 in = 1.0668 m,
46 in = 1.1684 m). It is *not* the width of the mouth. With the default 90° opening a 42" net's mouth is 1.509 m wide
corner to corner and 0.754 m deep from the spreader to the cord.

---

## 1. Start the application

1. Double-click **`start_studio.bat`**.
2. The window opens. Blender is found in this order:
   1. the `NET_BLENDER` environment variable (path to `blender.exe`);
   2. the sibling Bivvy Studio's portable Blender, `..\bivvy-project\_vendor\blender-5.2.3-windows-x64\` (used read-only);
   3. this project's own `_vendor\` (run `setup_blender.ps1` once to download Blender 5.2.3, about 400 MB, checksum-verified);
   4. an installed Blender, or `blender` on PATH.

   `python -m studio.cli blender` shows which one is used.

Requirements: Windows, Python 3.10+ (`python` on PATH). No Python packages to install: the window uses tkinter.

## 2. Generate a net

In the window:

1. Pick a **Preset**: `net_42_one_piece`, `net_42_two_piece`, `net_46_one_piece` or `net_46_two_piece`.
2. **Quick preview** (about 15 s): builds LOD0 and renders one view in the chosen **Quick state**: deployed (empty),
   scooping (with a display-only fish), wet, or disassembled (display layout).
3. **Generate (full)** (about 25 s): draws the texture maps (cached after the first time), builds LOD0-2, runs about
   170-200 checks, exports FBX, GLB, textures and manifest, saves the .blend and renders 30-odd previews.
4. The status line shows **PASSED** or **FAILED** with triangle counts. The log shows every warning.

Without the window:

```
generate.bat net_42_one_piece                       full build
generate.bat net_42_one_piece --quick --state scooping
generate.bat all                                    all presets
python -m studio.cli check net_46_two_piece         validate a preset and print its dimensions (no Blender)
python -m studio.cli export-unity net_42_one_piece C:\repos\carp\CarpFishingSimulator
```

Everything lands in `output\<net id>\`:

| File | What |
| --- | --- |
| `export\<id>.fbx` | the model for Unity: LOD0-2 per part, the `Scooping` blendshape on each bag, markers |
| `export\<id>_LOD0.glb` | LOD0 with embedded textures, alpha-clipped double-sided netting, the scooping morph target |
| `export\Textures\` | BaseColor (netting alpha in A), Normal, MaskMap (metallic R, smoothness A), Roughness, per material |
| `export\net_manifest.json` | what the Unity importer reads: dimensions, axes, mouth polygon and plane, markers, sections, pose, materials, LODs |
| `previews\*.png` | three_quarter, side, top, front, head, spreader, bag_detail, under (against the sky), hand_scale, hands_whole, scooping, pose_transition, wet_dry, disassembled, lod_compare, distance_sheet (near/mid/far × sky/water/bank), contact_sheet |
| `<id>.blend` | the Blender file (it also holds the preview set and proxies; the exports never do) |
| `validation_report.json` | every check with ok / info / warn / fail |
| `build_log.txt` | Blender's full log |

## 3. What you can change

- **Head:** arm length in inches, opening angle (mouth width and depth follow from it), arm bow, arm and cord diameters.
- **Handle:** length (default 1.80 m), one or two sections, joint position, spigot overlap, butt and top diameters,
  rear grip length, front hand position, grip pattern (knurled diamond or ribbed).
- **Bag:** depth (default 0.90 m), bulge, soft folds, rounding, **hole size in mm** (clear opening, strand edge to
  strand edge; default 9 mm), twine thickness (default 1.5 mm), diamond or square holes, knotless or knotted, seam tape, netting over the arms.
- **Material:** six colours, **wetness** (darker, glossier; material parameters only), roughness.
- **Quality:** texture size 1024 or 2048, seed (folds and texture variation), GLB on/off, pickup capsule (off by default).

The window shows the derived dimensions live (arm in metres, mouth width × depth and area, socket angle, overall
length) and any problem in red. Numbers are checked before Blender starts: out-of-range values are clamped with a note.
Non-numbers, unsafe ids, a joint outside the middle of the handle, or arms that would touch at the spreader are errors.
**Save preset as...** writes only what differs from `config\defaults.json` to `presets\<name>.json`.

## 4. Export to Unity

1. Generate (full) first.
2. **Export to Unity...** and pick the Unity project. It suggests `..\carp\CarpFishingSimulator`.
3. A confirmation lists every file. **Nothing outside `Assets\NetStudio\` is touched:**
   - `Assets\NetStudio\Editor\`: the importer (editor-only assembly `Carp.NetStudio.Editor`),
   - `Assets\NetStudio\Runtime\`: `NetStudioNet` and `NetMouth` (assembly `Carp.NetStudio`),
   - `Assets\NetStudio\Nets\<id>\`: FBX, textures, manifest.
4. In Unity: **Tools → Net Studio → Rebuild All Net Prefabs**. You can also use **Tools → Net Studio → Import Export
   Folder...** on `output\<id>\export`, or run it in batch mode:
   `-executeMethod Carp.NetStudio.Editor.NetStudioImporter.ImportFromCommandLine -netExport <folder>`.

Exporting is always explicit. The studio never writes into the game on its own, and the prefab is not placed in any scene.

## 5. What you get in Unity

`Assets\NetStudio\Nets\<id>\<id>.prefab`:

- **Frame:** metres, +Y up. The origin is the butt cap centre, the handle runs along **+Z** to the spreader, and the
  mouth opens forward of it along +Z, flat and facing +Y in the neutral deployed pose. The bag hangs towards −Y.
  Details and every marker: [docs/COORDINATES.md](docs/COORDINATES.md).
- **LODGroup:** LOD0 → LOD1 at **2 m**, LOD1 → LOD2 at 19 m, culled at 280 m (60° FOV). `NetStudioNet` cancels
  `QualitySettings.lodBias` (2 on the game's PC High) so those distances hold.
- **Netting:** LOD0 uses an **alpha-clipped**, double-sided URP Lit material (opaque queue, so no sorting) with a mip
  chain the importer builds to keep the twine's coverage. LOD1/LOD2 use an alpha-blended haze whose opacity is the
  twine's coverage. Why, with measurements: [docs/NETTING_DISTANCE.md](docs/NETTING_DISTANCE.md). The LOD0 bag casts
  clipped shadows; the far bags cast none.
- **Poses:** the bag is a SkinnedMeshRenderer with the `Scooping` blendshape (0 = deployed empty, 100 = scooping).
  The rim never moves. It's a display pose, not cloth, water or load simulation.
- **`NetStudioNet` component:** markers by name, the mouth polygon (48 points) and plane, `scoop`, `wetness`,
  `disassembled` (display layout only), `IsOverMouth()` and `SegmentCrossesMouth()`. These are metadata helpers for
  later fish-over-mouth tests, not capture logic. No colliders are added; the optional pickup capsule is a trigger and off by default.
- Reimporting keeps the prefab, materials and textures (same paths, same GUIDs).

## 6. Checks

`validation_report.json`, from Blender:

- Mesh health per object, triangle ceilings (18k / 7k / 2k; actual about 10k / 2.6k / 0.8k), each LOD lighter than the last.
- Exact dimensions: pivot to corner = arm length, mouth width, handle length, butt at the origin.
- Head symmetry, joins (handle to spreader, arms in sockets, tip caps on the corners, two-piece sections, spigot hidden).
- Bag: attached all round the rim in both poses, below the mouth plane, depth as set, no row folding over, open mouth,
  no flare, bottom markers per LOD and pose.
- Hole scale: twine bars keep their real length in UV space.
- Markers, LOD sizes, an FBX round trip (objects, triangles, materials, UVs, blendshape, origins, markers, no
  proxies), and GLB contents (alphaMode MASK, double-sided, morph target, markers, no proxies).

`python -m unittest discover -s tests` runs the plain-Python tests (dimensions, geometry, sections, drape, config,
path safety, generated manifests) and a Blender smoke test (skip it with `NET_SKIP_BLENDER=1`).

`tools\test_unity_import.ps1 -Net <id> [-Pipeline urp|builtin] [-Shots <folder>]` imports into a throwaway Unity
project (`_unitytest\`, URP 17.4, MSAA off like the game) and checks the prefab: materials, clipping, culling, LODs,
blendshape, markers against the manifest, scale, reimport GUIDs, wetness, the display layout, a mock fish crossing the
mouth polygon, and renders that measure the netting's coverage from 0.8 m to 60 m, its underside and its shadow.
**Never run it on the game project.**

## 7. Adding nets

A new size is usually just a **preset**: change `head.arm_length_in`, the handle and the bag, then save. New geometry
goes in `blender\net\build.py`. The shared maths (head, sections, markers, bag drape) is plain Python in
`studio\geometry.py` and `studio\bagshape.py`, so tests can check it without Blender. Materials are in
`blender\net\materials.py`.

## 8. Troubleshooting

| Problem | Fix |
| --- | --- |
| "Blender not found" | Set `NET_BLENDER`, or run `setup_blender.ps1`. |
| `python` is not recognised | Install Python 3.12 from python.org and tick "Add python.exe to PATH". |
| FAILED | Read the `FAIL:` lines in the log or `validation_report.json`. |
| The Unity test can't resolve packages | Delete `_unitytest\` and run it again; it rebuilds the project. |

Origin of the brief and the reference files: [references/PROVENANCE.md](references/PROVENANCE.md).
