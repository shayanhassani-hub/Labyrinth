using UnityEngine;
using UnityEngine.InputSystem;

public class HologramToggle : MonoBehaviour
{
    public Material pbrMaterial;
    public Material hologramMaterial;

    // Changed this to an array of the generic 'Renderer' class
    private Renderer[] allRenderers;
    private bool isHologram = false;

    void Start()
    {
        // Tells Unity to find every renderer on this object and all its children
        allRenderers = GetComponentsInChildren<Renderer>();

        // Set the default material for every part found
        ApplyMaterial(pbrMaterial);
    }

    void Update()
    {
        if (Keyboard.current != null && Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            isHologram = !isHologram;
            ApplyMaterial(isHologram ? hologramMaterial : pbrMaterial);
        }
    }

    // A small helper method to swap the material on every part of the drone
    private void ApplyMaterial(Material mat)
    {
        foreach (Renderer r in allRenderers)
        {
            r.material = mat;
        }
    }
}