// DashboardManager.cs
// Replaces SceneAnchor + HomeScreen + PatientSwitcher.
// Builds a world-space Canvas (2000×1000 px at 0.001 scale) with a Home panel
// and a Dashboard panel. OVRUIPointer handles raycasting; this script handles
// state, layout, and data wiring.

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;
using UnityEngine.Networking;
using TMPro;

public class DashboardManager : MonoBehaviour
{
    // ── Color palette — forwarded from SonoXRTheme ────────────────────────────────
    static Color C_BG_PANEL => SonoXRTheme.BG_PANEL;
    static Color C_ACCENT   => SonoXRTheme.CYAN;
    static Color C_TITLE    => SonoXRTheme.TXT_BLUE;
    static Color C_MUTED    => SonoXRTheme.TXT_MUTED;
    static Color C_WARNING  => SonoXRTheme.WARNING;
    static Color C_BTN_NRM  => SonoXRTheme.BTN_NRM;
    static Color C_BTN_HOV  => SonoXRTheme.BTN_HOV;
    static Color C_BTN_PRE  => SonoXRTheme.BTN_PRE;
    static Color C_EF_GRN   => SonoXRTheme.EF_GREEN;
    static Color C_EF_ORG   => SonoXRTheme.EF_AMBER;
    static Color C_EF_RED   => SonoXRTheme.EF_RED;

    // ── State ─────────────────────────────────────────────────────────────────────
    enum AppState { Home, Dashboard }
    AppState _state = AppState.Home;

    // ── Scene refs ────────────────────────────────────────────────────────────────
    PatientBundleLoader _loader;
    HeartAnchor         _heartAnchor;   // kept for legacy compatibility only
    Transform           _heartRoot;     // DM-owned parent for GLB mesh — always valid
    Transform           _cam;

    // ── Canvas / panels ───────────────────────────────────────────────────────────
    Canvas           _canvas;
    RectTransform    _canvasRT;
    GameObject       _panelHome;
    GameObject       _panelDashboard;
    float            _yaw;

    // ── Home panel refs ───────────────────────────────────────────────────────────
    Transform _patientListRoot;

    // ── Dashboard panel refs ──────────────────────────────────────────────────────
    TextMeshProUGUI _navCounterTMP;
    RawImage        _scan4CH, _scan2CH;
    TextMeshProUGUI _efText, _volumeTMP, _uncTMP;   // _qualityTMP merged into _volumeTMP
    ClaudeAgentPanel _claudePanel;
    Transform        _rightPanelTransform;

    // ── Bundle meta ───────────────────────────────────────────────────────────────
    string _bundleRoot;

    [Serializable] class IndexJson { public List<string> patients; public string hero; }

    // ─────────────────────────────────────────────────────────────────────────────
    // Lifecycle
    // ─────────────────────────────────────────────────────────────────────────────

    void Awake()
    {
        _bundleRoot = System.IO.Path.Combine(Application.streamingAssetsPath, "patient_bundles");

        // Find or auto-create PatientBundleLoader
        _loader = FindAnyObjectByType<PatientBundleLoader>();
        if (_loader == null)
        {
            var go = new GameObject("PatientBundleLoader_Auto");
            _loader = go.AddComponent<PatientBundleLoader>();
            Debug.Log("[DashboardManager] Auto-created PatientBundleLoader.");
        }

        // Find HeartAnchor
        _heartAnchor = FindAnyObjectByType<HeartAnchor>();
        if (_heartAnchor == null)
            Debug.LogWarning("[DashboardManager] HeartAnchor not found in scene.");

        // Disable HeartGrabbable and HeartGrabber
        if (_heartAnchor != null)
        {
            var grabbable = _heartAnchor.GetComponent<HeartGrabbable>();
            if (grabbable != null) grabbable.enabled = false;

            var grabber = _heartAnchor.GetComponent<HeartGrabber>();
            if (grabber != null) grabber.enabled = false;
        }

        // Kill the legacy HeartHUD billboard overlay — DashboardManager owns all UI now.
        foreach (var hud in FindObjectsByType<HeartHUD>(FindObjectsSortMode.None))
            hud.gameObject.SetActive(false);
        _loader.hud = null;

        // Disable HeartAnchor — DashboardManager drives heart position directly.
        if (_heartAnchor != null)
            _heartAnchor.gameObject.SetActive(false);

        // Create DM-owned HeartRoot immediately so the hero GLB parents here from Start().
        // Scale 6 matches HeartAnchor.displayScale — life-size LV (~9 cm) → ~54 cm display.
        var hrGO = new GameObject("DM_HeartRoot");
        _heartRoot = hrGO.transform;
        _heartRoot.localScale = Vector3.one * 4.8f;   // 20% smaller than original 6×
        _heartRoot.gameObject.SetActive(false);   // hidden until Dashboard state
        _loader.heartMeshRoot = _heartRoot;        // all GLBs parent here from now on

        // Subscribe to loader event
        _loader.OnPatientLoaded += OnPatientLoaded;

        // Ensure EventSystem exists
        EnsureEventSystem();
    }

    void Start()
    {
        // Destroy HeartGrabbable's SphereCollider so it doesn't block UI raycasts
        if (_heartAnchor != null)
        {
            var sc = _heartAnchor.GetComponent<SphereCollider>();
            if (sc != null) Destroy(sc);
        }

        StartCoroutine(InitAfterFrames());
    }

    IEnumerator InitAfterFrames()
    {
        yield return null;
        yield return null;
        yield return StartCoroutine(Init());
    }

    void OnDestroy()
    {
        if (_loader != null)
            _loader.OnPatientLoaded -= OnPatientLoaded;
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Init
    // ─────────────────────────────────────────────────────────────────────────────

    IEnumerator Init()
    {
        yield return new WaitForSeconds(1f);

        // Find camera
        var rig = FindAnyObjectByType<OVRCameraRig>();
        _cam = rig != null ? rig.centerEyeAnchor : Camera.main?.transform;
        if (_cam == null)
        {
            Debug.LogWarning("[DashboardManager] No camera found — canvas not placed.");
            yield break;
        }

        _yaw = _cam.eulerAngles.y;

        Vector3 eyePos = _cam.position;
        Vector3 fwd    = _cam.forward; fwd.y = 0f;
        if (fwd.sqrMagnitude < 0.001f) fwd = Vector3.forward;
        fwd.Normalize();

        // Place canvas
        Vector3 canvasPos = eyePos + fwd * 2.0f;

        // Build canvas first — heart position is derived from canvas world-position
        BuildCanvas(canvasPos, Quaternion.Euler(0f, _yaw, 0f));

        // Force layout
        Canvas.ForceUpdateCanvases();
        yield return null;

        // Add BoxColliders to all buttons
        AddBoxCollidersToButtons(_canvas.transform);

        // Load home screen patient list
        yield return StartCoroutine(LoadHomeScreen());

        // Set initial state
        SetState(AppState.Home);

        Debug.Log($"[DashboardManager] Ready. Canvas at {canvasPos:F2}, yaw={_yaw:F1}°");
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Canvas construction
    // ─────────────────────────────────────────────────────────────────────────────

    void BuildCanvas(Vector3 worldPos, Quaternion worldRot)
    {
        // Canvas root
        var canvasGO = new GameObject("DashboardCanvas");
        canvasGO.transform.position = worldPos;
        canvasGO.transform.rotation = worldRot;

        _canvas = canvasGO.AddComponent<Canvas>();
        _canvas.renderMode = RenderMode.WorldSpace;

        _canvasRT = canvasGO.GetComponent<RectTransform>();
        _canvasRT.sizeDelta = new Vector2(2000f, 1300f);
        canvasGO.transform.localScale = Vector3.one * 0.001f;

        // CanvasScaler (reference pixels per unit)
        var scaler = canvasGO.AddComponent<CanvasScaler>();
        scaler.dynamicPixelsPerUnit = 1f;

        // GraphicRaycaster for EventSystem
        canvasGO.AddComponent<GraphicRaycaster>();

        // Panel_Home
        _panelHome = BuildPanelHome(_canvas.transform);

        // Panel_Dashboard
        _panelDashboard = BuildPanelDashboard(_canvas.transform);
    }

    // ─── Panel_Home ───────────────────────────────────────────────────────────────

    GameObject BuildPanelHome(Transform canvasRoot)
    {
        var panel = MakePanel(canvasRoot, "Panel_Home", new Vector2(2000f, 1300f));
        var bg = panel.GetComponent<Image>() ?? panel.AddComponent<Image>();
        SonoXRTheme.ApplyCard(bg, SonoXRTheme.BG_PANEL, 0);

        var vlg = panel.GetComponent<VerticalLayoutGroup>() ?? panel.AddComponent<VerticalLayoutGroup>();
        vlg.childAlignment         = TextAnchor.UpperCenter;
        vlg.childForceExpandWidth  = true;
        vlg.childForceExpandHeight = false;
        vlg.padding                = new RectOffset(60, 60, 60, 40);
        vlg.spacing                = 20f;

        // Title
        var titleGO = new GameObject("TitleText");
        titleGO.transform.SetParent(panel.transform, false);
        var titleTMP = titleGO.AddComponent<TextMeshProUGUI>();
        titleTMP.text      = "SonoXR";
        titleTMP.fontSize  = 52f;
        titleTMP.fontStyle = FontStyles.Bold;
        titleTMP.color     = SonoXRTheme.CYAN;
        titleTMP.alignment = TextAlignmentOptions.Center;
        var titleLE = titleGO.AddComponent<LayoutElement>();
        titleLE.preferredHeight = 72f;

        // Subtitle
        var subGO = new GameObject("SubtitleText");
        subGO.transform.SetParent(panel.transform, false);
        var subTMP = subGO.AddComponent<TextMeshProUGUI>();
        subTMP.text     = "Select a patient";
        subTMP.fontSize = 26f;
        subTMP.color    = C_MUTED;
        subTMP.alignment = TextAlignmentOptions.Center;
        var subLE = subGO.AddComponent<LayoutElement>();
        subLE.preferredHeight = 42f;

        // PatientListRoot — a ScrollRect
        var listRootGO = new GameObject("PatientListRoot");
        listRootGO.transform.SetParent(panel.transform, false);
        var listRT = listRootGO.AddComponent<RectTransform>();
        var listSR = listRootGO.AddComponent<ScrollRect>();
        listSR.horizontal = false;
        listSR.vertical   = true;
        var listLE = listRootGO.AddComponent<LayoutElement>();
        listLE.flexibleHeight = 1f;

        // Viewport
        var vpGO = new GameObject("Viewport");
        vpGO.transform.SetParent(listRootGO.transform, false);
        var vpRT = vpGO.AddComponent<RectTransform>();
        vpRT.anchorMin = Vector2.zero; vpRT.anchorMax = Vector2.one;
        vpRT.offsetMin = Vector2.zero; vpRT.offsetMax = Vector2.zero;
        vpGO.AddComponent<Image>().color = new Color(0f, 0f, 0f, 0.01f);
        var mask = vpGO.AddComponent<Mask>();
        mask.showMaskGraphic = false;
        listSR.viewport = vpRT;

        // Content inside viewport
        var contentGO = new GameObject("Content");
        contentGO.transform.SetParent(vpGO.transform, false);
        var contentRT = contentGO.AddComponent<RectTransform>();
        contentRT.anchorMin = new Vector2(0f, 1f);
        contentRT.anchorMax = new Vector2(1f, 1f);
        contentRT.pivot     = new Vector2(0.5f, 1f);
        contentRT.offsetMin = Vector2.zero;
        contentRT.offsetMax = Vector2.zero;
        var contentVLG = contentGO.AddComponent<VerticalLayoutGroup>();
        contentVLG.childAlignment        = TextAnchor.UpperCenter;
        contentVLG.childForceExpandWidth = true;
        contentVLG.childForceExpandHeight= false;
        contentVLG.spacing               = 12f;
        contentVLG.padding               = new RectOffset(20, 20, 10, 10);
        var csf = contentGO.AddComponent<ContentSizeFitter>();
        csf.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        listSR.content = contentRT;

        _patientListRoot = contentGO.transform;

        // Footer
        var footerGO = new GameObject("FooterText");
        footerGO.transform.SetParent(panel.transform, false);
        var footerTMP = footerGO.AddComponent<TextMeshProUGUI>();
        footerTMP.text      = "Real CAMUS data  ·  NOT a clinical device";
        footerTMP.fontSize  = 18f;
        footerTMP.color     = C_MUTED;
        footerTMP.alignment = TextAlignmentOptions.Center;
        var footerLE = footerGO.AddComponent<LayoutElement>();
        footerLE.preferredHeight = 32f;

        return panel;
    }

    // ─── Panel_Dashboard ──────────────────────────────────────────────────────────

    GameObject BuildPanelDashboard(Transform canvasRoot)
    {
        var panel = MakePanel(canvasRoot, "Panel_Dashboard", new Vector2(2000f, 1300f));
        // NO full-panel background Image — the center gap must stay transparent so the
        // 3D heart mesh is visible through it. TitleBar/BottomBar/LeftPanel/RightPanel
        // each carry their own Image backgrounds.

        var vlg = panel.GetComponent<VerticalLayoutGroup>() ?? panel.AddComponent<VerticalLayoutGroup>();
        vlg.childAlignment         = TextAnchor.UpperCenter;
        vlg.childForceExpandWidth  = true;
        vlg.childForceExpandHeight = false;
        vlg.spacing                = 0f;
        vlg.padding                = new RectOffset(0, 0, 0, 0);

        // TitleBar
        BuildTitleBar(panel.transform);

        // ContentRow
        BuildContentRow(panel.transform);

        // BottomBar
        BuildBottomBar(panel.transform);

        panel.SetActive(false);
        return panel;
    }

    void BuildTitleBar(Transform parent)
    {
        var bar = new GameObject("TitleBar");
        bar.transform.SetParent(parent, false);
        var barImg = bar.AddComponent<Image>();
        SonoXRTheme.ApplyCard(barImg, SonoXRTheme.BG_DEEP, 0);
        var hlg = bar.AddComponent<HorizontalLayoutGroup>();
        hlg.childAlignment         = TextAnchor.MiddleLeft;
        hlg.childForceExpandWidth  = false;
        hlg.childForceExpandHeight = true;
        hlg.padding                = new RectOffset(24, 16, 8, 8);
        hlg.spacing                = 14f;
        var barLE = bar.AddComponent<LayoutElement>();
        barLE.preferredHeight = 58f;

        // Title TMP (flexible) — cyan "SonoXR" + dim "Cardiac Analysis"
        var titleGO = new GameObject("TitleTMP");
        titleGO.transform.SetParent(bar.transform, false);
        var titleTMP = titleGO.AddComponent<TextMeshProUGUI>();
        titleTMP.text      = "<color=#2ECBF2>SonoXR</color>  <size=34><color=#B8DFFFA0>Cardiac Analysis</color></size>";
        titleTMP.fontSize  = 46f;
        titleTMP.fontStyle = FontStyles.Bold;
        titleTMP.color     = Color.white;
        titleTMP.alignment = TextAlignmentOptions.MidlineLeft;
        titleTMP.richText  = true;
        var titleLE = titleGO.AddComponent<LayoutElement>();
        titleLE.flexibleWidth = 1f;

        // NavCounter badge
        var badgeGO = new GameObject("NavBadge");
        badgeGO.transform.SetParent(bar.transform, false);
        var badgeImg = badgeGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(badgeImg, SonoXRTheme.BG_CARD, 16);
        var badgeLE = badgeGO.AddComponent<LayoutElement>();
        badgeLE.preferredWidth  = 90f;
        badgeLE.preferredHeight = 46f;
        var navGO = new GameObject("NavCounterTMP");
        navGO.transform.SetParent(badgeGO.transform, false);
        var navRT = navGO.AddComponent<RectTransform>();
        navRT.anchorMin = Vector2.zero; navRT.anchorMax = Vector2.one;
        navRT.offsetMin = Vector2.zero; navRT.offsetMax = Vector2.zero;
        _navCounterTMP = navGO.AddComponent<TextMeshProUGUI>();
        _navCounterTMP.text      = "1 / 5";
        _navCounterTMP.fontSize  = 28f;
        _navCounterTMP.fontStyle = FontStyles.Bold;
        _navCounterTMP.color     = SonoXRTheme.CYAN;
        _navCounterTMP.alignment = TextAlignmentOptions.Center;

        // Recenter Button
        var recenterBtn = MakeButton(bar.transform, "RecenterBtn", "↺  Recenter", 160f, 48f);
        recenterBtn.onClick.AddListener(Recenter);

        // Home Button
        var homeBtn = MakeButton(bar.transform, "HomeBtn", "⌂  Home", 130f, 48f);
        homeBtn.onClick.AddListener(ShowHome);
    }

    void BuildContentRow(Transform parent)
    {
        var row = new GameObject("ContentRow");
        row.transform.SetParent(parent, false);
        var rowHLG = row.AddComponent<HorizontalLayoutGroup>();
        rowHLG.childAlignment         = TextAnchor.UpperLeft;
        rowHLG.childForceExpandWidth  = false;
        rowHLG.childForceExpandHeight = true;
        rowHLG.spacing                = 0f;
        rowHLG.padding                = new RectOffset(0, 0, 0, 0);
        var rowLE = row.AddComponent<LayoutElement>();
        rowLE.flexibleHeight = 1f;

        // Left Panel (320px)
        BuildLeftPanel(row.transform);

        // Center Gap (transparent, heart visible through)
        var gapGO = new GameObject("CenterGap");
        gapGO.transform.SetParent(row.transform, false);
        var gapLE = gapGO.AddComponent<LayoutElement>();
        gapLE.flexibleWidth = 1f;
        // No Image — fully transparent gap

        // Right Panel (320px)
        BuildRightPanel(row.transform);
    }

    void BuildLeftPanel(Transform parent)
    {
        var leftGO = new GameObject("LeftPanel");
        leftGO.transform.SetParent(parent, false);
        var leftImg = leftGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(leftImg, SonoXRTheme.BG_PANEL, 12);
        var leftVLG = leftGO.AddComponent<VerticalLayoutGroup>();
        leftVLG.childAlignment         = TextAnchor.UpperCenter;
        leftVLG.childForceExpandWidth  = true;
        leftVLG.childForceExpandHeight = false;
        leftVLG.padding                = new RectOffset(14, 14, 14, 14);
        leftVLG.spacing                = 6f;
        var leftLE = leftGO.AddComponent<LayoutElement>();
        leftLE.preferredWidth = 200f;
        leftLE.minWidth       = 0f; // prevent children from forcing panel wider than 200 px

        // Panel header
        var headerGO = new GameObject("ScanHeaderTMP");
        headerGO.transform.SetParent(leftGO.transform, false);
        var headerTMP = headerGO.AddComponent<TextMeshProUGUI>();
        headerTMP.text      = "ECHO SCANS";
        headerTMP.fontSize  = 22f;
        headerTMP.fontStyle = FontStyles.Bold;
        headerTMP.color     = SonoXRTheme.CYAN;
        headerTMP.alignment = TextAlignmentOptions.Left;
        headerTMP.characterSpacing = 3f;
        var headerLE = headerGO.AddComponent<LayoutElement>();
        headerLE.preferredHeight = 34f;

        SonoXRTheme.AddDivider(leftGO.transform, 1.5f);

        // Scan 4CH — frame + image
        var frame4 = new GameObject("Scan4Frame");
        frame4.transform.SetParent(leftGO.transform, false);
        var frame4Img = frame4.AddComponent<Image>();
        SonoXRTheme.ApplyCard(frame4Img, SonoXRTheme.CYAN_DIM, 8);
        var frame4VLG = frame4.AddComponent<VerticalLayoutGroup>();
        frame4VLG.padding = new RectOffset(2, 2, 2, 2);
        frame4VLG.childForceExpandWidth  = true;
        frame4VLG.childForceExpandHeight = true;
        var frame4LE = frame4.AddComponent<LayoutElement>();
        frame4LE.preferredHeight = 260f;

        var scan4GO = new GameObject("Scan4CH");
        scan4GO.transform.SetParent(frame4.transform, false);
        _scan4CH = scan4GO.AddComponent<RawImage>();
        _scan4CH.color = Color.white;

        var lbl4GO = new GameObject("Label4CHTMP");
        lbl4GO.transform.SetParent(leftGO.transform, false);
        var lbl4TMP = lbl4GO.AddComponent<TextMeshProUGUI>();
        lbl4TMP.text      = "4-Chamber · End-Diastole";
        lbl4TMP.fontSize  = 22f;
        lbl4TMP.color     = SonoXRTheme.TXT_MUTED;
        lbl4TMP.alignment = TextAlignmentOptions.Center;
        var lbl4LE = lbl4GO.AddComponent<LayoutElement>();
        lbl4LE.preferredHeight = 34f;

        // Scan 2CH — frame + image
        var frame2 = new GameObject("Scan2Frame");
        frame2.transform.SetParent(leftGO.transform, false);
        var frame2Img = frame2.AddComponent<Image>();
        SonoXRTheme.ApplyCard(frame2Img, SonoXRTheme.CYAN_DIM, 8);
        var frame2VLG = frame2.AddComponent<VerticalLayoutGroup>();
        frame2VLG.padding = new RectOffset(2, 2, 2, 2);
        frame2VLG.childForceExpandWidth  = true;
        frame2VLG.childForceExpandHeight = true;
        var frame2LE = frame2.AddComponent<LayoutElement>();
        frame2LE.preferredHeight = 260f;

        var scan2GO = new GameObject("Scan2CH");
        scan2GO.transform.SetParent(frame2.transform, false);
        _scan2CH = scan2GO.AddComponent<RawImage>();
        _scan2CH.color = Color.white;

        var lbl2GO = new GameObject("Label2CHTMP");
        lbl2GO.transform.SetParent(leftGO.transform, false);
        var lbl2TMP = lbl2GO.AddComponent<TextMeshProUGUI>();
        lbl2TMP.text      = "2-Chamber · End-Diastole";
        lbl2TMP.fontSize  = 22f;
        lbl2TMP.color     = SonoXRTheme.TXT_MUTED;
        lbl2TMP.alignment = TextAlignmentOptions.Center;
        var lbl2LE = lbl2GO.AddComponent<LayoutElement>();
        lbl2LE.preferredHeight = 34f;

        SonoXRTheme.AddDivider(leftGO.transform, 1f);

        // Source note
        var srcGO = new GameObject("SourceNoteTMP");
        srcGO.transform.SetParent(leftGO.transform, false);
        var srcTMP = srcGO.AddComponent<TextMeshProUGUI>();
        srcTMP.text               = "CAMUS dataset  ·  LV contour from expert mask";
        srcTMP.fontSize           = 18f;
        srcTMP.color              = SonoXRTheme.TXT_HINT;
        srcTMP.alignment          = TextAlignmentOptions.Center;
        srcTMP.enableWordWrapping = true;
        var srcLE = srcGO.AddComponent<LayoutElement>();
        srcLE.preferredHeight = 44f;

        // Flexible spacer absorbs remaining height so content doesn't stretch
        var spacerGO = new GameObject("BottomSpacer");
        spacerGO.transform.SetParent(leftGO.transform, false);
        spacerGO.AddComponent<LayoutElement>().flexibleHeight = 1f;
    }

    void BuildRightPanel(Transform parent)
    {
        var rightGO = new GameObject("RightPanel");
        rightGO.transform.SetParent(parent, false);
        var rightImg = rightGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(rightImg, SonoXRTheme.BG_PANEL, 12);
        var rightVLG = rightGO.AddComponent<VerticalLayoutGroup>();
        rightVLG.childAlignment         = TextAnchor.UpperCenter;
        rightVLG.childForceExpandWidth  = true;
        rightVLG.childForceExpandHeight = false;
        rightVLG.padding                = new RectOffset(8, 8, 8, 8);
        rightVLG.spacing                = 4f;
        var rightLE = rightGO.AddComponent<LayoutElement>();
        rightLE.preferredWidth = 200f;
        rightLE.minWidth       = 0f; // hard-limit panel to 200 px, gap stays 1600 px

        _rightPanelTransform = rightGO.transform;

        // ClaudeAgentPanel component
        _claudePanel = rightGO.AddComponent<ClaudeAgentPanel>();
        _claudePanel.BuildUI(rightGO.transform);
    }

    void BuildBottomBar(Transform parent)
    {
        var bar = new GameObject("BottomBar");
        bar.transform.SetParent(parent, false);
        var barImg = bar.AddComponent<Image>();
        SonoXRTheme.ApplyCard(barImg, SonoXRTheme.BG_DEEP, 0);
        var hlg = bar.AddComponent<HorizontalLayoutGroup>();
        hlg.childAlignment         = TextAnchor.MiddleCenter;
        hlg.childForceExpandWidth  = false;
        hlg.childForceExpandHeight = true;
        hlg.padding                = new RectOffset(16, 16, 10, 10);
        hlg.spacing                = 14f;
        var barLE = bar.AddComponent<LayoutElement>();
        barLE.preferredHeight = 90f;

        // Prev button
        var prevBtn = MakeButton(bar.transform, "PrevBtn", "◄  Previous", 210f, 66f);
        prevBtn.onClick.AddListener(() =>
        {
            if (Time.time - _navLastTime < NAV_COOLDOWN) return;
            _navLastTime = Time.time;
            Debug.Log("[DashboardManager] PREV button clicked");
            _loader?.PrevPatient();
        });

        // Stats card — EF hero + volume + uncertainty
        var statsGO = new GameObject("StatsPanel");
        statsGO.transform.SetParent(bar.transform, false);
        var statsCardImg = statsGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(statsCardImg, SonoXRTheme.BG_CARD, 14);
        var statsVLG = statsGO.AddComponent<VerticalLayoutGroup>();
        statsVLG.childAlignment         = TextAnchor.MiddleCenter;
        statsVLG.childForceExpandWidth  = true;
        statsVLG.childForceExpandHeight = false;
        statsVLG.padding                = new RectOffset(12, 12, 8, 8);
        statsVLG.spacing                = 2f;
        var statsLE = statsGO.AddComponent<LayoutElement>();
        statsLE.flexibleWidth = 1f;

        var efGO = new GameObject("EFText");
        efGO.transform.SetParent(statsGO.transform, false);
        _efText = efGO.AddComponent<TextMeshProUGUI>();
        _efText.text      = "EF  —";
        _efText.fontSize  = 64f;
        _efText.fontStyle = FontStyles.Bold;
        _efText.color     = C_EF_GRN;
        _efText.alignment = TextAlignmentOptions.Center;
        var efLE = efGO.AddComponent<LayoutElement>();
        efLE.preferredHeight = 72f;

        var volGO = new GameObject("VolumeTMP");
        volGO.transform.SetParent(statsGO.transform, false);
        _volumeTMP = volGO.AddComponent<TextMeshProUGUI>();
        _volumeTMP.text      = "EDV — mL  ·  ESV — mL";
        _volumeTMP.fontSize  = 26f;
        _volumeTMP.color     = SonoXRTheme.TXT_MUTED;
        _volumeTMP.alignment = TextAlignmentOptions.Center;
        var volLE = volGO.AddComponent<LayoutElement>();
        volLE.preferredHeight = 34f;

        var uncGO = new GameObject("UncTMP");
        uncGO.transform.SetParent(statsGO.transform, false);
        _uncTMP = uncGO.AddComponent<TextMeshProUGUI>();
        _uncTMP.text               = "";
        _uncTMP.fontSize           = 22f;
        _uncTMP.color              = C_WARNING;
        _uncTMP.alignment          = TextAlignmentOptions.Center;
        _uncTMP.enableWordWrapping = false;
        _uncTMP.overflowMode       = TextOverflowModes.Ellipsis;
        var uncLE = uncGO.AddComponent<LayoutElement>();
        uncLE.preferredHeight = 22f;

        // Next button
        var nextBtn = MakeButton(bar.transform, "NextBtn", "Next  ►", 210f, 66f);
        nextBtn.onClick.AddListener(() =>
        {
            if (Time.time - _navLastTime < NAV_COOLDOWN) return;
            _navLastTime = Time.time;
            Debug.Log("[DashboardManager] NEXT button clicked");
            _loader?.NextPatient();
        });
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // State machine
    // ─────────────────────────────────────────────────────────────────────────────

    void SetState(AppState newState)
    {
        _state = newState;
        if (_panelHome      != null) _panelHome.SetActive(newState == AppState.Home);
        if (_panelDashboard != null) _panelDashboard.SetActive(newState == AppState.Dashboard);
        if (_heartRoot      != null) _heartRoot.gameObject.SetActive(newState == AppState.Dashboard);
        // Re-bake colliders after panel activates so layout dimensions are final.
        if (newState == AppState.Dashboard && _canvas != null)
            StartCoroutine(RefreshColliders());
    }

    IEnumerator RefreshColliders()
    {
        Canvas.ForceUpdateCanvases();
        yield return null;
        if (_canvas != null) AddBoxCollidersToButtons(_canvas.transform);
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Home screen
    // ─────────────────────────────────────────────────────────────────────────────

    IEnumerator LoadHomeScreen()
    {
        string url = FileUri(System.IO.Path.Combine(_bundleRoot, "index.json"));
        using var req = UnityWebRequest.Get(url);
        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogWarning($"[DashboardManager] Could not load index.json: {req.error}");
            AddHomeCard("demo_patient", "EF: ---", "unknown", null);
            yield break;
        }

        IndexJson idx = null;
        try { idx = JsonUtility.FromJson<IndexJson>(req.downloadHandler.text); }
        catch (Exception e) { Debug.LogWarning($"[DashboardManager] index.json parse error: {e.Message}"); }

        if (idx?.patients == null || idx.patients.Count == 0)
        {
            Debug.LogWarning("[DashboardManager] No patients in index.json");
            yield break;
        }

        // For each patient, try to fetch meta to show EF/quality on the card
        foreach (string pid in idx.patients)
        {
            string metaUrl = FileUri(System.IO.Path.Combine(_bundleRoot, pid, "meta.json"));
            using var metaReq = UnityWebRequest.Get(metaUrl);
            yield return metaReq.SendWebRequest();

            string efStr = "EF: ---";
            string qualStr = "";
            string capturedPid = pid; // capture for lambda
            if (metaReq.result == UnityWebRequest.Result.Success)
            {
                try
                {
                    var meta = JsonUtility.FromJson<PatientBundleMeta>(metaReq.downloadHandler.text);
                    if (meta != null)
                    {
                        efStr   = $"EF: {meta.EF_pct:F0}%";
                        qualStr = meta.image_quality ?? "";
                    }
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[DashboardManager] meta.json parse error for {pid}: {e.Message}");
                }
            }
            AddHomeCard(capturedPid, efStr, qualStr, capturedPid);
        }

        // Refresh colliders after cards added
        Canvas.ForceUpdateCanvases();
        yield return null;
        AddBoxCollidersToButtons(_canvas.transform);
    }

    void AddHomeCard(string pid, string efStr, string quality, string pidToLoad)
    {
        if (_patientListRoot == null) return;

        var cardGO = new GameObject($"Card_{pid}");
        cardGO.transform.SetParent(_patientListRoot, false);
        var cardImg = cardGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(cardImg, SonoXRTheme.BTN_NRM, 14);

        var cardLE = cardGO.AddComponent<LayoutElement>();
        cardLE.preferredHeight = 80f;

        var btn = cardGO.AddComponent<Button>();
        btn.colors = BtnColors();
        var capturedPid = pidToLoad ?? pid;
        btn.onClick.AddListener(() => SelectPatient(capturedPid));

        var hlg = cardGO.AddComponent<HorizontalLayoutGroup>();
        hlg.childAlignment         = TextAnchor.MiddleLeft;
        hlg.childForceExpandWidth  = false;
        hlg.childForceExpandHeight = true;
        hlg.padding                = new RectOffset(20, 20, 10, 10);
        hlg.spacing                = 16f;

        var nameGO = new GameObject("NameTMP");
        nameGO.transform.SetParent(cardGO.transform, false);
        var nameTMP = nameGO.AddComponent<TextMeshProUGUI>();
        nameTMP.text      = pid;
        nameTMP.fontSize  = 26f;
        nameTMP.fontStyle = FontStyles.Bold;
        nameTMP.color     = C_TITLE;
        var nameLE = nameGO.AddComponent<LayoutElement>();
        nameLE.flexibleWidth = 1f;

        var efGO = new GameObject("EF_TMP");
        efGO.transform.SetParent(cardGO.transform, false);
        var efTMP = efGO.AddComponent<TextMeshProUGUI>();
        efTMP.text      = efStr;
        efTMP.fontSize  = 24f;
        efTMP.color     = C_EF_GRN;
        var efLE = efGO.AddComponent<LayoutElement>();
        efLE.preferredWidth = 120f;

        if (!string.IsNullOrEmpty(quality))
        {
            var qGO = new GameObject("Quality_TMP");
            qGO.transform.SetParent(cardGO.transform, false);
            var qTMP = qGO.AddComponent<TextMeshProUGUI>();
            qTMP.text     = quality;
            qTMP.fontSize = 20f;
            qTMP.color    = C_MUTED;
            var qLE = qGO.AddComponent<LayoutElement>();
            qLE.preferredWidth = 100f;
        }
    }

    void SelectPatient(string pid)
    {
        SetState(AppState.Dashboard);
        try { _loader?.LoadByPid(pid); }
        catch (Exception e) { Debug.LogWarning($"[DashboardManager] LoadByPid error: {e.Message}"); }
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Data callback
    // ─────────────────────────────────────────────────────────────────────────────

    void OnPatientLoaded(PatientBundleData data, int idx, int total)
    {
        if (data == null) return;

        // Nav counter
        if (_navCounterTMP != null)
            _navCounterTMP.text = $"{idx} / {total}";

        // Scan textures
        if (_scan4CH != null) _scan4CH.texture = data.scan4ch;
        if (_scan2CH != null) _scan2CH.texture = data.scan2ch;

        // EF + volumes
        if (data.meta != null)
        {
            float ef = data.meta.EF_pct;

            if (_efText != null)
            {
                _efText.text  = $"EF {ef:F0}%";
                _efText.color = ef >= 50f ? C_EF_GRN : (ef >= 40f ? C_EF_ORG : C_EF_RED);
            }

            if (_volumeTMP != null)
            {
                string q = data.meta.image_quality ?? "---";
                _volumeTMP.text = $"EDV {data.meta.EDV_mL:F0} mL  ·  ESV {data.meta.ESV_mL:F0} mL  ·  {q}";
            }

            if (_uncTMP != null)
            {
                var unc = data.meta.uncertainty_region;
                _uncTMP.text = unc != null
                    ? $"Low confidence: {unc.region_name} ({unc.fraction_of_lv}) — {unc.reason}"
                    : "";
            }
        }

        // Claude panel
        if (_claudePanel != null && data.meta != null)
        {
            string pid = data.meta.patient ?? "unknown";
            _claudePanel.SetPatient(data.meta, pid);
        }
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // Navigation
    // ─────────────────────────────────────────────────────────────────────────────

    void Recenter()
    {
        if (_cam == null || _canvas == null) return;
        _yaw = _cam.eulerAngles.y;
        _canvas.transform.rotation = Quaternion.Euler(0f, _yaw, 0f);
    }

    void ShowHome()
    {
        SetState(AppState.Home);
    }

    // ─────────────────────────────────────────────────────────────────────────────
    // LateUpdate — lazy head-follow
    // ─────────────────────────────────────────────────────────────────────────────

    void Update()
    {
        if (_state != AppState.Dashboard) return;

        // ── Heart rotation via right thumbstick ───────────────────────────────────
        // Explicit RTouch so it works regardless of which hand holds the active pointer.
        // Euler tracking avoids drift from repeated Rotate() calls being overridden elsewhere.
        if (_heartRoot != null)
        {
            var rs = OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.RTouch);
            if (rs.sqrMagnitude > 0.01f)
            {
                _heartYaw   += rs.x  * HEART_ROT_SPEED * Time.deltaTime;
                _heartPitch -= rs.y  * HEART_ROT_SPEED * Time.deltaTime;
                _heartPitch  = Mathf.Clamp(_heartPitch, -80f, 80f); // prevent upside-down flip
                _heartRoot.rotation = Quaternion.Euler(_heartPitch, _heartYaw, 0f);
            }
        }

        if (_loader == null) return;

        // ── Patient navigation (left grip / Y / left-stick click) ─────────────────
        // Right stick is reserved for heart rotation — only use grip + face button.
        bool wantPrev =
            OVRInput.GetDown(OVRInput.Button.PrimaryHandTrigger,    OVRInput.Controller.LTouch)
         || OVRInput.GetDown(OVRInput.Button.Two,                   OVRInput.Controller.LTouch)   // Y
         || OVRInput.GetDown(OVRInput.Button.PrimaryThumbstickLeft, OVRInput.Controller.LTouch);

        bool wantNext =
            OVRInput.GetDown(OVRInput.Button.PrimaryHandTrigger,    OVRInput.Controller.RTouch)
         || OVRInput.GetDown(OVRInput.Button.Two,                   OVRInput.Controller.RTouch);  // B

        if ((wantPrev || wantNext) && Time.time - _navLastTime >= NAV_COOLDOWN)
        {
            _navLastTime = Time.time;
            if (wantPrev) _loader.PrevPatient();
            if (wantNext) _loader.NextPatient();
        }
    }

    void LateUpdate()
    {
        if (_cam == null || _canvas == null) return;
        float camYaw = _cam.eulerAngles.y;
        float diff   = Mathf.DeltaAngle(_yaw, camYaw);
        if (Mathf.Abs(diff) > 28f)
        {
            _yaw = Mathf.MoveTowardsAngle(_yaw, camYaw, 45f * Time.deltaTime);
            _canvas.transform.rotation = Quaternion.Euler(0f, _yaw, 0f);
        }

        // Keep heart locked to the canvas centre gap every frame.
        // Anchor to canvas world-position (not camera), so moving your head
        // forward/backward doesn't make the heart drift.
        // Canvas only rotates in place via yaw-follow — its world position never changes.
        if (_heartRoot != null && _state == AppState.Dashboard && _canvas != null)
        {
            // 15 cm IN FRONT of canvas (toward user) — heart renders on top of the UI plane,
            // so it can never appear "behind" panels. Gap is 1340 px (1.34 m) wide so there
            // is no chance the heart mesh extends far enough sideways to hit the side panels.
            _heartRoot.position = _canvas.transform.position
                                - _canvas.transform.forward * 0.15f;

            // Diagnostic — logs every ~2 s so we can confirm position + child count via logcat.
            _heartDbgTimer -= Time.deltaTime;
            if (_heartDbgTimer <= 0f)
            {
                _heartDbgTimer = 2f;
                Debug.Log($"[DM] heartRoot active={_heartRoot.gameObject.activeSelf} " +
                          $"pos={_heartRoot.position:F2} children={_heartRoot.childCount} " +
                          $"cam={_cam.position:F2} canvas={_canvas.transform.position:F2}");
            }
        }
    }
    float _heartDbgTimer = 0f;
    float _navLastTime   = -99f;
    float _heartYaw      = 0f;   // accumulated yaw  (right stick X)
    float _heartPitch    = 0f;   // accumulated pitch (right stick Y)
    const float NAV_COOLDOWN    = 0.35f;
    const float HEART_ROT_SPEED = 90f;   // degrees per second at full deflection

    // ─────────────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────────────

    static ColorBlock BtnColors() => SonoXRTheme.BtnColors();

    Button MakeButton(Transform parent, string name, string label, float w, float h)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);

        var img = go.AddComponent<Image>();
        SonoXRTheme.ApplyCard(img, SonoXRTheme.BTN_NRM, 20);

        var btn = go.AddComponent<Button>();
        btn.colors        = BtnColors();
        btn.targetGraphic = img;

        var le = go.AddComponent<LayoutElement>();
        le.preferredWidth  = w;
        le.preferredHeight = h;

        var txtGO = new GameObject("Label");
        txtGO.transform.SetParent(go.transform, false);
        var txtRT = txtGO.AddComponent<RectTransform>();
        txtRT.anchorMin = Vector2.zero;
        txtRT.anchorMax = Vector2.one;
        txtRT.offsetMin = Vector2.zero;
        txtRT.offsetMax = Vector2.zero;
        var tmp = txtGO.AddComponent<TextMeshProUGUI>();
        tmp.text      = label;
        tmp.fontSize  = 21f;
        tmp.fontStyle = FontStyles.Bold;
        tmp.color     = SonoXRTheme.TXT_WHITE;
        tmp.alignment = TextAlignmentOptions.Center;

        return btn;
    }

    static GameObject MakePanel(Transform parent, string name, Vector2 size)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        var rt = go.AddComponent<RectTransform>();
        rt.anchorMin = Vector2.zero;
        rt.anchorMax = Vector2.one;
        rt.offsetMin = Vector2.zero;
        rt.offsetMax = Vector2.zero;
        return go;
    }

    static void AddBoxCollidersToButtons(Transform root)
    {
        var buttons = root.GetComponentsInChildren<Button>(true);
        foreach (var btn in buttons)
        {
            var col = btn.GetComponent<BoxCollider>();
            if (col == null) col = btn.gameObject.AddComponent<BoxCollider>();
            var rt = btn.GetComponent<RectTransform>();
            if (rt == null) continue;
            float w = rt.rect.width;
            float h = rt.rect.height;
            // Fall back to LayoutElement preferred values if layout hasn't run yet (inactive panels).
            if (w < 1f) { var le = btn.GetComponent<LayoutElement>(); w = (le != null && le.preferredWidth  > 0) ? le.preferredWidth  : 200f; }
            if (h < 1f) { var le = btn.GetComponent<LayoutElement>(); h = (le != null && le.preferredHeight > 0) ? le.preferredHeight : 60f;  }
            col.size = new Vector3(w, h, 50f);
        }
    }

    static void EnsureEventSystem()
    {
        if (FindAnyObjectByType<EventSystem>() != null) return;
        var esGO = new GameObject("EventSystem");
        esGO.AddComponent<EventSystem>();
        esGO.AddComponent<StandaloneInputModule>();
        Debug.Log("[DashboardManager] Auto-created EventSystem.");
    }

    static string FileUri(string path)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        return path;
#else
        return "file://" + path.Replace("\\", "/");
#endif
    }
}
