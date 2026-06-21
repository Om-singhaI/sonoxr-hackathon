// ClaudeAgentPanel.cs
// Self-contained UI component for the AI analysis right panel.
// Added to the RightPanel by DashboardManager.
// Manages preset query buttons, a response scroll area, and Android TTS.

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.Networking;
using TMPro;

public class ClaudeAgentPanel : MonoBehaviour
{
    // ── Patient state ─────────────────────────────────────────────────────────────
    PatientBundleMeta _meta;
    string            _pid;
    string            _lastResponse;

    // ── UI refs ───────────────────────────────────────────────────────────────────
    TextMeshProUGUI _statusTMP;
    TextMeshProUGUI _responseTMP;
    ScrollRect      _responseScroll;
    Coroutine       _dotsCoroutine;

    // ── Deepgram TTS + STT ────────────────────────────────────────────────────────
    DeepgramTTS     _tts;
    DeepgramSTT     _stt;
    TextMeshProUGUI _speakBtnLabel;
    TextMeshProUGUI _askBtnLabel;
    Image           _askBtnImg;
    bool            _recording;

    // ── Debounce — OVRUIPointer fires multiple click events per trigger press ─────
    bool            _queryInProgress;      // blocks concurrent RunQuery coroutines
    float           _lastClickTime;        // shared cooldown for preset + speak buttons
    float           _recordingStartTime;   // when mic recording began
    const float     CLICK_COOLDOWN  = 0.8f;
    const float     MIN_RECORD_SECS = 0.4f; // minimum recording before stop is honoured

    // ── Colors — forwarded from SonoXRTheme ───────────────────────────────────────
    static Color C_ACCENT  => SonoXRTheme.CYAN;
    static Color C_MUTED   => SonoXRTheme.TXT_MUTED;
    static Color C_TITLE   => SonoXRTheme.TXT_BLUE;
    static Color C_BTN_NRM => SonoXRTheme.BTN_NRM;
    static Color C_BTN_HOV => SonoXRTheme.BTN_HOV;
    static Color C_BTN_PRE => SonoXRTheme.BTN_PRE;
    static Color C_BTN_REC => SonoXRTheme.BTN_REC;

    // ── System prompt ─────────────────────────────────────────────────────────────
    const string SYSTEM_PROMPT =
        "You are an AI assistant for SonoXR, a research demonstration of ultrasound-derived 3D cardiac reconstruction. " +
        "Rules: (1) Explain in plain language for educated non-specialists. " +
        "(2) NEVER diagnose or make clinical recommendations. " +
        "(3) ALWAYS flag that EF is a biplane geometric estimate, not a precision clinical measurement. " +
        "(4) ALWAYS mention low-confidence regions when relevant. " +
        "(5) NEVER invent anatomy or measurements beyond what is provided. " +
        "(6) State data is from CAMUS dataset (real patients, not live scanning). " +
        "(7) Keep responses to 4-6 sentences. " +
        "(8) End every response with: \"This is a research demonstration only — not a clinical assessment.\"";

    // ── Public API ────────────────────────────────────────────────────────────────

    public void SetPatient(PatientBundleMeta meta, string pid)
    {
        _meta = meta;
        _pid  = pid ?? "unknown";
        if (_statusTMP != null)
            _statusTMP.text = "Patient updated — select a query above.";
        if (_responseTMP != null)
            _responseTMP.text = "";
        _lastResponse = null;
    }

    public void BuildUI(Transform parent)
    {
        // ── Section header ─────────────────────────────────────────────────────────
        var headerGO = new GameObject("AgentHeaderTMP");
        headerGO.transform.SetParent(parent, false);
        var headerTMP = headerGO.AddComponent<TextMeshProUGUI>();
        headerTMP.text             = "AI ANALYSIS";
        headerTMP.fontSize         = 22f;
        headerTMP.fontStyle        = FontStyles.Bold;
        headerTMP.color            = SonoXRTheme.INDIGO;
        headerTMP.alignment        = TextAlignmentOptions.Left;
        headerTMP.characterSpacing = 3f;
        headerGO.AddComponent<LayoutElement>().preferredHeight = 34f;

        SonoXRTheme.AddDivider(parent, 1.5f, new Color(0.45f, 0.35f, 0.92f, 0.35f));

        // ── Preset buttons — 2 × 2 grid (no ScrollRect) ──────────────────────────
        // Layout: 2 HLG rows inside a VLG container. Saves ~130px vs old scroll.
        string[] labels = new[]
        {
            "Explain Heart",
            "What is EF?",
            "Why uncertain?",
            "EF in range?"
        };

        var gridGO = new GameObject("PresetGrid");
        gridGO.transform.SetParent(parent, false);
        var gridVLG = gridGO.AddComponent<VerticalLayoutGroup>();
        gridVLG.childAlignment         = TextAnchor.UpperCenter;
        gridVLG.childForceExpandWidth  = true;
        gridVLG.childForceExpandHeight = false;
        gridVLG.spacing                = 5f;
        gridGO.AddComponent<LayoutElement>().preferredHeight = 116f; // 2×55 + 6

        for (int row = 0; row < 2; row++)
        {
            var rowGO  = new GameObject($"Row{row}");
            rowGO.transform.SetParent(gridGO.transform, false);
            var rowHLG = rowGO.AddComponent<HorizontalLayoutGroup>();
            rowHLG.childAlignment         = TextAnchor.MiddleCenter;
            rowHLG.childForceExpandWidth  = true;
            rowHLG.childForceExpandHeight = true;
            rowHLG.spacing                = 5f;
            rowGO.AddComponent<LayoutElement>().preferredHeight = 55f;

            for (int col = 0; col < 2; col++)
            {
                int idx = row * 2 + col;
                int capturedIdx = idx;
                var btnGO  = new GameObject($"PresetBtn_{idx}");
                btnGO.transform.SetParent(rowGO.transform, false);
                var btnImg = btnGO.AddComponent<Image>();
                SonoXRTheme.ApplyCard(btnImg, SonoXRTheme.BTN_NRM, 12);
                var btn = btnGO.AddComponent<Button>();
                btn.colors        = BtnColors();
                btn.targetGraphic = btnImg;
                btn.onClick.AddListener(() => OnPresetClicked(capturedIdx));

                var lblGO  = new GameObject("Label");
                lblGO.transform.SetParent(btnGO.transform, false);
                var lblRT  = lblGO.AddComponent<RectTransform>();
                lblRT.anchorMin = Vector2.zero; lblRT.anchorMax = Vector2.one;
                lblRT.offsetMin = new Vector2(4, 0); lblRT.offsetMax = new Vector2(-4, 0);
                var lblTMP = lblGO.AddComponent<TextMeshProUGUI>();
                lblTMP.text             = labels[idx];
                lblTMP.fontSize         = 18f;
                lblTMP.color            = SonoXRTheme.TXT_WHITE;
                lblTMP.alignment        = TextAlignmentOptions.Center;
                lblTMP.enableWordWrapping = true;
            }
        }

        SonoXRTheme.AddDivider(parent, 1.5f);

        // ── Status line ─────────────────────────────────────────────────────────
        var statusGO = new GameObject("StatusTMP");
        statusGO.transform.SetParent(parent, false);
        _statusTMP = statusGO.AddComponent<TextMeshProUGUI>();
        _statusTMP.text      = "Select a query above  ·  or ask the agent";
        _statusTMP.fontSize  = 20f;
        _statusTMP.color     = SonoXRTheme.TXT_HINT;
        _statusTMP.alignment = TextAlignmentOptions.Center;
        statusGO.AddComponent<LayoutElement>().preferredHeight = 32f;

        // ── Response card — takes ALL remaining space; auto-size font to always fit ──
        // Using a plain card + auto-sizing TMP instead of ScrollRect avoids VR
        // scroll interaction issues. The text shrinks to fit rather than getting cut.
        _responseScroll = null; // not used; the one external reference is already null-checked
        var respCardGO  = new GameObject("ResponseCard");
        respCardGO.transform.SetParent(parent, false);
        var respCardImg = respCardGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(respCardImg, SonoXRTheme.BG_INSET, 10);
        var respCardLE = respCardGO.AddComponent<LayoutElement>();
        respCardLE.preferredHeight = 250f; // minimum guaranteed height
        respCardLE.flexibleHeight  = 1f;   // expands to fill any remaining space

        var respTextGO = new GameObject("ResponseTMP");
        respTextGO.transform.SetParent(respCardGO.transform, false);
        var respRT = respTextGO.AddComponent<RectTransform>();
        respRT.anchorMin = Vector2.zero; respRT.anchorMax = Vector2.one;
        respRT.offsetMin = new Vector2(10, 8); respRT.offsetMax = new Vector2(-10, -8);
        _responseTMP = respTextGO.AddComponent<TextMeshProUGUI>();
        _responseTMP.text               = "";
        _responseTMP.enableAutoSizing   = true;
        _responseTMP.fontSizeMin        = 18f;
        _responseTMP.fontSizeMax        = 26f;
        _responseTMP.color              = SonoXRTheme.TXT_WHITE;
        _responseTMP.alignment          = TextAlignmentOptions.TopLeft;
        _responseTMP.enableWordWrapping = true;
        _responseTMP.overflowMode       = TextOverflowModes.Overflow;

        // ── Bottom row: Read Aloud + Ask Agent side by side ───────────────────────
        var btnRowGO  = new GameObject("BtnRow");
        btnRowGO.transform.SetParent(parent, false);
        var btnRowHLG = btnRowGO.AddComponent<HorizontalLayoutGroup>();
        btnRowHLG.childAlignment         = TextAnchor.MiddleCenter;
        btnRowHLG.childForceExpandWidth  = true;
        btnRowHLG.childForceExpandHeight = true;
        btnRowHLG.spacing                = 6f;
        btnRowGO.AddComponent<LayoutElement>().preferredHeight = 62f;

        // Speak button
        var speakGO  = new GameObject("SpeakBtn");
        speakGO.transform.SetParent(btnRowGO.transform, false);
        var speakImg = speakGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(speakImg, SonoXRTheme.BTN_NRM, 18);
        var speakBtn = speakGO.AddComponent<Button>();
        speakBtn.colors        = BtnColors();
        speakBtn.targetGraphic = speakImg;
        speakBtn.onClick.AddListener(() => {
            if (Time.time - _lastClickTime < CLICK_COOLDOWN) return;
            _lastClickTime = Time.time;
            SpeakResponse();
        });

        var speakLblGO = new GameObject("Label");
        speakLblGO.transform.SetParent(speakGO.transform, false);
        var speakLblRT = speakLblGO.AddComponent<RectTransform>();
        speakLblRT.anchorMin = Vector2.zero; speakLblRT.anchorMax = Vector2.one;
        speakLblRT.offsetMin = Vector2.zero; speakLblRT.offsetMax = Vector2.zero;
        _speakBtnLabel = speakLblGO.AddComponent<TextMeshProUGUI>();
        _speakBtnLabel.text      = "▶  Read Aloud";
        _speakBtnLabel.fontSize  = 17f;
        _speakBtnLabel.fontStyle = FontStyles.Bold;
        _speakBtnLabel.color     = SonoXRTheme.TXT_WHITE;
        _speakBtnLabel.alignment = TextAlignmentOptions.Center;

        // Ask button
        var askGO  = new GameObject("AskBtn");
        askGO.transform.SetParent(btnRowGO.transform, false);
        _askBtnImg = askGO.AddComponent<Image>();
        SonoXRTheme.ApplyCard(_askBtnImg, SonoXRTheme.BTN_NRM, 18);
        var askBtn = askGO.AddComponent<Button>();
        askBtn.colors        = BtnColors();
        askBtn.targetGraphic = _askBtnImg;
        askBtn.onClick.AddListener(() => {
            if (!_recording && Time.time - _lastClickTime < CLICK_COOLDOWN) return;
            if (!_recording) _lastClickTime = Time.time;
            OnAskAgentClicked();
        });

        var askLblGO = new GameObject("Label");
        askLblGO.transform.SetParent(askGO.transform, false);
        var askLblRT = askLblGO.AddComponent<RectTransform>();
        askLblRT.anchorMin = Vector2.zero; askLblRT.anchorMax = Vector2.one;
        askLblRT.offsetMin = Vector2.zero; askLblRT.offsetMax = Vector2.zero;
        _askBtnLabel = askLblGO.AddComponent<TextMeshProUGUI>();
        _askBtnLabel.text      = "◉  Ask the Agent";
        _askBtnLabel.fontSize  = 17f;
        _askBtnLabel.fontStyle = FontStyles.Bold;
        _askBtnLabel.color     = SonoXRTheme.TXT_WHITE;
        _askBtnLabel.alignment = TextAlignmentOptions.Center;

        // ── Deepgram TTS + STT ─────────────────────────────────────────────────────
        var ttsGO = new GameObject("DeepgramTTS");
        ttsGO.transform.SetParent(transform, false);
        _tts = ttsGO.AddComponent<DeepgramTTS>();

        var sttGO = new GameObject("DeepgramSTT");
        sttGO.transform.SetParent(transform, false);
        _stt = sttGO.AddComponent<DeepgramSTT>();
    }

    // ── Preset queries ────────────────────────────────────────────────────────────

    string[] Prompts(PatientBundleMeta m)
    {
        if (m == null) return new[] { "No patient data available.", "", "", "" };

        string uncName   = m.uncertainty_region?.region_name ?? "basal";
        string uncReason = m.uncertainty_region?.reason ?? "limited acoustic window in apical views";

        return new[]
        {
            $"Explain what the 3D reconstruction of this patient's left ventricle tells us. " +
            $"EF={m.EF_pct:F0}%, EDV={m.EDV_mL:F0}mL, ESV={m.ESV_mL:F0}mL, quality={m.image_quality}. " +
            $"Uncertainty in {uncName}: {uncReason}",

            "In plain language, what does ejection fraction measure and why does it matter " +
            "for understanding heart function?",

            $"Why is the {uncName} region uncertain " +
            $"in apical ultrasound reconstructions? Explain for a non-specialist. " +
            $"Context: {uncReason}",

            $"This patient has EF={m.EF_pct:F0}%. Is this normal, mildly reduced, or severely reduced " +
            $"by standard clinical thresholds, and what does that typically indicate about cardiac function?"
        };
    }

    void OnPresetClicked(int idx)
    {
        // Guard: OVRUIPointer can fire multiple events per trigger press
        if (_queryInProgress) return;
        if (Time.time - _lastClickTime < CLICK_COOLDOWN) return;
        _lastClickTime = Time.time;

        if (_meta == null)
        {
            SetStatus("No patient loaded.");
            return;
        }
        string[] prompts = Prompts(_meta);
        if (idx < 0 || idx >= prompts.Length) return;
        StartCoroutine(RunQuery(idx, prompts[idx]));
    }

    // ── Voice agent (Ask the Agent) ───────────────────────────────────────────────

    void OnAskAgentClicked()
    {
        if (_stt == null) return;

        if (!_recording)
        {
            // Start recording
            _tts?.StopSpeaking();
            _stt.StartRecording();
            _recording = true;
            _recordingStartTime = Time.time;
            if (_askBtnLabel != null) _askBtnLabel.text = "■  Stop · Send to Agent";
            if (_askBtnImg   != null) _askBtnImg.color  = C_BTN_REC;
            SetStatus("Listening... tap 'Stop' when done speaking.");
        }
        else
        {
            // Guard: ignore stop if not enough audio has been captured yet.
            // OVRUIPointer can fire start+stop within 30ms — MIN_RECORD_SECS blocks that.
            if (Time.time - _recordingStartTime < MIN_RECORD_SECS)
            {
                Debug.Log($"[ClaudeAgentPanel] Stop ignored — only " +
                          $"{Time.time - _recordingStartTime:F2}s recorded (min={MIN_RECORD_SECS}s)");
                return;
            }

            // Stop and transcribe
            _recording = false;
            if (_askBtnLabel != null) _askBtnLabel.text = "Transcribing...";
            if (_askBtnImg   != null) _askBtnImg.color  = C_BTN_NRM;
            SetStatus("Transcribing your question...");

            _stt.StopAndTranscribe(
                onTranscript: transcript =>
                {
                    SetStatus($"You: \"{transcript}\"");
                    StartCoroutine(RunVoiceQuery(transcript));
                },
                onError: err =>
                {
                    SetStatus($"Mic error: {err}");
                    if (_askBtnLabel != null) _askBtnLabel.text = "◉  Ask the Agent";
                }
            );
        }
    }

    IEnumerator RunVoiceQuery(string userQuestion)
    {
        if (_responseTMP != null) _responseTMP.text = "";
        _lastResponse = null;

        if (_dotsCoroutine != null) StopCoroutine(_dotsCoroutine);
        _dotsCoroutine = StartCoroutine(AnimateDots());

        // Build a context-aware prompt combining patient data + user question
        string contextPrompt = _meta != null
            ? $"Patient context: EF={_meta.EF_pct:F0}%, EDV={_meta.EDV_mL:F0}mL, " +
              $"ESV={_meta.ESV_mL:F0}mL, quality={_meta.image_quality}. " +
              $"User question: {userQuestion}"
            : userQuestion;

        var client = AnthropicClient.Instance;
        if (client == null)
        {
            ShowError("AI unavailable — no AnthropicClient found.");
            if (_askBtnLabel != null) _askBtnLabel.text = "◉  Ask the Agent";
            yield break;
        }

        bool   done     = false;
        string response = null;
        string error    = null;

        client.SendMessage(SYSTEM_PROMPT, contextPrompt,
            result => { response = result; done = true; },
            err    => { error    = err;    done = true; });

        while (!done) yield return null;

        if (_dotsCoroutine != null) { StopCoroutine(_dotsCoroutine); _dotsCoroutine = null; }
        if (_askBtnLabel != null) _askBtnLabel.text = "◉  Ask the Agent";

        if (!string.IsNullOrEmpty(error))
        {
            ShowError($"Claude error: {error}");
        }
        else if (!string.IsNullOrEmpty(response))
        {
            _lastResponse = response;
            ShowResponse(response);
            SpeakResponse();
        }
    }

    // ── Query pipeline ────────────────────────────────────────────────────────────

    IEnumerator RunQuery(int queryIdx, string userPrompt)
    {
        _queryInProgress = true;
        SetStatus("Thinking...");
        if (_responseTMP != null) _responseTMP.text = "";
        _lastResponse = null;

        if (_dotsCoroutine != null) StopCoroutine(_dotsCoroutine);
        _dotsCoroutine = StartCoroutine(AnimateDots());

        // Try cache first
        string cacheFile = $"{_pid}_q{queryIdx}.txt";
        string cachePath = System.IO.Path.Combine(
            Application.streamingAssetsPath, "claude_cache", cacheFile);
        string cacheUrl  = FileUri(cachePath);

        bool cacheHit = false;
        using (var req = UnityWebRequest.Get(cacheUrl))
        {
            yield return req.SendWebRequest();
            if (req.result == UnityWebRequest.Result.Success &&
                !string.IsNullOrEmpty(req.downloadHandler.text))
            {
                cacheHit      = true;
                _lastResponse = req.downloadHandler.text;
            }
        }

        if (cacheHit)
        {
            if (_dotsCoroutine != null) { StopCoroutine(_dotsCoroutine); _dotsCoroutine = null; }
            ShowResponse(_lastResponse);
            // Auto-speak only if not already playing something
            if (_tts != null && !_tts.IsSpeaking) SpeakResponse();
            _queryInProgress = false;
            yield break;
        }

        // Call AnthropicClient
        bool done = false;
        string response = null;
        string error    = null;

        var client = AnthropicClient.Instance;
        if (client == null)
        {
            ShowError("AI unavailable — API key not configured");
            _queryInProgress = false;
            yield break;
        }

        client.SendMessage(SYSTEM_PROMPT, userPrompt,
            result => { response = result; done = true; },
            err    => { error    = err;    done = true; });

        while (!done) yield return null;

        if (_dotsCoroutine != null) { StopCoroutine(_dotsCoroutine); _dotsCoroutine = null; }
        _queryInProgress = false;

        if (!string.IsNullOrEmpty(error))
        {
            ShowError($"Couldn't reach Claude. {error}");
        }
        else if (!string.IsNullOrEmpty(response))
        {
            _lastResponse = response;
            ShowResponse(response);
            // Auto-speak only if not already playing something
            if (_tts != null && !_tts.IsSpeaking) SpeakResponse();
        }
    }

    void ShowResponse(string text)
    {
        SetStatus("");
        if (_responseTMP != null) _responseTMP.text = text;
        if (_responseScroll != null) _responseScroll.verticalNormalizedPosition = 1f;
    }

    void ShowError(string msg)
    {
        SetStatus(msg);
        if (_responseTMP != null) _responseTMP.text = "";
    }

    void SetStatus(string msg)
    {
        if (_statusTMP != null) _statusTMP.text = msg;
    }

    IEnumerator AnimateDots()
    {
        int count = 0;
        while (true)
        {
            count = (count + 1) % 4;
            SetStatus("Thinking" + new string('.', count));
            yield return new WaitForSeconds(0.4f);
        }
    }

    // ── Voice (Deepgram TTS) ──────────────────────────────────────────────────────

    void SpeakResponse()
    {
        if (string.IsNullOrEmpty(_lastResponse))
        {
            SetStatus("Nothing to read — run a query first.");
            return;
        }

        if (_tts == null) return;

        // If already speaking, stop and don't restart (button acts as toggle stop)
        if (_tts.IsSpeaking)
        {
            _tts.StopSpeaking();
            if (_speakBtnLabel != null) _speakBtnLabel.text = "▶  Read Aloud";
            SetStatus("Stopped.");
            return;
        }

        SetStatus("Speaking...");
        if (_speakBtnLabel != null) _speakBtnLabel.text = "■  Stop";

        _tts.Speak(
            _lastResponse,
            onDone:  () => {
                SetStatus("");
                if (_speakBtnLabel != null) _speakBtnLabel.text = "▶  Read Aloud";
            },
            onError: err => {
                SetStatus($"Voice error: {err}");
                if (_speakBtnLabel != null) _speakBtnLabel.text = "▶  Read Aloud";
            }
        );
    }

    // ── Helpers ───────────────────────────────────────────────────────────────────

    static ColorBlock BtnColors() => SonoXRTheme.BtnColors();

    static string FileUri(string path)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        return path;
#else
        return "file://" + path.Replace("\\", "/");
#endif
    }

}
