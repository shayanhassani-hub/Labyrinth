// ServiceArmBuilder.cs - assembles Hero 01b, the ceiling service arm, in the open scene and saves it as a prefab.
//
// Menu:  Tools > Labyrinth > ServiceArm: Apply Import Settings   (models + textures, hero mode)
//        Tools > Labyrinth > Build ServiceArm                     (Build(): material, hierarchy, driver, prefab, Verify())
//        Tools > Labyrinth > Verify ServiceArm                    (Verify())
// Code:  LabyrinthVR.EnvironmentTools.ServiceArmBuilder.ApplyImportSettings() / Build() / Verify()
//
// Source of truth: Documentation/HERO_SPEC.md section 4; build notes Documentation/Heroes/ServiceArm_BUILD.md.
// Meshes: Tools/Blender/heroes/servicearm_export.py (hero export mode, EXPORT_CONTRACT.md), every part modelled in
// the STOWED pose with its origin on its hinge; textures: servicearm_tex.py.
//
//   HERO_ServiceArm (0, 0, 0), yaw 0                    ServiceArmDriver (joints wired below)
//     Mount     (0, 4.00, 5.30)    ceiling face
//       Turret    (0, -0.07, 0)      yaw   about Y
//         UpperArm  (0, -0.16, 0)      pitch about X
//           Forearm   (0.12, 0, 1.00)    pitch about X
//             Wrist     (0.10, 0, -0.90)   pitch about X
//               ToolHead  (0, 0, -0.078)     roll  about Z
// The builder leaves the arm in the working pose (ServiceArmDriver's values); Play starts the idle from there.
//
// One material M_LAB_HERO_ServiceArm (URP Lit, metallic workflow) exactly as the Gate: BaseColor, Normal (OpenGL),
// Mask (R metallic, G AO, A smoothness) in the Metallic and the Occlusion slot, Emission map at intensity 1.
// Colliders: none. The arm hangs 2.04 m or higher over the docked drone, out of reach and outside the teleport
// floor; nothing in the sequence needs to hit it (decision in ServiceArm_BUILD.md). Verify fails on any collider.
// It replaces an existing HERO_ServiceArm, never saves the scene, one Undo step. The prefab
// Assets/Environment/Heroes/ServiceArm/HERO_ServiceArm.prefab is written (AssetDatabase).

using System.Collections.Generic;
using System.Linq;
using System.Text;
using LabyrinthVR.Gameplay;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace LabyrinthVR.EnvironmentTools
{
    public static class ServiceArmBuilder
    {
        const string Dir = "Assets/Environment/Heroes/ServiceArm/";
        const string TexDir = Dir + "Textures/";
        const string MatPath = Dir + "M_LAB_HERO_ServiceArm.mat";
        const string MatName = "M_LAB_HERO_ServiceArm";
        const string PrefabPath = Dir + "HERO_ServiceArm.prefab";
        const string RootName = "HERO_ServiceArm", UndoName = "Build ServiceArm";
        const string Hero = "LAB_HERO_ServiceArm_";

        // Hand-tuned values (owner may change in the Editor or here)
        public static float EmissionIntensity = 1.0f;     // the cyan strips must not clip to white
        public static int MaxTextureSize = 1024;          // H2b (owner): one 1024 sheet at 512 px/m

        // part -> (fbx, parent, local position, triangles) - HERO_SPEC section 4 chain, servicearm_kin.py
        static readonly (string fbx, string name, string parent, Vector3 local, int tris)[] Parts =
        {
            (Hero + "Mount_01", "Mount", null, new Vector3(0f, 4.00f, 5.30f), 420),
            (Hero + "Turret_01", "Turret", "Mount", new Vector3(0f, -0.07f, 0f), 936),
            (Hero + "UpperArm_01", "UpperArm", "Turret", new Vector3(0f, -0.16f, 0f), 1628),
            (Hero + "Forearm_01", "Forearm", "UpperArm", new Vector3(0.12f, 0f, 1.00f), 1425),
            (Hero + "Wrist_01", "Wrist", "Forearm", new Vector3(0.10f, 0f, -0.90f), 564),
            (Hero + "ToolHead_01", "ToolHead", "Wrist", new Vector3(0f, 0f, -0.078f), 272),
        };

        // Tool tip in ToolHead space and the HERO_SPEC 4 targets the Verify checks against
        static readonly Vector3 ToolTipLocal = new Vector3(0f, 0f, -0.20f);
        static readonly Vector3 WorkingTip = new Vector3(0f, 2.04f, 4.69f);
        const float StowY0 = 3.60f, StowY1 = 3.95f;   // owner decision 2026-11-03 (HERO_SPEC 4 change at merge)

        static readonly (string map, bool srgb, bool normal, TextureImporterFormat astc)[] Maps =
        {
            ("BaseColor", true, false, TextureImporterFormat.ASTC_6x6),
            ("Normal", false, true, TextureImporterFormat.ASTC_4x4),
            ("Mask", false, false, TextureImporterFormat.ASTC_6x6),
            ("Emission", true, false, TextureImporterFormat.ASTC_6x6),
        };

        static string TexPath(string map) => $"{TexDir}T_LAB_HERO_ServiceArm_{map}.png";

        // ----------------------------------------------------------------- import settings

        [MenuItem("Tools/Labyrinth/ServiceArm: Apply Import Settings")]
        static void ImportFromMenu() => Debug.Log(ApplyImportSettings());

        /// EXPORT_CONTRACT.md importer settings, hero mode (normals and tangents from the FBX), and the ASSET_RULES
        /// texture settings - identical to GateBuilder. Confirm with git diff on the .meta files afterwards.
        public static string ApplyImportSettings()
        {
            var r = new StringBuilder("[ServiceArmBuilder] import settings\n");
            foreach (var p in Parts)
            {
                var mi = AssetImporter.GetAtPath(Dir + p.fbx + ".fbx") as ModelImporter;
                if (mi == null) { r.AppendLine($"FAIL no model importer for {Dir}{p.fbx}.fbx"); continue; }
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
                r.AppendLine($"PASS model import settings {p.fbx}");
            }
            foreach (var m in Maps)
            {
                var ti = AssetImporter.GetAtPath(TexPath(m.map)) as TextureImporter;
                if (ti == null) { r.AppendLine($"FAIL no texture importer for {TexPath(m.map)}"); continue; }
                ti.textureType = m.normal ? TextureImporterType.NormalMap : TextureImporterType.Default;
                ti.sRGBTexture = m.srgb;
                ti.alphaSource = m.map == "Mask" ? TextureImporterAlphaSource.FromInput : TextureImporterAlphaSource.None;
                ti.alphaIsTransparency = false;
                ti.mipmapEnabled = true;
                ti.wrapMode = TextureWrapMode.Repeat;
                ti.maxTextureSize = MaxTextureSize;
                var android = ti.GetPlatformTextureSettings("Android");
                android.overridden = true;
                android.maxTextureSize = MaxTextureSize;
                android.format = m.astc;
                ti.SetPlatformTextureSettings(android);
                ti.SaveAndReimport();
                r.AppendLine($"PASS texture import settings {m.map}: {(m.normal ? "normal map" : m.srgb ? "sRGB" : "linear")}, " +
                             $"mipmaps, Android {m.astc} max {MaxTextureSize}");
            }
            return r.ToString();
        }

        // ----------------------------------------------------------------- material

        static Material LoadOrCreateMaterial(StringBuilder r)
        {
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) { r.AppendLine("FAIL URP Lit shader not found"); return null; }
            var tex = new Dictionary<string, Texture2D>();
            foreach (var m in Maps)
            {
                var t = AssetDatabase.LoadAssetAtPath<Texture2D>(TexPath(m.map));
                if (t == null) { r.AppendLine($"FAIL missing {TexPath(m.map)}"); return null; }
                tex[m.map] = t;
            }
            var mat = AssetDatabase.LoadAssetAtPath<Material>(MatPath);
            var created = mat == null;
            if (created) mat = new Material(shader);
            else mat.shader = shader;

            mat.SetFloat("_WorkflowMode", 1f);
            mat.SetTexture("_BaseMap", tex["BaseColor"]);
            mat.SetColor("_BaseColor", Color.white);
            mat.SetTexture("_BumpMap", tex["Normal"]);
            mat.SetFloat("_BumpScale", 1f);
            mat.EnableKeyword("_NORMALMAP");
            mat.SetTexture("_MetallicGlossMap", tex["Mask"]);
            mat.SetFloat("_SmoothnessTextureChannel", 0f);
            mat.SetFloat("_Smoothness", 1f);
            mat.EnableKeyword("_METALLICSPECGLOSSMAP");
            mat.SetTexture("_OcclusionMap", tex["Mask"]);
            mat.SetFloat("_OcclusionStrength", 1f);
            mat.EnableKeyword("_OCCLUSIONMAP");
            mat.SetTexture("_EmissionMap", tex["Emission"]);
            mat.SetColor("_EmissionColor", Color.white * EmissionIntensity);
            mat.EnableKeyword("_EMISSION");
            mat.globalIlluminationFlags = MaterialGlobalIlluminationFlags.BakedEmissive;

            if (created) { AssetDatabase.CreateAsset(mat, MatPath); r.AppendLine($"created {MatPath}"); }
            else { EditorUtility.SetDirty(mat); r.AppendLine($"updated {MatPath}"); }
            AssetDatabase.SaveAssets();
            return mat;
        }

        // ----------------------------------------------------------------- build

        [MenuItem("Tools/Labyrinth/Build ServiceArm")]
        static void BuildFromMenu() => Log(Build());

        [MenuItem("Tools/Labyrinth/Verify ServiceArm")]
        static void VerifyFromMenu() => Log(Verify());

        static void Log(string report)
        {
            if (report.Contains("RESULT: PASS")) Debug.Log(report); else Debug.LogError(report);
        }

        public static string Build()
        {
            var r = new StringBuilder();
            var scene = SceneManager.GetActiveScene();
            r.AppendLine($"[ServiceArmBuilder] scene: {scene.path}");

            var assets = new Dictionary<string, GameObject>();
            foreach (var p in Parts)
            {
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(Dir + p.fbx + ".fbx");
                if (go == null) return r.AppendLine($"FAIL missing {Dir}{p.fbx}.fbx\nRESULT: FAIL (scene unchanged)").ToString();
                assets[p.name] = go;
            }
            var mat = LoadOrCreateMaterial(r);
            if (mat == null) return r.AppendLine("RESULT: FAIL (scene unchanged)").ToString();

            Undo.IncrementCurrentGroup();
            var group = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName(UndoName);
            var old = scene.GetRootGameObjects().Where(g => g.name == RootName).ToList();
            foreach (var g in old) Undo.DestroyObjectImmediate(g);

            var root = new GameObject(RootName);
            Undo.RegisterCreatedObjectUndo(root, UndoName);
            root.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);

            var placed = new Dictionary<string, Transform>();
            foreach (var p in Parts)
            {
                var parent = p.parent == null ? root.transform : placed[p.parent];
                placed[p.name] = Place(assets[p.name], parent, p.name, p.local, mat).transform;
            }

            var drv = root.AddComponent<ServiceArmDriver>();
            drv.turret = placed["Turret"];
            drv.upperArm = placed["UpperArm"];
            drv.forearm = placed["Forearm"];
            drv.wrist = placed["Wrist"];
            drv.toolHead = placed["ToolHead"];
            ApplyPose(drv, drv.workTurretYaw, drv.workShoulder, drv.workElbow, drv.workWrist, 0f);

            var prefab = PrefabUtility.SaveAsPrefabAssetAndConnect(root, PrefabPath, InteractionMode.UserAction);
            Undo.CollapseUndoOperations(group);
            EditorSceneManager.MarkSceneDirty(scene);
            r.AppendLine(prefab != null ? $"saved prefab {PrefabPath}" : $"FAIL prefab {PrefabPath} not saved");
            r.AppendLine($"built {RootName}{(old.Count > 0 ? $" (replaced {old.Count})" : "")}");
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

        // the same joint convention as ServiceArmDriver.Apply
        static void ApplyPose(ServiceArmDriver d, float yaw, float shoulder, float elbow, float wrist, float roll)
        {
            d.turret.localRotation = Quaternion.Euler(0f, yaw, 0f);
            d.upperArm.localRotation = Quaternion.Euler(shoulder, 0f, 0f);
            d.forearm.localRotation = Quaternion.Euler(elbow, 0f, 0f);
            d.wrist.localRotation = Quaternion.Euler(wrist, 0f, 0f);
            d.toolHead.localRotation = Quaternion.Euler(0f, 0f, roll);
        }

        // ----------------------------------------------------------------- verify

        public static string Verify()
        {
            var r = new StringBuilder("[ServiceArmBuilder] verify\n");
            var root = GameObject.Find("/" + RootName);
            if (root == null) return r.AppendLine("FAIL no HERO_ServiceArm\nRESULT: FAIL").ToString();
            var pass = true;
            void Check(bool ok, string line) { pass &= ok; r.AppendLine($"{(ok ? "PASS" : "FAIL")} {line}"); }

            var found = new Dictionary<string, Transform>();
            foreach (var p in Parts)
            {
                var t = root.GetComponentsInChildren<Transform>(true).FirstOrDefault(x => x.name == p.name);
                if (t == null) { Check(false, $"{p.name} missing"); continue; }
                found[p.name] = t;
                var expectParent = p.parent == null ? root.transform : found.TryGetValue(p.parent, out var pp) ? pp : null;
                Check(t.parent == expectParent, $"{p.name}: parent {(t.parent != null ? t.parent.name : "none")} (expected {(p.parent ?? RootName)})");
                var mf = t.GetComponent<MeshFilter>(); var mr = t.GetComponent<MeshRenderer>();
                var mesh = mf != null ? mf.sharedMesh : null;
                var tris = mesh != null ? mesh.triangles.Length / 3 : -1;
                Check(tris == p.tris && mesh.subMeshCount == 1, $"{p.name}: {tris} tris (build table {p.tris}), submeshes {(mesh != null ? mesh.subMeshCount : 0)}");
                Check((t.localPosition - p.local).magnitude < 1e-4f && t.localScale == Vector3.one,
                      $"{p.name}: local position {F(t.localPosition)} (chain {F(p.local)}), scale 1");
                Check(mr != null && mr.sharedMaterial != null && mr.sharedMaterial.name == MatName,
                      $"{p.name}: material {(mr != null && mr.sharedMaterial != null ? mr.sharedMaterial.name : "none")}");
                if (mesh != null) r.AppendLine($"INFO {p.name}: tangents {(mesh.tangents.Length > 0 ? "yes" : "NO")}, uv0 {(mesh.uv.Length > 0 ? "yes" : "NO")}");
            }
            Check(!root.GetComponentsInChildren<Collider>(true).Any(), "no colliders (arm out of reach; see ServiceArm_BUILD.md)");

            var drv = root.GetComponent<ServiceArmDriver>();
            var wired = drv != null && found.Count == Parts.Length && drv.turret == found["Turret"] && drv.upperArm == found["UpperArm"]
                        && drv.forearm == found["Forearm"] && drv.wrist == found["Wrist"] && drv.toolHead == found["ToolHead"];
            Check(wired, "ServiceArmDriver on the root, joints wired");
            if (wired)
            {
                Check(Mathf.Approximately(drv.foldDelay, 2.5f) && Mathf.Approximately(drv.foldDuration, 2.0f)
                      && drv.idleTurretAmplitude <= 10f + 1e-4f && drv.idleWristAmplitude <= 15f + 1e-4f,
                      $"driver timings: fold delay {drv.foldDelay} s, fold {drv.foldDuration} s, idle turret +-{drv.idleTurretAmplitude}, wrist +-{drv.idleWristAmplitude} (HERO_SPEC 4)");
                var saved = found.Values.ToDictionary(t => t, t => t.localRotation);
                try
                {
                    ApplyPose(drv, drv.workTurretYaw, drv.workShoulder, drv.workElbow, drv.workWrist, 0f);
                    var tip = found["ToolHead"].TransformPoint(ToolTipLocal);
                    Check((tip - WorkingTip).magnitude < 0.005f, $"working pose: tool tip {F(tip)} (target {F(WorkingTip)}, drone top y 1.986)");
                    ApplyPose(drv, drv.stowTurretYaw, drv.stowShoulder, drv.stowElbow, drv.stowWrist, drv.stowRoll);
                    float y0 = float.MaxValue, y1 = float.MinValue;
                    foreach (var p in Parts.Where(p => p.name != "Mount"))
                    {
                        var b = found[p.name].GetComponent<MeshRenderer>().bounds;
                        y0 = Mathf.Min(y0, b.min.y); y1 = Mathf.Max(y1, b.max.y);
                    }
                    Check(y0 >= StowY0 - 0.002f && y1 <= StowY1 + 0.002f, $"stowed pose: arm y {y0:0.000} .. {y1:0.000} (HERO_SPEC layer {StowY0} .. {StowY1})");
                }
                finally { foreach (var kv in saved) kv.Key.localRotation = kv.Value; }
            }

            var mat = AssetDatabase.LoadAssetAtPath<Material>(MatPath);
            Check(mat != null && mat.IsKeywordEnabled("_NORMALMAP") && mat.IsKeywordEnabled("_METALLICSPECGLOSSMAP")
                  && mat.IsKeywordEnabled("_OCCLUSIONMAP") && mat.IsKeywordEnabled("_EMISSION"),
                  "material keywords _NORMALMAP _METALLICSPECGLOSSMAP _OCCLUSIONMAP _EMISSION");
            foreach (var m in Maps)
            {
                var ti = AssetImporter.GetAtPath(TexPath(m.map)) as TextureImporter;
                var a = ti != null ? ti.GetPlatformTextureSettings("Android") : null;
                Check(ti != null && (m.normal || ti.sRGBTexture == m.srgb)
                      && (ti.textureType == TextureImporterType.NormalMap) == m.normal && ti.mipmapEnabled
                      && a.overridden && a.format == m.astc,
                      $"texture {m.map}: {(ti == null ? "missing" : $"{ti.textureType}, sRGB {ti.sRGBTexture}, mipmaps {ti.mipmapEnabled}, Android {a.format}")}");
            }
            r.AppendLine(pass ? "RESULT: PASS - scene marked dirty, NOT saved." : "RESULT: FAIL");
            return r.ToString();
        }

        static string F(Vector3 v) => $"({v.x:0.000}, {v.y:0.000}, {v.z:0.000})";
    }
}
