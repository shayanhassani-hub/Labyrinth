// CradleBuilder.cs - assembles Hero 01, the docking cradle v2, in the open scene and saves it as a prefab.
// Step C-T2 (2026-11-13), on the GateBuilder pattern. The superseded Part 1 builder is CradlePart1Builder.cs.
//
// Menu:  Tools > Labyrinth > Cradle: Apply Import Settings   (models + textures, hero mode)
//        Tools > Labyrinth > Build Cradle                     (Build(): material, hierarchy, prefab, Verify())
//        Tools > Labyrinth > Verify Cradle                    (Verify())
// Code:  LabyrinthVR.EnvironmentTools.CradleBuilder.ApplyImportSettings() / Build() / Verify()
//
// Source of truth: Documentation/HERO_SPEC.md section 3. Meshes: Tools/Blender/heroes/cradle_v2_export.py
// (hero export mode from the export-identical bake lows, EXPORT_CONTRACT.md); textures: cradle_v2_tex.py (C-T1b).
//
//   HERO_Cradle (0, 0, 4.69), yaw 0
//     Base      (0, 0, 0)                   primitive colliders (plinth tiers, turntable, column, beam, drums, hub)
//     Arm_L     (-0.385, 0.637, 0)          HingeDriver Z +75 deg / 1.2 s eased, kinematic Rigidbody, 2 boxes
//       Riser_L (-0.115, 1.0621, 0)         box
//       Pad_L   (-0.115, 1.1165, 0)         box (on the riser)
//     Arm_R     (+0.385, 0.637, 0)          HingeDriver Z -75 deg / 1.2 s eased, kinematic Rigidbody, 2 boxes
//       Pad_R   (+0.115, 1.0621, 0)         box
//
// One material M_LAB_HERO_Cradle (URP Lit, metallic workflow): BaseColor, Normal (OpenGL), Mask (R metallic,
// G AO, A smoothness: the same texture in the Metallic and the Occlusion slot, ASSET_RULES), Emission map with
// intensity 1 (the map carries the STYLE_GUIDE cyan; the status strip must not clip to white).
// It replaces an existing HERO_Cradle (the Part 1 cradle too), never saves the scene, one Undo step. The prefab
// asset Assets/Environment/Heroes/Cradle/HERO_Cradle.prefab is written (AssetDatabase).
//
// Verify(): parts, origins, material, textures, HingeDrivers; then, with the drone moved to the docking pose
// (HERO_SPEC section 3 / 10: (-0.032, 2.000, 4.754), yaw -28.3) and the arms swept 0 -> 75 deg, mesh distances
// (vertices + 2 mm edge samples against triangles, both ways): pads under the drone, the opening path, arms vs
// base, the released pose, and the ServiceArm rule (>= 50 mm to the drone mesh and the cradle). Every pose and
// the drone are restored afterwards.

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
    public static class CradleBuilder
    {
        const string Dir = "Assets/Environment/Heroes/Cradle/";
        const string TexDir = Dir + "Textures/";
        const string MatPath = Dir + "M_LAB_HERO_Cradle.mat";
        const string PrefabPath = Dir + "HERO_Cradle.prefab";
        const string RootName = "HERO_Cradle", UndoName = "Build Cradle";
        const string Hero = "LAB_HERO_Cradle_";

        // Hand-tuned values (owner may change in the Editor or here)
        public static float EmissionIntensity = 1.0f;     // the status strip must not clip to white
        public static int MaxTextureSize = 2048;          // ASSET_RULES: authored at 2048, may ship at 1024 after the Quest test
        public static float OpenDeg = 75f, OpenSeconds = 1.2f;

        static readonly Vector3 Origin = new Vector3(0f, 0f, 4.69f);

        // HERO_SPEC section 3 parts: (fbx, child name, parent child name ("" = root), local position, tris).
        // Positions from cradle_v2_export.py (export.json "children").
        static readonly (string fbx, string name, string parent, Vector3 pos, int tris)[] Parts =
        {
            (Hero + "Base_01", "Base", "", Vector3.zero, 2800),
            (Hero + "Arm_L_01", "Arm_L", "", new Vector3(-0.385f, 0.637f, 0f), 500),
            (Hero + "Arm_R_01", "Arm_R", "", new Vector3(0.385f, 0.637f, 0f), 500),
            (Hero + "Riser_L_01", "Riser_L", "Arm_L", new Vector3(-0.115f, 1.0621f, 0f), 38),
            (Hero + "Pad_01", "Pad_L", "Arm_L", new Vector3(-0.115f, 1.1165f, 0f), 38),
            (Hero + "Pad_01", "Pad_R", "Arm_R", new Vector3(0.115f, 1.0621f, 0f), 38),
        };
        static IEnumerable<string> Fbx => Parts.Select(p => p.fbx).Distinct();

        // HERO_SPEC section 3 targets
        const float PadTopR = 1.7091f, PadTopL = 1.7635f, PadTopTol = 0.0005f;
        const float DroneFloorY = 1.19f, MinOpenClear = 0.002f, MinBaseClear = 0.001f, ServiceArmRule = 0.050f;
        static readonly Vector3 DockPos = new Vector3(-0.032f, 2.000f, 4.754f);
        const float DockYaw = -28.3f;
        public static string DroneName = "DroneAI2", ServiceArmName = "HERO_ServiceArm";

        static readonly (string map, bool srgb, bool normal, TextureImporterFormat astc)[] Maps =
        {
            ("BaseColor", true, false, TextureImporterFormat.ASTC_6x6),
            ("Normal", false, true, TextureImporterFormat.ASTC_4x4),
            ("Mask", false, false, TextureImporterFormat.ASTC_6x6),
            ("Emission", true, false, TextureImporterFormat.ASTC_6x6),
        };

        static string TexPath(string map) => $"{TexDir}T_LAB_HERO_Cradle_{map}.png";

        // ----------------------------------------------------------------- import settings

        [MenuItem("Tools/Labyrinth/Cradle: Apply Import Settings")]
        static void ImportFromMenu() => Debug.Log(ApplyImportSettings());

        /// EXPORT_CONTRACT.md importer settings, hero mode (normals and tangents from the FBX), and the
        /// ASSET_RULES texture settings. Confirm with git diff on the .meta files afterwards.
        public static string ApplyImportSettings()
        {
            var r = new StringBuilder("[CradleBuilder] import settings\n");
            foreach (var f in Fbx)
            {
                var mi = AssetImporter.GetAtPath(Dir + f + ".fbx") as ModelImporter;
                if (mi == null) { r.AppendLine($"FAIL no model importer for {Dir}{f}.fbx"); continue; }
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
                r.AppendLine($"PASS model import settings {f}");
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
            AssetDatabase.SaveAssets();
            return mat;
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

            var assets = new Dictionary<string, GameObject>();
            foreach (var f in Fbx)
            {
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(Dir + f + ".fbx");
                if (go == null) return r.AppendLine($"FAIL missing {Dir}{f}.fbx\nRESULT: FAIL (scene unchanged)").ToString();
                assets[f] = go;
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
            root.transform.SetPositionAndRotation(Origin, Quaternion.identity);

            var placed = new Dictionary<string, GameObject>();
            foreach (var p in Parts)
            {
                var parent = p.parent == "" ? root.transform : placed[p.parent].transform;
                placed[p.name] = Place(assets[p.fbx], parent, p.name, p.pos, mat);
            }

            AddBaseColliders(placed["Base"]);
            foreach (var (side, sign) in new[] { ("L", 1f), ("R", -1f) })
            {
                var arm = placed["Arm_" + side];
                AddArmColliders(arm);
                var rb = arm.AddComponent<Rigidbody>();
                rb.isKinematic = true; rb.useGravity = false;
                var hinge = arm.AddComponent<HingeDriver>();
                hinge.part = arm.transform;
                hinge.axis = Vector3.forward;
                hinge.openAngle = sign * OpenDeg;          // Unity +Z turns +Y towards -X: + opens Arm_L outward
                hinge.duration = OpenSeconds;
                hinge.easeInOut = true;
            }
            foreach (var n in new[] { "Pad_L", "Pad_R", "Riser_L" }) BoundsBox(placed[n], placed[n].GetComponent<MeshFilter>().sharedMesh.bounds);

            var prefab = PrefabUtility.SaveAsPrefabAssetAndConnect(root, PrefabPath, InteractionMode.UserAction);
            Undo.CollapseUndoOperations(group);
            EditorSceneManager.MarkSceneDirty(scene);
            r.AppendLine(prefab != null ? $"saved prefab {PrefabPath}" : $"FAIL prefab {PrefabPath} not saved");
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

        static BoxCollider BoundsBox(GameObject go, Bounds b)
        {
            var c = go.AddComponent<BoxCollider>(); c.center = b.center; c.size = b.size; return c;
        }

        static void Box(GameObject parent, string name, Vector3 center, Vector3 size, float yaw)
        {
            if (Mathf.Approximately(yaw, 0f)) { var c0 = parent.AddComponent<BoxCollider>(); c0.center = center; c0.size = size; return; }
            var go = new GameObject("COL_" + name);
            go.transform.SetParent(parent.transform, false);
            go.transform.localPosition = center;
            go.transform.localRotation = Quaternion.Euler(0f, yaw, 0f);
            var c = go.AddComponent<BoxCollider>(); c.size = size;
        }

        /// HERO_SPEC section 3 dimensions (cradle-local). Octagons = the union of an axis box and a 45 deg box.
        static void AddBaseColliders(GameObject b)
        {
            Box(b, "Tier1_X", new Vector3(0f, 0.103f, 0f), new Vector3(2.428f, 0.206f, 0.884f), 0f);   // X faces z +-0.442
            Box(b, "Tier1_Z", new Vector3(0f, 0.103f, 0f), new Vector3(0.980f, 0.206f, 2.428f), 0f);   // Z faces x +-0.490
            Box(b, "Tier1_D1", new Vector3(0f, 0.103f, 0f), new Vector3(2.320f, 0.206f, 0.680f), 45f); // diagonal faces at 1.16
            Box(b, "Tier1_D2", new Vector3(0f, 0.103f, 0f), new Vector3(2.320f, 0.206f, 0.680f), -45f);
            Box(b, "Tier2_A", new Vector3(0f, 0.262f, 0f), new Vector3(1.700f, 0.112f, 1.700f), 0f);   // flats ~0.85
            Box(b, "Tier2_D", new Vector3(0f, 0.262f, 0f), new Vector3(1.700f, 0.112f, 1.700f), 45f);
            Box(b, "Turntable_A", new Vector3(0f, 0.346f, 0f), new Vector3(1.010f, 0.092f, 1.010f), 0f); // r 0.505, y 0.300-0.392
            Box(b, "Turntable_D", new Vector3(0f, 0.346f, 0f), new Vector3(1.010f, 0.092f, 1.010f), 45f);
            Box(b, "Column", new Vector3(0f, 0.5735f, 0f), new Vector3(0.360f, 0.363f, 0.448f), 0f);    // y 0.392-0.755
            Box(b, "Beam", new Vector3(0f, 0.6275f, 0f), new Vector3(0.800f, 0.255f, 0.307f), 0f);      // y 0.500-0.755
            Box(b, "Hub", new Vector3(0f, 0.8185f, 0f), new Vector3(0.330f, 0.127f, 0.304f), 0f);       // y 0.755-0.882
            foreach (var x in new[] { -0.385f, 0.385f })                                               // drums + pin caps
            {
                var cap = b.AddComponent<CapsuleCollider>();
                cap.direction = 2; cap.radius = 0.119f; cap.height = 0.461f;
                cap.center = new Vector3(x, 0.637f, -0.0095f);                                         // world z 4.450-4.911
            }
        }

        /// Arm-local boxes from the arm mesh: the rest plate (y >= 0.951) and the limb below it.
        static void AddArmColliders(GameObject arm)
        {
            var v = arm.GetComponent<MeshFilter>().sharedMesh.vertices;
            const float plateY = 0.951f;
            Bounds Of(IEnumerable<Vector3> pts) { var a = pts.ToArray(); var bb = new Bounds(a[0], Vector3.zero); foreach (var q in a) bb.Encapsulate(q); return bb; }
            var plate = Of(v.Where(q => q.y >= plateY - 0.001f));
            var limb = Of(v.Where(q => q.y < plateY - 0.001f));
            BoundsBox(arm, plate);
            BoundsBox(arm, limb);
        }

        // ----------------------------------------------------------------- verify

        public static string Verify()
        {
            var r = new StringBuilder("[CradleBuilder] verify\n");
            var root = GameObject.Find("/" + RootName);
            if (root == null) return r.AppendLine("FAIL no HERO_Cradle\nRESULT: FAIL").ToString();
            var pass = true;
            void Check(bool ok, string line) { pass &= ok; r.AppendLine($"{(ok ? "PASS" : "FAIL")} {line}"); }

            Check((root.transform.position - Origin).magnitude < 1e-4f && root.transform.rotation == Quaternion.identity,
                  $"root {F(root.transform.position)} yaw {root.transform.eulerAngles.y:0.0} (HERO_SPEC {F(Origin)}, yaw 0)");
            var t = new Dictionary<string, Transform>();
            foreach (var p in Parts)
            {
                var parent = p.parent == "" ? root.transform : t.ContainsKey(p.parent) ? t[p.parent] : null;
                var tr = parent != null ? parent.Find(p.name) : null;
                if (tr == null) { Check(false, $"{p.name} missing"); continue; }
                t[p.name] = tr;
                var mf = tr.GetComponent<MeshFilter>(); var mr = tr.GetComponent<MeshRenderer>();
                var mesh = mf != null ? mf.sharedMesh : null;
                var tris = mesh != null ? mesh.triangles.Length / 3 : -1;
                Check(tris == p.tris && mesh.subMeshCount == 1 && mesh.name == p.fbx,
                      $"{p.name}: mesh {(mesh != null ? mesh.name : "none")}, {tris} tris (HERO_SPEC {p.tris}), submeshes {(mesh != null ? mesh.subMeshCount : 0)}");
                Check((tr.localPosition - p.pos).magnitude < 1e-4f && tr.localScale == Vector3.one,
                      $"{p.name}: local position {F4(tr.localPosition)} (export {F4(p.pos)}), scale 1");
                Check(mr != null && mr.sharedMaterial != null && mr.sharedMaterial.name == "M_LAB_HERO_Cradle",
                      $"{p.name}: material {(mr != null && mr.sharedMaterial != null ? mr.sharedMaterial.name : "none")}, tangents {(mesh != null && mesh.tangents.Length > 0 ? "yes" : "NO")}");
            }
            Check(!root.GetComponentsInChildren<MeshCollider>(true).Any(), $"no mesh colliders; primitive colliders {root.GetComponentsInChildren<Collider>(true).Length}");
            if (t.Count < Parts.Length) return r.AppendLine("RESULT: FAIL").ToString();

            var arms = new[] { t["Arm_L"], t["Arm_R"] };
            foreach (var (arm, sign) in new[] { (arms[0], 1f), (arms[1], -1f) })
            {
                var h = arm.GetComponent<HingeDriver>(); var rb = arm.GetComponent<Rigidbody>();
                Check(h != null && h.part == arm && h.axis == Vector3.forward && Mathf.Approximately(h.openAngle, sign * OpenDeg)
                      && Mathf.Approximately(h.duration, OpenSeconds) && h.easeInOut,
                      $"{arm.name} HingeDriver: axis Z, {(h != null ? h.openAngle : 0f):+0;-0} deg, {(h != null ? h.duration : 0f)} s, eased");
                Check(rb != null && rb.isKinematic, $"{arm.name} kinematic Rigidbody");
                Check(arm.localRotation == Quaternion.identity, $"{arm.name} closed (rotation 0)");
            }
            var mat = AssetDatabase.LoadAssetAtPath<Material>(MatPath);
            Check(mat != null && mat.IsKeywordEnabled("_NORMALMAP") && mat.IsKeywordEnabled("_METALLICSPECGLOSSMAP")
                  && mat.IsKeywordEnabled("_OCCLUSIONMAP") && mat.IsKeywordEnabled("_EMISSION")
                  && mat.GetColor("_EmissionColor") == Color.white * EmissionIntensity,
                  $"material keywords _NORMALMAP _METALLICSPECGLOSSMAP _OCCLUSIONMAP _EMISSION, emission x{EmissionIntensity}");
            foreach (var m in Maps)
            {
                var ti = AssetImporter.GetAtPath(TexPath(m.map)) as TextureImporter;
                var a = ti != null ? ti.GetPlatformTextureSettings("Android") : null;
                Check(ti != null && (m.normal || ti.sRGBTexture == m.srgb) && (ti.textureType == TextureImporterType.NormalMap) == m.normal
                      && ti.mipmapEnabled && a.overridden && a.format == m.astc,
                      $"texture {m.map}: {(ti == null ? "missing" : $"{ti.textureType}, sRGB {ti.sRGBTexture}, mipmaps {ti.mipmapEnabled}, Android {a.format}")}");
            }

            // standby
            var padR = Mesh(t["Pad_R"]); var padL = Mesh(t["Pad_L"]);
            var topR = padR.W.Max(q => q.y); var topL = padL.W.Max(q => q.y);
            Check(Mathf.Abs(topR - PadTopR) <= PadTopTol && Mathf.Abs(topL - PadTopL) <= PadTopTol,
                  $"closed pad tops y R {topR:0.0000} / L {topL:0.0000} (HERO_SPEC {PadTopR} / {PadTopL})");

            // drone at the docking pose, arm sweep (restored in finally)
            var drone = GameObject.Find(DroneName);
            var savedRot = arms.Select(a => a.localRotation).ToArray();
            Vector3 dPos = default; Quaternion dRot = default;
            if (drone == null) r.AppendLine($"WARN drone '{DroneName}' not found: drone checks skipped");
            else { dPos = drone.transform.position; dRot = drone.transform.rotation; }
            try
            {
                var baseM = Mesh(t["Base"]);
                var baseGrid = new TriGrid(baseM.Tris());
                List<Vector3[]> droneTris = null; TriGrid droneGrid = null; List<Vector3> droneSamples = null;
                if (drone != null)
                {
                    drone.transform.SetPositionAndRotation(DockPos, Quaternion.Euler(0f, DockYaw, 0f));
                    var dm = drone.GetComponentsInChildren<MeshFilter>(false)
                                  .Where(f => f.sharedMesh != null && f.GetComponent<Renderer>() != null && f.GetComponent<Renderer>().enabled)
                                  .Select(f => Mesh(f.transform)).ToList();
                    droneTris = dm.SelectMany(m => m.Tris()).ToList();
                    droneGrid = new TriGrid(droneTris);
                    droneSamples = dm.SelectMany(m => m.Samples()).ToList();
                    var db = new Bounds(dm[0].W[0], Vector3.zero); foreach (var m in dm) foreach (var q in m.W) db.Encapsulate(q);
                    r.AppendLine($"INFO drone '{DroneName}' at the docking pose {F(DockPos)} yaw {DockYaw} (scene pose {F(dPos)} yaw {dRot.eulerAngles.y:0.0}, restored after): " +
                                 $"{dm.Count} meshes, {droneTris.Count} tris, bounds {F(db.min)}..{F(db.max)}");

                    // pads under the drone (closed): gap to the drone mesh and drone geometry above the pad footprint
                    foreach (var (n, pm, top) in new[] { ("Pad_R", padR, topR), ("Pad_L", padL, topL) })
                    {
                        var gap = Distance(pm, new TriGrid(pm.Tris()), droneSamples, droneGrid, 0.06f);
                        var pb = pm.Bounds();
                        var above = droneSamples.Count(q => q.x > pb.min.x && q.x < pb.max.x && q.z > pb.min.z && q.z < pb.max.z && q.y >= top && q.y < top + 0.05f);
                        var under = droneSamples.Where(q => q.x > pb.min.x && q.x < pb.max.x && q.z > pb.min.z && q.z < pb.max.z && q.y >= top - 0.001f)
                                                .Select(q => q.y - top).DefaultIfEmpty(9f).Min();
                        Check(gap >= 0.001f && gap <= 0.010f && above > 0,
                              $"closed {n} under the drone: mesh gap {gap * 1000f:0.00} mm (HERO_SPEC contact gap 3.0), drone samples over the pad footprint {above}, lowest {under * 1000f:0.0} mm above the pad top");
                    }
                }

                // sweep
                var steps = new[] { 0, 1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75 };
                var movingNames = new[] { new[] { "Arm_L", "Riser_L", "Pad_L" }, new[] { "Arm_R", "Pad_R" } };
                float minDrone = 9f, minDroneOpen = 9f, minBase = 9f; int atDrone = -1, atBase = -1;
                var rows = new StringBuilder();
                float hi75 = 0f, lo75 = 9f;
                foreach (var deg in steps)
                {
                    arms[0].localRotation = Quaternion.Euler(0f, 0f, deg);     // L outward (+)
                    arms[1].localRotation = Quaternion.Euler(0f, 0f, -deg);    // R outward (-)
                    rows.Append($"  {deg,2} deg");
                    for (var s = 0; s < 2; s++)
                    {
                        var ms = movingNames[s].Select(n => Mesh(t[n])).ToList();
                        var mTris = ms.SelectMany(m => m.Tris()).ToList(); var mGrid = new TriGrid(mTris);
                        var mSamples = ms.SelectMany(m => m.Samples()).ToList();
                        var dB = Distance(mSamples, baseGrid, baseM.Samples().ToList(), mGrid, 0.06f);
                        if (dB < minBase) { minBase = dB; atBase = deg; }
                        rows.Append($"  {(s == 0 ? "L" : "R")}: base {Mm(dB, 0.06f)}");
                        if (droneGrid != null)
                        {
                            var dD = Distance(mSamples, droneGrid, droneSamples, mGrid, 0.06f);
                            if (dD < minDrone) { minDrone = dD; atDrone = deg; }
                            if (deg > 0) minDroneOpen = Mathf.Min(minDroneOpen, dD);
                            rows.Append($" drone {Mm(dD, 0.06f)}");
                        }
                        if (deg == 75) { hi75 = Mathf.Max(hi75, mSamples.Max(q => q.y)); lo75 = Mathf.Min(lo75, mSamples.Min(q => q.y)); }
                    }
                    rows.AppendLine(" mm");
                }
                r.Append(rows);
                if (droneGrid != null)
                    Check(minDroneOpen >= MinOpenClear,
                          $"opening path clear of the drone: min {minDroneOpen * 1000f:0.0} mm over 1-75 deg (>= {MinOpenClear * 1000f:0} mm; closed {minDrone * 1000f:0.0} mm at {atDrone} deg)");
                Check(minBase >= MinBaseClear, $"arms / pads / riser vs Base over 0-75 deg: min {minBase * 1000f:0.0} mm at {atBase} deg (>= {MinBaseClear * 1000f:0} mm, no interpenetration)");
                Check(hi75 < DroneFloorY && lo75 > 0f, $"released 75 deg: highest y {hi75:0.000} (< drone volume floor {DroneFloorY}), lowest y {lo75:0.000} (> floor 0)");
                arms[0].localRotation = Quaternion.Euler(0f, 0f, 1f);
                Check(t["Pad_L"].position.x < arms[0].position.x - 0.1f && arms[0].TransformPoint(Vector3.up).x < arms[0].position.x,
                      "Arm_L +Z opens toward -X (outward), Arm_R -Z toward +X");

                // ServiceArm rule (HERO_SPEC section 4): >= 50 mm to the drone mesh (docking pose) and to the cradle
                var sa = GameObject.Find(ServiceArmName);
                if (sa == null) r.AppendLine($"WARN '{ServiceArmName}' not found: ServiceArm clearance skipped");
                else
                {
                    var sm = sa.GetComponentsInChildren<MeshFilter>(false).Where(f => f.sharedMesh != null).Select(f => Mesh(f.transform)).ToList();
                    var sSamples = sm.SelectMany(m => m.Samples()).ToList(); var sGrid = new TriGrid(sm.SelectMany(m => m.Tris()).ToList());
                    var cr = root.GetComponentsInChildren<MeshFilter>().Select(f => Mesh(f.transform)).ToList();
                    foreach (var (pose, deg) in new[] { ("closed", 0f), ("open 75", 75f) })
                    {
                        arms[0].localRotation = Quaternion.Euler(0f, 0f, deg); arms[1].localRotation = Quaternion.Euler(0f, 0f, -deg);
                        cr = root.GetComponentsInChildren<MeshFilter>().Select(f => Mesh(f.transform)).ToList();
                        var d = Distance(sSamples, new TriGrid(cr.SelectMany(m => m.Tris()).ToList()), cr.SelectMany(m => m.Samples()).ToList(), sGrid, 0.10f);
                        Check(d >= ServiceArmRule, $"ServiceArm (scene pose) to the {pose} cradle: {Mm(d, 0.10f)} mm (>= {ServiceArmRule * 1000f:0}; Blender H1b 371 mm over all poses)");
                    }
                    if (droneGrid != null)
                    {
                        var d = Distance(sSamples, droneGrid, droneSamples, sGrid, 0.10f);
                        Check(d >= ServiceArmRule, $"ServiceArm (scene pose) to the docked drone mesh: {Mm(d, 0.10f)} mm (>= {ServiceArmRule * 1000f:0}; H1b 54.1 mm over all poses)");
                    }
                }

                // colliders vs the drone's colliders at the docking pose (closed)
                arms[0].localRotation = arms[1].localRotation = Quaternion.identity;
                if (drone != null)
                {
                    Physics.SyncTransforms();
                    var dc = drone.GetComponentsInChildren<Collider>(false).Where(c => c.enabled && !c.isTrigger).ToList();
                    var hits = new List<string>();
                    foreach (var c in root.GetComponentsInChildren<Collider>(true))
                        foreach (var o in dc)
                            if (Physics.ComputePenetration(c, c.transform.position, c.transform.rotation, o, o.transform.position, o.transform.rotation, out _, out var depth))
                                hits.Add($"{PathOf(c.transform)} {c.GetType().Name} / {PathOf(o.transform)} {depth * 1000f:0.0} mm");
                    Check(hits.Count == 0, $"cradle colliders vs drone colliders at the docking pose: {dc.Count} drone colliders, {hits.Count} overlaps{(hits.Count > 0 ? ": " + string.Join("; ", hits.Take(6)) : "")}");
                }
            }
            finally
            {
                for (var i = 0; i < arms.Length; i++) arms[i].localRotation = savedRot[i];
                if (drone != null) drone.transform.SetPositionAndRotation(dPos, dRot);
                Physics.SyncTransforms();
            }
            r.AppendLine("arms and drone restored");
            r.AppendLine(pass ? "RESULT: PASS - scene marked dirty, NOT saved." : "RESULT: FAIL");
            return r.ToString();
        }

        // ----------------------------------------------------------------- mesh distance helpers

        class M
        {
            public Vector3[] W; public int[] Tri;
            public IEnumerable<Vector3[]> Tris() { for (var i = 0; i < Tri.Length; i += 3) yield return new[] { W[Tri[i]], W[Tri[i + 1]], W[Tri[i + 2]] }; }
            /// world vertices plus points every 2 mm along every triangle edge
            public IEnumerable<Vector3> Samples()
            {
                foreach (var q in W) yield return q;
                for (var i = 0; i < Tri.Length; i += 3)
                    for (var e = 0; e < 3; e++)
                    {
                        var a = W[Tri[i + e]]; var b = W[Tri[i + (e + 1) % 3]];
                        var n = (int)((b - a).magnitude / 0.002f);
                        for (var k = 1; k <= n; k++) yield return Vector3.Lerp(a, b, k / (n + 1f));
                    }
            }
            public Bounds Bounds() { var b = new Bounds(W[0], Vector3.zero); foreach (var q in W) b.Encapsulate(q); return b; }
        }

        static M Mesh(Transform tr)
        {
            var m = tr.GetComponent<MeshFilter>().sharedMesh;
            return new M { W = m.vertices.Select(tr.TransformPoint).ToArray(), Tri = m.triangles };
        }

        /// symmetric sampled distance between two meshes, capped at maxR (= "more than maxR")
        static float Distance(M a, TriGrid aGrid, List<Vector3> bSamples, TriGrid bGrid, float maxR) =>
            Distance(a.Samples().ToList(), bGrid, bSamples, aGrid, maxR);

        static float Distance(List<Vector3> aSamples, TriGrid bGrid, List<Vector3> bSamples, TriGrid aGrid, float maxR)
        {
            var best = maxR;
            foreach (var q in aSamples) best = Mathf.Min(best, bGrid.Nearest(q, best));
            foreach (var q in bSamples) best = Mathf.Min(best, aGrid.Nearest(q, best));
            return best;
        }

        class TriGrid
        {
            const float Cell = 0.03f;
            readonly List<Vector3[]> m_Tris;
            readonly Dictionary<Vector3Int, List<int>> m_Map = new Dictionary<Vector3Int, List<int>>();

            public TriGrid(IEnumerable<Vector3[]> tris)
            {
                m_Tris = tris.ToList();
                for (var i = 0; i < m_Tris.Count; i++)
                {
                    var t = m_Tris[i];
                    var lo = Key(Vector3.Min(t[0], Vector3.Min(t[1], t[2]))); var hi = Key(Vector3.Max(t[0], Vector3.Max(t[1], t[2])));
                    for (var x = lo.x; x <= hi.x; x++)
                        for (var y = lo.y; y <= hi.y; y++)
                            for (var z = lo.z; z <= hi.z; z++)
                            {
                                var k = new Vector3Int(x, y, z);
                                if (!m_Map.TryGetValue(k, out var l)) m_Map[k] = l = new List<int>();
                                l.Add(i);
                            }
                }
            }

            static Vector3Int Key(Vector3 p) => new Vector3Int(Mathf.FloorToInt(p.x / Cell), Mathf.FloorToInt(p.y / Cell), Mathf.FloorToInt(p.z / Cell));

            /// distance to the nearest triangle if closer than maxR, else maxR
            public float Nearest(Vector3 p, float maxR)
            {
                var best = maxR;
                var lo = Key(p - Vector3.one * maxR); var hi = Key(p + Vector3.one * maxR);
                for (var x = lo.x; x <= hi.x; x++)
                    for (var y = lo.y; y <= hi.y; y++)
                        for (var z = lo.z; z <= hi.z; z++)
                        {
                            if (!m_Map.TryGetValue(new Vector3Int(x, y, z), out var l)) continue;
                            foreach (var i in l)
                            {
                                var t = m_Tris[i];
                                var d = (p - ClosestOnTri(p, t[0], t[1], t[2])).magnitude;
                                if (d < best) best = d;
                            }
                        }
                return best;
            }
        }

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

        static string Mm(float d, float cap) => d >= cap - 1e-6f ? $">{cap * 1000f:0}" : $"{d * 1000f:0.0}";
        static string F(Vector3 v) => $"({v.x:0.000}, {v.y:0.000}, {v.z:0.000})";
        static string F4(Vector3 v) => $"({v.x:0.0000}, {v.y:0.0000}, {v.z:0.0000})";
        static string PathOf(Transform t) => t.parent == null ? t.name : PathOf(t.parent) + "/" + t.name;
    }
}
