using UnityEngine;

public class Test : MonoBehaviour
{
    [Header("Movment Bounds")]
    public BoxCollider bounds;
    
    private Vector3 GetRandomPointInBounds()
    {
        Vector3 center = bounds.transform.TransformPoint(bounds.center);
        Vector3 size = bounds.bounds.size;

        float randomX = Random.Range(-size.x / 2f, size.x / 2f);
        float randomY = Random.Range(-size.y / 2f, size.y / 2f);
        float randomZ = Random.Range(-size.z / 2f, size.z / 2f);

        return center + new Vector3(randomX, randomY, randomZ);
    }
    
    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        
    }
}
