import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import CandidatePortalHeader from '../components/CandidatePortalHeader'
import LoadingPulse from '../components/LoadingPulse'

function sectionRoute(sectionType) {
  if (sectionType === 'coding') return 'coding'
  if (sectionType === 'verbal') return 'verbal'
  return 'mcq'
}

export default function SectionInstructionsPage() {
  const { candidateId, sectionId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [waitingForGeneration, setWaitingForGeneration] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function loadInstructions() {
      try {
        const info = await api(`/api/candidate/${candidateId}/sections/${sectionId}/instructions`)
        if (cancelled) return
        setData(info)
        setError('')
        setWaitingForGeneration(false)
        return
      } catch (requestError) {
        const message = String(requestError?.message || 'Unable to load section instructions.')
        if (message.includes('still generating')) {
          if (cancelled) return
          setWaitingForGeneration(true)
          setError('Preparing the next section. Please wait...')
          return
        }
        if (
          message.includes('Section already completed') ||
          message.includes('Complete ') ||
          message.includes('Section not active')
        ) {
          try {
            const next = await api(`/api/candidate/${candidateId}/next-section`)
            if (next?.next_section_id && next.next_section_id !== sectionId) {
              navigate(`/candidate/${candidateId}/sections/${encodeURIComponent(next.next_section_id)}/instructions`, { replace: true })
              return
            }
            navigate(`/candidate/${candidateId}/review`, { replace: true })
            return
          } catch (fallbackError) {
            console.error('section_instructions_fallback_failed', fallbackError)
          }
        }
        setError(message)
      }
    }

    loadInstructions()
    const retryId = window.setInterval(() => {
      if (cancelled || !waitingForGeneration) return
      loadInstructions()
    }, 3000)

    return () => {
      cancelled = true
      window.clearInterval(retryId)
    }
  }, [candidateId, navigate, sectionId, waitingForGeneration])

  async function begin() {
    if (!data) return
    setBusy(true)
    try {
      if (data.status !== 'in_progress') {
        await api(`/api/candidate/${candidateId}/sections/${sectionId}/start`, {
          method: 'POST',
          body: JSON.stringify({ agreed_rules: true })
        })
      }
      navigate(`/candidate/${candidateId}/sections/${sectionId}/${sectionRoute(data.section.section_type)}`, { replace: true })
    } catch (requestError) {
      setError(String(requestError?.message || 'Unable to start section.'))
      setBusy(false)
    }
  }

  if (!data && !error) return <LoadingPulse fullPage />

  return (
    <div className="candidate-journey">
      <CandidatePortalHeader status="Instructions" statusTone="ok" candidateName={data?.candidate?.full_name} />
      <main className="candidate-page candidate-page--centered">
        <section className="instructions-card">
          <p className="eyebrow">{data?.section?.title || 'Section Instructions'}</p>
          <h1>{data?.section?.title || 'Instructions'}</h1>
          <p className="instructions-time">{data?.section?.duration_minutes || 0} Minutes</p>
          {error ? <p className="error">{error}</p> : null}
          <ul className="instructions-list">
            {(data?.rules || []).map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
          <div className="actions-row actions-row--center">
          <button className="primary" type="button" onClick={begin} disabled={busy || waitingForGeneration || Boolean(error && !waitingForGeneration)}>
            {busy ? 'Starting...' : data?.status === 'in_progress' ? 'Resume Section' : 'Start Section'}
          </button>
          </div>
        </section>
      </main>
    </div>
  )
}
