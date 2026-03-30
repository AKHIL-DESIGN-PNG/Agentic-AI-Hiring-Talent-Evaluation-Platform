import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, googleClientId } from '../api'
import LoadingOverlay from '../components/LoadingOverlay'
import Modal from '../components/Modal'

function BrandMark() {
  return (
    <div className="auth-premium-brandmark" aria-hidden="true">
      <span>A</span>
    </div>
  )
}

export default function AdminAuthPage() {
  const navigate = useNavigate()
  const [authMode, setAuthMode] = useState('signin')
  const [panelKey, setPanelKey] = useState(0)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [signInPassword, setSignInPassword] = useState('')
  const [signupPassword, setSignupPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [keepSignedIn, setKeepSignedIn] = useState(false)
  const [signupCompanyName, setSignupCompanyName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [showCompanyCard, setShowCompanyCard] = useState(false)
  const [pendingToken, setPendingToken] = useState('')
  const [pendingProfile, setPendingProfile] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [forgotSent, setForgotSent] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showSignupPassword, setShowSignupPassword] = useState(false)
  const [showSignupConfirmPassword, setShowSignupConfirmPassword] = useState(false)

  useEffect(() => {
    let cancelled = false
    let initTimer = null

    async function handleGoogleCredential(response) {
      if (cancelled) return
      setGoogleLoading(true)
      try {
        const data = await api('/api/auth/google', {
          method: 'POST',
          body: JSON.stringify({ credential: response.credential })
        })
        if (data.needs_company_profile) {
          setPendingToken(data.token)
          setPendingProfile(data.admin)
          setShowCompanyCard(true)
          return
        }
        sessionStorage.removeItem('admin_token')
        sessionStorage.removeItem('admin_profile')
        localStorage.setItem('admin_token', data.token)
        localStorage.setItem('admin_profile', JSON.stringify(data.admin || {}))
        navigate('/admin/assessments', { replace: true })
      } catch (requestError) {
        setError(requestError.message)
      } finally {
        setGoogleLoading(false)
      }
    }

    function initGoogle() {
      const gsi = window.google?.accounts?.id
      const host = document.getElementById('google-one-tap-btn')
      if (!gsi || !host) return false

      gsi.initialize({
        client_id: googleClientId,
        callback: handleGoogleCredential,
        auto_select: true,
        cancel_on_tap_outside: false
      })
      gsi.renderButton(host, {
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        width: 360
      })
      gsi.prompt()
      return true
    }

    if (authMode !== 'signin' || showCompanyCard) return undefined

    if (!initGoogle()) {
      initTimer = window.setInterval(() => {
        if (initGoogle() && initTimer) {
          window.clearInterval(initTimer)
          initTimer = null
        }
      }, 250)
    }

    return () => {
      cancelled = true
      if (initTimer) window.clearInterval(initTimer)
      window.google?.accounts?.id?.cancel()
    }
  }, [authMode, navigate, panelKey, showCompanyCard])

  function switchAuthMode(nextMode) {
    setError('')
    setLoading(false)
    setForgotSent(false)
    setShowPassword(false)
    setShowSignupPassword(false)
    setShowSignupConfirmPassword(false)
    setAuthMode(nextMode)
    setPanelKey((value) => value + 1)
  }

  function storeAdminSession(data, persist) {
    if (persist) {
      sessionStorage.removeItem('admin_token')
      sessionStorage.removeItem('admin_profile')
      localStorage.setItem('admin_token', data.token)
      localStorage.setItem('admin_profile', JSON.stringify(data.admin || {}))
      return
    }
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_profile')
    sessionStorage.setItem('admin_token', data.token)
    sessionStorage.setItem('admin_profile', JSON.stringify(data.admin || {}))
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), password: signInPassword })
      })
      if (data.needs_company_profile) {
        setPendingToken(data.token)
        setPendingProfile(data.admin)
        setShowCompanyCard(true)
        return
      }
      storeAdminSession(data, keepSignedIn)
      navigate('/admin/assessments', { replace: true })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitSignup(event) {
    event.preventDefault()
    setError('')
    if (signupPassword !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      const data = await api('/api/auth/signup', {
        method: 'POST',
        body: JSON.stringify({
          full_name: fullName.trim(),
          email: email.trim(),
          password: signupPassword,
          company_name: signupCompanyName.trim()
        })
      })
      localStorage.setItem('admin_token', data.token)
      localStorage.setItem('admin_profile', JSON.stringify(data.admin || {}))
      navigate('/admin/assessments', { replace: true })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitForgotPassword(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api('/api/admin/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim() })
      })
      setForgotSent(true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitCompanyProfile(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const company = companyName.trim()
      if (!company) throw new Error('Company name is required')
      const data = await api('/api/auth/company-profile', {
        method: 'POST',
        headers: { Authorization: `Bearer ${pendingToken}` },
        body: JSON.stringify({ company_name: company })
      })
      localStorage.setItem('admin_token', pendingToken)
      localStorage.setItem('admin_profile', JSON.stringify(data.admin || pendingProfile))
      navigate('/admin/assessments', { replace: true })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-premium-page">
      <div className="auth-premium-bg" aria-hidden="true">
        <div className="auth-premium-orb auth-premium-orb--one" />
        <div className="auth-premium-orb auth-premium-orb--two" />
      </div>

      <main className="auth-premium-shell">
        <section className="auth-premium-brand">
          <div className="auth-premium-brand__top">
            <div className="auth-premium-brand__logo">
              <BrandMark />
              <span>AITS</span>
            </div>
            <h1>The Intelligent Layer for Hiring.</h1>
            <p>Access high-fidelity assessment data and AI-driven candidate calibration in one secure workspace.</p>
          </div>
        </section>

        <section className="auth-premium-panel">
          <div className="auth-premium-mobile-brand">
            <BrandMark />
            <span>AITS</span>
          </div>

          {!showCompanyCard && (
            <div key={panelKey} className="auth-premium-form auth-premium-form--animated loading-overlay-host">
              <LoadingOverlay open={loading} label="Please wait..." />
              {authMode !== 'signin' && (
                <button type="button" className="auth-premium-back" onClick={() => switchAuthMode('signin')}>
                  Back to sign in
                </button>
              )}

              {authMode === 'signin' && (
                <>
                  <div className="auth-premium-copy">
                    <h2>Secure Access</h2>
                    <p>Welcome back. Please enter your credentials.</p>
                  </div>

                  <form onSubmit={submit} className="auth-premium-fields">
                    <div className="auth-premium-field">
                      <label htmlFor="auth-email">Email Address</label>
                      <input
                        id="auth-email"
                        type="email"
                        placeholder="name@company.com"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                      />
                    </div>

                    <div className="auth-premium-field">
                      <div className="auth-premium-field__row">
                        <label htmlFor="auth-password">Password</label>
                        <button
                          type="button"
                          className="auth-premium-link auth-premium-link--button"
                          onClick={() => switchAuthMode('forgot')}
                        >
                          Forgot password?
                        </button>
                      </div>
                      <div className="auth-premium-password">
                        <input
                          id="auth-password"
                          type={showPassword ? 'text' : 'password'}
                          placeholder="Enter your password"
                          value={signInPassword}
                          onChange={(event) => setSignInPassword(event.target.value)}
                          required
                        />
                        <button type="button" className="auth-premium-password__toggle" onClick={() => setShowPassword((prev) => !prev)}>
                          {showPassword ? 'Hide' : 'Show'}
                        </button>
                      </div>
                    </div>

                    <label className="auth-premium-check">
                      <input
                        type="checkbox"
                        checked={keepSignedIn}
                        onChange={(event) => setKeepSignedIn(event.target.checked)}
                      />
                      <span>Keep me signed in for 30 days</span>
                    </label>

                    <button className="auth-premium-submit" type="submit" disabled={loading}>Sign In to Dashboard</button>
                  </form>

                  <div className="auth-premium-divider">
                    <span>or</span>
                  </div>

                  <div className="auth-premium-google">
                    <div id="google-one-tap-btn" />
                    {googleLoading && <p className="muted">Waiting for Google sign-in...</p>}
                  </div>

                  <footer className="auth-premium-footer">
                    <p>
                      Don&apos;t have an organization account?{' '}
                      <button
                        type="button"
                        className="auth-premium-link auth-premium-link--button"
                        onClick={() => switchAuthMode('signup')}
                      >
                        Create account
                      </button>
                    </p>
                  </footer>
                </>
              )}

              {authMode === 'signup' && (
                <>
                  <div className="auth-premium-copy">
                    <h2>Create Account</h2>
                    <p>Set up your organization workspace and continue into the dashboard.</p>
                  </div>

                  <form onSubmit={submitSignup} className="auth-premium-fields">
                    <div className="auth-premium-field">
                      <label htmlFor="signup-full-name">Full Name</label>
                      <input
                        id="signup-full-name"
                        type="text"
                        placeholder="Your full name"
                        value={fullName}
                        onChange={(event) => setFullName(event.target.value)}
                      />
                    </div>

                    <div className="auth-premium-field">
                      <label htmlFor="signup-email">Email Address</label>
                      <input
                        id="signup-email"
                        type="email"
                        placeholder="name@company.com"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                      />
                    </div>

                    <div className="auth-premium-field">
                      <label htmlFor="signup-password">Password</label>
                      <div className="auth-premium-password">
                        <input
                          id="signup-password"
                          type={showSignupPassword ? 'text' : 'password'}
                          placeholder="Create a password"
                          value={signupPassword}
                          onChange={(event) => setSignupPassword(event.target.value)}
                          required
                        />
                        <button type="button" className="auth-premium-password__toggle" onClick={() => setShowSignupPassword((prev) => !prev)}>
                          {showSignupPassword ? 'Hide' : 'Show'}
                        </button>
                      </div>
                    </div>

                    <div className="auth-premium-field">
                      <label htmlFor="signup-confirm-password">Confirm Password</label>
                      <div className="auth-premium-password">
                        <input
                          id="signup-confirm-password"
                          type={showSignupConfirmPassword ? 'text' : 'password'}
                          placeholder="Confirm your password"
                          value={confirmPassword}
                          onChange={(event) => setConfirmPassword(event.target.value)}
                          required
                        />
                        <button type="button" className="auth-premium-password__toggle" onClick={() => setShowSignupConfirmPassword((prev) => !prev)}>
                          {showSignupConfirmPassword ? 'Hide' : 'Show'}
                        </button>
                      </div>
                    </div>

                    <div className="auth-premium-field">
                      <label htmlFor="signup-company-name">Company Name</label>
                      <input
                        id="signup-company-name"
                        type="text"
                        placeholder="Company name"
                        value={signupCompanyName}
                        onChange={(event) => setSignupCompanyName(event.target.value)}
                        required
                      />
                    </div>

                    <button className="auth-premium-submit" type="submit" disabled={loading}>Create Account</button>
                  </form>
                </>
              )}

              {authMode === 'forgot' && (
                <>
                  <div className="auth-premium-copy">
                    <h2>Forgot Password</h2>
                    <p>Enter your work email and we&apos;ll send you a reset link.</p>
                  </div>

                  <form onSubmit={submitForgotPassword} className="auth-premium-fields">
                    <div className="auth-premium-field">
                      <label htmlFor="forgot-email">Email Address</label>
                      <input
                        id="forgot-email"
                        type="email"
                        placeholder="name@company.com"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        required
                      />
                    </div>

                    {forgotSent && <p className="muted">If the account exists, a reset link has been sent.</p>}

                    <button className="auth-premium-submit" type="submit" disabled={loading || forgotSent}>{forgotSent ? 'Link Sent' : 'Send Reset Link'}</button>
                  </form>
                </>
              )}
            </div>
          )}

          {showCompanyCard && (
            <div className="auth-premium-form loading-overlay-host">
              <LoadingOverlay open={loading} label="Please wait..." />
              <div className="auth-premium-copy">
                <h2>You are hiring for</h2>
                <p>Complete the last step before entering the dashboard.</p>
              </div>

              <form onSubmit={submitCompanyProfile} className="auth-premium-fields">
                <div className="auth-premium-field">
                  <label htmlFor="company-name">Company Name</label>
                  <input
                    id="company-name"
                    type="text"
                    placeholder="Company name"
                    value={companyName}
                    onChange={(event) => setCompanyName(event.target.value)}
                    required
                  />
                </div>

                <button className="auth-premium-submit" type="submit" disabled={loading}>Continue to Dashboard</button>
              </form>
            </div>
          )}
        </section>
      </main>

      <div className="auth-premium-badges" aria-hidden="true">
        <span>Encrypted</span>
        <span>Secure</span>
      </div>

      <Modal open={Boolean(error)} title="Authentication Notice" onClose={() => setError('')} hideCloseButton>
        <div className="stack modal-body">
          <p>{error}</p>
          <button className="primary" type="button" onClick={() => setError('')}>OK</button>
        </div>
      </Modal>
    </div>
  )
}
