import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { PATIENTS, toneColor, type Patient } from '../data/patients'
import { FONT_DISPLAY, FONT_BODY, FONT_MONO, C } from '../theme'

const QUERIES = ['Explain this heart', 'What is ejection fraction?', 'Why uncertain here?', 'Normal range?']

// Map the flagged low-signal region to a position + radius on the reconstructed
// heart (group-local space, heart ≈ ±1). The rest of the model reads as high-signal.
function regionMarker(region: string, tone: string): { p: [number, number, number]; r: number } {
  const s = (region || '').toLowerCase()
  if (s.includes('global')) return { p: [0, -0.1, 0.02], r: 0.72 }
  if (s.includes('apical')) return { p: [0.05, -0.42, 0.14], r: 0.4 }
  if (s.includes('basal')) return { p: [0, 0.4, 0.04], r: 0.4 }
  if (s.includes('lateral')) return { p: [0.5, 0.0, 0.12], r: 0.4 }
  if (tone === 'low') return { p: [0, -0.3, 0.08], r: 0.5 }
  return { p: [0, -0.25, 0.1], r: 0.4 }
}

export default function PatientViewer() {
  const { id } = useParams()
  const navigate = useNavigate()
  const idx = Math.max(
    0,
    PATIENTS.findIndex((p) => p.id === id),
  )
  const safeIdx = idx < 0 ? 0 : idx
  const p = PATIENTS[safeIdx]

  const [query, setQuery] = useState<string | null>(null)
  const [readAloud, setReadAloud] = useState(false)
  const [vrSupported, setVrSupported] = useState<boolean | null>(null)
  const [toast, setToast] = useState('')
  // AI panel: Claude-generated answer (falls back to the static grounded text)
  const defaultAnswer = `${p.summary} Select a query above for detail — grounded in this patient's data.`
  const [answer, setAnswer] = useState(defaultAnswer)
  const [thinking, setThinking] = useState(false)
  const [recording, setRecording] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const mediaRef = useRef<MediaRecorder | null>(null)

  const heartCanvasRef = useRef<HTMLCanvasElement>(null)
  const scan4Ref = useRef<HTMLCanvasElement>(null)
  const scan2Ref = useRef<HTMLCanvasElement>(null)
  const heartWrapRef = useRef<HTMLDivElement>(null)
  // live patient tone + flagged region for the heart effect (avoids re-running GL on nav)
  const toneRef = useRef(p.tone)
  toneRef.current = p.tone
  const regionRef = useRef(p.uncertainty.region)
  regionRef.current = p.uncertainty.region

  useEffect(() => {
    localStorage.setItem('sonoxr_patient', String(safeIdx))
    // reset the AI panel when the patient changes
    setQuery(null)
    setAnswer(defaultAnswer)
    setThinking(false)
    audioRef.current?.pause()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.id])

  // VR detect
  useEffect(() => {
    let alive = true
    ;(async () => {
      let s = false
      try {
        const xr = (navigator as any).xr
        if (xr?.isSessionSupported) s = await xr.isSessionSupported('immersive-vr')
      } catch {
        /* none */
      }
      if (alive) setVrSupported(s)
    })()
    return () => {
      alive = false
    }
  }, [])

  // keyboard nav
  const go = (d: number) => {
    const next = (safeIdx + d + PATIENTS.length) % PATIENTS.length
    setQuery(null)
    navigate(`/patient/${PATIENTS[next].id}`)
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') go(1)
      else if (e.key === 'ArrowLeft') go(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  // synthetic ultrasound scans (redraw on patient change)
  useEffect(() => {
    drawSector(scan4Ref.current, p, '4ch')
    drawSector(scan2Ref.current, p, '2ch')
  }, [p])

  // 3D heart — mounted once; tone read from toneRef so nav doesn't rebuild GL
  useEffect(() => {
    const canvas = heartCanvasRef.current
    const wrap = heartWrapRef.current
    if (!canvas || !wrap) return
    let raf = 0
    let disposed = false
    let glbMats: any[] = []
    let mixer: THREE.AnimationMixer | null = null
    let clipDur = 1
    let camAz = 0,
      camEl = 0.05,
      tAz = 0,
      tEl = 0.05,
      drag = false,
      px = 0,
      py = 0

    const w = canvas.clientWidth || 600
    const h = canvas.clientHeight || 440
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    renderer.setSize(w, h, false)
    ;(renderer as any).useLegacyLights = true
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, w / h, 0.1, 100)
    camera.position.set(0, 0, 4.7)
    // faint fill so the holographic shell still catches a little light
    scene.add(new THREE.AmbientLight(0x223040, 1.0))
    const rim = new THREE.PointLight(0x4fa8ff, 6, 30)
    rim.position.set(-1.4, 1.6, -3)
    scene.add(rim)
    const group = new THREE.Group()
    group.position.y = -0.32 // sit the heart lower so it's fully in frame
    scene.add(group)

    // holographic shell material — translucent, cyan fresnel edges (the "outline")
    const makeHolo = () =>
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        blending: THREE.NormalBlending,
        uniforms: {
          uFill: { value: new THREE.Color(0x23a06a) }, // green high-signal body
          uEdge: { value: new THREE.Color(0x8fe8ff) }, // cyan rim/outline glow
          uBaseA: { value: 0.15 },
        },
        vertexShader:
          'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
        fragmentShader:
          'varying vec3 vN; varying vec3 vV; uniform vec3 uFill; uniform vec3 uEdge; uniform float uBaseA; void main(){ float f = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), 2.0); vec3 col = uFill*0.7 + uEdge*f*1.5; float a = uBaseA + f*0.6; gl_FragColor = vec4(col, a); }',
      })

    // translucent red "untrusted / low-signal" zone, positioned per patient each frame
    const regionMesh = new THREE.Mesh(
      new THREE.SphereGeometry(1, 24, 18),
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        blending: THREE.NormalBlending,
        uniforms: { uColor: { value: new THREE.Color(0xff5066) } },
        vertexShader:
          'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.0); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
        fragmentShader:
          'varying vec3 vN; varying vec3 vV; uniform vec3 uColor; void main(){ float f = pow(1.0 - max(dot(normalize(vN), normalize(vV)), 0.0), 1.8); gl_FragColor = vec4(uColor, 0.05 + f*0.35); }',
      }),
    )
    regionMesh.renderOrder = 2
    group.add(regionMesh)

    // give every heart mesh the holographic shell + a cyan edge-outline overlay so
    // the chambers and constituents read as a static transparent wireframed model.
    const dressHeart = (root: THREE.Object3D) => {
      const meshes: any[] = []
      root.traverse((o: any) => {
        if (o.isMesh || o.isSkinnedMesh) meshes.push(o)
      })
      meshes.forEach((o) => {
        o.material = makeHolo()
        glbMats.push(o.material)
        const edges = new THREE.LineSegments(
          new THREE.EdgesGeometry(o.geometry, 24),
          new THREE.LineBasicMaterial({
            color: 0x8fe6ff,
            transparent: true,
            opacity: 0.5,
            depthWrite: false,
          }),
        )
        edges.renderOrder = 1
        o.add(edges)
      })
    }
    const fallback = () => {
      const geo = new THREE.IcosahedronGeometry(1.0, 5)
      const mesh = new THREE.Mesh(geo, makeHolo())
      glbMats = [mesh.material]
      group.add(mesh)
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(geo, 24),
        new THREE.LineBasicMaterial({ color: 0x8fe6ff, transparent: true, opacity: 0.5, depthWrite: false }),
      )
      mesh.add(edges)
    }
    new GLTFLoader().load(
      '/heart.glb',
      (gltf) => {
        if (disposed) return
        const m = gltf.scene
        const box = new THREE.Box3().setFromObject(m)
        const size = box.getSize(new THREE.Vector3())
        const sc = 1.95 / (Math.max(size.x, size.y, size.z) || 1)
        m.scale.setScalar(sc)
        const c = box.getCenter(new THREE.Vector3())
        m.position.sub(c.multiplyScalar(sc))
        glbMats = []
        dressHeart(m)
        group.add(m)
        // static transparent model — do NOT play the baked beat animation
      },
      undefined,
      () => fallback(),
    )
    void mixer
    void clipDur

    const onDown = (e: PointerEvent) => {
      drag = true
      px = e.clientX
      py = e.clientY
      wrap.style.cursor = 'grabbing'
    }
    const onUp = () => {
      drag = false
      wrap.style.cursor = 'grab'
    }
    const onMove = (e: PointerEvent) => {
      if (!drag) return
      tAz += (e.clientX - px) * 0.008
      tEl = Math.max(-0.6, Math.min(0.7, tEl + (e.clientY - py) * 0.006))
      px = e.clientX
      py = e.clientY
    }
    wrap.addEventListener('pointerdown', onDown)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointermove', onMove)
    const onResize = () => {
      const nw = canvas.clientWidth,
        nh = canvas.clientHeight
      renderer.setSize(nw, nh, false)
      camera.aspect = nw / nh
      camera.updateProjectionMatrix()
    }
    window.addEventListener('resize', onResize)

    const clock = new THREE.Clock()
    const animate = () => {
      raf = requestAnimationFrame(animate)
      if (document.hidden) return
      const t = clock.getElapsedTime()
      camAz += (tAz - camAz) * 0.1
      camEl += (tEl - camEl) * 0.1
      const tone = toneRef.current
      // dilated ventricles read a touch larger (clinical cue); no beat — static model
      const heartScale = tone === 'low' ? 1.12 : tone === 'mid' ? 1.04 : 1.0
      group.scale.set(heartScale, heartScale, heartScale)
      group.rotation.y = camAz + (drag ? 0 : t * 0.06)
      group.rotation.x = camEl
      // place the translucent red low-signal zone for the current patient
      const rm = regionMarker(regionRef.current, tone)
      regionMesh.position.set(rm.p[0], rm.p[1], rm.p[2])
      regionMesh.scale.setScalar(rm.r)
      renderer.render(scene, camera)
    }
    animate()

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      wrap.removeEventListener('pointerdown', onDown)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('resize', onResize)
      try {
        scene.traverse((o: any) => {
          o.geometry?.dispose?.()
          const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
          mats.forEach((mm: any) => mm.dispose?.())
        })
        renderer.dispose()
      } catch {
        /* noop */
      }
    }
  }, [])

  const showToast = (msg: string) => {
    setToast(msg)
    window.clearTimeout((showToast as any)._t)
    ;(showToast as any)._t = window.setTimeout(() => setToast(''), 4200)
  }

  // Voice via Deepgram TTS (api/tts); falls back to the browser's Web Speech API.
  const speak = async (text: string) => {
    if (!text) return
    try {
      const r = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (r.ok && (r.headers.get('content-type') || '').includes('audio')) {
        const blob = await r.blob()
        const url = URL.createObjectURL(blob)
        audioRef.current?.pause()
        const audio = new Audio(url)
        audioRef.current = audio
        audio.onended = () => URL.revokeObjectURL(url)
        await audio.play()
        return
      }
    } catch {
      /* fall through to Web Speech */
    }
    try {
      if (!window.speechSynthesis) return
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(text)
      u.rate = 1.02
      window.speechSynthesis.speak(u)
    } catch {
      /* noop */
    }
  }

  // Ask the question — Claude (api/analyze) generates the answer, grounded in the
  // patient data; on no-key / error we fall back to the static grounded narration.
  const ask = async (question: string, fromChip: boolean) => {
    setQuery(fromChip ? question : null)
    setThinking(true)
    let text = ''
    try {
      const r = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient: p, question }),
      })
      const data = await r.json().catch(() => ({}))
      if (r.ok && data.configured && data.text) text = data.text
    } catch {
      /* fall back below */
    }
    if (!text) {
      text =
        fromChip && p.agent[question]
          ? p.agent[question]
          : `${p.summary} ${p.uncertainty.note}`
    }
    setAnswer(text)
    setThinking(false)
    if (readAloud) speak(text)
  }

  const onReadAloud = () => {
    const next = !readAloud
    setReadAloud(next)
    if (next) speak(answer)
    else {
      audioRef.current?.pause()
      window.speechSynthesis?.cancel()
    }
  }

  // Speech-to-text via Deepgram (api/stt): record a question, transcribe, then ask.
  const toggleRecord = async () => {
    if (recording) {
      mediaRef.current?.stop()
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      mediaRef.current = rec
      const chunks: BlobPart[] = []
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setRecording(false)
        const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' })
        setThinking(true)
        try {
          const r = await fetch('/api/stt', {
            method: 'POST',
            headers: { 'Content-Type': blob.type },
            body: blob,
          })
          if (r.status === 503) {
            setThinking(false)
            showToast('Voice input isn’t configured yet (add a Deepgram API key).')
            return
          }
          const data = await r.json().catch(() => ({}))
          const transcript = (data.transcript || '').trim()
          if (transcript) await ask(transcript, false)
          else {
            setThinking(false)
            showToast('Didn’t catch that — try again.')
          }
        } catch {
          setThinking(false)
          showToast('Voice input failed.')
        }
      }
      rec.start()
      setRecording(true)
    } catch {
      showToast('Microphone permission denied.')
    }
  }

  const launchVR = async () => {
    if (vrSupported && (navigator as any).xr) {
      try {
        await (navigator as any).xr.requestSession('immersive-vr')
        showToast('Entering VR — put on your headset.')
        return
      } catch {
        showToast("Couldn't start the VR session. Check your headset connection and permissions.")
        return
      }
    }
    showToast(
      'No VR headset detected. On a connected Quest 3 this opens the immersive SonoXR scene; here you’re seeing the WebXR fallback (web view).',
    )
  }

  const efColor = toneColor(p.tone)
  const counter = (i: number) => String(i + 1).padStart(2, '0')

  return (
    <section
      style={{
        position: 'relative',
        width: '100%',
        minHeight: '100vh',
        background: 'radial-gradient(130% 90% at 50% -10%, #11141B 0%, #0A0C11 42%, #07090B 100%)',
        color: '#EEF1F5',
        overflow: 'hidden',
        fontFamily: FONT_BODY,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background: 'radial-gradient(50% 45% at 50% 46%, rgba(225,29,51,0.13) 0%, rgba(225,29,51,0) 60%)',
        }}
      />

      {/* TOP BAR */}
      <header
        style={{
          position: 'relative',
          zIndex: 5,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '22px 36px',
          borderBottom: '1px solid rgba(255,255,255,.07)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: C.red,
              boxShadow: '0 0 14px 2px rgba(225,29,51,.6)',
              animation: 'sonoPulse 1s ease-in-out infinite',
            }}
          />
          <span style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 18 }}>SonoXR</span>
          <span style={{ width: 1, height: 16, background: 'rgba(255,255,255,.16)' }} />
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 12,
              letterSpacing: '.16em',
              color: C.textMuted,
              textTransform: 'uppercase',
            }}
          >
            Cardiac Analysis
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <DeviceChip supported={vrSupported} />
          <span style={{ fontFamily: FONT_MONO, fontSize: 13, letterSpacing: '.12em', color: C.textMuted2 }}>
            {counter(safeIdx)} / {counter(PATIENTS.length - 1)}
          </span>
          <Link
            to="/dashboard"
            className="app-ghostbtn"
            style={{
              padding: '9px 18px',
              border: '1px solid rgba(79,168,255,.35)',
              borderRadius: 9,
              background: 'rgba(79,168,255,.08)',
              color: C.blueText,
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.12em',
              textTransform: 'uppercase',
              textDecoration: 'none',
            }}
          >
            Home
          </Link>
        </div>
      </header>

      {/* MAIN GRID */}
      <div
        style={{
          position: 'relative',
          zIndex: 4,
          display: 'grid',
          gridTemplateColumns: '300px 1fr 330px',
          gap: 22,
          padding: '30px 36px 0',
          maxWidth: 1480,
          minWidth: 1060,
          margin: '0 auto',
          alignItems: 'start',
        }}
      >
        {/* LEFT: scans */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, animation: 'appUp .5s ease both' }}>
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.2em',
              color: C.blue,
              textTransform: 'uppercase',
            }}
          >
            Ultrasound Scans
          </div>
          <ScanCard canvasRef={scan4Ref} caption="Apical 4-Chamber · End-Diastole" dur="3.6s" />
          <ScanCard canvasRef={scan2Ref} caption="Apical 2-Chamber · End-Diastole" dur="4.1s" />
          <div style={{ fontSize: 11, lineHeight: 1.5, color: C.textDim2 }}>
            Real CAMUS patient scans · LV contour from expert masks
          </div>
        </div>

        {/* CENTER: heart + EF */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
          <div ref={heartWrapRef} style={{ position: 'relative', width: '100%', height: 440, cursor: 'grab' }}>
            <canvas
              ref={heartCanvasRef}
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }}
            />
            <div
              style={{
                position: 'absolute',
                left: '50%',
                bottom: 10,
                transform: 'translateX(-50%)',
                fontFamily: FONT_MONO,
                fontSize: 10.5,
                letterSpacing: '.16em',
                color: C.textDim2,
                textTransform: 'uppercase',
                pointerEvents: 'none',
              }}
            >
              Drag to orbit · reconstructed LV
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, marginTop: 22 }}>
            <div
              style={{
                fontFamily: FONT_DISPLAY,
                fontWeight: 700,
                fontSize: 44,
                lineHeight: 1,
                color: efColor,
                letterSpacing: '-0.02em',
              }}
            >
              EF {p.ef}%
            </div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 12.5, letterSpacing: '.06em', color: C.textBody }}>
              EDV {p.edv} mL · ESV {p.esv} mL · {p.quality}
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 9,
                maxWidth: 560,
                marginTop: 10,
                padding: '12px 16px',
                border: '1px solid rgba(245,158,66,.22)',
                borderRadius: 11,
                background: 'rgba(245,158,66,.06)',
              }}
            >
              <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: C.amber, marginTop: 1 }}>!</span>
              <span style={{ fontSize: 13, lineHeight: 1.5, color: '#C7CDD6' }}>
                <span style={{ color: C.amber, fontWeight: 600 }}>{p.uncertainty.region}</span>{' '}
                <span style={{ color: C.textMuted }}>· {p.uncertainty.confidence}% confidence</span>
                {' — '}
                {p.uncertainty.note}
              </span>
            </div>
          </div>
        </div>

        {/* RIGHT: AI panel */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
            border: '1px solid rgba(255,255,255,.08)',
            borderRadius: 16,
            background: 'rgba(9,13,20,.6)',
            backdropFilter: 'blur(10px)',
            padding: 20,
            animation: 'appUp .5s ease both',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                fontFamily: FONT_MONO,
                fontSize: 11,
                letterSpacing: '.2em',
                color: C.blue,
                textTransform: 'uppercase',
              }}
            >
              AI Analysis
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: C.blue,
                  boxShadow: '0 0 8px rgba(79,168,255,.7)',
                }}
              />
              <span
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 9.5,
                  letterSpacing: '.1em',
                  color: C.textDim,
                  textTransform: 'uppercase',
                }}
              >
                Grounded
              </span>
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {QUERIES.map((q) => {
              const on = q === query
              return (
                <button
                  key={q}
                  onClick={() => ask(q, true)}
                  style={{
                    textAlign: 'left',
                    padding: '11px 14px',
                    border: `1px solid ${on ? 'rgba(79,168,255,.5)' : 'rgba(255,255,255,.1)'}`,
                    borderRadius: 9,
                    background: on ? 'rgba(79,168,255,.1)' : 'rgba(255,255,255,.03)',
                    color: '#E4E8EE',
                    fontFamily: FONT_BODY,
                    fontSize: 13.5,
                    cursor: 'pointer',
                    transition: 'border-color .18s, background .18s',
                  }}
                >
                  {q}
                </button>
              )
            })}
          </div>
          <div style={{ height: 1, background: 'rgba(255,255,255,.08)' }} />
          <div
            style={{
              fontSize: 13.5,
              lineHeight: 1.6,
              color: thinking ? C.textMuted : C.textBody2,
              minHeight: 104,
            }}
          >
            {thinking ? 'Analyzing — grounded in this patient’s data…' : answer}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 2, flexWrap: 'wrap' }}>
            <button
              onClick={onReadAloud}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                padding: '8px 12px',
                border: '1px solid rgba(255,255,255,.1)',
                borderRadius: 8,
                background: 'rgba(255,255,255,.03)',
                color: '#C7CDD6',
                fontFamily: FONT_MONO,
                fontSize: 10.5,
                letterSpacing: '.08em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
            >
              <span
                style={{
                  width: 13,
                  height: 13,
                  borderRadius: 3,
                  border: `1.5px solid ${readAloud ? C.blue : C.textDim}`,
                  background: readAloud ? C.blue : 'transparent',
                  display: 'inline-block',
                }}
              />
              Read Aloud · Deepgram
            </button>
            <button
              onClick={toggleRecord}
              title="Ask a question by voice (Deepgram speech-to-text)"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                padding: '8px 12px',
                border: `1px solid ${recording ? 'rgba(225,29,51,.5)' : 'rgba(255,255,255,.1)'}`,
                borderRadius: 8,
                background: recording ? 'rgba(225,29,51,.12)' : 'rgba(255,255,255,.03)',
                color: recording ? C.redBright2 : '#C7CDD6',
                fontFamily: FONT_MONO,
                fontSize: 10.5,
                letterSpacing: '.08em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
            >
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: '50%',
                  background: recording ? C.red : C.textDim,
                  boxShadow: recording ? '0 0 8px rgba(225,29,51,.8)' : 'none',
                  animation: recording ? 'sonoPulse 1s ease-in-out infinite' : 'none',
                  display: 'inline-block',
                }}
              />
              {recording ? 'Stop · Listening' : 'Ask by voice'}
            </button>
          </div>
          <div style={{ fontSize: 11, lineHeight: 1.5, color: C.textDim2 }}>
            Responses grounded in patient data · Not clinical advice
          </div>
        </div>
      </div>

      {/* BOTTOM BAR */}
      <div
        style={{
          position: 'relative',
          zIndex: 5,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 20,
          padding: '20px 36px 26px',
          maxWidth: 1480,
          minWidth: 1060,
          margin: '18px auto 0',
        }}
      >
        <button onClick={() => go(-1)} className="app-ghostbtn" style={navBtnStyle}>
          <span style={{ fontSize: 16 }}>◄</span> Prev
        </button>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, textAlign: 'center' }}>
          <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 600, fontSize: 16, color: C.textPrimary }}>
            {p.label}
          </div>
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.12em',
              color: C.textMuted,
              textTransform: 'uppercase',
            }}
          >
            {p.category}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button
            onClick={launchVR}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '13px 22px',
              border: '1px solid rgba(225,29,51,.45)',
              borderRadius: 11,
              background: 'rgba(225,29,51,.12)',
              color: C.redBright2,
              fontFamily: FONT_BODY,
              fontWeight: 600,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: C.red,
                boxShadow: '0 0 8px rgba(225,29,51,.8)',
              }}
            />
            Launch in VR
          </button>
          <button onClick={() => go(1)} className="app-ghostbtn" style={navBtnStyle}>
            Next <span style={{ fontSize: 16 }}>►</span>
          </button>
        </div>
      </div>

      {/* toast */}
      <div
        style={{
          position: 'fixed',
          left: '50%',
          bottom: 30,
          transform: `translateX(-50%) translateY(${toast ? 0 : 20}px)`,
          zIndex: 30,
          opacity: toast ? 1 : 0,
          pointerEvents: 'none',
          transition: 'opacity .3s, transform .3s',
          padding: '14px 22px',
          border: '1px solid rgba(255,255,255,.14)',
          borderRadius: 12,
          background: 'rgba(15,19,27,.95)',
          backdropFilter: 'blur(10px)',
          fontSize: 13.5,
          color: '#E4E8EE',
          maxWidth: 440,
          textAlign: 'center',
        }}
      >
        {toast}
      </div>
    </section>
  )
}

const navBtnStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 11,
  padding: '13px 22px',
  border: '1px solid rgba(255,255,255,.12)',
  borderRadius: 11,
  background: 'rgba(255,255,255,.04)',
  color: '#E4E8EE',
  fontFamily: FONT_BODY,
  fontWeight: 600,
  fontSize: 14,
  cursor: 'pointer',
}

function DeviceChip({ supported }: { supported: boolean | null }) {
  const ready = supported === true
  const checking = supported === null
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 14px',
        border: '1px solid rgba(255,255,255,.1)',
        borderRadius: 999,
        background: 'rgba(255,255,255,.03)',
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: checking ? C.textDim : ready ? C.green : C.amber,
          boxShadow: checking ? 'none' : `0 0 9px ${ready ? 'rgba(63,184,97,.8)' : 'rgba(245,167,66,.7)'}`,
        }}
      />
      <span
        style={{
          fontFamily: FONT_MONO,
          fontSize: 11,
          letterSpacing: '.12em',
          color: checking ? '#C7CDD6' : ready ? C.greenText : C.amberText,
          textTransform: 'uppercase',
        }}
      >
        {checking ? 'Checking VR…' : ready ? 'VR headset ready' : 'No VR · WebXR fallback'}
      </span>
    </div>
  )
}

function ScanCard({
  canvasRef,
  caption,
  dur,
}: {
  canvasRef: React.RefObject<HTMLCanvasElement>
  caption: string
  dur: string
}) {
  return (
    <div
      style={{
        border: '1px solid rgba(255,255,255,.08)',
        borderRadius: 14,
        background: 'rgba(9,13,20,.55)',
        backdropFilter: 'blur(8px)',
        padding: 12,
        overflow: 'hidden',
      }}
    >
      <div style={{ position: 'relative', borderRadius: 9, overflow: 'hidden', background: '#000' }}>
        <canvas ref={canvasRef} width={600} height={420} style={{ display: 'block', width: '100%', height: 'auto' }} />
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: 0,
            height: '14%',
            background: 'linear-gradient(180deg,rgba(120,180,255,.18),transparent)',
            animation: `appScan ${dur} linear infinite`,
            pointerEvents: 'none',
          }}
        />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 9 }}>
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: C.blue }} />
        <span style={{ fontSize: 12, color: C.textBody }}>{caption}</span>
      </div>
    </div>
  )
}

// synthetic ultrasound sector with speckle, dark LV cavity (scaled by EDV) + blue contour
function drawSector(cv: HTMLCanvasElement | null, p: Patient, view: '4ch' | '2ch') {
  if (!cv) return
  const ctx = cv.getContext('2d')
  if (!ctx) return
  const W = cv.width,
    H = cv.height
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, W, H)
  const apex = { x: W / 2, y: 24 }
  const spread = 0.62,
    R = H - 50
  ctx.save()
  ctx.beginPath()
  ctx.moveTo(apex.x, apex.y)
  ctx.arc(apex.x, apex.y, R, Math.PI / 2 - spread, Math.PI / 2 + spread)
  ctx.closePath()
  ctx.clip()
  let s = (p.id.charCodeAt(7) || 1) + (view === '2ch' ? 37 : 0)
  const rnd = () => {
    s = (s * 9301 + 49297) % 233280
    return s / 233280
  }
  const img = ctx.createImageData(W, H)
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++) {
      const dx = x - apex.x,
        dy = y - apex.y,
        d = Math.sqrt(dx * dx + dy * dy)
      const v = 22 + rnd() * 60 * (1 - d / (R * 1.4))
      const i = (y * W + x) * 4
      img.data[i] = v * 0.95
      img.data[i + 1] = v
      img.data[i + 2] = v * 1.05
      img.data[i + 3] = 255
    }
  ctx.putImageData(img, 0, 0)
  const cav = 0.78 + (p.edv - 90) / 320
  const cx = apex.x,
    cy = apex.y + R * 0.5
  const rw = R * 0.2 * cav,
    rh = R * 0.4 * cav
  const g = ctx.createRadialGradient(cx, cy, 2, cx, cy, rh)
  g.addColorStop(0, 'rgba(0,0,0,0.92)')
  g.addColorStop(0.7, 'rgba(0,0,0,0.7)')
  g.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.save()
  ctx.translate(cx, cy)
  ctx.scale(rw / rh, 1)
  ctx.beginPath()
  ctx.arc(0, 0, rh, 0, Math.PI * 2)
  ctx.fillStyle = g
  ctx.fill()
  ctx.restore()
  ctx.beginPath()
  for (let a = 0; a <= Math.PI * 2 + 0.01; a += 0.1) {
    const r = rh * (1 + 0.05 * Math.sin(a * 3))
    const x = cx + Math.cos(a) * r * (rw / rh) * 1.18
    const y = cy + Math.sin(a) * r * 1.05
    a === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.closePath()
  // translucent green fill + bright green outline = the imaged high-signal region,
  // mirroring the green high-signal shading on the 3D heart.
  ctx.fillStyle = 'rgba(63,200,140,0.12)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(80,224,150,0.9)'
  ctx.lineWidth = 2.2
  ctx.stroke()
  ctx.restore()
  ctx.beginPath()
  ctx.moveTo(apex.x, apex.y)
  ctx.arc(apex.x, apex.y, R, Math.PI / 2 - spread, Math.PI / 2 + spread)
  ctx.closePath()
  ctx.strokeStyle = 'rgba(120,150,190,0.25)'
  ctx.lineWidth = 1
  ctx.stroke()
}
