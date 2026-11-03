// GateButton.cs - the facility gate's push button (Documentation/HERO_SPEC.md sections 1 and 7).
// The player presses it (XRI select on the button's XRSimpleInteractable: ray / near-far, or poke once
// the rig has a poke interactor); the cap travels -X by 8 mm, fires onPressed at the bottom of the
// stroke and springs back. GateBuilder wires onPressed -> the leaf's SlideDriver.Open.
// FacilitySequence (not written yet) can listen to onPressed as well; HERO_SPEC section 1, state 1:
// "player presses the gate button -> gate leaf slides open (2.0 s), room teleport area enabled".
// A press while the cap is still moving is ignored. Use the component's context menu "Press" to test
// in Play Mode without a headset.

using System.Collections;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.XR.Interaction.Toolkit;
using UnityEngine.XR.Interaction.Toolkit.Interactables;

namespace LabyrinthVR.Gameplay
{
    public class GateButton : MonoBehaviour
    {
        [Tooltip("XRSimpleInteractable on the button; its select starts a press.")]
        public XRSimpleInteractable interactable;
        [Tooltip("The moving cap; defaults to this transform.")]
        public Transform cap;
        [Tooltip("Press travel in the cap's parent space (metres). HERO_SPEC section 7: -X 0.008.")]
        public Vector3 pressOffset = new Vector3(-0.008f, 0f, 0f);
        public float pressTime = 0.08f;
        public float holdTime = 0.10f;
        public float releaseTime = 0.15f;

        public UnityEvent onPressed = new UnityEvent();

        public bool IsPressing => m_Pressing;

        Vector3 m_Rest;
        bool m_Pressing;

        void Awake()
        {
            if (cap == null) cap = transform;
            m_Rest = cap.localPosition;
        }

        void OnEnable()
        {
            if (interactable != null) interactable.selectEntered.AddListener(OnSelectEntered);
        }

        void OnDisable()
        {
            if (interactable != null) interactable.selectEntered.RemoveListener(OnSelectEntered);
            if (m_Pressing) { StopAllCoroutines(); cap.localPosition = m_Rest; m_Pressing = false; }
        }

        void OnSelectEntered(SelectEnterEventArgs args) => Press();

        [ContextMenu("Press")]
        public void Press()
        {
            if (m_Pressing || !isActiveAndEnabled) return;
            StartCoroutine(PressRoutine());
        }

        IEnumerator PressRoutine()
        {
            m_Pressing = true;
            yield return Move(0f, 1f, pressTime);
            onPressed.Invoke();
            if (holdTime > 0f) yield return new WaitForSeconds(holdTime);
            yield return Move(1f, 0f, releaseTime);
            m_Pressing = false;
        }

        IEnumerator Move(float from, float to, float time)
        {
            for (var t = 0f; t < time; t += Time.deltaTime)
            {
                cap.localPosition = m_Rest + pressOffset * Mathf.SmoothStep(from, to, t / time);
                yield return null;
            }
            cap.localPosition = m_Rest + pressOffset * to;
        }
    }
}
