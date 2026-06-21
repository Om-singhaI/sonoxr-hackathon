// PatientBundleLoader.cs
// Loads per-patient CAMUS data bundles from StreamingAssets at runtime.
//
// Bundle layout (built by scripts/build_camus_bundle.py):
//   StreamingAssets/patient_bundles/index.json
//   StreamingAssets/patient_bundles/<pid>/meta.json
//   StreamingAssets/patient_bundles/<pid>/scan_4ch.png
//   StreamingAssets/patient_bundles/<pid>/scan_2ch.png
//   StreamingAssets/patient_bundles/<pid>/lv_ed.glb
//
// Setup:
//   1. Copy frontend/patient_bundles/ → Assets/StreamingAssets/patient_bundles/
//   2. Attach this script to a GameObject in the scene.
//   3. Drag your HeartHUD into the 'hud' field.
//   4. Optionally drag your Heart root transform into 'heartMeshRoot' for GLB swapping.
//   5. Call NextPatient() / PrevPatient() from UI buttons or a gesture trigger.
//
// On Start: auto-loads the hero patient (index.json "hero" field).
// All IO uses UnityWebRequest — works on both editor and Quest 3 (jar:// assets).

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using GLTFast;

// ── Data transfer objects ───────────────────────────────────────────────────────

[Serializable]
public class PatientBundleMeta
{
    public string patient;
    public string image_quality;
    public float  EDV_mL;
    public float  ESV_mL;
    public float  EF_pct;
    public float  reference_ef;
    public float  ef_vs_reference_pp;
    public string narration;
    public string honesty_note;
    public string citation;
    public string data_source;
    public string method;
    public string scan_4ch;
    public string scan_2ch;
    public string glb_ed;
    public UncertaintyRegion uncertainty_region;
}

[Serializable]
public class UncertaintyRegion
{
    public string region_name;
    public string fraction_of_lv;
    public string reason;
    public int[]  disc_range;
}

[Serializable]
class BundleIndex
{
    public List<string> patients;
    public string       hero;
}

public class PatientBundleData
{
    public PatientBundleMeta meta;
    public Texture2D         scan4ch;
    public Texture2D         scan2ch;
    public GameObject        glbRoot;  // instantiated ED mesh — may be null if GLB load fails
}

// ── Loader MonoBehaviour ────────────────────────────────────────────────────────

public class PatientBundleLoader : MonoBehaviour
{
    public event Action<PatientBundleData, int, int> OnPatientLoaded;

    [Header("UI — receives data when a patient loads")]
    public HeartHUD hud;

    [Header("Analysis-room scene components — drag to wire (all optional)")]
    public HeartVisuals   heartVisuals;
    public ScanPanelGroup scanPanels;
    public AnalysisPanel  analysisPanel;
    public LVLabels       lvLabels;

    [Header("Heart scene root — new GLB mesh is parented here (optional)")]
    public Transform heartMeshRoot;

    // Runtime state
    List<string>  _patients;
    int           _index = -1;
    bool          _loading;        // informational only — NOT used to gate navigation
    int           _gen    = 0;     // incremented on every new load; stale coroutines abort when gen changes
    string        _bundleRoot;
    GameObject    _currentGlb;

    // ── Unity lifecycle ──────────────────────────────────────────────────────────

    void Start()
    {
        _bundleRoot = System.IO.Path.Combine(Application.streamingAssetsPath, "patient_bundles");
        StartCoroutine(CoLoadIndex());
    }

    // ── Public patient-navigation API ────────────────────────────────────────────

    public int  PatientCount  => _patients?.Count ?? 0;
    public int  CurrentIndex  => _index;
    public bool IsLoading     => _loading;

    public void NextPatient()
    {
        if (!CanNavigate()) { Debug.LogWarning("[PBL] NextPatient: index not ready"); return; }
        int next = (_index + 1) % _patients.Count;
        Debug.Log($"[PBL] NextPatient → {next} ({_patients[next]})");
        StartCoroutine(CoLoadPatient(_patients[next], next));
    }

    public void PrevPatient()
    {
        if (!CanNavigate()) { Debug.LogWarning("[PBL] PrevPatient: index not ready"); return; }
        int prev = (_index - 1 + _patients.Count) % _patients.Count;
        Debug.Log($"[PBL] PrevPatient → {prev} ({_patients[prev]})");
        StartCoroutine(CoLoadPatient(_patients[prev], prev));
    }

    public void LoadByPid(string pid)
    {
        StartCoroutine(CoLoadByPidDeferred(pid));
    }

    IEnumerator CoLoadByPidDeferred(string pid)
    {
        float deadline = Time.time + 15f;
        while (_patients == null && Time.time < deadline) yield return null;
        if (_patients == null) { Debug.LogError($"[PBL] Timeout waiting for index"); yield break; }

        // No longer waits for _loading — generation counter handles concurrent loads.
        int idx = _patients.IndexOf(pid);
        if (idx < 0) { Debug.LogWarning($"[PBL] Unknown pid: {pid}"); yield break; }
        yield return StartCoroutine(CoLoadPatient(pid, idx));
    }

    // Navigation is gated only on whether the index has loaded — NOT on _loading.
    bool CanNavigate() => _patients != null && _patients.Count > 0;

    // ── Coroutines ───────────────────────────────────────────────────────────────

    IEnumerator CoLoadIndex()
    {
        string url = FileUri(System.IO.Path.Combine(_bundleRoot, "index.json"));
        using var req = UnityWebRequest.Get(url);
        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError($"[PatientBundleLoader] index.json not found at {url}\n" +
                           "Copy frontend/patient_bundles/ into Assets/StreamingAssets/patient_bundles/");
            yield break;
        }

        var index = JsonUtility.FromJson<BundleIndex>(req.downloadHandler.text);
        _patients = index?.patients ?? new List<string>();

        if (_patients.Count == 0) { Debug.LogError("[PatientBundleLoader] index.json lists no patients."); yield break; }

        // Load the hero patient first.
        string hero = index?.hero;
        int heroIdx = string.IsNullOrEmpty(hero) ? 0 : Mathf.Max(0, _patients.IndexOf(hero));
        yield return StartCoroutine(CoLoadPatient(_patients[heroIdx], heroIdx));
    }

    IEnumerator CoLoadPatient(string pid, int index)
    {
        // Claim this generation. Any older coroutine watching _gen will abort.
        int myGen = ++_gen;
        _loading = true;
        Debug.Log($"[PBL] CoLoadPatient gen={myGen} pid={pid}");

        string dir = System.IO.Path.Combine(_bundleRoot, pid);

        // 1 — meta.json
        PatientBundleMeta meta = null;
        yield return StartCoroutine(FetchJson(dir, "meta.json", t =>
            meta = JsonUtility.FromJson<PatientBundleMeta>(t)));

        if (myGen != _gen) { _loading = false; yield break; }   // superseded
        if (meta == null)  { _loading = false;
            Debug.LogError($"[PBL] meta.json missing for {pid}"); yield break; }

        // 2 — scan PNGs
        Texture2D scan4ch = null, scan2ch = null;
        yield return StartCoroutine(FetchTexture(dir, meta.scan_4ch ?? "scan_4ch.png", t => scan4ch = t));
        if (myGen != _gen) { _loading = false; yield break; }

        yield return StartCoroutine(FetchTexture(dir, meta.scan_2ch ?? "scan_2ch.png", t => scan2ch = t));
        if (myGen != _gen) { _loading = false; yield break; }

        // Commit — navigation is now free for this or newer loads
        _index   = index;
        _loading = false;
        Debug.Log($"[PBL] Ready gen={myGen} {pid} EF={meta.EF_pct:F1}%");

        var data = new PatientBundleData { meta = meta, scan4ch = scan4ch, scan2ch = scan2ch };
        try { if (hud           != null) hud.LoadFromBundle(data, _index + 1, _patients.Count); }
        catch (Exception e) { Debug.LogWarning($"[PBL] hud: {e.Message}"); }
        try { if (heartVisuals  != null) heartVisuals.LoadFromBundle(data); }
        catch (Exception e) { Debug.LogWarning($"[PBL] hv: {e.Message}"); }
        try { if (scanPanels    != null) scanPanels.LoadFromBundle(data); }
        catch (Exception e) { Debug.LogWarning($"[PBL] sp: {e.Message}"); }
        try { if (analysisPanel != null) analysisPanel.LoadFromBundle(data); }
        catch (Exception e) { Debug.LogWarning($"[PBL] ap: {e.Message}"); }
        try { if (lvLabels      != null) lvLabels.LoadFromBundle(data); }
        catch (Exception e) { Debug.LogWarning($"[PBL] lv: {e.Message}"); }
        try { OnPatientLoaded?.Invoke(data, _index + 1, _patients.Count); }
        catch (Exception e) { Debug.LogWarning($"[PBL] evt: {e.Message}"); }

        // 3 — GLB (fire-and-forget background load — never blocks navigation)
        if (!string.IsNullOrEmpty(meta.glb_ed))
            StartCoroutine(LoadGlbBackground(pid, dir, meta.glb_ed, myGen));
    }

    // Loads a GLB in the background and swaps _currentGlb when done.
    // Navigation is never blocked by this — _loading is already false when this runs.
    IEnumerator LoadGlbBackground(string pid, string dir, string filename, int gen)
    {
        Debug.Log($"[PBL] GLB loading gen={gen} {pid}");
        GameObject glbRoot = null;
        yield return StartCoroutine(LoadGlb(dir, filename, go => glbRoot = go));

        if (glbRoot == null)
        {
            Debug.LogWarning($"[PBL] GLB load failed: {pid}/{filename}");
            yield break;
        }
        if (gen != _gen)
        {
            // A newer load claimed _gen — discard this mesh.
            Debug.Log($"[PBL] Discarding stale GLB gen={gen} (current={_gen}) for {pid}");
            Destroy(glbRoot);
            yield break;
        }
        if (_currentGlb != null) Destroy(_currentGlb);
        _currentGlb = glbRoot;
        Debug.Log($"[PBL] GLB active: {pid}  root={glbRoot.name}  children={glbRoot.transform.childCount}");
    }

    // ── IO helpers ───────────────────────────────────────────────────────────────

    IEnumerator FetchJson(string dir, string filename, Action<string> onDone)
    {
        using var req = UnityWebRequest.Get(FileUri(System.IO.Path.Combine(dir, filename)));
        yield return req.SendWebRequest();
        if (req.result == UnityWebRequest.Result.Success)
            onDone(req.downloadHandler.text);
        else
            Debug.LogWarning($"[PatientBundleLoader] {filename}: {req.error}");
    }

    IEnumerator FetchTexture(string dir, string filename, Action<Texture2D> onDone)
    {
        using var req = UnityWebRequestTexture.GetTexture(FileUri(System.IO.Path.Combine(dir, filename)));
        yield return req.SendWebRequest();
        if (req.result == UnityWebRequest.Result.Success)
            onDone(DownloadHandlerTexture.GetContent(req));
        else
            Debug.LogWarning($"[PatientBundleLoader] {filename}: {req.error}");
    }

    IEnumerator LoadGlb(string dir, string filename, Action<GameObject> onDone)
    {
        string url = FileUri(System.IO.Path.Combine(dir, filename));
        Debug.Log($"[PBL] LoadGlb fetching: {url}");

        // Fetch GLB bytes via UnityWebRequest — the ONLY reliable way to read
        // StreamingAssets on Android (jar:// URIs). GLTFast.Load(url) can fail
        // silently when the jar:// scheme isn't handled by its internal loader.
        byte[] glbBytes = null;
        using (var req = UnityWebRequest.Get(url))
        {
            yield return req.SendWebRequest();
            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogWarning($"[PBL] GLB fetch failed: {filename} — {req.error}");
                yield break;
            }
            glbBytes = req.downloadHandler.data;
        }
        Debug.Log($"[PBL] GLB fetched {glbBytes.Length} bytes: {filename}");

        var gltf     = new GltfImport();
        // uri=null: GLB is self-contained — no external buffer/texture references.
        // Passing a jar:// URI to System.Uri would throw; null is safe here.
        var loadTask = gltf.LoadGltfBinary(glbBytes, null);
        while (!loadTask.IsCompleted) yield return null;

        if (loadTask.IsFaulted || !loadTask.Result)
        {
            Debug.LogWarning($"[PBL] GLB parse failed: {filename} — " +
                             (loadTask.Exception?.Message ?? "no result"));
            yield break;
        }

        // Create an explicit wrapper child so GLTFast never treats heartMeshRoot
        // itself as the SceneTransform. Without this, SceneTransform == heartMeshRoot,
        // and Destroy(_currentGlb) on the next patient swap destroys heartMeshRoot.
        Transform actualParent = heartMeshRoot != null ? heartMeshRoot : transform;
        var wrapper = new GameObject("GLBWrapper");
        wrapper.transform.SetParent(actualParent, false);

        var instantiator = new GameObjectInstantiator(gltf, wrapper.transform);
        var instTask     = gltf.InstantiateMainSceneAsync(instantiator);
        while (!instTask.IsCompleted) yield return null;

        if (instTask.IsFaulted || !instTask.Result)
        {
            Debug.LogWarning($"[PBL] GLB instantiation failed: {filename}");
            Destroy(wrapper);
            yield break;
        }

        var root = wrapper;   // track the wrapper — never heartMeshRoot

        // Remove any MeshColliders so they don't block the UI pointer raycasts.
        foreach (var mc in root.GetComponentsInChildren<MeshCollider>(true))
            Destroy(mc);

        var renderers = root.GetComponentsInChildren<Renderer>(true);
        Debug.Log($"[PBL] GLB instantiated: {filename}  renderers={renderers.Length}  " +
                  $"parent={actualParent.name}  rootActive={root.activeSelf}");

        // The GLB has no material definition — GLTFast's default is metallic-PBR
        // which renders as near-black in passthrough MR.  Apply an emissive crimson
        // material so the LV mesh is always visible regardless of ambient lighting.
        if (renderers.Length > 0)
        {
            var heartMat = SonoXRShaders.MakeCrimson(
                new Color(0.72f, 0.15f, 0.18f),   // deep cardiac red
                new Color(0.45f, 0.05f, 0.06f));   // dim red emission — ensures visibility in MR
            foreach (var r in renderers)
                r.material = heartMat;
            Debug.Log($"[PBL] Applied crimson material to {renderers.Length} renderer(s)");
        }

        onDone(root);
    }

    // On Android/Quest, Application.streamingAssetsPath is already a jar:// URI.
    // On editor/desktop, prepend file:// so UnityWebRequest can read local files.
    static string FileUri(string path)
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        return path;
#else
        return "file://" + path.Replace("\\", "/");
#endif
    }
}
