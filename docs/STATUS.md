# Status

Last updated 2026-11-01. Everything below was run on this machine (Windows 11, Python 3.12.10, the sibling bivvy's
portable Blender 5.2.3, Unity 6000.4.10f1 with URP 17.4.0, RTX 4060).

## Works today

| Area | State |
| --- | --- |
| Presets | `net_42_one_piece`, `net_42_two_piece`, `net_46_one_piece`, `net_46_two_piece`, all from shared parts; `net_60_sturgeon_knotless` (2026-11-10, carp F50 ST9: 60" arms on 14/10 mm, 2 m two-piece handle, 1.3 m deep bag of 6 mm knotless mesh; `studio.cli check` passes, not generated yet, not in the game) |
| Geometry | tapered twill-carbon arms (bowed, in sockets with anodised ferrules), moulded spreader block with threaded rear boss, plastic tip caps, braided rim cord, carbon handle with a knurled rubber grip, rubber butt cap and a threaded insert; two-piece: joint ferrule collar, hidden spigot, upper-section ring |
| Bag | hanging, rounded, soft folds, attached all round the rim, netting wrapped over the arms and cord, back seam tape; UVs unwrapped for real twine length (median 1.000, 90 % of edges within 0.92-1.20) |
| Netting | 9 mm knotless diamond holes, 1.5 mm twine (configurable; square holes and knots optional), alpha-clipped and double-sided in Blender, GLB and Unity |
| Poses | deployed (empty) and scooping as a blendshape on every LOD, with the preview transition; display-only fish and hand proxies, never exported |
| States | wet / dry (material parameters), disassembled display layout (sections side by side, head off) |
| LODs | about 9.9k / 2.5k / 0.8k triangles (one-piece) and 10.3k / 2.7k / 0.9k (two-piece), against ceilings of 18k / 7k / 2k |
| Exports | FBX (all LODs, blendshape, markers), GLB (LOD0, embedded textures, morph target), 1K PBR maps (2K optional), .blend, manifest, validation report, previews and contact sheet |
| Studio | tkinter window (presets, save-as, every parameter, live dimensions and validation, quick states, full build, progress and log, preview tabs, explicit Unity export with a confirmation listing); CLI and `.bat` launchers |
| Unity | importer `Carp.NetStudio.Editor`, runtime `Carp.NetStudio` (`NetStudioNet`, `NetMouth`); prefab under `Assets/NetStudio/Nets/<id>/` |

## Results (2026-11-01)

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | 28 tests OK (includes the Blender smoke test of quick deployed and scooping builds) |
| Blender validation, 42" one-piece / 46" one-piece | PASSED, 168 ok + 3 info, 0 warn, 0 fail |
| Blender validation, 42" two-piece / 46" two-piece | PASSED, 202 ok + 3 info, 0 warn, 0 fail |
| Unity (URP, MSAA off), 42" / 46" one-piece | ALL PASSED, 64 checks each |
| Unity (URP, MSAA off), 42" / 46" two-piece | ALL PASSED, 65 checks each |
| Unity Built-in, 42" one-piece | ALL PASSED, 47 checks |
| Full generate time | 21-25 s per net (textures cached) |

Dimensions as built: 42" mouth 1.509 × 0.754 m, 46" mouth 1.652 × 0.826 m, overall 2.599 / 2.671 m, bag 0.90 / 0.95 m
deep (1.008 / 1.064 m scooping). See [COORDINATES.md](COORDINATES.md).

The Unity test checks the prefab path and its root, that a reimport keeps GUIDs, the 3-LOD group, URP Lit materials
with all maps, the netting's clip, culling, queue and mip chain, far netting on LOD1/2, bag shadows on LOD0 only,
the blendshape on every LOD, all markers against the manifest (worst 0.00 mm), +Z forward with the right corner on +X,
mouth width, frame length, bag depth in both poses, wetness on and off, disassembled and back, a mock fish crossing
the mouth polygon (and three paths that don't), and the 2 m LOD hand-over at lodBias 2. Renders measure the netting:
26-37 % of the bag's silhouette covered from 0.8 m to 60 m, the underside visible from below (21 %), and a partial
clipped shadow (ground under the mouth 8 % darker). See [NETTING_DISTANCE.md](NETTING_DISTANCE.md).

Renders were inspected by eye: whole net, side, top, front, spreader close-up, bag detail, underside against the sky,
hand scale, scooping, pose transition, wet/dry, disassembled, LOD comparison, the distance sheet (near, mid and far
against sky, water and bank), and the Unity shots.

## Commands

```
start_studio.bat                                         the window
generate.bat net_42_one_piece | all                      full builds
python -m studio.cli check <preset>                      validate without Blender
python -m unittest discover -s tests                     Python + Blender smoke tests
powershell -File tools\test_unity_import.ps1 -Net <id> [-Pipeline builtin] [-Shots output\_unity_shots\<id>]
python -m studio.cli export-unity <preset> <unity project>   explicit copy into Assets\NetStudio only
```

Output paths: `output\<id>\` (export, previews, .blend, report, log), `output\_texture_cache\`,
`output\_unity_shots\<id>\`, and the Unity test logs in `_unitytest\<id>_<pipeline>.log`.

## Decisions taken (and why)

- **"42 inch" = each arm, spreader pivot to corner, as a straight line.** The bowed arm is 0.6 mm longer along its curve.
- **Default 90° opening, 1.80 m handle, 0.90 m bag (0.95 m for the 46"), 9 mm holes with 1.5 mm twine:** proposed proportions, labelled
  as such in the manifest. The arm bow (16 mm) makes the sockets about 99° apart, as on real nets whose cord pulls the
  arm tips in.
- **The scooping pose** deepens the bag by 12 % and draws its bottom back towards the handle by 16 % of the mouth depth:
  a net being lifted with weight in it. It's a pose only.
- **Netting at distance:** alpha clip close up, alpha-blended haze from LOD1 (2 m) on, with the LOD hand-over fixed in
  metres. Measured in [NETTING_DISTANCE.md](NETTING_DISTANCE.md); it's the one deliberate exception to "clip by default".
- **Alpha-to-coverage off:** the game renders without MSAA, and with MSAA A2C thinned the twine.
- **9 mm mesh, 1.5 mm twine (was 6 / 1.1 mm), 2026-11-01:** after Erwin's playtest ("doesn't really look like a net")
  the fine micromesh read as a smooth grey veil from a couple of metres. 9 mm is a common carp-net mesh and its twine
  stays visible about half as far again; coverage hardly changes (26 % vs 28 %), so the distance behaviour holds (Unity: 28-34 %
  of the bag at 0.8-60 m).
- **Far netting without "preserve specular":** URP's default added full-strength highlights to the blended netting
  whatever its alpha, so it showed as a glossy grey sheet in play. The importer turns it off.
- **Lying pose** (the net by the pod): the rim stays on the arms and the bag gathers into a heap a little forward of the
  mouth's centre, pleating back on itself so it lies two or three layers deep in wandering folds, 5-35 mm above the
  ground. A single flat layer read as a faint sheet.
- **Wet:** base colour × 0.62 and smoothness up to × 2 (capped per material). Subtle by design: wet dark netting mostly gains sheen.

## Not done / known limits

- **In the game since 2026-11-01 (Erwin: "yes replace it"):** `net_42_one_piece` is the net in the water, look id
  `landing_net_42` (`StudioLandingNet` in the carp repo, `StudioLandingNetTests`), imported with Carp → Studios → Import
  Landing Net, and since the second playtest also laid flat by the pod in the lying pose (`StudioLandingNet.TryLay`).
  Adapter steps 1-3 are done; hands and a capture rule using the mouth polygon are not
  ([ADAPTER.md](ADAPTER.md)). Not yet checked in play.
- **Compact folding nets** aren't started (deferred by the spec). Taking a handle section off doesn't fold a rigid head,
  and the studio doesn't pretend it does.
- **Close-up moiré** (about 1-2 m) with MSAA off, and **no bag shadow beyond 2 m** (the blended far bags cast none).
- **URP Lit doesn't flip normals on back faces,** so the inside of the double-sided netting is lit with the outside's
  normal. On thin dark twine this hardly shows.
- **Built-in pipeline:** the Standard shader has no cull switch, so the netting is one-sided there. URP is the target.
- **HDRP** material setup is written but untested.
- **Hand and fish proxies** are deliberately crude display shapes for scale.
- **No per-knot geometry or close-detail strands:** the twine is all texture (normal-mapped), well inside the triangle budget.
- **Not checked interactively:** how the prefab looks in the game at Willow Mere's light, in motion (LOD pops, shimmer
  while walking), and with the game's post-processing. That needs Erwin in Play mode once the adapter exists.
