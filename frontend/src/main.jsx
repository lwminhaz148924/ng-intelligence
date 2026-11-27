
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
  ArrowLeft,
  Mail,
  RefreshCw
} from 'lucide-react'
import './styles.css'

const API =
  import.meta.env.VITE_API_URL || 'https://ng-intelligence.onrender.com'

const token = () => localStorage.getItem('ng_token')

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
    const detail = d.detail
    const message = Array.isArray(detail)
      ? detail.map(x => x.msg).join(', ')
      : detail || d.message || 'Request failed'

    throw Error(message)
  }

  return d
}

/* =========================
   BRAND
========================= */

function Brand() {
  return (
    <div className="brand">
      <span className="brandmark">N</span>
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

function Auth({ done }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [resendBusy, setResendBusy] = useState(false)

  function changeMode(nextMode) {
    setMode(nextMode)
    setErr('')
    setNotice('')
    setCode('')
    setNewPassword('')
    setConfirmPassword('')
  }

  function handleEmail(value) {
    setEmail(value.trim())
  }

  /* LOGIN */

  async function login(e) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setNotice('')

    try {
      const d = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email,
          password
        })
      })

      localStorage.setItem('ng_token', d.token)
      done(d.user)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  /* REGISTER */

  async function register(e) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setNotice('')

    if (password.length < 8) {
      setErr('Password must be at least 8 characters.')
      setBusy(false)
      return
    }

    try {
      const d = await api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          email,
          password
        })
      })

      if (d.verification_required) {
        setMode('verify')
        setNotice(
          d.message || 'A verification code has been sent to your email.'
        )
      } else {
        setErr('Unexpected registration response. Please try again.')
      }
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  /* VERIFY EMAIL */

  async function verify(e) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setNotice('')

    if (!/^\d{6}$/.test(code.trim())) {
      setErr('Enter the 6-digit verification code.')
      setBusy(false)
      return
    }

    try {
      const d = await api('/api/auth/verify', {
        method: 'POST',
        body: JSON.stringify({
          email,
          code: code.trim()
        })
      })

      if (!d.token || !d.user) {
        throw Error('Verification succeeded but login information was not received.')
      }

      localStorage.setItem('ng_token', d.token)
      done(d.user)
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  /* RESEND VERIFICATION */

  async function resendCode() {
    setResendBusy(true)
    setErr('')
    setNotice('')

    try {
      const d = await api('/api/auth/resend-verification', {
        method: 'POST',
        body: JSON.stringify({ email })
      })

      setNotice(d.message || 'A new verification code has been sent.')
      setCode('')
    } catch (e) {
      setErr(e.message)
    } finally {
      setResendBusy(false)
    }
  }

  /* FORGOT PASSWORD */

  async function forgotPassword(e) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setNotice('')

    try {
      const d = await api('/api/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email })
      })

      setMode('reset')
      setNotice(
        d.message ||
        'If an account exists for this email, a reset code has been sent.'
      )
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  /* RESET PASSWORD */

  async function resetPassword(e) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setNotice('')

    if (!/^\d{6}$/.test(code.trim())) {
      setErr('Enter the 6-digit reset code.')
      setBusy(false)
      return
    }

    if (newPassword.length < 8) {
      setErr('New password must be at least 8 characters.')
      setBusy(false)
      return
    }

    if (newPassword !== confirmPassword) {
      setErr('Passwords do not match.')
      setBusy(false)
      return
    }

    try {
      const d = await api('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({
          email,
          code: code.trim(),
          new_password: newPassword
        })
      })

      setPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setCode('')
      setMode('login')
      setNotice(d.message || 'Password reset successfully. Please sign in.')
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const titles = {
    login: {
      eyebrow: 'PRIVATE AI WORKSPACE',
      title: 'Welcome back.',
      description: 'Sign in to continue to your intelligent workspace.'
    },
    register: {
      eyebrow: 'CREATE YOUR WORKSPACE',
      title: 'Start building.',
      description: 'Create your NG INTELLIGENCE account.'
    },
    verify: {
      eyebrow: 'EMAIL VERIFICATION',
      title: 'Check your inbox.',
      description: `Enter the 6-digit code sent to ${email}.`
    },
    forgot: {
      eyebrow: 'ACCOUNT RECOVERY',
      title: 'Forgot password?',
      description: 'Enter your account email to receive a reset code.'
    },
    reset: {
      eyebrow: 'RESET PASSWORD',
      title: 'Create a new password.',
      description: `Enter the reset code sent to ${email}.`
    }
  }

  const current = titles[mode]

  return (
    <div className="auth">
      <div className="glow g1" />
      <div className="glow g2" />

      <div className="authbox">
        <Brand />

        <div className="authcopy">
          <span className="eyebrow">{current.eyebrow}</span>
          <h1>{current.title}</h1>
          <p>{current.description}</p>
        </div>

        {mode === 'login' && (
          <form onSubmit={login}>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={e => handleEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </label>

            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Your password"
                autoComplete="current-password"
                required
              />
            </label>

            <div style={{ textAlign: 'right', margin: '4px 0 14px' }}>
              <button
                type="button"
                onClick={() => changeMode('forgot')}
                style={{
                  background: 'transparent',
                  color: '#ad8aff',
                  padding: '5px',
                  border: 0
                }}
              >
                Forgot password?
              </button>
            </div>

            {err && <div className="error">{err}</div>}
            {notice && <div className="notice">{notice}</div>}

            <button
              className="gradientbtn authbtn"
              disabled={busy}
              type="submit"
            >
              {busy ? 'Please wait…' : 'Sign in'}
            </button>

            <div className="switch">
              New to NG INTELLIGENCE?
              <button
                type="button"
                onClick={() => changeMode('register')}
              >
                Create account
              </button>
            </div>
          </form>
        )}

        {mode === 'register' && (
          <form onSubmit={register}>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={e => handleEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </label>

            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                minLength={8}
                autoComplete="new-password"
                required
              />
            </label>

            {err && <div className="error">{err}</div>}
            {notice && <div className="notice">{notice}</div>}

            <button
              className="gradientbtn authbtn"
              disabled={busy}
              type="submit"
            >
              {busy ? 'Sending verification code…' : 'Create account'}
            </button>

            <div className="switch">
              Already have an account?
              <button
                type="button"
                onClick={() => changeMode('login')}
              >
                Sign in
              </button>
            </div>
          </form>
        )}

        {mode === 'verify' && (
          <form onSubmit={verify}>
            <label>
              Verification code
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={e =>
                  setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                }
                placeholder="000000"
                required
              />
            </label>

            {err && <div className="error">{err}</div>}
            {notice && <div className="notice">{notice}</div>}

            <button
              className="gradientbtn authbtn"
              disabled={busy}
              type="submit"
            >
              {busy ? 'Verifying…' : 'Verify email'}
            </button>

            <div className="switch">
              Didn't receive the code?
              <button
                type="button"
                disabled={resendBusy}
                onClick={resendCode}
              >
                {resendBusy ? 'Sending…' : 'Resend code'}
              </button>
            </div>

            <div className="switch">
              <button
                type="button"
                onClick={() => changeMode('register')}
              >
                <ArrowLeft size={14} /> Back to registration
              </button>
            </div>
          </form>
        )}

        {mode === 'forgot' && (
          <form onSubmit={forgotPassword}>
            <label>
              Account email
              <input
                type="email"
                value={email}
                onChange={e => handleEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </label>

            {err && <div className="error">{err}</div>}
            {notice && <div className="notice">{notice}</div>}

            <button
              className="gradientbtn authbtn"
              disabled={busy}
              type="submit"
            >
              {busy ? 'Sending reset code…' : 'Send reset code'}
            </button>

            <div className="switch">
              Remember your password?
              <button
                type="button"
                onClick={() => changeMode('login')}
              >
                Sign in
              </button>
            </div>
          </form>
        )}

        {mode === 'reset' && (
          <form onSubmit={resetPassword}>
            <label>
              Reset code
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={e =>
                  setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                }
                placeholder="000000"
                required
              />
            </label>

            <label>
              New password
              <input
                type="password"
                value={newPassword}
                onChange={e => setNewPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                minLength={8}
                autoComplete="new-password"
                required
              />
            </label>

            <label>
              Confirm new password
              <input
                type="password"
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                placeholder="Enter password again"
                minLength={8}
                autoComplete="new-password"
                required
              />
            </label>

            {err && <div className="error">{err}</div>}
            {notice && <div className="notice">{notice}</div>}

            <button
              className="gradientbtn authbtn"
              disabled={busy}
              type="submit"
            >
              {busy ? 'Resetting password…' : 'Reset password'}
            </button>

            <div className="switch">
              <button
                type="button"
                onClick={() => changeMode('forgot')}
              >
                <RefreshCw size={14} /> Request another code
              </button>
            </div>

            <div className="switch">
              <button
                type="button"
                onClick={() => changeMode('login')}
              >
                <ArrowLeft size={14} /> Back to sign in
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
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
  const [err, setErr] = useState('')

  const load = async () => {
    setErr('')

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
    } catch (e) {
      setErr(e.message)
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
            <span className="eyebrow">CONTROL CENTER</span>
            <h2>NG INTELLIGENCE Admin</h2>
          </div>

          <button className="icon" onClick={close}>
            <X />
          </button>
        </div>

        <div className="admintabs">
          {[
            ['overview', 'Overview'],
            ['keys', 'Gemini Keys'],
            ['settings', 'AI Settings'],
            ['users', 'Users'],
            ['logs', 'Logs']
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

        {err && <div className="error">{err}</div>}

        {tab === 'overview' && (
          stats ? (
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
                  <b>{Number(x[1] || 0).toLocaleString()}</b>
                </div>
              ))}
            </div>
          ) : (
            <p>Loading overview…</p>
          )
        )}

        {tab === 'keys' && (
          <Keys keys={keys} reload={load} />
        )}

        {tab === 'settings' && (
          <SettingsPanel data={settings} reload={load} />
        )}

        {tab === 'users' && (
          <div className="table">
            {users.map(x => (
              <div className="row" key={x.id}>
                <div>
                  <b>{x.email}</b>
                  <small>
                    {x.role} · {x.active ? 'Active' : 'Disabled'}
                    {' · '}
                    {x.is_verified ? 'Verified' : 'Unverified'}
                  </small>
                </div>

                <button
                  onClick={async () => {
                    try {
                      await api('/api/admin/users/' + x.id + '/toggle', {
                        method: 'PATCH'
                      })
                      load()
                    } catch (e) {
                      setErr(e.message)
                    }
                  }}
                >
                  {x.active ? 'Disable' : 'Enable'}
                </button>
              </div>
            ))}
            {!users.length && <p>No users found.</p>}
          </div>
        )}

        {tab === 'logs' && (
          <div className="logs">
            {logs.map(x => (
              <div className="log" key={x.id}>
                <b>{x.event}</b>
                <span>{x.status}</span>
                <small>{x.details} · {x.created_at}</small>
              </div>
            ))}
            {!logs.length && <p>No logs found.</p>}
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
  const [label, setLabel] = useState('Primary Gemini')
  const [key, setKey] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function addKey() {
    if (!label.trim() || !key.trim() || busy) return

    setBusy(true)
    setErr('')

    try {
      await api('/api/admin/keys', {
        method: 'POST',
        body: JSON.stringify({
          label: label.trim(),
          key: key.trim()
        })
      })

      setKey('')
      reload()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="notice">
        <KeyRound />
        <div>
          <b>Secure Gemini key management</b>
          <p>
            Keys are encrypted at rest and never rendered back to the browser.
          </p>
        </div>
      </div>

      {err && <div className="error">{err}</div>}

      {keys.map(k => (
        <div className="row" key={k.id}>
          <div>
            <b>{k.label}</b>
            <small>
              {k.active ? 'Active' : 'Disabled'} · {k.created_at}
            </small>
          </div>

          <button
            onClick={async () => {
              try {
                await api('/api/admin/keys/' + k.id, {
                  method: 'PATCH'
                })
                reload()
              } catch (e) {
                setErr(e.message)
              }
            }}
          >
            {k.active ? 'Disable' : 'Enable'}
          </button>

          <button
            onClick={async () => {
              if (!window.confirm('Delete this API key?')) return

              try {
                await api('/api/admin/keys/' + k.id, {
                  method: 'DELETE'
                })
                reload()
              } catch (e) {
                setErr(e.message)
              }
            }}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}

      <div className="add">
        <input
          value={label}
          onChange={e => setLabel(e.target.value)}
          placeholder="Key label"
        />

        <input
          type="password"
          value={key}
          onChange={e => setKey(e.target.value)}
          placeholder="Gemini API key"
        />

        <button
          className="gradientbtn"
          disabled={busy || !key.trim() || !label.trim()}
          onClick={addKey}
        >
          {busy ? 'Adding…' : 'Add key'}
        </button>
      </div>
    </div>
  )
}

/* =========================
   SETTINGS
========================= */

function SettingsPanel({ data, reload }) {
  const [model, setModel] = useState(data.model || '')
  const [prompt, setPrompt] = useState(data.system_prompt || '')
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setModel(data.model || '')
    setPrompt(data.system_prompt || '')
  }, [data])

  async function save() {
    setBusy(true)
    setErr('')
    setNotice('')

    try {
      await api('/api/admin/settings', {
        method: 'PUT',
        body: JSON.stringify({
          name: 'model',
          value: model
        })
      })

      await api('/api/admin/settings', {
        method: 'PUT',
        body: JSON.stringify({
          name: 'system_prompt',
          value: prompt
        })
      })

      setNotice('AI configuration saved successfully.')
      reload()
    } catch (e) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="settings">
      <label>
        Gemini model
        <input
          value={model}
          onChange={e => setModel(e.target.value)}
        />
      </label>

      <label>
        System prompt
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
        />
      </label>

      {err && <div className="error">{err}</div>}
      {notice && <div className="notice">{notice}</div>}

      <button
        className="gradientbtn"
        onClick={save}
        disabled={busy}
      >
        {busy ? 'Saving…' : 'Save AI configuration'}
      </button>
    </div>
  )
}

/* =========================
   TYPING INDICATOR
========================= */

function TypingIndicator() {
  return (
    <div
      className="msg assistant typingmsg"
      role="status"
      aria-label="NG INTELLIGENCE is responding"
    >
      <div className="typingbubble">
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

function MessageBubble({ message, index }) {
  const isAI = message.role === 'assistant'

  return (
    <div
      className={'msg ' + message.role + ' message-enter'}
      style={{
        animationDelay: `${Math.min(index * 35, 180)}ms`
      }}
    >
      {!isAI && <div className="avatar">U</div>}

      <div className="content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.content}
        </ReactMarkdown>

        {isAI && <div className="message-glow" />}
      </div>
    </div>
  )
}

/* =========================
   MAIN APP
========================= */

function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const messagesEndRef = useRef(null)

  const [side, setSide] = useState(true)
  const [chats, setChats] = useState([])
  const [cid, setCid] = useState(null)
  const [msgs, setMsgs] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [admin, setAdmin] = useState(false)
  const [chatError, setChatError] = useState('')

  /* AUTO SCROLL */

  useEffect(() => {
    if (!msgs.length && !busy) return

    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'end'
      })
    })
  }, [msgs, busy])

  /* CHECK LOGIN */

  useEffect(() => {
    let active = true

    async function checkLogin() {
      if (!token()) {
        setChecking(false)
        return
      }

      try {
        const u = await api('/api/me')
        if (active) setUser(u)
      } catch {
        localStorage.removeItem('ng_token')
      } finally {
        if (active) setChecking(false)
      }
    }

    checkLogin()

    return () => {
      active = false
    }
  }, [])

  /* LOAD CHATS */

  useEffect(() => {
    if (user) {
      loadChats()
    }
  }, [user])

  async function loadChats() {
    try {
      setChats(await api('/api/chats'))
    } catch (e) {
      console.error(e)
    }
  }

  /* OPEN CHAT */

  async function openChat(id) {
    try {
      setChatError('')
      setCid(id)
      setMsgs(await api('/api/chats/' + id))
    } catch (e) {
      setChatError(e.message)
    }
  }

  /* NEW CHAT */

  function newChat() {
    setCid(null)
    setMsgs([])
    setInput('')
    setChatError('')
  }

  /* SEND MESSAGE */

  async function send() {
    const text = input.trim()

    if (!text || busy) return

    setInput('')
    setChatError('')

    setMsgs(m => [
      ...m,
      {
        role: 'user',
        content: text
      }
    ])

    setBusy(true)

    try {
      const d = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: text,
          chat_id: cid
        })
      })

      setCid(d.chat_id)

      setMsgs(m => [
        ...m,
        {
          role: 'assistant',
          content: d.answer
        }
      ])

      loadChats()
    } catch (e) {
      setChatError(e.message)

      setMsgs(m => [
        ...m,
        {
          role: 'assistant',
          content: '**Request failed:** ' + e.message
        }
      ])
    } finally {
      setBusy(false)
    }
  }

  /* DELETE CHAT */

  async function deleteChat(id) {
    if (!window.confirm('Delete this conversation?')) return

    try {
      await api('/api/chats/' + id, {
        method: 'DELETE'
      })

      if (cid === id) {
        newChat()
      }

      loadChats()
    } catch (e) {
      setChatError(e.message)
    }
  }

  /* LOGOUT */

  function logout() {
    localStorage.removeItem('ng_token')
    setUser(null)
    setChats([])
    setMsgs([])
    setCid(null)
    setInput('')
    setAdmin(false)
  }

  if (checking) {
    return (
      <div className="auth">
        <div className="authbox">
          <Brand />
          <p style={{ textAlign: 'center', color: '#9290aa' }}>
            Loading NG INTELLIGENCE…
          </p>
        </div>
      </div>
    )
  }

  if (!user) {
    return <Auth done={setUser} />
  }

  return (
    <div className="app">

      {/* HEADER */}

      <header>
        <button
          className="icon"
          onClick={() => setSide(!side)}
          aria-label="Toggle sidebar"
        >
          {side ? <X /> : <Menu />}
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
              onClick={() => setAdmin(true)}
              aria-label="Admin panel"
            >
              <Shield />
            </button>
          )}

          <button
            className="icon"
            onClick={logout}
            aria-label="Sign out"
          >
            <LogOut />
          </button>
        </div>
      </header>

      <div className="layout">

        {/* SIDEBAR */}

        {side && (
          <aside>
            <button
              className="newchat"
              onClick={newChat}
            >
              <Plus />
              New conversation
            </button>

            <div className="label">CONVERSATIONS</div>

            <div className="chatlist">
              {chats.map(c => (
                <div
                  className={
                    'conversation-wrap ' +
                    (cid === c.id ? 'selected' : '')
                  }
                  key={c.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5
                  }}
                >
                  <button
                    className={
                      'conversation ' +
                      (cid === c.id ? 'selected' : '')
                    }
                    style={{
                      flex: 1,
                      minWidth: 0,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 9,
                      textAlign: 'left',
                      border: 0,
                      background: 'transparent'
                    }}
                    onClick={() => openChat(c.id)}
                  >
                    <MessageSquare size={15} />
                    <span style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}>
                      {c.title}
                    </span>
                  </button>

                  <button
                    className="icon"
                    title="Delete conversation"
                    aria-label="Delete conversation"
                    onClick={() => deleteChat(c.id)}
                    style={{
                      padding: 6,
                      background: 'transparent',
                      border: 0,
                      color: '#9290aa'
                    }}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}

              {!chats.length && (
                <p style={{
                  color: '#77748d',
                  fontSize: 12,
                  padding: 10
                }}>
                  No conversations yet.
                </p>
              )}
            </div>

            <div className="sidebottom">
              <div className="userpill">
                <div className="avatar">
                  {user.email[0].toUpperCase()}
                </div>

                <div style={{ minWidth: 0 }}>
                  <b style={{
                    display: 'block',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis'
                  }}>
                    {user.email}
                  </b>
                  <small>{user.role}</small>
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

        <main style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column'
        }}>
          <div className="maininner">

            {msgs.length === 0 ? (
              <Home setInput={setInput} />
            ) : (
              <div className="messages">

                {msgs.map((m, i) => (
                  <MessageBubble
                    key={`${i}-${m.role}-${String(m.content).slice(0, 24)}`}
                    message={m}
                    index={i}
                  />
                ))}

                {busy && <TypingIndicator />}

                <div
                  ref={messagesEndRef}
                  className="messages-end"
                  aria-hidden="true"
                />

              </div>
            )}

          </div>

          {chatError && (
            <div className="error" style={{
              width: 'min(900px, calc(100% - 48px))',
              margin: '0 auto 10px'
            }}>
              {chatError}
            </div>
          )}

          {/* COMPOSER - HIDDEN WHILE AI RESPONDS */}

          {!busy && (
            <div className="composer">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onInput={e => {
                  e.currentTarget.style.height = '45px'
                  e.currentTarget.style.height =
                    `${Math.min(e.currentTarget.scrollHeight, 150)}px`
                }}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
                placeholder="Ask NG INTELLIGENCE anything…"
              />

              <button
                className={'send ' + (input.trim() ? 'ready' : '')}
                onClick={send}
                disabled={!input.trim()}
                aria-label="Send message"
              >
                <Send size={18} />
              </button>
            </div>
          )}

        </main>
      </div>

      {/* ADMIN MODAL */}

      {admin && (
        <Admin close={() => setAdmin(false)} />
      )}

    </div>
  )
}

/* =========================
   HOME
========================= */

function Home({ setInput }) {
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

      <span className="eyebrow">NG INTELLIGENCE</span>

      <h1>What can I help you build?</h1>

      <p>
        A private AI workspace for coding,
        debugging, research, and creation.
      </p>

      <div className="cards">
        {cards.map(x => (
          <button
            key={x[0]}
            onClick={() => setInput(x[2])}
          >
            <div>
              <b>{x[0]}</b>
              <span>{x[1]}</span>
            </div>

            <ChevronRight size={15} />
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
