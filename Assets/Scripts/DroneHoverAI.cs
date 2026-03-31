using System.Runtime.CompilerServices;
using UnityEngine;
using UnityEngine.InputSystem;

public class DroneHoverAI : MonoBehaviour
{
    public BoxCollider bounds; // Assign the DroneBounds BoxCollider in the Inspector
    private Vector3 targetPoint; // current destination
    public float moveSpeed = 2f; // units per second
    public float reachThreshold = 0.1f; // how close before picking a new point
    public float hoverAmplitude = 0.3f;
    public float hoverFrequency = 2f;

    // Function: pick a random point inside the BoxCollider bounds
    private Vector3 GetRandomPointInBounds()
    {
        // Take the BoxCollider’s world center and size
        // Vector3 center = bounds.center + bounds.transform.position;
        // Vector3 size = bounds.size;
        Vector3 center = bounds.transform.TransformPoint(bounds.center);
        Vector3 size = bounds.bounds.size; // world-space size

        // Generate random offsets for x, y, z within half the size of the box
        float randomX = Random.Range(-size.x / 2f, size.x / 2f);
        float randomY = Random.Range(-size.y / 2f, size.y / 2f);
        float randomZ = Random.Range(-size.z / 2f, size.z / 2f);

        // Return the random point in world space
        return center + new Vector3(randomX, randomY, randomZ);
    }

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        targetPoint = GetRandomPointInBounds(); // Pick initial random point
    }

    // Update is called once per frame
    void Update()
    {
        // Test: Draw a red sphere at a random point when pressing space
        //if (Input.GetKeyDown(KeyCode.Space))
        if (Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            Vector3 randomPoint = GetRandomPointInBounds();
            Debug.DrawLine(transform.position, randomPoint, Color.red, 2f);
            Debug.Log("Random Point: " + randomPoint);
        }

        // Move drone toward targetPoint
        Vector3 baseMove = Vector3.Lerp(transform.position, targetPoint, moveSpeed * Time.deltaTime);
        float hoverOffset = Mathf.Sin(Time.time * hoverFrequency) * hoverAmplitude;
        transform.position = baseMove + new Vector3(0, hoverOffset, 0);

        // Check if reached
        // if (Vector3.Distance(transform.position, targetPoint) < reachThreshold)
        if ((transform.position - targetPoint).sqrMagnitude < reachThreshold * reachThreshold)
        {
            targetPoint = GetRandomPointInBounds();
        }

        // Optional: debug
        Debug.DrawLine(transform.position, targetPoint, Color.green);
    }

    void OnDrawGizmos()
    {
        if (bounds != null)
        {
            Gizmos.color = Color.cyan;
            Gizmos.DrawWireCube(bounds.bounds.center, bounds.bounds.size);
        }
    }
}
