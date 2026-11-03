// ServiceArmDriver.cs - drives the ceiling service arm (Documentation/HERO_SPEC.md section 4; build notes in
// Documentation/Heroes/ServiceArm_BUILD.md). Rigid hinges, no animation clips: every joint is a localRotation.
//
// Hierarchy (built by ServiceArmBuilder): Mount > Turret (yaw, Y) > UpperArm (pitch, X) > Forearm (pitch, X)
// > Wrist (pitch, X) > ToolHead (roll, Z). All angles 0 = the stowed pose (links flat against the ceiling, +Z).
//
// States:
//   Working (Standby, HERO_SPEC section 1 state 0): the working pose plus a procedural idle - turret +-10 deg,
//     wrist +-15 deg, each the sum of two slow sines with unrelated frequencies (0.2-0.5 Hz) and random phases, so
//     the motion never visibly repeats; the tool spins about its axis at a slowly varying speed.
//   Folding: from wherever the idle left the joints to the stowed pose in foldDuration (2.0 s), smoothstep
//     ease-in-out per joint; the tool roll unwinds the short way. Idle stops when the fold starts.
//   Stowed.
// Hook for FacilitySequence (HERO_SPEC section 1 state 2, section 10): call RequestFold() when the terminal button
// is pressed - the fold starts foldDelay (2.5 s) later; or call BeginFold() to start at once. onStowed fires when
// the arm is flat; FacilitySequence arms the lever from it (the lever must stay locked until then).
// The clearance of every pose this script can produce (working pose, idle extremes, the fold from any idle state,
// stowed) against the docked drone is checked offline by Tools/Blender/heroes/servicearm_check.py -- clearance.
// If you change the working pose or the idle amplitudes, re-run that sweep.

using UnityEngine;
using UnityEngine.Events;

namespace LabyrinthVR.Gameplay
{
    public class ServiceArmDriver : MonoBehaviour
    {
        public enum ArmState { Working, Folding, Stowed }

        [Header("Joints (set by ServiceArmBuilder)")]
        public Transform turret;
        public Transform upperArm;
        public Transform forearm;
        public Transform wrist;
        public Transform toolHead;

        [Header("Working pose (deg; HERO_SPEC 4, IK in servicearm_kin.py)")]
        [Tooltip("Turret yaw: brings the +X elbow/wrist offsets (0.22 m) onto the drone's centre line.")]
        public float workTurretYaw = 21.14f;
        public float workShoulder = 78.61f;
        public float workElbow = -110.22f;
        [Tooltip("Keeps the tool vertical; tip 0.05 above the drone's top (y 2.04).")]
        public float workWrist = -58.39f;

        [Header("Stowed pose (deg)")]
        public float stowTurretYaw = 0f;
        public float stowShoulder = 0f;
        public float stowElbow = 0f;
        public float stowWrist = 0f;
        public float stowRoll = 0f;

        [Header("Idle (Standby)")]
        [Tooltip("Turret yaw amplitude (deg). The clearance sweep covers +-10.")]
        public float idleTurretAmplitude = 10f;
        [Tooltip("Wrist pitch amplitude (deg). The clearance sweep covers +-15.")]
        public float idleWristAmplitude = 15f;
        [Tooltip("Two frequencies (Hz) per joint, summed 60/40; keep them unrelated and within 0.2-0.5 Hz.")]
        public Vector2 turretFrequencies = new Vector2(0.21f, 0.34f);
        public Vector2 wristFrequencies = new Vector2(0.27f, 0.43f);
        [Tooltip("Mean tool spin (deg/s) and how much it varies (0..1), varied by a slow sine.")]
        public float toolRollSpeed = 90f;
        [Range(0f, 1f)] public float toolRollVariation = 0.35f;
        public float toolRollFrequency = 0.23f;
        [Tooltip("Seconds over which the idle fades in after start (no jump from the prefab pose).")]
        public float idleFadeIn = 1.5f;

        [Header("Fold (HERO_SPEC 1 / 4)")]
        [Tooltip("Delay between RequestFold() (the terminal button) and the fold start.")]
        public float foldDelay = 2.5f;
        public float foldDuration = 2.0f;
        public bool startStowed;

        public UnityEvent onFoldStarted = new UnityEvent();
        public UnityEvent onStowed = new UnityEvent();

        public ArmState State => m_State;
        public bool IsStowed => m_State == ArmState.Stowed;

        ArmState m_State;
        float m_IdleTime, m_Roll, m_FoldT, m_DelayLeft = -1f;
        Vector2 m_TurretPhase, m_WristPhase;
        float m_RollPhase;
        float[] m_FoldFrom = new float[5];

        void Awake()
        {
            m_TurretPhase = new Vector2(Random.value, Random.value) * 2f * Mathf.PI;
            m_WristPhase = new Vector2(Random.value, Random.value) * 2f * Mathf.PI;
            m_RollPhase = Random.value * 2f * Mathf.PI;
            m_State = startStowed ? ArmState.Stowed : ArmState.Working;
            if (startStowed) Apply(stowTurretYaw, stowShoulder, stowElbow, stowWrist, stowRoll);
            else Apply(workTurretYaw, workShoulder, workElbow, workWrist, 0f);
        }

        /// <summary>Terminal button pressed: fold after foldDelay seconds (HERO_SPEC 1, state Armed).</summary>
        public void RequestFold()
        {
            if (m_State != ArmState.Working || m_DelayLeft >= 0f) return;
            m_DelayLeft = foldDelay;
        }

        /// <summary>Start the fold now, from the current (idle) joint angles.</summary>
        public void BeginFold()
        {
            if (m_State != ArmState.Working) return;
            m_DelayLeft = -1f;
            m_FoldFrom[0] = Yaw(turret);
            m_FoldFrom[1] = Pitch(upperArm);
            m_FoldFrom[2] = Pitch(forearm);
            m_FoldFrom[3] = Pitch(wrist);
            // roll: unwind the short way to the stowed roll
            m_FoldFrom[4] = stowRoll + Mathf.DeltaAngle(stowRoll, m_Roll);
            m_FoldT = 0f;
            m_State = ArmState.Folding;
            onFoldStarted.Invoke();
        }

        /// <summary>Editor / test helper: jump back to the working pose and restart the idle.</summary>
        [ContextMenu("Reset To Working")]
        public void ResetToWorking()
        {
            m_State = ArmState.Working; m_DelayLeft = -1f; m_IdleTime = 0f; m_Roll = 0f;
            Apply(workTurretYaw, workShoulder, workElbow, workWrist, 0f);
        }

        [ContextMenu("Fold Now")]
        void FoldNowMenu() => BeginFold();

        void Update()
        {
            float dt = Time.deltaTime;
            if (m_State == ArmState.Working)
            {
                if (m_DelayLeft >= 0f)
                {
                    m_DelayLeft -= dt;
                    if (m_DelayLeft <= 0f) { BeginFold(); Fold(0f); return; }
                }
                Idle(dt);
            }
            else if (m_State == ArmState.Folding)
            {
                Fold(dt);
            }
        }

        void Idle(float dt)
        {
            m_IdleTime += dt;
            float fade = idleFadeIn > 0f ? Mathf.SmoothStep(0f, 1f, m_IdleTime / idleFadeIn) : 1f;
            float t = m_IdleTime;
            float yaw = idleTurretAmplitude * fade * Wave(t, turretFrequencies, m_TurretPhase);
            float wr = idleWristAmplitude * fade * Wave(t, wristFrequencies, m_WristPhase);
            float speed = toolRollSpeed * (1f + toolRollVariation * Mathf.Sin(2f * Mathf.PI * toolRollFrequency * t + m_RollPhase));
            m_Roll = Mathf.Repeat(m_Roll + speed * fade * dt, 360f);
            Apply(workTurretYaw + yaw, workShoulder, workElbow, workWrist + wr, m_Roll);
        }

        static float Wave(float t, Vector2 f, Vector2 phase)
        {
            // 0.6 + 0.4 = 1: never exceeds the amplitude the clearance sweep covers
            return 0.6f * Mathf.Sin(2f * Mathf.PI * f.x * t + phase.x) + 0.4f * Mathf.Sin(2f * Mathf.PI * f.y * t + phase.y);
        }

        void Fold(float dt)
        {
            m_FoldT = foldDuration > 0f ? Mathf.Min(1f, m_FoldT + dt / foldDuration) : 1f;
            float e = Mathf.SmoothStep(0f, 1f, m_FoldT);
            Apply(Mathf.Lerp(m_FoldFrom[0], stowTurretYaw, e), Mathf.Lerp(m_FoldFrom[1], stowShoulder, e),
                  Mathf.Lerp(m_FoldFrom[2], stowElbow, e), Mathf.Lerp(m_FoldFrom[3], stowWrist, e),
                  Mathf.Lerp(m_FoldFrom[4], stowRoll, e));
            if (m_FoldT >= 1f)
            {
                m_State = ArmState.Stowed;
                onStowed.Invoke();
            }
        }

        void Apply(float yaw, float shoulder, float elbow, float wristPitch, float roll)
        {
            if (turret) turret.localRotation = Quaternion.Euler(0f, yaw, 0f);
            if (upperArm) upperArm.localRotation = Quaternion.Euler(shoulder, 0f, 0f);
            if (forearm) forearm.localRotation = Quaternion.Euler(elbow, 0f, 0f);
            if (wrist) wrist.localRotation = Quaternion.Euler(wristPitch, 0f, 0f);
            if (toolHead) toolHead.localRotation = Quaternion.Euler(0f, 0f, roll);
        }

        // signed joint angles read back from the transforms (single-axis rotations)
        static float Yaw(Transform t) => t ? Mathf.DeltaAngle(0f, t.localEulerAngles.y) : 0f;

        static float Pitch(Transform t)
        {
            if (!t) return 0f;
            // single-axis X rotation: angle from the rotated forward vector (localEulerAngles.x is ambiguous past 90)
            Vector3 f = t.localRotation * Vector3.forward;
            return Mathf.Atan2(-f.y, f.z) * Mathf.Rad2Deg;
        }
    }
}
