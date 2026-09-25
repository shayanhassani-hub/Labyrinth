// LabyrinthBuilder.cs - assembles the Labyrinth v2 tilt mechanic (stand, pivot, panel,
// handle, ball lid, goal trigger) under "LAB_Labyrinth" in the open scene, sets the three
// physics layers and their collision matrix, places the ball, deactivates the old panel,
// and switches the projectile prefab to Continuous collision.
//
// Menu:  Tools > Labyrinth > Rebuild Labyrinth
// Code:  LabyrinthVR.EnvironmentTools.LabyrinthBuilder.Rebuild()  (returns the report)
//
// Source of truth: Documentation/HERO_SPEC.md section 8, Tools/Blender/labyrinth_maze_v1.json.
//
// What it owns: everything under "LAB_Labyrinth" (destroyed and re-created on every run),
// the layer + name on "Labyrinth Ball" and its world position, the active state of the old
// "Labyrinth Panel", and the layer + collision detection mode on the Sphere projectile
// prefab asset. Nothing else is touched. It never saves the scene - review, then Ctrl+S.
// One Undo step for the scene edits: Ctrl+Z reverts them (the physics-layer and prefab-asset
// edits are project-settings/asset changes and are not part of that Undo step).

using System.Collections.Generic;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace LabyrinthVR.EnvironmentTools
{
    public static class LabyrinthBuilder
    {
        const string PropsDir = "Assets/Environment/Props/Labyrinth/";
        const string MaterialPath = "Assets/Environment/Materials/M_Greybox.mat";
        const string ProjectilePath = "Assets/3D Models/Sphere.prefab";
        const string RootName = "LAB_Labyrinth";
        const string UndoName = "Rebuild Labyrinth";

        const string StandModule = "LAB_PROP_LabyrinthStand_01";
        const string PanelModule = "LAB_PROP_LabyrinthPanel_01";
        const string HandleModule = "LAB_PROP_LabyrinthPanel_Handle_01";

        const string LayerBall = "LabyrinthBall";
        const string LayerLid = "LabyrinthLid";
        const string LayerProjectile = "Projectile";
        const int LayerSearchStart = 6; // 0-5 are Unity's reserved/built-in slots

        static readonly Vector3 StandPos = new Vector3(0.025f, 0f, 1.225f);
        static readonly Vector3 PivotPos = new Vector3(0.025f, 1.00f, 1.225f);
        static readonly Vector3 LidCenter = new Vector3(0f, 0.155f, 0f);
        static readonly Vector3 LidSize = new Vector3(0.95f, 0.02f, 0.95f);
        static readonly Vector3 GoalCenter = new Vector3(0.40f, -0.03f, 0.40f);
        static readonly Vector3 GoalSize = new Vector3(0.14f, 0.04f, 0.14f);
        static readonly Vector3 BallOffset = new Vector3(-0.304f, 0f, -0.390f); // y handled separately
        const float PlateTopLocalY = 0.025f;
        const float BallClearance = 0.002f;

        static readonly Vector3 ExpectedPanelMin = new Vector3(-0.5f, 1.00f, 0.70f);
        static readonly Vector3 ExpectedPanelMax = new Vector3(0.55f, 1.105f, 1.75f);
        static readonly Vector2 ExpectedGoalXZ = new Vector2(0.425f, 1.625f);
        const float Tol = 0.02f;

        [MenuItem("Tools/Labyrinth/Rebuild Labyrinth")]
        static void RebuildFromMenu()
        {
            var report = Rebuild();
            if (report.Contains("RESULT: PASS")) Debug.Log(report);
            else Debug.LogError(report);
        }

        public static string Rebuild()
        {
            var r = new StringBuilder();
            var scene = SceneManager.GetActiveScene();
            r.AppendLine($"[LabyrinthBuilder] scene: {scene.path}");
            var pass = true;

            // 1. Physics layers + collision matrix (project settings; not part of the scene Undo step).
            int ballLayer, lidLayer, projLayer;
            if (!SetupLayers(out ballLayer, out lidLayer, out projLayer, r))
                return r.AppendLine("RESULT: FAIL (nothing else changed)").ToString();
            SetupCollisionMatrix(ballLayer, lidLayer, projLayer);
            AssetDatabase.SaveAssets();
            r.AppendLine($"layers: {LayerBall}={ballLayer}, {LayerLid}={lidLayer}, {LayerProjectile}={projLayer}");

            // 2. Load props before touching the scene, so a missing asset changes nothing.
            var standAsset = AssetDatabase.LoadAssetAtPath<GameObject>(PropsDir + StandModule + ".fbx");
            var panelAsset = AssetDatabase.LoadAssetAtPath<GameObject>(PropsDir + PanelModule + ".fbx");
            var handleAsset = AssetDatabase.LoadAssetAtPath<GameObject>(PropsDir + HandleModule + ".fbx");
            if (standAsset == null || panelAsset == null || handleAsset == null)
                return r.AppendLine("FAIL missing a prop asset in " + PropsDir + "\nRESULT: FAIL").ToString();
            var mat = AssetDatabase.LoadAssetAtPath<Material>(MaterialPath);
            if (mat == null)
                return r.AppendLine("FAIL missing " + MaterialPath + "\nRESULT: FAIL").ToString();

            // 3. Root: destroy and rebuild everything this script owns.
            Undo.IncrementCurrentGroup();
            var undoGroup = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName(UndoName);

            var root = scene.GetRootGameObjects().FirstOrDefault(g => g.name == RootName);
            var rootIsNew = root == null;
            if (rootIsNew)
            {
                root = new GameObject(RootName);
                Undo.RegisterCreatedObjectUndo(root, UndoName);
            }
            else
            {
                foreach (Transform c in root.transform.Cast<Transform>().ToList())
                    Undo.DestroyObjectImmediate(c.gameObject);
            }
            root.transform.position = Vector3.zero;
            root.transform.rotation = Quaternion.identity;
            root.transform.localScale = Vector3.one;

            var stand = (GameObject)PrefabUtility.InstantiatePrefab(standAsset, scene);
            Undo.RegisterCreatedObjectUndo(stand, UndoName);
            stand.transform.SetParent(root.transform, false);
            stand.transform.position = StandPos;
            stand.transform.rotation = Quaternion.identity;
            stand.isStatic = true;
            stand.GetComponent<MeshRenderer>().sharedMaterial = mat;

            var pivotGo = new GameObject("LabyrinthPivot");
            Undo.RegisterCreatedObjectUndo(pivotGo, UndoName);
            pivotGo.transform.SetParent(root.transform, false);
            pivotGo.transform.position = PivotPos;
            pivotGo.transform.rotation = Quaternion.identity;
            var pivotRb = pivotGo.AddComponent<Rigidbody>();
            pivotRb.isKinematic = true;
            pivotRb.interpolation = RigidbodyInterpolation.Interpolate;
            pivotRb.useGravity = false;

            var panel = (GameObject)PrefabUtility.InstantiatePrefab(panelAsset, scene);
            Undo.RegisterCreatedObjectUndo(panel, UndoName);
            panel.transform.SetParent(pivotGo.transform, false);
            panel.transform.localPosition = Vector3.zero;
            panel.transform.localRotation = Quaternion.identity;
            panel.GetComponent<MeshRenderer>().sharedMaterial = mat;
            var panelMesh = panel.GetComponent<MeshFilter>().sharedMesh;
            var panelCollider = panel.AddComponent<MeshCollider>();
            panelCollider.sharedMesh = panelMesh;
            panelCollider.convex = false;

            var handle = (GameObject)PrefabUtility.InstantiatePrefab(handleAsset, scene);
            Undo.RegisterCreatedObjectUndo(handle, UndoName);
            handle.transform.SetParent(pivotGo.transform, false);
            handle.transform.localPosition = Vector3.zero;
            handle.transform.localRotation = Quaternion.identity;
            handle.GetComponent<MeshRenderer>().sharedMaterial = mat;
            var handleBounds = handle.GetComponent<MeshFilter>().sharedMesh.bounds;
            var cap = handle.AddComponent<CapsuleCollider>();
            cap.direction = 0; // X axis, along the bar
            cap.center = handleBounds.center;
            cap.radius = Mathf.Max(handleBounds.extents.y, handleBounds.extents.z);
            cap.height = handleBounds.size.x;

            var ballLid = new GameObject("BallLid");
            Undo.RegisterCreatedObjectUndo(ballLid, UndoName);
            ballLid.transform.SetParent(pivotGo.transform, false);
            ballLid.transform.localPosition = Vector3.zero;
            ballLid.transform.localRotation = Quaternion.identity;
            ballLid.layer = lidLayer;
            var lidBox = ballLid.AddComponent<BoxCollider>();
            lidBox.center = LidCenter;
            lidBox.size = LidSize;

            var goalTrigger = new GameObject("GoalTrigger");
            Undo.RegisterCreatedObjectUndo(goalTrigger, UndoName);
            goalTrigger.transform.SetParent(pivotGo.transform, false);
            goalTrigger.transform.localPosition = Vector3.zero;
            goalTrigger.transform.localRotation = Quaternion.identity;
            var goalBox = goalTrigger.AddComponent<BoxCollider>();
            goalBox.isTrigger = true;
            goalBox.center = GoalCenter;
            goalBox.size = GoalSize;

            // 4. Ball: reuse the existing object, place it by its (offset) collider centre.
            var ball = GameObject.Find("Labyrinth Ball");
            if (ball == null)
            {
                Undo.CollapseUndoOperations(undoGroup);
                return r.AppendLine("FAIL 'Labyrinth Ball' not found in scene\nRESULT: FAIL").ToString();
            }
            var ballSphere = ball.GetComponent<SphereCollider>();
            var posToWorldCenter = ball.transform.TransformPoint(ballSphere.center) - ball.transform.position;
            var lossy = ball.transform.lossyScale;
            var uniformCheck = Mathf.Abs(lossy.x - lossy.y) + Mathf.Abs(lossy.y - lossy.z);
            var worldRadius = ballSphere.radius * lossy.x;
            var targetCenter = PivotPos + new Vector3(BallOffset.x, PlateTopLocalY + worldRadius + BallClearance, BallOffset.z);
            Undo.RecordObject(ball.transform, UndoName);
            ball.transform.position = targetCenter - posToWorldCenter;
            ball.layer = ballLayer;
            var actualCenter = ball.transform.TransformPoint(ballSphere.center);
            r.AppendLine($"ball world collider centre {F(actualCenter)}, radius {worldRadius:0.0000}"
                + (uniformCheck > 0.0001f ? " WARN non-uniform ball scale, radius approximate" : ""));

            // 5. Old panel: deactivate, do not delete.
            var oldPanel = GameObject.Find("Labyrinth Panel");
            if (oldPanel != null)
            {
                Undo.RecordObject(oldPanel, UndoName);
                oldPanel.SetActive(false);
            }
            else r.AppendLine("WARN 'Labyrinth Panel' (old) not found - nothing to deactivate");

            Undo.CollapseUndoOperations(undoGroup);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(scene);
            r.AppendLine(rootIsNew ? $"created {RootName}" : $"rebuilt {RootName}");

            // 6. Projectile prefab asset.
            SetupProjectile(projLayer, r);

            // 7. Verify.
            var pivotOk = Near(pivotGo.transform.position, PivotPos); pass &= pivotOk;
            r.AppendLine($"{(pivotOk ? "PASS" : "FAIL")} LabyrinthPivot world position {F(pivotGo.transform.position)} (expect {F(PivotPos)})");

            var panelRenderer = panel.GetComponent<MeshRenderer>();
            var pb = panelRenderer.bounds;
            var boundsOk = Near(pb.min, ExpectedPanelMin) && Near(pb.max, ExpectedPanelMax); pass &= boundsOk;
            r.AppendLine($"{(boundsOk ? "PASS" : "FAIL")} panel world bounds {F(pb.min)} .. {F(pb.max)} (expect {F(ExpectedPanelMin)} .. {F(ExpectedPanelMax)})");

            var goalWorld = goalTrigger.transform.TransformPoint(goalBox.center);
            var goalXZ = new Vector2(goalWorld.x, goalWorld.z);
            var goalOk = (goalXZ - ExpectedGoalXZ).magnitude < Tol; pass &= goalOk;
            r.AppendLine($"{(goalOk ? "PASS" : "FAIL")} goal hole world centre x,z ({goalWorld.x:0.000}, {goalWorld.z:0.000}) (expect {ExpectedGoalXZ.x:0.000}, {ExpectedGoalXZ.y:0.000})");

            var envRoot = scene.GetRootGameObjects().FirstOrDefault(g => g.name == "ENV_Greybox");
            var teleport = envRoot != null ? envRoot.transform.Find("NAV_TeleportFloor")
                ?? envRoot.GetComponentsInChildren<Transform>(true).FirstOrDefault(t => t.name == "NAV_TeleportFloor") : null;
            var envOk = envRoot != null && teleport != null; pass &= envOk;
            r.AppendLine($"{(envOk ? "PASS" : "FAIL")} ENV_Greybox and NAV_TeleportFloor present (not touched by this script)");

            r.AppendLine(pass ? "RESULT: PASS - scene marked dirty, NOT saved. Review, then Ctrl+S."
                              : "RESULT: FAIL - review before saving. Ctrl+Z reverts the scene edits.");
            return r.ToString();
        }

        static bool SetupLayers(out int ballLayer, out int lidLayer, out int projLayer, StringBuilder r)
        {
            var tagManagerAssets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/TagManager.asset");
            if (tagManagerAssets.Length == 0)
            {
                ballLayer = lidLayer = projLayer = -1;
                r.AppendLine("FAIL ProjectSettings/TagManager.asset not found");
                return false;
            }
            var so = new SerializedObject(tagManagerAssets[0]);
            var layers = so.FindProperty("layers");

            ballLayer = EnsureLayer(layers, LayerBall);
            lidLayer = EnsureLayer(layers, LayerLid);
            projLayer = EnsureLayer(layers, LayerProjectile);
            so.ApplyModifiedProperties();

            if (ballLayer < 0 || lidLayer < 0 || projLayer < 0)
            {
                r.AppendLine("FAIL no free layer slot (6-31 all occupied)");
                return false;
            }
            return true;
        }

        static int EnsureLayer(SerializedProperty layers, string name)
        {
            for (var i = 0; i < layers.arraySize; i++)
                if (layers.GetArrayElementAtIndex(i).stringValue == name) return i;
            for (var i = LayerSearchStart; i < layers.arraySize; i++)
            {
                var sp = layers.GetArrayElementAtIndex(i);
                if (string.IsNullOrEmpty(sp.stringValue))
                {
                    sp.stringValue = name;
                    return i;
                }
            }
            return -1;
        }

        static void SetupCollisionMatrix(int ballLayer, int lidLayer, int projLayer)
        {
            // LabyrinthLid collides ONLY with LabyrinthBall.
            for (var i = 0; i < 32; i++)
                Physics.IgnoreLayerCollision(lidLayer, i, i != ballLayer);
            // Projectile does NOT collide with LabyrinthLid (already true from the loop above,
            // set explicitly so intent is clear and it holds even if lidLayer == ballLayer somehow).
            Physics.IgnoreLayerCollision(projLayer, lidLayer, true);
        }

        static void SetupProjectile(int projLayer, StringBuilder r)
        {
            var contents = PrefabUtility.LoadPrefabContents(ProjectilePath);
            contents.layer = projLayer;
            var rb = contents.GetComponent<Rigidbody>();
            if (rb != null) rb.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            PrefabUtility.SaveAsPrefabAsset(contents, ProjectilePath);
            PrefabUtility.UnloadPrefabContents(contents);
            r.AppendLine($"projectile prefab: layer={projLayer}, collisionDetectionMode={(rb != null ? "ContinuousDynamic" : "no Rigidbody found")}");
        }

        static bool Near(Vector3 a, Vector3 b) => (a - b).sqrMagnitude < Tol * Tol * 3f;
        static string F(Vector3 v) => $"({v.x:0.000}, {v.y:0.000}, {v.z:0.000})";
    }
}
