// SlideDriver.cs - moves one part between its closed and open pose along a straight line
// (Documentation/HERO_SPEC.md section 10, "HingeDriver / SlideDriver"). Used by the facility gate:
// the leaf slides -X by 1.70 m in 2.0 s, ease-in-out (HERO_SPEC section 7).
//
// The closed pose is the part's localPosition when this component wakes up; the open pose is
// closed + openOffset (parent-local metres). Open() / Close() / Toggle() start a move from wherever
// the part is now, so a call during a move reverses it smoothly instead of jumping.
//
// Sequence wiring (HERO_SPEC section 1 / 10): GateButton.onPressed -> SlideDriver.Open (set up by
// GateBuilder). FacilitySequence (not written yet) listens to onOpenStarted to enable the room
// teleport collider, and can call Open() itself. If the part has a Rigidbody it must be kinematic;
// the leaf's BoxCollider moves with it and keeps blocking the player and the teleport ray while closed.

using UnityEngine;
using UnityEngine.Events;

namespace LabyrinthVR.Gameplay
{
    public class SlideDriver : MonoBehaviour
    {
        [Tooltip("The moving part; defaults to this transform.")]
        public Transform part;
        [Tooltip("Open pose = closed pose + this offset, in the part's parent space (metres). Gate leaf: -1.70 on X.")]
        public Vector3 openOffset = new Vector3(-1.70f, 0f, 0f);
        [Tooltip("Seconds for a full closed -> open move.")]
        public float duration = 2.0f;
        [Tooltip("Ease in and out (smoothstep). Off = constant speed.")]
        public bool easeInOut = true;
        public bool startOpen;

        public UnityEvent onOpenStarted = new UnityEvent();
        public UnityEvent onOpened = new UnityEvent();
        public UnityEvent onCloseStarted = new UnityEvent();
        public UnityEvent onClosed = new UnityEvent();

        /// <summary>0 = closed, 1 = open (linear progress; the eased value drives the position).</summary>
        public float Progress => m_Progress;
        public bool IsOpen => m_Progress >= 1f && m_Target >= 1f;
        public bool IsMoving => !Mathf.Approximately(m_Progress, m_Target);

        Vector3 m_Closed;
        float m_Progress, m_Target;
        bool m_Initialized;

        void Awake() => Init();

        void Init()
        {
            if (m_Initialized) return;
            if (part == null) part = transform;
            m_Closed = part.localPosition;
            m_Progress = m_Target = startOpen ? 1f : 0f;
            Apply();
            m_Initialized = true;
        }

        public void Open()
        {
            Init();
            if (m_Target >= 1f) return;
            m_Target = 1f;
            onOpenStarted.Invoke();
        }

        public void Close()
        {
            Init();
            if (m_Target <= 0f) return;
            m_Target = 0f;
            onCloseStarted.Invoke();
        }

        public void Toggle()
        {
            if (m_Target >= 1f) Close(); else Open();
        }

        void Update()
        {
            if (!IsMoving) return;
            var step = duration > 0f ? Time.deltaTime / duration : 1f;
            m_Progress = Mathf.MoveTowards(m_Progress, m_Target, step);
            Apply();
            if (!IsMoving) (m_Target >= 1f ? onOpened : onClosed).Invoke();
        }

        void Apply()
        {
            var t = easeInOut ? Mathf.SmoothStep(0f, 1f, m_Progress) : m_Progress;
            part.localPosition = m_Closed + openOffset * t;
        }
    }
}
