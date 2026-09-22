using UnityEngine;

public class ProjectileLifetime : MonoBehaviour
{
    [SerializeField] private float lifetime = 6f;

    private void Start()
    {
        Destroy(gameObject, lifetime);
    }
}
