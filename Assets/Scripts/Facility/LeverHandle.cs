// LeverHandle.cs - the launch lever on the lever stand (Documentation/HERO_SPEC.md sections 1, 6 and 10).
//
// The player grabs the ochre grip (XRSimpleInteractable on the grip collider: direct / near-far select) and
// the lever follows the hand AROUND ITS HINGE ONLY: the hand position is projected into the hinge's YZ
// plane and only the hinge angle (local Euler X of `hinge`) changes - no free grab, the lever never leaves
// its slot. The angle is applied relative to the grab, so grabbing does not make the lever jump.
//
// Angles are the hinge's local Euler X in the stand's frame (HERO_SPEC section 6; stand yaw 180, so local +Z
// faces the player): rest -30 (leans away from the player), pulled +30 (toward the player). The pull
// triggers at 80 % of the travel (+18 deg).
//
// States (HERO_SPEC section 1):
//   Locked  (before Armed)  a grab only lets the lever give a few degrees, fires onDenied once per grab
//                           (the "denied" cue) and springs back on release.
//   Armed   (Arm(), called by FacilitySequence once the service arm is stowed): the lever follows the hand;
//                           released before the trigger it springs back to rest. LeverLamp pulses amber.
//   Pulled  at 80 % of the travel: onPulled fires once (FacilitySequence -> Released), the lever runs to the
//           full pulled pose and latches there; grabs are ignored. The lamp switches to `lampAfterPull`.
// Context menus "Arm", "Simulate Pull" and "Reset" test it in Play Mode without a headset.

using UnityEngine;
using UnityEngine.Events;
using UnityEngine.XR.Interaction.Toolkit;
using UnityEngine.XR.Interaction.Toolkit.Interactables;

namespace LabyrinthVR.Gameplay
{
    public class LeverHandle : MonoBehaviour
    {
        public enum State { Locked, Armed, Pulled }

        [Tooltip("XRSimpleInteractable on the grip (its collider is on the lever, so it moves with it).")]
        public XRSimpleInteractable interactable;
        [Tooltip("The lever part; its origin is on the hinge, it rotates about its local X. Defaults to this transform.")]
        public Transform hinge;
        [Tooltip("Optional amber lamp on the housing.")]
        public LeverLamp lamp;

        [Header("Travel (hinge local Euler X, degrees; HERO_SPEC section 6)")]
        public float restAngle = -30f;
        public float pulledAngle = 30f;
        [Range(0.1f, 1f)] public float triggerFraction = 0.8f;

        [Header("Feel")]
        [Tooltip("Max hinge speed while following the hand (deg/s): smooths tracking jitter.")]
        public float followSpeed = 540f;
        [Tooltip("Spring-back speed after an early release or a denied pull (deg/s).")]
        public float returnSpeed = 180f;
        [Tooltip("After the trigger the lever runs to the pulled pose at this speed (deg/s).")]
        public float latchSpeed = 240f;
        [Tooltip("Locked: how far the lever gives toward 'pulled' before it stops (deg).")]
        public float deniedPlay = 3f;

        [Header("Lamp")]
        public LeverLamp.Mode lampAfterPull = LeverLamp.Mode.Steady;

        [Header("Events")]
        public UnityEvent onPulled = new UnityEvent();
        public UnityEvent onDenied = new UnityEvent();
        public UnityEvent onArmed = new UnityEvent();

        public State CurrentState => m_State;
        public float Angle => m_Angle;
        public float TriggerAngle => Mathf.Lerp(restAngle, pulledAngle, triggerFraction);
        /// 0 at rest, 1 fully pulled
        public float Travel => Mathf.InverseLerp(restAngle, pulledAngle, m_Angle);

        State m_State = State.Locked;
        float m_Angle;
        Transform m_Hand;                 // the selecting interactor's attach transform while grabbed
        float m_GrabHandAngle, m_GrabLeverAngle;
        bool m_DeniedThisGrab;

        void Awake()
        {
            if (hinge == null) hinge = transform;
            m_Angle = restAngle;
            Apply();
        }

        void OnEnable()
        {
            if (interactable == null) return;
            interactable.selectEntered.AddListener(OnSelectEntered);
            interactable.selectExited.AddListener(OnSelectExited);
        }

        void OnDisable()
        {
            if (interactable == null) return;
            interactable.selectEntered.RemoveListener(OnSelectEntered);
            interactable.selectExited.RemoveListener(OnSelectExited);
            m_Hand = null;
        }

        void OnSelectEntered(SelectEnterEventArgs args)
        {
            if (m_State == State.Pulled) return;
            m_Hand = args.interactorObject.GetAttachTransform(interactable);
            m_GrabHandAngle = HandAngle(m_Hand.position);
            m_GrabLeverAngle = m_Angle;
            m_DeniedThisGrab = false;
        }

        void OnSelectExited(SelectExitEventArgs args)
        {
            if (m_Hand == args.interactorObject.GetAttachTransform(interactable)) m_Hand = null;
        }

        /// angle of a world point about the hinge axis, in the hinge's parent space (0 = straight up, + toward local +Z)
        float HandAngle(Vector3 world)
        {
            var parent = hinge.parent;
            var p = parent != null ? parent.InverseTransformPoint(world) : world;
            var d = p - hinge.localPosition;
            return Mathf.Atan2(d.z, d.y) * Mathf.Rad2Deg;
        }

        void Update()
        {
            float target;
            switch (m_State)
            {
                case State.Pulled:
                    m_Angle = Mathf.MoveTowards(m_Angle, pulledAngle, latchSpeed * Time.deltaTime);
                    Apply();
                    return;
                case State.Locked:
                    if (m_Hand != null)
                    {
                        var want = m_GrabLeverAngle + Mathf.DeltaAngle(m_GrabHandAngle, HandAngle(m_Hand.position));
                        target = ClampTravel(want, restAngle, restAngle + Mathf.Sign(pulledAngle - restAngle) * deniedPlay);
                        if (!m_DeniedThisGrab && Mathf.Abs(want - restAngle) > deniedPlay)
                        {
                            m_DeniedThisGrab = true;
                            onDenied.Invoke();
                        }
                        m_Angle = Mathf.MoveTowards(m_Angle, target, followSpeed * Time.deltaTime);
                    }
                    else m_Angle = Mathf.MoveTowards(m_Angle, restAngle, returnSpeed * Time.deltaTime);
                    break;
                default:                                                     // Armed
                    if (m_Hand != null)
                    {
                        target = ClampTravel(m_GrabLeverAngle + Mathf.DeltaAngle(m_GrabHandAngle, HandAngle(m_Hand.position)),
                                             restAngle, pulledAngle);
                        m_Angle = Mathf.MoveTowards(m_Angle, target, followSpeed * Time.deltaTime);
                        if (Travel >= triggerFraction) { Trigger(); return; }
                    }
                    else m_Angle = Mathf.MoveTowards(m_Angle, restAngle, returnSpeed * Time.deltaTime);
                    break;
            }
            Apply();
        }

        static float ClampTravel(float a, float from, float to) => Mathf.Clamp(a, Mathf.Min(from, to), Mathf.Max(from, to));

        void Apply() => hinge.localRotation = Quaternion.Euler(m_Angle, 0f, 0f);

        void Trigger()
        {
            m_State = State.Pulled;
            m_Hand = null;
            if (lamp != null) lamp.SetMode(lampAfterPull);
            onPulled.Invoke();
        }

        /// FacilitySequence: the service arm is stowed, the launch may happen (HERO_SPEC section 1, state 2 end).
        [ContextMenu("Arm")]
        public void Arm()
        {
            if (m_State != State.Locked) return;
            m_State = State.Armed;
            if (lamp != null) lamp.SetMode(LeverLamp.Mode.Pulse);
            onArmed.Invoke();
        }

        [ContextMenu("Simulate Pull")]
        public void SimulatePull()
        {
            if (m_State == State.Locked) { onDenied.Invoke(); return; }
            if (m_State == State.Armed) { m_Angle = TriggerAngle; Trigger(); }
        }

        /// back to Locked at rest, lamp off (tests, or a future restart of the sequence)
        [ContextMenu("Reset")]
        public void ResetLever()
        {
            m_State = State.Locked;
            m_Hand = null;
            m_Angle = restAngle;
            if (lamp != null) lamp.SetMode(LeverLamp.Mode.Off);
            Apply();
        }
    }
}
