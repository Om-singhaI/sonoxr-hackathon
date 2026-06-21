import { useState, type CSSProperties } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { FONT_DISPLAY, FONT_BODY, FONT_MONO, C } from '../theme'

type Tab = 'in' | 'up'

// Sample admin account (front-end demo stub — no real backend yet).
const ADMIN_EMAIL = 'admin@sonoxr.com'
const ADMIN_PASS = 'admin1234'

const labelStyle: CSSProperties = {
  fontFamily: FONT_MONO,
  fontSize: 10.5,
  letterSpacing: '.12em',
  color: C.textMuted,
  textTransform: 'uppercase',
}
const inputStyle: CSSProperties = {
  padding: '13px 15px',
  border: '1px solid rgba(255,255,255,.12)',
  borderRadius: 10,
  background: 'rgba(255,255,255,.03)',
  color: '#EEF1F5',
  fontFamily: FONT_BODY,
  fontSize: 14.5,
  transition: 'border-color .2s, background .2s',
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from || '/dashboard'
  const [tab, setTab] = useState<Tab>('in')
  const [email, setEmail] = useState('')
  const [pass, setPass] = useState('')
  const [err, setErr] = useState('')
  const [ok, setOk] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !email.includes('@')) {
      setOk(false)
      setErr('Enter a valid email address.')
      return
    }
    if (!pass || pass.length < 4) {
      setOk(false)
      setErr('Enter your password (4+ characters).')
      return
    }
    setOk(true)
    // Front-end stub: the sample admin account gets the 'admin' role. TODO: replace
    // with a real auth provider + server-side roles.
    const role = email.trim().toLowerCase() === ADMIN_EMAIL ? 'admin' : 'clinician'
    setErr(
      role === 'admin'
        ? 'Signed in as admin — opening console…'
        : tab === 'up'
          ? 'Account created — opening console…'
          : 'Signed in — opening console…',
    )
    localStorage.setItem('sonoxr_user', email)
    localStorage.setItem('sonoxr_role', role)
    window.setTimeout(() => navigate(from, { replace: true }), 700)
  }

  const tabBtn = (t: Tab, label: string) => (
    <button
      type="button"
      onClick={() => {
        setTab(t)
        setErr('')
      }}
      style={{
        flex: 1,
        padding: 10,
        border: 'none',
        borderRadius: 8,
        background: tab === t ? C.blue : 'transparent',
        color: tab === t ? '#06121f' : '#C7CDD6',
        fontFamily: FONT_BODY,
        fontWeight: 600,
        fontSize: 14,
        cursor: 'pointer',
        transition: 'background .2s, color .2s',
      }}
    >
      {label}
    </button>
  )

  return (
    <section
      style={{
        position: 'relative',
        width: '100%',
        minHeight: '100vh',
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        background: C.bg,
        color: '#EEF1F5',
        fontFamily: FONT_BODY,
      }}
      className="login-grid"
    >
      {/* LEFT: brand panel */}
      <div
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '40px 48px',
          background:
            'radial-gradient(120% 90% at 30% 20%, #14171F 0%, #0A0C11 50%, #07090B 100%)',
          overflow: 'hidden',
          minHeight: '100vh',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            background:
              'radial-gradient(48% 42% at 40% 48%, rgba(225,29,51,0.18) 0%, rgba(225,29,51,0) 62%)',
          }}
        />
        <Link
          to="/"
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            gap: 13,
            textDecoration: 'none',
            color: 'inherit',
          }}
        >
          <div
            style={{
              width: 13,
              height: 13,
              borderRadius: '50%',
              background: C.red,
              boxShadow: '0 0 16px 3px rgba(225,29,51,.6)',
              animation: 'sonoPulse 1s ease-in-out infinite',
            }}
          />
          <span style={{ fontFamily: FONT_DISPLAY, fontWeight: 700, fontSize: 19 }}>SonoXR</span>
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: '.16em',
              color: C.textDim,
              textTransform: 'uppercase',
            }}
          >
            EchoAR
          </span>
        </Link>

        <div
          style={{
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 30,
            margin: 'auto 0',
          }}
        >
          <div
            style={{
              width: 150,
              height: 150,
              borderRadius: '50%',
              background: 'radial-gradient(circle at 38% 34%, #ff5566, #E11D33 42%, #7a0f1d 100%)',
              boxShadow: '0 0 70px -8px rgba(225,29,51,.65), inset -14px -18px 40px rgba(0,0,0,.5)',
              animation: 'appBeat 1s ease-in-out infinite',
            }}
          />
          <div style={{ textAlign: 'center', maxWidth: 380 }}>
            <div
              style={{
                fontFamily: FONT_DISPLAY,
                fontWeight: 600,
                fontSize: 22,
                lineHeight: 1.25,
                color: C.textPrimary,
                marginBottom: 10,
                textWrap: 'balance' as CSSProperties['textWrap'],
              }}
            >
              The Quest 3 demo, in your browser.
            </div>
            <div style={{ fontSize: 14, lineHeight: 1.55, color: C.textMuted2 }}>
              Sign in to open the cardiac console — five reconstructed echoes with the honesty
              layer, ready for web or headset.
            </div>
          </div>
        </div>

        <div
          style={{
            position: 'relative',
            display: 'flex',
            gap: 22,
            flexWrap: 'wrap',
            fontFamily: FONT_MONO,
            fontSize: 10.5,
            letterSpacing: '.12em',
            color: C.textDim2,
            textTransform: 'uppercase',
          }}
        >
          <span>Meta Quest 3</span>
          <span>·</span>
          <span>Voice by Deepgram</span>
          <span>·</span>
          <span>Not clinical advice</span>
        </div>
      </div>

      {/* RIGHT: auth form */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '40px 8vw',
          minHeight: '100vh',
          position: 'relative',
        }}
      >
        <Link
          to="/"
          style={{
            position: 'absolute',
            top: 30,
            right: 36,
            fontFamily: FONT_MONO,
            fontSize: 11,
            letterSpacing: '.12em',
            color: C.textDim,
            textTransform: 'uppercase',
            textDecoration: 'none',
          }}
        >
          ← Back to site
        </Link>

        <div style={{ maxWidth: 400, width: '100%', margin: '0 auto', animation: 'appUp .5s ease both' }}>
          <div
            style={{
              fontFamily: FONT_DISPLAY,
              fontWeight: 700,
              fontSize: 30,
              letterSpacing: '-0.02em',
              color: C.textPrimary,
              marginBottom: 8,
            }}
          >
            {tab === 'up' ? 'Create your account' : 'Welcome back'}
          </div>
          <div style={{ fontSize: 14.5, color: C.textMuted2, marginBottom: 28 }}>
            {tab === 'up'
              ? 'Set up access to the SonoXR console.'
              : 'Sign in to launch the SonoXR console.'}
          </div>

          <div
            style={{
              display: 'inline-flex',
              width: '100%',
              padding: 4,
              border: '1px solid rgba(255,255,255,.1)',
              borderRadius: 11,
              background: 'rgba(255,255,255,.03)',
              marginBottom: 24,
            }}
          >
            {tabBtn('in', 'Sign in')}
            {tabBtn('up', 'Create account')}
          </div>

          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {tab === 'up' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <label style={labelStyle}>Full name</label>
                <input className="app-input" type="text" placeholder="Dr. Maria Reyes" style={inputStyle} />
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <label style={labelStyle}>Email</label>
              <input
                className="app-input"
                type="email"
                placeholder="you@hospital.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={inputStyle}
              />
            </div>
            {tab === 'up' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <label style={labelStyle}>Institution</label>
                <input className="app-input" type="text" placeholder="UCSF Medical Center" style={inputStyle} />
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <label style={labelStyle}>Password</label>
              <input
                className="app-input"
                type="password"
                placeholder="••••••••"
                value={pass}
                onChange={(e) => setPass(e.target.value)}
                style={inputStyle}
              />
            </div>
            <button
              type="submit"
              className="app-redbtn"
              style={{
                marginTop: 8,
                padding: 14,
                border: 'none',
                borderRadius: 10,
                background: C.red,
                color: '#fff',
                fontFamily: FONT_BODY,
                fontWeight: 600,
                fontSize: 15,
                cursor: 'pointer',
                boxShadow: '0 8px 26px -8px rgba(225,29,51,.6)',
              }}
            >
              {tab === 'up' ? 'Create account & launch' : 'Sign in & launch console'}
            </button>
            <div style={{ fontSize: 12.5, color: ok ? C.greenText : C.redBright2, minHeight: 16 }}>
              {err}
            </div>
          </form>

          {/* sample admin account (demo stub) */}
          <div
            style={{
              marginTop: 18,
              padding: '12px 14px',
              border: '1px solid rgba(255,255,255,.1)',
              borderRadius: 10,
              background: 'rgba(255,255,255,.02)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              flexWrap: 'wrap',
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: FONT_MONO,
                  textTransform: 'uppercase',
                  fontSize: 10,
                  letterSpacing: '.14em',
                  color: C.textDim,
                  marginBottom: 4,
                }}
              >
                Sample admin
              </div>
              <div style={{ fontSize: 12.5, color: C.textMuted2 }}>
                {ADMIN_EMAIL} · {ADMIN_PASS}
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                setTab('in')
                setEmail(ADMIN_EMAIL)
                setPass(ADMIN_PASS)
                setErr('')
              }}
              style={{
                padding: '8px 14px',
                border: '1px solid rgba(79,168,255,.4)',
                borderRadius: 8,
                background: 'rgba(79,168,255,.08)',
                color: C.blueText,
                fontFamily: FONT_BODY,
                fontWeight: 600,
                fontSize: 12.5,
                cursor: 'pointer',
              }}
            >
              Use sample admin
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
