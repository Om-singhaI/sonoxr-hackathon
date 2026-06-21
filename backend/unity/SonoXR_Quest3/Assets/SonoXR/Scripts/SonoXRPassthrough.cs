// SonoXRPassthrough.cs
// Iteration 8 — Quest 3 mixed-reality setup.
// Attach to the OVRCameraRig GameObject in the scene.
// Requires: Meta XR Core SDK (com.meta.xr.sdk.core)
//
// What this does:
//   1. Forces passthrough mode on startup (real room visible).
//   2. Sets the camera background to black (transparent key for passthrough layer).
//   3. Creates/finds the OVRPassthroughLayer and enables it.
//   4. Reports the passthrough state so you can confirm it's running.

using UnityEngine;

[RequireComponent(typeof(OVRManager))]
public class SonoXRPassthrough : MonoBehaviour
{
    [Header("Passthrough")]
    [Tooltip("The passthrough layer component — drag it here or it will be found/created at Start.")]
    public OVRPassthroughLayer passthroughLayer;

    [Tooltip("Background camera colour — must be pure black so passthrough shows through.")]
    private readonly Color _clearColor = new Color(0f, 0f, 0f, 0f);

    void Awake()
    {
        // OVRManager passthrough flag must be set before Start runs.
        var mgr = GetComponent<OVRManager>();
        mgr.isInsightPassthroughEnabled = true;
    }

    void Start()
    {
        // Ensure all cameras use a transparent black clear colour.
        foreach (var cam in Camera.allCameras)
        {
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = _clearColor;
        }

        // Find or create the passthrough layer.
        if (passthroughLayer == null)
            passthroughLayer = FindAnyObjectByType<OVRPassthroughLayer>();

        if (passthroughLayer == null)
        {
            var go = new GameObject("OVRPassthroughLayer");
            passthroughLayer = go.AddComponent<OVRPassthroughLayer>();
            Debug.Log("[SonoXR] Created OVRPassthroughLayer at runtime.");
        }

        passthroughLayer.projectionSurfaceType = OVRPassthroughLayer.ProjectionSurfaceType.Reconstructed;
        passthroughLayer.enabled = true;

        Debug.Log("[SonoXR] Passthrough enabled. isInsightPassthroughEnabled=" +
                  GetComponent<OVRManager>().isInsightPassthroughEnabled);
    }

    // Expose a toggle so you can flip passthrough off from the Inspector at runtime.
    public void SetPassthrough(bool on)
    {
        passthroughLayer.enabled = on;
    }
}
