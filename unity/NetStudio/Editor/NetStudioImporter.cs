using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace Carp.NetStudio.Editor
{
    /// <summary>
    /// Turns a Net Studio export folder (FBX + Textures/ + net_manifest.json) into a prefab under
    /// Assets/NetStudio/Nets/&lt;id&gt;/: pipeline materials (alpha-clipped, double-sided netting with a mip chain that
    /// keeps the twine's coverage, see <see cref="NetCoverageMips"/>; alpha-blended haze on the far LODs), LODGroup (LOD0-2), the scooping blendshape, markers, and a <see cref="NetStudioNet"/>
    /// component with the mouth polygon. Reimporting keeps the prefab, material and texture assets (same paths, same GUIDs).
    /// Nothing outside Assets/NetStudio is touched, and nothing is added to scenes.
    /// </summary>
    public static class NetStudioImporter
    {
        public const string NetsRoot = "Assets/NetStudio/Nets";
        private const string ManifestName = "net_manifest.json";
        private static readonly Regex SafeId = new Regex("^[a-z][a-z0-9_]{0,47}$");

        [Serializable]
        private class Manifest
        {
            public string schema;
            public string id;
            public string name;
            public string root;
            public FileList files;
            public UnityPart unity;
        }

        [Serializable]
        private class FileList
        {
            public string fbx;
            public string[] textures;
        }

        [Serializable]
        private class UnityPart
        {
            public LodEntry[] lods;
            public MaterialEntry[] materials;
            public Named[] markers;
            public Named[] mouthPolygon;
            public float[] mouthNormal;
            public float lodReferenceFov;
            public SectionEntry[] sections;
            public string blendshape;
            public string lyingBlendshape;
            public float lyingGroundY;
            public string[] bagObjects;
            public float defaultWetness;
            public bool pickupEnabled;
            public float[] pickupCentre;
            public float pickupHeight;
            public float pickupRadius;
        }

        [Serializable]
        private class LodEntry
        {
            public string name;
            public string[] objects;
            public float switchMetres;
            public bool bagCastsShadows;
            public bool blendedNetting;
        }

        [Serializable]
        private class MaterialEntry
        {
            public string name;
            public string baseMap;
            public string normalMap;
            public string maskMap;
            public float[] tiling;
            public float metallic;
            public float smoothness;
            public bool alphaClip;
            public float cutoff;
            public bool doubleSided;
            public float wetTint;
            public float wetSmoothness;
            public float smoothnessCap;
            public float strandPx;
            public float pitchPx;
        }

        [Serializable]
        private class Named
        {
            public string name;
            public float[] position;
        }

        [Serializable]
        private class SectionEntry
        {
            public string name;
            public string[] objects;
            public float[] assembled;
            public float[] disassembled;
        }

        [MenuItem("Tools/Net Studio/Import Export Folder...")]
        private static void ImportFolderMenu()
        {
            var source = EditorUtility.OpenFolderPanel("Net Studio export folder (has net_manifest.json)", "", "");
            if (string.IsNullOrEmpty(source))
            {
                return;
            }

            var prefab = ImportExportFolder(source);
            EditorUtility.DisplayDialog("Net Studio", "Prefab created:\n" + prefab, "OK");
            Selection.activeObject = AssetDatabase.LoadAssetAtPath<GameObject>(prefab);
        }

        [MenuItem("Tools/Net Studio/Rebuild All Net Prefabs")]
        private static void RebuildAllMenu()
        {
            var built = BuildAll();
            EditorUtility.DisplayDialog("Net Studio", built.Count == 0 ? "No nets under " + NetsRoot : "Rebuilt:\n" + string.Join("\n", built), "OK");
        }

        /// <summary>Batch mode: -executeMethod Carp.NetStudio.Editor.NetStudioImporter.ImportFromCommandLine -netExport &lt;folder&gt;</summary>
        public static void ImportFromCommandLine()
        {
            var args = Environment.GetCommandLineArgs();
            var at = Array.IndexOf(args, "-netExport");
            if (at < 0 || at + 1 >= args.Length)
            {
                throw new ArgumentException("Pass -netExport <export folder>");
            }

            Debug.Log("[NetStudio] prefab: " + ImportExportFolder(args[at + 1]));
        }

        /// <summary>Copy an export folder into Assets/NetStudio/Nets/&lt;id&gt; (the GLB is left out) and build its prefab.</summary>
        public static string ImportExportFolder(string sourceFolder)
        {
            var manifest = ReadManifest(Path.Combine(sourceFolder, ManifestName));
            var target = NetsRoot + "/" + manifest.id;
            var targetFull = Path.GetFullPath(target);
            var listed = new List<string> { manifest.files.fbx, ManifestName };
            listed.AddRange(manifest.files.textures ?? Array.Empty<string>());
            foreach (var relative in listed)
            {
                var destination = Path.GetFullPath(Path.Combine(targetFull, relative));
                if (!IsSafeRelative(relative) || !destination.StartsWith(targetFull + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidOperationException("Unsafe path in the manifest: " + relative);
                }

                var source = Path.Combine(sourceFolder, relative);
                if (!File.Exists(source))
                {
                    throw new FileNotFoundException("Listed in the manifest but missing from the export folder", source);
                }

                Directory.CreateDirectory(Path.GetDirectoryName(destination));
                File.Copy(source, destination, true);
            }

            AssetDatabase.Refresh();
            return Build(target);
        }

        public static List<string> BuildAll()
        {
            var built = new List<string>();
            if (!AssetDatabase.IsValidFolder(NetsRoot))
            {
                return built;
            }

            foreach (var folder in AssetDatabase.GetSubFolders(NetsRoot))
            {
                if (File.Exists(Path.Combine(folder, ManifestName)))
                {
                    built.Add(Build(folder));
                }
            }

            return built;
        }

        /// <summary>Build (or rebuild) the prefab for an export folder already inside Assets/.</summary>
        public static string Build(string folder)
        {
            var manifest = ReadManifest(Path.Combine(folder, ManifestName));
            var shader = FindLitShader(out var pipeline);
            var materials = new Dictionary<string, Material>();
            Material farNet = null;
            foreach (var entry in manifest.unity.materials)
            {
                materials[entry.name] = CreateMaterial(folder, entry, shader, pipeline);
                if (entry.alphaClip && manifest.unity.lods.Any(l => l.blendedNetting))
                {
                    farNet = CreateFarNetting(folder, entry, shader, pipeline);
                }
            }

            var fbxPath = folder + "/" + manifest.files.fbx;
            var importer = (ModelImporter)AssetImporter.GetAtPath(fbxPath);
            if (importer == null)
            {
                throw new FileNotFoundException("FBX not imported", fbxPath);
            }

            importer.globalScale = 1f;
            importer.useFileScale = true;
            importer.bakeAxisConversion = true;
            importer.importBlendShapes = true;
            importer.importAnimation = false;
            importer.animationType = ModelImporterAnimationType.None;
            importer.importCameras = false;
            importer.importLights = false;
            importer.isReadable = true;
            importer.importNormals = ModelImporterNormals.Import;
            importer.importBlendShapeNormals = ModelImporterNormals.Calculate;
            importer.importTangents = ModelImporterTangents.CalculateMikk;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            foreach (var pair in materials)
            {
                importer.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), pair.Key), pair.Value);
            }

            importer.SaveAndReimport();

            var model = AssetDatabase.LoadAssetAtPath<GameObject>(fbxPath);
            var instance = (GameObject)UnityEngine.Object.Instantiate(model);
            instance.name = manifest.root;
            try
            {
                var byName = instance.GetComponentsInChildren<Transform>(true).GroupBy(t => t.name).ToDictionary(g => g.Key, g => g.First());
                Transform Find(string objectName)
                {
                    if (!byName.TryGetValue(objectName, out var t))
                    {
                        throw new InvalidOperationException("Missing from the FBX: " + objectName);
                    }

                    return t;
                }

                // With animation import off, Unity gives a mesh with blendshapes a plain MeshRenderer, which can't drive them.
                foreach (var bagName in manifest.unity.bagObjects)
                {
                    var t = Find(bagName);
                    var filter = t.GetComponent<MeshFilter>();
                    if (filter == null)
                    {
                        continue;
                    }

                    var mesh = filter.sharedMesh;
                    var materialsOnBag = t.GetComponent<MeshRenderer>().sharedMaterials;
                    UnityEngine.Object.DestroyImmediate(t.GetComponent<MeshRenderer>());
                    UnityEngine.Object.DestroyImmediate(filter);
                    var skinned = t.gameObject.AddComponent<SkinnedMeshRenderer>();
                    skinned.sharedMesh = mesh;
                    skinned.sharedMaterials = materialsOnBag;
                    skinned.rootBone = t;
                }

                var lods = new List<LOD>();
                foreach (var lod in manifest.unity.lods)
                {
                    var renderers = lod.objects.Select(n => Find(n).GetComponent<Renderer>()).Where(r => r != null).ToArray();
                    foreach (var r in renderers)
                    {
                        var isBag = manifest.unity.bagObjects.Contains(r.name);
                        if (isBag && lod.blendedNetting && farNet != null)
                        {
                            r.sharedMaterials = r.sharedMaterials.Select(m => m != null && m.name == "NT_Net" ? farNet : m).ToArray();
                        }

                        r.shadowCastingMode = !isBag || lod.bagCastsShadows ? ShadowCastingMode.On : ShadowCastingMode.Off;
                        r.receiveShadows = true;
                        if (r is SkinnedMeshRenderer skinned)
                        {
                            skinned.updateWhenOffscreen = false;
                            skinned.localBounds = Inflate(skinned.sharedMesh.bounds, 0.2f);
                        }
                    }

                    // Provisional, strictly falling heights (Unity drops renderers from equal ones); set from metres below.
                    lods.Add(new LOD(0.9f / (1 + lods.Count * 4), renderers));
                }

                var group = instance.AddComponent<LODGroup>();
                group.SetLODs(lods.ToArray());
                group.RecalculateBounds();
                // Hand-over distances in metres -> screen heights. A close LOD0 range can need a height above 1, which
                // Unity doesn't allow, so the group's size is scaled down instead (the same relative heights).
                var tanHalf = Mathf.Tan(manifest.unity.lodReferenceFov * 0.5f * Mathf.Deg2Rad);
                var heights = manifest.unity.lods.Select(l => group.size / (2f * tanHalf * l.switchMetres)).ToArray();
                var shrink = Mathf.Max(1f, heights[0] / 0.999f);
                var lodArray = group.GetLODs();
                for (var i = 0; i < lodArray.Length; i++)
                {
                    lodArray[i].screenRelativeTransitionHeight = heights[i] / shrink;
                }

                group.SetLODs(lodArray);
                group.size /= shrink;

                var net = instance.AddComponent<NetStudioNet>();
                net.netId = manifest.id;
                net.markers = manifest.unity.markers.Select(m => new NetStudioNet.Marker { name = m.name, transform = Find(m.name) }).ToArray();
                net.mouthPolygon = manifest.unity.mouthPolygon.Select(p => V(p.position)).ToArray();
                net.mouthNormal = V(manifest.unity.mouthNormal);
                net.mouthCentre = V(manifest.unity.markers.First(m => m.name == "Marker_MouthCentre").position);
                net.blendShape = manifest.unity.blendshape;
                net.lyingBlendShape = string.IsNullOrEmpty(manifest.unity.lyingBlendshape) ? "Lying" : manifest.unity.lyingBlendshape;
                net.lyingGroundY = manifest.unity.lyingGroundY;
                net.bagRenderers = manifest.unity.bagObjects.Select(n => Find(n).GetComponent<SkinnedMeshRenderer>()).ToArray();
                for (var i = 0; i < net.bagRenderers.Length; i++)
                {
                    var bag = net.bagRenderers[i];
                    if (bag == null || bag.sharedMesh.GetBlendShapeIndex(net.blendShape) < 0)
                    {
                        var t = Find(manifest.unity.bagObjects[i]);
                        var mesh = bag != null ? bag.sharedMesh : t.GetComponent<MeshFilter>()?.sharedMesh;
                        var names = mesh == null ? "no mesh" : string.Join(", ", Enumerable.Range(0, mesh.blendShapeCount).Select(mesh.GetBlendShapeName));
                        throw new InvalidOperationException($"{t.name} came in without its '{net.blendShape}' blendshape "
                                                            + $"(renderer {t.GetComponent<Renderer>()?.GetType().Name}, blendshapes: {names})");
                    }
                }

                net.sections = manifest.unity.sections.Select(s => new NetStudioNet.Section
                {
                    name = s.name,
                    objects = s.objects.Select(Find).ToArray(),
                    assembled = V(s.assembled),
                    disassembled = V(s.disassembled),
                }).ToArray();
                net.wetMaterials = manifest.unity.materials.Select(m => new NetStudioNet.WetMaterial
                {
                    name = m.name,
                    wetTint = m.wetTint,
                    wetSmoothness = m.wetSmoothness,
                    smoothnessCap = m.smoothnessCap,
                }).ToArray();
                net.wetRenderers = instance.GetComponentsInChildren<Renderer>(true);
                net.wetness = manifest.unity.defaultWetness;
                net.lodSizeAtBiasOne = group.size;

                if (manifest.unity.pickupEnabled)
                {
                    var capsule = instance.AddComponent<CapsuleCollider>();
                    capsule.direction = 2;
                    capsule.center = V(manifest.unity.pickupCentre);
                    capsule.height = manifest.unity.pickupHeight;
                    capsule.radius = manifest.unity.pickupRadius;
                    capsule.isTrigger = true;
                }

                var prefabPath = folder + "/" + manifest.id + ".prefab";
                PrefabUtility.SaveAsPrefabAsset(instance, prefabPath);
                Debug.Log($"[NetStudio] {manifest.name}: {prefabPath} ({pipeline}, {lods.Count} LODs, {net.markers.Length} markers)");
                return prefabPath;
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(instance);
            }
        }

        private static Bounds Inflate(Bounds b, float fraction)
        {
            b.Expand(b.size * fraction);
            return b;
        }

        private static Vector3 V(float[] p)
        {
            return new Vector3(p[0], p[1], p[2]);
        }

        private static bool IsSafeRelative(string path)
        {
            if (string.IsNullOrEmpty(path) || Path.IsPathRooted(path) || path.Contains(":"))
            {
                return false;
            }

            return path.Replace('\\', '/').Split('/').All(part => part.Length > 0 && part != ".." && part != ".");
        }

        private static Manifest ReadManifest(string path)
        {
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("No net_manifest.json here", path);
            }

            var manifest = JsonUtility.FromJson<Manifest>(File.ReadAllText(path));
            if (manifest.schema != "carp-net-studio/1")
            {
                throw new InvalidOperationException("Not a Net Studio manifest (schema " + manifest.schema + ")");
            }

            if (manifest.id == null || !SafeId.IsMatch(manifest.id))
            {
                throw new InvalidOperationException("Unsafe net id in the manifest: " + manifest.id);
            }

            return manifest;
        }

        /// <summary>The render pipeline's lit shader: URP, HDRP or the Built-in Standard shader.</summary>
        private static Shader FindLitShader(out string pipeline)
        {
            var asset = GraphicsSettings.currentRenderPipeline;
            var typeName = asset == null ? "" : asset.GetType().Name;
            if (typeName.Contains("Universal"))
            {
                pipeline = "URP";
                return Shader.Find("Universal Render Pipeline/Lit");
            }

            if (typeName.Contains("HDRenderPipeline"))
            {
                pipeline = "HDRP";
                return Shader.Find("HDRP/Lit");
            }

            pipeline = "Built-in";
            return Shader.Find("Standard");
        }

        private static Material CreateMaterial(string folder, MaterialEntry entry, Shader shader, string pipeline)
        {
            var baseMap = Texture(folder + "/" + entry.baseMap, entry.alphaClip ? TextureKind.ClippedColour : TextureKind.Colour, entry.cutoff);
            if (entry.alphaClip)
            {
                // Netting: its own mip chain that keeps the twine's coverage at every distance (see NetCoverageMips).
                baseMap = NetCoverageMips.Build(folder + "/" + entry.baseMap, entry.cutoff, entry.strandPx, entry.pitchPx);
            }
            var normalMap = Texture(folder + "/" + entry.normalMap, TextureKind.Normal, 0f);
            var maskMap = Texture(folder + "/" + entry.maskMap, TextureKind.Data, 0f);
            var path = folder + "/Materials/" + entry.name + ".mat";
            Directory.CreateDirectory(Path.GetFullPath(folder + "/Materials"));
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                material = new Material(shader);
                AssetDatabase.CreateAsset(material, path);
            }
            else
            {
                material.shader = shader;
            }

            var tiling = new Vector2(entry.tiling[0], entry.tiling[1]);
            switch (pipeline)
            {
                case "URP":
                    material.SetTexture("_BaseMap", baseMap);
                    material.SetColor("_BaseColor", Color.white);
                    material.SetTexture("_BumpMap", normalMap);
                    material.SetTexture("_MetallicGlossMap", maskMap);
                    material.SetFloat("_Smoothness", 1f);
                    material.EnableKeyword("_NORMALMAP");
                    material.EnableKeyword("_METALLICSPECGLOSSMAP");
                    material.SetTextureScale("_BaseMap", tiling);
                    material.SetFloat("_Surface", 0f);
                    if (entry.alphaClip)
                    {
                        material.SetFloat("_AlphaClip", 1f);
                        material.SetFloat("_Cutoff", entry.cutoff);
                        material.EnableKeyword("_ALPHATEST_ON");
                        // Alpha-to-coverage off: URP sharpens alpha around the cutoff under A2C, which thinned the twine
                        // by ~40 % at every distance in the coverage study.
                        material.SetFloat("_AlphaToMask", 0f);
                        material.SetOverrideTag("RenderType", "TransparentCutout");
                        material.renderQueue = (int)RenderQueue.AlphaTest;
                    }
                    else
                    {
                        material.SetFloat("_AlphaClip", 0f);
                        material.DisableKeyword("_ALPHATEST_ON");
                        material.SetFloat("_AlphaToMask", 0f);
                        material.SetOverrideTag("RenderType", "Opaque");
                        material.renderQueue = (int)RenderQueue.Geometry;
                    }

                    material.SetFloat("_Cull", entry.doubleSided ? (float)CullMode.Off : (float)CullMode.Back);
                    break;
                case "HDRP":
                    material.SetTexture("_BaseColorMap", baseMap);
                    material.SetTexture("_NormalMap", normalMap);
                    material.SetTexture("_MaskMap", maskMap);
                    material.EnableKeyword("_NORMALMAP");
                    material.EnableKeyword("_MASKMAP");
                    material.SetTextureScale("_BaseColorMap", tiling);
                    if (entry.alphaClip)
                    {
                        material.SetFloat("_AlphaCutoffEnable", 1f);
                        material.SetFloat("_AlphaCutoff", entry.cutoff);
                        material.SetFloat("_DoubleSidedEnable", 1f);
                        material.EnableKeyword("_ALPHATEST_ON");
                        material.EnableKeyword("_DOUBLESIDED_ON");
                    }

                    break;
                default:
                    material.SetTexture("_MainTex", baseMap);
                    material.SetTexture("_BumpMap", normalMap);
                    material.SetTexture("_MetallicGlossMap", maskMap);
                    material.SetFloat("_GlossMapScale", 1f);
                    material.EnableKeyword("_NORMALMAP");
                    material.EnableKeyword("_METALLICGLOSSMAP");
                    material.SetTextureScale("_MainTex", tiling);
                    if (entry.alphaClip)
                    {
                        // Built-in Standard cutout: one-sided (Standard has no cull switch); URP is the supported target.
                        material.SetFloat("_Mode", 1f);
                        material.SetFloat("_Cutoff", entry.cutoff);
                        material.EnableKeyword("_ALPHATEST_ON");
                        material.SetOverrideTag("RenderType", "TransparentCutout");
                        material.renderQueue = (int)RenderQueue.AlphaTest;
                    }

                    break;
            }

            EditorUtility.SetDirty(material);
            return material;
        }

        /// <summary>
        /// Netting for the far LODs: alpha-blended, so its opacity is the twine's real coverage (plain box-filtered mips hold
        /// exactly that). One uniform colour, so the blend order inside the bag barely shows; no shadow (the importer turns
        /// it off on those LODs). Only built for URP; other pipelines keep the clipped netting on every LOD.
        /// </summary>
        private static Material CreateFarNetting(string folder, MaterialEntry entry, Shader shader, string pipeline)
        {
            if (pipeline != "URP")
            {
                return null;
            }

            var path = folder + "/Materials/NT_Net_Far.mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                material = new Material(shader);
                AssetDatabase.CreateAsset(material, path);
            }
            else
            {
                material.shader = shader;
            }

            material.SetTexture("_BaseMap", AssetDatabase.LoadAssetAtPath<Texture2D>(folder + "/" + entry.baseMap));
            material.SetColor("_BaseColor", Color.white);
            material.SetTexture("_BumpMap", AssetDatabase.LoadAssetAtPath<Texture2D>(folder + "/" + entry.normalMap));
            material.SetTexture("_MetallicGlossMap", AssetDatabase.LoadAssetAtPath<Texture2D>(folder + "/" + entry.maskMap));
            material.SetFloat("_Smoothness", 1f);
            material.EnableKeyword("_NORMALMAP");
            material.EnableKeyword("_METALLICSPECGLOSSMAP");
            material.SetTextureScale("_BaseMap", new Vector2(entry.tiling[0], entry.tiling[1]));
            material.SetFloat("_Surface", 1f);
            material.SetFloat("_Blend", 0f);
            material.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            material.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            material.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            material.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
            material.SetFloat("_ZWrite", 0f);
            // Highlights scale with the twine's coverage. URP's default "preserve specular" adds them at full strength
            // whatever the alpha, which made the netting a glossy grey sheet (playtest 2026-11-01).
            material.SetFloat("_BlendModePreserveSpecular", 0f);
            material.DisableKeyword("_ALPHAPREMULTIPLY_ON");
            material.SetFloat("_AlphaClip", 0f);
            material.SetFloat("_AlphaToMask", 0f);
            material.SetFloat("_Cull", (float)CullMode.Off);
            material.DisableKeyword("_ALPHATEST_ON");
            material.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            material.SetOverrideTag("RenderType", "Transparent");
            material.renderQueue = (int)RenderQueue.Transparent;
            material.SetShaderPassEnabled("ShadowCaster", false);
            EditorUtility.SetDirty(material);
            return material;
        }

        private enum TextureKind
        {
            Colour,
            ClippedColour,
            Normal,
            Data,
        }

        private static Texture2D Texture(string path, TextureKind kind, float cutoff)
        {
            var importer = (TextureImporter)AssetImporter.GetAtPath(path);
            if (importer == null)
            {
                throw new FileNotFoundException("Texture missing from the export folder", path);
            }

            importer.textureType = kind == TextureKind.Normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
            importer.sRGBTexture = kind == TextureKind.Colour || kind == TextureKind.ClippedColour;
            importer.alphaSource = kind == TextureKind.Data || kind == TextureKind.ClippedColour
                ? TextureImporterAlphaSource.FromInput
                : TextureImporterAlphaSource.None;
            // Netting PNG: the source for NetCoverageMips, which the material uses. Unity's own coverage preservation is
            // off because it turns distant netting solid. Twine colour bleeds into the holes so filtered edges stay clean.
            importer.alphaIsTransparency = kind == TextureKind.ClippedColour;
            importer.mipMapsPreserveCoverage = false;
            importer.alphaTestReferenceValue = kind == TextureKind.ClippedColour ? cutoff : 0.5f;
            importer.wrapMode = TextureWrapMode.Repeat;
            importer.mipmapEnabled = true;
            importer.anisoLevel = 8;
            importer.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }
    }
}
