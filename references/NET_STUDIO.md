# Carp Landing Net Studio

Specification, 1 November 2026. New repository: `C:\repos\net-project`.
Launch prompt: `NET_STUDIO_PROMPT.md`. Source briefs: `docs/design/references/landing-net/`.
Status: design only. Read the preserved brief; keep reference files unchanged.

## Initial models

First release: original unbranded triangular carp nets, 42-inch and 46-inch arms, each
with a one-piece and two-piece handle option. Define inches as EACH arm's length from
spreader pivot to front corner, not net mouth width. Convert exactly: 1.0668 m and
1.1684 m. Expose the arm opening angle and derive mouth width/depth; label all separately.
Default handle length 1.80 m, bag depth 0.90 m and opening angle 90 degrees are proposed
artistic dimensions. Refine against proportions and gameplay fit, not assumed manufacturer data.
Compact folding net is later: don't pretend removing a handle section folds a rigid head.

Model tapered carbon arms, spreader block, sockets/ferrules, handle, grip, cap, rim cord,
seams and a hanging net bag. Arms join the block and bag attaches continuously to the rim.
The bag must sag naturally with an open mouth; not a flat filled triangle. Netting has
visible holes, not opaque cloth. Do not model each knot at unnecessary cost.

## Net material and states

Provide an optimized UV-mapped alpha-clipped net material with double-sided rendering and
appropriate shadow settings. Preserve this in Unity URP and GLB as well as Blender previews.
Use alpha clipping rather than alpha-blended sorting as the default; show hole size in mm
and retain consistent physical scale. Optional close-detail strands can be used within budget;
lower LODs keep readable netting without becoming a solid black bag. Test distant shimmer.

Ship deployed empty and scooping bag poses with a small rig or blendshapes and a preview
transition. A display-only fish proxy can demonstrate capacity, excluded from exports.
These poses do not implement cloth, water drag, fish capture or a load-bearing simulation.
Two-piece handle uses explicit sections and assembly transforms; optional disassembled
display state is clearly separate from gameplay deployment. Wet/dry material parameter
changes roughness/colour; does not claim a dynamic water simulation.

## Coordinates and gameplay contract

Inspect current game net/landing consumers and rod/hand pose conventions read-only.
Unity metres, +Y up; origin at butt-cap centre, handle toward +Z, mouth forward from
the spreader in +Z, opening toward +Y in neutral deployed pose. Mark grip positions,
handle joint, spreader, mouth centre, mouth corners and bag bottom; document axes.
Export a mouth polygon/local plane plus depth metadata separately from visual mesh and
any collision proxy. This enables later fish-over-mouth tests without using the bag's
render mesh as a capture volume. No automatic capture logic or solid bag collider.
Optional pickup proxy is disabled by default. Preserve markers in every LOD/state.

## Studio and pipeline

Python/tkinter and CLI, background Blender. Resolve NET_BLENDER, then existing sibling
bivvy portable Blender. Presets expose head/handle size, sections, grip, opening, bag depth,
mesh-hole size, material colours, wetness, seed and quality. Save-as, quick/full builds,
progress/logs, state selection and explicit Unity export. Plain-Python layout validates
finite dimensions, head geometry, handle joints and safe IDs before launch.

Layout: studio/, config/, presets/, blender/net/, unity/NetStudio/{Editor,Runtime}/,
tests/, docs/, references/, output/. Keep geometry, drape, materials, pose, export and
validation modular. Build all four head/handle combinations from shared parts.

Export FBX with LOD0/1/2 and pose data, textured GLB, PBR maps including alpha, .blend,
resolved settings, previews/contact sheet, logs, validation and export/net_manifest.json.
Manifest records schema, source/proposed dimensions, metres/axes, head polygon, markers,
sections, pose mechanism, materials/alpha settings, relative files and LOD counts.
Initial triangle ceilings 18k / 7k / 2k; maps 1K/2K. Budget any detailed net strands.
Preview whole net, side/top, spreader, bag detail, wet/dry, scooping and hand-scale views.

Importer Carp.NetStudio.Editor, optional small pose-preview runtime Carp.NetStudio.
Destination Assets/NetStudio/Nets/<id>/. Build pipeline materials with correct clipping,
normals and culling, LODGroup, poses, markers and prefab. Reimport with stable identities.
Explicit export only; do not edit the live game or other creators.

## Acceptance

Test dimension conversion, mouth/arm geometry, sections, config and manifest/path safety.
Blender checks symmetry, joins, mesh health, UV/hole scale, bag drape, poses, marker positions,
LOD budgets and FBX round trip. Inspect alpha against sky, bank and water at near/far ranges.
In isolated Unity verify clipping, shadows, underside visibility, pose data, scale, LODs and
mouth markers. Test a separate mock fish crossing the recorded mouth polygon as a metadata
demonstration, without changing production landing rules. Record missing interactive checks.

Deliver complete 42/46-inch head and handle variants, then consider folding designs.
Maintain README and docs/STATUS.md with actual validation, startup/export commands and
an adapter plan for later hand/ground/water placement and existing capture behavior.
