// LabyrinthTilt.cs - the Labyrinth v2 "pan model" control (Documentation/HERO_SPEC.md section 8).
// Lives on LabyrinthPivot (kinematic Rigidbody). The pivot's position never changes; only its
// pitch and roll do, and never its yaw.
//
// Grab: the XRSimpleInteractable on the handle. A select is accepted only when the interactor's
// attach point is within grabRadius of the handle collider (no far-ray or poke grabs).
// While held:
//   forward/back = the hand's elevation seen from the pivot (vertical plane along the board's
//                  forward axis), relative to the elevation at grab; lifting the hand lifts the
//                  handle edge and dips the far edge.
//   sideways     = the hand's twist around the forward axis since the grab (wrist roll).
//   Sideways hand movement does nothing. Both are combined into a target up-vector, clamped to a
//   cone of maxTilt around world up, and turned into a rotation by the shortest arc from world up.
// FixedUpdate moves the Rigidbody toward the target with MoveRotation, capped at maxAngularSpeed.
// On release the board keeps its current tilt.
//
// All the maths is in the static ComputeTargetRotation (tested by LabyrinthTiltTests, no XR needed).

using UnityEngine;
using UnityEngine.XR.Interaction.Toolkit;
using UnityEngine.XR.Interaction.Toolkit.Filtering;
using UnityEngine.XR.Interaction.Toolkit.Interactables;
using UnityEngine.XR.Interaction.Toolkit.Interactors;

namespace LabyrinthVR.Gameplay
{
    [RequireComponent(typeof(Rigidbody))]
    public class LabyrinthTilt : MonoBehaviour, IXRSelectFilter
    {
        public float maxTilt = 12f;           // degrees, cone around world up
        public float maxAngularSpeed = 90f;   // degrees per second
        public float grabRadius = 0.25f;      // metres from the handle collider
        public XRSimpleInteractable handle;
        public Collider handleCollider;

        /// <summary>Hand pose and board tilt stored at the moment of the grab.</summary>
        public struct GrabState
        {
            public Vector3 handPosition;
            public Quaternion handRotation;
            public float boardPitch;   // degrees, + = far edge down
            public float boardRoll;    // degrees, + = same sense as a + twist around forward
        }

        Rigidbody m_Body;
        Vector3 m_Pivot;               // world position, fixed at Awake
        Vector3 m_Forward;             // horizontal board forward (yaw frame), fixed at Awake
        Transform m_Hand;              // pose source while held, null when released
        GrabState m_Grab;
        Quaternion m_Target;

        public bool IsHeld => m_Hand != null;
        public Quaternion TargetRotation => m_Target;

        void Awake()
        {
            m_Body = GetComponent<Rigidbody>();
            m_Pivot = transform.position;
            m_Forward = HorizontalForward(transform.parent != null ? transform.parent.rotation : Quaternion.identity);
            m_Target = transform.rotation;
        }

        void OnEnable()
        {
            if (handle == null) return;
            handle.selectFilters.Add(this);
            handle.selectEntered.AddListener(OnSelectEntered);
            handle.selectExited.AddListener(OnSelectExited);
        }

        void OnDisable()
        {
            if (handle == null) return;
            handle.selectFilters.Remove(this);
            handle.selectEntered.RemoveListener(OnSelectEntered);
            handle.selectExited.RemoveListener(OnSelectExited);
            EndGrab();
        }

        // IXRSelectFilter: near grabs only.
        public bool canProcess => isActiveAndEnabled;

        public bool Process(IXRSelectInteractor interactor, IXRSelectInteractable interactable)
        {
            if (interactor is XRPokeInteractor) return false;
            var attach = interactor.GetAttachTransform(interactable);
            if (attach == null || handleCollider == null) return false;
            var p = attach.position;
            return (handleCollider.ClosestPoint(p) - p).sqrMagnitude <= grabRadius * grabRadius;
        }

        void OnSelectEntered(SelectEnterEventArgs args) => BeginGrab(args.interactorObject.transform);

        void OnSelectExited(SelectExitEventArgs args)
        {
            if (args.interactorObject.transform == m_Hand) EndGrab();
        }

        /// <summary>Start following a hand. Also used by the Play mode check with a fake hand.</summary>
        public void BeginGrab(Transform hand)
        {
            m_Hand = hand;
            m_Grab = CreateGrabState(m_Body != null ? m_Body.rotation : transform.rotation, m_Forward, hand.position, hand.rotation);
        }

        /// <summary>Stop following; the board keeps the tilt it has right now.</summary>
        public void EndGrab()
        {
            m_Hand = null;
            m_Target = m_Body != null ? m_Body.rotation : transform.rotation;
        }

        void FixedUpdate()
        {
            if (m_Hand != null)
                m_Target = ComputeTargetRotation(m_Pivot, m_Forward, m_Grab, m_Hand.position, m_Hand.rotation, maxTilt);
            var next = Quaternion.RotateTowards(m_Body.rotation, m_Target, maxAngularSpeed * Time.fixedDeltaTime);
            m_Body.MoveRotation(next);
        }

        // ---------------------------------------------------------------- pure maths

        /// <summary>Horizontal forward of a yaw frame (the board's forward with pitch/roll removed).</summary>
        public static Vector3 HorizontalForward(Quaternion frame)
        {
            var f = Vector3.ProjectOnPlane(frame * Vector3.forward, Vector3.up);
            return f.sqrMagnitude > 1e-8f ? f.normalized : Vector3.forward;
        }

        public static GrabState CreateGrabState(Quaternion boardRotation, Vector3 forward, Vector3 handPosition, Quaternion handRotation)
        {
            TiltAngles(boardRotation * Vector3.up, forward, out var pitch, out var roll);
            return new GrabState { handPosition = handPosition, handRotation = handRotation, boardPitch = pitch, boardRoll = roll };
        }

        /// <summary>Hand pose + grab state -> target board rotation (zero yaw, within the maxTilt cone).</summary>
        public static Quaternion ComputeTargetRotation(Vector3 pivot, Vector3 forward, GrabState grab,
            Vector3 handPosition, Quaternion handRotation, float maxTiltDeg)
        {
            forward = Vector3.ProjectOnPlane(forward, Vector3.up).normalized;
            var right = Vector3.Cross(Vector3.up, forward);

            // Forward/back: change in the hand's elevation around the pivot since the grab.
            var pitch = grab.boardPitch + Mathf.DeltaAngle(Elevation(pivot, forward, grab.handPosition), Elevation(pivot, forward, handPosition));
            // Sideways: wrist twist around the forward axis since the grab.
            var roll = grab.boardRoll + TwistAngle(handRotation * Quaternion.Inverse(grab.handRotation), forward);

            // Keep tan() finite; the cone clamp below is the real limit.
            pitch = Mathf.Clamp(pitch, -80f, 80f);
            roll = Mathf.Clamp(roll, -80f, 80f);
            var up = (Vector3.up + Mathf.Tan(pitch * Mathf.Deg2Rad) * forward - Mathf.Tan(roll * Mathf.Deg2Rad) * right).normalized;

            // Cone clamp around world up.
            if (Vector3.Angle(Vector3.up, up) > maxTiltDeg)
                up = Vector3.RotateTowards(Vector3.up, up, maxTiltDeg * Mathf.Deg2Rad, 0f);

            // Shortest arc from world up: its rotation axis is horizontal, so it has no yaw.
            return Quaternion.FromToRotation(Vector3.up, up) * Quaternion.LookRotation(forward, Vector3.up);
        }

        /// <summary>Elevation (degrees) of a point seen from the pivot, in the vertical plane along forward,
        /// measured on the handle side (-forward). The rest handle sits at a small positive elevation.</summary>
        public static float Elevation(Vector3 pivot, Vector3 forward, Vector3 point)
        {
            var rel = point - pivot;
            return Mathf.Atan2(rel.y, -Vector3.Dot(rel, forward)) * Mathf.Rad2Deg;
        }

        /// <summary>Signed twist (degrees) of a rotation around an axis (swing-twist decomposition).</summary>
        public static float TwistAngle(Quaternion q, Vector3 axis)
        {
            if (q.w < 0f) { q.x = -q.x; q.y = -q.y; q.z = -q.z; q.w = -q.w; }
            var proj = Vector3.Dot(new Vector3(q.x, q.y, q.z), axis.normalized);
            return 2f * Mathf.Atan2(proj, q.w) * Mathf.Rad2Deg;
        }

        /// <summary>Pitch (+ = up tilted toward forward) and roll (+ = up tilted toward -right) of an up-vector.</summary>
        public static void TiltAngles(Vector3 up, Vector3 forward, out float pitch, out float roll)
        {
            var right = Vector3.Cross(Vector3.up, forward);
            pitch = Mathf.Atan2(Vector3.Dot(up, forward), up.y) * Mathf.Rad2Deg;
            roll = Mathf.Atan2(-Vector3.Dot(up, right), up.y) * Mathf.Rad2Deg;
        }
    }
}
