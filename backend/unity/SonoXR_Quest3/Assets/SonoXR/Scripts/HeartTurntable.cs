// HeartTurntable.cs
// Centered turntable rotation for the LV heart.
// Position always stays locked at HeartAnchor.worldPosition — the heart CANNOT
// be flung away. Only rotation is controlled by the user.
//
// Controls:
//   Right thumbstick X  → yaw  (left / right rotation)
//   Right thumbstick Y  → pitch (tilt forward / back)
//   Left  thumbstick X  → yaw  (alternate hand)
//   Grip trigger (either hand) → grab-rotate in place:
//       while held, heart rotation = delta(hand rotation from grab start).
//       Position remains at anchor centre — only rotation is applied.
//
// Call ResetOrientation() to snap back to default facing (e.g., from a RESET button).
// Requires: HeartAnchor on the same GameObject.

using System.Collections;
using UnityEngine;

[RequireComponent(typeof(HeartAnchor))]
public class HeartTurntable : MonoBehaviour
{
    [Header("Thumbstick sensitivity (degrees per second at full stick)")]
    public float yawSpeed   = 90f;
    public float pitchSpeed = 60f;

    [Header("Grab-rotate sensitivity (1 = 1:1 with hand rotation)")]
    [Range(0.5f, 3f)]
    public float grabSensitivity = 1.4f;

    [Header("Grip threshold")]
    [Range(0.1f, 0.9f)]
    public float gripThreshold = 0.5f;

    // ── private ───────────────────────────────────────────────────────────────────

    HeartAnchor          _anchor;
    OVRCameraRig         _rig;
    bool                 _grabbed;
    OVRInput.Controller  _ctrl;
    Quaternion           _grabStartHandRot;
    Quaternion           _grabStartHeartRot;
    float                _prevGripL, _prevGripR;

    // ── lifecycle ─────────────────────────────────────────────────────────────────

    void Awake()
    {
        _anchor = GetComponent<HeartAnchor>();
        StartCoroutine(FindRig());
    }

    IEnumerator FindRig()
    {
        yield return null;
        yield return null;
        _rig = FindAnyObjectByType<OVRCameraRig>();
        if (_rig == null)
            Debug.LogWarning("[HeartTurntable] No OVRCameraRig found.");
        else
            Debug.Log("[HeartTurntable] Ready. Thumbstick=rotate, Grip=grab-rotate.");
    }

    // ── update ────────────────────────────────────────────────────────────────────

    void Update()
    {
        if (_rig == null) return;

        // Thumbstick rotation — only while not grab-rotating.
        if (!_grabbed) ApplyThumbstick();

        // Grip grab-rotate.
        float gripL = OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger, OVRInput.Controller.LTouch);
        float gripR = OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger, OVRInput.Controller.RTouch);

        bool pressL = gripL > gripThreshold && _prevGripL <= gripThreshold;
        bool pressR = gripR > gripThreshold && _prevGripR <= gripThreshold;
        bool heldL  = gripL > gripThreshold;
        bool heldR  = gripR > gripThreshold;

        if (!_grabbed)
        {
            if (pressR) BeginGrab(OVRInput.Controller.RTouch, _rig.rightHandAnchor);
            else if (pressL) BeginGrab(OVRInput.Controller.LTouch, _rig.leftHandAnchor);
        }
        else
        {
            bool held = _ctrl == OVRInput.Controller.LTouch ? heldL : heldR;
            if (held) ContinueGrab();
            else EndGrab();
        }

        _prevGripL = gripL;
        _prevGripR = gripR;
    }

    // ── thumbstick ────────────────────────────────────────────────────────────────

    void ApplyThumbstick()
    {
        // Accept input from either hand; sum them (usually only one is active).
        Vector2 stickL = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.LTouch);
        Vector2 stickR = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.RTouch);
        float yawInput   = stickL.x + stickR.x;
        float pitchInput = stickL.y + stickR.y;

        if (Mathf.Abs(yawInput) < 0.05f && Mathf.Abs(pitchInput) < 0.05f) return;

        float yaw   = yawInput   *  yawSpeed   * Time.deltaTime;
        float pitch = pitchInput * -pitchSpeed  * Time.deltaTime;   // stick up = tilt top away

        // Yaw around world Y keeps the "up" axis stable.
        transform.Rotate(Vector3.up, yaw, Space.World);
        // Pitch around local X for natural forward/back tilt.
        transform.Rotate(Vector3.right, pitch, Space.Self);
    }

    // ── grab-rotate ───────────────────────────────────────────────────────────────

    void BeginGrab(OVRInput.Controller ctrl, Transform hand)
    {
        _grabbed           = true;
        _ctrl              = ctrl;
        _grabStartHandRot  = hand.rotation;
        _grabStartHeartRot = transform.rotation;
        // Do NOT set grabLocked — HeartAnchor position locking must stay active.
        Debug.Log($"[HeartTurntable] Grab-rotate start ({ctrl})");
    }

    void ContinueGrab()
    {
        Transform hand     = HandTransform(_ctrl);
        Quaternion delta   = hand.rotation * Quaternion.Inverse(_grabStartHandRot);

        // Scale the rotation delta by grabSensitivity.
        delta.ToAngleAxis(out float angle, out Vector3 axis);
        if (axis.sqrMagnitude < 0.001f) return;     // degenerate quaternion guard
        Quaternion scaled  = Quaternion.AngleAxis(angle * grabSensitivity, axis);

        transform.rotation = scaled * _grabStartHeartRot;
    }

    void EndGrab()
    {
        _grabbed = false;
        _ctrl    = OVRInput.Controller.None;
        Debug.Log($"[HeartTurntable] Grab-rotate end, eulerAngles={transform.eulerAngles:F0}");
    }

    // ── public API ────────────────────────────────────────────────────────────────

    public void ResetOrientation()
    {
        if (_grabbed) EndGrab();
        transform.rotation = Quaternion.identity;
        Debug.Log("[HeartTurntable] Orientation reset to identity.");
    }

    // ── helpers ───────────────────────────────────────────────────────────────────

    Transform HandTransform(OVRInput.Controller ctrl)
        => ctrl == OVRInput.Controller.LTouch ? _rig.leftHandAnchor : _rig.rightHandAnchor;
}
