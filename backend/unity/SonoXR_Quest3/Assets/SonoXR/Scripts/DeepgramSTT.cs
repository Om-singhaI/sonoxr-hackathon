// DeepgramSTT.cs
// Captures microphone audio on Quest 3 and transcribes it via Deepgram Listen API.
// Usage: StartRecording() → StopAndTranscribe(onTranscript, onError)

using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

public class DeepgramSTT : MonoBehaviour
{
    // ── Constants ─────────────────────────────────────────────────────────────────
    const string API_URL      = "https://api.deepgram.com/v1/listen";
    const int    MIC_RATE     = 16000;
    const int    MAX_SECS     = 30;
    const int    TIMEOUT      = 20;

    // ── State ─────────────────────────────────────────────────────────────────────
    AudioClip _micClip;
    string    _micDevice;
    bool      _recording;

    public bool IsRecording => _recording;

    // ── Lifecycle ─────────────────────────────────────────────────────────────────

    void Awake()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        // Request mic permission early so the dialog appears before the user taps.
        // Permission is async — we re-check Microphone.devices in StartRecording().
        if (!UnityEngine.Android.Permission.HasUserAuthorizedPermission(
                UnityEngine.Android.Permission.Microphone))
        {
            UnityEngine.Android.Permission.RequestUserPermission(
                UnityEngine.Android.Permission.Microphone);
        }
#endif
        RefreshMicDevice();
    }

    void RefreshMicDevice()
    {
        _micDevice = Microphone.devices.Length > 0 ? Microphone.devices[0] : null;
        if (_micDevice == null)
            Debug.Log("[DeepgramSTT] No mic device yet (permission may still be pending).");
        else
            Debug.Log($"[DeepgramSTT] Mic device: {_micDevice}");
    }

    // ── Public API ────────────────────────────────────────────────────────────────

    public void StartRecording()
    {
        if (_recording)
        {
            Debug.LogWarning("[DeepgramSTT] Already recording.");
            return;
        }

        // Re-check devices in case permission was granted after Awake()
        if (_micDevice == null) RefreshMicDevice();

        if (_micDevice == null)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            // Permission might still be pending — request again
            UnityEngine.Android.Permission.RequestUserPermission(
                UnityEngine.Android.Permission.Microphone);
#endif
            Debug.LogWarning("[DeepgramSTT] No microphone available. " +
                             "Grant Microphone permission in Settings > Apps > SonoXR > Permissions.");
            return;
        }
        _micClip  = Microphone.Start(_micDevice, false, MAX_SECS, MIC_RATE);
        _recording = true;
        Debug.Log("[DeepgramSTT] Recording started.");
    }

    /// <summary>Stops recording and sends audio to Deepgram STT. Returns transcript via callback.</summary>
    public void StopAndTranscribe(Action<string> onTranscript, Action<string> onError)
    {
        if (!_recording)
        {
            onError?.Invoke("Not recording.");
            return;
        }
        int samplePos = Microphone.GetPosition(_micDevice);
        Microphone.End(_micDevice);
        _recording = false;
        Debug.Log($"[DeepgramSTT] Recording stopped — {samplePos} samples ({samplePos / (float)MIC_RATE:F1}s)");

        if (samplePos < MIC_RATE / 2)   // less than 0.5s of audio
        {
            onError?.Invoke("Recording too short — speak for at least 0.5 seconds.");
            return;
        }
        StartCoroutine(CoTranscribe(_micClip, samplePos, onTranscript, onError));
    }

    // ── Coroutine ─────────────────────────────────────────────────────────────────

    IEnumerator CoTranscribe(AudioClip clip, int sampleCount, Action<string> onTranscript, Action<string> onError)
    {
        string apiKey = AnthropicClient.DeepgramKey;
        if (string.IsNullOrEmpty(apiKey))
        {
            onError?.Invoke("Deepgram key not configured — add deepgram_api_key to sonoxr_config.json");
            yield break;
        }

        // Encode captured samples as WAV
        float[] samples = new float[sampleCount];
        clip.GetData(samples, 0);
        byte[] wav = EncodeWav(samples, MIC_RATE);

        Debug.Log($"[DeepgramSTT] Sending {wav.Length} WAV bytes to Deepgram...");

        string url = $"{API_URL}?model=nova-2&language=en&smart_format=true&punctuate=true";

        using var req = new UnityWebRequest(url, "POST");
        req.uploadHandler   = new UploadHandlerRaw(wav);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.timeout         = TIMEOUT;
        req.SetRequestHeader("Authorization", $"Token {apiKey}");
        req.SetRequestHeader("Content-Type",  "audio/wav");

        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            string detail = req.responseCode > 0 ? $"HTTP {req.responseCode}: {req.error}" : req.error;
            Debug.LogWarning($"[DeepgramSTT] API error: {detail}");
            onError?.Invoke($"Transcription failed: {detail}");
            yield break;
        }

        string raw = req.downloadHandler.text;
        Debug.Log($"[DeepgramSTT] Response: {raw.Substring(0, Mathf.Min(200, raw.Length))}");

        DGListenResponse resp = null;
        try { resp = JsonUtility.FromJson<DGListenResponse>(raw); }
        catch (Exception e) { onError?.Invoke($"Parse error: {e.Message}"); yield break; }

        string transcript = resp?.results?.channels != null && resp.results.channels.Length > 0 &&
                            resp.results.channels[0].alternatives != null &&
                            resp.results.channels[0].alternatives.Length > 0
            ? resp.results.channels[0].alternatives[0].transcript
            : null;

        if (string.IsNullOrWhiteSpace(transcript))
        {
            onError?.Invoke("No speech detected — please try again.");
            yield break;
        }

        Debug.Log($"[DeepgramSTT] Transcript: \"{transcript}\"");
        onTranscript?.Invoke(transcript);
    }

    // ── WAV encoder ───────────────────────────────────────────────────────────────

    static byte[] EncodeWav(float[] samples, int sampleRate)
    {
        int dataLen = samples.Length * 2;           // 16-bit = 2 bytes per sample
        byte[] wav  = new byte[44 + dataLen];
        int    p    = 0;

        // RIFF header
        Str(wav, ref p, "RIFF");
        I32(wav, ref p, 36 + dataLen);
        Str(wav, ref p, "WAVE");
        // fmt chunk
        Str(wav, ref p, "fmt ");
        I32(wav, ref p, 16);                        // chunk size
        I16(wav, ref p, 1);                         // PCM
        I16(wav, ref p, 1);                         // mono
        I32(wav, ref p, sampleRate);
        I32(wav, ref p, sampleRate * 2);            // byte rate
        I16(wav, ref p, 2);                         // block align
        I16(wav, ref p, 16);                        // bits per sample
        // data chunk
        Str(wav, ref p, "data");
        I32(wav, ref p, dataLen);
        // PCM samples
        for (int i = 0; i < samples.Length; i++)
        {
            short s = (short)(Mathf.Clamp(samples[i], -1f, 1f) * 32767f);
            wav[p++] = (byte)(s & 0xFF);
            wav[p++] = (byte)(s >> 8);
        }
        return wav;
    }

    static void Str(byte[] b, ref int p, string s) { for (int i = 0; i < s.Length; i++) b[p++] = (byte)s[i]; }
    static void I32(byte[] b, ref int p, int  v)   { b[p++]=(byte)v; b[p++]=(byte)(v>>8); b[p++]=(byte)(v>>16); b[p++]=(byte)(v>>24); }
    static void I16(byte[] b, ref int p, short v)  { b[p++]=(byte)v; b[p++]=(byte)(v>>8); }

    // ── DTOs ─────────────────────────────────────────────────────────────────────
    [Serializable] class DGListenResponse { public DGResults results; }
    [Serializable] class DGResults        { public DGChannel[] channels; }
    [Serializable] class DGChannel        { public DGAlt[] alternatives; }
    [Serializable] class DGAlt            { public string transcript; public float confidence; }
}
