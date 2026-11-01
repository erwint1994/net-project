# Netting at distance: what was measured and what was chosen

Netting was 28 % twine and 72 % hole when this was measured (6 mm holes, 1.1 mm twine; the default is now 9 mm and 1.5 mm, 26 % twine, and the as-shipped check gives 28-34 % at 0.8-60 m). Seen through both walls of the bag, about 48 % of
the silhouette should look covered. Once the twine is thinner than a pixel, a real net reads as an even dark veil
of that density. A game net must neither **vanish** nor turn into a **solid black bag**.

## The measurement

The Unity test (`tools\test_unity_import.ps1`) renders the 42" bag in URP 17.4 with **MSAA off, as every URP asset of
the carp game is set** (`m_MSAA: 1`). It measures *optical coverage*, how much the white background is darkened inside
the bag's silhouette, from 0.8 m to 60 m. Results from 2026-11-01 (60° FOV for "as shipped", 40° for the variants; LOD0 forced
for the variants):

| Netting | 0.8 m | 3 m | 6 m | 12 m | 25 m |
| --- | --- | --- | --- | --- | --- |
| Alpha clip, plain box-filtered mips | 30 % | 1 % | 1 % | 0 % | 0 % |
| Alpha clip, Unity `mipMapsPreserveCoverage` | 54 % | 91 % | 91 % | 91 % | 91 % |
| Alpha clip, Net Studio quantile mips | 32 % | 13 % | 9 % | 10 % | 3 % |

- **Plain mips:** box filtering turns 28 % twine into a uniform alpha of 0.28, which a 0.5 clip throws away. The net vanishes.
- **Unity's coverage preservation** scales alpha up. Once a mip is uniform, the only way to keep 28 % of texels above
  the clip is to push all of them over. The bag turns solid.
- **Quantile mips** (`NetCoverageMips`: each mip shifted by its own quantile, ordered dither for ties, a 1.3× allowance
  for filtering loss) keep the right share of *texels*. Bilinear and trilinear filtering of that sparse pattern still
  thins it on screen. A steeper allowance (1.8×) overshot to 77-81 %; the response is too steep to tune reliably.
- **Alpha-to-coverage** needs MSAA, which the game doesn't use. With MSAA it measured thinner at every distance,
  because URP sharpens alpha around the cutoff.

## What ships

| Range (60° FOV) | LOD | Netting | Coverage measured |
| --- | --- | --- | --- |
| up to 2 m | LOD0 | alpha clip, double-sided, opaque queue, quantile mips, clipped shadows | 26-32 % |
| 2-19 m | LOD1 | alpha-blended haze, plain mips (opacity = twine coverage), no shadow | 33-37 % |
| 19-280 m | LOD2 | as LOD1 | 33 % |

As shipped (automatic LOD, lodBias 2 cancelled by `NetStudioNet`) the bag covers **26-37 % of its silhouette at every
distance from 0.8 m to 60 m**, so it never vanishes and never goes solid. The test fails if any distance falls outside 12-80 %.

- **Alpha clip stays the default for close-up netting.** That's where holes are resolved, depth matters and shadows show.
- **Blending in the far LODs** is the one place the spec's "clip rather than blend" default is set aside, because every
  clip variant measured above fails there. The netting is a single uniform colour, so the blend order inside the bag
  barely changes the result. The blended bags cast no shadow, because URP would draw a blended bag's shadow solid.
- **The clipped shadow** (LOD0) darkens the ground under the mouth by about 8 % in an overhead sun: a speckled, partial
  shadow, not a solid one.

## Known limits

- With MSAA off, close-up netting (about 1-2 m) shows **moiré rings**, the regular mesh aliasing against the pixel
  grid. MSAA or TAA in the game would smooth this. The studio can't fix it in the texture alone.
- Beyond 2 m the bag casts no shadow.
- The Blender previews approximate the Unity look with Eevee's dithered alpha (raw alpha, averaged by TAA). The GLB keeps
  a hard alpha clip (alphaMode MASK) for other viewers.
- The coverage numbers are from one camera path and one lighting setup; they are a regression guard, not a perceptual study.
