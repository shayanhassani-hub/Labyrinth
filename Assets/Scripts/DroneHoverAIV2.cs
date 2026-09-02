using UnityEngine;

public class DroneHoverAIV2 : MonoBehaviour
{
    // --------------------------------------------------------
    // [1] MOVEMENT & TARGETING VARIABLES
    // --------------------------------------------------------
    [Header("Movement Bounds")]
    [Tooltip("The invisible box that dictates where the drone is allowed to fly.")]
    public BoxCollider bounds;

    [Header("Target to Look At")]
    [Tooltip("The object the drone should always face (e.g., the player or the labyrinth).")]
    public GameObject labyrinthBall;

    [Header("Movement Settings")]
    public float moveSpeed = 1.5f;
    [Tooltip("How close the drone needs to get to its target point before picking a new one.")]
    public float reachThreshold = 0.1f;

    [Header("Hover Settings")]
    [Tooltip("How high and low the drone bobs up and down.")]
    public float hoverAmplitude = 0.3f;
    [Tooltip("How fast the drone bobs up and down.")]
    public float hoverFrequency = 2f;

    [Header("Rotation Settings")]
    [Tooltip("How quickly the drone rotates to face the target.")]
    public float rotationSpeed = 3f;

    // --------------------------------------------------------
    // [2] SHOOTING VARIABLES
    // --------------------------------------------------------
    [Header("Shooting Settings")]
    public GameObject projectilePrefab;
    [Tooltip("Assign the ToShoot_low transform here so the projectile spawns at the barrel tip.")]
    public Transform firePoint;
    public float shootInterval = 2f;
    public float projectileSpeed = 5f;

    // Internal timer to track when the drone is allowed to shoot next
    private float shootTimer = 0f;

    // --------------------------------------------------------
    // [3] VFX & OPTIMIZATION VARIABLES
    // --------------------------------------------------------
    [Header("VFX Settings")]
    [Tooltip("Any mesh renderer on the drone that uses the M_Drone material.")]
    public Renderer droneRenderer;
    public ParticleSystem ringSparks;
    [Tooltip("How bright the ring flashes when firing.")]
    public float peakEmissionIntensity = 5f;
    [Tooltip("How quickly the bright flash fades back to normal.")]
    public float flashDecaySpeed = 15f;

    // These variables allow us to change the material's emission without breaking 
    // the single-batch draw call optimization required for the Quest 3s.
    private MaterialPropertyBlock propBlock;
    private int emissionPropertyID;
    private float currentEmission = 0f;

    // Internal navigation tracking
    private Vector3 targetPoint;
    private Vector3 basePosition;

    // ========================================================
    // UNITY METHODS
    // ========================================================

    void Start()
    {
        // Pick the very first random destination inside our bounding box
        targetPoint = GetRandomPointInBounds();

        // Record where the drone is currently sitting in the world
        basePosition = transform.position;

        // Initialize the MaterialPropertyBlock. 
        // I use this instead of modifying the material directly so Unity doesn't 
        // accidentally create a duplicate material in memory, which would hurt VR performance.
        propBlock = new MaterialPropertyBlock();

        // Cache the exact string name of the Float property we made in our Shader Graph
        emissionPropertyID = Shader.PropertyToID("_Ring_Intensity");
    }

    void Update()
    {
        // --------------------------------------------------------
        // 1. HANDLE VFX (The Emissive Flash Decay)
        // --------------------------------------------------------
        // If the ring is currently glowing, slowly fade it back to 0 over time
        if (currentEmission > 0)
        {
            // Lerp smoothly interpolates between the current brightness and 0
            currentEmission = Mathf.Lerp(currentEmission, 0f, Time.deltaTime * flashDecaySpeed);

            // Apply the new, slightly dimmer brightness to the drone's material block
            if (droneRenderer != null)
            {
                droneRenderer.GetPropertyBlock(propBlock);
                propBlock.SetFloat(emissionPropertyID, currentEmission);
                droneRenderer.SetPropertyBlock(propBlock);
            }
        }

        // --------------------------------------------------------
        // 2. HANDLE MOVEMENT (Drifting to target)
        // --------------------------------------------------------
        // Move the drone's invisible "base" position smoothly toward the target point
        basePosition = Vector3.Lerp(
            basePosition,
            targetPoint,
            moveSpeed * Time.deltaTime
        );

        // Calculate the physical bobbing motion using a Sine wave (Mathf.Sin)
        // Time.time keeps it smoothly animating forever based on the game clock
        float hoverOffset = Mathf.Sin(Time.time * hoverFrequency) * hoverAmplitude;

        // Apply the physical bobbing offset to the base position
        Vector3 finalPosition = basePosition + new Vector3(0, hoverOffset, 0);
        transform.position = finalPosition;

        // --------------------------------------------------------
        // 3. HANDLE ROTATION (Looking at the target)
        // --------------------------------------------------------
        if (labyrinthBall != null)
        {
            // Find the direction from the drone to the target
            Vector3 lookDir = labyrinthBall.transform.position - transform.position;

            // Only rotate if the target isn't sitting inside the drone (prevents math errors)
            if (lookDir.sqrMagnitude > 0.001f)
            {
                // Calculate the rotation needed to look at the target
                Quaternion targetRot = Quaternion.LookRotation(lookDir);

                // If the front of your 3D model is modeled facing backward, 
                // this 180-degree flip fixes it. 
                targetRot *= Quaternion.Euler(0f, 180f, 0f);

                // Smoothly rotate the drone toward the target rotation
                transform.rotation = Quaternion.Slerp(
                    transform.rotation,
                    targetRot,
                    rotationSpeed * Time.deltaTime
                );
            }
        }

        // --------------------------------------------------------
        // 4. HANDLE NAVIGATION (Picking a new target)
        // --------------------------------------------------------
        // If the drone is close enough to its current destination, pick a new one
        if (Vector3.Distance(transform.position, targetPoint) < reachThreshold)
        {
            targetPoint = GetRandomPointInBounds();
        }

        // Draw a green line in the Scene view so we can see where the drone is trying to go
        Debug.DrawLine(transform.position, targetPoint, Color.green);

        // --------------------------------------------------------
        // 5. HANDLE SHOOTING TIMERS
        // --------------------------------------------------------
        // Advance the shoot timer by the time passed since the last frame
        shootTimer += Time.deltaTime;

        // If enough time has passed, fire the weapon and reset the timer
        if (shootTimer >= shootInterval)
        {
            Shoot();
            shootTimer = 0f;
        }
    }

    // ========================================================
    // CUSTOM METHODS
    // ========================================================

    /// <summary>
    /// Handles the logic for firing a projectile and triggering the visual effects.
    /// </summary>
    void Shoot()
    {
        // Safety check: ensure all necessary components are assigned in the Inspector
        if (labyrinthBall == null || projectilePrefab == null || firePoint == null)
            return;

        // --- TRIGGER VISUAL EFFECTS ---
        // 1. Instantly spike the emission brightness to maximum
        currentEmission = peakEmissionIntensity;

        // 2. Fire the radial spark particle system
        if (ringSparks != null) ringSparks.Play();

        // --- FIRE PROJECTILE ---
        // Spawn the projectile prefab exactly at the barrel's tip (firePoint)
        GameObject projectile = Instantiate(
            projectilePrefab,
            firePoint.position,
            firePoint.rotation
        );

        // Calculate the direction the bullet needs to travel to hit the target
        Vector3 direction = (labyrinthBall.transform.position - firePoint.position).normalized;

        // Grab the bullet's Rigidbody and apply physical velocity to shoot it forward
        Rigidbody rb = projectile.GetComponent<Rigidbody>();
        if (rb != null)
        {
            rb.linearVelocity = direction * projectileSpeed;
        }
    }

    /// <summary>
    /// Calculates a random coordinate within the assigned BoxCollider bounds.
    /// </summary>
    /// <returns>A Vector3 representing a point in 3D space.</returns>
    private Vector3 GetRandomPointInBounds()
    {
        // Get the absolute center of the BoxCollider in world space
        Vector3 center = bounds.transform.TransformPoint(bounds.center);

        // Get the total dimensions (width, height, depth) of the box
        Vector3 size = bounds.bounds.size;

        // Pick a random spot along the X, Y, and Z axes within those dimensions
        float randomX = Random.Range(-size.x / 2f, size.x / 2f);
        float randomY = Random.Range(-size.y / 2f, size.y / 2f);
        float randomZ = Random.Range(-size.z / 2f, size.z / 2f);

        // Combine the center point with the random offset and return it
        return center + new Vector3(randomX, randomY, randomZ);
    }
}