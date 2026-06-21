// HeartHUD.cs
// Floating world-space data panel — data-driven from PatientBundleLoader.
//
// Displays: EF%, EDV/ESV, cardiac phase, real ultrasound scan thumbnails,
// patient ID, nav counter, honesty watermark.
//
// Setup:
//   1. Create a Canvas (World Space, 0.8 × 0.55 m) as a sibling of the heart.
//   2. Attach this script to the Canvas.
//   3. Create the child objects listed under "Inspector fields" below.
//   4. Drag a PatientBundleLoader into the 'loader' field.
//   5. Drag HeartBeatController into 'heart' for live phase sync.
//
// Canvas child layout (suggested):
//   EF_Text         — TextMeshProUGUI, font 80 bold, colour #5b9dff, top-left
//   Volume_Text     — TextMeshProUGUI, font 36, colour white, below EF
//   Phase_Text      — TextMeshProUGUI, font 48, colour driven at runtime
//   PatientID_Text  — TextMeshProUGUI, font 28, colour #93a0b2
//   NavCounter_Text — TextMeshProUGUI, font 24, colour #666, e.g. "2 / 5"
//   Honesty_Text    — TextMeshProUGUI, font 20, colour #666
//   Scan4CH_Image   — RawImage, 200 × 160 px, bottom-left
//   Scan2CH_Image   — RawImage, 200 × 160 px, next to 4CH

using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class HeartHUD : MonoBehaviour
{
    // ── Inspector fields ─────────────────────────────────────────────────────────

    [Header("Text — assign child TextMeshProUGUI objects")]
    public TextMeshProUGUI efLabel;          // "EF 64%"
    public TextMeshProUGUI volumeLabel;      // "EDV 91 mL · ESV 33 mL"
    public TextMeshProUGUI phaseLabel;       // "DIASTOLE" / "SYSTOLE"
    public TextMeshProUGUI patientIDLabel;   // "patient0001 · Good"
    public TextMeshProUGUI navCounter;       // "1 / 5"
    public TextMeshProUGUI honesty;          // disclaimer

    [Header("Scan image panels — assign RawImage children (optional)")]
    public RawImage scan4CHImage;
    public RawImage scan2CHImage;

    [Header("Heart reference — for live cardiac-phase sync")]
    public HeartBeatController heart;

    [Header("Patient loader — for Next/Prev button wiring")]
    public PatientBundleLoader loader;

    [Header("Billboard — always face the viewer")]
    public bool billboard = true;

    // ── Private state ────────────────────────────────────────────────────────────

    float _ef    = 64f;
    float _edvML = 91f;
    float _esvML = 32.7f;

    Transform _cam;

    static readonly Color ColAccent  = new Color(0.36f, 0.62f, 1.00f);  // #5b9dff
    static readonly Color ColGreen   = new Color(0.26f, 0.75f, 0.54f);  // #43c08a
    static readonly Color ColMuted   = new Color(0.58f, 0.63f, 0.70f);  // #93a0b2
    static readonly Color ColWarning = new Color(1.00f, 0.58f, 0.17f);  // #f5972b

    // ── Unity lifecycle ──────────────────────────────────────────────────────────

    void Start()
    {
        _cam = Camera.main?.transform;
        RefreshStaticLabels();
    }

    void LateUpdate()
    {
        UpdatePhaseLabel();
        BillboardToCamera();
    }

    // ── Public API (called by PatientBundleLoader) ───────────────────────────────

    /// <summary>
    /// Update the HUD with data from a freshly loaded patient bundle.
    /// Called by PatientBundleLoader after every successful patient load.
    /// </summary>
    public void LoadFromBundle(PatientBundleData data, int patientNumber, int patientTotal)
    {
        if (data == null || data.meta == null) return;

        var m = data.meta;
        _ef    = m.EF_pct;
        _edvML = m.EDV_mL;
        _esvML = m.ESV_mL;

        RefreshStaticLabels();

        // Patient ID + quality badge
        if (patientIDLabel != null)
        {
            patientIDLabel.text  = $"{m.patient}  ·  quality: {m.image_quality}";
            patientIDLabel.color = ColMuted;
        }

        // Navigation counter
        if (navCounter != null)
        {
            navCounter.text  = $"{patientNumber} / {patientTotal}";
            navCounter.color = ColMuted;
        }

        // Scan thumbnails
        if (scan4CHImage != null && data.scan4ch != null)
            scan4CHImage.texture = data.scan4ch;
        if (scan2CHImage != null && data.scan2ch != null)
            scan2CHImage.texture = data.scan2ch;

        // Honesty footer — prefer bundle narration as a subtitle
        if (honesty != null)
        {
            string note = string.IsNullOrEmpty(m.honesty_note)
                ? "Real CAMUS echo data · biplane geometric estimate · not a clinical device."
                : m.honesty_note;
            honesty.text  = note;
            honesty.color = ColMuted;
        }
    }

    // ── Private helpers ──────────────────────────────────────────────────────────

    void RefreshStaticLabels()
    {
        // EF — colour-code by range (ACC/AHA thresholds)
        if (efLabel != null)
        {
            efLabel.text  = $"EF {_ef:F0}%";
            efLabel.color = EfColour(_ef);
        }

        // Volumes
        if (volumeLabel != null)
            volumeLabel.text = $"EDV {_edvML:F0} mL  ·  ESV {_esvML:F0} mL";

        // Honesty default (overwritten by LoadFromBundle)
        if (honesty != null && string.IsNullOrEmpty(honesty.text))
        {
            honesty.text  = "Biplane geometric estimate — not a clinical measurement.\n" +
                            "Cardiac cycle is a visualisation (ED↔ES from CAMUS expert masks).";
            honesty.color = ColMuted;
        }
    }

    void UpdatePhaseLabel()
    {
        if (phaseLabel == null || heart == null) return;
        float phase = (Time.time % heart.cycleDuration) / heart.cycleDuration;
        bool  isDiastole = phase < 0.5f;
        phaseLabel.text  = isDiastole ? "DIASTOLE" : "SYSTOLE";
        phaseLabel.color = isDiastole ? ColGreen : ColAccent;
    }

    void BillboardToCamera()
    {
        if (!billboard || _cam == null) return;
        transform.rotation = Quaternion.LookRotation(transform.position - _cam.position);
    }

    // ACC/AHA: normal ≥55%, mildly reduced 41-54%, severely reduced ≤40%
    static Color EfColour(float ef)
    {
        if (ef >= 55f) return ColGreen;
        if (ef >= 41f) return ColWarning;
        return new Color(1f, 0.36f, 0.36f);   // red for severely reduced
    }
}
