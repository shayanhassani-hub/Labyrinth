// FacilitySequenceBuilder.cs - wires the launch sequence in the open scene (Documentation/HERO_SPEC.md sections 1, 9, 10).
//
// Menu:  Tools > Labyrinth > Facility Sequence: Build    (Build(): objects, references, scene poses, then Verify())
//        Tools > Labyrinth > Facility Sequence: Verify   (Verify())
// Code:  LabyrinthVR.EnvironmentTools.FacilitySequenceBuilder.Build() / Verify()
//
// Build (one Undo group; marks the scene dirty, never saves it):
//   SYS_FacilitySequence   FacilitySequence: Gate Leaf SlideDriver, TerminalController, ServiceArmDriver, LeverHandle,
//                          Cradle Arm_L / Arm_R HingeDrivers, AtmosphereController, DroneAI2 + DroneHoverAIV2,
//                          PropellerSpin x4, XR Origin, NAV_TeleportFloor's room BoxCollider.
//   FX_Atmosphere          AtmosphereController + LIGHT_Accent_Cradle, LIGHT_Accent_Terminal (realtime point, no shadows).
//                          Accent renderers: hero renderers whose emission map holds only the cyan accent (UV-sampled
//                          in Verify): Gate Leaf, Terminal Body, LeverStand Body, Cradle Base. Gate ButtonPanel is left
//                          out (cyan and the amber lamp share it; the per-channel recolour would blow the amber out).
//   DroneAI2               docking pose (-0.032, 2.000, 4.754), yaw -28.3 (resting on the Cradle v2 pads);
//                          DroneHoverAIV2 disabled; PropellerSpin added to Propellor1-4_low (pivots on the hubs), disabled.
//   XR Origin (XR Rig)     spawn (-1, 0, 13), yaw 180.
// The scene poses equal FacilitySequence's Arrival values, so the Editor shows the start state; Arrival re-applies them.

using System.Collections.Generic;
using System.Linq;
using System.Text;
using LabyrinthVR.Gameplay;
using Unity.XR.CoreUtils;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace LabyrinthVR.EnvironmentTools
{
    public static class FacilitySequenceBuilder
    {
        const string SequenceName = "SYS_FacilitySequence";
        const string AtmosphereName = "FX_Atmosphere";
        const string DroneName = "DroneAI2";
        static readonly string[] AccentPaths = { "HERO_Gate/Leaf", "HERO_Terminal/Body", "HERO_LeverStand/Body", "HERO_Cradle/Base" };
        static readonly (string name, Vector3 pos)[] AccentLights =
        {
            ("LIGHT_Accent_Cradle", new Vector3(1.2f, 3.3f, 6.2f)),
            ("LIGHT_Accent_Terminal", new Vector3(-2.2f, 3.3f, -0.8f)),
        };
        const float AccentLightIntensity = 1.5f, AccentLightRange = 6f;

        [MenuItem("Tools/Labyrinth/Facility Sequence: Build")]
        public static void BuildMenu() => Build();

        [MenuItem("Tools/Labyrinth/Facility Sequence: Verify")]
        public static void VerifyMenu() => Verify();

        public static string Build()
        {
            var log = new StringBuilder("[FacilitySequenceBuilder] build\n");
            Undo.IncrementCurrentGroup();
            var group = Undo.GetCurrentGroup();
            Undo.SetCurrentGroupName("Build Facility Sequence");

            // atmosphere
            var atmoGo = GameObject.Find(AtmosphereName);
            if (atmoGo == null) { atmoGo = new GameObject(AtmosphereName); Undo.RegisterCreatedObjectUndo(atmoGo, "atmo"); }
            var atmo = GetOrAdd<AtmosphereController>(atmoGo);
            var lights = new List<Light>();
            foreach (var (name, pos) in AccentLights)
            {
                var t = atmoGo.transform.Find(name);
                if (t == null) { var go = new GameObject(name); Undo.RegisterCreatedObjectUndo(go, name); t = go.transform; t.SetParent(atmoGo.transform, false); }
                t.position = pos;
                var l = GetOrAdd<Light>(t.gameObject);
                l.type = LightType.Point; l.lightmapBakeType = LightmapBakeType.Realtime; l.shadows = LightShadows.None;
                l.range = AccentLightRange; l.intensity = AccentLightIntensity; l.color = atmo.standbyColor;
                lights.Add(l);
            }
            Undo.RecordObject(atmo, "atmo");
            atmo.accentLights = lights.ToArray();
            atmo.accentRenderers = AccentPaths.Select(p => Find(p)?.GetComponent<Renderer>()).Where(r => r != null).ToArray();
            log.AppendLine($"atmosphere: {atmo.accentRenderers.Length} accent renderers, {lights.Count} lights");

            // drone
            var drone = GameObject.Find(DroneName);
            var hover = drone != null ? drone.GetComponent<DroneHoverAIV2>() : null;
            var props = new List<PropellerSpin>();
            if (drone != null)
            {
                Undo.RecordObject(drone.transform, "drone pose");
                drone.transform.SetPositionAndRotation(new Vector3(-0.032f, 2.000f, 4.754f), Quaternion.Euler(0f, -28.3f, 0f));
                if (hover != null) { Undo.RecordObject(hover, "hover"); hover.enabled = false; }
                foreach (var t in drone.GetComponentsInChildren<Transform>(true).Where(t => t.name.StartsWith("Propellor")).OrderBy(t => t.name))
                {
                    var ps = GetOrAdd<PropellerSpin>(t.gameObject);
                    Undo.RecordObject(ps, "spin"); ps.enabled = false;
                    props.Add(ps);
                }
            }

            // player
            var xr = Object.FindAnyObjectByType<XROrigin>(FindObjectsInactive.Include);

            // sequence
            var seqGo = GameObject.Find(SequenceName);
            if (seqGo == null) { seqGo = new GameObject(SequenceName); Undo.RegisterCreatedObjectUndo(seqGo, "seq"); }
            var seq = GetOrAdd<FacilitySequence>(seqGo);
            Undo.RecordObject(seq, "seq");
            seq.gate = Find("HERO_Gate/Leaf")?.GetComponent<SlideDriver>();
            seq.terminal = Object.FindAnyObjectByType<TerminalController>(FindObjectsInactive.Include);
            seq.serviceArm = Object.FindAnyObjectByType<ServiceArmDriver>(FindObjectsInactive.Include);
            seq.lever = Object.FindAnyObjectByType<LeverHandle>(FindObjectsInactive.Include);
            seq.cradleArmL = Find("HERO_Cradle/Arm_L")?.GetComponent<HingeDriver>();
            seq.cradleArmR = Find("HERO_Cradle/Arm_R")?.GetComponent<HingeDriver>();
            seq.atmosphere = atmo;
            seq.drone = drone != null ? drone.transform : null;
            seq.droneHover = hover;
            seq.propellers = props.ToArray();
            seq.xrOrigin = xr != null ? xr.transform : null;
            seq.roomTeleportCollider = RoomTeleportCollider();
            if (xr != null)
            {
                Undo.RecordObject(xr.transform, "spawn");
                xr.transform.SetPositionAndRotation(seq.spawnPosition, Quaternion.Euler(0f, seq.spawnYaw, 0f));
            }

            Undo.CollapseUndoOperations(group);
            EditorSceneManager.MarkSceneDirty(UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            log.Append(Verify());
            return log.ToString();
        }

        public static string Verify()
        {
            var sb = new StringBuilder("[FacilitySequenceBuilder] verify\n");
            var fails = 0;
            void Check(bool ok, string what) { sb.AppendLine((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; }

            var seq = Object.FindAnyObjectByType<FacilitySequence>(FindObjectsInactive.Include);
            Check(seq != null, "FacilitySequence in the scene");
            if (seq == null) { sb.AppendLine("RESULT: FAIL"); Debug.Log(sb); return sb.ToString(); }
            Check(seq.gate != null && seq.terminal != null && seq.serviceArm != null && seq.lever != null && seq.cradleArmL != null
                  && seq.cradleArmR != null && seq.atmosphere != null && seq.drone != null && seq.droneHover != null && seq.xrOrigin != null
                  && seq.roomTeleportCollider != null, "all references set");

            // existing persistent wiring the sequence relies on (hero builders)
            var gateButton = Find("HERO_Gate/Button")?.GetComponent<GateButton>();
            Check(HasPersistent(gateButton, seq.gate, "Open"), "Gate button onPressed -> Leaf SlideDriver.Open (GateBuilder)");
            var termButton = Find("HERO_Terminal/Button")?.GetComponent<GateButton>();
            Check(HasPersistent(termButton, seq.terminal, "Arm"), "Terminal button onPressed -> TerminalController.Arm (TerminalBuilder)");
            Check(seq.cradleArmL != null && Mathf.Approximately(seq.cradleArmL.openAngle, 75f) && seq.cradleArmR != null && Mathf.Approximately(seq.cradleArmR.openAngle, -75f),
                  "Cradle HingeDrivers +75 / -75");
            Check(seq.serviceArm != null && !seq.serviceArm.startStowed, "ServiceArm starts in the working pose");

            // drone at the docking pose, scripts off
            if (seq.drone != null)
            {
                var p = seq.drone.position; var yaw = Mathf.DeltaAngle(0f, seq.drone.eulerAngles.y);
                Check((p - seq.dockPosition).magnitude < 1e-4f && Mathf.Abs(Mathf.DeltaAngle(yaw, seq.dockYaw)) < 0.01f,
                      $"drone at the docking pose {p.ToString("F3")} yaw {yaw:0.0} (= Arrival {seq.dockPosition.ToString("F3")} yaw {seq.dockYaw})");
                Check(seq.droneHover != null && !seq.droneHover.enabled, "DroneHoverAIV2 disabled in the scene");
                Check(seq.propellers.Length == 4 && seq.propellers.All(x => x != null && !x.enabled), $"PropellerSpin on {seq.propellers.Length} propellers, all disabled");
            }
            if (seq.xrOrigin != null)
                Check((seq.xrOrigin.position - seq.spawnPosition).magnitude < 1e-4f && Mathf.Abs(Mathf.DeltaAngle(seq.xrOrigin.eulerAngles.y, seq.spawnYaw)) < 0.01f,
                      $"XR Origin at the spawn {seq.xrOrigin.position.ToString("F2")} yaw {seq.xrOrigin.eulerAngles.y:0}");
            if (seq.roomTeleportCollider != null)
            {
                var b = seq.roomTeleportCollider.bounds;
                Check(b.Contains(new Vector3(0f, b.center.y, 3f)) && !b.Contains(new Vector3(-1f, b.center.y, 12f)),
                      $"room teleport collider = the room box {b.min.ToString("F1")}..{b.max.ToString("F1")} (corridor collider untouched)");
            }

            // atmosphere
            var atmo = seq.atmosphere;
            if (atmo != null)
            {
                Check(atmo.accentLights.Length >= 1 && atmo.accentLights.Length <= 3 && atmo.accentLights.All(l => l != null && l.lightmapBakeType == LightmapBakeType.Realtime && l.shadows == LightShadows.None),
                      $"{atmo.accentLights.Length} accent lights, realtime, no shadows (HERO_SPEC 9: at most 2-3)");
                foreach (var r in atmo.accentRenderers)
                {
                    var (cyan, nonCyan) = SampleEmission(r);
                    Check(nonCyan == 0, $"accent {Path(r.transform)}: emission samples cyan {cyan}, other colours {nonCyan}");
                }
                var buttonPanel = Find("HERO_Gate/ButtonPanel")?.GetComponent<Renderer>();
                if (buttonPanel != null)
                {
                    var (c, n) = SampleEmission(buttonPanel);
                    sb.AppendLine($"INFO not an accent: HERO_Gate/ButtonPanel emission samples cyan {c}, other (amber lamp) {n}");
                }
            }

            sb.AppendLine(fails == 0 ? "RESULT: PASS - scene marked dirty only by Build; NOT saved." : $"RESULT: FAIL ({fails})");
            Debug.Log(sb.ToString());
            return sb.ToString();
        }

        // ------------------------------------------------------------------ helpers

        static Collider RoomTeleportCollider()
        {
            var nav = GameObject.Find("NAV_TeleportFloor");
            if (nav == null) return null;
            return nav.GetComponents<BoxCollider>().FirstOrDefault(c => c.bounds.Contains(new Vector3(0f, c.bounds.center.y, 3f)));
        }

        static bool HasPersistent(GateButton b, Object target, string method)
        {
            if (b == null || target == null) return false;
            for (int i = 0; i < b.onPressed.GetPersistentEventCount(); i++)
                if (b.onPressed.GetPersistentTarget(i) == target && b.onPressed.GetPersistentMethodName(i) == method) return true;
            return false;
        }

        // UV-samples the renderer's emission map (PNG read from disk): 10 samples per triangle.
        static (int cyan, int other) SampleEmission(Renderer r)
        {
            var mat = r.sharedMaterial; var mf = r.GetComponent<MeshFilter>();
            if (mat == null || mf == null || !mat.HasProperty("_EmissionMap") || mat.GetTexture("_EmissionMap") == null) return (0, -1);
            var tex = new Texture2D(2, 2);
            ImageConversion.LoadImage(tex, System.IO.File.ReadAllBytes(AssetDatabase.GetAssetPath(mat.GetTexture("_EmissionMap"))));
            int cyan = 0, other = 0;
            var mesh = mf.sharedMesh; var uv = mesh.uv; var tris = mesh.triangles;
            for (int i = 0; i < tris.Length; i += 3)
            {
                Vector2 a = uv[tris[i]], b = uv[tris[i + 1]], c = uv[tris[i + 2]];
                for (int s = 0; s < 10; s++)
                {
                    float u = ((s * 7) % 10 + 0.5f) / 10f, v = ((s * 3) % 10 + 0.5f) / 10f;
                    if (u + v > 1f) { u = 1f - u; v = 1f - v; }
                    var p = a + (b - a) * u + (c - a) * v;
                    var col = (Color32)tex.GetPixelBilinear(p.x, p.y);
                    if (Mathf.Max(col.r, col.g, col.b) <= 20) continue;
                    if (col.b > col.r + 60 && col.b >= col.g) cyan++; else other++;
                }
            }
            Object.DestroyImmediate(tex);
            return (cyan, other);
        }

        static T GetOrAdd<T>(GameObject go) where T : Component
        {
            var c = go.GetComponent<T>();
            return c != null ? c : Undo.AddComponent<T>(go);
        }

        static Transform Find(string path)
        {
            var parts = path.Split('/');
            var root = GameObject.Find(parts[0]);
            if (root == null) return null;
            return parts.Length == 1 ? root.transform : root.transform.Find(string.Join("/", parts.Skip(1)));
        }

        static string Path(Transform t) => t.parent == null ? t.name : Path(t.parent) + "/" + t.name;
    }
}
