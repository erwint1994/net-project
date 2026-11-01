# Claude launch prompt: Landing Net Studio

Paste into a separate Claude session:

```text
Implement C:\repos\carp\docs\design\NET_STUDIO.md as a new standalone project
at C:\repos\net-project. Read applicable AGENTS.md instructions first.

My supplied starter brief is preserved at:
C:\repos\carp\docs\design\references\landing-net\
Read its PROJECT_SPEC.md, README.md and project.json alongside the main specification.
Preserve original references and record provenance in the new repository.

Start with 42-inch and 46-inch triangular carp nets, each with one- and two-piece handle
options. Inches refer to each arm length, not head width. Build plausible carbon arms,
spreader, joints, grip and hanging open net bag. Holes must remain visible with efficient
alpha-clipped netting in Blender AND Unity; no opaque cloth bag. Provide deployed empty
and scooping bag poses, optional wetness and explicitly documented attachment/mouth data.
Compact folding designs come later.

Study C:\repos\bivvy-project for the existing studio pipeline. Inspect current game
net, landing, hand and water-placement consumers read-only to define an integration
adapter. Keep live game scripts/scenes and sibling studios unchanged. Other sessions
are working there. Do not add or replace production fish capture logic.

Build the CLI, tkinter editor, editable/saveable presets, geometry/materials/pose system,
previews, three LODs, FBX/GLB/PBR exports, manifests, validation and Unity importer.
Resolve NET_BLENDER first, then reuse sibling bivvy portable Blender read-only. Keep
the new project independently runnable. Export explicit mouth polygon/plane and grip,
spreader and corner markers. Preview fish/hand proxies must be excluded from exports.

Inspect actual renders and test all four head/handle combinations. Verify dimensions,
bag drape, rim attachment, pose transitions, alpha/shadows and hole scale at multiple
distances against sky/water/bank. Test actual exports and importer in an isolated Unity
project. Do not use complex render mesh collision as the default capture mechanism.

Maintain README.md and docs/STATUS.md with launch/export commands, output paths, actual
results and remaining limits. If tools block verification, finish independent work and
report pending checks honestly. Deliver working generated models and the complete studio,
not only a scaffold or plan. Do not commit or push.
```
