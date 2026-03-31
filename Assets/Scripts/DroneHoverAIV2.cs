using UnityEditor.Experimental.GraphView;
using UnityEngine;

public class DroneHoverAIV2 : MonoBehaviour
{
    [Header("Movement Bounds")]
    public BoxCollider bounds; // assign your DroneBounds BoxCollider in Inspector

    [Header("Target to Look At")]
    public GameObject labyrinthBall; // the labyrinth or ball the drone should look at

    [Header("Movement Settings")]
    public float moveSpeed = 1.5f;
    public float reachThreshold = 0.1f;

    [Header("Hover Settings")]
    public float hoverAmplitude = 0.3f; // how high/low the drone bobs
    public float hoverFrequency = 2f;   // how fast it bobs

    [Header("Rotation Settings")]
    public float rotationSpeed = 3f; // how smoothly the drone rotates toward target

    private Vector3 targetPoint;  // random destination inside the bounds
    private Vector3 basePosition; // drone’s base position without sine-wave offset

    // ----------- PICK RANDOM POINT IN BOUNDS -----------
    private Vector3 GetRandomPointInBounds()
    {
        Vector3 center = bounds.transform.TransformPoint(bounds.center);
        Vector3 size = bounds.bounds.size;

        float randomX = Random.Range(-size.x / 2f, size.x / 2f);
        float randomY = Random.Range(-size.y / 2f, size.y / 2f);
        float randomZ = Random.Range(-size.z / 2f, size.z / 2f);

        return center + new Vector3(randomX, randomY, randomZ);
    }

    // ----------- UNITY START -----------
    void Start()
    {
        targetPoint = GetRandomPointInBounds(); // initial random target
        basePosition = transform.position;      // remember starting base position
    }

    // ----------- UNITY UPDATE -----------
    void Update()
    {
        // ---- MOVEMENT (smooth drifting toward random point) ----
        basePosition = Vector3.Lerp(
            basePosition,
            targetPoint,
            moveSpeed * Time.deltaTime
        );

        // ---- HOVER BOB (sine-wave motion) ----
        float hoverOffset = Mathf.Sin(Time.time * hoverFrequency) * hoverAmplitude;
        Vector3 finalPosition = basePosition + new Vector3(0, hoverOffset, 0);

        transform.position = finalPosition;

        // ---- LOOK AT LABYRINTH ----
        if (labyrinthBall != null)
        {
            Vector3 lookDir = labyrinthBall.transform.position - transform.position;
            if (lookDir.sqrMagnitude > 0.001f) // avoid zero-length errors
            {
                Quaternion targetRot = Quaternion.LookRotation(lookDir);
                transform.rotation = Quaternion.Slerp(
                    transform.rotation,
                    targetRot,
                    rotationSpeed * Time.deltaTime
                );
            }
        }

        // ---- PICK NEW RANDOM TARGET ----
        if (Vector3.Distance(transform.position, targetPoint) < reachThreshold)
        {
            targetPoint = GetRandomPointInBounds();
        }

        // ---- DEBUG VISUALS ----
        Debug.DrawLine(transform.position, targetPoint, Color.green);
    }
}
