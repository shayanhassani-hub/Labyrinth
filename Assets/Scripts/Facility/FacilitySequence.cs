// FacilitySequence.cs - the launch sequence state machine (Documentation/HERO_SPEC.md sections 1, 9, 10).
//
//   Arrival   scene start: the drone sits docked in the Cradle v2 (DroneHoverAIV2 and PropellerSpin off), the room's
//             teleport collider is off, the player stands at the corridor end facing the gate, the room is Standby.
//   GateOpen  the gate's SlideDriver starts opening (gate button) -> room teleport collider on.
//   Armed     TerminalController.onArmed (terminal button) -> AtmosphereController Armed (cyan -> orange) and
//             ServiceArmDriver.RequestFold() (fold starts after its foldDelay); ServiceArmDriver.onStowed -> LeverHandle.Arm().
//   Released  LeverHandle.onPulled -> TerminalController.Release(), both Cradle HingeDrivers Open(), atmosphere Released
//             (slow alarm pulse); droneEnableDelay later DroneHoverAIV2 + PropellerSpin are enabled: the drone takes off.
//   LeverHandle.onDenied (pull before Armed) -> onLeverDenied, the hook for a later sound cue.
//
// The heroes keep their own logic; this script only listens to their events (runtime listeners, added in OnEnable) and
// calls their public methods. References are set by FacilitySequenceBuilder (Tools > Labyrinth > Facility Sequence).
// Context menu "Debug/..." jumps forward through the states for Play Mode tests without a headset;
// "Debug/Skip To Released" runs the whole chain at once (arm snapped stowed) and puts the player at the labyrinth.

using System.Collections;
using UnityEngine;
using UnityEngine.Events;

namespace LabyrinthVR.Gameplay
{
    public enum FacilityState { Arrival, GateOpen, Armed, Released }

    [System.Serializable] public class FacilityStateEvent : UnityEvent<FacilityState> { }

    public class FacilitySequence : MonoBehaviour
    {
        [Header("Heroes (set by FacilitySequenceBuilder)")]
        public SlideDriver gate;
        public TerminalController terminal;
        public ServiceArmDriver serviceArm;
        public LeverHandle lever;
        public HingeDriver cradleArmL;
        public HingeDriver cradleArmR;
        public AtmosphereController atmosphere;

        [Header("Drone")]
        public Transform drone;
        public DroneHoverAIV2 droneHover;
        public PropellerSpin[] propellers = new PropellerSpin[0];
        [Tooltip("HERO_SPEC section 10: docked on the Cradle v2 pads.")]
        public Vector3 dockPosition = new Vector3(-0.032f, 2.000f, 4.754f);
        public float dockYaw = -28.3f;
        public bool applyDockPoseOnStart = true;

        [Header("Player")]
        public Transform xrOrigin;
        [Tooltip("HERO_SPEC section 1 / ENVIRONMENT_SPEC: corridor end, facing the gate (-Z).")]
        public Vector3 spawnPosition = new Vector3(-1f, 0f, 13f);
        public float spawnYaw = 180f;
        public bool applySpawnOnStart = true;
        [Tooltip("Labyrinth operating position, used by Debug/Skip To Released.")]
        public Vector3 playPosition = Vector3.zero;
        public float playYaw = 0f;

        [Header("Teleport")]
        [Tooltip("NAV_TeleportFloor's room BoxCollider: off until the gate opens. The corridor collider stays on.")]
        public Collider roomTeleportCollider;

        [Header("Timings (s)")]
        [Tooltip("Lever pull -> DroneHoverAIV2 + PropellerSpin enabled (HERO_SPEC section 1: t = +1.0 s).")]
        public float droneEnableDelay = 1.0f;

        [Header("Events")]
        public FacilityStateEvent onStateChanged = new FacilityStateEvent();
        [Tooltip("Lever pulled before Armed: hook for the 'denied' sound cue.")]
        public UnityEvent onLeverDenied = new UnityEvent();
        public UnityEvent onDroneLaunched = new UnityEvent();

        public bool logTransitions = true;

        [SerializeField] FacilityState m_State = FacilityState.Arrival;
        public FacilityState State => m_State;
        public bool DroneLaunched { get; private set; }

        float m_StartTime;

        void OnEnable()
        {
            if (gate != null) gate.onOpenStarted.AddListener(OnGateOpenStarted);
            if (terminal != null) terminal.onArmed.AddListener(OnTerminalArmed);
            if (serviceArm != null) serviceArm.onStowed.AddListener(OnArmStowed);
            if (lever != null) { lever.onPulled.AddListener(OnLeverPulled); lever.onDenied.AddListener(OnLeverDenied); }
        }

        void OnDisable()
        {
            if (gate != null) gate.onOpenStarted.RemoveListener(OnGateOpenStarted);
            if (terminal != null) terminal.onArmed.RemoveListener(OnTerminalArmed);
            if (serviceArm != null) serviceArm.onStowed.RemoveListener(OnArmStowed);
            if (lever != null) { lever.onPulled.RemoveListener(OnLeverPulled); lever.onDenied.RemoveListener(OnLeverDenied); }
        }

        void Start()
        {
            m_StartTime = Time.time;
            EnterArrival();
        }

        // ---------------------------------------------------------------- states

        void EnterArrival()
        {
            m_State = FacilityState.Arrival;
            SetDroneActive(false);
            if (applyDockPoseOnStart && drone != null)
                drone.SetPositionAndRotation(dockPosition, Quaternion.Euler(0f, dockYaw, 0f));
            if (applySpawnOnStart) PlacePlayer(spawnPosition, spawnYaw);
            if (roomTeleportCollider != null) roomTeleportCollider.enabled = false;
            if (atmosphere != null) atmosphere.SetStandby();
            Log("Arrival");
            onStateChanged.Invoke(m_State);
        }

        void OnGateOpenStarted()
        {
            if (roomTeleportCollider != null) roomTeleportCollider.enabled = true;
            if (m_State != FacilityState.Arrival) return;
            m_State = FacilityState.GateOpen;
            Log("GateOpen (room teleport on)");
            onStateChanged.Invoke(m_State);
        }

        void OnTerminalArmed()
        {
            if (m_State == FacilityState.Armed || m_State == FacilityState.Released) return;
            if (roomTeleportCollider != null) roomTeleportCollider.enabled = true;
            m_State = FacilityState.Armed;
            if (atmosphere != null) atmosphere.SetArmed();
            if (serviceArm != null) serviceArm.RequestFold();
            Log("Armed (atmosphere -> orange, service arm fold requested)");
            onStateChanged.Invoke(m_State);
        }

        void OnArmStowed()
        {
            if (m_State != FacilityState.Armed) return;
            if (lever != null) lever.Arm();
            Log("ServiceArm stowed -> lever armed");
        }

        void OnLeverPulled()
        {
            if (m_State == FacilityState.Released) return;
            m_State = FacilityState.Released;
            if (terminal != null) terminal.Release();
            if (cradleArmL != null) cradleArmL.Open();
            if (cradleArmR != null) cradleArmR.Open();
            if (atmosphere != null) atmosphere.SetReleased();
            Log("Released (cradle opening, alarm pulse)");
            onStateChanged.Invoke(m_State);
            StartCoroutine(LaunchDrone());
        }

        void OnLeverDenied()
        {
            Log("lever denied");
            onLeverDenied.Invoke();
        }

        IEnumerator LaunchDrone()
        {
            if (droneEnableDelay > 0f) yield return new WaitForSeconds(droneEnableDelay);
            SetDroneActive(true);
            DroneLaunched = true;
            Log("drone launched (DroneHoverAIV2 + PropellerSpin on)");
            onDroneLaunched.Invoke();
        }

        // ---------------------------------------------------------------- helpers

        void SetDroneActive(bool on)
        {
            if (droneHover != null) droneHover.enabled = on;
            if (propellers != null)
                foreach (var p in propellers) if (p != null) p.enabled = on;
        }

        void PlacePlayer(Vector3 position, float yaw)
        {
            if (xrOrigin == null) return;
            xrOrigin.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f));
        }

        void Log(string what)
        {
            if (logTransitions) Debug.Log($"[FacilitySequence] t={Time.time - m_StartTime:0.000} s  {what}");
        }

        // ---------------------------------------------------------------- debug jumps (Play Mode)

        [ContextMenu("Debug/1 Open Gate")]
        public void DebugOpenGate() { if (gate != null) gate.Open(); }

        [ContextMenu("Debug/2 Arm (terminal button)")]
        public void DebugArm()
        {
            DebugOpenGate();
            if (terminal != null) terminal.Arm();
        }

        [ContextMenu("Debug/3 Stow Service Arm Now")]
        public void DebugStowArm()
        {
            if (m_State != FacilityState.Armed) DebugArm();
            if (serviceArm != null) serviceArm.SnapStowed();
        }

        [ContextMenu("Debug/4 Pull Lever")]
        public void DebugPullLever()
        {
            if (lever == null) return;
            if (lever.CurrentState == LeverHandle.State.Locked && m_State == FacilityState.Armed && serviceArm != null && serviceArm.IsStowed)
                lever.Arm();
            lever.SimulatePull();
        }

        [ContextMenu("Debug/Skip To Released")]
        public void DebugSkipToReleased()
        {
            DebugStowArm();
            DebugPullLever();
            if (atmosphere != null) atmosphere.SnapReleased();
            PlacePlayer(playPosition, playYaw);
        }
    }
}
