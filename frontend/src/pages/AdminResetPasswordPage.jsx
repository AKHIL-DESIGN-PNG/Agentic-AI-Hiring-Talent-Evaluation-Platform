import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import LoadingOverlay from '../components/LoadingOverlay'

export default function AdminResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (!token) {
      setError('Reset token is missing or invalid')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      await api('/api/admin/reset-password', {
        method: 'POST',
        body: JSON.stringify({
          token,
          password,
          confirm_password: confirmPassword
        })
      })
      setDone(true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card loading-overlay-host">
        <LoadingOverlay open={loading} label="Resetting password..." />
        <h1>Choose New Password</h1>
        <form onSubmit={submit}>
          <input type="password" placeholder="New password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          <input type="password" placeholder="Confirm password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
          {error && <p className="error">{error}</p>}
          {done && <p className="muted">Password updated successfully.</p>}
          <button className="primary auth-submit" disabled={loading || done}>{done ? 'Password updated' : 'Reset password'}</button>
        </form>
        <p className="switch"><Link to="/admin/auth">Back to sign in</Link></p>
      </section>
    </main>
  )
}
