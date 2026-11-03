// LeverStandBuilder.cs - assembles Hero 02b, the lever stand, in the open scene and saves it as a prefab.
//
// Menu:  Tools > Labyrinth > LeverStand: Apply Import Settings   (models + textures, hero mode)
//        Tools > Labyrinth > Build LeverStand                     (Build(): material, hierarchy, prefab, Verify())
//        Tools > Labyrinth > Verify LeverStand                    (Verify())
// Code:  LabyrinthVR.EnvironmentTools.LeverStandBuilder.ApplyImportSettings() / Build() / Verify()
//
// Source of truth: Documentation/HERO_SPEC.md section 6; build notes Documentation/Heroes/LeverStand_BUILD.md.
// Meshes: Tools/Blender/heroes/leverstand_export.py (hero mode); textures: leverstand_tex.py (one 1024 set).
//
//   HERO_LeverStand  world (0.85, 0, 0.60), yaw 180 (front = local +Z faces the player)
//     Body    (0, 0, 0)               static; BoxColliders: pedestal 0.30 x 0.95 x 0.30, housing 0.22 x 0.08 x 0.16
//     Lever   (0.041, 0.995, -0.010)  the hinge; rotates about local X: rest -30, pulled +30 (HERO_SPEC "+30 away
//                                     from the player" in world axes); CapsuleCollider on the grip, kinematic
//                                     Rigidbody, XRSimpleInteractable, LeverHandle
//     Lamp    (-0.055, 1.040, -0.035) LeverLamp (MaterialPropertyBlock), no collider (inside the cage)
//
// One material M_LAB_HERO_LeverStand (URP Lit, metallic workflow): BaseColor, Normal (OpenGL), Mask (R metallic,
// G AO, A smoothness: same texture in the Metallic and Occlusion slots), Emission (cyan strip + amber lamp; the lamp's
// share is scaled per renderer by LeverLamp). Colliders are primitives only. Replaces an existing HERO_LeverStand,
// never saves the scene, one Undo step. Prefab: Assets/Environment/Heroes/LeverStand/HERO_LeverStand.prefab.
// FacilitySequence (not written) calls LeverHandle.Arm() once the service arm is stowed and listens to onPulled.

using System.Collections.Generic;
using System.Linq;
using System.Text;
using LabyrinthVR.Gameplay;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.XR.Interaction.Toolkit.Interactables;

namespace LabyrinthVR.EnvironmentTools
{
    public static class LeverStandBuilder
    {
        const string Dir = "Assets/Environment/Heroes/LeverStand/";
        const string TexDir = Dir + "Textures/";
        const string MatPath = Dir + "M_LAB_HERO_LeverStand.mat";
        const string PrefabPath = Dir + "HERO_LeverStand.prefab";
        const string RootName = "HERO_LeverStand", UndoName = "Build LeverStand";
        const string Hero = "LAB_HERO_LeverStand_";

        // Hand-tuned values (owner may change in the Editor or here)
        public static float EmissionIntensity = 1.0f;     // the cyan strip must not clip to white
        public static int MaxTextureSize = 1024;          // the set is authored at 1024 (575 px/m, BUILD.md)

        // HERO_SPEC section 6 placement
        static readonly Vector3 RootPosition = new Vector3(0.85f, 0f, 0.60f);
        static readonly Quaternion RootRotation = Quaternion.Euler(0f, 180f, 0f);

        // part -> (child name, stand-local origin, triangles); triangle counts from leverstand_export.py check
        static readonly (string fbx, string name, Vector3 origin, int tris)[] Parts =
        {
            (Hero + "Body_01", "Body", Vector3.zero, BodyTris),
            (Hero + "Lever_01", "Lever", new Vector3(0.041f, 0.995f, -0.010f), LeverTris),
            (Hero + "Lamp_01", "Lamp", new Vector3(-0.055f, 1.040f, -0.035f), LampTris),
        };
        const int BodyTris = 836, LeverTris = 206, LampTris = 58;   // leverstand_export.py check (H3a)

        // Primitive colliders (part-local)
        static readonly Vector3 PedestalCenter = new Vector3(0f, 0.475f, 0f), PedestalSize = new Vector3(0.30f, 0.95f, 0.30f);
        static readonly Vector3 HousingCenter = new Vector3(0f, 0.99f, 0f), HousingSize = new Vector3(0.22f, 0.08f, 0.16f);
        // grip: Ø 0.05 x 0.10 on top of the 0.22 shaft (lever-local, upright mesh)
        static readonly Vector3 GripCenter = new Vector3(0f, 0.27f, 0f);
        const float GripRadius = 0.03f, GripHeight = 0.12f;  // 5 mm larger than the grip: easier to grab

        const float RestAngle = -30f, PulledAngle = 30f, TriggerFraction = 0.8f;

        static readonly (string map, bool srgb, bool normal, TextureImporterFormat astc)[] Maps =
        {
            ("BaseColor", true, false, TextureImporterFormat.ASTC_6x6),
            ("Normal", false, true, TextureImporterFormat.ASTC_4x4),
            ("Mask", false, false, TextureImporterFormat.ASTC_6x6),
            ("Emission", true, false, TextureImporterFormat.ASTC_6x6),
        };

        static string TexPath(string map) => $"{TexDir}T_LAB_HERO_LeverStand_{map}.png";

        // ----------------------------------------------------------------- import settings

        [MenuItem("Tools/Labyrinth/LeverStand: Apply Import Settings")]
        static void ImportFromMenu() => Debug.Log(ApplyImportSettings());

        /// EXPORT_CONTRACT.md importer settings, hero mode, and the ASSET_RULES texture settings.
        /// Confirm with git diff on the .meta files afterwards.
        public static string ApplyImportSettings()
        {
            var r = new StringBuilder("[LeverStandBuilder] import settings\n");
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
            mat.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;   // the lamp switches at runtime

            if (created) { AssetDatabase.CreateAsset(mat, MatPath); r.AppendLine($"created {MatPath}"); }
            else { EditorUtility.SetDirty(mat); r.AppendLine($"updated {MatPath}"); }
            AssetDatabase.SaveAssets();
            return mat;
        }

        // ----------------------------------------------------------------- build

        [MenuItem("Tools/Labyrinth/Build LeverStand")]
        static void BuildFromMenu() => Log(Build());

        [MenuItem("Tools/Labyrinth/Verify LeverStand")]
        static void VerifyFromMenu() => Log(Verify());

        static void Log(string report)
        {
            if (report.Contains("RESULT: PASS")) Debug.Log(report); else Debug.LogError(report);
        }

        public static string Build()
        {
            var r = new StringBuilder();
            var scene = SceneManager.GetActiveScene();
            r.AppendLine($"[LeverStandBuilder] scene: {scene.path}");

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
            root.transform.SetPositionAndRotation(RootPosition, RootRotation);

            var placed = new Dictionary<string, GameObject>();
            foreach (var p in Parts) placed[p.name] = Place(assets[p.name], root.transform, p.name, p.origin, mat);

            // Body: static, two boxes (pedestal, housing)
            var body = placed["Body"];
            GameObjectUtility.SetStaticEditorFlags(body, StaticEditorFlags.BatchingStatic | StaticEditorFlags.ContributeGI
                                                         | StaticEditorFlags.OccluderStatic | StaticEditorFlags.OccludeeStatic
                                                         | StaticEditorFlags.ReflectionProbeStatic);
            var ped = body.AddComponent<BoxCollider>(); ped.center = PedestalCenter; ped.size = PedestalSize;
            var hou = body.AddComponent<BoxCollider>(); hou.center = HousingCenter; hou.size = HousingSize;

            // Lamp: emission driven per renderer
            var lamp = placed["Lamp"].AddComponent<LeverLamp>();
            lamp.mode = LeverLamp.Mode.Off;

            // Lever: grip capsule, kinematic body, XRI select, hinge script
            var lever = placed["Lever"];
            lever.transform.localRotation = Quaternion.Euler(RestAngle, 0f, 0f);
            var cap = lever.AddComponent<CapsuleCollider>();
            cap.direction = 1; cap.center = GripCenter; cap.radius = GripRadius; cap.height = GripHeight;
            var rb = lever.AddComponent<Rigidbody>();
            rb.isKinematic = true; rb.useGravity = false;
            var interactable = lever.AddComponent<XRSimpleInteractable>();
            var handle = lever.AddComponent<LeverHandle>();
            handle.interactable = interactable;
            handle.hinge = lever.transform;
            handle.lamp = lamp;
            handle.restAngle = RestAngle; handle.pulledAngle = PulledAngle; handle.triggerFraction = TriggerFraction;

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

        // ----------------------------------------------------------------- verify

        public static string Verify()
        {
            var r = new StringBuilder("[LeverStandBuilder] verify\n");
            var root = GameObject.Find("/" + RootName);
            if (root == null) return r.AppendLine("FAIL no HERO_LeverStand\nRESULT: FAIL").ToString();
            var pass = true;
            void Check(bool ok, string line) { pass &= ok; r.AppendLine($"{(ok ? "PASS" : "FAIL")} {line}"); }

            Check((root.transform.position - RootPosition).magnitude < 1e-4f && Quaternion.Angle(root.transform.rotation, RootRotation) < 0.01f
                  && root.transform.localScale == Vector3.one,
                  $"root at {F(root.transform.position)}, yaw {root.transform.eulerAngles.y:0.0} (HERO_SPEC (0.850, 0.000, 0.600), 180)");
            foreach (var p in Parts)
            {
                var t = root.transform.Find(p.name);
                if (t == null) { Check(false, $"{p.name} missing"); continue; }
                var mf = t.GetComponent<MeshFilter>(); var mr = t.GetComponent<MeshRenderer>();
                var tris = mf != null && mf.sharedMesh != null ? mf.sharedMesh.triangles.Length / 3 : -1;
                Check(tris == p.tris, $"{p.name}: {tris} tris (export {p.tris}), submeshes {(mf != null && mf.sharedMesh != null ? mf.sharedMesh.subMeshCount : 0)}");
                Check((t.localPosition - p.origin).magnitude < 1e-4f && t.localScale == Vector3.one,
                      $"{p.name}: origin {F(t.localPosition)} (stand-local {F(p.origin)}), scale 1");
                Check(mr != null && mr.sharedMaterial != null && mr.sharedMaterial.name == "M_LAB_HERO_LeverStand",
                      $"{p.name}: material {(mr != null && mr.sharedMaterial != null ? mr.sharedMaterial.name : "none")}");
                Check(!t.GetComponentsInChildren<MeshCollider>(true).Any(), $"{p.name}: no mesh colliders");
                if (mf != null && mf.sharedMesh != null)
                    r.AppendLine($"INFO {p.name}: world bounds {F(mr.bounds.min)}..{F(mr.bounds.max)}, tangents {(mf.sharedMesh.tangents.Length > 0 ? "yes" : "NO")}");
            }

            // HERO_SPEC section 6/8: the pedestal's -X world face stays 0.15 from the panel's +X edge (x 0.55)
            var bodyT = root.transform.Find("Body");
            if (bodyT != null)
            {
                var b = bodyT.GetComponent<MeshRenderer>().bounds;
                Check(b.min.x > 0.55f + 0.15f - 0.002f, $"Body world x {b.min.x:0.000} .. {b.max.x:0.000}: >= 0.15 from the panel's +X edge (0.550)");
                Check(Mathf.Abs(b.min.y) < 0.002f && Mathf.Abs(b.max.y - 1.1155f) < 0.003f, $"Body world y {b.min.y:0.000} .. {b.max.y:0.000} (export check 0.000 .. 1.116: cage top)");
            }

            var lever = root.transform.Find("Lever");
            var h = lever != null ? lever.GetComponent<LeverHandle>() : null;
            Check(h != null && h.interactable != null && h.hinge == lever && h.lamp != null, "Lever: LeverHandle wired (interactable, hinge, lamp)");
            Check(h != null && Mathf.Approximately(h.restAngle, RestAngle) && Mathf.Approximately(h.pulledAngle, PulledAngle)
                  && Mathf.Approximately(h.triggerFraction, TriggerFraction),
                  $"Lever travel {(h != null ? $"{h.restAngle} .. {h.pulledAngle}, trigger {h.triggerFraction:0.00} ({h.TriggerAngle:0.0} deg)" : "-")}");
            Check(lever != null && Quaternion.Angle(lever.localRotation, Quaternion.Euler(RestAngle, 0f, 0f)) < 0.01f, "Lever at rest (-30 local X)");
            if (lever != null)
            {
                // rest leans AWAY from the player (world +Z), pulled toward the player (world -Z)
                var up = lever.up;
                Check(up.z > 0.4f, $"Lever rest direction {F(up)}: leans toward world +Z (away from the player)");
                var cap = lever.GetComponent<CapsuleCollider>();
                Check(cap != null && lever.GetComponent<Rigidbody>() != null && lever.GetComponent<Rigidbody>().isKinematic,
                      "Lever: grip CapsuleCollider + kinematic Rigidbody");
            }
            var lamp = root.transform.Find("Lamp");
            Check(lamp != null && lamp.GetComponent<LeverLamp>() != null && lamp.GetComponent<Collider>() == null, "Lamp: LeverLamp, no collider");

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
