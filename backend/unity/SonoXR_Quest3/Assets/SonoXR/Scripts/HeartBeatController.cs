// HeartBeatController.cs
// Iteration 8 — drives the ED<->ES beating animation.
//
// TWO PATHS — the script detects which assets were imported and picks automatically:
//
//   PATH A (preferred): beating.glb imported via GLTFast.
//     GLTFast converts morph targets to Unity BlendShapes and imports the "beat"
//     AnimationClip. This script finds the Animator/Animation and plays it on loop.
//
//   PATH B (fallback): lv_ed.glb + lv_es.glb imported as static meshes.
//     The script lerps vertex positions between the two meshes every frame.
//     Works because both meshes share identical topology (same disc-stack builder).
//     At 962 vertices (20 discs × 48 ring verts + 2 caps) this is fast on CPU.
//
// Set-up:
//   - Drag the imported beating.glb prefab (or lv_ed.glb object) onto heartRoot.
//   - If using Path B, also drag the lv_es.glb mesh into esMesh.
//   - cycleDuration = 0.9 s matches the glTF "beat" animation timing.

using System.Collections;
using UnityEngine;

public class HeartBeatController : MonoBehaviour
{
    [Header("Path A — GLTFast animated prefab (preferred)")]
    [Tooltip("Root GameObject of the beating.glb import. Leave null to use Path B.")]
    public GameObject heartRoot;

    [Header("Path B — two static meshes (fallback)")]
    [Tooltip("Mesh from lv_ed.glb import.")]
    public Mesh edMesh;
    [Tooltip("Mesh from lv_es.glb import.")]
    public Mesh esMesh;
    [Tooltip("MeshFilter that will receive the interpolated mesh.")]
    public MeshFilter targetMeshFilter;

    [Header("Timing")]
    [Tooltip("Full ED->ES->ED cycle in seconds. 0.9 s = ~67 bpm.")]
    public float cycleDuration = 0.9f;

    // -- internals --
    private enum BeatPath { Unknown, AnimatorClip, BlendShape, VertexLerp }
    private BeatPath _path = BeatPath.Unknown;

    // Path A — animator
    private Animator _animator;
    // Path A — blendshape fallback (GLTFast morph without animation clip)
    private SkinnedMeshRenderer _smr;
    private int _blendShapeIndex = -1;
    // Path B — vertex lerp
    private Mesh _workMesh;
    private Vector3[] _edVerts, _esVerts;
    private Vector3[] _normsED, _normsES;

    void Start()
    {
        if (heartRoot != null)
            TrySetupPathA();

        if (_path == BeatPath.Unknown)
            TrySetupPathB();

        if (_path == BeatPath.Unknown)
            Debug.LogWarning("[HeartBeat] No static beat setup — heart will be static until " +
                             "a GLB with Animator/BlendShape is assigned to heartRoot in the Inspector.");
        else
            Debug.Log($"[HeartBeat] Using {_path} path, cycle={cycleDuration}s.");
    }

    // -------------------------------------------------------------------------
    void TrySetupPathA()
    {
        // 1. Try Animator with an AnimationClip named "beat".
        _animator = heartRoot.GetComponentInChildren<Animator>();
        if (_animator != null && _animator.runtimeAnimatorController != null)
        {
            // Force loop on the first state and play.
            _animator.speed = 1f;
            _animator.Play(0, 0, 0f);
            _path = BeatPath.AnimatorClip;
            Debug.Log("[HeartBeat] Path A: Animator clip found and playing.");
            return;
        }

        // 2. Try Animation component (legacy).
        var legAnim = heartRoot.GetComponentInChildren<Animation>();
        if (legAnim != null && legAnim.clip != null)
        {
            legAnim.wrapMode = WrapMode.Loop;
            legAnim.Play();
            _path = BeatPath.AnimatorClip;
            Debug.Log("[HeartBeat] Path A: Legacy Animation clip found and playing.");
            return;
        }

        // 3. GLTFast may import morph targets as BlendShapes without an animation clip.
        //    Drive the blendshape weight manually.
        _smr = heartRoot.GetComponentInChildren<SkinnedMeshRenderer>();
        if (_smr != null && _smr.sharedMesh.blendShapeCount > 0)
        {
            _blendShapeIndex = 0;   // GLTFast names them "0", "1", ...
            _path = BeatPath.BlendShape;
            Debug.Log($"[HeartBeat] Path A: BlendShape[0] found on SkinnedMeshRenderer " +
                      $"'{_smr.name}', driving manually.");
            return;
        }

        Debug.Log("[HeartBeat] Path A: no Animator / BlendShape found in heartRoot; falling to Path B.");
    }

    void TrySetupPathB()
    {
        if (edMesh == null || esMesh == null || targetMeshFilter == null)
        {
            Debug.LogWarning("[HeartBeat] Path B: edMesh / esMesh / targetMeshFilter not assigned.");
            return;
        }
        if (edMesh.vertexCount != esMesh.vertexCount)
        {
            Debug.LogError($"[HeartBeat] Path B: vertex count mismatch " +
                           $"(ED={edMesh.vertexCount} ES={esMesh.vertexCount}). " +
                           "Meshes must share identical topology.");
            return;
        }

        _edVerts = edMesh.vertices;
        _esVerts = esMesh.vertices;
        _normsED = edMesh.normals;
        _normsES = esMesh.normals;

        _workMesh = new Mesh { name = "HeartBeat_Dynamic" };
        _workMesh.vertices  = _edVerts;
        _workMesh.triangles = edMesh.triangles;
        _workMesh.normals   = _normsED;
        _workMesh.RecalculateBounds();
        targetMeshFilter.mesh = _workMesh;

        _path = BeatPath.VertexLerp;
        Debug.Log($"[HeartBeat] Path B (vertex lerp): {_edVerts.Length} verts, ready.");
    }

    // -------------------------------------------------------------------------
    void Update()
    {
        // t: 0 (ED) -> 1 (ES) -> 0 (ED), smooth sine envelope
        float phase = (Time.time % cycleDuration) / cycleDuration;   // 0..1
        float t = Mathf.SmoothStep(0f, 1f,
                      phase < 0.5f ? phase * 2f : (1f - phase) * 2f);

        switch (_path)
        {
            case BeatPath.BlendShape:
                _smr.SetBlendShapeWeight(_blendShapeIndex, t * 100f);
                break;

            case BeatPath.VertexLerp:
                UpdateVertexLerp(t);
                break;
            // AnimatorClip drives itself; nothing to do in Update.
        }
    }

    void UpdateVertexLerp(float t)
    {
        var verts = new Vector3[_edVerts.Length];
        var norms = new Vector3[_normsED.Length];
        for (int i = 0; i < verts.Length; i++)
        {
            verts[i] = Vector3.LerpUnclamped(_edVerts[i], _esVerts[i], t);
            norms[i] = Vector3.LerpUnclamped(_normsED[i], _normsES[i], t).normalized;
        }
        _workMesh.vertices = verts;
        _workMesh.normals  = norms;
        _workMesh.RecalculateBounds();
    }

    // Public API — lets other scripts pause/resume the cycle.
    public void SetPaused(bool paused) => enabled = !paused;
}
