using System;
using UnityEngine;

namespace Carp.NetStudio
{
    /// <summary>
    /// The data a Net Studio prefab carries for its consumers: named markers, the mouth polygon and plane, and three display
    /// controls (scooping and lying poses, wetness, a disassembled layout). Filled in by the importer from net_manifest.json.
    /// This is an adapter surface, not gameplay: it never catches a fish, never simulates cloth or water, and has no
    /// colliders except an optional pickup capsule the importer adds when the preset asks for one.
    /// </summary>
    [ExecuteAlways]
    [DisallowMultipleComponent]
    public sealed class NetStudioNet : MonoBehaviour
    {
        [Serializable]
        public sealed class Marker
        {
            public string name;
            public Transform transform;
        }

        [Serializable]
        public sealed class Section
        {
            public string name;
            public Transform[] objects;
            public Vector3 assembled;
            public Vector3 disassembled;
        }

        [Serializable]
        public sealed class WetMaterial
        {
            public string name;
            public float wetTint = 1f;
            public float wetSmoothness = 1f;
            public float smoothnessCap = 1f;
        }

        public string netId;
        [Tooltip("Mouth opening along the arms and cord, net-local, clockwise seen from +Y.")]
        public Vector3[] mouthPolygon;
        public Vector3 mouthNormal = Vector3.up;
        public Vector3 mouthCentre;
        public Marker[] markers;
        public SkinnedMeshRenderer[] bagRenderers;
        public string blendShape = "Scooping";
        public string lyingBlendShape = "Lying";
        [Tooltip("Net-local height of the ground when the net lies flat (lying = 1): under the spreader's rear boss and the butt cap.")]
        public float lyingGroundY;
        public Section[] sections;
        public WetMaterial[] wetMaterials;
        public Renderer[] wetRenderers;

        [Tooltip("Keep the LOD hand-over distances the studio chose (LOD0 only close up) whatever QualitySettings.lodBias is.")]
        public bool compensateLodBias = true;
        [HideInInspector] public float lodSizeAtBiasOne;

        [Range(0f, 1f)] public float scoop;
        [Tooltip("The net laid flat on the ground, its bag collapsed (display pose; the frame stays where it is).")]
        [Range(0f, 1f)] public float lying;
        [Range(0f, 1f)] public float wetness;
        [Tooltip("Display layout only (sections side by side, head off). Never a gameplay deployment; markers assume the assembled net.")]
        public bool disassembled;

        private MaterialPropertyBlock _block;
        private float _appliedScoop = -1f;
        private float _appliedLying = -1f;
        private float _appliedWetness = -1f;
        private bool? _appliedLayout;
        private float _appliedBias = -1f;

        public void SetScoop(float weight)
        {
            scoop = Mathf.Clamp01(weight);
            Apply();
        }

        public void SetLying(float weight)
        {
            lying = Mathf.Clamp01(weight);
            Apply();
        }

        public void SetWetness(float value)
        {
            wetness = Mathf.Clamp01(value);
            Apply();
        }

        public void SetDisassembled(bool apart)
        {
            disassembled = apart;
            Apply();
        }

        /// <summary>A marker's transform by name (Marker_Spreader, Marker_CornerLeft, Marker_GripRear, ...), or null.</summary>
        public Transform FindMarker(string markerName)
        {
            if (markers == null)
            {
                return null;
            }

            foreach (var m in markers)
            {
                if (m != null && m.name == markerName)
                {
                    return m.transform;
                }
            }

            return null;
        }

        /// <summary>The world point lies over (or under) the mouth opening, projected along the mouth normal.</summary>
        public bool IsOverMouth(Vector3 world)
        {
            return NetMouth.ContainsXZ(mouthPolygon, transform.InverseTransformPoint(world));
        }

        /// <summary>
        /// A path from a to b (world) passes through the mouth's plane inside the opening. Metadata only: the game's
        /// landing rules decide what that means.
        /// </summary>
        public bool SegmentCrossesMouth(Vector3 worldA, Vector3 worldB, out Vector3 worldCrossing)
        {
            var hit = NetMouth.SegmentCrosses(mouthPolygon, mouthCentre.y, transform.InverseTransformPoint(worldA),
                transform.InverseTransformPoint(worldB), out var local);
            worldCrossing = transform.TransformPoint(local);
            return hit;
        }

        private void OnEnable()
        {
            _appliedScoop = -1f;
            _appliedLying = -1f;
            _appliedWetness = -1f;
            _appliedLayout = null;
            Apply();
        }

        private void OnValidate()
        {
            Apply();
        }

        private void Update()
        {
            if (!Mathf.Approximately(scoop, _appliedScoop) || !Mathf.Approximately(lying, _appliedLying)
                || !Mathf.Approximately(wetness, _appliedWetness) || _appliedLayout != disassembled
                || !Mathf.Approximately(QualitySettings.lodBias, _appliedBias))
            {
                Apply();
            }
        }

        private void Apply()
        {
            ApplyLodBias();
            if (bagRenderers != null)
            {
                foreach (var bag in bagRenderers)
                {
                    if (bag == null || bag.sharedMesh == null)
                    {
                        continue;
                    }

                    var index = bag.sharedMesh.GetBlendShapeIndex(blendShape);
                    if (index >= 0)
                    {
                        bag.SetBlendShapeWeight(index, scoop * 100f);
                    }

                    var lyingIndex = bag.sharedMesh.GetBlendShapeIndex(lyingBlendShape);
                    if (lyingIndex >= 0)
                    {
                        bag.SetBlendShapeWeight(lyingIndex, lying * 100f);
                    }
                }
            }

            ApplyWetness();
            if (sections != null)
            {
                foreach (var s in sections)
                {
                    if (s?.objects == null)
                    {
                        continue;
                    }

                    foreach (var t in s.objects)
                    {
                        if (t != null)
                        {
                            t.localPosition = disassembled ? s.disassembled : s.assembled;
                        }
                    }
                }
            }

            _appliedScoop = scoop;
            _appliedLying = lying;
            _appliedWetness = wetness;
            _appliedLayout = disassembled;
        }

        /// <summary>
        /// The netting changes material between LOD0 (clipped, holes resolved) and LOD1 (blended haze); a lodBias of 2 would
        /// keep the clipped netting out to twice the distance, where its twine falls under a pixel and thins out.
        /// </summary>
        private void ApplyLodBias()
        {
            _appliedBias = QualitySettings.lodBias;
            if (!compensateLodBias || lodSizeAtBiasOne <= 0f || !TryGetComponent<LODGroup>(out var group))
            {
                return;
            }

            group.size = lodSizeAtBiasOne / Mathf.Max(0.01f, QualitySettings.lodBias);
        }

        private void ApplyWetness()
        {
            if (wetRenderers == null || wetMaterials == null)
            {
                return;
            }

            _block ??= new MaterialPropertyBlock();
            foreach (var r in wetRenderers)
            {
                if (r == null)
                {
                    continue;
                }

                var mats = r.sharedMaterials;
                for (var i = 0; i < mats.Length; i++)
                {
                    var wet = Find(mats[i] == null ? null : mats[i].name);
                    r.GetPropertyBlock(_block, i);
                    if (wet == null || wetness <= 0f)
                    {
                        _block.Clear();
                    }
                    else
                    {
                        var tint = Mathf.Lerp(1f, wet.wetTint, wetness);
                        var smooth = Mathf.Min(Mathf.Lerp(1f, wet.wetSmoothness, wetness), wet.smoothnessCap);
                        var colour = new Color(tint, tint, tint, 1f);
                        _block.SetColor("_BaseColor", colour);
                        _block.SetColor("_Color", colour);
                        _block.SetFloat("_Smoothness", smooth);
                        _block.SetFloat("_GlossMapScale", smooth);
                    }

                    r.SetPropertyBlock(_block, i);
                }
            }
        }

        private WetMaterial Find(string materialName)
        {
            if (materialName == null)
            {
                return null;
            }

            foreach (var w in wetMaterials)
            {
                if (w != null && w.name == materialName)
                {
                    return w;
                }
            }

            return null;
        }

        /// <summary>The wetness block's base tint on a renderer's material slot (for tests and tools).</summary>
        public Color AppliedTint(Renderer r, int materialIndex)
        {
            _block ??= new MaterialPropertyBlock();
            r.GetPropertyBlock(_block, materialIndex);
            return _block.isEmpty ? Color.white : _block.GetColor("_BaseColor");
        }
    }
}
