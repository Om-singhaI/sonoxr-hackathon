// DeepgramTTS.cs
// Converts text to speech using Deepgram's Aura neural TTS API.
// Requests raw linear16 PCM, builds an AudioClip, and plays it via AudioSource.
// Stop fix: uses WaitForSeconds(clip.length) — polling isPlaying exits one frame too early.

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public class DeepgramTTS : MonoBehaviour
{
    // ── Constants ─────────────────────────────────────────────────────────────────
    const string API_URL    = "https://api.deepgram.com/v1/speak";
    const string VOICE      = "aura-asteria-en";   // female, natural English voice
    const int    SAMPLE_RATE = 24000;              // Deepgram linear16 supports: 8000, 16000, 24000 only
    const int    TIMEOUT     = 30;

    // ── State ─────────────────────────────────────────────────────────────────────
    AudioSource _audio;
    bool        _speaking;

    public bool IsSpeaking => _speaking;

    // ── Lifecycle ─────────────────────────────────────────────────────────────────

    void Awake()
    {
        _audio             = gameObject.AddComponent<AudioSource>();
        _audio.playOnAwake = false;
        _audio.spatialBlend = 0f;   // 2D — comes from the headset speakers, not world-space
        _audio.volume      = 1f;
    }

    // ── Public API ────────────────────────────────────────────────────────────────

    /// <summary>Speak text via Deepgram neural TTS. Stops any in-progress speech first.</summary>
    public void Speak(string text, Action onDone = null, Action<string> onError = null)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        StopSpeaking();
        StartCoroutine(CoSpeak(text, onDone, onError));
    }

    public void StopSpeaking()
    {
        StopAllCoroutines();
        if (_audio.isPlaying) _audio.Stop();
        _speaking = false;
    }

    // ── Coroutine ─────────────────────────────────────────────────────────────────

    IEnumerator CoSpeak(string text, Action onDone, Action<string> onError)
    {
        string apiKey = AnthropicClient.DeepgramKey;
        if (string.IsNullOrEmpty(apiKey))
        {
            onError?.Invoke("Deepgram key not configured — add deepgram_api_key to sonoxr_config.json");
            yield break;
        }

        _speaking = true;
        Debug.Log($"[DeepgramTTS] Requesting speech ({text.Length} chars)...");

        string url = $"{API_URL}?model={VOICE}&encoding=linear16&sample_rate={SAMPLE_RATE}";
        // Use JsonUtility so Claude responses with **, backticks, etc. are safe
        byte[] bodyBytes = System.Text.Encoding.UTF8.GetBytes(
            JsonUtility.ToJson(new DGSpeakRequest { text = text }));

        using var req = new UnityWebRequest(url, "POST");
        req.uploadHandler   = new UploadHandlerRaw(bodyBytes);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.timeout         = TIMEOUT;
        req.SetRequestHeader("Authorization", $"Token {apiKey}");
        req.SetRequestHeader("Content-Type",  "application/json");

        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            _speaking = false;
            string detail = req.responseCode > 0
                ? $"HTTP {req.responseCode}: {req.error}"
                : req.error;
            Debug.LogWarning($"[DeepgramTTS] API error: {detail}");
            onError?.Invoke($"Voice synthesis failed: {detail}");
            yield break;
        }

        byte[] pcm = req.downloadHandler.data;
        if (pcm == null || pcm.Length < 2)
        {
            _speaking = false;
            onError?.Invoke("Deepgram returned empty audio.");
            yield break;
        }

        Debug.Log($"[DeepgramTTS] Received {pcm.Length} PCM bytes → creating AudioClip...");

        // Convert signed 16-bit little-endian PCM → float samples
        int     sampleCount = pcm.Length / 2;
        float[] samples     = new float[sampleCount];
        for (int i = 0; i < sampleCount; i++)
        {
            short s    = (short)(pcm[i * 2] | (pcm[i * 2 + 1] << 8));
            samples[i] = s / 32768f;
        }

        var clip = AudioClip.Create("DeepgramSpeech", sampleCount, 1, SAMPLE_RATE, false);
        clip.SetData(samples, 0);

        _audio.clip = clip;
        _audio.Play();

        float duration = clip.length;
        Debug.Log($"[DeepgramTTS] Playing {duration:F1}s of speech.");

        // WaitForSeconds is reliable — polling isPlaying can exit one frame early
        // before Unity's audio subsystem registers the clip as playing.
        yield return new WaitForSeconds(duration + 0.15f);

        _speaking = false;
        onDone?.Invoke();
    }

    // ── DTO ───────────────────────────────────────────────────────────────────────
    [System.Serializable] class DGSpeakRequest { public string text; }
}
