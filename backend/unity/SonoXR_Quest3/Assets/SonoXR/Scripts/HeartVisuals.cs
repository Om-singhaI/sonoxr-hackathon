// HeartVisuals.cs
// Build step 1+4+5: red beating LV · transparent generic shell · honest 3D labels.
//
// HONESTY SPLIT (mandatory, do not merge):
//   RED MESH  = our CAMUS biplane reconstruction — real patient geometry, unchanged.
//   SHELL     = generic anatomical context — semi-transparent, clearly labeled "generic".
//
// Attach to the Heart root GameObject (alongside HeartAnchor).
// The shell and labels are scene-root siblings so they are NOT scaled by HeartAnchor.
//
// Build order contract: if CreateShell() or CreateLabels() throw, ApplyLVMaterial()
// still worked (each method is independent / cuttable).

using System.Collections.Generic;
using UnityEngine;
using TMPro;

[RequireComponent(typeof(HeartAnchor))]
public class HeartVisuals : MonoBehaviour
{
    [Header("Materials — leave null to auto-create")]
    public Material reconstructedLVMaterial;
    public Material referenceShellMaterial;

    [Header("Generic reference shell")]
    [Tooltip("Drag in any free heart model prefab. Leave null for a sphere placeholder.")]
    public GameObject genericHeartPrefab;

    [Tooltip("World-space radius of the sphere placeholder (set automatically from HeartAnchor.displayScale).")]
    public float shellSphereRadius = 0.14f;

    // ── private ──────────────────────────────────────────────────────────────────
    GameObject _shell;
    readonly List<(GameObject go, Vector3 worldOffset)> _labels = new List<(GameObject, Vector3)>();

    static readonly Color CrimsonBase = new Color(0.72f, 0.08f, 0.10f);
    static readonly Color CrimsonEmit = new Color(0.35f, 0.01f, 0.02f);
    static readonly Color ShellTint   = new Color(0.84f, 0.72f, 0.72f, 0.13f);

    // ── lifecycle ─────────────────────────────────────────────────────────────────

    void Start()
    {
        // Snapshot LV renderers NOW — before the shell (which will be added to
        // the scene tree AFTER this snapshot) could be included.
        var lvRenderers = GetComponentsInChildren<Renderer>(true);

        ApplyLVMaterial(lvRenderers);   // step 1
        // CreateShell() disabled — URP transparent material causes magenta artifact.
        CreateHonestLabels();           // step 5 (cuttable)
    }

    void LateUpdate()
    {
        // Shell follows the heart (HeartAnchor re-anchors position each LateUpdate).
        if (_shell != null)
        {
            _shell.transform.position = transform.position;
            _shell.transform.rotation = transform.rotation;
        }

        // Labels follow the heart and billboard toward the camera.
        if (Camera.main == null) return;
        Vector3 camPos = Camera.main.transform.position;

        foreach (var (go, offset) in _labels)
        {
            if (go == null) continue;
            go.transform.position = transform.position + offset;
            // TMP glyphs are on the -Z face. We need -Z to face the camera, so +Z
            // must face AWAY from camera. LookRotation(pos - cam) → +Z toward scene.
            Vector3 away = go.transform.position - camPos;
            if (away.sqrMagnitude > 0.001f)
                go.transform.rotation = Quaternion.LookRotation(away, Vector3.up);
        }
    }

    // ── step 1: crimson tissue material on every LV renderer ─────────────────────

    void ApplyLVMaterial(Renderer[] renderers)
    {
        if (reconstructedLVMaterial == null)
            reconstructedLVMaterial = SonoXRShaders.MakeCrimson(CrimsonBase, CrimsonEmit);

        foreach (var r in renderers)
            r.sharedMaterial = reconstructedLVMaterial;
    }

    // ── step 4: generic reference shell (cuttable) ───────────────────────────────

    void CreateShell()
    {
        _shell = genericHeartPrefab != null
            ? Instantiate(genericHeartPrefab)
            : CreateSphereShell();

        _shell.name = "ReferenceHeart_Generic";

        if (referenceShellMaterial == null)
            referenceShellMaterial = MakeTransparentMaterial();

        foreach (var r in _shell.GetComponentsInChildren<Renderer>(true))
            r.sharedMaterial = referenceShellMaterial;

        _shell.transform.position = transform.position;
        _shell.transform.rotation = transform.rotation;
    }

    GameObject CreateSphereShell()
    {
        // Derive shell radius from HeartAnchor.displayScale and the known LV GLB size.
        // LV mesh vertices are scaled ×0.01 in build_camus_bundle.py → ~0.03m in GLB.
        // At displayScale=6 that's ~0.18m world height; bounding sphere ≈ 0.09m radius.
        var anchor = GetComponent<HeartAnchor>();
        if (anchor != null)
            shellSphereRadius = 0.03f * anchor.displayScale * 0.5f * 1.45f;

        var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
        Destroy(go.GetComponent<Collider>());
        // Sphere has radius=0.5 at localScale=1; scale to hit shellSphereRadius.
        go.transform.localScale = Vector3.one * (shellSphereRadius * 2f);
        return go;
    }

    Material MakeTransparentMaterial()
        => SonoXRShaders.MakeTransparent(ShellTint);

    // ── step 5: honest 3D labels (cuttable) ──────────────────────────────────────

    void CreateHonestLabels()
    {
        // World offset relative to heart's world position.
        // At displayScale=6 the LV is ~18cm tall: offsets of ±22cm clear it.
        SpawnLabel("LV_HonestyLabel",
            "Reconstructed from this patient's\nultrasound  (Simpson's biplane)",
            new Vector3(0f, -0.22f, -0.02f),
            0.028f, new Color(1.00f, 0.55f, 0.55f));

        SpawnLabel("Shell_HonestyLabel",
            "Anatomical reference  (generic)",
            new Vector3(0f, +0.28f, -0.02f),
            0.022f, new Color(0.70f, 0.70f, 0.70f));
    }

    void SpawnLabel(string goName, string text, Vector3 worldOffset, float fontSize, Color colour)
    {
        var go = new GameObject(goName);
        go.transform.position = transform.position + worldOffset;

        var tmp = go.AddComponent<TextMeshPro>();
        tmp.text       = text;
        tmp.fontSize   = fontSize;
        tmp.color      = colour;
        tmp.alignment  = TextAlignmentOptions.Center;
        tmp.enableAutoSizing = false;
        tmp.GetComponent<RectTransform>().sizeDelta = new Vector2(0.7f, 0.12f);

        _labels.Add((go, worldOffset));
    }

    // ── public API ────────────────────────────────────────────────────────────────

    // Apply crimson to the freshly loaded GLB renderers.
    // HeartVisuals.Start() snapshots renderers before the GLB is loaded (async),
    // so this is the only place where the GLB's own renderers get the right material.
    public void LoadFromBundle(PatientBundleData data)
    {
        if (data?.glbRoot == null) return;
        ApplyLVMaterial(data.glbRoot.GetComponentsInChildren<Renderer>(true));
    }
}
