// HeartGrabber.cs
// Iteration 8 — hand-tracking grab-and-rotate the heart.
// Uses Meta XR Core SDK: OVRHand + OVRSkeleton (no full Interaction SDK needed).
//
// Gesture: PINCH (index + thumb) on either hand to grab.
//   - While pinching: heart follows hand rotation (rotate around its own centre).
//   - Release pinch: heart stays at new orientation; position re-anchors via HeartAnchor.
//
// Attach to the Heart root GameObject alongside HeartAnchor.
//
// Requires com.meta.xr.sdk.core — OVRHand is in the scene under OVRCameraRig/
//   TrackingSpace/LeftHandAnchor/OVRHandPrefab (same for Right).
// Add OVRHand prefabs to the scene via: Meta > Tools > Building Blocks > Hand Tracking.

using UnityEngine;

[RequireComponent(typeof(HeartAnchor))]
public class HeartGrabber : MonoBehaviour
{
    [Header("Hand references — drag OVRHand prefab objects here")]
    public OVRHand leftHand;
    public OVRHand rightHand;

    [Header("Pinch threshold")]
    [Range(0f, 1f)]
    public float pinchThreshold = 0.85f;

    [Header("Rotation smoothing")]
    public float rotationSpeed = 120f;   // degrees per second at full hand tilt

    private HeartAnchor _anchor;
    private bool   _isGrabbing;
    private OVRHand _grabbingHand;
    private Quaternion _grabStartHandRot;
    private Quaternion _grabStartHeartRot;

    void Awake() => _anchor = GetComponent<HeartAnchor>();

    void Update()
    {
        if (!_isGrabbing)
            TryBeginGrab();
        else
            UpdateGrab();
    }

    void TryBeginGrab()
    {
        OVRHand hand = GetPinchingHand();
        if (hand == null) return;

        _isGrabbing       = true;
        _grabbingHand     = hand;
        _grabStartHandRot = hand.PointerPose.rotation;
        _grabStartHeartRot= transform.rotation;
        _anchor.grabLocked = true;

        Debug.Log($"[HeartGrabber] Grab started ({(_grabbingHand == leftHand ? "left" : "right")} hand).");
    }

    void UpdateGrab()
    {
        // Check release.
        if (_grabbingHand == null ||
            _grabbingHand.GetFingerPinchStrength(OVRHand.HandFinger.Index) < pinchThreshold * 0.7f)
        {
            EndGrab();
            return;
        }

        // Rotate the heart by the delta rotation of the grabbing hand.
        Quaternion handDelta = _grabbingHand.PointerPose.rotation *
                               Quaternion.Inverse(_grabStartHandRot);
        transform.rotation = handDelta * _grabStartHeartRot;
    }

    void EndGrab()
    {
        _isGrabbing = false;
        _anchor.CommitPosition(transform.position);  // re-lock position, keep new rotation
        Debug.Log("[HeartGrabber] Released.");
    }

    OVRHand GetPinchingHand()
    {
        if (IsPinching(leftHand))  return leftHand;
        if (IsPinching(rightHand)) return rightHand;
        return null;
    }

    bool IsPinching(OVRHand hand)
    {
        if (hand == null || !hand.IsTracked) return false;
        return hand.GetFingerPinchStrength(OVRHand.HandFinger.Index) >= pinchThreshold;
    }

    void OnDisable()
    {
        if (_isGrabbing) EndGrab();
    }
}
