using UnityEngine;

public class PropellerSpin : MonoBehaviour
{
    [Tooltip("Speed of the propeller in degrees per second. Positive for clockwise, negative for counter-clockwise.")]
    public float rotationSpeed = 3500f;

    void Update()
    {
        // Applies rotation around the local Y-axis (0f for X, rotationSpeed for Y, 0f for Z)
        // Multiplying by Time.deltaTime ensures the speed is consistent regardless of framerate
        transform.Rotate(0f, rotationSpeed * Time.deltaTime, 0f, Space.Self);
    }
}