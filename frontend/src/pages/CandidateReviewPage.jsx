import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import LoadingPulse from '../components/LoadingPulse'
import useMinimumDelay from '../hooks/useMinimumDelay'

export default function CandidateReviewPage() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [finalizing, setFinalizing] = useState(false)
  const ready = useMinimumDelay(Boolean(data))

  useEffect(() => {
    api(`/api/candidate/${candidateId}/review`)
      .then(setData)
      .catch((error) => {
        console.error('candidate_review_load_failed', error)
        navigate(`/candidate/${candidateId}/completed`, { replace: true })
      })
  }, [candidateId, navigate])

  if (!data || !ready) {
    return <LoadingPulse fullPage />
  }

  async function finishAssessment() {
    setFinalizing(true)
    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen()
      } catch (error) {
        console.error('exit_fullscreen_failed', error)
      }
    }
    navigate(`/candidate/${candidateId}/completed`, { replace: true })
  }

  function verbalAttemptedCount(prompt, preview) {
    const listeningCount = ((prompt?.listening_blocks || []).flatMap((block) => {
      if (Array.isArray(block.questions) && block.questions.length) {
        return block.questions.filter((item) => preview?.listening_answers?.[item.id])
      }
      return preview?.listening_answers?.[block.id] ? [block] : []
    })).length
    const speakingCount = (prompt?.speaking_tasks || []).filter((item) =>
      (preview?.speaking_responses || []).some((entry) => entry.id === item.id && (entry.audio_url || entry.transcript))
    ).length
    const writingCount = (prompt?.writing_tasks || []).filter((item) =>
      (preview?.writing_responses || []).some((entry) => entry.id === item.id && String(entry.text || '').trim())
    ).length
    const dragDropCount = (prompt?.drag_drop_questions || []).filter((item) =>
      Array.isArray(preview?.drag_drop_answers?.[item.id]) && preview.drag_drop_answers[item.id].length > 0
    ).length
    return listeningCount + speakingCount + writingCount + dragDropCount
  }

  return (
    <main className="candidate-page candidate-page--centered">
      <section className="candidate-card" style={{ width: 'min(980px, 100%)' }}>
        <div className="candidate-review__head">
          <p className="eyebrow">Assessment Preview</p>
          <h1>{data.assessment.name}</h1>
          <p className="muted">Review how many questions you attempted before final submission.</p>
        </div>

        <div className="review-list">
          {data.sections.map(({ section, attempt, preview, prompt }) => (
            <article className="review-item" key={section.id}>
              <div>
                <h3>{section.title}</h3>
                <p className="muted">{attempt.status === 'completed' ? 'Completed' : 'Pending'}</p>
                {section.section_type === 'mcq' && (
                  <p className="muted" style={{ margin: '12px 0 0' }}>
                    Questions attempted: {(preview.questions || []).filter((item) => item.selected_answer).length} / {(preview.questions || []).length}
                  </p>
                )}
                {section.section_type === 'verbal' && (
                  <p className="muted" style={{ margin: '12px 0 0' }}>
                    Questions attempted: {verbalAttemptedCount(prompt, preview)}
                  </p>
                )}
                {section.section_type === 'coding' && (
                  <p className="muted" style={{ margin: '12px 0 0' }}>
                    Problems attempted: {(preview.problem_states || []).filter((item) => String(item?.code || '').trim()).length} / {((prompt.problems || []).length || 1)}
                  </p>
                )}
              </div>
            </article>
          ))}
        </div>

        <div className="actions-row actions-row--center">
          <button className="primary" type="button" onClick={finishAssessment} disabled={finalizing}>
            {finalizing ? 'Submitting...' : 'Final Submit'}
          </button>
        </div>
      </section>
    </main>
  )
}
