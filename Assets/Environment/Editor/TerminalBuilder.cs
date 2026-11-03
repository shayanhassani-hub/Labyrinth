// TerminalBuilder.cs - assembles Hero 02, the control terminal, in the open scene and saves it as a prefab.
//
// Menu:  Tools > Labyrinth > Terminal: Apply Import Settings   (models + textures, hero mode)
//        Tools > Labyrinth > Build Terminal                     (Build(): materials, hierarchy, prefab, Verify())
//        Tools > Labyrinth > Verify Terminal                    (Verify())
// Code:  LabyrinthVR.EnvironmentTools.TerminalBuilder.ApplyImportSettings() / Build() / Verify()
//
// Source of truth: Documentation/HERO_SPEC.md section 5 (+ sections 1, 9, 10) and the build notes
// Documentation/Heroes/Terminal_BUILD.md. Meshes: Tools/Blender/heroes/terminal_export.py (hero export mode,
// EXPORT_CONTRACT.md); textures: terminal_tex.py (2048 set) and terminal_holo.py (holo screen, 1024 x 512).
//
//   HERO_Terminal (-2.2, 0, -2.0), yaw 0 - HERO_SPEC section 5 origin (back wall face, floor, centre)
//     Body        (0, 0, 0)               static; BoxColliders: Pillar_L, Pillar_R, desk / lower body
//     Button      (0, 1.031, 0.521)       SphereCollider, XRSimpleInteractable, GateButton (press 0.015 along the
//                                         desk normal), GateButton.onPressed -> TerminalController.Arm (persistent)
//     Indicators  (0, 0, 0)               switching (MaterialPropertyBlock from TerminalController)
//     Beacon      (1.02, 1.272, 0.33)     switching (MaterialPropertyBlock from TerminalController)
//     Display     (0, 1.10, 0.15)         holo screen, M_LAB_HERO_Terminal_Holo, no collider
//   TerminalController on the root: indicators / beacon renderers, onArmed for FacilitySequence.
//
// Materials: M_LAB_HERO_Terminal (URP Lit, metallic workflow, as the Gate): BaseColor, Normal (OpenGL), Mask (R metallic,
// G AO, A smoothness: the same texture in the Metallic and the Occlusion slot), Emission map at intensity 1.
// M_LAB_HERO_Terminal_Holo (URP Unlit, transparent, alpha blend, both faces, no depth write): the holo texture.
// Colliders are primitives only. It replaces an existing HERO_Terminal, never saves the scene, one Undo step.
// The prefab asset Assets/Environment/Heroes/Terminal/HERO_Terminal.prefab is written (AssetDatabase).

using System.Collections.Generic;
using System.Linq;
using System.Text;
using LabyrinthVR.Gameplay;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
using UnityEngine.XR.Interaction.Toolkit.Interactables;

namespace LabyrinthVR.EnvironmentTools
{
    public static class TerminalBuilder
    {
        const string Dir = "Assets/Environment/Heroes/Terminal/";
        const string TexDir = Dir + "Textures/";
        const string MatPath = Dir + "M_LAB_HERO_Terminal.mat";
        const string HoloMatPath = Dir + "M_LAB_HERO_Terminal_Holo.mat";
        const string HoloTexPath = TexDir + "T_LAB_HERO_Terminal_Holo.png";
        const string PrefabPath = Dir + "HERO_Terminal.prefab";
        const string RootName = "HERO_Terminal", UndoName = "Build Terminal";
        const string Hero = "LAB_HERO_Terminal_";

        // Hand-tuned values (owner may change in the Editor or here)
        public static float EmissionIntensity = 1.0f;     // the light strips must not clip to white
        public static int MaxTextureSize = 2048;          // ASSET_RULES: authored at 2048, may ship at 1024 after the Quest test
        public static int HoloMaxSize = 1024;

        // HERO_SPEC section 5: root placement
        static readonly Vector3 RootPosition = new Vector3(-2.2f, 0f, -2.0f);

        // part -> (child name, local position under the root, triangles, hero material?)
        static readonly (string fbx, string name, Vector3 origin, int tris, bool holo)[] Parts =
        {
            (Hero + "Body_01", "Body", Vector3.zero, 1676, false),
            (Hero + "Button_01", "Button", new Vector3(0f, 1.03107f, 0.52094f), 140, false),
            (Hero + "Indicators_01", "Indicators", Vector3.zero, 30, false),
            (Hero + "Beacon_01", "Beacon", new Vector3(1.02f, 1.272f, 0.33f), 112, false),
            (Hero + "Display_01", "Display", new Vector3(0f, 1.10f, 0.15f), 2, true),
        };

        // Desk normal (15 deg slope, toward the player and up) and the button stroke along it (HERO_SPEC: 0.015)
        static readonly Vector3 DeskNormal = new Vector3(0f, 0.965926f, 0.258819f);
        const float ButtonTravel = 0.015f;

        // Primitive colliders in Body-local space (= root space): pillars 0.36 x 1.25 x 0.80 (H2b), desk / lower body
        static readonly (Vector3 center, Vector3 size)[] BodyBoxes =
        {
            (new Vector3(1.02f, 0.625f, 0.40f), new Vector3(0.36f, 1.25f, 0.80f)),    // Pillar_L (+X, player's left)
            (new Vector3(-1.02f, 0.625f, 0.40f), new Vector3(0.36f, 1.25f, 0.80f)),   // Pillar_R
            (new Vector3(0f, 0.525f, 0.375f), new Vector3(1.68f, 1.05f, 0.75f)),      // desk + lower body (box over the slope)
        };
        const float ButtonSphereRadius = 0.06f;

        // map -> (sRGB, normal map, Android ASTC block) - ASSET_RULES: 6x6 colour/mask, 4x4 normal
        static readonly (string map, bool srgb, bool normal, TextureImporterFormat astc)[] Maps =
        {
            ("BaseColor", true, false, TextureImporterFormat.ASTC_6x6),
            ("Normal", false, true, TextureImporterFormat.ASTC_4x4),
            ("Mask", false, false, TextureImporterFormat.ASTC_6x6),
            ("Emission", true, false, TextureImporterFormat.ASTC_6x6),
        };

        static string TexPath(string map) => $"{TexDir}T_LAB_HERO_Terminal_{map}.png";

        // ----------------------------------------------------------------- import settings

        [MenuItem("Tools/Labyrinth/Terminal: Apply Import Settings")]
        static void ImportFromMenu() => Debug.Log(ApplyImportSettings());

        /// EXPORT_CONTRACT.md importer settings, hero mode (normals and tangents from the FBX), and the ASSET_RULES
        /// texture settings. Confirm with git diff on the .meta files afterwards.
        public static string ApplyImportSettings()
        {
            var r = new StringBuilder("[TerminalBuilder] import settings\n");
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
                SetAndroid(ti, MaxTextureSize, m.astc);
                ti.SaveAndReimport();
                r.AppendLine($"PASS texture import settings {m.map}: {(m.normal ? "normal map" : m.srgb ? "sRGB" : "linear")}, " +
                             $"mipmaps, Android {m.astc} max {MaxTextureSize}");
            }
            var hi = AssetImporter.GetAtPath(HoloTexPath) as TextureImporter;
            if (hi == null) r.AppendLine($"FAIL no texture importer for {HoloTexPath}");
            else
            {
                hi.textureType = TextureImporterType.Default;
                hi.sRGBTexture = true;
                hi.alphaSource = TextureImporterAlphaSource.FromInput;
                hi.alphaIsTransparency = true;
                hi.mipmapEnabled = true;
                hi.wrapMode = TextureWrapMode.Clamp;
                hi.maxTextureSize = HoloMaxSize;
                SetAndroid(hi, HoloMaxSize, TextureImporterFormat.ASTC_6x6);
                hi.SaveAndReimport();
                r.AppendLine($"PASS texture import settings Holo: sRGB + alpha, clamp, mipmaps, Android ASTC_6x6 max {HoloMaxSize}");
            }
            return r.ToString();
        }

        static void SetAndroid(TextureImporter ti, int size, TextureImporterFormat format)
        {
            var android = ti.GetPlatformTextureSettings("Android");
            android.overridden = true;
            android.maxTextureSize = size;
            android.format = format;
            ti.SetPlatformTextureSettings(android);
        }

        // ----------------------------------------------------------------- materials

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
            mat.SetFloat("_SmoothnessTextureChannel", 0f);
            mat.SetFloat("_Smoothness", 1f);
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
            return mat;
        }

        /// The one allowed second material (owner brief): URP Unlit, transparent alpha blend, both faces, no depth
        /// write, the holo texture (colour = light, alpha = panel opacity).
        static Material LoadOrCreateHoloMaterial(StringBuilder r)
        {
            var shader = Shader.Find("Universal Render Pipeline/Unlit");
            if (shader == null) { r.AppendLine("FAIL URP Unlit shader not found"); return null; }
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(HoloTexPath);
            if (tex == null) { r.AppendLine($"FAIL missing {HoloTexPath}"); return null; }
            var mat = AssetDatabase.LoadAssetAtPath<Material>(HoloMatPath);
            var created = mat == null;
            if (created) mat = new Material(shader);
            else mat.shader = shader;
            mat.SetTexture("_BaseMap", tex);
            mat.SetColor("_BaseColor", Color.white);
            mat.SetFloat("_Surface", 1f);                                         // transparent
            mat.SetFloat("_Blend", 0f);                                           // alpha
            mat.SetFloat("_AlphaClip", 0f);
            mat.SetFloat("_Cull", (float)CullMode.Off);                           // both faces
            mat.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            mat.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            mat.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            mat.SetFloat("_DstBlendAlpha", (float)BlendMode.OneMinusSrcAlpha);
            mat.SetFloat("_ZWrite", 0f);
            mat.SetOverrideTag("RenderType", "Transparent");
            mat.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            mat.DisableKeyword("_ALPHATEST_ON");
            mat.renderQueue = (int)RenderQueue.Transparent;
            if (created) { AssetDatabase.CreateAsset(mat, HoloMatPath); r.AppendLine($"created {HoloMatPath}"); }
            else { EditorUtility.SetDirty(mat); r.AppendLine($"updated {HoloMatPath}"); }
            return mat;
        }

        // ----------------------------------------------------------------- build

        [MenuItem("Tools/Labyrinth/Build Terminal")]
        static void BuildFromMenu() => Log(Build());

        [MenuItem("Tools/Labyrinth/Verify Terminal")]
        static void VerifyFromMenu() => Log(Verify());

        static void Log(string report)
        {
            if (report.Contains("RESULT: PASS")) Debug.Log(report); else Debug.LogError(report);
        }

        public static string Build()
        {
            var r = new StringBuilder();
            var scene = SceneManager.GetActiveScene();
            r.AppendLine($"[TerminalBuilder] scene: {scene.path}");

            // Load everything first, so a missing asset changes nothing in the scene.
            var assets = new Dictionary<string, GameObject>();
            foreach (var p in Parts)
            {
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(Dir + p.fbx + ".fbx");
                if (go == null) return r.AppendLine($"FAIL missing {Dir}{p.fbx}.fbx\nRESULT: FAIL (scene unchanged)").ToString();
                assets[p.name] = go;
            }
            var mat = LoadOrCreateMaterial(r);
            var holo = LoadOrCreateHoloMaterial(r);
            if (mat == null || holo == null) return r.AppendLine("RESULT: FAIL (scene unchanged)").ToString();
            AssetDatabase.SaveAssets();

            Undo.IncrementCurrentGroup();
            var group = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName(UndoName);
            var old = scene.GetRootGameObjects().Where(g => g.name == RootName).ToList();
            foreach (var g in old) Undo.DestroyObjectImmediate(g);

            var root = new GameObject(RootName);
            Undo.RegisterCreatedObjectUndo(root, UndoName);
            root.transform.SetPositionAndRotation(RootPosition, Quaternion.identity);

            var placed = new Dictionary<string, GameObject>();
            foreach (var p in Parts) placed[p.name] = Place(assets[p.name], root.transform, p.name, p.origin, p.holo ? holo : mat);

            // Body: primitive colliders (pillars, desk / lower body) - block the player and the teleport ray
            var body = placed["Body"];
            foreach (var b in BodyBoxes)
            {
                var box = body.AddComponent<BoxCollider>();
                box.center = b.center; box.size = b.size;
            }

            // Button: XRI select (ray / near-far; poke once the rig has a poke interactor) -> press -> Arm
            var button = placed["Button"];
            var sphere = button.AddComponent<SphereCollider>();
            sphere.center = -DeskNormal * 0.02f; sphere.radius = ButtonSphereRadius;
            var interactable = button.AddComponent<XRSimpleInteractable>();
            var gb = button.AddComponent<GateButton>();
            gb.interactable = interactable;
            gb.cap = button.transform;
            gb.pressOffset = -DeskNormal * ButtonTravel;

            var ctrl = root.AddComponent<TerminalController>();
            ctrl.indicators = placed["Indicators"].GetComponent<MeshRenderer>();
            ctrl.beacon = placed["Beacon"].GetComponent<MeshRenderer>();
            ctrl.indicatorIntensity = EmissionIntensity;
            UnityEventTools.AddPersistentListener(gb.onPressed, new UnityAction(ctrl.Arm));
            ctrl.ResetToStandby();

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
            var r = new StringBuilder("[TerminalBuilder] verify\n");
            var root = GameObject.Find("/" + RootName);
            if (root == null) return r.AppendLine("FAIL no HERO_Terminal\nRESULT: FAIL").ToString();
            var pass = true;
            void Check(bool ok, string line) { pass &= ok; r.AppendLine($"{(ok ? "PASS" : "FAIL")} {line}"); }

            Check((root.transform.position - RootPosition).magnitude < 1e-4f && root.transform.rotation == Quaternion.identity
                  && root.transform.localScale == Vector3.one,
                  $"{RootName}: position {F(root.transform.position)} (HERO_SPEC {F(RootPosition)}), yaw 0, scale 1");
            foreach (var p in Parts)
            {
                var t = root.transform.Find(p.name);
                if (t == null) { Check(false, $"{p.name} missing"); continue; }
                var mf = t.GetComponent<MeshFilter>(); var mr = t.GetComponent<MeshRenderer>();
                var tris = mf != null && mf.sharedMesh != null ? mf.sharedMesh.triangles.Length / 3 : -1;
                Check(tris == p.tris, $"{p.name}: {tris} tris (build notes {p.tris}), submeshes {(mf != null && mf.sharedMesh != null ? mf.sharedMesh.subMeshCount : 0)}");
                Check((t.localPosition - p.origin).magnitude < 1e-4f && t.localRotation == Quaternion.identity && t.localScale == Vector3.one,
                      $"{p.name}: local origin {F(t.localPosition)} (expected {F(p.origin)}), rotation 0, scale 1");
                var want = p.holo ? "M_LAB_HERO_Terminal_Holo" : "M_LAB_HERO_Terminal";
                Check(mr != null && mr.sharedMaterial != null && mr.sharedMaterial.name == want,
                      $"{p.name}: material {(mr != null && mr.sharedMaterial != null ? mr.sharedMaterial.name : "none")} (expected {want})");
                Check(!t.GetComponentsInChildren<MeshCollider>(true).Any(), $"{p.name}: no mesh colliders");
                if (mf != null && mf.sharedMesh != null)
                    r.AppendLine($"INFO {p.name}: world bounds {F(mr.bounds.min)}..{F(mr.bounds.max)}, tangents {(mf.sharedMesh.tangents.Length > 0 ? "yes" : "NO")}");
            }

            // HERO_SPEC section 5 footprint: x -3.4 ... -1.0, z -2.0 ... -1.2
            var bodyT = root.transform.Find("Body");
            if (bodyT != null)
            {
                var b = bodyT.GetComponent<MeshRenderer>().bounds;
                Check(b.min.x > -3.4f - 0.002f && b.max.x < -1.0f + 0.002f && b.min.z > -2.0f - 0.002f && b.max.z < -1.2f + 0.002f && b.min.y > -0.002f,
                      $"Body inside the footprint x -3.4 ... -1.0, z -2.0 ... -1.2: x {b.min.x:0.000} .. {b.max.x:0.000}, z {b.min.z:0.000} .. {b.max.z:0.000}");
                Check(bodyT.GetComponents<BoxCollider>().Length == BodyBoxes.Length, $"Body: {bodyT.GetComponents<BoxCollider>().Length} primitive box colliders");
            }

            var button = root.transform.Find("Button");
            var gb = button != null ? button.GetComponent<GateButton>() : null;
            var ctrl = root.GetComponent<TerminalController>();
            Check(gb != null && gb.interactable != null && (gb.pressOffset + DeskNormal * ButtonTravel).magnitude < 1e-5f,
                  $"Button: GateButton + XRSimpleInteractable, travel {(gb != null ? F(gb.pressOffset) : "-")} (0.015 along the desk normal)");
            var listeners = gb != null ? gb.onPressed.GetPersistentEventCount() : 0;
            Check(listeners == 1 && gb.onPressed.GetPersistentTarget(0) == ctrl && gb.onPressed.GetPersistentMethodName(0) == "Arm",
                  $"Button onPressed -> TerminalController.Arm ({listeners} persistent listener(s))");
            Check(ctrl != null && ctrl.indicators != null && ctrl.beacon != null
                  && ctrl.indicators.transform == root.transform.Find("Indicators") && ctrl.beacon.transform == root.transform.Find("Beacon"),
                  "TerminalController: indicators and beacon renderers wired");

            var mat = AssetDatabase.LoadAssetAtPath<Material>(MatPath);
            Check(mat != null && mat.IsKeywordEnabled("_NORMALMAP") && mat.IsKeywordEnabled("_METALLICSPECGLOSSMAP")
                  && mat.IsKeywordEnabled("_OCCLUSIONMAP") && mat.IsKeywordEnabled("_EMISSION"),
                  "material keywords _NORMALMAP _METALLICSPECGLOSSMAP _OCCLUSIONMAP _EMISSION");
            var holo = AssetDatabase.LoadAssetAtPath<Material>(HoloMatPath);
            Check(holo != null && holo.renderQueue == (int)RenderQueue.Transparent && holo.IsKeywordEnabled("_SURFACE_TYPE_TRANSPARENT")
                  && Mathf.Approximately(holo.GetFloat("_Cull"), (float)CullMode.Off),
                  "holo material: transparent queue, _SURFACE_TYPE_TRANSPARENT, both faces");
            foreach (var m in Maps)
            {
                var ti = AssetImporter.GetAtPath(TexPath(m.map)) as TextureImporter;
                var a = ti != null ? ti.GetPlatformTextureSettings("Android") : null;
                Check(ti != null && (m.normal || ti.sRGBTexture == m.srgb)
                      && (ti.textureType == TextureImporterType.NormalMap) == m.normal && ti.mipmapEnabled
                      && a.overridden && a.format == m.astc,
                      $"texture {m.map}: {(ti == null ? "missing" : $"{ti.textureType}, sRGB {ti.sRGBTexture}, mipmaps {ti.mipmapEnabled}, Android {a.format}")}");
            }
            var hi = AssetImporter.GetAtPath(HoloTexPath) as TextureImporter;
            Check(hi != null && hi.sRGBTexture && hi.alphaSource == TextureImporterAlphaSource.FromInput && hi.maxTextureSize <= HoloMaxSize,
                  $"texture Holo: {(hi == null ? "missing" : $"sRGB {hi.sRGBTexture}, alpha {hi.alphaSource}, max {hi.maxTextureSize}")}");
            r.AppendLine(pass ? "RESULT: PASS - scene marked dirty, NOT saved." : "RESULT: FAIL");
            return r.ToString();
        }

        static string F(Vector3 v) => $"({v.x:0.000}, {v.y:0.000}, {v.z:0.000})";
    }
}
