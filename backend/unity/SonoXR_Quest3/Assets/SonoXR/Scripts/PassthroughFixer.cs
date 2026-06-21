// PassthroughFixer.cs
// Attach to any GameObject in the scene.
// Automatically fixes the most common cause of black-screen passthrough on Quest 3:
// the CenterEyeAnchor camera's background alpha being 255 (opaque black) instead of 0.
//
// Also ensures OVRPassthroughLayer is enabled and present.

using System.Collections;
using UnityEngine;

public class PassthroughFixer : MonoBehaviour
{
    void Awake()
    {
        // Fix the camera immediately — before the first frame renders.
        FixAllCameras();

        // OVRPassthroughLayer needs one extra frame to initialise.
        StartCoroutine(EnsurePassthroughLayer());
    }

    void FixAllCameras()
    {
        // Find every camera in the scene and make its background fully transparent.
        // This lets the OVRPassthroughLayer show the real world underneath.
        foreach (var cam in Camera.allCameras)
        {
            cam.clearFlags      = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0f, 0f, 0f, 0f);   // alpha MUST be 0
        }
        Debug.Log("[PassthroughFixer] Camera backgrounds set to transparent.");
    }

    IEnumerator EnsurePassthroughLayer()
    {
        yield return null;

        // Re-fix cameras in case OVR added/replaced them after Awake.
        FixAllCameras();

        // Make sure there is an OVRPassthroughLayer in the scene.
        var layer = FindAnyObjectByType<OVRPassthroughLayer>();
        if (layer == null)
        {
            Debug.Log("[PassthroughFixer] No OVRPassthroughLayer found — creating one.");
            var go = new GameObject("PassthroughLayer_Auto");
            layer = go.AddComponent<OVRPassthroughLayer>();
        }

        layer.enabled = true;
        Debug.Log($"[PassthroughFixer] OVRPassthroughLayer enabled on '{layer.gameObject.name}'.");
    }
}
