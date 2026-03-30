import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import LoadingOverlay from '../components/LoadingOverlay'

export default function AdminForgotPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState(searchParams.get('email') || '')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api('/api/admin/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim() })
      })
      setSent(true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card loading-overlay-host">
        <LoadingOverlay open={loading} label="Sending reset link..." />
        <h1>Reset Password</h1>
        <form onSubmit={submit}>
          <input type="email" placeholder="Email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          {error && <p className="error">{error}</p>}
          {sent && <p className="muted">If the account exists, a reset link has been sent.</p>}
          <button className="primary auth-submit" disabled={loading || sent}>{sent ? 'Link sent' : 'Send reset link'}</button>
        </form>
        <div className="auth-links">
          <Link to="/admin/auth">Back to sign in</Link>
          <button type="button" className="link-btn" onClick={() => navigate('/admin/auth')}>Go to login</button>
        </div>
      </section>
    </main>
  )
}
