using System;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace Carp.NetStudio.Editor
{
    /// <summary>
    /// The netting's base map with a mip chain built for alpha clipping: every mip keeps the twine's real coverage.
    ///
    /// Plain box-filtered mips average 28 % twine into a uniform alpha of 0.28, which a 0.5 clip throws away: the net
    /// vanishes past ~3 m. Unity's mipMapsPreserveCoverage scales alpha instead, and once a mip is uniform the only way to
    /// keep 28 % of texels above the clip is to push all of them over: the bag turns solid. Measured in the Unity test
    /// (tools\test_unity_import.ps1 -CoverageStudy). Here each mip is shifted by its own quantile so exactly the twine's
    /// share passes the clip, and a small ordered dither breaks ties once holes are smaller than a texel, so far netting
    /// reads as a fine screen of the right density. Mip 0 is the PNG unchanged.
    ///
    /// Bilinear filtering of a sparse pattern trims the kept texels' area once the twine is thinner than a texel (an
    /// isolated texel loses up to half). So each mip keeps the true coverage while the twine is at least two texels wide,
    /// rising to <see cref="FilterBoost"/> times it by the mip where the hole pitch is two texels (calibrated with the
    /// coverage study in the Unity test).
    /// </summary>
    public static class NetCoverageMips
    {
        private const float DitherAmplitude = 0.04f;
        private const float EdgeGain = 40f;
        public const float FilterBoost = 1.3f;

        private static readonly int[] Bayer8 =
        {
            0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4, 36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22,
            3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7, 39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21,
        };

        /// <summary>Build (or update in place, keeping its GUID) the texture asset next to the PNG. Returns it.</summary>
        /// <param name="strandPx">Twine width in texels at full size.</param>
        /// <param name="pitchPx">Hole pitch (twine centre to twine centre) in texels at full size.</param>
        public static Texture2D Build(string pngPath, float cutoff, float strandPx, float pitchPx)
        {
            var source = new Texture2D(2, 2, TextureFormat.RGBA32, false, false);
            if (!source.LoadImage(File.ReadAllBytes(Path.GetFullPath(pngPath))))
            {
                throw new InvalidOperationException("Can't read " + pngPath);
            }

            var size = source.width;
            if (size != source.height || (size & (size - 1)) != 0)
            {
                throw new InvalidOperationException("Netting texture must be square and a power of two: " + pngPath);
            }

            var levels = (int)Math.Log(size, 2) + 1;
            var tex = new Texture2D(size, size, TextureFormat.RGBA32, levels, false);
            var px = source.GetPixels32();
            var rgb = new Color[px.Length];
            var alpha = new float[px.Length];
            var covered = 0;
            for (var i = 0; i < px.Length; i++)
            {
                alpha[i] = px[i].a / 255f;
                rgb[i] = new Color(px[i].r / 255f, px[i].g / 255f, px[i].b / 255f);
                covered += alpha[i] > cutoff ? 1 : 0;
            }

            var coverage = covered / (float)px.Length;
            tex.SetPixels32(px, 0);
            var w = size;
            for (var level = 1; level < levels; level++)
            {
                var nw = w / 2;
                var nRgb = new Color[nw * nw];
                var nAlpha = new float[nw * nw];
                for (var y = 0; y < nw; y++)
                {
                    for (var x = 0; x < nw; x++)
                    {
                        var c = Color.clear;
                        var a = 0f;
                        var wsum = 0f;
                        for (var k = 0; k < 4; k++)
                        {
                            var i = (2 * y + (k >> 1)) * w + 2 * x + (k & 1);
                            a += alpha[i];
                            // Twine colour weighted by twine, so holes don't darken or lighten the average.
                            var wt = alpha[i] + 1e-3f;
                            c += rgb[i] * wt;
                            wsum += wt;
                        }

                        nRgb[y * nw + x] = c / wsum;
                        nAlpha[y * nw + x] = a / 4f;
                    }
                }

                rgb = nRgb;
                alpha = nAlpha;
                w = nw;
                var t = Mathf.InverseLerp(Mathf.Log(strandPx / 2f, 2f), Mathf.Log(pitchPx / 2f, 2f), level);
                var boost = 1f + (FilterBoost - 1f) * t * t * (3f - 2f * t);
                tex.SetPixels32(Remap(rgb, alpha, w, level, Mathf.Min(0.95f, coverage * boost), cutoff), level);
            }

            tex.Apply(false, false);
            EditorUtility.CompressTexture(tex, TextureFormat.BC7, TextureCompressionQuality.Normal);
            tex.wrapMode = TextureWrapMode.Repeat;
            tex.filterMode = FilterMode.Trilinear;
            tex.anisoLevel = 8;
            var assetPath = Path.ChangeExtension(pngPath, null) + "_CoverageMips.asset";
            var existing = AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
            if (existing == null)
            {
                tex.name = Path.GetFileNameWithoutExtension(assetPath);
                AssetDatabase.CreateAsset(tex, assetPath);
                existing = tex;
            }
            else
            {
                EditorUtility.CopySerialized(tex, existing);
                existing.name = Path.GetFileNameWithoutExtension(assetPath);
                EditorUtility.SetDirty(existing);
            }

            UnityEngine.Object.DestroyImmediate(source);
            AssetDatabase.SaveAssets();
            return existing;
        }

        /// <summary>Shift one mip's alpha so the share above the cutoff equals the full-size coverage.</summary>
        private static Color32[] Remap(Color[] rgb, float[] alpha, int w, int level, float coverage, float cutoff)
        {
            var n = alpha.Length;
            var dithered = new float[n];
            for (var y = 0; y < w; y++)
            {
                for (var x = 0; x < w; x++)
                {
                    var b = Bayer8[((y + level * 3) & 7) * 8 + ((x + level * 5) & 7)] / 64f + 1f / 128f;
                    dithered[y * w + x] = alpha[y * w + x] + (b - 0.5f) * DitherAmplitude;
                }
            }

            var sorted = (float[])dithered.Clone();
            Array.Sort(sorted);
            var keep = Mathf.Clamp(Mathf.RoundToInt(coverage * n), 0, n);
            // The threshold sits between the last texel dropped and the first kept.
            float threshold;
            if (keep >= n) threshold = sorted[0] - 1f;
            else if (keep <= 0) threshold = sorted[n - 1] + 1f;
            else threshold = 0.5f * (sorted[n - keep - 1] + sorted[n - keep]);
            var outPx = new Color32[n];
            for (var i = 0; i < n; i++)
            {
                var a = Mathf.Clamp01(cutoff + (dithered[i] - threshold) * EdgeGain);
                var c = rgb[i];
                outPx[i] = new Color32((byte)Mathf.RoundToInt(c.r * 255f), (byte)Mathf.RoundToInt(c.g * 255f),
                    (byte)Mathf.RoundToInt(c.b * 255f), (byte)Mathf.RoundToInt(a * 255f));
            }

            return outPx;
        }
    }
}
