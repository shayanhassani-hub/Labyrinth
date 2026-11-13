// HingeDriver.cs - turns one part between its closed and open pose about a local axis
// (Documentation/HERO_SPEC.md section 10, "HingeDriver / SlideDriver"). Generic; first used by the
// docking cradle v2: Arm_L 0 -> +75 deg, Arm_R 0 -> -75 deg about local Z, 1.2 s, eased (HERO_SPEC section 3).
//
// The closed pose is the part's localRotation when this component wakes up; the open pose is
// closed * AngleAxis(openAngle, axis) (axis in the part's own local space, i.e. about the pivot the mesh
// origin sits on). Open() / Close() / Toggle() start a move from wherever the part is now, so a call
// during a move reverses it smoothly instead of jumping. All four also sit in the component's context menu
// (Play Mode test).
//
// Sequence wiring (HERO_SPEC section 1 / 10): FacilitySequence (not written yet) calls Open() on both
// cradle arms at release and can listen to onOpenStarted / onOpened. Children (pads, riser) turn with the
// part. If the part has a Rigidbody it must be kinematic.

using UnityEngine;
using UnityEngine.Events;

namespace LabyrinthVR.Gameplay
{
    public class HingeDriver : MonoBehaviour
    {
        [Tooltip("The turning part; defaults to this transform. Its origin must sit on the hinge axis.")]
        public Transform part;
        [Tooltip("Hinge axis in the part's local space. Cradle arms: Z.")]
        public Vector3 axis = Vector3.forward;
        [Tooltip("Open angle in degrees about the axis (signed). Cradle: Arm_L +75, Arm_R -75.")]
        public float openAngle = 75f;
        [Tooltip("Seconds for a full closed -> open move.")]
        public float duration = 1.2f;
        [Tooltip("Ease in and out (smoothstep). Off = constant angular speed.")]
        public bool easeInOut = true;
        public bool startOpen;

        public UnityEvent onOpenStarted = new UnityEvent();
        public UnityEvent onOpened = new UnityEvent();
        public UnityEvent onCloseStarted = new UnityEvent();
        public UnityEvent onClosed = new UnityEvent();

        /// <summary>0 = closed, 1 = open (linear progress; the eased value drives the angle).</summary>
        public float Progress => m_Progress;
        /// <summary>Current angle in degrees from the closed pose.</summary>
        public float Angle => openAngle * Eased(m_Progress);
        public bool IsOpen => m_Progress >= 1f && m_Target >= 1f;
        public bool IsMoving => !Mathf.Approximately(m_Progress, m_Target);

        Quaternion m_Closed;
        float m_Progress, m_Target;
        bool m_Initialized;

        void Awake() => Init();

        void Init()
        {
            if (m_Initialized) return;
            if (part == null) part = transform;
            m_Closed = part.localRotation;
            m_Progress = m_Target = startOpen ? 1f : 0f;
            Apply();
            m_Initialized = true;
        }

        [ContextMenu("Open")]
        public void Open()
        {
            Init();
            if (m_Target >= 1f) return;
            m_Target = 1f;
            onOpenStarted.Invoke();
        }

        [ContextMenu("Close")]
        public void Close()
        {
            Init();
            if (m_Target <= 0f) return;
            m_Target = 0f;
            onCloseStarted.Invoke();
        }

        [ContextMenu("Toggle")]
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

        float Eased(float p) => easeInOut ? Mathf.SmoothStep(0f, 1f, p) : p;

        void Apply()
        {
            part.localRotation = m_Closed * Quaternion.AngleAxis(openAngle * Eased(m_Progress), axis.normalized);
        }
    }
}
