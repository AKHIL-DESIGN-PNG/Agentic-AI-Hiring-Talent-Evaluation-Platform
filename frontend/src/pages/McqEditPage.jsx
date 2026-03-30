import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, sanitizeMessage } from '../api'
import LoadingPulse from '../components/LoadingPulse'
import Modal from '../components/Modal'
import Toast from '../components/Toast'
import TopNav from '../components/TopNav'
import ActionButtons from '../components/mcq/ActionButtons'
import FormContainer from '../components/mcq/FormContainer'
import QuestionCard from '../components/mcq/QuestionCard'

let nextQuestionId = 1

function generateQuestionId() {
  return `q-${Date.now()}-${nextQuestionId++}`
}

function createEmptyQuestion() {
  const id = generateQuestionId()
  return {
    id,
    text: '',
    difficulty: 'MEDIUM',
    options: [
      { id: `${id}-o1`, value: '' },
      { id: `${id}-o2`, value: '' },
      { id: `${id}-o3`, value: '' },
      { id: `${id}-o4`, value: '' }
    ],
    correctOptionId: null,
    meta: {
      passage: '',
      audio: '',
      video: '',
      image: ''
    }
  }
}

function mapApiQuestion(question, index) {
  const id = String(question.id || generateQuestionId())
  const options = Array.isArray(question.options) && question.options.length
    ? question.options.map((value, optionIndex) => ({
        id: `${id}-o${optionIndex + 1}`,
        value: String(value || '')
      }))
    : createEmptyQuestion().options
  const correctOption = options.find((option) => option.value === String(question.answer || ''))

  return {
    id,
    text: String(question.question || ''),
    difficulty: String(question.difficulty || 'MEDIUM').toUpperCase(),
    options,
    correctOptionId: correctOption?.id || null,
    meta: {
      originalId: String(question.id || `${id}-${index + 1}`),
      passage: String(question.passage || ''),
      audio: String(question.audio || ''),
      video: String(question.video || ''),
      image: String(question.image || '')
    }
  }
}

function serializeQuestion(question, index) {
  const options = question.options.map((option) => option.value)
  const correctOption = question.options.find((option) => option.id === question.correctOptionId)

  return {
    id: question.meta?.originalId || question.id || `mcq-${index + 1}`,
    question: question.text,
    options,
    answer: correctOption?.value || '',
    difficulty: question.difficulty,
    passage: question.meta?.passage || '',
    audio: question.meta?.audio || '',
    video: question.meta?.video || '',
    image: question.meta?.image || ''
  }
}

export default function McqEditPage() {
  const { assessmentSlug, sectionKey } = useParams()
  const navigate = useNavigate()
  const [assessment, setAssessment] = useState(null)
  const [section, setSection] = useState(null)
  const [questions, setQuestions] = useState([])
  const [displayCount, setDisplayCount] = useState(0)
  const [errorsMap, setErrorsMap] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [loadFailed, setLoadFailed] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [aiCount, setAiCount] = useState(5)
  const [aiDifficulty, setAiDifficulty] = useState('MEDIUM')
  const [aiBusy, setAiBusy] = useState(false)

  useEffect(() => {
    async function load() {
      const detail = await api(`/api/admin/assessments/slug/${assessmentSlug}`, {}, true)
      const targetSection = (detail.sections || []).find((item) => item.key === sectionKey)
      if (!targetSection) throw new Error('Section not found')
      const data = await api(`/api/admin/assessments/${detail.id}/sections/${targetSection.id}/mcq-config`, {}, true)
      setAssessment(detail)
      setSection(data.section)
      setQuestions(data.questions?.length ? data.questions.map(mapApiQuestion) : [createEmptyQuestion()])
      setDisplayCount(typeof data.display_count === 'number' ? data.display_count : (data.questions?.length || 0))
      setErrorsMap({})
      setError('')
      setLoadFailed(false)
      setLoading(false)
    }

    load().catch((requestError) => {
      setError(sanitizeMessage(requestError?.message || 'Unable to load MCQ editor.'))
      setQuestions([])
      setDisplayCount(0)
      setLoadFailed(true)
      setLoading(false)
    })
  }, [assessmentSlug, sectionKey])

  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(''), 2400)
    return () => clearTimeout(timer)
  }, [toast])

  function updateQuestion(updatedQuestion) {
    setQuestions((current) => current.map((question) => (
      question.id === updatedQuestion.id ? updatedQuestion : question
    )))
  }

  function moveQuestion(sourceId, targetId) {
    setQuestions((current) => {
      const updated = [...current]
      const sourceIndex = updated.findIndex((item) => item.id === sourceId)
      const targetIndex = updated.findIndex((item) => item.id === targetId)
      if (sourceIndex < 0 || targetIndex < 0) return current
      const [moved] = updated.splice(sourceIndex, 1)
      updated.splice(targetIndex, 0, moved)
      return updated
    })
  }

  function moveOption(questionId, sourceId, targetId) {
    setQuestions((current) => current.map((question) => {
      if (question.id !== questionId) return question
      const updatedOptions = [...question.options]
      const sourceIndex = updatedOptions.findIndex((item) => item.id === sourceId)
      const targetIndex = updatedOptions.findIndex((item) => item.id === targetId)
      if (sourceIndex < 0 || targetIndex < 0) return question
      const [moved] = updatedOptions.splice(sourceIndex, 1)
      updatedOptions.splice(targetIndex, 0, moved)
      return { ...question, options: updatedOptions }
    }))
  }

  function removeQuestion(questionId) {
    setQuestions((current) => current.filter((question) => question.id !== questionId))
    setErrorsMap((current) => {
      const next = { ...current }
      delete next[questionId]
      return next
    })
  }

  function addQuestion() {
    setQuestions((current) => [...current, createEmptyQuestion()])
  }

  function clearError(questionId, field, optionId) {
    setErrorsMap((current) => {
      const nextQuestionErrors = { ...(current[questionId] || {}) }

      if (field === 'text') delete nextQuestionErrors.text
      if (field === 'correctAnswer') delete nextQuestionErrors.correctAnswer
      if (field === 'option' && optionId) {
        const nextOptionErrors = { ...(nextQuestionErrors.options || {}) }
        delete nextOptionErrors[optionId]
        nextQuestionErrors.options = Object.keys(nextOptionErrors).length ? nextOptionErrors : undefined
      }

      return { ...current, [questionId]: nextQuestionErrors }
    })
  }

  function validate() {
    const nextErrors = {}
    let valid = true

    questions.forEach((question) => {
      const questionErrors = {}

      if (!question.text.trim()) {
        questionErrors.text = 'Question is required'
        valid = false
      }

      const optionErrors = {}
      question.options.forEach((option) => {
        if (!option.value.trim()) {
          optionErrors[option.id] = 'Option cannot be empty'
          valid = false
        }
      })
      if (Object.keys(optionErrors).length) questionErrors.options = optionErrors

      if (!question.correctOptionId) {
        questionErrors.correctAnswer = 'Select the correct answer'
        valid = false
      }

      if (Object.keys(questionErrors).length) nextErrors[question.id] = questionErrors
    })

    setErrorsMap(nextErrors)
    return valid
  }

  async function handleSave() {
    if (loadFailed) return

    if (!validate()) {
      setToast('Fix the highlighted fields before saving.')
      return
    }

    try {
      setSaving(true)
      setError('')
      await api(
        `/api/admin/assessments/${assessment.id}/sections/${section.id}/mcq-config`,
        {
          method: 'PUT',
          body: JSON.stringify({
            questions: questions.map(serializeQuestion),
            display_count: Math.max(0, Math.min(displayCount, questions.length)),
          })
        },
        true
      )
      const assignedCount = Math.max(0, Math.min(displayCount, questions.length))
      setToast(`Saved ${assignedCount} assigned question${assignedCount === 1 ? '' : 's'}.`)
    } catch (requestError) {
      setError(sanitizeMessage(requestError?.message || 'Unable to save MCQ questions.'))
    } finally {
      setSaving(false)
    }
  }

  async function handleAiGenerate() {
    try {
      setAiBusy(true)
      const response = await api(
        `/api/admin/assessments/${assessment.id}/sections/${section.id}/mcq-ai-generate`,
        {
          method: 'POST',
          body: JSON.stringify({ count: aiCount, difficulty: aiDifficulty })
        },
        true
      )
      const generated = (response.questions || []).map(mapApiQuestion)
      setQuestions((current) => [...current, ...generated])
      setAiOpen(false)
      setToast(`Added ${generated.length} AI question${generated.length === 1 ? '' : 's'}.`)
    } catch (requestError) {
      setError(sanitizeMessage(requestError?.message || 'Unable to generate AI questions.'))
    } finally {
      setAiBusy(false)
    }
  }

  if (loading) {
    return (
      <div>
        <TopNav />
        <LoadingPulse fullPage />
      </div>
    )
  }

  return (
    <div className="mcq-edit-page-shell">
      <TopNav />
      <Toast open={Boolean(toast)} message={toast} />

      <main className="mcq-edit-page">
        <header className="mcq-edit-header">
          <div>
            <p className="muted">AITS &gt; Assessments &gt; MCQ Editor</p>
            <h1>Edit MCQ Questions</h1>
            <p className="mcq-edit-header__meta">
              {section?.title || 'MCQ Section'} · {questions.length} question{questions.length === 1 ? '' : 's'}
            </p>
          </div>
          <ActionButtons
            onCancel={() => navigate(-1)}
            onSave={handleSave}
            isSaving={saving || loadFailed}
          />
        </header>

        {error && <p className="error">{error}</p>}
        {!loadFailed && (
          <div className="actions-row">
            <button className="ghost-btn" type="button" onClick={() => setAiOpen(true)}>
              AI Generate
            </button>
          </div>
        )}

        {loadFailed ? (
          <FormContainer
            title="MCQ Questions Unavailable"
            description="The editor could not load the configured MCQ questions from the backend. Restart the backend server and retry this page."
          >
            <div className="mcq-edit-empty">
              <button className="primary" type="button" onClick={() => window.location.reload()}>
                Retry
              </button>
            </div>
          </FormContainer>
        ) : (
          <FormContainer
            title="Question Set"
            description=""
          >
            <div className="mcq-edit-settings">
              <label className="mcq-edit-field">
                <span className="mcq-edit-field__label">Questions shown to candidate</span>
                <input
                  className="mcq-edit-input"
                  type="number"
                  min="0"
                  max={questions.length}
                  value={Math.max(0, Math.min(displayCount, questions.length))}
                  onChange={(event) => {
                    const next = Number(event.target.value)
                    if (Number.isNaN(next)) return
                    setDisplayCount(Math.max(0, Math.min(next, questions.length)))
                  }}
                />
              </label>
              <p className="muted">
                Candidate will see {Math.max(0, Math.min(displayCount, questions.length))} of {questions.length} configured questions.
              </p>
            </div>
            <div className="mcq-edit-list">
              {questions.map((question, index) => (
                <QuestionCard
                  key={question.id}
                  question={question}
                  index={index}
                  totalQuestions={questions.length}
                  errors={errorsMap[question.id]}
                  onUpdate={updateQuestion}
                  onRemove={() => removeQuestion(question.id)}
                  onClearError={(field, optionId) => clearError(question.id, field, optionId)}
                  onMoveQuestion={moveQuestion}
                  onMoveOption={moveOption}
                />
              ))}
            </div>

            <div className="mcq-edit-add-row">
              <button className="mcq-edit-add-btn" type="button" onClick={addQuestion}>
                Add Question
              </button>
            </div>
          </FormContainer>
        )}
      </main>
      <Modal open={aiOpen} title="Generate MCQs with AI" onClose={() => setAiOpen(false)}>
        <div className="stack modal-body">
          <label>Number of questions</label>
          <input type="number" min="1" max="20" value={aiCount} onChange={(event) => setAiCount(Number(event.target.value) || 1)} />
          <label>Difficulty</label>
          <select value={aiDifficulty} onChange={(event) => setAiDifficulty(event.target.value)}>
            <option value="EASY">EASY</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="HARD">HARD</option>
          </select>
          <div className="actions-row">
            <button className="ghost-btn" type="button" onClick={() => setAiOpen(false)}>Cancel</button>
            <button className="primary" type="button" onClick={handleAiGenerate} disabled={aiBusy}>
              {aiBusy ? 'Generating...' : 'Generate'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
