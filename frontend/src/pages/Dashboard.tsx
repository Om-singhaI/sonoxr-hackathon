import { useEffect, useState, type CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PATIENTS, toneColor, type Patient } from '../data/patients'
import { FONT_DISPLAY, FONT_BODY, FONT_MONO, C } from '../theme'

type Mode = 'web' | 'vr'

export default function Dashboard() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<Mode>(
    () => (localStorage.getItem('sonoxr_mode') as Mode) || 'web',
  )
  const [vrSupported, setVrSupported] = useState<boolean | null>(null)
  const [toast, setToast] = useState('')
  const isAdmin =
    typeof window !== 'undefined' && localStorage.getItem('sonoxr_role') === 'admin'

  useEffect(() => {
    let alive = true
    ;(async () => {
      let supported = false
      try {
        const xr = (navigator as any).xr
        if (xr?.isSessionSupported) supported = await xr.isSessionSupported('immersive-vr')
      } catch {
        /* no xr */
      }
      if (alive) setVrSupported(supported)
    })()
    return () => {
      alive = false
    }
  }, [])

  const setModePersist = (m: Mode) => {
    setMode(m)
    localStorage.setItem('sonoxr_mode', m)
  }

  const showToast = (msg: string) => {
    setToast(msg)
    window.clearTimeout((showToast as any)._t)
    ;(showToast as any)._t = window.setTimeout(() => setToast(''), 3800)
  }

  const open = (i: number) => {
    localStorage.setItem('sonoxr_patient', String(i))
    const p = PATIENTS[i]
    if (mode === 'vr') {
      if (vrSupported) {
        showToast(`Launching ${p.label} into the headset — put on your Quest 3.`)
        // TODO: navigator.xr.requestSession('immersive-vr') inside the gesture
      } else {
        showToast(`No headset connected. Opening the web view of ${p.label} instead.`)
        window.setTimeout(() => navigate(`/patient/${p.id}`), 1400)
      }
      return
    }
    navigate(`/patient/${p.id}`)
  }

  const eyebrow: CSSProperties = {
    fontFamily: FONT_MONO,
    fontSize: 11.5,
    letterSpacing: '.22em',
    color: C.blue,
    textTransform: 'uppercase',
    marginBottom: 14,
  }

  return (
    <section
      style={{
        position: 'relative',
        width: '100%',
        minHeight: '100vh',
        background:
          'radial-gradient(130% 80% at 50% -10%, #11141B 0%, #0A0C11 44%, #07090B 100%)',
        color: '#EEF1F5',
        paddingBottom: 60,
        fontFamily: FONT_BODY,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background:
            'radial-gradient(46% 40% at 70% 0%, rgba(79,168,255,0.1) 0%, rgba(79,168,255,0) 60%)',
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
          padding: '22px 40px',
          borderBottom: '1px solid rgba(255,255,255,.07)',
          flexWrap: 'wrap',
          gap: 14,
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
            Clinical Console
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <Link
            to="/"
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.12em',
              color: C.textMuted,
              textTransform: 'uppercase',
              textDecoration: 'none',
            }}
          >
            ← Site
          </Link>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 9,
              padding: '9px 15px',
              border: `1px solid ${isAdmin ? 'rgba(79,168,255,.35)' : 'rgba(255,255,255,.1)'}`,
              borderRadius: 999,
              background: isAdmin ? 'rgba(79,168,255,.06)' : 'rgba(255,255,255,.03)',
            }}
          >
            <span
              style={{
                width: 24,
                height: 24,
                borderRadius: '50%',
                background: isAdmin
                  ? 'linear-gradient(135deg,#4FA8FF,#1d4f7a)'
                  : 'linear-gradient(135deg,#E11D33,#7a0f1d)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontFamily: FONT_DISPLAY,
                fontWeight: 600,
                fontSize: 11,
                color: '#fff',
              }}
            >
              {isAdmin ? 'AD' : 'DR'}
            </span>
            <span style={{ fontSize: 13, color: '#C7CDD6' }}>
              {isAdmin ? 'Admin' : 'Dr. Reyes'}
            </span>
            {isAdmin && (
              <span
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 9,
                  letterSpacing: '.14em',
                  textTransform: 'uppercase',
                  color: C.blueText,
                  border: '1px solid rgba(79,168,255,.4)',
                  borderRadius: 5,
                  padding: '2px 6px',
                }}
              >
                Admin
              </span>
            )}
          </div>
        </div>
      </header>

      <div
        style={{
          position: 'relative',
          zIndex: 4,
          maxWidth: 1180,
          margin: '0 auto',
          padding: '0 40px',
        }}
      >
        {/* HERO ROW */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap: 30,
            flexWrap: 'wrap',
            padding: '46px 0 30px',
            animation: 'appUp .5s ease both',
          }}
        >
          <div>
            <div style={eyebrow}>Patient Library</div>
            <h1
              style={{
                fontFamily: FONT_DISPLAY,
                fontWeight: 700,
                fontSize: 'clamp(30px,3.4vw,44px)',
                lineHeight: 1.05,
                letterSpacing: '-0.02em',
                color: C.textPrimary,
                marginBottom: 12,
              }}
            >
              Select a study to review.
            </h1>
            <p style={{ fontSize: 15, lineHeight: 1.55, color: C.textBody, maxWidth: 520 }}>
              Five reconstructed cardiac echoes. Open one in the browser, or launch it into the
              headset for hands-on review in mixed reality.
            </p>
          </div>
          {/* VR status card */}
          <VrCard supported={vrSupported} />
        </div>

        {/* VIEW TOGGLE */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            marginBottom: 26,
            flexWrap: 'wrap',
            animation: 'appUp .5s ease .05s both',
          }}
        >
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.14em',
              color: C.textDim,
              textTransform: 'uppercase',
            }}
          >
            Open studies in
          </span>
          <div
            style={{
              display: 'inline-flex',
              padding: 4,
              border: '1px solid rgba(255,255,255,.1)',
              borderRadius: 11,
              background: 'rgba(255,255,255,.03)',
            }}
          >
            <ModeBtn label="Web view" dot="square" active={mode === 'web'} onClick={() => setModePersist('web')} />
            <ModeBtn label="VR view" dot="round" active={mode === 'vr'} vr onClick={() => setModePersist('vr')} />
          </div>
          <span style={{ fontSize: 12.5, color: C.textMuted }}>
            {mode === 'vr'
              ? 'Launches the study into your connected headset.'
              : 'Opens the dashboard in your browser.'}
          </span>
        </div>

        {/* PATIENT GRID */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill,minmax(330px,1fr))',
            gap: 18,
          }}
        >
          {PATIENTS.map((p, i) => (
            <PatientCard key={p.id} p={p} i={i} mode={mode} onOpen={() => open(i)} />
          ))}
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

function ModeBtn({
  label,
  dot,
  active,
  vr,
  onClick,
}: {
  label: string
  dot: 'square' | 'round'
  active: boolean
  vr?: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '9px 18px',
        border: 'none',
        borderRadius: 8,
        background: active ? (vr ? C.red : C.blue) : 'transparent',
        color: active ? (vr ? '#fff' : '#06121f') : '#C7CDD6',
        fontFamily: FONT_BODY,
        fontWeight: 600,
        fontSize: 13.5,
        cursor: 'pointer',
        transition: 'background .2s, color .2s',
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: dot === 'round' ? '50%' : 2,
          background: 'currentColor',
        }}
      />
      {label}
    </button>
  )
}

function VrCard({ supported }: { supported: boolean | null }) {
  const ready = supported === true
  const checking = supported === null
  const dotColor = checking ? C.textDim : ready ? C.green : C.amber
  const border = checking
    ? 'rgba(255,255,255,.1)'
    : ready
      ? 'rgba(63,184,97,.3)'
      : 'rgba(245,167,66,.28)'
  return (
    <div
      style={{
        width: 280,
        border: `1px solid ${border}`,
        borderRadius: 14,
        background: 'rgba(9,13,20,.6)',
        backdropFilter: 'blur(10px)',
        padding: 18,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}
      >
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 10.5,
            letterSpacing: '.16em',
            color: C.textMuted2,
            textTransform: 'uppercase',
          }}
        >
          Headset
        </span>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: dotColor,
            boxShadow: checking ? 'none' : `0 0 9px ${ready ? 'rgba(63,184,97,.8)' : 'rgba(245,167,66,.7)'}`,
          }}
        />
      </div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontWeight: 600,
          fontSize: 18,
          color: C.textPrimary,
          marginBottom: 4,
        }}
      >
        {checking ? 'Checking…' : ready ? 'Quest 3 ready' : 'No headset'}
      </div>
      <div style={{ fontSize: 12.5, lineHeight: 1.45, color: C.textMuted }}>
        {checking
          ? 'Looking for a connected WebXR device.'
          : ready
            ? 'A WebXR device is connected. VR view is available.'
            : 'Connect a WebXR device for VR view. Web view works without one.'}
      </div>
    </div>
  )
}

function PatientCard({
  p,
  i,
  mode,
  onOpen,
}: {
  p: Patient
  i: number
  mode: Mode
  onOpen: () => void
}) {
  const col = toneColor(p.tone)
  const [hover, setHover] = useState(false)
  const stat = (v: string, l: string) => (
    <div>
      <div style={{ fontSize: 13, color: '#C7CDD6', fontWeight: 600 }}>{v}</div>
      <div
        style={{
          fontSize: 10,
          color: C.textDim2,
          fontFamily: FONT_MONO,
          letterSpacing: '.08em',
          textTransform: 'uppercase',
        }}
      >
        {l}
      </div>
    </div>
  )
  return (
    <div
      onClick={onOpen}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: 'relative',
        border: `1px solid ${hover ? 'rgba(255,255,255,.22)' : 'rgba(255,255,255,.09)'}`,
        borderRadius: 16,
        background: hover ? 'rgba(13,18,26,.7)' : 'rgba(9,13,20,.55)',
        backdropFilter: 'blur(8px)',
        padding: 22,
        cursor: 'pointer',
        overflow: 'hidden',
        transform: hover ? 'translateY(-3px)' : 'translateY(0)',
        transition: 'border-color .2s, transform .2s, background .2s',
        animation: `appUp .5s ease ${0.06 * i + 0.1}s both`,
      }}
    >
      <div
        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: 3, background: col, opacity: 0.8 }}
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 18,
        }}
      >
        <div>
          <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 600, fontSize: 18, color: C.textPrimary }}>
            {p.label}
          </div>
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 10.5,
              letterSpacing: '.1em',
              color: C.textMuted,
              textTransform: 'uppercase',
              marginTop: 4,
            }}
          >
            {p.category}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 30, lineHeight: 1, color: col }}>
            {p.ef}%
          </div>
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 9.5,
              letterSpacing: '.12em',
              color: C.textDim2,
              textTransform: 'uppercase',
              marginTop: 3,
            }}
          >
            Ejection Fraction
          </div>
        </div>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 3,
          background: 'rgba(255,255,255,.07)',
          overflow: 'hidden',
          marginBottom: 16,
        }}
      >
        <div style={{ height: '100%', width: `${p.ef}%`, background: col, borderRadius: 3 }} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: 16 }}>
          {stat(`${p.edv} mL`, 'EDV')}
          {stat(`${p.esv} mL`, 'ESV')}
          {stat(p.quality, 'Quality')}
        </div>
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 11,
            letterSpacing: '.1em',
            color: mode === 'vr' ? C.redBright2 : C.blue,
            textTransform: 'uppercase',
          }}
        >
          {mode === 'vr' ? 'Launch in VR →' : 'Open →'}
        </span>
      </div>
    </div>
  )
}
