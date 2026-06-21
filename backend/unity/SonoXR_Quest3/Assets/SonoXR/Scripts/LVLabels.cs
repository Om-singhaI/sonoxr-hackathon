// LVLabels.cs
// Build step 5 (supplemental): floating EDV/ESV volume markers near the heart.
//
// Shows the actual volumes from the patient's bundle data:
//   "EDV 91 mL" — near upper half of heart (full end-diastole)
//   "ESV 33 mL" — near lower half (empty end-systole)
//
// Labels are positioned relative to the heart root and billboard toward the camera
// each frame. They update whenever a new patient bundle loads.
//
// Create an empty GameObject "LVLabels" in the scene and attach this script.

using UnityEngine;
using TMPro;

public class LVLabels : MonoBehaviour
{
    [Header("Heart reference — drag the Heart root GameObject")]
    public Transform heartRoot;

    [Header("Label offsets in world metres (relative to heart world position)")]
    public Vector3 edvOffset = new Vector3( 0.18f,  0.08f, -0.04f);
    public Vector3 esvOffset = new Vector3( 0.18f, -0.08f, -0.04f);

    TextMeshPro _edvLabel;
    TextMeshPro _esvLabel;
    TextMeshPro _edvTitle;
    TextMeshPro _esvTitle;

    static readonly Color EDColour  = new Color(0.36f, 0.62f, 1.00f);   // blue — full
    static readonly Color ESColour  = new Color(1.00f, 0.58f, 0.17f);   // orange — empty
    static readonly Color TitleCol  = new Color(0.65f, 0.72f, 0.82f);

    // ── lifecycle ─────────────────────────────────────────────────────────────────

    void Awake()
    {
        CreateLabels();
    }

    void LateUpdate()
    {
        if (heartRoot == null || Camera.main == null) return;
        Vector3 camPos  = Camera.main.transform.position;
        Vector3 heartWP = heartRoot.position;

        UpdateLabelTransform(_edvLabel?.transform.parent, heartWP + edvOffset, camPos);
        UpdateLabelTransform(_esvLabel?.transform.parent, heartWP + esvOffset, camPos);
    }

    // ── construction ──────────────────────────────────────────────────────────────

    void CreateLabels()
    {
        var edvGO = CreateLabelGroup("EDV_Marker");
        _edvTitle = AddLine(edvGO, "END-DIASTOLE", 0.020f, TitleCol, 0f);
        _edvLabel = AddLine(edvGO, "EDV -- mL",     0.028f, EDColour, -0.033f);

        var esvGO = CreateLabelGroup("ESV_Marker");
        _esvTitle = AddLine(esvGO, "END-SYSTOLE",   0.020f, TitleCol, 0f);
        _esvLabel = AddLine(esvGO, "ESV -- mL",     0.028f, ESColour, -0.033f);
    }

    GameObject CreateLabelGroup(string name)
    {
        var go = new GameObject(name);
        return go;
    }

    TextMeshPro AddLine(GameObject parent, string text, float fontSize, Color colour, float localY)
    {
        var go = new GameObject(text.Length > 16 ? text.Substring(0, 16) : text);
        go.transform.SetParent(parent.transform, false);
        go.transform.localPosition = new Vector3(0f, localY, 0f);

        var tmp = go.AddComponent<TextMeshPro>();
        tmp.text       = text;
        tmp.fontSize   = fontSize;
        tmp.color      = colour;
        tmp.alignment  = TextAlignmentOptions.Left;
        tmp.enableAutoSizing = false;
        tmp.GetComponent<RectTransform>().sizeDelta = new Vector2(0.40f, 0.05f);
        return tmp;
    }

    static void UpdateLabelTransform(Transform group, Vector3 worldPos, Vector3 camPos)
    {
        if (group == null) return;
        group.position = worldPos;
        Vector3 dir = camPos - worldPos;
        if (dir.sqrMagnitude > 0.001f)
            group.rotation = Quaternion.LookRotation(dir, Vector3.up);
    }

    // ── public API ────────────────────────────────────────────────────────────────

    public void LoadFromBundle(PatientBundleData data)
    {
        if (data?.meta == null) return;
        if (_edvLabel != null) _edvLabel.text = $"EDV {data.meta.EDV_mL:F0} mL";
        if (_esvLabel != null) _esvLabel.text = $"ESV {data.meta.ESV_mL:F0} mL";
    }
}
