# Landing Net Studio — Project Specification

## Goal
Procedural carp landing nets with realistic mesh and hardware.

## Requirements
- Presets: 42-inch triangular carp landing net, 46-inch large net, compact folding net, two-piece handle variation.
- Geometry: spreader block, two removable carbon arms, realistic taper, handle with textured grip, end cap, connection ferrules; physically plausible net bag sag and depth.
- Net mesh: configurable mesh hole size and knot pattern; optimized alpha-cutout/normal-mapped option for game LODs; detailed mesh only for close-up LOD0. No solid opaque fabric net.
- Interaction: open/closed states where supported; grip/pivot points, net water interaction attachment points; Unity pickup and fish-scooping collider guidance (do not implement fish capture logic unless repo integration exists).
- Materials: matte carbon fiber, black anodized fittings, rubber grip, dark olive mesh, subtle wet/dry appearance.
- Exports: FBX/glTF, texture maps, 3 LODs, collision meshes, prefabs guidance, dimensions in meters.
- Validation: arm symmetry, net drape, mesh transparency sorting, realistic handle length, reasonable triangle budgets.

## Shared architecture
- Standalone Python GUI for presets, parameters, preview, full generate, and export.
- Blender 5.2.3 background-mode generator, portable Blender supported.
- Reproducible seeded generation; modular geometry/material/rig/export pipeline.
- Quick preview and separate full-quality render.
- LOD0, LOD1, LOD2; configurable texture size (1024/2048).
- Unity-compatible FBX and optional glTF export, PBR maps, correctly oriented axes and real-world dimensions.
- Unit tests for parameter ranges, geometry bounds, generated file existence; smoke-test Blender generation.
- Keep all generated files in `output/` and exclude them from version control.
- No dependence on paid assets; do not copy proprietary models or logos.

## Deliverables
1. Working generator and GUI, with at least one complete default preset.
2. Preview images (3/4, front, side, top, detail).
3. LOD meshes, materials, Unity export and import instructions.
4. Automated generation and validation script.
5. Screenshots plus a summary of what works and remaining limitations.
