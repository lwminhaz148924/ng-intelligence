import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Send,
  Plus,
  LogOut,
  Menu,
  X,
  Shield,
  KeyRound,
  Sparkles,
  MessageSquare,
  Trash2,
  ChevronRight,
  UserCircle,
  Settings,
  Upload,
  CheckCircle,
  Download,
  FileText
} from 'lucide-react'
import './styles.css'

const API =
  import.meta.env.VITE_API_URL || 'https://ng-intelligence.onrender.com'

const token = () => localStorage.getItem('ng_token')

// Keep provider and infrastructure details private. Only NG INTELLIGENCE's
// own user-safe language is allowed to reach the interface.
function brandedErrorMessage(message, status = 0) {
  const raw = String(message || '').toLowerCase()
  if (status === 401 || raw.includes('invalid email or password')) return 'আপনার ইমেইল অথবা পাসওয়ার্ড সঠিক নয়। আবার চেষ্টা করুন।'
  if (status === 403 || raw.includes('account is disabled')) return 'এই অ্যাকাউন্টে প্রবেশ করা যাচ্ছে না। সহায়তার জন্য NG INTELLIGENCE সাপোর্টের সঙ্গে যোগাযোগ করুন।'
  if (status === 404 && raw.includes('chat')) return 'কথোপকথনটি খুঁজে পাওয়া যায়নি। পেজটি রিফ্রেশ করে আবার চেষ্টা করুন।'
  if (status === 429 || raw.includes('too many requests')) return 'আপনি অল্প সময়ে অনেকগুলো অনুরোধ পাঠিয়েছেন। কিছুক্ষণ অপেক্ষা করে আবার চেষ্টা করুন।'
  if (status >= 500 || !message || /gemini|google|provider|api key|candidate|finishreason|max_tokens|model|upstream|internal server|network|fetch failed/i.test(raw)) {
    return 'NG INTELLIGENCE এই মুহূর্তে আপনার অনুরোধটি সম্পন্ন করতে পারছে না। অনুগ্রহ করে একটু পরে আবার চেষ্টা করুন।'
  }
  // Do not expose technical exception text, stack traces, or provider names.
  if (/exception|traceback|http|sql|database|connection|timeout|502|503|504/i.test(raw)) {
    return 'একটি সাময়িক সমস্যা হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।'
  }
  return String(message)
}

async function api(path, opt = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(opt.headers || {})
  }

  if (token()) {
    headers.Authorization = 'Bearer ' + token()
  }

  const r = await fetch(API + path, {
    ...opt,
    headers
  })

  const d = await r.json().catch(() => ({}))

  if (!r.ok) {
    throw Error(brandedErrorMessage(d.detail || 'Request failed', r.status))
  }

  return d
}

/* =========================
   BRAND
========================= */

function Brand() {
  const [branding, setBranding] = useState(null)

  useEffect(() => {
    api('/api/branding').then(setBranding).catch(() => {})
  }, [])

  return (
    <div className="brand">
      {branding?.logo_data ? (
        <img className="brandlogo" src={branding.logo_data} alt="NG INTELLIGENCE" />
      ) : (
        <span className="brandmark">N</span>
      )}
      <div>
        <b>NG INTELLIGENCE</b>
        <small>INTELLIGENCE, REIMAGINED.</small>
      </div>
    </div>
  )
}

/* =========================
   AUTH
========================= */

function Verification({ email, onVerified, onBack }) {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [resent, setResent] = useState(false)
  const [verified, setVerified] = useState(false)

  async function verify(e) {
    e.preventDefault()
    if (!/^\d{6}$/.test(code)) return setErr('Enter the 6-digit verification code.')
    setBusy(true)
    setErr('')
    try {
      const d = await api('/api/auth/verify', {
        method: 'POST', body: JSON.stringify({ email, code })
      })
      localStorage.setItem('ng_token', d.token)
      setVerified(true)
      setCode('')
      window.setTimeout(() => onVerified(d.user), 850)
    } catch (x) {
      setErr(x.message)
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    setBusy(true); setErr('')
    try {
      await api('/api/auth/resend-verification', {
        method: 'POST', body: JSON.stringify({ email })
      })
      setResent(true)
      setTimeout(() => setResent(false), 2500)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  return (
    <AuthShell>
      <div className={'verify-icon ' + (verified ? 'verified' : '')}><CheckCircle size={28} /></div>
      <div className="authcopy">
        <span className="eyebrow">VERIFY YOUR EMAIL</span>
        <h1>{verified ? 'Verified!' : 'Almost there.'}</h1>
        <p>{verified ? 'Your email has been successfully verified.' : <>We sent a 6-digit verification code to <b>{email}</b>.</>}</p>
      </div>
      <form onSubmit={verify}>
        <label>Verification code
          <input className="otpinput" inputMode="numeric" maxLength={6} value={code} onChange={e => setCode(e.target.value.replace(/\D/g,'').slice(0,6))} placeholder="000000" autoFocus required />
        </label>
        {busy && !verified && <div className="verify-progress"><span className="spinner" /> Verifying your email…</div>}
        {verified && <div className="verify-progress verified-text"><CheckCircle size={17}/> Verified successfully</div>}
        {err && <div className="error">{err}</div>}
        {resent && <div className="success">A new verification code was sent.</div>}
        <button className="gradientbtn authbtn" disabled={busy || code.length !== 6} type="submit">{verified ? 'Verified ✓' : busy ? 'Verifying…' : 'Verify email'}</button>
      </form>
      <div className="authlinks">
        <button onClick={resend} disabled={busy}>Resend code</button>
        <button onClick={onBack} disabled={busy}>Use another email</button>
      </div>
    </AuthShell>
  )
}

function AuthShell({ children }) {
  return <div className="auth"><div className="glow g1" /><div className="glow g2" /><div className="authbox"><Brand />{children}</div></div>
}

function Auth({ done }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [pass, setPass] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [pendingEmail, setPendingEmail] = useState('')

  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const d = await api('/api/auth/' + mode, { method:'POST', body:JSON.stringify({ email, password:pass }) })
      if (mode === 'register' && d.verification_required) {
        setPendingEmail(d.email); setMode('verify'); return
      }
      localStorage.setItem('ng_token', d.token); done(d.user)
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  async function forgot(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      await api('/api/auth/forgot-password', { method:'POST', body:JSON.stringify({ email }) })
      setPendingEmail(email.trim().toLowerCase()); setMode('reset')
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  async function reset(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      await api('/api/auth/reset-password', { method:'POST', body:JSON.stringify({ email:pendingEmail, code:pass.split(':')[0], new_password:pass.split(':')[1] || '' }) })
      setEmail(pendingEmail); setPass(''); setMode('login')
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }

  if (mode === 'verify') return <Verification email={pendingEmail} onVerified={done} onBack={() => setMode('register')} />

  if (mode === 'forgot') {
    return <AuthShell><div className="verify-icon"><KeyRound size={27} /></div><div className="authcopy"><span className="eyebrow">ACCOUNT RECOVERY</span><h1>Reset your password.</h1><p>Enter your account email and we’ll send a reset code.</p></div><form onSubmit={forgot}><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required /></label>{err && <div className="error">{err}</div>}<button className="gradientbtn authbtn" disabled={busy} type="submit">{busy ? 'Sending code…' : 'Send reset code'}</button></form><div className="authlinks"><button onClick={()=>setMode('login')}>Back to sign in</button></div></AuthShell>
  }

  if (mode === 'reset') {
    return <AuthShell>
      <div className="verify-icon"><KeyRound size={27} /></div>
      <div className="authcopy"><span className="eyebrow">RESET PASSWORD</span><h1>Create a new password.</h1><p>Enter the code sent to <b>{pendingEmail}</b>.</p></div>
      <form onSubmit={reset}>
        <label>Reset code<input inputMode="numeric" maxLength={6} value={pass.split(':')[0]} onChange={e => setPass(e.target.value.replace(/\D/g,'').slice(0,6)+':'+(pass.split(':')[1]||''))} placeholder="000000" required /></label>
        <label>New password<input type="password" minLength={8} value={pass.split(':')[1]||''} onChange={e => setPass((pass.split(':')[0]||'')+':'+e.target.value)} placeholder="Minimum 8 characters" required /></label>
        {err && <div className="error">{err}</div>}
        <button className="gradientbtn authbtn" disabled={busy} type="submit">{busy ? 'Resetting…' : 'Reset password'}</button>
      </form>
      <div className="authlinks"><button onClick={() => setMode('login')}>Back to sign in</button></div>
    </AuthShell>
  }

  return <AuthShell>
    <div className="authcopy"><span className="eyebrow">{mode==='login' ? 'PRIVATE AI WORKSPACE' : 'CREATE YOUR WORKSPACE'}</span><h1>{mode==='login' ? 'Welcome back.' : 'Start building.'}</h1><p>{mode==='login' ? 'Sign in to continue to your intelligent workspace.' : 'Create a private NG INTELLIGENCE account.'}</p></div>
    <form onSubmit={mode === 'login' ? submit : submit}>
      <label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com" required /></label>
      <label>Password<input type="password" value={pass} onChange={e=>setPass(e.target.value)} placeholder="Minimum 8 characters" minLength="8" required /></label>
      {mode === 'login' && <button className="forgotlink" type="button" onClick={() => {setErr('');setMode('forgot')}}>Forgot password?</button>}
      {err && <div className="error">{err}</div>}
      <button className="gradientbtn authbtn" disabled={busy} type="submit">{busy ? 'Please wait…' : mode==='login' ? 'Sign in' : 'Create account'}</button>
    </form>
    <div className="switch">{mode==='login' ? 'New to NG INTELLIGENCE?' : 'Already have an account?'} <button onClick={()=>{setErr('');setMode(mode==='login'?'register':'login')}}>{mode==='login'?'Create account':'Sign in'}</button></div>
    {mode === 'forgot' && <div className="authlinks"><button onClick={()=>setMode('login')}>Back to sign in</button></div>}
  </AuthShell>
}
/* =========================
   ADMIN
========================= */

function Admin({ close }) {
  const [tab, setTab] = useState('overview')
  const [keys, setKeys] = useState([])
  const [stats, setStats] = useState(null)
  const [users, setUsers] = useState([])
  const [settings, setSettings] = useState({
    model: '',
    system_prompt: ''
  })
  const [logs, setLogs] = useState([])
  const [branding, setBranding] = useState({ logo_data: '' })

  const load = async () => {
    try {
      if (tab === 'overview') {
        setStats(await api('/api/admin/stats'))
      }

      if (tab === 'keys') {
        setKeys(await api('/api/admin/keys'))
      }

      if (tab === 'users') {
        setUsers(await api('/api/admin/users'))
      }

      if (tab === 'settings') {
        setSettings(await api('/api/admin/settings'))
      }

      if (tab === 'logs') {
        setLogs(await api('/api/admin/logs'))
      }
      if (tab === 'branding') {
        setBranding(await api('/api/admin/branding'))
      }
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    load()
  }, [tab])

  return (
    <div className="modal">
      <div className="admin">
        <div className="adminhead">
          <div>
            <span className="eyebrow">
              CONTROL CENTER
            </span>

            <h2>NG INTELLIGENCE Admin</h2>
          </div>

          <button
            className="icon"
            onClick={close}
          >
            <X />
          </button>
        </div>

        <div className="admintabs">
          {[
            ['overview', 'Overview'],
            ['keys', 'Gemini Keys'],
            ['settings', 'AI Settings'],
            ['users', 'Users'],
            ['logs', 'Logs'],
            ['branding', 'Branding']
          ].map(x => (
            <button
              className={tab === x[0] ? 'active' : ''}
              onClick={() => setTab(x[0])}
              key={x[0]}
            >
              {x[1]}
            </button>
          ))}
        </div>

        {tab === 'overview' && stats && (
          <div className="statgrid">
            {[
              ['Users', stats.users],
              ['Chats', stats.chats],
              ['Messages', stats.messages],
              ['Characters', stats.characters],
              ['Logs', stats.logs]
            ].map(x => (
              <div className="stat" key={x[0]}>
                <span>{x[0]}</span>
                <b>
                  {Number(x[1]).toLocaleString()}
                </b>
              </div>
            ))}
          </div>
        )}

        {tab === 'keys' && (
          <Keys
            keys={keys}
            reload={load}
          />
        )}

        {tab === 'settings' && (
          <SettingsPanel
            data={settings}
            reload={load}
          />
        )}

        {tab === 'users' && (
          <div className="table">
            {users.map(x => (
              <div
                className="row"
                key={x.id}
              >
                <div>
                  <b>{x.email}</b>

                  <small>
                    {x.role} ·{' '}
                    {x.active
                      ? 'Active'
                      : 'Disabled'}
                  </small>
                </div>

                <button
                  onClick={() =>
                    api(
                      '/api/admin/users/' +
                        x.id +
                        '/toggle',
                      {
                        method: 'PATCH'
                      }
                    ).then(load)
                  }
                >
                  {x.active
                    ? 'Disable'
                    : 'Enable'}
                </button>
              </div>
            ))}
          </div>
        )}

        {tab === 'branding' && (
          <BrandingPanel data={branding} reload={load} />
        )}

        {tab === 'logs' && (
          <div className="logs">
            {logs.map(x => (
              <div
                className="log"
                key={x.id}
              >
                <b>{x.event}</b>

                <span>{x.status}</span>

                <small>
                  {x.details} ·{' '}
                  {x.created_at}
                </small>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/* =========================
   GEMINI KEYS
========================= */

function Keys({ keys, reload }) {
  const [label, setLabel] =
    useState('Primary Gemini')

  const [key, setKey] =
    useState('')

  return (
    <div>
      <div className="notice">
        <KeyRound />

        <div>
          <b>
            Secure Gemini key management
          </b>

          <p>
            Keys are encrypted at rest and
            never rendered back to the browser.
          </p>
        </div>
      </div>

      {keys.map(k => (
        <div
          className="row"
          key={k.id}
        >
          <div>
            <b>{k.label}</b>

            <small>
              {k.active
                ? 'Active'
                : 'Disabled'}{' '}
              · {k.created_at}
            </small>
          </div>

          <button
            onClick={() =>
              api(
                '/api/admin/keys/' +
                  k.id,
                {
                  method: 'PATCH'
                }
              ).then(reload)
            }
          >
            {k.active
              ? 'Disable'
              : 'Enable'}
          </button>

          <button
            onClick={() =>
              api(
                '/api/admin/keys/' +
                  k.id,
                {
                  method: 'DELETE'
                }
              ).then(reload)
            }
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}

      <div className="add">
        <input
          value={label}
          onChange={e =>
            setLabel(e.target.value)
          }
          placeholder="Key label"
        />

        <input
          value={key}
          onChange={e =>
            setKey(e.target.value)
          }
          placeholder="Gemini API key"
        />

        <button
          className="gradientbtn"
          onClick={() =>
            api('/api/admin/keys', {
              method: 'POST',
              body: JSON.stringify({
                label,
                key
              })
            }).then(() => {
              setKey('')
              reload()
            })
          }
        >
          Add key
        </button>
      </div>
    </div>
  )
}

function BrandingPanel({ data, reload }) {
  const [logo, setLogo] = useState(data.logo_data || '')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  async function choose(e) {
    const file=e.target.files?.[0]; if(!file) return
    if(file.size > 2*1024*1024) return setMsg('Logo must be 2 MB or smaller.')
    const reader=new FileReader(); reader.onload=()=>setLogo(reader.result); reader.readAsDataURL(file)
  }
  async function save() {
    setBusy(true); setMsg('')
    try { await api('/api/admin/branding',{method:'PUT',body:JSON.stringify({logo_data:logo})}); setMsg('Website logo saved.'); reload() }
    catch(e){setMsg(e.message)} finally{setBusy(false)}
  }
  return <div className="settings branding-panel"><span className="eyebrow">WEBSITE BRANDING</span><h3>Website logo</h3><p>Upload the logo that appears across NG INTELLIGENCE.</p><div className="logo-preview">{logo ? <img src={logo} alt="Website logo" /> : <span>N</span>}</div><label className="uploadbox"><Upload size={17}/> Choose logo<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={choose}/></label>{msg&&<div className="success">{msg}</div>}<button className="gradientbtn" onClick={save} disabled={busy}>{busy?'Saving…':'Save website logo'}</button></div>
}

/* =========================
   SETTINGS
========================= */

function SettingsPanel({
  data,
  reload
}) {
  const [model, setModel] =
    useState(data.model)

  const [prompt, setPrompt] =
    useState(data.system_prompt)

  return (
    <div className="settings">
      <label>
        Gemini model

        <input
          value={model}
          onChange={e =>
            setModel(e.target.value)
          }
        />
      </label>

      <label>
        System prompt

        <textarea
          value={prompt}
          onChange={e =>
            setPrompt(e.target.value)
          }
        />
      </label>

      <button
        className="gradientbtn"
        onClick={async () => {
          await api(
            '/api/admin/settings',
            {
              method: 'PUT',
              body: JSON.stringify({
                name: 'model',
                value: model
              })
            }
          )

          await api(
            '/api/admin/settings',
            {
              method: 'PUT',
              body: JSON.stringify({
                name: 'system_prompt',
                value: prompt
              })
            }
          )

          reload()
        }}
      >
        Save AI configuration
      </button>
    </div>
  )
}

/* =========================
   TYPING INDICATOR
========================= */

function TypingIndicator({ siteLogo, continuationStatus }) {
  return (
    <div
      className="msg assistant typingmsg"
      role="status"
      aria-label="NG INTELLIGENCE is responding"
    >
      <div className="avatar ai-avatar">
        {siteLogo ? <img src={siteLogo} alt="NG INTELLIGENCE" /> : 'N'}
      </div>

      <div className="typingbubble">
        <span className="typinglabel">{continuationStatus || 'Thinking'}</span>
        <span className="typingdot" />
        <span className="typingdot" />
        <span className="typingdot" />
      </div>
    </div>
  )
}

/* =========================
   MESSAGE BUBBLE
========================= */

function parseGeneratedFiles(raw = '') {
  const marker = /\n?\n?<!--NG_CONTINUATION_PARTS:(\d+);COMPLETE:([01])-->\s*$/i
  const metaMatch = raw.match(marker)
  const continuation = metaMatch
    ? { parts: Number(metaMatch[1]), complete: metaMatch[2] === '1' }
    : null
  const withoutMeta = raw.replace(marker, '').trim()
  const files = []
  const pattern = /<FILE\s+path=["\']([^"\']+)["\']\s*>([\s\S]*?)<\/FILE>/gi
  let match
  while ((match = pattern.exec(withoutMeta)) !== null) {
    files.push({ path: match[1].trim(), content: match[2].trim() })
  }
  const content = withoutMeta
    .replace(pattern, '')
    .replace(/<\/?FILE(?:\s+[^>]*)?>/gi, '')
    .trim()
  return { content, files, continuation }
}

function downloadGeneratedFile(file) {
  const blob = new Blob([file.content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = file.path.replaceAll('/', '__') || 'generated-file.txt'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function MessageBubble({
  message,
  index,
  userAvatar,
  siteLogo
}) {
  const isAI = message.role === 'assistant'
  const parsed = isAI ? parseGeneratedFiles(message.content || '') : { content: message.content || '', files: [] }
  const files = message.files?.length ? message.files : parsed.files

  return (
    <div
      className={
        'msg ' +
        message.role +
        ' message-enter'
      }
      style={{
        animationDelay:
          `${Math.min(index * 35, 180)}ms`
      }}
    >
      <div
        className={
          'avatar ' +
          (isAI ? 'ai-avatar' : '')
        }
      >
        {isAI
          ? (siteLogo ? <img src={siteLogo} alt="NG INTELLIGENCE" /> : 'N')
          : (userAvatar ? <img src={userAvatar} alt="Your profile" /> : 'U')}
      </div>

      <div className="content">
        {parsed.content && (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {parsed.content}
          </ReactMarkdown>
        )}

        {isAI && files.length > 0 && (
          <div className="generated-files">
            <div className="generated-files-heading">
              <span><FileText size={16} /> Generated files</span>
              <small>{files.length} {files.length === 1 ? 'file' : 'files'}</small>
            </div>
            {files.map((file, fileIndex) => (
              <div className="generated-file" key={`${file.path}-${fileIndex}`}>
                <div className="generated-file-info">
                  <FileText size={18} />
                  <div>
                    <b>{file.path}</b>
                    <small>{new Blob([file.content || '']).size.toLocaleString()} bytes</small>
                  </div>
                </div>
                <button type="button" className="generated-file-download" onClick={() => downloadGeneratedFile(file)} aria-label={`Download ${file.path}`}>
                  <Download size={16} /> Download
                </button>
              </div>
            ))}
          </div>
        )}

        {isAI && parsed.continuation && (
          <div
            className={`continuation-note ${parsed.continuation.complete ? '' : 'continuation-warning'}`}
            style={{
              marginTop: 12,
              padding: '9px 12px',
              borderRadius: 10,
              fontSize: 12,
              lineHeight: 1.5,
              color: parsed.continuation.complete ? 'inherit' : '#92400e',
              background: parsed.continuation.complete ? 'rgba(100,116,139,.08)' : 'rgba(234,179,8,.10)',
              border: `1px solid ${parsed.continuation.complete ? 'rgba(100,116,139,.14)' : 'rgba(234,179,8,.25)'}`
            }}
          >
            {parsed.continuation.complete
              ? `${parsed.files.length ? '↪ File output' : '↪ Text output'} automatically continued and assembled (${parsed.continuation.parts} parts).`
              : `⚠️ ${parsed.files.length ? 'File' : 'Text'} output reached the automatic continuation limit after ${parsed.continuation.parts} parts; the result may be incomplete.`}
          </div>
        )}

        {isAI && (
          <div className="message-glow" />
        )}
      </div>
    </div>
  )
}

function ProfilePanel({ user, onClose, onSaved }) {
  const [avatar, setAvatar] = useState(user.avatar_data || '')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  async function choose(e) {
    const file=e.target.files?.[0]; if(!file) return
    if(file.size > 2*1024*1024) return setMsg('Profile photo must be 2 MB or smaller.')
    const reader=new FileReader(); reader.onload=()=>setAvatar(reader.result); reader.readAsDataURL(file)
  }
  async function save() {
    setBusy(true); setMsg('')
    try { const d=await api('/api/profile',{method:'PUT',body:JSON.stringify({avatar_data:avatar})}); onSaved(d.user); setMsg('Profile photo updated.') } catch(e){setMsg(e.message)} finally{setBusy(false)}
  }
  return <div className="profile-overlay" onClick={onClose}><div className="profile-card" onClick={e=>e.stopPropagation()}><div className="profile-head"><div><span className="eyebrow">PROFILE & SETTINGS</span><h2>Your profile</h2></div><button className="icon" onClick={onClose}><X/></button></div><div className="profile-avatar">{avatar?<img src={avatar} alt="Profile"/>:<UserCircle size={42}/>}</div><label className="uploadbox"><Upload size={17}/> Upload profile photo<input type="file" accept="image/png,image/jpeg,image/webp" onChange={choose}/></label><div className="profile-email"><span>Email</span><b>{user.email}</b><small>Your account email is your permanent login identity.</small></div>{msg&&<div className="success">{msg}</div>}<button className="gradientbtn" onClick={save} disabled={busy}>{busy?'Saving…':'Save profile'}</button></div></div>
}

/* =========================
   MAIN APP
========================= */

function App() {
  const [user, setUser] =
    useState(null)
  const [siteLogo, setSiteLogo] = useState('')
  const messagesEndRef = useRef(null)

  useEffect(() => {
    api('/api/branding').then(data => setSiteLogo(data.logo_data || '')).catch(() => {})
  }, [])

  const [side, setSide] =
    useState(true)

  const [chats, setChats] =
    useState([])

  const [cid, setCid] =
    useState(null)

  const [msgs, setMsgs] =
    useState([])

  const [input, setInput] =
    useState('')

  const [busy, setBusy] =
    useState(false)
  const [revealing, setRevealing] = useState(false)
  const [continuationStatus, setContinuationStatus] = useState('')

  const [admin, setAdmin] =
    useState(false)
  const [profile, setProfile] = useState(false)

  useEffect(() => {
    if (msgs.length > 0 || busy) {
      messagesEndRef.current?.scrollIntoView({
        behavior: revealing ? 'auto' : 'smooth',
        block: 'end'
      })
    }
  }, [msgs, busy, revealing])

  useEffect(() => {
    if (token()) {
      api('/api/me')
        .then(setUser)
        .catch(() => {
          localStorage.removeItem(
            'ng_token'
          )
        })
    }
  }, [])

  useEffect(() => {
    if (!user) return

    // Show the last known conversation list immediately while the database loads.
    const cacheKey = `ng_chat_list_${user.id}`
    let cachedChats = []
    try {
      const saved = JSON.parse(localStorage.getItem(cacheKey) || '[]')
      if (Array.isArray(saved)) cachedChats = saved
    } catch (e) {
      console.warn('Could not read cached conversations:', e)
    }
    if (cachedChats.length) setChats(cachedChats)

    loadChats().then(async (items) => {
      const savedId = localStorage.getItem(`ng_active_chat_${user.id}`)
      if (savedId && items.some(item => String(item.id) === savedId)) {
        await openChat(Number(savedId))
      }
    })

    // Refresh when the user returns to the tab, without clearing the list on a transient failure.
    const refreshChats = () => {
      if (document.visibilityState === 'visible') loadChats()
    }
    window.addEventListener('focus', refreshChats)
    document.addEventListener('visibilitychange', refreshChats)
    return () => {
      window.removeEventListener('focus', refreshChats)
      document.removeEventListener('visibilitychange', refreshChats)
    }
  }, [user])

  async function loadChats() {
    const cacheKey = user?.id ? `ng_chat_list_${user.id}` : null
    let cachedChats = []
    if (cacheKey) {
      try {
        const saved = JSON.parse(localStorage.getItem(cacheKey) || '[]')
        if (Array.isArray(saved)) cachedChats = saved
      } catch (e) {
        console.warn('Could not read cached conversations:', e)
      }
    }

    try {
      const items = await api('/api/chats')
      if (!Array.isArray(items)) throw Error('Invalid conversation list response')

      // A temporary empty response must not erase a previously populated sidebar.
      if (items.length === 0 && cachedChats.length > 0) {
        setChats(current => current.length ? current : cachedChats)
        return cachedChats
      }

      setChats(items)
      if (cacheKey) localStorage.setItem(cacheKey, JSON.stringify(items))
      return items
    } catch (e) {
      console.error('Could not refresh conversations; keeping the last saved list.', e)
      if (cachedChats.length) setChats(current => current.length ? current : cachedChats)
      return cachedChats
    }
  }

  async function openChat(id) {
    try {
      setCid(id)
      if (user?.id) localStorage.setItem(`ng_active_chat_${user.id}`, String(id))

      setMsgs(
        await api(
          '/api/chats/' + id
        )
      )
    } catch (e) {
      console.error(e)
    }
  }

  async function send() {
    const text = input.trim()
    if (!text || busy) return

    const requestId = (window.crypto && window.crypto.randomUUID)
      ? window.crypto.randomUUID()
      : `ng_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`

    setInput('')
    setMsgs(m => [...m, { role: 'user', content: text }])
    setBusy(true)
    setRevealing(false)
    setContinuationStatus('')

    let polling = true
    const pollProgress = async () => {
      while (polling) {
        try {
          const progress = await api(`/api/chat/progress/${requestId}`)
          if (progress.status === 'continuing') {
            setContinuationStatus(`পরবর্তী অংশ তৈরি হচ্ছে — Part ${progress.part}...`)
          } else if (progress.status === 'generating') {
            setContinuationStatus('')
          } else if (progress.status === 'completed') {
            setContinuationStatus('সব অংশ একত্র করা হচ্ছে...')
          } else if (progress.status === 'limit_reached') {
            setContinuationStatus('আউটপুটের সর্বোচ্চ অংশ তৈরি হয়েছে...')
          }
        } catch (_) {
          // The chat request remains authoritative if progress polling fails.
        }
        await new Promise(resolve => window.setTimeout(resolve, 1000))
      }
    }
    const progressTask = pollProgress()

    try {
      const d = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, chat_id: cid, request_id: requestId })
      })

      polling = false
      await progressTask
      setCid(d.chat_id)
      if (user?.id) localStorage.setItem(`ng_active_chat_${user.id}`, String(d.chat_id))

      const fullAnswer = String(d.answer || '')
      setContinuationStatus('')
      setRevealing(true)
      setMsgs(m => [...m, { role: 'assistant', content: '' }])

      // Reveal the fully assembled response only after all continuation parts
      // have been collected and saved by the backend.
      const chunkSize = Math.max(3, Math.ceil(fullAnswer.length / 700))
      for (let index = 0; index < fullAnswer.length; index += chunkSize) {
        const visible = fullAnswer.slice(0, index + chunkSize)
        setMsgs(current => {
          const next = [...current]
          const last = next[next.length - 1]
          if (last?.role === 'assistant') {
            next[next.length - 1] = { ...last, content: visible }
          }
          return next
        })
        await new Promise(resolve => window.setTimeout(resolve, 12))
      }

      setMsgs(current => {
        const next = [...current]
        const last = next[next.length - 1]
        if (last?.role === 'assistant') next[next.length - 1] = { ...last, content: fullAnswer }
        return next
      })
      loadChats()
    } catch (e) {
      polling = false
      await progressTask
      setContinuationStatus('')
      setRevealing(false)
      setMsgs(m => [...m, { role: 'assistant', content: '**NG INTELLIGENCE**\n\n' + brandedErrorMessage(e.message) }])
    } finally {
      polling = false
      setContinuationStatus('')
      setRevealing(false)
      setBusy(false)
    }
  }

  function logout() {
    localStorage.removeItem(
      'ng_token'
    )

    setUser(null)
  }

  if (!user) {
    return (
      <Auth done={setUser} />
    )
  }

  return (
    <div className={'app ' + (side ? 'sidebar-open' : 'sidebar-closed')}>
      {/* HEADER */}

      <header>
        <button
          className="icon"
          onClick={() =>
            setSide(!side)
          }
        >
          {side ? (
            <X />
          ) : (
            <Menu />
          )}
        </button>

        <Brand />

        <div className="top">
          <span className="online">
            <i />
            ONLINE
          </span>

          {user.role === 'admin' && (
            <button
              className="icon"
              onClick={() =>
                setAdmin(true)
              }
            >
              <Shield />
            </button>
          )}

          <button className="profile-trigger" onClick={() => setProfile(true)} title="Profile settings">
            {user.avatar_data ? <img src={user.avatar_data} alt="Profile" /> : <UserCircle size={18} />}
            <span>{user.email.split('@')[0]}</span>
          </button>

          <button className="icon" onClick={logout}><LogOut /></button>
        </div>
      </header>

      <div className="layout">

        {/* SIDEBAR */}

        {side && (
          <aside>
            <button
              className="newchat"
              onClick={() => {
                setCid(null)
                if (user?.id) localStorage.removeItem(`ng_active_chat_${user.id}`)
                setMsgs([])
                setSide(false)
              }}
            >
              <Plus />
              New conversation
            </button>

            <div className="label">
              CONVERSATIONS
            </div>

            <div className="chatlist">
              {chats.map(c => (
                <button
                  className={
                    'conversation ' +
                    (cid === c.id
                      ? 'selected'
                      : '')
                  }
                  key={c.id}
                  onClick={() => {
                    openChat(c.id)
                    setSide(false)
                  }}
                >
                  <MessageSquare
                    size={15}
                  />

                  <span>
                    {c.title}
                  </span>
                </button>
              ))}
            </div>

            <div className="sidebottom">
              <div className="userpill">
                <div className="avatar">
                  {user.avatar_data ? <img src={user.avatar_data} alt="Profile" /> : user.email[0].toUpperCase()}
                </div>

                <div>
                  <b>
                    {user.email}
                  </b>

                  <small>
                    {user.role}
                  </small>
                </div>
              </div>

              <button
                className="conversation"
                onClick={logout}
              >
                <LogOut size={15} />
                Sign out
              </button>
            </div>
          </aside>
        )}

        {/* MAIN */}

        <main>
          <div className="maininner">

            {msgs.length === 0 ? (
              <Home
                setInput={
                  setInput
                }
              />
            ) : (
              <div className="messages">

                {msgs.map(
                  (m, i) => (
                    <MessageBubble
                      key={`${i}-${m.role}-${m.content.slice(0, 24)}`}
                      message={m}
                      index={i}
                      userAvatar={user?.avatar_data || ''}
                      siteLogo={siteLogo}
                    />
                  )
                )}

                {busy && !revealing && (
                  <TypingIndicator siteLogo={siteLogo} continuationStatus={continuationStatus} />
                )}

                <div
                  ref={messagesEndRef}
                  className="messages-end"
                  aria-hidden="true"
                />

              </div>
            )}

          </div>

          {/* COMPOSER */}

          {!busy && <div className="composer">

            <textarea
              value={input}
              onChange={e =>
                setInput(
                  e.target.value
                )
              }
              onInput={e => {
                e.currentTarget.style.height =
                  '45px'
                e.currentTarget.style.height =
                  `${Math.min(
                    e.currentTarget.scrollHeight,
                    150
                  )}px`
              }}
              onKeyDown={e => {
                if (
                  e.key === 'Enter' &&
                  !e.shiftKey
                ) {
                  e.preventDefault()
                  send()
                }
              }}
              placeholder="Ask NG INTELLIGENCE anything…"
            />

            <button
              className={
                'send ' +
                (input.trim()
                  ? 'ready'
                  : '')
              }
              onClick={send}
              disabled={
                busy ||
                !input.trim()
              }
            >
              {busy ? (
                <span className="sendloading">
                  <i />
                  <i />
                  <i />
                </span>
              ) : (
                <Send size={18} />
              )}
            </button>
          </div>}

        </main>
      </div>

      {profile && <ProfilePanel user={user} onClose={() => setProfile(false)} onSaved={u => { setUser(u); setProfile(false) }} />}

      {admin && (
        <Admin
          close={() =>
            setAdmin(false)
          }
        />
      )}
    </div>
  )
}

/* =========================
   HOME
========================= */

function Home({
  setInput
}) {
  const cards = [
    [
      'Build',
      'Create complete software projects.',
      'Build a complete Python project.'
    ],
    [
      'Debug',
      'Analyze errors and repair source code.',
      'Debug this code and explain the fix.'
    ],
    [
      'Explain',
      'Understand complex code and systems.',
      'Explain this code step by step.'
    ],
    [
      'Create',
      'Turn ideas into working solutions.',
      'Help me create something.'
    ]
  ]

  return (
    <div className="home">

      <div className="heroicon">
        <Sparkles />
      </div>

      <span className="eyebrow">
        NG INTELLIGENCE
      </span>

      <h1>
        What can I help you build?
      </h1>

      <p>
        A private AI workspace for coding,
        debugging, research, and creation.
      </p>

      <div className="cards">
        {cards.map(x => (
          <button
            key={x[0]}
            onClick={() =>
              setInput(x[2])
            }
          >
            <div>
              <b>{x[0]}</b>
              <span>{x[1]}</span>
            </div>

            <ChevronRight
              size={15}
            />
          </button>
        ))}
      </div>
    </div>
  )
}

createRoot(
  document.getElementById('root')
).render(
  <App />
)
