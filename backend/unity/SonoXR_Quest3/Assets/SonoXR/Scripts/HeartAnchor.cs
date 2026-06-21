// HeartAnchor.cs
// Iteration 8 — places the heart at a fixed world position in the room at
// standing eye height, scaled up for a demo crowd, on first frame.
//
// Attach to the Heart root GameObject.
// The initial position is set once in Start(); the judge can grab-rotate from there.

using UnityEngine;

public class HeartAnchor : MonoBehaviour
{
    [Header("Placement")]
    [Tooltip("World-space position. Default: 1.5 m in front, 1.6 m high (standing eye level).")]
    public Vector3 worldPosition = new Vector3(0f, 1.6f, 1.5f);

    [Tooltip("Uniform scale multiplier. Life-size LV ~ 9 cm long; 6x -> ~54 cm, easy to walk around.")]
    [Range(2f, 12f)]
    public float displayScale = 6f;

    [Tooltip("Face toward the camera rig origin on Start.")]
    public bool faceCamera = true;

    [Header("Camera rig reference (auto-found if null)")]
    public Transform cameraRig;

    void Start()
    {
        if (cameraRig == null)
        {
            var rig = FindAnyObjectByType<OVRCameraRig>();
            if (rig != null) cameraRig = rig.transform;
        }

        // Position and scale.
        transform.position   = worldPosition;
        transform.localScale = Vector3.one * displayScale;

        if (faceCamera && cameraRig != null)
        {
            Vector3 dir = (cameraRig.position - transform.position);
            dir.y = 0f;
            if (dir.sqrMagnitude > 0.001f)
                transform.rotation = Quaternion.LookRotation(-dir);  // face toward viewer
        }

        Debug.Log($"[HeartAnchor] placed at {worldPosition}, scale {displayScale}x.");
    }

    // Called by HeartGrabber to temporarily unlock position during grab.
    [HideInInspector] public bool grabLocked = false;

    void LateUpdate()
    {
        // If not grabbed, re-anchor position (prevents drift from physics).
        if (!grabLocked)
            transform.position = worldPosition;
    }

    public void CommitPosition(Vector3 newWorldPos)
    {
        worldPosition = newWorldPos;
        grabLocked    = false;
    }
}
