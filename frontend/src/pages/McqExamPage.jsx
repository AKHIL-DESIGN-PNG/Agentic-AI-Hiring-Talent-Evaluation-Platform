import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import CameraPanel from '../components/CameraPanel'
import LoadingPulse from '../components/LoadingPulse'
import Modal from '../components/Modal'
import Toast from '../components/Toast'
import useExamSecurity from '../hooks/useExamSecurity'
import useMinimumDelay from '../hooks/useMinimumDelay'

const QUESTION_TIME_SECONDS = 60

function formatClock(remaining) {
  const m = Math.floor(remaining / 60)
  const s = remaining % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export default function McqExamPage() {
  const { candidateId, sectionId } = useParams()
  const navigate = useNavigate()
  const localKey = `mcq-progress:${candidateId}:${sectionId}`
  const activeViolationRef = useRef(null)
  const [data, setData] = useState(null)
  const [answers, setAnswers] = useState({})
  const [currentIndex, setCurrentIndex] = useState(0)
  const [questionRemaining, setQuestionRemaining] = useState(QUESTION_TIME_SECONDS)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [toast, setToast] = useState('')
  const [activeViolation, setActiveViolation] = useState(null)
  const [proctor, setProctor] = useState({
    faceVisible: true,
    blocked: false,
    status: 'initializing',
    gadgetDetected: false,
    streamReady: false,
    faces: 1,
    multipleFaces: false,
    mobileDetected: false,
    noFaceDurationSec: 0
  })
  const [nextPrompt, setNextPrompt] = useState(null)
  const [sectionSubmitted, setSectionSubmitted] = useState(false)

  const security = useExamSecurity({
    candidateId,
    sectionId,
    enabled: Boolean(data),
    onViolationLimit: () => submitAnswers(true)
  })

  useEffect(() => {
    async function load() {
      const info = await api(`/api/candidate/${candidateId}/sections/${sectionId}/exam`)
      const localSaved = JSON.parse(localStorage.getItem(localKey) || '{}')
      const mergedAnswers = { ...(info.saved_answers || {}), ...(localSaved.answers || {}) }
      const mergedIndex = Number.isInteger(localSaved.current_index)
        ? localSaved.current_index
        : (info.saved_state?.current_index || 0)

      setData(info)
      setAnswers(mergedAnswers)
      setCurrentIndex(Math.max(0, Math.min(mergedIndex, (info.questions?.length || 1) - 1)))
      setQuestionRemaining(QUESTION_TIME_SECONDS)
    }

    load().catch((error) => {
      console.error('mcq_exam_load_failed', error)
      navigate(`/candidate/${candidateId}/dashboard`, { replace: true })
    })
  }, [candidateId, sectionId, navigate, localKey])

  useEffect(() => {
    if (!data || data.generated_count >= data.expected_count) return undefined
    const id = window.setInterval(async () => {
      try {
        const info = await api(`/api/candidate/${candidateId}/sections/${sectionId}/exam`)
        setData((current) => {
          if (!current) return info
          return {
            ...current,
            ...info,
            questions: info.questions
          }
        })
      } catch (error) {
        console.error('mcq_exam_poll_failed', error)
      }
    }, 3000)
    return () => window.clearInterval(id)
  }, [data, candidateId, sectionId])

  useEffect(() => {
    if (!data || isSubmitting || sectionSubmitted) return undefined
    const timer = setInterval(() => {
      setQuestionRemaining((value) => {
        if (value <= 1) {
          window.setTimeout(() => handleNext(true), 0)
          return QUESTION_TIME_SECONDS
        }
        return value - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [data, isSubmitting, currentIndex])

  useEffect(() => {
    if (data && !security.fullscreenActive) {
      security.requestFullscreen()
    }
  }, [data, security.fullscreenActive])

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(''), 2800)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    if (!security.warning?.message) return
    setToast(security.warning.message)
    security.dismissWarning()
  }, [security.warning])

  useEffect(() => {
    if (!data || sectionSubmitted) return undefined
    const autosave = async () => {
      const payload = { answers, current_index: currentIndex }
      localStorage.setItem(localKey, JSON.stringify(payload))
      if (!navigator.onLine) return
      try {
        await api(`/api/candidate/${candidateId}/sections/${sectionId}/save-mcq`, {
          method: 'POST',
          body: JSON.stringify(payload)
        })
      } catch (error) {
        console.error('mcq_autosave_failed', error)
      }
    }

    const id = setInterval(autosave, 4000)
    return () => clearInterval(id)
  }, [answers, candidateId, currentIndex, data, localKey, sectionId, sectionSubmitted])

  useEffect(() => {
    if (!data) return
    let next = null
    if (proctor.mobileDetected) {
      next = { key: 'mobile_detected', message: 'Mobile phone detected in camera frame.' }
    } else if (proctor.multipleFaces) {
      next = { key: 'multiple_faces', message: 'Multiple faces detected in camera frame.' }
    } else if (proctor.faces === 0) {
      next = { key: 'no_face', message: 'No face detected.' }
    }

    setActiveViolation(next)
    if (!next) {
      activeViolationRef.current = null
      return
    }
    if (activeViolationRef.current === next.key) return
    activeViolationRef.current = next.key
    security.raiseWarning(next.message, { increment: true, event: next.key, cooldownMs: 1500 })
    setToast(next.message)
  }, [data, proctor.mobileDetected, proctor.multipleFaces, proctor.faces, security])

  const activeQuestion = data?.questions?.[currentIndex]
  const ready = useMinimumDelay(Boolean(activeQuestion))
  const isLastFiveSeconds = questionRemaining <= 5

  async function submitAnswers(auto = false, reason = 'timeout') {
    if (isSubmitting) return
    setIsSubmitting(true)
    try {
      const result = await api(`/api/candidate/${candidateId}/sections/${sectionId}/submit-mcq`, {
        method: 'POST',
        body: JSON.stringify({ answers })
      })
      setSectionSubmitted(true)
      localStorage.removeItem(localKey)
      if (auto) {
        navigate(`/candidate/${candidateId}/completed`, {
          replace: true,
          state: { timedOut: reason === 'timeout', terminated: reason === 'terminated' }
        })
        return
      }
      if (result.next_section_id) {
        setNextPrompt({ sectionId: result.next_section_id, sectionName: result.next_section_name })
        setIsSubmitting(false)
        return
      }
      navigate(`/candidate/${candidateId}/review`, { replace: true })
    } catch (error) {
      console.error('mcq_submit_failed', error)
      if (!auto) {
        security.raiseWarning('Unable to submit right now. Your progress remains saved locally.', {
          increment: false,
          event: 'submit_failed'
        })
      }
      setIsSubmitting(false)
    }
  }

  function handleNext(autoAdvance = false) {
    if (!data || isSubmitting) return
    if (currentIndex === data.questions.length - 1) {
      if (data.generated_count < data.expected_count || data.generation_status === 'generating') {
        setToast('Waiting for the next generated question batch.')
        setQuestionRemaining(QUESTION_TIME_SECONDS)
        return
      }
      submitAnswers(autoAdvance, 'timeout')
      return
    }
    setCurrentIndex((value) => Math.min(value + 1, data.questions.length - 1))
    setQuestionRemaining(QUESTION_TIME_SECONDS)
  }

  const shouldBlur = Boolean(
    security.securityLocked ||
    activeViolation ||
    proctor.status === 'camera_denied' ||
    proctor.status === 'error' ||
    proctor.status === 'unavailable'
  )
  const blurReason = security.tabHidden
    ? 'To continue the exam go to fullscreen.'
    : !security.fullscreenActive
      ? 'Fullscreen is required. Return to fullscreen to continue.'
      : security.securityLocked
        ? 'Close screen-sharing/virtual camera apps to continue.'
        : activeViolation?.key === 'mobile_detected'
          ? 'Mobile phone detected. Remove the device to continue.'
          : activeViolation?.key === 'multiple_faces'
            ? 'Multiple faces detected. Keep only one face in frame.'
            : activeViolation?.key === 'no_face'
              ? 'No face detected. Keep your face visible.'
              : 'Security monitoring issue. Please restore camera access.'

  if (!data || !activeQuestion || !ready) {
    return <LoadingPulse fullPage />
  }

  return (
    <main className="secure-exam-shell">
      <header className="exam-header">
        <div className="exam-header__title">{data.section.title}</div>
        <div className="exam-header__meta">
          <span className="network-indicator">
            <span className={security.networkState.barClass}>
              {security.networkState.bars.map((active, index) => (
                <span key={index} className={`network-signal__bar${active ? ' network-signal__bar--active' : ''}`} />
              ))}
            </span>
          </span>
          {!security.fullscreenActive && (
            <button className="ghost-btn exam-header__fullscreen-btn" type="button" onClick={security.requestFullscreen}>
              Resume Fullscreen
            </button>
          )}
          <span>{data.candidate.full_name}</span>
        </div>
      </header>

      <section className="mcq-shell">
        <div className={`mcq-stage ${shouldBlur ? 'mcq-stage--blurred' : ''}`}>
          {shouldBlur && (
            <div className="blur-message">
              <h3>Assessment Locked</h3>
              <p>{blurReason}</p>
            </div>
          )}
          <article key={activeQuestion.id} className="mcq-card question-transition">
            <div className="question-meta-row">
              <p className="eyebrow">Question {currentIndex + 1} of {data.questions.length}</p>
              <span
                className={`question-timer ${isLastFiveSeconds ? 'question-timer--danger' : 'question-timer--safe'}`}
              >
                {formatClock(questionRemaining)}
              </span>
            </div>
            <h2>{activeQuestion.question}</h2>
            {activeQuestion.passage && <p className="mcq-passage">{activeQuestion.passage}</p>}
            {(activeQuestion.audio || activeQuestion.video || activeQuestion.image) && (
              <div className="question-media-preview question-media-preview--top">
                {activeQuestion.audio && <audio controls className="section-media-player" src={activeQuestion.audio} />}
                {activeQuestion.video && <video controls className="section-media-player" src={activeQuestion.video} />}
                {activeQuestion.image && <img src={activeQuestion.image} alt="Question media" className="section-media-image" />}
              </div>
            )}
            <div className="options">
              {activeQuestion.options.map((opt) => (
                <label key={opt} className={`option-card ${answers[activeQuestion.id] === opt ? 'option-card--active' : ''}`}>
                  <input
                    type="radio"
                    name={activeQuestion.id}
                    value={opt}
                    checked={answers[activeQuestion.id] === opt}
                    onChange={(event) => setAnswers((prev) => ({ ...prev, [activeQuestion.id]: event.target.value }))}
                  />
                  <span>{opt}</span>
                </label>
              ))}
            </div>
            <div className="exam-footer-actions">
              <button
                className="primary"
                type="button"
                disabled={security.securityLocked || isSubmitting}
                onClick={() => handleNext(false)}
              >
                {currentIndex === data.questions.length - 1
                  ? (data.generated_count < data.expected_count || data.generation_status === 'generating'
                      ? 'Waiting for Next Batch'
                      : (isSubmitting ? 'Submitting...' : 'Submit Section'))
                  : 'Next'}
              </button>
            </div>
          </article>
        </div>
      </section>

      <CameraPanel candidateId={candidateId} onProctorUpdate={setProctor} />
      <Toast open={Boolean(toast)} message={toast} />

      <Modal
        open={Boolean(nextPrompt)}
        title="Next Section"
        onClose={() => setNextPrompt(null)}
        disableBackdropClose
        hideCloseButton
      >
        <div className="stack modal-body">
          <p>Move to next section {nextPrompt?.sectionName}?</p>
          <div className="actions-row">
            <button className="ghost-btn" type="button" onClick={() => navigate(`/candidate/${candidateId}/review`, { replace: true })}>
              No
            </button>
            <button className="primary" type="button" onClick={() => navigate(`/candidate/${candidateId}/sections/${encodeURIComponent(nextPrompt.sectionId)}/instructions`, { replace: true })}>
              Yes
            </button>
          </div>
        </div>
      </Modal>
    </main>
  )
}
