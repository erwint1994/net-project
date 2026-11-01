# Provenance

Copied unchanged on 2026-11-01 from the carp game repository (`C:\repos\carp`, branch `main`, commit `22fde434`):

| File here | Source | SHA-256 |
| --- | --- | --- |
| `landing-net/CODEX_START_PROMPT.md` | `docs/design/references/landing-net/CODEX_START_PROMPT.md` (Erwin's starter brief) | `d2c9fedd2c10dc7b7bf5dd4d3047d7dfae4142cd924c58efb86d20260e830a61` |
| `landing-net/PROJECT_SPEC.md` | `docs/design/references/landing-net/PROJECT_SPEC.md` | `88f52d7e1d7244b77b04f759761259828352ca5da8fcfdfd61fd44bc6f81b5aa` |
| `landing-net/README.md` | `docs/design/references/landing-net/README.md` | `fd95a4a75523bbdd0a08ff0185105a2b7d430af027814ce101154ebbfd65c7e0` |
| `landing-net/project.json` | `docs/design/references/landing-net/project.json` | `336fb356e5d7d59ac7392ba9bb21ef86e637ce147a5317a224d8f5f7d45efb81` |
| `NET_STUDIO.md` | `docs/design/NET_STUDIO.md` (the main specification) | `55e69c5e250f3a5e71de149766de349128be73a69a2acc745c1152dfe55489e5` |
| `NET_STUDIO_PROMPT.md` | `docs/design/NET_STUDIO_PROMPT.md` (the launch prompt) | `199331bc4d44fe4e88614826bcd6751d0c8938e1179544cdc7c1100c5f4adeb6` |

Precedence: `NET_STUDIO.md` and the launch prompt over the starter brief where they differ. The starter brief's compact
folding net is deferred, as the specification says.

## What else was used

- **Architecture:** the sibling Carp Bivvy Studio (`C:\repos\bivvy-project`), read only: the studio / Blender / Unity
  layout, the runner, and the importer and Unity-test pattern. `blender/net/meshkit.py` follows its MeshBuilder idea;
  everything else was written for this project.
- **Blender:** the bivvy's portable Blender 5.2.3 is run read-only, and never modified or updated from here.
- **Game consumers** (read-only, for the adapter plan and the coordinate frame): see [docs/ADAPTER.md](../docs/ADAPTER.md).

## What was not used

No manufacturer models, drawings, photos, logos or measurements. All geometry and every texture is generated
procedurally from the parameters in `config/` and `presets/`. Dimensions marked "proposed" are artistic choices for
realism and gameplay fit.
