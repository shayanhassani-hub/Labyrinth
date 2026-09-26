// CradleBuilder.cs - assembles Hero 01, the docking cradle, in the open scene.
//
// Menu:  Tools > Labyrinth > Build Cradle     (Build(), returns the report)
//        Tools > Labyrinth > Verify Cradle    (Verify(), standby + 0-100 deg hinge sweep)
// Code:  LabyrinthVR.EnvironmentTools.CradleBuilder.ApplyImportSettings() / FootprintReport()
//
// Source of truth: Documentation/HERO_SPEC.md section 3. Meshes come from
// Tools/Blender/heroes/cradle.py (hero export mode, EXPORT_CONTRACT.md).
//
//   HERO_Cradle (0, 0, 4.69), yaw 0
//     Base
//     Hinge_L (-0.13, 1.04, 0) -> Arm -> Pad
//     Hinge_R (+0.13, 1.04, 0) -> Arm -> Pad
//
// Outward: Hinge_L +Z rotation, Hinge_R -Z rotation (localEulerAngles.z = +/-deg).
// It replaces an existing HERO_Cradle, never saves the scene, one Undo step.
// No colliders and no motion scripts yet.

using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace LabyrinthVR.EnvironmentTools
{
    public static class CradleBuilder
    {
        const string Dir = "Assets/Environment/Heroes/Cradle/";
        const string BaseFbx = "LAB_HERO_Cradle_Base_01", ArmFbx = "LAB_HERO_Cradle_Arm_01", PadFbx = "LAB_HERO_Cradle_Pad_01";
        const string GreyPath = "Assets/Environment/Materials/M_Greybox.mat";
        const string AmberPath = "Assets/Environment/Materials/M_Greybox_Amber.mat";
        const string RootName = "HERO_Cradle", UndoName = "Build Cradle";

        static readonly Vector3 Origin = new Vector3(0f, 0f, 4.69f);
        static readonly Vector3 HingeL = new Vector3(-0.13f, 1.04f, 0f), HingeR = new Vector3(0.13f, 1.04f, 0f);
        const float HingeY = 1.04f, HingeX = 0.13f, PinRadius = 0.01f;

        // HERO_SPEC section 3 targets
        const float PadTopY = 1.565f, PadTopTol = 0.002f, ReleaseDeg = 100f, DroneFloorY = 1.19f, DroneArmY = 1.65f;
        const float MinClearance = 0.003f, Footprint = 1.2f, FootprintTop = 1.6f;

        static string[] Parts => new[] { BaseFbx, ArmFbx, PadFbx };

        // ----------------------------------------------------------------- import settings

        /// EXPORT_CONTRACT.md importer settings, hero mode: normals and tangents come from the FBX.
        public static string ApplyImportSettings()
        {
            var r = new StringBuilder();
            foreach (var name in Parts)
            {
                var mi = AssetImporter.GetAtPath(Dir + name + ".fbx") as ModelImporter;
                if (mi == null) { r.AppendLine($"FAIL no model importer for {Dir}{name}.fbx"); continue; }
                mi.globalScale = 1f;
                mi.useFileUnits = true;
                mi.bakeAxisConversion = false;
                mi.importBlendShapes = false;
                mi.importVisibility = false;
                mi.importCameras = false;
                mi.importLights = false;
                mi.meshCompression = ModelImporterMeshCompression.Off;
                mi.isReadable = false;
                mi.optimizeMeshPolygons = true;
                mi.optimizeMeshVertices = true;
                mi.addCollider = false;
                mi.importNormals = ModelImporterNormals.Import;
                mi.importTangents = ModelImporterTangents.Import;
                mi.generateSecondaryUV = false;
                mi.animationType = ModelImporterAnimationType.None;
                mi.importAnimation = false;
                mi.materialImportMode = ModelImporterMaterialImportMode.None;
                mi.SaveAndReimport();
                r.AppendLine($"PASS import settings {name}");
            }
            return r.ToString();
        }

        // ----------------------------------------------------------------- footprint

        /// Scene renderers/colliders inside the cradle footprint (2.4 m octagon, y 0..1.6). Reports only.
        public static string FootprintReport()
        {
            var r = new StringBuilder("[CradleBuilder] objects in the cradle footprint:\n");
            var hits = new List<string>();
            foreach (var go in SceneManager.GetActiveScene().GetRootGameObjects())
            {
                if (go.name == RootName) continue;
                foreach (var rd in go.GetComponentsInChildren<Renderer>(true))
                    if (InFootprint(rd.bounds)) hits.Add($"renderer {PathOf(rd.transform)} {F(rd.bounds.min)}..{F(rd.bounds.max)}{(rd.enabled && rd.gameObject.activeInHierarchy ? "" : " (inactive)")}");
                foreach (var c in go.GetComponentsInChildren<Collider>(true))
                    if (InFootprint(c.bounds)) hits.Add($"collider {c.GetType().Name} {PathOf(c.transform)} {F(c.bounds.min)}..{F(c.bounds.max)}{(c.enabled && c.gameObject.activeInHierarchy ? "" : " (inactive)")}");
            }
            foreach (var h in hits) r.AppendLine("  " + h);
            if (hits.Count == 0) r.AppendLine("  none");
            return r.ToString();
        }

        static bool InFootprint(Bounds b)
        {
            const float tol = 0.001f;
            if (b.max.y <= tol || b.min.y >= FootprintTop - tol) return false;
            // closest point of the bounds' XZ rectangle to the cradle axis, tested against the octagon
            var cx = Mathf.Clamp(Origin.x, b.min.x, b.max.x) - Origin.x;
            var cz = Mathf.Clamp(Origin.z, b.min.z, b.max.z) - Origin.z;
            for (var k = 0; k < 4; k++)
            {
                var a = k * Mathf.PI / 4f;
                if (Mathf.Abs(cx * Mathf.Cos(a) + cz * Mathf.Sin(a)) >= Footprint - tol) return false;
            }
            return true;
        }

        // ----------------------------------------------------------------- build

        [MenuItem("Tools/Labyrinth/Build Cradle")]
        static void BuildFromMenu() => Log(Build());

        [MenuItem("Tools/Labyrinth/Verify Cradle")]
        static void VerifyFromMenu() => Log(Verify());

        static void Log(string report)
        {
            if (report.Contains("RESULT: PASS")) Debug.Log(report); else Debug.LogError(report);
        }

        public static string Build()
        {
            var r = new StringBuilder();
            var scene = SceneManager.GetActiveScene();
            r.AppendLine($"[CradleBuilder] scene: {scene.path}");

            // Load everything first, so a missing asset changes nothing.
            var assets = new Dictionary<string, GameObject>();
            foreach (var name in Parts)
            {
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(Dir + name + ".fbx");
                if (go == null) return r.AppendLine($"FAIL missing {Dir}{name}.fbx\nRESULT: FAIL (scene unchanged)").ToString();
                assets[name] = go;
            }
            var grey = AssetDatabase.LoadAssetAtPath<Material>(GreyPath);
            if (grey == null) return r.AppendLine($"FAIL missing {GreyPath}\nRESULT: FAIL (scene unchanged)").ToString();
            var amber = LoadOrCreateAmber(r);
            if (amber == null) return r.AppendLine("RESULT: FAIL (scene unchanged)").ToString();

            Undo.IncrementCurrentGroup();
            var group = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName(UndoName);
            var old = scene.GetRootGameObjects().Where(g => g.name == RootName).ToList();
            foreach (var g in old) Undo.DestroyObjectImmediate(g);

            var root = new GameObject(RootName);
            Undo.RegisterCreatedObjectUndo(root, UndoName);
            root.transform.SetPositionAndRotation(Origin, Quaternion.identity);

            Place(assets[BaseFbx], root.transform, "Base", Vector3.zero, grey);
            foreach (var (side, pos) in new[] { ("L", HingeL), ("R", HingeR) })
            {
                var hinge = new GameObject("Hinge_" + side);
                Undo.RegisterCreatedObjectUndo(hinge, UndoName);
                hinge.transform.SetParent(root.transform, false);
                hinge.transform.localPosition = pos;
                var arm = Place(assets[ArmFbx], hinge.transform, "Arm", Vector3.zero, grey);
                Place(assets[PadFbx], arm.transform, "Pad", Vector3.zero, amber);
            }
            Undo.CollapseUndoOperations(group);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(scene);
            r.AppendLine($"built {RootName} at {F(Origin)}{(old.Count > 0 ? $" (replaced {old.Count})" : "")}");
            r.Append(Verify());
            return r.ToString();
        }

        static GameObject Place(GameObject asset, Transform parent, string name, Vector3 pos, Material mat)
        {
            var go = (GameObject)PrefabUtility.InstantiatePrefab(asset, parent.gameObject.scene);
            Undo.RegisterCreatedObjectUndo(go, UndoName);
            go.name = name;
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos;
            go.transform.localRotation = Quaternion.identity;
            go.transform.localScale = Vector3.one;
            go.GetComponent<MeshRenderer>().sharedMaterial = mat;
            return go;
        }

        static Material LoadOrCreateAmber(StringBuilder r)
        {
            var mat = AssetDatabase.LoadAssetAtPath<Material>(AmberPath);
            if (mat != null) return mat;
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) { r.AppendLine("FAIL URP Lit shader not found"); return null; }
            mat = new Material(shader);
            mat.SetColor("_BaseColor", new Color32(0xE0, 0xA0, 0x20, 0xFF));
            mat.SetFloat("_Smoothness", 0.3f);
            mat.SetFloat("_Metallic", 0f);
            AssetDatabase.CreateAsset(mat, AmberPath);
            AssetDatabase.SaveAssets();
            r.AppendLine($"created {AmberPath}");
            return mat;
        }

        // ----------------------------------------------------------------- verify

        struct Part { public Transform T; public Vector3[] V; public int[] Tri; }

        public static string Verify()
        {
            var r = new StringBuilder("[CradleBuilder] verify\n");
            var root = GameObject.Find("/" + RootName);
            if (root == null) return r.AppendLine("FAIL no HERO_Cradle\nRESULT: FAIL").ToString();
            var pass = true;
            var hinges = new[] { root.transform.Find("Hinge_L"), root.transform.Find("Hinge_R") };
            var saved = hinges.Select(h => h.localRotation).ToArray();
            try
            {
                foreach (var h in hinges) h.localRotation = Quaternion.identity;
                var basePart = Load(root.transform.Find("Base"));
                var moving = hinges.Select(h => new[] { Load(h.Find("Arm")), Load(h.Find("Arm/Pad")) }).ToArray();

                // Import: identity roots, tris
                foreach (var t in root.GetComponentsInChildren<MeshFilter>().Select(m => m.transform))
                {
                    var ok = t.localPosition == Vector3.zero && t.localRotation == Quaternion.identity && t.localScale == Vector3.one;
                    pass &= ok;
                    r.AppendLine($"{(ok ? "PASS" : "FAIL")} {PathOf(t)} local transform identity, mesh {t.GetComponent<MeshFilter>().sharedMesh.name}: " +
                                 $"{t.GetComponent<MeshFilter>().sharedMesh.triangles.Length / 3} tris, bounds {F(t.GetComponent<MeshFilter>().sharedMesh.bounds.min)}..{F(t.GetComponent<MeshFilter>().sharedMesh.bounds.max)}");
                }

                // Standby
                for (var s = 0; s < 2; s++)
                {
                    var side = s == 0 ? "L" : "R";
                    var pad = World(moving[s][1]); var arm = World(moving[s][0]);
                    var pb = BoundsOf(pad); var ab = BoundsOf(arm);
                    var topOk = Mathf.Abs(pb.max.y - PadTopY) <= PadTopTol;
                    var sign = s == 0 ? -1f : 1f;
                    var xOk = Near(pb.min.x, sign < 0 ? -0.18f : 0.08f) && Near(pb.max.x, sign < 0 ? -0.08f : 0.18f)
                              && Near(ab.min.x, sign < 0 ? -0.16f : 0.10f) && Near(ab.max.x, sign < 0 ? -0.10f : 0.16f);
                    pass &= topOk && xOk;
                    r.AppendLine($"{(topOk ? "PASS" : "FAIL")} standby Pad_{side} top y {pb.max.y:0.0000} (expect {PadTopY} +/-{PadTopTol})");
                    r.AppendLine($"{(xOk ? "PASS" : "FAIL")} standby {side}: pad x {pb.min.x - Origin.x:0.000}..{pb.max.x - Origin.x:0.000}, arm x {ab.min.x - Origin.x:0.000}..{ab.max.x - Origin.x:0.000}");
                }

                var body = GameObject.Find("Body_low");
                if (body != null && body.GetComponent<Renderer>() != null)
                {
                    var bb = body.GetComponent<Renderer>().bounds;
                    var padTop = moving.Max(m => BoundsOf(World(m[1])).max.y);
                    var armTop = moving.Max(m => BoundsOf(World(m[0])).max.y);
                    r.AppendLine($"INFO drone Body_low bounds {F(bb.min)}..{F(bb.max)} (live)");
                    r.AppendLine($"INFO gap pad top -> body underside {(bb.min.y - padTop) * 1000f:0.0} mm; highest cradle point {Mathf.Max(padTop, armTop):0.000} -> drone arms (y {DroneArmY}) {(DroneArmY - Mathf.Max(padTop, armTop)) * 1000f:0.0} mm");
                }
                else r.AppendLine("WARN Body_low not found - drone gaps not measured");

                // Sweep
                var groups = new Dictionary<string, List<Vector3[]>> { { "block", new List<Vector3[]>() }, { "cheeks", new List<Vector3[]>() }, { "column", new List<Vector3[]>() } };
                var bw = World(basePart);
                for (var i = 0; i < basePart.Tri.Length; i += 3)
                {
                    var a = basePart.V[basePart.Tri[i]]; var b = basePart.V[basePart.Tri[i + 1]]; var c = basePart.V[basePart.Tri[i + 2]];
                    if (IsPin(a) && IsPin(b) && IsPin(c)) continue;
                    var ctr = (a + b + c) / 3f;
                    string g = ctr.y < 0.3f - 1e-4f ? null : ctr.y <= 1.0f + 1e-4f ? "column"
                             : Mathf.Abs(ctr.x) <= 0.095f + 1e-4f && Mathf.Abs(ctr.z) < 0.095f ? "block" : "cheeks";
                    if (g != null) groups[g].Add(new[] { bw[basePart.Tri[i]], bw[basePart.Tri[i + 1]], bw[basePart.Tri[i + 2]] });
                }
                var worst = new Dictionary<string, float> { { "block", 9f }, { "cheeks", 9f }, { "column", 9f } };
                var rows = new StringBuilder();
                float top100 = 0f; var tips = new float[2];
                for (var deg = 0; deg <= (int)ReleaseDeg; deg += 5)
                {
                    hinges[0].localRotation = Quaternion.Euler(0f, 0f, deg);    // L outward
                    hinges[1].localRotation = Quaternion.Euler(0f, 0f, -deg);   // R outward
                    rows.Append($"  {deg,3} deg");
                    for (var s = 0; s < 2; s++)
                    {
                        var pts = new List<Vector3>();
                        foreach (var p in moving[s]) pts.AddRange(Samples(p));
                        var hingeW = hinges[s].position;
                        var near = pts.Where(q => (q - hingeW).sqrMagnitude < NearHinge * NearHinge).ToList();
                        rows.Append(s == 0 ? "  L:" : "  R:");
                        foreach (var g in new[] { "block", "cheeks", "column" })
                        {
                            var d = MinDistance(near, groups[g]);
                            worst[g] = Mathf.Min(worst[g], d);
                            rows.Append($" {g} {d * 1000f,5:0.0}");
                        }
                        if (deg == (int)ReleaseDeg)
                        {
                            top100 = Mathf.Max(top100, pts.Max(q => q.y));
                            tips[s] = moving[s][1].T.TransformPoint(new Vector3(0f, 0.5125f, 0f)).y;
                        }
                    }
                    rows.AppendLine(" mm");
                }
                var sideOk = moving[0][1].T.TransformPoint(new Vector3(0f, 0.5125f, 0f)).x < Origin.x - 0.5f;
                var sweepOk = worst.Values.All(v => v >= MinClearance) && top100 < DroneFloorY && sideOk;
                pass &= sweepOk;
                r.Append(rows);
                r.AppendLine($"{(worst.Values.All(v => v >= MinClearance) ? "PASS" : "FAIL")} sweep min clearance: block {worst["block"] * 1000f:0.0} mm, cheeks {worst["cheeks"] * 1000f:0.0} mm, column {worst["column"] * 1000f:0.0} mm (>= {MinClearance * 1000f:0} mm, pin excluded)");
                r.AppendLine($"{(top100 < DroneFloorY ? "PASS" : "FAIL")} at {ReleaseDeg} deg highest point y {top100:0.000} (< {DroneFloorY}), pad centres y L {tips[0]:0.000} R {tips[1]:0.000}");
                r.AppendLine($"{(sideOk ? "PASS" : "FAIL")} Hinge_L +Z opens toward -X (outward), Hinge_R -Z toward +X");
            }
            finally
            {
                for (var i = 0; i < hinges.Length; i++) hinges[i].localRotation = saved[i];
            }
            r.AppendLine("standby restored");
            r.AppendLine(pass ? "RESULT: PASS - scene marked dirty, NOT saved." : "RESULT: FAIL");
            return r.ToString();
        }

        // Only points this close to the hinge can come near the hub or column: the Base geometry
        // checked here lies within 0.33 m of the hinge and the column below it is inboard.
        const float NearHinge = 0.4f;

        static float MinDistance(List<Vector3> pts, List<Vector3[]> tris)
        {
            var lo = tris.Select(t => Vector3.Min(t[0], Vector3.Min(t[1], t[2]))).ToArray();
            var hi = tris.Select(t => Vector3.Max(t[0], Vector3.Max(t[1], t[2]))).ToArray();
            var best = float.MaxValue;
            foreach (var q in pts)
                for (var i = 0; i < tris.Count; i++)
                {
                    var box = (Vector3.Max(lo[i] - q, Vector3.Max(q - hi[i], Vector3.zero))).sqrMagnitude;
                    if (box >= best * best) continue;
                    var d = (q - ClosestOnTri(q, tris[i][0], tris[i][1], tris[i][2])).magnitude;
                    if (d < best) best = d;
                }
            return best;
        }

        static Part Load(Transform t)
        {
            var m = t.GetComponent<MeshFilter>().sharedMesh;
            return new Part { T = t, V = m.vertices, Tri = m.triangles };
        }

        static Vector3[] World(Part p) => p.V.Select(p.T.TransformPoint).ToArray();

        static Bounds BoundsOf(Vector3[] pts)
        {
            var b = new Bounds(pts[0], Vector3.zero);
            foreach (var q in pts) b.Encapsulate(q);
            return b;
        }

        /// World vertices plus points every 2 mm along every triangle edge.
        static IEnumerable<Vector3> Samples(Part p)
        {
            var w = World(p);
            foreach (var q in w) yield return q;
            for (var i = 0; i < p.Tri.Length; i += 3)
                for (var e = 0; e < 3; e++)
                {
                    var a = w[p.Tri[i + e]]; var b = w[p.Tri[i + (e + 1) % 3]];
                    var n = (int)((b - a).magnitude / 0.002f);
                    for (var k = 1; k <= n; k++) yield return Vector3.Lerp(a, b, k / (n + 1f));
                }
        }

        static bool IsPin(Vector3 v) =>
            Mathf.Min(new Vector2(v.x + HingeX, v.y - HingeY).magnitude, new Vector2(v.x - HingeX, v.y - HingeY).magnitude) <= PinRadius + 1e-4f;

        // Ericson, Real-Time Collision Detection 5.1.5
        static Vector3 ClosestOnTri(Vector3 p, Vector3 a, Vector3 b, Vector3 c)
        {
            Vector3 ab = b - a, ac = c - a, ap = p - a;
            float d1 = Vector3.Dot(ab, ap), d2 = Vector3.Dot(ac, ap);
            if (d1 <= 0f && d2 <= 0f) return a;
            Vector3 bp = p - b; float d3 = Vector3.Dot(ab, bp), d4 = Vector3.Dot(ac, bp);
            if (d3 >= 0f && d4 <= d3) return b;
            float vc = d1 * d4 - d3 * d2;
            if (vc <= 0f && d1 >= 0f && d3 <= 0f) return a + ab * (d1 / (d1 - d3));
            Vector3 cp = p - c; float d5 = Vector3.Dot(ab, cp), d6 = Vector3.Dot(ac, cp);
            if (d6 >= 0f && d5 <= d6) return c;
            float vb = d5 * d2 - d1 * d6;
            if (vb <= 0f && d2 >= 0f && d6 <= 0f) return a + ac * (d2 / (d2 - d6));
            float va = d3 * d6 - d5 * d4;
            if (va <= 0f && (d4 - d3) >= 0f && (d5 - d6) >= 0f) return b + (c - b) * ((d4 - d3) / ((d4 - d3) + (d5 - d6)));
            float den = 1f / (va + vb + vc);
            return a + ab * (vb * den) + ac * (vc * den);
        }

        static bool Near(float worldX, float cradleX) => Mathf.Abs(worldX - Origin.x - cradleX) < 0.001f;
        static string F(Vector3 v) => $"({v.x:0.000}, {v.y:0.000}, {v.z:0.000})";
        static string PathOf(Transform t) => t.parent == null ? t.name : PathOf(t.parent) + "/" + t.name;
    }
}
