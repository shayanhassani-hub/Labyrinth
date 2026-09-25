// LabyrinthTiltTests.cs - EditMode tests for LabyrinthTilt.ComputeTargetRotation (the pan model),
// driven with synthetic hand poses; no XR or scene needed. Numbers match BasicScene: pivot
// (0.025, 1.00, 1.225), handle collider centre at pivot-local (0, 0.065, -0.5738), board forward +Z.

using LabyrinthVR.Gameplay;
using NUnit.Framework;
using UnityEngine;

namespace LabyrinthVR.Tests
{
    public class LabyrinthTiltTests
    {
        const float MaxTilt = 12f;
        const float Eps = 1e-3f;
        static readonly Vector3 Pivot = new Vector3(0.025f, 1.00f, 1.225f);
        static readonly Vector3 Forward = Vector3.forward;
        static readonly Vector3 HandAtHandle = Pivot + new Vector3(0f, 0.065f, -0.5738f);

        static LabyrinthTilt.GrabState LevelGrab(Quaternion handRotation) =>
            LabyrinthTilt.CreateGrabState(Quaternion.identity, Forward, HandAtHandle, handRotation);

        static Quaternion Solve(Vector3 handPos, Quaternion handRot, Quaternion grabHandRot) =>
            LabyrinthTilt.ComputeTargetRotation(Pivot, Forward, LevelGrab(grabHandRot), handPos, handRot, MaxTilt);

        static Quaternion Solve(Vector3 handPos, Quaternion handRot) => Solve(handPos, handRot, Quaternion.identity);

        static float Tilt(Quaternion q) => Vector3.Angle(Vector3.up, q * Vector3.up);

        // Height of a board-local point after rotation, relative to the pivot.
        static float EdgeY(Quaternion q, Vector3 local) => (q * local).y;

        [Test]
        public void NoHandMovement_IsLevel()
        {
            var q = Solve(HandAtHandle, Quaternion.identity);
            Assert.Less(Tilt(q), Eps, "tilt");
        }

        [Test]
        public void HandLifted10cm_FarEdgeDips_WithinLimit()
        {
            var q = Solve(HandAtHandle + new Vector3(0f, 0.10f, 0f), Quaternion.identity);
            var far = EdgeY(q, new Vector3(0f, 0f, 0.525f));
            var near = EdgeY(q, new Vector3(0f, 0f, -0.525f));
            Assert.Less(far, near, "far edge (+Z) should be lower than near edge");
            Assert.Greater(Tilt(q), 1f, "board should tilt");
            Assert.LessOrEqual(Tilt(q), MaxTilt + Eps, "tilt within limit");
            Assert.Less(Mathf.Abs(EdgeY(q, new Vector3(0.525f, 0f, 0f))), Eps, "no sideways tilt");
        }

        [Test]
        public void WristTwistPlus20_RollsSameWay()
        {
            // Hand twisted +20 deg around +Z: the board rolls +Z too (clamped to 12): +X edge rises.
            var twist = Quaternion.AngleAxis(20f, Forward);
            var q = Solve(HandAtHandle, twist);
            var plusX = EdgeY(q, new Vector3(0.525f, 0f, 0f));
            var minusX = EdgeY(q, new Vector3(-0.525f, 0f, 0f));
            Assert.Greater(plusX, minusX, "+X edge should rise for a +20 deg twist around +Z");
            Assert.AreEqual(MaxTilt, Tilt(q), Eps, "20 deg clamps to 12");
            Assert.Less(Mathf.Abs(EdgeY(q, new Vector3(0f, 0f, 0.525f))), Eps, "no forward tilt");

            // Small twist is followed 1:1.
            var q5 = Solve(HandAtHandle, Quaternion.AngleAxis(5f, Forward));
            Assert.AreEqual(5f, Tilt(q5), Eps, "5 deg twist -> 5 deg roll");

            // Twist is measured relative to the grab: grabbing with a rotated hand changes nothing.
            var grabRot = Quaternion.Euler(30f, -40f, 10f);
            Assert.Less(Tilt(Solve(HandAtHandle, grabRot, grabRot)), Eps, "rotated grab, no motion -> level");
        }

        [Test]
        public void SidewaysHandMove_NoTilt()
        {
            var q = Solve(HandAtHandle + new Vector3(0.3f, 0f, 0f), Quaternion.identity);
            Assert.Less(Tilt(q), Eps, "tilt");
            var q2 = Solve(HandAtHandle + new Vector3(-0.3f, 0f, 0f), Quaternion.identity);
            Assert.Less(Tilt(q2), Eps, "tilt (other side)");
        }

        [Test]
        public void ExtremeMotion_ClampsAtExactlyMaxTilt_EveryDirection()
        {
            var lifts = new[] { 2f, -2f, 0f };
            var twists = new[] { 80f, -80f, 0f };
            foreach (var lift in lifts)
            foreach (var twist in twists)
            {
                if (lift == 0f && twist == 0f) continue;
                var q = Solve(HandAtHandle + new Vector3(0f, lift, 0f), Quaternion.AngleAxis(twist, Forward));
                Assert.AreEqual(MaxTilt, Tilt(q), Eps, $"lift {lift}, twist {twist}");
            }
            // Diagonal direction is kept: 20 deg pitch + 20 deg roll demand -> clamped on the 45 deg azimuth.
            var rest = LabyrinthTilt.Elevation(Pivot, Forward, HandAtHandle);
            var lift20 = 0.5738f * Mathf.Tan((rest + 20f) * Mathf.Deg2Rad) - 0.065f;
            var qd = Solve(HandAtHandle + new Vector3(0f, lift20, 0f), Quaternion.AngleAxis(20f, Forward));
            var d = qd * Vector3.up;
            Assert.AreEqual(MaxTilt, Tilt(qd), Eps, "diagonal clamp");
            Assert.AreEqual(-d.x, d.z, Eps, "diagonal azimuth (up toward -X and +Z equally)");
        }

        [Test]
        public void EveryResult_HasZeroYaw()
        {
            var worstForwardX = 0f;
            for (var lift = -0.5f; lift <= 0.5f; lift += 0.05f)
            for (var twist = -60f; twist <= 60f; twist += 10f)
            for (var side = -0.3f; side <= 0.3f; side += 0.3f)
            {
                var handRot = Quaternion.AngleAxis(twist, Forward) * Quaternion.Euler(15f, 25f, 0f);
                var q = Solve(HandAtHandle + new Vector3(side, lift, 0f), handRot, Quaternion.Euler(15f, 25f, 0f));
                // Yaw = twist of the rotation around world up (swing-twist); zero for a shortest arc from up.
                Assert.AreEqual(0f, LabyrinthTilt.TwistAngle(q, Vector3.up), Eps, $"yaw at lift {lift}, twist {twist}");
                // Forward stays in the vertical plane of +Z exactly for pure pitch or pure roll.
                var f = q * Vector3.forward;
                if (Mathf.Abs(twist) < 0.01f || Mathf.Abs(lift) < 0.01f)
                    Assert.AreEqual(0f, f.x, Eps, $"forward.x at lift {lift}, twist {twist}");
                worstForwardX = Mathf.Max(worstForwardX, Mathf.Abs(f.x));
            }
            // Diagonal tilts: the shortest arc moves forward.x by at most (1 - cos 12)/2 = 0.011.
            Assert.LessOrEqual(worstForwardX, (1f - Mathf.Cos(MaxTilt * Mathf.Deg2Rad)) / 2f + Eps, "diagonal forward.x");
        }

        [Test]
        public void GrabOnTiltedBoard_KeepsTilt()
        {
            var tilted = Quaternion.FromToRotation(Vector3.up, Quaternion.Euler(6f, 0f, -4f) * Vector3.up);
            var grab = LabyrinthTilt.CreateGrabState(tilted, Forward, HandAtHandle, Quaternion.identity);
            var q = LabyrinthTilt.ComputeTargetRotation(Pivot, Forward, grab, HandAtHandle, Quaternion.identity, MaxTilt);
            Assert.Less(Quaternion.Angle(q, tilted), Eps, "no jump on grab");
        }
    }
}
