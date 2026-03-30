import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import LoadingOverlay from '../components/LoadingOverlay'

export default function AdminSignupPage() {
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setError('')
    if (password !== confirmPassword) {
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
          password,
          company_name: companyName.trim()
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

  return (
    <main className="auth-page">
      <section className="auth-card loading-overlay-host">
        <LoadingOverlay open={loading} label="Creating account..." />
        <h1>Create Admin Account</h1>
        <form onSubmit={submit}>
          <input placeholder="Full name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          <input type="email" placeholder="Email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <input type="password" placeholder="Password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          <input type="password" placeholder="Confirm password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
          <input type="text" placeholder="Company name" value={companyName} onChange={(event) => setCompanyName(event.target.value)} required />
          {error && <p className="error">{error}</p>}
          <button className="primary auth-submit" disabled={loading}>Create account</button>
        </form>
        <p className="switch">Already have an account? <Link to="/admin/auth">Sign in</Link></p>
      </section>
    </main>
  )
}
