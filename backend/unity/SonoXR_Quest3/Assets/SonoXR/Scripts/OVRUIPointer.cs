// OVRUIPointer.cs
// Controller laser pointer that drives real Unity UI Buttons via ExecuteEvents.
// Replaces ControllerPointer.cs + ClickButton.cs.
// OVRInput only — no Interaction SDK.

using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;

public class OVRUIPointer : MonoBehaviour
{
    [Header("Ray settings")]
    public float rayLength = 8f;

    [Header("Appearance")]
    public float lineWidth = 0.003f;
    public float dotRadius = 0.010f;

    static readonly Color LaserCol = new Color(0.55f, 0.85f, 1f);
    static readonly Color DotCol   = Color.white;

    // Per-hand state
    class HandState
    {
        public Transform    anchor;
        public LineRenderer line;
        public GameObject   dot;
        public Button       hoveredButton;
        public ScrollRect   hoveredScroll;
        public float        prevTrigger;
        public bool         OVRInput_L; // true = left controller
    }

    HandState _left, _right;
    OVRCameraRig _rig;

    // ── lifecycle ─────────────────────────────────────────────────────────────────

    void Awake() => StartCoroutine(Init());

    IEnumerator Init()
    {
        yield return null;
        yield return null;

        _rig = FindAnyObjectByType<OVRCameraRig>();
        if (_rig == null)
        {
            Debug.LogWarning("[OVRUIPointer] No OVRCameraRig found — UI pointers disabled.");
            yield break;
        }

        _left  = CreateHandState(_rig.leftHandAnchor,  "LaserL", "DotL", isLeft: true);
        _right = CreateHandState(_rig.rightHandAnchor, "LaserR", "DotR", isLeft: false);

        Debug.Log("[OVRUIPointer] UI laser pointers ready.");
    }

    HandState CreateHandState(Transform anchor, string lineName, string dotName, bool isLeft)
    {
        var hs = new HandState
        {
            anchor   = anchor,
            line     = MakeLine(lineName),
            dot      = MakeDot(dotName),
            OVRInput_L = isLeft
        };
        return hs;
    }

    // ── update ────────────────────────────────────────────────────────────────────

    void Update()
    {
        if (_rig == null) return;
        if (_left  != null) ProcessHand(_left,  OVRInput.Controller.LTouch);
        if (_right != null) ProcessHand(_right, OVRInput.Controller.RTouch);
    }

    void ProcessHand(HandState hs, OVRInput.Controller ctrl)
    {
        if (hs.anchor == null || hs.line == null || hs.dot == null) return;

        Vector3 origin = hs.anchor.position;
        Vector3 dir    = hs.anchor.forward;

        // RaycastAll — skip SphereCollider (heart grab proxy)
        var hits = Physics.RaycastAll(new Ray(origin, dir), rayLength);
        RaycastHit? best     = null;
        float       bestDist = float.MaxValue;
        foreach (var h in hits)
        {
            if (h.collider is SphereCollider) continue;
            if (h.distance < bestDist) { bestDist = h.distance; best = h; }
        }

        // Update laser visuals
        Vector3 endPt = best.HasValue ? best.Value.point : origin + dir * rayLength;
        hs.line.SetPosition(0, origin);
        hs.line.SetPosition(1, endPt);
        hs.dot.SetActive(best.HasValue);
        if (best.HasValue) hs.dot.transform.position = best.Value.point;

        // Find button and scroll rect on hit
        Button    newBtn    = null;
        ScrollRect newScroll = null;
        if (best.HasValue)
        {
            newBtn    = FindButtonInHierarchy(best.Value.collider.transform);
            newScroll = best.Value.collider.GetComponentInParent<ScrollRect>();
        }

        // Hover events
        if (newBtn != hs.hoveredButton)
        {
            if (hs.hoveredButton != null)
                ExecuteEvents.Execute(hs.hoveredButton.gameObject,
                    new PointerEventData(EventSystem.current), ExecuteEvents.pointerExitHandler);

            if (newBtn != null)
                ExecuteEvents.Execute(newBtn.gameObject,
                    new PointerEventData(EventSystem.current), ExecuteEvents.pointerEnterHandler);

            hs.hoveredButton = newBtn;
        }
        hs.hoveredScroll = newScroll;

        // Click detection — index trigger
        float trigger = OVRInput.Get(OVRInput.Axis1D.PrimaryIndexTrigger, ctrl);
        bool  clicked = OVRInput.GetDown(OVRInput.Button.PrimaryIndexTrigger, ctrl)
                     || (trigger > 0.85f && hs.prevTrigger <= 0.85f);

        if (clicked && hs.hoveredButton != null)
        {
            var ptrData = new PointerEventData(EventSystem.current);
            ExecuteEvents.Execute(hs.hoveredButton.gameObject, ptrData,
                ExecuteEvents.pointerClickHandler);
            // Also invoke directly for reliability
            hs.hoveredButton.onClick.Invoke();
        }
        hs.prevTrigger = trigger;

        // Thumbstick Y scroll (right controller only)
        if (ctrl == OVRInput.Controller.RTouch && hs.hoveredScroll != null)
        {
            float scrollY = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, ctrl).y;
            if (Mathf.Abs(scrollY) > 0.1f)
                hs.hoveredScroll.verticalNormalizedPosition =
                    Mathf.Clamp01(hs.hoveredScroll.verticalNormalizedPosition + scrollY * Time.deltaTime * 1.5f);
        }
    }

    static Button FindButtonInHierarchy(Transform t)
    {
        while (t != null)
        {
            var btn = t.GetComponent<Button>();
            if (btn != null) return btn;
            t = t.parent;
        }
        return null;
    }

    // ── factories ─────────────────────────────────────────────────────────────────

    LineRenderer MakeLine(string goName)
    {
        var go = new GameObject(goName);
        go.transform.SetParent(transform);
        var lr = go.AddComponent<LineRenderer>();
        lr.positionCount     = 2;
        lr.startWidth        = lineWidth;
        lr.endWidth          = lineWidth * 0.25f;
        lr.useWorldSpace     = true;
        lr.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        lr.receiveShadows    = false;
        lr.material          = SonoXRShaders.MakeLine(LaserCol);
        return lr;
    }

    GameObject MakeDot(string goName)
    {
        var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        go.name = goName;
        Destroy(go.GetComponent<Collider>());
        go.transform.SetParent(transform);
        go.transform.localScale = Vector3.one * (dotRadius * 2f);
        go.GetComponent<Renderer>().material = SonoXRShaders.MakeLine(DotCol);
        go.SetActive(false);
        return go;
    }
}
