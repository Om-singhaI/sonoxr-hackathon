// AnthropicClient.cs
// Singleton MonoBehaviour that sends messages to the Anthropic Claude API.
// API key read from StreamingAssets/sonoxr_config.json at startup.
// {"anthropic_api_key": "sk-ant-..."}

using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

public class AnthropicClient : MonoBehaviour
{
    // ── Singleton ─────────────────────────────────────────────────────────────────
    static AnthropicClient _inst;
    public static AnthropicClient Instance => _inst;

    // ── Constants ─────────────────────────────────────────────────────────────────
    const string API_URL  = "https://api.anthropic.com/v1/messages";
    const string MODEL    = "claude-sonnet-4-6";
    const int    MAX_TOK  = 400;
    const float  TIMEOUT  = 12f;
    const string API_VER  = "2023-06-01";

    // ── State ─────────────────────────────────────────────────────────────────────
    string _apiKey;
    string _deepgramKey;
    bool   _keyLoaded;
    bool   _keyValid;

    public static string DeepgramKey => _inst?._deepgramKey;

    // ── DTOs ─────────────────────────────────────────────────────────────────────

    [Serializable] class ApiRequest  { public string model; public string system; public int max_tokens; public ApiMessage[] messages; }
    [Serializable] class ApiMessage  { public string role; public string content; }
    [Serializable] class ApiResponse { public ApiContent[] content; }
    [Serializable] class ApiContent  { public string type; public string text; }
    [Serializable] class SonoXRConfig{ public string anthropic_api_key; public string deepgram_api_key; }

    // ── Lifecycle ─────────────────────────────────────────────────────────────────

    void Awake()
    {
        if (_inst != null && _inst != this) { Destroy(gameObject); return; }
        _inst = this;
        DontDestroyOnLoad(gameObject);
        StartCoroutine(LoadConfig());
    }

    IEnumerator LoadConfig()
    {
        string configPath = System.IO.Path.Combine(Application.streamingAssetsPath, "sonoxr_config.json");
        string url        = FileUri(configPath);

        using var req = UnityWebRequest.Get(url);
        req.timeout = 5;
        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogWarning($"[AnthropicClient] sonoxr_config.json not found at {url}. " +
                             "AI features will be unavailable.");
            _keyLoaded = true;
            _keyValid  = false;
            yield break;
        }

        SonoXRConfig cfg = null;
        try { cfg = JsonUtility.FromJson<SonoXRConfig>(req.downloadHandler.text); }
        catch (Exception e) { Debug.LogWarning($"[AnthropicClient] Config parse error: {e.Message}"); }

        if (cfg != null && !string.IsNullOrEmpty(cfg.anthropic_api_key) &&
            cfg.anthropic_api_key.StartsWith("sk-ant"))
        {
            _apiKey   = cfg.anthropic_api_key;
            _keyValid = true;
            Debug.Log("[AnthropicClient] Claude API key loaded.");
        }
        else
        {
            Debug.LogWarning("[AnthropicClient] Claude API key missing or invalid in sonoxr_config.json.");
            _keyValid = false;
        }

        if (cfg != null && !string.IsNullOrEmpty(cfg.deepgram_api_key) &&
            !cfg.deepgram_api_key.StartsWith("PASTE"))
        {
            _deepgramKey = cfg.deepgram_api_key;
            Debug.Log("[AnthropicClient] Deepgram API key loaded.");
        }
        else
        {
            Debug.Log("[AnthropicClient] Deepgram key not configured — voice synthesis will be unavailable.");
        }
        _keyLoaded = true;
    }

    // ── Public API ────────────────────────────────────────────────────────────────

    /// <summary>
    /// Sends a message to the Anthropic API.
    /// onDone is called on the main thread with the response text.
    /// onError is called on the main thread with an error description.
    /// </summary>
    public void SendMessage(string systemPrompt, string userMessage,
                            Action<string> onDone, Action<string> onError)
    {
        StartCoroutine(CoSendMessage(systemPrompt, userMessage, onDone, onError));
    }

    IEnumerator CoSendMessage(string systemPrompt, string userMessage,
                               Action<string> onDone, Action<string> onError)
    {
        // Wait for config load
        float deadline = Time.time + 8f;
        while (!_keyLoaded && Time.time < deadline) yield return null;

        if (!_keyValid)
        {
            onError?.Invoke("AI unavailable — API key not configured. " +
                           "Add your key to StreamingAssets/sonoxr_config.json.");
            yield break;
        }

        // Build request body
        var requestObj = new ApiRequest
        {
            model      = MODEL,
            system     = systemPrompt,
            max_tokens = MAX_TOK,
            messages   = new[] { new ApiMessage { role = "user", content = userMessage } }
        };
        string json = JsonUtility.ToJson(requestObj);
        byte[] body = Encoding.UTF8.GetBytes(json);

        using var req = new UnityWebRequest(API_URL, "POST");
        req.uploadHandler   = new UploadHandlerRaw(body);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.timeout         = (int)TIMEOUT;
        req.SetRequestHeader("Content-Type",      "application/json");
        req.SetRequestHeader("x-api-key",         _apiKey);
        req.SetRequestHeader("anthropic-version", API_VER);

        float startTime = Time.time;
        var op = req.SendWebRequest();
        while (!op.isDone)
        {
            if (Time.time - startTime > TIMEOUT)
            {
                req.Abort();
                onError?.Invoke("Request timed out after 12 seconds.");
                yield break;
            }
            yield return null;
        }

        if (req.result != UnityWebRequest.Result.Success)
        {
            string detail = req.responseCode > 0
                ? $"HTTP {req.responseCode}: {req.error}"
                : req.error;
            Debug.LogWarning($"[AnthropicClient] API error: {detail}");
            onError?.Invoke($"API error: {detail}");
            yield break;
        }

        // Parse response
        string responseText = null;
        try
        {
            var resp = JsonUtility.FromJson<ApiResponse>(req.downloadHandler.text);
            if (resp?.content != null && resp.content.Length > 0)
            {
                foreach (var c in resp.content)
                {
                    if (c.type == "text" && !string.IsNullOrEmpty(c.text))
                    {
                        responseText = c.text;
                        break;
                    }
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[AnthropicClient] Response parse error: {e.Message}\n" +
                             $"Raw: {req.downloadHandler.text}");
            onError?.Invoke("Failed to parse AI response.");
            yield break;
        }

        if (string.IsNullOrEmpty(responseText))
        {
            Debug.LogWarning($"[AnthropicClient] Empty response. Raw: {req.downloadHandler.text}");
            onError?.Invoke("AI returned an empty response.");
            yield break;
        }

        Debug.Log($"[AnthropicClient] Response received ({responseText.Length} chars).");
        onDone?.Invoke(responseText);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────────

    static string FileUri(string path)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        return path;
#else
        return "file://" + path.Replace("\\", "/");
#endif
    }
}
