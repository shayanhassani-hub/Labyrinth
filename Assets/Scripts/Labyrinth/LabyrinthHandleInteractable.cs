// LabyrinthHandleInteractable.cs - the Labyrinth v2 handle (Documentation/HERO_SPEC.md section 8).
// An XRSimpleInteractable with two changes, both for this handle only:
//   - GetAttachTransform returns grabPoint (the bar centre). The handle mesh's origin is the
//     panel pivot by design, so without this XRI draws the selection line to the board's centre.
//   - While selected, the selecting interactor's line/curve visuals are switched off; on release
//     they get back exactly the enabled state they had. Other interactors and interactions
//     (teleport ray etc.) are never touched.

using System.Collections.Generic;
using UnityEngine;
using UnityEngine.XR.Interaction.Toolkit;
using UnityEngine.XR.Interaction.Toolkit.Interactables;
using UnityEngine.XR.Interaction.Toolkit.Interactors;
using UnityEngine.XR.Interaction.Toolkit.Interactors.Visuals;

namespace LabyrinthVR.Gameplay
{
    public class LabyrinthHandleInteractable : XRSimpleInteractable
    {
        public Transform grabPoint;

        // Per selecting interactor: the visuals hidden and their enabled state before the grab.
        readonly Dictionary<IXRSelectInteractor, List<(Component component, bool wasEnabled)>> m_Hidden =
            new Dictionary<IXRSelectInteractor, List<(Component, bool)>>();

        public override Transform GetAttachTransform(IXRInteractor interactor) =>
            grabPoint != null ? grabPoint : base.GetAttachTransform(interactor);

        /// <summary>True while this handle has the given interactor's visuals switched off.</summary>
        public bool IsHidingVisualsOf(IXRSelectInteractor interactor) => m_Hidden.ContainsKey(interactor);

        protected override void OnSelectEntered(SelectEnterEventArgs args)
        {
            base.OnSelectEntered(args);
            HideVisuals(args.interactorObject);
        }

        protected override void OnSelectExited(SelectExitEventArgs args)
        {
            base.OnSelectExited(args);
            RestoreVisuals(args.interactorObject);
        }

        protected override void OnDisable()
        {
            base.OnDisable();
            foreach (var interactor in new List<IXRSelectInteractor>(m_Hidden.Keys))
                RestoreVisuals(interactor);
        }

        void HideVisuals(IXRSelectInteractor interactor)
        {
            if (interactor == null || m_Hidden.ContainsKey(interactor)) return;
            var hidden = new List<(Component, bool)>();
            // Visual behaviours first: their OnDisable also hides their LineRenderer.
            foreach (var c in interactor.transform.GetComponentsInChildren<Behaviour>(true))
                if ((c is XRInteractorLineVisual || c is CurveVisualController) && Owns(interactor, c))
                {
                    hidden.Add((c, c.enabled));
                    c.enabled = false;
                }
            foreach (var lr in interactor.transform.GetComponentsInChildren<LineRenderer>(true))
                if (Owns(interactor, lr))
                {
                    hidden.Add((lr, lr.enabled));
                    lr.enabled = false;
                }
            m_Hidden[interactor] = hidden;
        }

        void RestoreVisuals(IXRSelectInteractor interactor)
        {
            if (interactor == null || !m_Hidden.TryGetValue(interactor, out var hidden)) return;
            m_Hidden.Remove(interactor);
            // Reverse order: LineRenderers back first, then the behaviours that drive them.
            for (var i = hidden.Count - 1; i >= 0; i--)
            {
                var (c, wasEnabled) = hidden[i];
                if (c is Behaviour b) b.enabled = wasEnabled;
                else if (c is Renderer r) r.enabled = wasEnabled;
            }
        }

        // Only visuals whose nearest interactor up the hierarchy is this interactor.
        static bool Owns(IXRSelectInteractor interactor, Component c) =>
            ReferenceEquals(c.GetComponentInParent<IXRInteractor>(true), interactor);
    }
}
