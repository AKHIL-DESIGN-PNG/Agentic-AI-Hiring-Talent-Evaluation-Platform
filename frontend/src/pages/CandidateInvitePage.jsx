import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import CandidatePortalHeader from '../components/CandidatePortalHeader'
import LoadingPulse from '../components/LoadingPulse'
import LoadingOverlay from '../components/LoadingOverlay'
import useMinimumDelay from '../hooks/useMinimumDelay'
import useProctoringWarmup from '../hooks/useProctoringWarmup'

const INVITE_TOKEN_STORAGE_KEY = 'candidate_invite_token'

export default function CandidateInvitePage() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [signingUp, setSigningUp] = useState(false)
  const ready = useMinimumDelay(Boolean(data))
  const inviteToken = token || sessionStorage.getItem(INVITE_TOKEN_STORAGE_KEY) || ''
  useProctoringWarmup(false)

  useEffect(() => {
    async function load() {
      if (!inviteToken) {
        throw new Error('Invite token is missing')
      }

      const info = await api(`/api/candidate/invite/${inviteToken}`)
      sessionStorage.setItem(INVITE_TOKEN_STORAGE_KEY, inviteToken)
      setData(info)
      setFullName(info.invite.full_name || '')
      setEmail(info.invite.email || '')

      if (token) {
        navigate('/candidate/invite', { replace: true })
        return
      }

      if (info.candidate?.id && !info.already_taken) {
        sessionStorage.removeItem(INVITE_TOKEN_STORAGE_KEY)
        navigate(
          info.profile_completed
            ? `/candidate/${info.candidate.id}/dashboard`
            : `/candidate/${info.candidate.id}/profile`,
          { replace: true }
        )
      }
    }
    load().catch((requestError) => {
      console.error('candidate_invite_load_failed', requestError)
      sessionStorage.removeItem(INVITE_TOKEN_STORAGE_KEY)
      setError('This invitation link is not available.')
    })
  }, [inviteToken, navigate, token])

  async function signup(event) {
    event.preventDefault()
    try {
      setSigningUp(true)
      const res = await api(`/api/candidate/invite/${inviteToken}/signup`, {
        method: 'POST',
        body: JSON.stringify({ full_name: fullName, email })
      })
      sessionStorage.removeItem(INVITE_TOKEN_STORAGE_KEY)
      navigate(
        res.profile_completed
          ? `/candidate/${res.candidate_id}/dashboard`
          : `/candidate/${res.candidate_id}/profile`
      )
    } catch (requestError) {
      console.error('candidate_signup_failed', requestError)
      setError(requestError.message)
      setSigningUp(false)
    }
  }

  if (!data || !ready) {
    return <LoadingPulse fullPage />
  }

  if (data.already_taken) {
    return (
      <div className="candidate-journey">
        <CandidatePortalHeader status="Invite" candidateName={data.invite.full_name} />
        <main className="candidate-page candidate-page--centered">
          <section className="candidate-card candidate-card--narrow">
            <h1>You have already taken this assessment</h1>
            <p className="muted">contact {data.contact_email}</p>
          </section>
        </main>
      </div>
    )
  }

  return (
    <div className="candidate-journey">
      <CandidatePortalHeader status="Invite" candidateName={data.invite.full_name} />
      <main className="candidate-page candidate-page--centered">
        <section className="candidate-card candidate-card--narrow loading-overlay-host">
          <LoadingOverlay open={signingUp} label="Signing you up..." />
          <h1>You&apos;re signing up to take tests for {data.assessment.name}</h1>
          <form onSubmit={signup} className="stack">
            <label>Full name</label>
            <input value={fullName} onChange={(event) => setFullName(event.target.value)} required />
            <label>Email address</label>
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            {error && <p className="error">{error}</p>}
            <button className="primary" disabled={signingUp}>{signingUp ? 'Signing up...' : 'Sign up'}</button>
          </form>
        </section>
      </main>
    </div>
  )
}
