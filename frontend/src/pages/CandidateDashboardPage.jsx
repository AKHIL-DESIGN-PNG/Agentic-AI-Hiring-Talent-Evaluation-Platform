import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import CandidatePortalHeader from '../components/CandidatePortalHeader'
import LoadingPulse from '../components/LoadingPulse'
import useMinimumDelay from '../hooks/useMinimumDelay'
import useProctoringWarmup from '../hooks/useProctoringWarmup'

export default function CandidateDashboardPage() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const ready = useMinimumDelay(true)
  useProctoringWarmup(true)

  useEffect(() => {
    api(`/api/candidate/${candidateId}/dashboard`)
      .then((info) => {
        if (info.profile_completed === false) {
          navigate(`/candidate/${candidateId}/profile`, { replace: true })
          return
        }
        if (info.next_section_id) {
          navigate(`/candidate/${candidateId}/sections/${info.next_section_id}/instructions`, { replace: true })
          return
        }
        navigate(`/candidate/${candidateId}/review`, { replace: true })
      })
      .catch((requestError) => {
        console.error('candidate_dashboard_failed', requestError)
        setError(String(requestError?.message || 'Unable to continue assessment flow.'))
      })
  }, [candidateId, navigate])

  if (!ready && !error) {
    return <LoadingPulse fullPage />
  }

  return (
    <div className="candidate-journey">
      <CandidatePortalHeader status="Redirecting" statusTone="ok" candidateName="Candidate" />
      <main className="candidate-page candidate-page--centered">
        <section className="candidate-card candidate-card--narrow">
          {error ? <p className="error">{error}</p> : <LoadingPulse />}
        </section>
      </main>
    </div>
  )
}
