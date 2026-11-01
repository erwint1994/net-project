# Adapter plan: Net Studio nets in the carp game

Status (2026-11-01): steps 1 and 2 are done in the carp repo. `StudioGearSetup.ImportLandingNet` imports
`net_42_one_piece` as `landing_net_42`, and `LandingNetVisual` uses `StudioLandingNet` when the library has it (the
code-built net is the fallback). Steps 3-6 are still plans. The game's code was read on 2026-11-01 to define this.

## What the game has today (read-only findings)

| Where (`CarpFishingSimulator/Assets/Scripts/Lakes/`) | What it does |
| --- | --- |
| `LandingNetVisual.cs` | Code-built 42" net shown in the water. Local frame: +Z away from the angler, **mouth centred on the origin at the water surface**. Spreader at z = −0.5, arms 1.07 m at ±45°, flat 0.45 m bag, and a handle tube from the spreader up to the bank (+1.0 m up, 1.7 m back). `Place(show, centre, angler)` puts the root on the mouth centre and turns +Z away from the angler. Mesh opacity uses an alpha-blended material, no shadows. |
| `BankVisualController.cs` | The net lying by the rod pod (`Tackle_Net`, code-built), hidden while it's set in the margin (`SetBankNetVisible`). |
| `LakeGameplayEntryController.BankNet.cs` | N sets or moves the net in the margin where the angler looks (`BankNetSpot.Find`, within 45° of the swim at a peg). It's at `LakeGridTerrainHeights.WaterSurfaceY`, and the handle points back at the angler (`FightNetHandleFrom`). In a fight the bank net becomes the fight's net if it's within reach. |
| `BankNetSpot.cs` | Finds the water spot: half a metre out from the edge (`netMarginM`), out past a peg's staging. |
| `CarpFightSimulation.cs` | Netting rule: the fish is netted when its path this tick passes within **`NetMouthRadiusM` = 0.6 m** of the net's centre (a 2D circle on the fight plane), the net is in reach (`NetReachM` 4 m, `NetReachFromEdgeM` 2.5 m, `NetStepDownMaxM` 6 m), and the fish isn't running or weeded. Fish that are landed by hand skip the net. |
| `Resources/Data/Fish/fight_tuning.json` | `netStamina` 0.2, `netLeadTurnDegPerSec` 90, `netLeadMinRodPitchDeg` 30, `netMarginM` 0.5, `netMaxOffSwimDeg` 45. |
| `HeldRodPose.cs` | First-person rod and hand poses in view space (hands low on the right). There's no net-holding pose yet. |
| `Core/Editor/StudioGearSetup.cs` | How the other studios' gear reaches the game (it fills `Resources/GearLookLibrary`). |

## The adapter, step by step (each step only when Erwin asks)

1. **Bring the prefab in.** Use `studio.cli export-unity` (or the window) to copy the net into `Assets/NetStudio/`, then
   register it through `StudioGearSetup` like the other studios. The game's own scripts stay untouched by the studio.

2. **`StudioLandingNet` visual (new class in `Carp.Lakes`)**, with the same contract as `LandingNetVisual.Place(show,
   centre, angler)`, so the controller only swaps which visual it creates:
   - Instantiate the prefab. Put `Marker_MouthCentre` on `centre` (the water spot), with prefab +Z pointing away from the
     angler (as now).
   - **Pitch the whole net about the spreader** so the butt rises towards the angler's hands. A rigid triangle net
     can't keep a flat head with a raised handle: in the water the head tilts and the front sinks. Pitch =
     asin(rise / distance from `Marker_ButtCap` to `Marker_Spreader`). Keep `Marker_Spreader` at or just under the surface.
   - Set `NetStudioNet.wetness` to 1 when it goes in, and let it fall back over a few minutes on the bank (material only).
   - Drive `NetStudioNet.scoop` from 0 to 1 when the fight reaches `ReadyToNet` and the net is lifted. Display only.
   - In shallow margins, compare `Marker_BagBottom` with the lake bed height and pitch the head up until the bag clears
     it. Hiding the clipping isn't enough, because the bag is 0.9 m deep.

3. **The net lying on the bank** (`BankVisualController`): this needs a **collapsed bag pose** that the studio doesn't
   have yet. The bag hangs towards −Y and would go into the ground. Add it as a second blendshape, `Lying`, in the
   studio first, then lay the prefab flat beside the pod.

4. **Hands:** a later `HeldNetPose` (like `HeldRodPose`) puts the right hand on `Marker_GripRear` and the left on
   `Marker_GripFront`. For a two-piece net, use `Marker_HandleJoint` if the front hand should sit at the joint.

5. **Capture behaviour** stays the game's: no change to `CarpFightSimulation` without Erwin's decision. The manifest
   makes a more faithful rule possible later:
   - Today's circle (r = 0.6 m, 1.13 m²) is larger in area than a 42" net's real opening (0.588 m²; 0.704 m² for a 46").
   - `NetStudioNet.SegmentCrossesMouth(a, b)` and `NetMouth.ContainsXZ(polygon, p)` test a fish path against the real
     opening in net-local space. The Unity test shows them working on a net placed and turned in the world.
   - A 46" net could then be a real gear choice: a 9.5 % wider mouth and 20 % more opening.
   - Never use the bag's render mesh as a capture volume. There's no bag collider by design.

6. **Pickup:** if the game ever needs to pick the net up, turn on `export.pickup_proxy` (a trigger capsule along the
   grips) rather than adding mesh colliders.

## Fit with the current visual

| | Game's `LandingNetVisual` | Net Studio 42" |
| --- | --- | --- |
| Arm length | 1.07 m | 1.0668 m (42 in exactly) |
| Opening | 90° | 90° (chord), sockets 98.9° |
| Bag depth | 0.45 m (flat pyramid) | 0.90 m hanging bag |
| Origin | mouth centre at the water | butt cap (use `Marker_MouthCentre` to place) |
| Forward | +Z away from the angler | +Z from butt to mouth |
| Handle | a separate tube to the bank | a real 1.8 m handle in the head's plane |
