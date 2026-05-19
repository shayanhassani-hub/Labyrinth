using UnityEngine;
using UnityEngine.InputSystem; // 1. Added the modern Input System namespace

public class HologramToggle : MonoBehaviour
{
    public Material pbrMaterial;
    public Material hologramMaterial;
    private MeshRenderer meshRenderer;
    private bool isHologram = false;

    void Start()
    {
        meshRenderer = GetComponent<MeshRenderer>();
        meshRenderer.material = pbrMaterial; // Default to realistic look
    }

    void Update()
    {
        // 2. Updated to the new Input System keyboard check
        if (Keyboard.current != null && Keyboard.current.spaceKey.wasPressedThisFrame)
        {
            isHologram = !isHologram;
            meshRenderer.material = isHologram ? hologramMaterial : pbrMaterial;
        }
    }
}