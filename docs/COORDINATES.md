# Coordinates, markers and the mouth

## Frames

| | Build frame (Blender, `studio/geometry.py`) | Unity (FBX, manifest, prefab) |
| --- | --- | --- |
| Right | +X | +X |
| Up | +Z | +Y |
| Forward (butt → mouth) | +Y | +Z |
| Units | metres | metres |

Conversion: Unity `(x, y, z)` = build `(x, z, y)` (`geometry.to_unity`). The FBX goes out with `axis_up=Y`,
`axis_forward=-Z` and baked space transforms, and Unity imports it with `bakeAxisConversion`. The Unity test checks
every marker against the manifest to 0.01 mm, and checks that the right corner is on +X.

The GLB uses the standard glTF conversion from Blender (+Y up; the mouth faces −Z). Use the FBX for Unity.

## Neutral deployed pose

- The origin is the **butt cap centre**, the rear end of the handle.
- The handle lies along +Z, centred on the Z axis.
- The spreader pivot is on the handle axis, `handle length + 0.045 m` from the origin (1.845 m by default).
- The arms leave the spreader in the plane Y = 0 and bow slightly outwards. The corners are exactly
  `arm length` from the pivot at ± half the opening angle.
- The mouth (arms + cord) is flat in Y = 0 and opens upward (+Y). The bag hangs towards −Y.

## Dimensions (default 90° opening)

| | 42" | 46" |
| --- | --- | --- |
| Arm, pivot to corner (source) | 1.0668 m | 1.1684 m |
| Arm arc length (bowed) | 1.0674 m | 1.1690 m |
| Mouth width, corner to corner (derived) | 1.509 m | 1.652 m |
| Mouth depth, pivot to cord (derived) | 0.754 m | 0.826 m |
| Bag opening area (derived) | 0.588 m² | 0.704 m² |
| Socket angle (arms bow, so wider than 90°) | 98.9° | 98.1° |
| Overall length, butt to cord (derived) | 2.599 m | 2.671 m |
| Handle (proposed) | 1.80 m | 1.80 m |
| Bag depth (proposed) | 0.90 m | 0.95 m |
| Bag depth, scooping pose | 1.008 m | 1.064 m |

"Proposed" values are artistic proportions for gameplay fit, not manufacturer data. The manifest's `dimensions`
block labels each value as `source`, `proposed` or `derived`.

## Markers

Empties in the FBX, Transforms in the prefab, reachable through `NetStudioNet.FindMarker(name)`. They're the same for
every LOD; the Blender checks compare each LOD's bag bottom with them. They describe the **assembled** net.

| Marker | Where (42" two-piece, Unity) |
| --- | --- |
| `Marker_ButtCap` | (0, 0, 0) |
| `Marker_GripRear` | rear hand, middle of the rubber grip: (0, 0, 0.21) |
| `Marker_GripFront` | front hand: (0, 0, 1.05) |
| `Marker_HandleJoint` | two-piece only, the joint: (0, 0, 0.90) |
| `Marker_HandleTop` | face of the threaded insert: (0, 0, 1.80) |
| `Marker_Spreader` | spreader pivot: (0, 0, 1.845) |
| `Marker_MouthCentre` | centroid of the bag opening, on the mouth plane: (0, 0, 2.344) |
| `Marker_CornerLeft` / `Marker_CornerRight` | arm tips: (∓0.754, 0, 2.599) |
| `Marker_BagBottom` | lowest point, deployed: (0, −0.90, 2.344) |
| `Marker_BagBottomScooping` | lowest point, scooping (drawn back towards the handle): (0, −1.008, 2.223) |

## Mouth polygon and plane

`net_manifest.json → head`:

- `mouth_polygon`: 48 points along the bag's opening (right arm out from its socket, across the cord, back down the
  left arm, then the short edge across the front of the spreader), clockwise seen from +Y, first point where the right
  arm leaves the spreader. Also in `NetStudioNet.mouthPolygon` (net-local).
- `mouth_plane`: point = mouth centre, normal = +Y.
- `triangle`: spreader, right corner, left corner (the frame, a slightly larger triangle than the opening).
- `depth`: deployed and scooping bag depth and bottom points.

This is metadata, kept apart from the visual mesh. Use it for fish-over-mouth tests. Don't use the bag's render mesh as
a capture volume. There's no bag collider. The optional pickup capsule (`export.pickup_proxy`, off by default) is a
trigger along the grips.

## Sections and display states

`manifest.sections`: each handle section's extent along the handle, its spigot and its objects in every LOD, with the
part's **assembled** local position and a **disassembled** display position. In the disassembled layout the sections lie
side by side and the head is unscrewed and laid beyond them. That layout is for display only and is never a gameplay
deployment, and the markers keep describing the assembled net. `NetStudioNet.disassembled` switches between the two.

Part origins: `Handle` / `HandleLower` at the butt, `HandleUpper` at the joint, `Head` and `NetBag` at the spreader pivot.
