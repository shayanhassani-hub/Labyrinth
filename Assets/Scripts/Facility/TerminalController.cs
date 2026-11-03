// TerminalController.cs - the control terminal's own state and lights (Documentation/HERO_SPEC.md sections 1, 5, 9, 10;
// build notes Documentation/Heroes/Terminal_BUILD.md).
//
// HERO_SPEC section 1, state 2 "Armed": the player presses the terminal's central button ->
//   t = 0: three terminal indicators cyan -> red instantly, red beacon on.
// Everything after that (room accent lights, service arm fold, lever) belongs to FacilitySequence (not written yet),
// which listens to onArmed. Section 9: Released keeps the terminal red; Release() is for FacilitySequence to call.
//
// The switching parts are separate meshes that share the hero material M_LAB_HERO_Terminal: Indicators_01 (the three
// strips on the player's right) and Beacon_01 (the lens). Their emission-map texels are WHITE, so the colour comes from
// _EmissionColor, set per renderer with a MaterialPropertyBlock - no runtime material copies. The Body's own strips
// carry their cyan in the emission map and use the material's _EmissionColor (white x intensity).
// [ExecuteAlways] so the Editor shows the Standby colours (without the block the white texels would glow white).
//
// Wiring (TerminalBuilder): the button's GateButton.onPressed -> Arm() (persistent). A second press does nothing.
// Context menu: "Arm", "Release", "Reset To Standby" for Play Mode tests without a headset.

using UnityEngine;
using UnityEngine.Events;

namespace LabyrinthVR.Gameplay
{
    public enum TerminalState { Standby, Armed, Released }

    [ExecuteAlways]
    public class TerminalController : MonoBehaviour
    {
        static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");

        [Header("Switching renderers (share M_LAB_HERO_Terminal)")]
        [Tooltip("LAB_HERO_Terminal_Indicators_01: the three strips that turn red on Armed.")]
        public Renderer indicators;
        [Tooltip("LAB_HERO_Terminal_Beacon_01: the beacon lens on Pillar_L.")]
        public Renderer beacon;

        [Header("Colours (sRGB, as in STYLE_GUIDE; converted to linear for the shader)")]
        public Color standbyIndicatorColor = new Color(70f / 255f, 170f / 255f, 1f);     // cyan emissive 70 170 255
        public Color armedColor = new Color(230f / 255f, 35f / 255f, 25f / 255f);         // red 230 35 25 (Armed only)
        public Color beaconOffColor = Color.black;
        [Tooltip("Emission intensity for the switching parts; keep it equal to the material's so the cyan matches the Body's strips. Must not clip to white (STYLE_GUIDE).")]
        [Min(0f)] public float indicatorIntensity = 1.0f;
        [Min(0f)] public float beaconIntensity = 1.6f;

        [Header("Beacon pulse (optional; HERO_SPEC only asks for 'on')")]
        public bool pulseWhenArmed = false;
        public bool pulseWhenReleased = false;
        [Min(0.01f)] public float pulseHz = 0.8f;
        [Range(0f, 1f)] public float pulseMin = 0.35f;

        [Header("State")]
        [SerializeField] TerminalState m_State = TerminalState.Standby;

        public UnityEvent onArmed = new UnityEvent();
        public UnityEvent onReleased = new UnityEvent();

        public TerminalState State => m_State;

        MaterialPropertyBlock m_Block;

        void OnEnable() => Apply(1f);

        void OnValidate() => Apply(1f);

        void Update()
        {
            if (!Application.isPlaying) return;
            var pulse = (m_State == TerminalState.Armed && pulseWhenArmed) || (m_State == TerminalState.Released && pulseWhenReleased);
            if (!pulse) return;
            var t = 0.5f + 0.5f * Mathf.Sin(Time.time * pulseHz * 2f * Mathf.PI);
            SetBeacon(armedColor, beaconIntensity * Mathf.Lerp(pulseMin, 1f, t));
        }

        /// HERO_SPEC section 1, state 2. Called by the button (GateButton.onPressed). Only the first call counts.
        [ContextMenu("Arm")]
        public void Arm()
        {
            if (m_State != TerminalState.Standby) return;
            m_State = TerminalState.Armed;
            Apply(1f);
            if (Application.isPlaying) onArmed.Invoke();
        }

        /// HERO_SPEC section 1, state 3 (called by FacilitySequence when the lever is pulled). The terminal stays red.
        [ContextMenu("Release")]
        public void Release()
        {
            if (m_State != TerminalState.Armed) return;
            m_State = TerminalState.Released;
            Apply(1f);
            if (Application.isPlaying) onReleased.Invoke();
        }

        [ContextMenu("Reset To Standby")]
        public void ResetToStandby()
        {
            m_State = TerminalState.Standby;
            Apply(1f);
        }

        void Apply(float beaconScale)
        {
            var red = m_State != TerminalState.Standby;
            SetColor(indicators, red ? armedColor : standbyIndicatorColor, indicatorIntensity);
            SetBeacon(red ? armedColor : beaconOffColor, red ? beaconIntensity * beaconScale : 0f);
        }

        void SetBeacon(Color c, float intensity) => SetColor(beacon, c, intensity);

        void SetColor(Renderer r, Color srgb, float intensity)
        {
            if (r == null) return;
            if (m_Block == null) m_Block = new MaterialPropertyBlock();
            r.GetPropertyBlock(m_Block);
            m_Block.SetColor(EmissionColorId, srgb.linear * intensity);
            r.SetPropertyBlock(m_Block);
        }
    }
}
