# Coding agent kickoff: Landing Net Studio

Build a **new, separate repository** for Landing Net Studio, a standalone procedural asset studio for my realistic Unity carp-fishing simulator.

Context: I already have a successful Carp Bivvy Studio and Carp Furniture Studio using portable Blender 5.2.3, Python GUI, procedural mesh/material generation, preview renders, three LODs and Unity exports. Use these projects as architectural references **only if they are available in my workspace**. Do not assume you can read them. Do not modify other repositories.

Read `PROJECT_SPEC.md` in full.

First: inspect the current workspace, identify available Blender/Python/Unity tooling, and propose a short implementation plan with milestones. Then implement the smallest end-to-end working version: one preset -> parameterized mesh -> materials -> quick preview -> full render -> LODs -> Unity export -> validation. After that, add the other presets and advanced features.

Prioritize **realistic shape, materials, and construction** over simply increasing polygon count. Use original geometry and textures. Keep parameters meaningful, add informative error messages, and avoid placeholder geometry being presented as finished.

Specific requirements:
Presets: 42-inch triangular carp landing net, 46-inch large net, compact folding net, two-piece handle variation.
Geometry: spreader block, two removable carbon arms, realistic taper, handle with textured grip, end cap, connection ferrules; physically plausible net bag sag and depth.
Net mesh: configurable mesh hole size and knot pattern; optimized alpha-cutout/normal-mapped option for game LODs; detailed mesh only for close-up LOD0. No solid opaque fabric net.
Interaction: open/closed states where supported; grip/pivot points, net water interaction attachment points; Unity pickup and fish-scooping collider guidance (do not implement fish capture logic unless repo integration exists).
Materials: matte carbon fiber, black anodized fittings, rubber grip, dark olive mesh, subtle wet/dry appearance.
Exports: FBX/glTF, texture maps, 3 LODs, collision meshes, prefabs guidance, dimensions in meters.
Validation: arm symmetry, net drape, mesh transparency sorting, realistic handle length, reasonable triangle budgets.

When finished, run a complete default-preset generation, verify all output paths and provide the preview image locations and a concise status report.
