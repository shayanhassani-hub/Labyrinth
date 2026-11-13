// AtmosphereController.cs - room atmosphere states (Documentation/HERO_SPEC.md section 9, STYLE_GUIDE colours).
//
//   Standby   cyan accents (STYLE_GUIDE emission 70 170 255): the materials' own look, no property blocks.
//   Armed     cyan -> orange over armedDuration (2.5 s, smoothstep).
//   Released  orange with a slow alarm pulse (owner decision); if Released comes mid-transition, the blend finishes first.
//
// Three channels, all runtime-cheap (HERO_SPEC section 9):
// - Emissive accent strips: renderers whose emission map holds ONLY the cyan accent (checked per renderer by UV sampling
//   in FacilitySequenceBuilder; renderers that mix cyan with amber lamps are not listed). Emission = map x _EmissionColor,
//   so a per-channel _EmissionColor = target / mapCyan (linear) turns the cyan texels into the target colour exactly;
//   set through a MaterialPropertyBlock (no material copies). In Standby the block is cleared, so the renderers stay in
//   the SRP Batcher until the sequence leaves Standby.
// - At most a few realtime accent lights (no shadows): colour lerps, intensity follows the pulse.
// - Ambient tint: the scene's ambient probe captured at Awake, scaled per colour channel. Restored on disable.
// The colour lerp runs in sRGB (cyan -> a muted warm grey -> orange): no detour through green or magenta.

using UnityEngine;
using UnityEngine.Rendering;

namespace LabyrinthVR.Gameplay
{
    public class AtmosphereController : MonoBehaviour
    {
        public enum Mode { Standby, Armed, Released }

        static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");

        [Header("Emissive accent strips (emission map = cyan only)")]
        public Renderer[] accentRenderers = new Renderer[0];
        [Tooltip("The cyan baked into the hero emission maps (sRGB, STYLE_GUIDE 70 170 255).")]
        public Color mapCyan = new Color(70f / 255f, 170f / 255f, 1f);
        [Tooltip("Material emission intensity the hero materials use (x1).")]
        [Min(0f)] public float emissionIntensity = 1f;

        [Header("Accent lights (realtime, no shadows; keep to 2-3)")]
        public Light[] accentLights = new Light[0];

        [Header("Colours (sRGB)")]
        public Color standbyColor = new Color(70f / 255f, 170f / 255f, 1f);
        [Tooltip("Orange accent light (STYLE_GUIDE 'value set in the lighting pass'); distinct from amber 240 150 60 and red 230 35 25.")]
        public Color alarmColor = new Color(1f, 110f / 255f, 25f / 255f);

        [Header("Timing")]
        [Tooltip("Armed: cyan -> orange (HERO_SPEC section 1: 2.5 s, smoothstep).")]
        [Min(0.01f)] public float armedDuration = 2.5f;
        [Tooltip("Released: seconds per alarm pulse (slow).")]
        [Min(0.1f)] public float pulsePeriod = 2.4f;
        [Tooltip("Released: brightness at the low point of the pulse (1 = no pulse).")]
        [Range(0f, 1f)] public float pulseMin = 0.35f;
        public bool pulseEmission = true;
        public bool pulseLights = true;

        [Header("Ambient")]
        public bool tintAmbient = true;
        [Tooltip("Per-channel multiplier on the ambient probe when fully orange (white = no change).")]
        public Color ambientAlarmTint = new Color(1.0f, 0.78f, 0.68f);

        public Mode CurrentMode => m_Mode;
        /// 0 = cyan, 1 = orange
        public float Blend => m_Blend;

        Mode m_Mode = Mode.Standby;
        float m_Blend, m_BlendFrom, m_T, m_PulseT;
        MaterialPropertyBlock m_Block;
        float[] m_LightBase;
        SphericalHarmonicsL2 m_Ambient;
        bool m_HaveAmbient, m_BlocksSet;

        void Awake()
        {
            m_LightBase = new float[accentLights.Length];
            for (int i = 0; i < accentLights.Length; i++) m_LightBase[i] = accentLights[i] != null ? accentLights[i].intensity : 0f;
            m_Ambient = RenderSettings.ambientProbe;
            m_HaveAmbient = true;
        }

        void OnDisable()
        {
            if (m_HaveAmbient) RenderSettings.ambientProbe = m_Ambient;
            ClearBlocks();
            for (int i = 0; i < accentLights.Length; i++)
                if (accentLights[i] != null) { accentLights[i].color = standbyColor; accentLights[i].intensity = m_LightBase[i]; }
        }

        [ContextMenu("Standby")]
        public void SetStandby()
        {
            m_Mode = Mode.Standby; m_Blend = 0f;
            Apply(0f, 1f);
        }

        [ContextMenu("Armed")]
        public void SetArmed()
        {
            if (m_Mode != Mode.Standby) return;
            m_Mode = Mode.Armed; m_BlendFrom = m_Blend; m_T = 0f;
        }

        [ContextMenu("Released")]
        public void SetReleased()
        {
            if (m_Mode == Mode.Released) return;
            if (m_Mode == Mode.Standby) { m_BlendFrom = m_Blend; m_T = 0f; }
            m_Mode = Mode.Released; m_PulseT = 0f;
        }

        /// Released at once, fully orange (FacilitySequence Debug/Skip To Released).
        public void SnapReleased()
        {
            m_Mode = Mode.Released; m_Blend = 1f; m_BlendFrom = 1f; m_T = armedDuration; m_PulseT = 0f;
        }

        void Update()
        {
            if (m_Mode == Mode.Standby) return;
            var dt = Time.deltaTime;
            if (m_Blend < 1f)
            {
                m_T += dt;
                m_Blend = Mathf.Lerp(m_BlendFrom, 1f, Mathf.SmoothStep(0f, 1f, m_T / armedDuration));
                if (m_T >= armedDuration) m_Blend = 1f;
            }
            var level = 1f;
            if (m_Mode == Mode.Released && m_Blend >= 1f)
            {
                // starts at full brightness, then a slow cosine down to pulseMin and back
                m_PulseT += dt;
                level = Mathf.Lerp(pulseMin, 1f, 0.5f + 0.5f * Mathf.Cos(m_PulseT / pulsePeriod * 2f * Mathf.PI));
            }
            Apply(m_Blend, level);
        }

        void Apply(float blend, float level)
        {
            var srgb = Color.Lerp(standbyColor, alarmColor, blend);

            // emissive strips
            if (blend <= 0f && level >= 1f) ClearBlocks();
            else
            {
                var target = srgb.linear * emissionIntensity * (pulseEmission ? level : 1f);
                var cyan = mapCyan.linear;
                var e = new Color(target.r / Mathf.Max(cyan.r, 1e-4f), target.g / Mathf.Max(cyan.g, 1e-4f), target.b / Mathf.Max(cyan.b, 1e-4f), 1f);
                if (m_Block == null) m_Block = new MaterialPropertyBlock();
                foreach (var r in accentRenderers)
                {
                    if (r == null) continue;
                    r.GetPropertyBlock(m_Block);
                    m_Block.SetColor(EmissionColorId, e);
                    r.SetPropertyBlock(m_Block);
                }
                m_BlocksSet = true;
            }

            // lights
            for (int i = 0; i < accentLights.Length; i++)
            {
                var l = accentLights[i]; if (l == null) continue;
                l.color = srgb;
                l.intensity = m_LightBase[i] * (pulseLights ? level : 1f);
            }

            // ambient
            if (tintAmbient && m_HaveAmbient)
            {
                var tint = Color.Lerp(Color.white, ambientAlarmTint, blend);
                var sh = m_Ambient;
                for (int c = 0; c < 9; c++) { sh[0, c] *= tint.r; sh[1, c] *= tint.g; sh[2, c] *= tint.b; }
                RenderSettings.ambientProbe = sh;
            }
        }

        void ClearBlocks()
        {
            if (!m_BlocksSet) return;
            foreach (var r in accentRenderers) if (r != null) r.SetPropertyBlock(null);
            m_BlocksSet = false;
        }
    }
}
