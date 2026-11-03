// GateBuilder.cs - assembles Hero 03, the facility gate, in the open scene and saves it as a prefab.
//
// Menu:  Tools > Labyrinth > Gate: Apply Import Settings   (models + textures, hero mode)
//        Tools > Labyrinth > Build Gate                     (Build(): material, hierarchy, prefab, Verify())
//        Tools > Labyrinth > Verify Gate                    (Verify())
// Code:  LabyrinthVR.EnvironmentTools.GateBuilder.ApplyImportSettings() / Build() / Verify()
//
// Source of truth: Documentation/HERO_SPEC.md section 7. Meshes: Tools/Blender/heroes/gate_export.py
// (hero export mode, EXPORT_CONTRACT.md); textures: Tools/Blender/heroes/gate_tex.py (G2c).
//
//   HERO_Gate (0, 0, 0), yaw 0 - every part sits at its HERO_SPEC origin (Unity world = root space)
//     Leaf         (-0.150, 0.010, 7.910)  BoxCollider + kinematic Rigidbody, SlideDriver (-X 1.70 m, 2.0 s)
//     Rail         (-1.800, 2.475, 8.000)  no collider (above reach, nothing collides with it)
//     ButtonPanel  (-2.000, 1.200, 8.700)  BoxCollider
//     Button       (-1.893, 1.235, 8.700)  BoxCollider, XRSimpleInteractable, GateButton (-X 0.008)
//                                          GateButton.onPressed -> Leaf SlideDriver.Open (persistent)
//
// One material M_LAB_HERO_Gate (URP Lit, metallic workflow): BaseColor, Normal (OpenGL), Mask
// (R metallic, G AO, A smoothness: the same texture in the Metallic and the Occlusion slot,
// ASSET_RULES), Emission map with intensity 1 (the map carries the STYLE_GUIDE colour).
// Colliders are primitives only. It replaces an existing HERO_Gate, never saves the scene, one Undo
// step. The prefab asset Assets/Environment/Heroes/Gate/HERO_Gate.prefab is written (AssetDatabase).

using System.Collections.Generic;
using System.Linq;
using System.Text;
using LabyrinthVR.Gameplay;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.SceneManagement;
using UnityEngine.XR.Interaction.Toolkit.Interactables;

namespace LabyrinthVR.EnvironmentTools
{
    public static class GateBuilder
    {
        const string Dir = "Assets/Environment/Heroes/Gate/";
        const string TexDir = Dir + "Textures/";
        const string MatPath = Dir + "M_LAB_HERO_Gate.mat";
        const string PrefabPath = Dir + "HERO_Gate.prefab";
        const string RootName = "HERO_Gate", UndoName = "Build Gate";
        const string Hero = "LAB_HERO_Gate_";

        // Hand-tuned values (owner may change in the Editor or here)
        public static float EmissionIntensity = 1.0f;     // the light strip must not clip to white
        public static int MaxTextureSize = 2048;          // ASSET_RULES: authored at 2048, may ship at 1024 after the Quest test

        // HERO_SPEC section 7: part -> (child name, origin, triangles)
        static readonly (string fbx, string name, Vector3 origin, int tris)[] Parts =
        {
            (Hero + "Leaf_01", "Leaf", new Vector3(-0.15f, 0.010f, 7.91f), 1048),
            (Hero + "Rail_01", "Rail", new Vector3(-1.80f, 2.475f, 8.00f), 272),
            (Hero + "ButtonPanel_01", "ButtonPanel", new Vector3(-2.00f, 1.20f, 8.70f), 298),
            (Hero + "Button_01", "Button", new Vector3(-1.893f, 1.235f, 8.70f), 118),
        };

        // Primitive colliders, part-local (from the exported mesh bounds, gate_export.py check)
        static readonly Vector3 LeafBoxCenter = new Vector3(-0.85f, 1.225f, 0f), LeafBoxSize = new Vector3(1.70f, 2.45f, 0.06f);
        static readonly Vector3 PanelBoxCenter = new Vector3(0.0475f, 0f, 0f), PanelBoxSize = new Vector3(0.095f, 0.30f, 0.22f);
        static readonly Vector3 ButtonBoxCenter = new Vector3(-0.0185f, 0f, 0f), ButtonBoxSize = new Vector3(0.037f, 0.07f, 0.07f);

        const float LeafTravel = 1.70f, LeafDuration = 2.0f, ButtonTravel = 0.008f;

        // map -> (sRGB, normal map, Android ASTC block) - ASSET_RULES: 6x6 colour/mask, 4x4 normal
        static readonly (string map, bool srgb, bool normal, TextureImporterFormat astc)[] Maps =
        {
            ("BaseColor", true, false, TextureImporterFormat.ASTC_6x6),
            ("Normal", false, true, TextureImporterFormat.ASTC_4x4),
            ("Mask", false, false, TextureImporterFormat.ASTC_6x6),
            ("Emission", true, false, TextureImporterFormat.ASTC_6x6),
        };

        static string TexPath(string map) => $"{TexDir}T_LAB_HERO_Gate_{map}.png";

        // ----------------------------------------------------------------- import settings

        [MenuItem("Tools/Labyrinth/Gate: Apply Import Settings")]
        static void ImportFromMenu() => Debug.Log(ApplyImportSettings());

        /// EXPORT_CONTRACT.md importer settings, hero mode (normals and tangents from the FBX), and the
        /// ASSET_RULES texture settings. Confirm with git diff on the .meta files afterwards.
        public static string ApplyImportSettings()
        {
            var r = new StringBuilder("[GateBuilder] import settings\n");
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
                ti.sRGBTexture = m.srgb;                                   // normal maps are always linear
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

            mat.SetFloat("_WorkflowMode", 1f);                                    // metallic
            mat.SetTexture("_BaseMap", tex["BaseColor"]);
            mat.SetColor("_BaseColor", Color.white);
            mat.SetTexture("_BumpMap", tex["Normal"]);
            mat.SetFloat("_BumpScale", 1f);
            mat.EnableKeyword("_NORMALMAP");
            mat.SetTexture("_MetallicGlossMap", tex["Mask"]);                     // R metallic, A smoothness
            mat.SetFloat("_SmoothnessTextureChannel", 0f);                       // smoothness from the metallic map's alpha
            mat.SetFloat("_Smoothness", 1f);                                      // multiplier on the map's alpha
            mat.EnableKeyword("_METALLICSPECGLOSSMAP");
            mat.SetTexture("_OcclusionMap", tex["Mask"]);                         // URP Lit reads occlusion from G
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

        [MenuItem("Tools/Labyrinth/Build Gate")]
        static void BuildFromMenu() => Log(Build());

        [MenuItem("Tools/Labyrinth/Verify Gate")]
        static void VerifyFromMenu() => Log(Verify());

        static void Log(string report)
        {
            if (report.Contains("RESULT: PASS")) Debug.Log(report); else Debug.LogError(report);
        }

        public static string Build()
        {
            var r = new StringBuilder();
            var scene = SceneManager.GetActiveScene();
            r.AppendLine($"[GateBuilder] scene: {scene.path}");

            // Load everything first, so a missing asset changes nothing in the scene.
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

            var placed = new Dictionary<string, GameObject>();
            foreach (var p in Parts) placed[p.name] = Place(assets[p.name], root.transform, p.name, p.origin, mat);

            // Leaf: blocks the player and the teleport ray while closed; slides open
            var leaf = placed["Leaf"];
            var leafBox = leaf.AddComponent<BoxCollider>();
            leafBox.center = LeafBoxCenter; leafBox.size = LeafBoxSize;
            var rb = leaf.AddComponent<Rigidbody>();
            rb.isKinematic = true; rb.useGravity = false;
            var slide = leaf.AddComponent<SlideDriver>();
            slide.part = leaf.transform;
            slide.openOffset = new Vector3(-LeafTravel, 0f, 0f);
            slide.duration = LeafDuration;
            slide.easeInOut = true;

            var panelBox = placed["ButtonPanel"].AddComponent<BoxCollider>();
            panelBox.center = PanelBoxCenter; panelBox.size = PanelBoxSize;

            // Button: XRI select (ray / near-far; poke once the rig has a poke interactor) -> press -> leaf opens
            var button = placed["Button"];
            var buttonBox = button.AddComponent<BoxCollider>();
            buttonBox.center = ButtonBoxCenter; buttonBox.size = ButtonBoxSize;
            var interactable = button.AddComponent<XRSimpleInteractable>();
            var gb = button.AddComponent<GateButton>();
            gb.interactable = interactable;
            gb.cap = button.transform;
            gb.pressOffset = new Vector3(-ButtonTravel, 0f, 0f);
            UnityEventTools.AddPersistentListener(gb.onPressed, new UnityAction(slide.Open));

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
            var r = new StringBuilder("[GateBuilder] verify\n");
            var root = GameObject.Find("/" + RootName);
            if (root == null) return r.AppendLine("FAIL no HERO_Gate\nRESULT: FAIL").ToString();
            var pass = true;
            void Check(bool ok, string line) { pass &= ok; r.AppendLine($"{(ok ? "PASS" : "FAIL")} {line}"); }

            foreach (var p in Parts)
            {
                var t = root.transform.Find(p.name);
                if (t == null) { Check(false, $"{p.name} missing"); continue; }
                var mf = t.GetComponent<MeshFilter>(); var mr = t.GetComponent<MeshRenderer>();
                var tris = mf != null && mf.sharedMesh != null ? mf.sharedMesh.triangles.Length / 3 : -1;
                Check(tris == p.tris, $"{p.name}: {tris} tris (HERO_SPEC {p.tris}), submeshes {(mf != null && mf.sharedMesh != null ? mf.sharedMesh.subMeshCount : 0)}");
                Check((t.localPosition - p.origin).magnitude < 1e-4f && t.localRotation == Quaternion.identity && t.localScale == Vector3.one,
                      $"{p.name}: origin {F(t.localPosition)} (HERO_SPEC {F(p.origin)}), rotation 0, scale 1");
                Check(mr != null && mr.sharedMaterial != null && mr.sharedMaterial.name == "M_LAB_HERO_Gate",
                      $"{p.name}: material {(mr != null && mr.sharedMaterial != null ? mr.sharedMaterial.name : "none")}");
                Check(!t.GetComponentsInChildren<MeshCollider>(true).Any(), $"{p.name}: no mesh colliders");
                if (mf != null && mf.sharedMesh != null)
                    r.AppendLine($"INFO {p.name}: world bounds {F(mr.bounds.min)}..{F(mr.bounds.max)}, tangents {(mf.sharedMesh.tangents.Length > 0 ? "yes" : "NO")}");
            }

            var leaf = root.transform.Find("Leaf");
            var slide = leaf != null ? leaf.GetComponent<SlideDriver>() : null;
            Check(slide != null && Mathf.Approximately(slide.openOffset.x, -LeafTravel) && Mathf.Approximately(slide.duration, LeafDuration),
                  $"Leaf SlideDriver: open offset {(slide != null ? F(slide.openOffset) : "-")}, {(slide != null ? slide.duration : 0f)} s");
            Check(leaf != null && leaf.GetComponent<Rigidbody>() != null && leaf.GetComponent<Rigidbody>().isKinematic, "Leaf kinematic Rigidbody");
            if (leaf != null)
            {
                var mr = leaf.GetComponent<MeshRenderer>();
                var saved = leaf.localPosition;
                try
                {
                    leaf.localPosition = saved + new Vector3(-LeafTravel, 0f, 0f);
                    var b = mr.bounds;
                    // HERO_SPEC section 7: open, the leaf covers x -3.55 ... -1.85 (the hangers and rollers inside)
                    Check(Mathf.Abs(b.min.x + 3.55f) < 0.002f && Mathf.Abs(b.max.x + 1.85f) < 0.002f,
                          $"Leaf open: x {b.min.x:0.000} .. {b.max.x:0.000} (HERO_SPEC -3.55 .. -1.85)");
                }
                finally { leaf.localPosition = saved; }
            }

            var button = root.transform.Find("Button");
            var gb = button != null ? button.GetComponent<GateButton>() : null;
            Check(gb != null && gb.interactable != null && Mathf.Approximately(gb.pressOffset.x, -ButtonTravel), "Button: GateButton + XRSimpleInteractable, travel -X 0.008");
            var listeners = gb != null ? gb.onPressed.GetPersistentEventCount() : 0;
            Check(listeners == 1 && gb.onPressed.GetPersistentTarget(0) == slide && gb.onPressed.GetPersistentMethodName(0) == "Open",
                  $"Button onPressed -> Leaf SlideDriver.Open ({listeners} persistent listener(s))");

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
