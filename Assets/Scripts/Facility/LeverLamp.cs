// LeverLamp.cs - the caged amber lamp on the lever stand's housing (HERO_SPEC sections 1 and 6).
// Off -> amber pulse when Armed (LeverHandle.Arm), then `LeverHandle.lampAfterPull` once the lever is pulled.
// The lamp glass is its own part (LAB_HERO_LeverStand_Lamp_01) with the shared hero material; its emission map
// holds the amber (STYLE_GUIDE 240 150 60). This component scales the emission through a MaterialPropertyBlock
// on the lamp's renderer only: no material copies, the cyan strip on the body is untouched.
// Note: a renderer with a property block drops out of the SRP Batcher (one extra, cheap draw).

using UnityEngine;

namespace LabyrinthVR.Gameplay
{
    [RequireComponent(typeof(Renderer))]
    public class LeverLamp : MonoBehaviour
    {
        public enum Mode { Off, Pulse, Steady }

        public Mode mode = Mode.Off;
        [Tooltip("Emission multiplier when fully on (the map carries the colour; keep it from clipping to white).")]
        public float onIntensity = 1.5f;
        [Tooltip("Emission multiplier at the low point of a pulse.")]
        public float pulseLow = 0.15f;
        [Tooltip("Seconds per pulse.")]
        public float pulsePeriod = 1.0f;

        static readonly int EmissionColorId = Shader.PropertyToID("_EmissionColor");
        Renderer m_Renderer;
        MaterialPropertyBlock m_Block;
        float m_Last = -1f;
        float m_PulseStart;

        void Awake()
        {
            m_Renderer = GetComponent<Renderer>();
            m_Block = new MaterialPropertyBlock();
            Write(Level(), true);
        }

        public void SetMode(Mode m)
        {
            if (m == Mode.Pulse && mode != Mode.Pulse) m_PulseStart = Time.time;
            mode = m;
            Write(Level(), true);
        }

        float Level()
        {
            switch (mode)
            {
                case Mode.Steady: return onIntensity;
                case Mode.Pulse:
                    var t = (Time.time - m_PulseStart) / Mathf.Max(0.05f, pulsePeriod);
                    var s = 0.5f - 0.5f * Mathf.Cos(t * 2f * Mathf.PI);           // starts dark, smooth
                    return Mathf.Lerp(pulseLow, onIntensity, s);
                default: return 0f;
            }
        }

        void Update()
        {
            if (mode == Mode.Pulse) Write(Level(), false);
        }

        void Write(float level, bool force)
        {
            if (!force && Mathf.Abs(level - m_Last) < 1e-3f) return;
            m_Last = level;
            m_Renderer.GetPropertyBlock(m_Block);
            m_Block.SetColor(EmissionColorId, Color.white * level);
            m_Renderer.SetPropertyBlock(m_Block);
        }
    }
}
