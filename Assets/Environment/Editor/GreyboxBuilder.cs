// GreyboxBuilder.cs - rebuilds the Industrial Robotics Research Facility greybox
// (room + corridor) in the open scene from one data table.
//
// Menu:  Tools > Labyrinth > Rebuild Greybox
// Code:  LabyrinthVR.EnvironmentTools.GreyboxBuilder.Rebuild()  (returns the report)
//
// Source of truth for every number here: Documentation/ENVIRONMENT_SPEC.md.
// Pivots and yaw convention: Documentation/EXPORT_CONTRACT.md.
//
// What it owns: prefab instances of Assets/Environment/Kit/*.fbx under ENV_Greybox.
// Those are destroyed and re-created on every run. Everything else under ENV_Greybox
// (lights, future props) is left untouched. It never saves the scene - review, then Ctrl+S.
// One Undo step: Ctrl+Z reverts the whole rebuild.

using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace LabyrinthVR.EnvironmentTools
{
    public static class GreyboxBuilder
    {
        const string KitDir = "Assets/Environment/Kit/";
        const string MaterialPath = "Assets/Environment/Materials/M_Greybox.mat";
        const string RootName = "ENV_Greybox";
        const string UndoName = "Rebuild Greybox";

        // Kit modules
        const string Floor = "LAB_ENV_Floor_A_01";
        const string Ceiling = "LAB_ENV_Ceiling_A_01";
        const string WallA = "LAB_ENV_Wall_A_01";
        const string WallPanel = "LAB_ENV_Wall_Panel_01";
        const string WallCorner = "LAB_ENV_Wall_Corner_01";
        const string WallDoor = "LAB_ENV_Wall_Door_01";
        const string WallCorridor = "LAB_ENV_Wall_Corridor_01";
        const string Trim = "LAB_ENV_Trim_A_01";

        // Room (ENVIRONMENT_SPEC.md "Room")
        const float XMin = -4f, XMax = 4f, ZMin = -2f, ZMax = 8f;
        const float CeilingY = 4f, BandY = 2f;
        static readonly float[] CellX = { -3f, -1f, 1f, 3f };
        static readonly float[] CellZ = { -1f, 1f, 3f, 5f, 7f };
        const float DoorX = -1f;

        // Corridor (ENVIRONMENT_SPEC.md "Corridor")
        const float CorrX = -1f, CorrWallLeftX = -2f, CorrWallRightX = 0f;
        const float CorrCeilingY = 3f, CorrEndZ = 14f;
        static readonly float[] CorrTileZ = { 9f, 11f, 13f };
        static readonly float[] CorrWallZ = { 9.2f, 11.2f, 13.2f };

        // Wall yaw: body extends +Z local, i.e. away from the room (EXPORT_CONTRACT.md).
        const float YawBack = 180f, YawFar = 0f, YawLeft = 270f, YawRight = 90f;
        // Trim sits on the wall face and protrudes into the room: wall yaw + 180.
        const float TrimFlip = 180f;

        // Expected results - the self-check compares against these.
        static readonly Dictionary<string, int> ExpectedCounts = new Dictionary<string, int>
        {
            { "ENV_Floor", 20 }, { "ENV_Ceiling", 20 },
            { "ENV_Walls/Wall_Back", 8 }, { "ENV_Walls/Wall_Far", 7 },
            { "ENV_Walls/Wall_Left", 10 }, { "ENV_Walls/Wall_Right", 10 },
            { "ENV_Corners", 4 }, { "ENV_Trim", 17 },
            { "ENV_Corridor/Corr_Floor", 3 }, { "ENV_Corridor/Corr_Ceiling", 3 },
            { "ENV_Corridor/Corr_Walls", 7 },
        };
        static readonly Vector3 ExpectedMin = new Vector3(-4.2f, -0.1f, -2.2f);
        static readonly Vector3 ExpectedMax = new Vector3(4.2f, 4.1f, 14.2f);
        const float Tol = 0.001f;

        // Protected volumes (ENVIRONMENT_SPEC.md). The drone volume is read LIVE from the
        // DroneBounds collider plus this margin, so it stays right when DroneBounds changes.
        const float DroneMargin = 0.5f;
        const float PlayerRadius = 1f, PlayerHeight = 2.5f;

        struct Placement
        {
            public string Group, Module;
            public Vector3 Pos;
            public float Yaw;
            public Placement(string group, string module, float x, float y, float z, float yaw)
            { Group = group; Module = module; Pos = new Vector3(x, y, z); Yaw = yaw; }
        }

        static List<Placement> Layout()
        {
            var p = new List<Placement>();

            foreach (var x in CellX)
                foreach (var z in CellZ)
                {
                    p.Add(new Placement("ENV_Floor", Floor, x, 0f, z, 0f));
                    p.Add(new Placement("ENV_Ceiling", Ceiling, x, CeilingY, z, 0f));
                }

            foreach (var x in CellX)
            {
                p.Add(new Placement("ENV_Walls/Wall_Back", WallA, x, 0f, ZMin, YawBack));
                p.Add(new Placement("ENV_Walls/Wall_Back", WallPanel, x, BandY, ZMin, YawBack));
                p.Add(new Placement("ENV_Trim", Trim, x, 0f, ZMin, YawBack + TrimFlip));

                if (Mathf.Approximately(x, DoorX))
                {
                    p.Add(new Placement("ENV_Walls/Wall_Far", WallDoor, x, 0f, ZMax, YawFar));
                    continue; // no trim across the doorway
                }
                p.Add(new Placement("ENV_Walls/Wall_Far", WallA, x, 0f, ZMax, YawFar));
                p.Add(new Placement("ENV_Walls/Wall_Far", WallPanel, x, BandY, ZMax, YawFar));
                p.Add(new Placement("ENV_Trim", Trim, x, 0f, ZMax, YawFar + TrimFlip));
            }

            foreach (var z in CellZ)
            {
                p.Add(new Placement("ENV_Walls/Wall_Left", WallA, XMin, 0f, z, YawLeft));
                p.Add(new Placement("ENV_Walls/Wall_Left", WallPanel, XMin, BandY, z, YawLeft));
                p.Add(new Placement("ENV_Trim", Trim, XMin, 0f, z, YawLeft + TrimFlip));

                p.Add(new Placement("ENV_Walls/Wall_Right", WallA, XMax, 0f, z, YawRight));
                p.Add(new Placement("ENV_Walls/Wall_Right", WallPanel, XMax, BandY, z, YawRight));
                p.Add(new Placement("ENV_Trim", Trim, XMax, 0f, z, YawRight + TrimFlip));
            }

            // Corner column body extends +X,+Z local; these yaws put it outside each corner.
            p.Add(new Placement("ENV_Corners", WallCorner, XMin, 0f, ZMin, 180f));
            p.Add(new Placement("ENV_Corners", WallCorner, XMax, 0f, ZMin, 90f));
            p.Add(new Placement("ENV_Corners", WallCorner, XMin, 0f, ZMax, 270f));
            p.Add(new Placement("ENV_Corners", WallCorner, XMax, 0f, ZMax, 0f));

            foreach (var z in CorrTileZ)
            {
                p.Add(new Placement("ENV_Corridor/Corr_Floor", Floor, CorrX, 0f, z, 0f));
                p.Add(new Placement("ENV_Corridor/Corr_Ceiling", Ceiling, CorrX, CorrCeilingY, z, 0f));
            }
            foreach (var z in CorrWallZ)
            {
                p.Add(new Placement("ENV_Corridor/Corr_Walls", WallCorridor, CorrWallLeftX, 0f, z, YawLeft));
                p.Add(new Placement("ENV_Corridor/Corr_Walls", WallCorridor, CorrWallRightX, 0f, z, YawRight));
            }
            p.Add(new Placement("ENV_Corridor/Corr_Walls", WallCorridor, CorrX, 0f, CorrEndZ, YawFar));

            return p;
        }

        [MenuItem("Tools/Labyrinth/Rebuild Greybox")]
        static void RebuildFromMenu()
        {
            var report = Rebuild();
            if (report.Contains("RESULT: PASS")) Debug.Log(report);
            else Debug.LogError(report);
        }

        public static string Rebuild()
        {
            var r = new StringBuilder();
            var layout = Layout();
            var scene = SceneManager.GetActiveScene();
            r.AppendLine($"[GreyboxBuilder] scene: {scene.path}");

            // 1. Load everything BEFORE touching the scene, so a missing asset changes nothing.
            var assets = new Dictionary<string, GameObject>();
            foreach (var name in layout.Select(p => p.Module).Distinct())
            {
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(KitDir + name + ".fbx");
                if (go == null) return r.AppendLine($"FAIL missing kit asset {KitDir}{name}.fbx\nRESULT: FAIL (scene unchanged)").ToString();
                assets[name] = go;
            }
            var mat = LoadOrCreateMaterial(r);
            if (mat == null) return r.AppendLine("RESULT: FAIL (scene unchanged)").ToString();

            // 2. Root and groups must be untransformed, or local positions would not be world positions.
            var root = scene.GetRootGameObjects().FirstOrDefault(g => g.name == RootName);
            var rootIsNew = root == null;
            Undo.IncrementCurrentGroup();
            var undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName(UndoName);
            if (rootIsNew)
            {
                root = new GameObject(RootName);
                Undo.RegisterCreatedObjectUndo(root, UndoName);
            }

            var groups = new Dictionary<string, Transform>();
            foreach (var path in ExpectedCounts.Keys) groups[path] = GetOrCreate(root.transform, path);
            foreach (var t in groups.Values.Prepend(root.transform))
                for (var a = t; a != null; a = a.parent)
                    if (a.localPosition != Vector3.zero || a.localRotation != Quaternion.identity || a.localScale != Vector3.one)
                    {
                        Undo.CollapseUndoOperations(undoGroup);
                        return r.AppendLine($"FAIL '{a.name}' is not at identity transform - fix it, then rerun\nRESULT: FAIL").ToString();
                    }

            // 3. Replace kit instances only.
            var old = KitInstances(root.transform).ToList();
            foreach (var go in old) Undo.DestroyObjectImmediate(go);
            var strays = KitInstancesInScene(scene).Where(g => !g.transform.IsChildOf(root.transform)).ToList();

            foreach (var p in layout)
            {
                var go = (GameObject)PrefabUtility.InstantiatePrefab(assets[p.Module], scene);
                Undo.RegisterCreatedObjectUndo(go, UndoName);
                go.transform.SetParent(groups[p.Group], false);
                go.transform.localPosition = p.Pos;
                go.transform.localRotation = Quaternion.Euler(0f, p.Yaw, 0f);
                go.transform.localScale = Vector3.one;
                var mr = go.GetComponent<MeshRenderer>();
                if (mr != null) mr.sharedMaterial = mat;
            }
            Undo.CollapseUndoOperations(undoGroup);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(scene);
            r.AppendLine($"replaced {old.Count} kit instances with {layout.Count}{(rootIsNew ? " (new ENV_Greybox)" : "")}");

            // 4. Self-check.
            var pass = true;
            foreach (var kv in ExpectedCounts)
            {
                var n = groups[kv.Key].Cast<Transform>().Count(c => IsKitInstance(c.gameObject));
                var ok = n == kv.Value; pass &= ok;
                r.AppendLine($"{(ok ? "PASS" : "FAIL")} {kv.Key}: {n} (expect {kv.Value})");
            }

            var renderers = KitInstances(root.transform).SelectMany(g => g.GetComponentsInChildren<MeshRenderer>(true)).ToList();
            var all = renderers[0].bounds;
            foreach (var mr in renderers) all.Encapsulate(mr.bounds);
            var boundsOk = Near(all.min, ExpectedMin) && Near(all.max, ExpectedMax); pass &= boundsOk;
            r.AppendLine($"{(boundsOk ? "PASS" : "FAIL")} bounds {F(all.min)} .. {F(all.max)} (expect {F(ExpectedMin)} .. {F(ExpectedMax)})");

            var badMat = renderers.Where(mr => mr.sharedMaterial != mat).Select(mr => mr.name).ToList();
            pass &= badMat.Count == 0;
            r.AppendLine(badMat.Count == 0 ? "PASS material: all M_Greybox" : $"FAIL material: {string.Join(", ", badMat)}");

            var drone = DroneVolume();
            if (drone.HasValue)
            {
                var hits = renderers.Where(mr => Overlaps(mr.bounds, drone.Value)).Select(Path).ToList();
                pass &= hits.Count == 0;
                r.AppendLine(hits.Count == 0
                    ? $"PASS drone volume clear {F(drone.Value.min)} .. {F(drone.Value.max)} (DroneBounds + {DroneMargin})"
                    : $"FAIL drone volume hit by: {string.Join(", ", hits)}");
            }
            else r.AppendLine("WARN DroneBounds not found - drone volume not checked");

            var playerHits = renderers.Where(mr => InPlayerCylinder(mr.bounds)).Select(Path).ToList();
            pass &= playerHits.Count == 0;
            r.AppendLine(playerHits.Count == 0 ? "PASS player volume clear" : $"FAIL player volume hit by: {string.Join(", ", playerHits)}");

            if (strays.Count > 0)
                r.AppendLine($"WARN {strays.Count} kit instance(s) outside ENV_Greybox, not touched: {string.Join(", ", strays.Select(g => g.name))}");

            r.AppendLine(pass ? "RESULT: PASS - scene marked dirty, NOT saved. Review, then Ctrl+S."
                              : "RESULT: FAIL - do not save. Ctrl+Z reverts the rebuild.");
            return r.ToString();
        }

        static Material LoadOrCreateMaterial(StringBuilder r)
        {
            var mat = AssetDatabase.LoadAssetAtPath<Material>(MaterialPath);
            if (mat != null) return mat;
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) { r.AppendLine("FAIL URP Lit shader not found"); return null; }
            mat = new Material(shader);
            mat.SetColor("_BaseColor", new Color(0.5f, 0.5f, 0.5f, 1f));
            mat.SetFloat("_Smoothness", 0.1f);
            mat.SetFloat("_Metallic", 0f);
            AssetDatabase.CreateAsset(mat, MaterialPath);
            AssetDatabase.SaveAssets();
            r.AppendLine($"created {MaterialPath}");
            return mat;
        }

        static Transform GetOrCreate(Transform parent, string path)
        {
            var t = parent;
            foreach (var part in path.Split('/'))
            {
                var child = t.Find(part);
                if (child == null)
                {
                    var go = new GameObject(part);
                    Undo.RegisterCreatedObjectUndo(go, UndoName);
                    go.transform.SetParent(t, false);
                    child = go.transform;
                }
                t = child;
            }
            return t;
        }

        static bool IsKitInstance(GameObject go)
        {
            if (!PrefabUtility.IsOutermostPrefabInstanceRoot(go)) return false;
            var src = PrefabUtility.GetCorrespondingObjectFromSource(go);
            return src != null && AssetDatabase.GetAssetPath(src).StartsWith(KitDir);
        }

        static IEnumerable<GameObject> KitInstances(Transform root) =>
            root.GetComponentsInChildren<Transform>(true).Select(t => t.gameObject).Where(IsKitInstance);

        static IEnumerable<GameObject> KitInstancesInScene(Scene scene) =>
            scene.GetRootGameObjects().SelectMany(g => KitInstances(g.transform));

        static Bounds? DroneVolume()
        {
            var go = GameObject.Find("DroneBounds");
            var box = go != null ? go.GetComponent<BoxCollider>() : null;
            if (box == null) return null;
            var t = box.transform;
            var h = box.size * 0.5f;
            var b = new Bounds(t.TransformPoint(box.center), Vector3.zero);
            for (var i = 0; i < 8; i++)
                b.Encapsulate(t.TransformPoint(box.center + Vector3.Scale(h, new Vector3((i & 1) == 0 ? -1 : 1, (i & 2) == 0 ? -1 : 1, (i & 4) == 0 ? -1 : 1))));
            b.Expand(DroneMargin * 2f);
            return b;
        }

        // Strict overlap: surfaces that only touch (a floor top at the volume's floor) do not count.
        static bool Overlaps(Bounds a, Bounds b) =>
            a.min.x < b.max.x - Tol && a.max.x > b.min.x + Tol &&
            a.min.y < b.max.y - Tol && a.max.y > b.min.y + Tol &&
            a.min.z < b.max.z - Tol && a.max.z > b.min.z + Tol;

        static bool InPlayerCylinder(Bounds b)
        {
            var cx = Mathf.Clamp(0f, b.min.x, b.max.x);
            var cz = Mathf.Clamp(0f, b.min.z, b.max.z);
            return cx * cx + cz * cz < PlayerRadius * PlayerRadius - Tol
                && b.min.y < PlayerHeight - Tol && b.max.y > Tol;
        }

        static bool Near(Vector3 a, Vector3 b) => (a - b).sqrMagnitude < Tol * Tol * 3f;
        static string F(Vector3 v) => $"({v.x:0.00}, {v.y:0.00}, {v.z:0.00})";
        static string Path(MeshRenderer mr) => $"{mr.transform.parent.name}/{mr.name}";
    }
}
