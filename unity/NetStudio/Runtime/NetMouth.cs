using UnityEngine;

namespace Carp.NetStudio
{
    /// <summary>
    /// Geometry on a net's recorded mouth polygon (local space of the net, mouth plane normal +Y in the neutral pose).
    /// Metadata helpers for later fish-over-mouth tests: they decide nothing about catching a fish.
    /// </summary>
    public static class NetMouth
    {
        /// <summary>Point inside the polygon, both projected onto the XZ plane (local).</summary>
        public static bool ContainsXZ(Vector3[] polygon, Vector3 point)
        {
            if (polygon == null || polygon.Length < 3)
            {
                return false;
            }

            var inside = false;
            for (int i = 0, j = polygon.Length - 1; i < polygon.Length; j = i++)
            {
                var a = polygon[i];
                var b = polygon[j];
                if ((a.z > point.z) != (b.z > point.z) && point.x < (b.x - a.x) * (point.z - a.z) / (b.z - a.z) + a.x)
                {
                    inside = !inside;
                }
            }

            return inside;
        }

        /// <summary>
        /// The segment from a to b (local) passes through the mouth plane (height planeY) inside the polygon. Returns the
        /// crossing point in <paramref name="crossing"/>.
        /// </summary>
        public static bool SegmentCrosses(Vector3[] polygon, float planeY, Vector3 a, Vector3 b, out Vector3 crossing)
        {
            crossing = Vector3.zero;
            var da = a.y - planeY;
            var db = b.y - planeY;
            if (da * db > 0f || Mathf.Approximately(da, db))
            {
                return false;
            }

            crossing = Vector3.Lerp(a, b, da / (da - db));
            return ContainsXZ(polygon, crossing);
        }
    }
}
