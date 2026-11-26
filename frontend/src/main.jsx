
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
  ChevronRight
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
    throw Error(d.detail || 'Request failed')
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
  const [pass, setPass] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()

    setBusy(true)
    setErr('')

    try {
      const d = await api('/api/auth/' + mode, {
        method: 'POST',
        body: JSON.stringify({
          email,
          password: pass
        })
      })

      localStorage.setItem('ng_token', d.token)
      done(d.user)
    } catch (x) {
      setErr(x.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <div className="glow g1" />
      <div className="glow g2" />

      <div className="authbox">
        <Brand />

        <div className="authcopy">
          <span className="eyebrow">
            {mode === 'login'
              ? 'PRIVATE AI WORKSPACE'
              : 'CREATE YOUR WORKSPACE'}
          </span>

          <h1>
            {mode === 'login'
              ? 'Welcome back.'
              : 'Start building.'}
          </h1>

          <p>
            {mode === 'login'
              ? 'Sign in to continue to your intelligent workspace.'
              : 'Create a private NG INTELLIGENCE account.'}
          </p>
        </div>

        <form onSubmit={submit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
          </label>

          <label>
            Password
            <input
              type="password"
              value={pass}
              onChange={e => setPass(e.target.value)}
              placeholder="Minimum 8 characters"
              minLength="8"
              required
            />
          </label>

          {err && (
            <div className="error">
              {err}
            </div>
          )}

          <button
            className="gradientbtn authbtn"
            disabled={busy}
            type="submit"
          >
            {busy
              ? 'Please wait…'
              : mode === 'login'
                ? 'Sign in'
                : 'Create account'}
          </button>
        </form>

        <div className="switch">
          {mode === 'login'
            ? 'New to NG INTELLIGENCE?'
            : 'Already have an account?'}

          <button
            onClick={() =>
              setMode(
                mode === 'login'
                  ? 'register'
                  : 'login'
              )
            }
          >
            {mode === 'login'
              ? 'Create account'
              : 'Sign in'}
          </button>
        </div>
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

function MessageBubble({
  message,
  index
}) {
  const isAI =
    message.role === 'assistant'

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
      {!isAI && (
        <div className="avatar">
          U
        </div>
      )}

      <div className="content">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
        >
          {message.content}
        </ReactMarkdown>

        {isAI && (
          <div className="message-glow" />
        )}
      </div>
    </div>
  )
}

/* =========================
   MAIN APP
========================= */

function App() {
  const [user, setUser] =
    useState(null)

  const messagesEndRef = useRef(null)

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

  const [admin, setAdmin] =
    useState(false)

  useEffect(() => {
  if (!msgs.length && !busy) return

  requestAnimationFrame(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end'
    })
  })
}, [msgs, busy])
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
    if (user) {
      loadChats()
    }
  }, [user])

  async function loadChats() {
    try {
      setChats(
        await api('/api/chats')
      )
    } catch (e) {
      console.error(e)
    }
  }

  async function openChat(id) {
    try {
      setCid(id)

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
    const text =
      input.trim()

    if (!text || busy) {
      return
    }

    setInput('')

    setMsgs(m => [
      ...m,
      {
        role: 'user',
        content: text
      }
    ])

    setBusy(true)

    try {
      const d =
        await api('/api/chat', {
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
      setMsgs(m => [
        ...m,
        {
          role: 'assistant',
          content:
            '**Request failed:** ' +
            e.message
        }
      ])
    } finally {
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
    <div className="app">
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

          <button
            className="icon"
            onClick={logout}
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
              onClick={() => {
                setCid(null)
                setMsgs([])
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
                  onClick={() =>
                    openChat(c.id)
                  }
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
                  {user.email[0]
                    .toUpperCase()}
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
                    />
                  )
                )}

                {busy && (
                  <TypingIndicator />
                )}

                <div
                  ref={messagesEndRef}
                  className="messages-end"
                  aria-hidden="true"
                />

              </div>
            )}

          </div>

          {/* COMPOSER - HIDE WHILE AI IS RESPONDING */}

          {!busy && (
            <div className="composer"> 
              </main>

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
                disabled={!input.trim()}
              >
                <Send size={18} />
              </button>
            </div>
          )}


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
