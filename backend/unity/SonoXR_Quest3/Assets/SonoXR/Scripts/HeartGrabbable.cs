// HeartGrabbable.cs
// Point your controller at the heart and squeeze the grip trigger to grab.
// Move your hand to move and rotate the heart. Release grip to drop in place.
// Works at any distance via raycast — no need to physically reach the heart.
//
// Requires: HeartAnchor on the same GameObject.
// A SphereCollider is auto-added in Awake so the raycast has something to hit.

using System.Collections;
using UnityEngine;

[RequireComponent(typeof(HeartAnchor))]
public class HeartGrabbable : MonoBehaviour
{
    [Tooltip("Grip axis threshold (0-1). Lower = easier to trigger.")]
    [Range(0.1f, 0.9f)]
    public float gripThreshold = 0.5f;

    [Tooltip("Max ray length for pointing-at-heart grab (metres).")]
    public float rayReach = 5f;

    [Tooltip("Fallback proximity radius if ray misses (metres). 0 = disable.")]
    public float proximityRadius = 0.30f;

    public bool IsGrabbed => _grabbed;

    // ── private ───────────────────────────────────────────────────────────────────
    HeartAnchor         _anchor;
    OVRCameraRig        _rig;
    bool                _grabbed;
    OVRInput.Controller _ctrl = OVRInput.Controller.None;

    // Grab offsets in controller-local space.
    Vector3    _localPosOffset;
    Quaternion _localRotOffset;

    // Track grip axis state manually so we can detect "just pressed" reliably.
    float _prevGripL, _prevGripR;

    // ── lifecycle ─────────────────────────────────────────────────────────────────

    void Awake()
    {
        _anchor = GetComponent<HeartAnchor>();

        // Add a SphereCollider so the raycast can hit this GameObject.
        // Radius is in LOCAL space; HeartAnchor sets localScale = displayScale (6),
        // so worldRadius = localRadius × scale.  0.025 × 6 = 0.15 m — about right
        // for the LV mesh bounding sphere.  isTrigger=false so Physics.Raycast finds it.
        if (GetComponent<SphereCollider>() == null)
        {
            var col = gameObject.AddComponent<SphereCollider>();
            col.radius    = 0.025f;
            col.isTrigger = false;
        }

        StartCoroutine(FindRig());
    }

    IEnumerator FindRig()
    {
        yield return null;
        yield return null;
        _rig = FindAnyObjectByType<OVRCameraRig>();
        if (_rig == null)
            Debug.LogWarning("[HeartGrabbable] OVRCameraRig not found — grabbing disabled.");
        else
            Debug.Log("[HeartGrabbable] Ready.  Point at the heart and squeeze the grip trigger.");
    }

    void Update()
    {
        if (_rig == null) return;

        float gripL = OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger,   OVRInput.Controller.LTouch);
        float gripR = OVRInput.Get(OVRInput.Axis1D.PrimaryHandTrigger,   OVRInput.Controller.RTouch);

        bool pressedL = gripL > gripThreshold && _prevGripL <= gripThreshold;
        bool pressedR = gripR > gripThreshold && _prevGripR <= gripThreshold;
        bool heldL    = gripL > gripThreshold;
        bool heldR    = gripR > gripThreshold;

        if (!_grabbed)
        {
            if (pressedL) TryBeginGrab(OVRInput.Controller.LTouch,  _rig.leftHandAnchor);
            if (pressedR) TryBeginGrab(OVRInput.Controller.RTouch, _rig.rightHandAnchor);
        }
        else
        {
            bool held = _ctrl == OVRInput.Controller.LTouch ? heldL : heldR;
            if (held) ContinueGrab();
            else      ReleaseGrab();
        }

        _prevGripL = gripL;
        _prevGripR = gripR;
    }

    // ── grab logic ────────────────────────────────────────────────────────────────

    void TryBeginGrab(OVRInput.Controller ctrl, Transform hand)
    {
        if (_grabbed) return;

        bool hit = false;

        // 1. Raycast from the controller's forward direction.
        //    Only accept the hit if it landed on this heart or one of its children.
        var ray = new Ray(hand.position, hand.forward);
        if (Physics.Raycast(ray, out RaycastHit info, rayReach))
        {
            if (info.collider != null &&
                (info.collider.gameObject == gameObject ||
                 info.collider.transform.IsChildOf(transform)))
            {
                hit = true;
                Debug.Log($"[HeartGrabbable] Ray-grab with {ctrl}  dist={info.distance:F2} m");
            }
        }

        // 2. Proximity fallback — useful when the controller is already inside the mesh.
        if (!hit && proximityRadius > 0f)
        {
            hit = Vector3.Distance(hand.position, transform.position) <= proximityRadius;
            if (hit) Debug.Log($"[HeartGrabbable] Proximity-grab with {ctrl}");
        }

        if (!hit) return;

        _ctrl              = ctrl;
        _grabbed           = true;
        _anchor.grabLocked = true;

        // Capture offsets in controller-local space so position AND rotation follow the hand.
        _localPosOffset = Quaternion.Inverse(hand.rotation) * (transform.position - hand.position);
        _localRotOffset = Quaternion.Inverse(hand.rotation) * transform.rotation;
    }

    void ContinueGrab()
    {
        Transform hand  = HandTransform(_ctrl);
        transform.position = hand.position + hand.rotation * _localPosOffset;
        transform.rotation = hand.rotation * _localRotOffset;
    }

    void ReleaseGrab()
    {
        // Save the heart's current position as the new anchor point.
        _anchor.CommitPosition(transform.position);
        _grabbed = false;
        _ctrl    = OVRInput.Controller.None;
        Debug.Log($"[HeartGrabbable] Dropped at {transform.position:F2}");
    }

    Transform HandTransform(OVRInput.Controller ctrl)
        => ctrl == OVRInput.Controller.LTouch ? _rig.leftHandAnchor : _rig.rightHandAnchor;
}
