// LabyrinthGoal.cs - on GoalTrigger (child of LabyrinthPivot). When the ball drops into the goal
// hole it logs "GOAL" and, after resetDelay, puts the ball back at its start. It also resets the
// ball when it falls off (world y below fallY). The board's tilt is left as it is.
// The start is stored as the ball's collider centre in LabyrinthPivot-local space, so the reset
// lands on the plate even when the board is tilted.
// Also sets the ball's Rigidbody.sleepThreshold to 0 (not serialized by Unity, so it is set here).

using System.Collections;
using UnityEngine;

namespace LabyrinthVR.Gameplay
{
    public class LabyrinthGoal : MonoBehaviour
    {
        public Rigidbody ball;
        public Transform board;                                             // LabyrinthPivot
        public Vector3 ballStartLocal = new Vector3(-0.304f, 0.0818f, -0.390f); // collider centre, board-local
        public float resetDelay = 2f;
        public float fallY = 0.5f;

        SphereCollider m_BallCollider;
        bool m_ResetPending;

        void Awake()
        {
            if (ball == null) return;
            ball.sleepThreshold = 0f;
            m_BallCollider = ball.GetComponent<SphereCollider>();
        }

        void OnTriggerEnter(Collider other)
        {
            if (ball == null || other.attachedRigidbody != ball || m_ResetPending) return;
            Debug.Log("GOAL");
            StartCoroutine(ResetAfterDelay());
        }

        void FixedUpdate()
        {
            // The ball falls through the goal hole too; that case is already waiting for its reset.
            if (ball != null && !m_ResetPending && ball.position.y < fallY)
                ResetBall();
        }

        IEnumerator ResetAfterDelay()
        {
            m_ResetPending = true;
            yield return new WaitForSeconds(resetDelay);
            ResetBall();
            m_ResetPending = false;
        }

        public void ResetBall()
        {
            var t = ball.transform;
            var toCentre = m_BallCollider != null ? t.TransformPoint(m_BallCollider.center) - t.position : Vector3.zero;
            var target = board.TransformPoint(ballStartLocal) - toCentre;
            ball.linearVelocity = Vector3.zero;
            ball.angularVelocity = Vector3.zero;
            ball.position = target;
            t.position = target;
            ball.WakeUp();
        }
    }
}
