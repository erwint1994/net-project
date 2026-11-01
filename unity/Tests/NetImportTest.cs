using System;
using System.IO;
using System.Linq;
using Carp.NetStudio;
using Carp.NetStudio.Editor;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

/// <summary>
/// Runs in the throwaway project (_unitytest), never in the game: imports a Net Studio export and checks the prefab.
/// tools\test_unity_import.ps1 -Net &lt;id&gt; [-Shots &lt;folder&gt;]
/// </summary>
public static class NetImportTest
{
    static int failures;

    static string Arg(string[] args, string name)
    {
        var i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    static void Check(bool ok, string what)
    {
        Debug.Log((ok ? "[NetTest] PASS " : "[NetTest] FAIL ") + what);
        if (!ok) failures++;
    }

    [Serializable] class Named { public string name; public float[] position; }
    [Serializable] class Depth { public float deployed_m; public float scooping_m; }
    [Serializable] class Head { public Depth depth; }
    [Serializable] class Derived { public float overall_length_m; public float mouth_width_m; }
    [Serializable] class Dims { public Derived derived; }
    [Serializable] class UnityPart { public Named[] markers; public Named[] mouthPolygon; }
    [Serializable] class Manifest { public string id; public Head head; public Dims dimensions; public UnityPart unity; }

    static Vector3 V(float[] p) => new Vector3(p[0], p[1], p[2]);

    public static void Run()
    {
        try
        {
            RunChecks();
        }
        catch (Exception e)
        {
            Debug.LogException(e);
            failures++;
        }

        Debug.Log(failures == 0 ? "[NetTest] ALL PASSED" : "[NetTest] FAILURES: " + failures);
        EditorApplication.Exit(failures == 0 ? 0 : 1);
    }

    static void RunChecks()
    {
        var args = Environment.GetCommandLineArgs();
        var export = Arg(args, "-netExport");
        var urp = Arg(args, "-pipeline") != "builtin";
        if (urp)
        {
            var type = Type.GetType("UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset, Unity.RenderPipelines.Universal.Runtime");
            var rendererType = Type.GetType("UnityEngine.Rendering.Universal.UniversalRendererData, Unity.RenderPipelines.Universal.Runtime");
            var renderer = ScriptableObject.CreateInstance(rendererType);
            AssetDatabase.CreateAsset(renderer, "Assets/TestURP_Renderer.asset");
            var asset = (RenderPipelineAsset)type.GetMethods().First(m => m.Name == "Create" && m.GetParameters().Length == 1)
                                                 .Invoke(null, new object[] { renderer });
            // MSAA off, as in every URP asset of the carp game (m_MSAA: 1 in Assets/Settings, read 2026-11-01).
            type.GetProperty("msaaSampleCount").SetValue(asset, 1);
            type.GetProperty("shadowDistance")?.SetValue(asset, 30f);
            AssetDatabase.CreateAsset(asset, "Assets/TestURP.asset");
            GraphicsSettings.defaultRenderPipeline = asset;
        }

        Debug.Log("[NetTest] pipeline: " + (GraphicsSettings.currentRenderPipeline == null ? "Built-in" : GraphicsSettings.currentRenderPipeline.GetType().Name));
        var manifest = JsonUtility.FromJson<Manifest>(File.ReadAllText(Path.Combine(export, "net_manifest.json")));

        var prefabPath = NetStudioImporter.ImportExportFolder(export);
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
        Check(prefab != null, "prefab saved at " + prefabPath);
        Check(prefabPath == "Assets/NetStudio/Nets/" + manifest.id + "/" + manifest.id + ".prefab", "prefab under Assets/NetStudio/Nets/<id>/");
        Check(prefab.transform.localScale == Vector3.one && prefab.transform.position == Vector3.zero, "prefab root at origin, scale 1");

        // Reimport: same prefab and material assets (stable identities).
        var folder = Path.GetDirectoryName(prefabPath).Replace('\\', '/');
        var guidPrefab = AssetDatabase.AssetPathToGUID(prefabPath);
        var guidNet = AssetDatabase.AssetPathToGUID(folder + "/Materials/NT_Net.mat");
        NetStudioImporter.ImportExportFolder(export);
        Check(AssetDatabase.AssetPathToGUID(prefabPath) == guidPrefab && AssetDatabase.AssetPathToGUID(folder + "/Materials/NT_Net.mat") == guidNet,
            "reimport keeps the prefab and material GUIDs");
        prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);

        var lod = prefab.GetComponent<LODGroup>();
        Check(lod != null && lod.lodCount == 3, "LODGroup with 3 LODs");
        var lods = lod.GetLODs();
        foreach (var l in lods)
            Check(l.renderers.Length >= 3 && l.renderers.All(r => r != null), $"LOD at {l.screenRelativeTransitionHeight:0.####} has {l.renderers.Length} renderers");

        var renderers = prefab.GetComponentsInChildren<Renderer>(true);
        var mats = renderers.SelectMany(r => r.sharedMaterials).Distinct().ToList();
        var expectShader = urp ? "Universal Render Pipeline/Lit" : "Standard";
        Check(mats.All(m => m != null && m.shader.name == expectShader), $"{mats.Count} materials use {expectShader}");
        var mainTex = urp ? "_BaseMap" : "_MainTex";
        Check(mats.All(m => m.GetTexture(mainTex) != null && m.GetTexture("_BumpMap") != null && m.GetTexture("_MetallicGlossMap") != null),
            "every material has base, normal and mask maps");
        var net = mats.First(m => m.name == "NT_Net");
        Check(net.IsKeywordEnabled("_ALPHATEST_ON") && Mathf.Approximately(net.GetFloat("_Cutoff"), 0.5f), "netting is alpha-clipped at 0.5");
        Check(net.renderQueue == (int)RenderQueue.AlphaTest, $"netting renders in the alpha-test queue, not transparent ({net.renderQueue}): no sorting");
        if (urp)
        {
            Check(net.GetFloat("_AlphaClip") == 1f && net.GetFloat("_Surface") == 0f, "netting is opaque surface + alpha clip");
            Check(net.GetFloat("_Cull") == (float)CullMode.Off, "netting is double-sided (cull off)");
            Check(net.GetFloat("_AlphaToMask") == 0f, "close-up netting: plain alpha test (A2C thins the twine)");
            var bagsAll = prefab.GetComponent<NetStudioNet>().bagRenderers;
            var far = bagsAll[1].sharedMaterials.FirstOrDefault(m => m.name == "NT_Net_Far");
            Check(far != null && bagsAll[2].sharedMaterials.Contains(far) && !bagsAll[0].sharedMaterials.Contains(far),
                "LOD1 and LOD2 bags use the far netting, LOD0 the clipped netting");
            Check(far != null && far.renderQueue == (int)RenderQueue.Transparent && far.GetFloat("_ZWrite") == 0f && far.GetFloat("_Cull") == 0f
                  && !far.GetShaderPassEnabled("ShadowCaster"), "far netting: alpha-blended, double-sided, no shadow pass");
        }
        Check(mats.Where(m => !m.name.StartsWith("NT_Net")).All(m => m.renderQueue == (int)RenderQueue.Geometry), "hardware materials are opaque");
        var netMap = (Texture2D)net.GetTexture(mainTex);
        Check(AssetDatabase.GetAssetPath(netMap).EndsWith("_CoverageMips.asset") && netMap.mipmapCount > 8,
            $"netting uses the coverage-keeping mip chain ({AssetDatabase.GetAssetPath(netMap)}, {netMap.mipmapCount} mips)");
        Check(Mathf.Abs(net.GetTextureScale(mainTex).x - 1f / 0.0803f) < 0.2f, "netting tiling in metres: " + net.GetTextureScale(mainTex));

        // Bags: skinned, with the blendshape, shadows per LOD.
        var comp = prefab.GetComponent<NetStudioNet>();
        Check(comp != null && comp.bagRenderers.Length == 3, "NetStudioNet with 3 bag renderers");
        Check(comp.bagRenderers.All(b => b.sharedMesh.GetBlendShapeIndex("Scooping") >= 0), "every LOD's bag has the Scooping blendshape");
        Check(comp.bagRenderers[0].shadowCastingMode == ShadowCastingMode.On && comp.bagRenderers[1].shadowCastingMode == ShadowCastingMode.Off
              && comp.bagRenderers[2].shadowCastingMode == ShadowCastingMode.Off, "bag casts clipped shadows at LOD0 only");

        // Frame, scale and markers against the manifest.
        var worst = 0f;
        foreach (var m in manifest.unity.markers)
        {
            var t = comp.FindMarker(m.name);
            Check(t != null, "marker " + m.name);
            if (t != null) worst = Mathf.Max(worst, (prefab.transform.InverseTransformPoint(t.position) - V(m.position)).magnitude);
        }
        Check(worst < 0.001f, $"markers where the manifest says (worst {worst * 1000f:0.00} mm)");
        Vector3 M(string n) => prefab.transform.InverseTransformPoint(comp.FindMarker(n).position);
        Check(M("Marker_ButtCap").magnitude < 0.001f, "origin at the butt cap");
        Check(M("Marker_Spreader").z > 1.5f && Mathf.Abs(M("Marker_Spreader").x) < 0.001f, "handle runs along +Z to the spreader " + M("Marker_Spreader"));
        Check(M("Marker_CornerRight").x > 0.5f && M("Marker_CornerLeft").x < -0.5f, "right corner on +X, left on -X");
        Check(M("Marker_MouthCentre").z > M("Marker_Spreader").z, "mouth forward of the spreader (+Z)");
        Check(M("Marker_BagBottom").y < -0.5f, "bag hangs towards -Y");
        var width = (M("Marker_CornerRight") - M("Marker_CornerLeft")).magnitude;
        Check(Mathf.Abs(width - manifest.dimensions.derived.mouth_width_m) < 0.002f, $"mouth width {width:0.000} m");
        var b0 = new Bounds();
        var first = true;
        foreach (var r in lods[0].renderers)
        {
            var mesh = r is SkinnedMeshRenderer s ? s.sharedMesh : r.GetComponent<MeshFilter>().sharedMesh;
            foreach (var v in mesh.vertices)
            {
                var p = prefab.transform.InverseTransformPoint(r.transform.TransformPoint(v));
                if (first) { b0 = new Bounds(p, Vector3.zero); first = false; } else b0.Encapsulate(p);
            }
        }
        var frameEnd = lods[0].renderers.Where(r => !(r is SkinnedMeshRenderer)).Max(r =>
            r.GetComponent<MeshFilter>().sharedMesh.vertices.Max(v => prefab.transform.InverseTransformPoint(r.transform.TransformPoint(v)).z));
        Check(Mathf.Abs(b0.min.z) < 0.003f && Mathf.Abs(frameEnd - manifest.dimensions.derived.overall_length_m) < 0.02f,
            $"LOD0 frame runs 0..{frameEnd:0.000} m along Z (overall {manifest.dimensions.derived.overall_length_m} m to the cord)");
        Debug.Log($"[NetTest] the hanging bag reaches {b0.max.z - manifest.dimensions.derived.overall_length_m:0.000} m forward of the cord");
        Check(Mathf.Abs(-b0.min.y - manifest.head.depth.deployed_m) < 0.03f, $"LOD0 bag depth {-b0.min.y:0.000} m (manifest {manifest.head.depth.deployed_m})");

        // Scene checks: pose, wetness, display layout, mock fish.
        EditorSceneManager.NewScene(NewSceneSetup.EmptyScene);
        var inst = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
        var n = inst.GetComponent<NetStudioNet>();
        float BagLow(SkinnedMeshRenderer s)
        {
            var baked = new Mesh();
            s.BakeMesh(baked, true);
            var low = baked.vertices.Min(v => inst.transform.InverseTransformPoint(s.transform.TransformPoint(v)).y);
            UnityEngine.Object.DestroyImmediate(baked);
            return low;
        }
        n.SetScoop(0f);
        var dep = BagLow(n.bagRenderers[0]);
        n.SetScoop(1f);
        var sc = BagLow(n.bagRenderers[0]);
        Check(Mathf.Abs(-sc - manifest.head.depth.scooping_m) < 0.03f && sc < dep, $"scooping pose: bag {-dep:0.000} m -> {-sc:0.000} m deep");
        n.SetScoop(0f);
        n.SetLying(1f);
        float BagHigh(SkinnedMeshRenderer s)
        {
            var baked = new Mesh();
            s.BakeMesh(baked, true);
            var high = baked.vertices.Max(v => inst.transform.InverseTransformPoint(s.transform.TransformPoint(v)).y);
            UnityEngine.Object.DestroyImmediate(baked);
            return high;
        }
        var lyLow = BagLow(n.bagRenderers[0]);
        var lyHigh = BagHigh(n.bagRenderers[0]);
        Check(n.lyingGroundY < -0.005f && lyLow >= n.lyingGroundY - 0.001f && lyHigh - n.lyingGroundY < 0.07f,
            $"lying pose: bag flat on the ground ({(lyLow - n.lyingGroundY) * 1000f:0}-{(lyHigh - n.lyingGroundY) * 1000f:0} mm above it)");
        n.SetLying(0f);
        Check(Mathf.Abs(BagLow(n.bagRenderers[0]) - dep) < 0.005f, "back to the deployed pose");
        n.SetWetness(1f);
        var bagR = n.bagRenderers[0];
        var tint = n.AppliedTint(bagR, Array.FindIndex(bagR.sharedMaterials, m => m.name == "NT_Net"));
        Check(tint.r < 0.95f, "wetness darkens the netting (tint " + tint.r.ToString("0.00") + ")");
        n.SetWetness(0f);
        Check(n.AppliedTint(bagR, 0) == Color.white, "dry clears the wetness block");
        var section = n.sections.First(s => s.name == "Head");
        var before = section.objects[0].localPosition;
        n.SetDisassembled(true);
        var apart = section.objects[0].localPosition;
        n.SetDisassembled(false);
        Check((apart - before).magnitude > 0.1f && (section.objects[0].localPosition - before).magnitude < 1e-5f,
            "disassembled display moves the head and puts it back");

        // A mock fish crossing the recorded mouth polygon, with the net placed somewhere in the world (metadata demo only).
        inst.transform.SetPositionAndRotation(new Vector3(10f, 0.5f, -4f), Quaternion.Euler(0f, 30f, 0f));
        var centre = inst.transform.TransformPoint(n.mouthCentre);
        var down = inst.transform.up;
        Check(n.SegmentCrossesMouth(centre + down * 0.3f, centre - down * 0.3f, out var hit) && (hit - centre).magnitude < 0.01f,
            "mock fish dropping through the mouth centre crosses the mouth");
        var corner = inst.transform.TransformPoint(M("Marker_CornerRight"));
        var outside = corner + inst.transform.right * 0.2f;
        Check(!n.SegmentCrossesMouth(outside + down * 0.3f, outside - down * 0.3f, out _), "a path just outside the corner does not");
        var spreader = inst.transform.TransformPoint(M("Marker_Spreader"));
        var behind = spreader - inst.transform.forward * 0.15f;
        Check(!n.SegmentCrossesMouth(behind + down * 0.3f, behind - down * 0.3f, out _), "a path behind the spreader does not");
        Check(!n.SegmentCrossesMouth(centre + down * 0.3f, centre + down * 0.1f, out _), "a path that stays above the mouth does not");
        Check(n.IsOverMouth(centre + down * 0.5f) && !n.IsOverMouth(outside), "IsOverMouth agrees");
        inst.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);

        // Hand-over distance at a 60 deg FOV with the project's lodBias, after NetStudioNet's compensation.
        var g = inst.GetComponent<LODGroup>();
        foreach (var l in g.GetLODs())
            Debug.Log($"[NetTest] LOD hand-over at {g.size * QualitySettings.lodBias / (2f * Mathf.Tan(30f * Mathf.Deg2Rad) * l.screenRelativeTransitionHeight):0.0} m "
                      + $"(60 deg FOV, lodBias {QualitySettings.lodBias})");
        var d0 = g.size * QualitySettings.lodBias / (2f * Mathf.Tan(30f * Mathf.Deg2Rad) * g.GetLODs()[0].screenRelativeTransitionHeight);
        Check(Mathf.Abs(d0 - 2f) < 0.05f, $"clipped close-up netting hands over at 2 m whatever the lodBias ({d0:0.00} m at bias {QualitySettings.lodBias})");

        var shots = Arg(args, "-shots");
        if (urp)
            CoverageStudy(inst, shots);
        if (urp && shots != null)
            Shots(inst, n, shots, manifest);
    }

    /// <summary>
    /// How much of the bag's silhouette the twine covers on screen from 0.8 to 25 m, for three mip chains (the importer's
    /// coverage-keeping one, Unity's mipMapsPreserveCoverage, plain mips), with and without alpha-to-coverage. One layer
    /// of twine is about 28 %; looking through the bag's two walls, about 48 %. The importer's chain must stay in range.
    /// </summary>
    static void CoverageStudy(GameObject inst, string folder)
    {
        var bag = inst.GetComponent<NetStudioNet>().bagRenderers[0];
        var netIndex = Array.FindIndex(bag.sharedMaterials, m => m.name == "NT_Net");
        var net = bag.sharedMaterials[netIndex];
        var studio = (Texture2D)net.GetTexture("_BaseMap");
        var pngPath = AssetDatabase.GetAssetPath(studio).Replace("_CoverageMips.asset", ".png");
        var solid = Flat(Color.black, 0f);
        var cam = new GameObject("StudyCam").AddComponent<Camera>();
        cam.fieldOfView = 60f;
        cam.nearClipPlane = 0.05f;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Color.white;
        var light = new GameObject("StudySun").AddComponent<Light>();
        light.type = LightType.Directional;
        light.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
        var rt = new RenderTexture(960, 540, 24) { antiAliasing = 1 };
        cam.targetTexture = rt;
        var target = new Vector3(0.25f, -0.35f, 2.2f);
        var dir = new Vector3(0.45f, -1f, -0.25f).normalized;
        inst.GetComponent<LODGroup>().ForceLOD(0);
        var others = inst.GetComponentsInChildren<Renderer>(true).Where(r => r != bag).ToArray();
        foreach (var r in others) r.enabled = false;

        float Covered(Texture2D t, Texture2D mask)
        {
            var p = t.GetPixels();
            var m = mask.GetPixels();
            // Optical coverage: how much the white background is darkened inside the bag's silhouette (partly covered
            // pixels count partly, as they look).
            var inside = 0;
            var dark = 0f;
            for (var i = 0; i < p.Length; i++)
            {
                if (m[i].r > 0.5f) continue;
                inside++;
                dark += Mathf.Clamp01(1f - p[i].r);
            }
            return inside == 0 ? 0f : dark / inside;
        }

        Texture2D Png(bool preserve)
        {
            var ti = (TextureImporter)AssetImporter.GetAtPath(pngPath);
            ti.mipMapsPreserveCoverage = preserve;
            ti.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Texture2D>(pngPath);
        }

        var variants = new (string name, Func<Texture2D> tex)[] { ("net studio mips", () => studio), ("unity preserve", () => Png(true)), ("plain mips", () => Png(false)) };
        foreach (var (name, make) in variants)
        {
            net.SetTexture("_BaseMap", make());
            foreach (var a2c in new[] { true, false })
            {
                net.SetFloat("_AlphaToMask", a2c ? 1f : 0f);
                var row = $"[NetTest] coverage {name,-15} a2c {(a2c ? "on " : "off")}:";
                var worst = 1f;
                var most = 0f;
                foreach (var d in new[] { 0.8f, 3f, 6f, 12f, 25f })
                {
                    cam.transform.position = target + dir * d;
                    cam.transform.LookAt(target);
                    var mats = bag.sharedMaterials;
                    var solidMats = (Material[])mats.Clone();
                    solidMats[netIndex] = solid;
                    bag.sharedMaterials = solidMats;
                    var mask = Grab(cam, rt);
                    bag.sharedMaterials = mats;
                    var shot = Grab(cam, rt);
                    var c = Covered(shot, mask);
                    row += $" {d}m {c:P0}";
                    worst = Mathf.Min(worst, c);
                    most = Mathf.Max(most, c);
                    if (folder != null && d >= 3f && a2c)
                        File.WriteAllBytes(Path.Combine(folder, $"study_{name.Replace(' ', '_')}_{d:0}m.png"), shot.EncodeToPNG());
                    UnityEngine.Object.DestroyImmediate(mask);
                    UnityEngine.Object.DestroyImmediate(shot);
                }

                Debug.Log(row);
            }
        }

        Png(false);
        net.SetTexture("_BaseMap", studio);
        net.SetFloat("_AlphaToMask", 0f);

        // As shipped: LODGroup picks the LOD (clipped netting close up, blended haze further out).
        inst.GetComponent<LODGroup>().ForceLOD(-1);
        var shipped = "[NetTest] coverage as shipped (auto LOD):";
        var lo = 1f;
        var hi = 0f;
        var bags = inst.GetComponent<NetStudioNet>().bagRenderers;
        foreach (var b in bags) b.enabled = true;
        foreach (var d in new[] { 0.8f, 1.5f, 2.5f, 4f, 8f, 16f, 30f, 60f })
        {
            cam.transform.position = target + dir * d;
            cam.transform.LookAt(target);
            var saved = bags.Select(b => b.sharedMaterials).ToArray();
            foreach (var b in bags) b.sharedMaterials = b.sharedMaterials.Select(m => m != null && m.name.StartsWith("NT_Net") ? solid : m).ToArray();
            var mask = Grab(cam, rt);
            for (var i = 0; i < bags.Length; i++) bags[i].sharedMaterials = saved[i];
            var shot = Grab(cam, rt);
            var c = Covered(shot, mask);
            shipped += $" {d}m {c:P0}";
            lo = Mathf.Min(lo, c);
            hi = Mathf.Max(hi, c);
            if (folder != null)
                File.WriteAllBytes(Path.Combine(folder, $"shipped_{d:0}m.png"), shot.EncodeToPNG());
            UnityEngine.Object.DestroyImmediate(mask);
            UnityEngine.Object.DestroyImmediate(shot);
        }

        Debug.Log(shipped);
        Check(lo > 0.12f && hi < 0.8f, $"netting neither vanishes nor turns solid at any range ({lo:P0}-{hi:P0} of the bag, 0.8-60 m)");
        foreach (var r in others) r.enabled = true;
        inst.GetComponent<LODGroup>().ForceLOD(-1);
        UnityEngine.Object.DestroyImmediate(cam.gameObject);
        UnityEngine.Object.DestroyImmediate(light.gameObject);
        rt.Release();
    }

    static Material Flat(Color c, float smooth)
    {
        var m = new Material(Shader.Find("Universal Render Pipeline/Lit"));
        m.SetColor("_BaseColor", c);
        m.SetFloat("_Smoothness", smooth);
        return m;
    }

    static Texture2D Grab(Camera cam, RenderTexture rt)
    {
        cam.Render();
        RenderTexture.active = rt;
        var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
        tex.Apply();
        RenderTexture.active = null;
        return tex;
    }

    static float Differs(Texture2D a, Texture2D b)
    {
        var pa = a.GetPixels();
        var pb = b.GetPixels();
        var n = 0;
        for (var i = 0; i < pa.Length; i++)
            if (Mathf.Abs(pa[i].r - pb[i].r) + Mathf.Abs(pa[i].g - pb[i].g) + Mathf.Abs(pa[i].b - pb[i].b) > 0.03f) n++;
        return n / (float)pa.Length;
    }

    static void Shots(GameObject inst, NetStudioNet n, string folder, Manifest manifest)
    {
        Directory.CreateDirectory(folder);
        var sun = new GameObject("Sun").AddComponent<Light>();
        sun.type = LightType.Directional;
        sun.intensity = 1.6f;
        sun.shadows = LightShadows.Soft;
        sun.transform.rotation = Quaternion.Euler(62f, 200f, 0f);
        RenderSettings.ambientMode = AmbientMode.Trilight;
        RenderSettings.ambientSkyColor = new Color(0.55f, 0.62f, 0.72f);
        RenderSettings.ambientEquatorColor = new Color(0.38f, 0.4f, 0.36f);
        RenderSettings.ambientGroundColor = new Color(0.18f, 0.2f, 0.12f);
        var sky = new Color(0.62f, 0.72f, 0.84f);
        var bank = GameObject.CreatePrimitive(PrimitiveType.Plane);
        bank.transform.localScale = Vector3.one * 10f;
        bank.transform.position = new Vector3(0f, -1.3f, 1f);
        bank.GetComponent<Renderer>().sharedMaterial = Flat(new Color(0.2f, 0.26f, 0.1f), 0.1f);
        var water = GameObject.CreatePrimitive(PrimitiveType.Plane);
        water.transform.localScale = Vector3.one * 10f;
        water.transform.position = new Vector3(0f, -1.3f, 1f);
        water.GetComponent<Renderer>().sharedMaterial = Flat(new Color(0.04f, 0.07f, 0.06f), 0.85f);
        var cam = new GameObject("ShotCam").AddComponent<Camera>();
        cam.fieldOfView = 40f;
        cam.nearClipPlane = 0.05f;
        cam.farClipPlane = 200f;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = sky;
        var rt = new RenderTexture(960, 540, 24) { antiAliasing = 1 };
        cam.targetTexture = rt;
        var bagPoint = new Vector3(0.25f, -0.35f, 2.2f);
        var netRenderers = inst.GetComponentsInChildren<Renderer>(true);

        Texture2D Shot(string name, Vector3 dir, float dist, string backdrop, Vector3 target)
        {
            bank.SetActive(backdrop == "bank");
            water.SetActive(backdrop == "water");
            cam.transform.position = target + dir.normalized * dist;
            cam.transform.LookAt(target);
            var tex = Grab(cam, rt);
            File.WriteAllBytes(Path.Combine(folder, name + ".png"), tex.EncodeToPNG());
            return tex;
        }

        Texture2D Without(Func<Texture2D> shot)
        {
            inst.SetActive(false);
            var t = shot();
            inst.SetActive(true);
            return t;
        }

        // Near / mid / far against sky, water and bank: the net must stay visible (not vanish) at every range.
        foreach (var (backdrop, dir) in new[] { ("sky", new Vector3(0.45f, -1f, -0.25f)), ("water", new Vector3(0.4f, 0.85f, -0.3f)), ("bank", new Vector3(0.75f, 0.45f, -0.35f)) })
        {
            foreach (var d in new[] { 0.8f, 3f, 12f })
            {
                var name = backdrop + "_" + d.ToString("0.#", System.Globalization.CultureInfo.InvariantCulture) + "m";
                var with = Shot(name, dir, d, backdrop, bagPoint);
                var empty = Without(() => Shot(name + "_empty", dir, d, backdrop, bagPoint));
                var share = Differs(with, empty);
                Debug.Log($"[NetTest] shot {name}: net covers {share:P1} of the frame");
                Check(share > (d > 10f ? 0.0015f : 0.01f), $"net visible against {backdrop} at {d} m");
                File.Delete(Path.Combine(folder, name + "_empty.png"));
                UnityEngine.Object.DestroyImmediate(with);
                UnityEngine.Object.DestroyImmediate(empty);
            }
        }

        // Underside: straight up from below, against the sky (double-sided netting): how much of the bag's silhouette the
        // twine darkens, seen from underneath.
        var under = Shot("underside", Vector3.down, 2.5f, "sky", new Vector3(0f, -0.4f, 2.25f));
        var bags = n.bagRenderers;
        var black = Flat(Color.black, 0f);
        var keep = bags.Select(b => b.sharedMaterials).ToArray();
        foreach (var b in bags) b.sharedMaterials = b.sharedMaterials.Select(m => m != null && m.name.StartsWith("NT_Net") ? black : m).ToArray();
        var silhouette = Grab(cam, rt);
        for (var i = 0; i < bags.Length; i++) bags[i].sharedMaterials = keep[i];
        var underEmpty = Without(() => Grab(cam, rt));
        var pu = under.GetPixels();
        var ps = silhouette.GetPixels();
        var pb = underEmpty.GetPixels();
        float inBag = 0f, darker = 0f;
        for (var i = 0; i < pu.Length; i++)
        {
            if (Mathf.Abs(ps[i].r - pb[i].r) + Mathf.Abs(ps[i].g - pb[i].g) + Mathf.Abs(ps[i].b - pb[i].b) < 0.1f) continue;
            inBag++;
            var bg = 0.2126f * pb[i].r + 0.7152f * pb[i].g + 0.0722f * pb[i].b;
            var now = 0.2126f * pu[i].r + 0.7152f * pu[i].g + 0.0722f * pu[i].b;
            darker += Mathf.Clamp01(1f - now / Mathf.Max(bg, 1e-3f));
        }
        var underCover = inBag > 0 ? darker / inBag : 0f;
        Check(underCover > 0.12f && underCover < 0.8f, $"bag underside visible from below (twine covers {underCover:P0} of the bag's silhouette)");

        // Shadows: the net casts a clipped (speckled) shadow on the bank, seen top down with the net itself hidden.
        foreach (var r in netRenderers) r.shadowCastingMode = r.shadowCastingMode == ShadowCastingMode.Off ? ShadowCastingMode.Off : ShadowCastingMode.ShadowsOnly;
        sun.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
        var lodGroup = inst.GetComponent<LODGroup>();
        lodGroup.ForceLOD(0);
        cam.orthographic = true;
        cam.orthographicSize = 1.2f;
        bank.SetActive(true);
        water.SetActive(false);
        cam.transform.SetPositionAndRotation(new Vector3(0f, 5f, 2.25f), Quaternion.Euler(90f, 0f, 0f));
        var top = Grab(cam, rt);
        File.WriteAllBytes(Path.Combine(folder, "shadow_top.png"), top.EncodeToPNG());
        inst.SetActive(false);
        var topEmpty = Grab(cam, rt);
        inst.SetActive(true);
        // Inside the mouth's footprint on the ground (the sun is straight overhead): how much darker it is with the net.
        var poly = n.mouthPolygon;
        var halfW = cam.orthographicSize * cam.aspect;
        float sumWith = 0f, sumEmpty = 0f;
        var pw = top.GetPixels();
        var pe = topEmpty.GetPixels();
        for (var y = 0; y < rt.height; y++)
        {
            for (var x = 0; x < rt.width; x++)
            {
                var world = new Vector3(cam.transform.position.x + ((x + 0.5f) / rt.width - 0.5f) * 2f * halfW, 0f,
                    cam.transform.position.z + ((y + 0.5f) / rt.height - 0.5f) * 2f * cam.orthographicSize);
                if (!NetMouth.ContainsXZ(poly, world)) continue;
                var i = y * rt.width + x;
                sumWith += 0.2126f * pw[i].r + 0.7152f * pw[i].g + 0.0722f * pw[i].b;
                sumEmpty += 0.2126f * pe[i].r + 0.7152f * pe[i].g + 0.0722f * pe[i].b;
            }
        }
        var drop = sumEmpty > 0f ? 1f - sumWith / sumEmpty : 0f;
        Check(drop > 0.04f && drop < 0.7f, $"netting casts a partial (clipped) shadow: ground under the mouth {drop:P0} darker, not solid");
        foreach (var r in netRenderers) if (r.shadowCastingMode == ShadowCastingMode.ShadowsOnly) r.shadowCastingMode = ShadowCastingMode.On;
        lodGroup.ForceLOD(-1);
        cam.orthographic = false;
        sun.transform.rotation = Quaternion.Euler(50f, 200f, 0f);

        // Product shots: whole net, scooping pose, LOD2 forced.
        var whole = new Vector3(0f, -0.3f, 1.4f);
        Shot("whole_three_quarter", new Vector3(1.1f, 0.7f, -1f), 3.6f, "bank", whole);
        n.SetScoop(1f);
        Shot("scooping", new Vector3(1.1f, 0.7f, -1f), 3.6f, "bank", whole);
        n.SetScoop(0f);
        lodGroup.ForceLOD(2);
        Shot("lod2_forced", new Vector3(1.1f, 0.7f, -1f), 3.6f, "bank", whole);
        lodGroup.ForceLOD(-1);
        cam.targetTexture = null;
        UnityEngine.Object.DestroyImmediate(rt);
        Debug.Log("[NetTest] shots saved in " + folder);
    }
}
