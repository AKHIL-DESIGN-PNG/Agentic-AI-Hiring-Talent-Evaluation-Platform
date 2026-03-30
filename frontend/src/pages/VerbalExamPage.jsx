import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { API_BASE, api } from '../api'
import CameraPanel from '../components/CameraPanel'
import LoadingPulse from '../components/LoadingPulse'
import Toast from '../components/Toast'
import useExamSecurity from '../hooks/useExamSecurity'

const mutedLabelStyle = {
  margin: 0,
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.12em',
  color: '#7b89a4'
}

const inputStyle = {
  width: '100%',
  padding: '12px 14px',
  border: '1px solid #d3dbe8',
  borderRadius: 12,
  background: '#fff',
  color: '#14223e'
}

const ghostButtonStyle = {
  border: '1px solid #ced8e8',
  background: '#fff',
  color: '#1f2f4a',
  borderRadius: 12,
  padding: '10px 14px',
  fontSize: 12,
  fontWeight: 700,
  cursor: 'pointer'
}

const primaryButtonStyle = {
  border: 'none',
  background: '#252d72',
  color: '#fff',
  borderRadius: 12,
  padding: '12px 18px',
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer'
}

function MediaPlayer({ url, type }) {
  const resolvedUrl = resolveMediaUrl(url)
  const mediaKind = detectMediaKind(resolvedUrl, type)

  if (!resolvedUrl) {
    return <p style={{ margin: 0, fontSize: 13, color: '#9fb1cf' }}>No media uploaded for this block.</p>
  }
  if (mediaKind === 'video') {
    return <video controls src={resolvedUrl} style={{ width: '100%', borderRadius: 12 }} />
  }
  return <audio controls src={resolvedUrl} style={{ width: '100%' }} />
}

function resolveMediaUrl(url) {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('blob:') || value.startsWith('data:')) return value
  if (/^https?:\/\//i.test(value)) return value
  if (value.startsWith('/')) return `${API_BASE}${value}`
  return `${API_BASE}/${value.replace(/^\/+/, '')}`
}

function detectMediaKind(url, type) {
  const normalizedType = String(type || '').trim().toLowerCase()
  const normalizedUrl = String(url || '').trim().toLowerCase()

  if (/\.(mp3|wav|ogg|m4a|aac|flac|opus|weba)$/i.test(normalizedUrl)) return 'audio'
  if (/\.(mp4|webm|mov|m4v|avi|mkv|ogv)$/i.test(normalizedUrl)) return 'video'
  return normalizedType === 'video' ? 'video' : 'audio'
}

function QuestionMeta({ sectionLabel, currentIndex, total }) {
  return (
    <>
      <p className="eyebrow" style={{ margin: 0 }}>{sectionLabel}</p>
      <span className="pill">{currentIndex + 1} / {total}</span>
    </>
  )
}

function ListeningQuestion({ item, answers, onAnswer }) {
  const activeQuestionIndex = item.activeQuestionIndex || 0
  const activeQuestion = item.questions?.[activeQuestionIndex] || item.question || null
  const isText = item.type === 'listening_text' || !activeQuestion
  const mediaKind = detectMediaKind(resolveMediaUrl(item.block.media_url), item.block.media_type)

  return (
    <div style={{ display: 'grid', gap: 20 }}>
      <div
        style={{
          padding: 18,
          boxShadow: 'none',
          background: mediaKind === 'video' ? '#10131a' : '#f8fbff',
          color: mediaKind === 'video' ? '#d6deeb' : '#1f2f4a',
          minHeight: mediaKind === 'video' ? 0 : 'auto',
          display: 'grid',
          justifyItems: 'center',
          alignItems: 'center',
          borderRadius: 16,
          border: '1px solid #dbe3ef',
          maxWidth: mediaKind === 'video' ? 640 : 420,
          width: '100%',
          margin: '0 auto'
        }}
      >
        <MediaPlayer url={item.block.media_url} type={item.block.media_type} />
      </div>

      <div style={{ display: 'grid', gap: 16 }}>
        <p className="eyebrow" style={{ margin: 0 }}>
          {isText ? item.indexLabel : `Question ${activeQuestionIndex + 1} of ${item.questions.length}`}
        </p>

        {isText ? (
          <>
            <label style={mutedLabelStyle}>Your Response</label>
            <textarea
              rows={8}
              value={answers[item.block.id] || ''}
              onChange={(event) => onAnswer(item.block.id, event.target.value)}
              placeholder="Type your answer here"
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </>
        ) : (
          <>
            <h2 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: '#14223e' }}>
              {activeQuestion.prompt}
            </h2>
            <div className="options">
              {(activeQuestion.options || []).map((option, index) => {
                const checked = (answers[activeQuestion.id] || '') === option
                return (
                  <label
                    key={`${activeQuestion.id}-${index}`}
                    className={`option-card ${checked ? 'option-card--active' : ''}`}
                  >
                    <input
                      type="radio"
                      name={activeQuestion.id}
                      checked={checked}
                      value={option}
                      onChange={(event) => onAnswer(activeQuestion.id, event.target.value)}
                    />
                    <span>{option}</span>
                  </label>
                )
              })}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function SpeakingQuestion({
  item,
  responses,
  recordingTaskId,
  recordingError,
  onStartRecording,
  onStopRecording
}) {
  const response = responses.find((entry) => entry.id === item.task.id) || {}
  const isRecording = recordingTaskId === item.task.id

  return (
    <div style={{ display: 'grid', gap: 24 }}>
      <p className="eyebrow" style={{ margin: 0 }}>{item.indexLabel}</p>

      <h2 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: '#14223e', lineHeight: 1.35 }}>
        {item.task.prompt}
      </h2>

      <div style={{ display: 'grid', justifyItems: 'center', gap: 18, padding: '12px 0 4px' }}>
        <div
          style={{
            width: 140,
            height: 140,
            borderRadius: '50%',
            display: 'grid',
            placeItems: 'center',
            background: isRecording ? '#252d72' : '#f6f8fb',
            color: isRecording ? '#fff' : '#1f2f4a',
            border: `1px solid ${isRecording ? '#252d72' : '#dbe3ef'}`
          }}
        >
          <strong>{isRecording ? 'Recording' : 'Ready'}</strong>
        </div>

        {response.audio_url ? (
          <audio controls src={response.audio_url} style={{ width: '100%', maxWidth: 460 }} />
        ) : (
          <p style={{ margin: 0, fontSize: 13, color: '#5d6b88' }}>Record your answer once and move to the next question.</p>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          {!isRecording ? (
            <button type="button" onClick={() => onStartRecording(item.task.id)} style={ghostButtonStyle}>
              {response.audio_url ? 'Re-record' : 'Start Recording'}
            </button>
          ) : (
            <button type="button" onClick={() => onStopRecording(item.task.id)} style={primaryButtonStyle}>
              Stop Recording
            </button>
          )}
        </div>

        {recordingError ? (
          <p style={{ margin: 0, fontSize: 12, color: '#ba1a1a' }}>{recordingError}</p>
        ) : null}
      </div>
    </div>
  )
}

function WritingQuestion({ item, responses, onUpdate }) {
  const response = responses.find((entry) => entry.id === item.task.id) || {}

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <p className="eyebrow" style={{ margin: 0 }}>{item.indexLabel}</p>
        <span className="pill">Min {item.task.min_words} words</span>
      </div>

      <h2 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: '#14223e', lineHeight: 1.35 }}>
        {item.task.topic}
      </h2>

      <label style={mutedLabelStyle}>Your Answer</label>
      <textarea
        rows={9}
        value={response.text || ''}
        onChange={(event) => onUpdate(item.task.id, event.target.value)}
        placeholder="Write your response here"
        style={{ ...inputStyle, resize: 'vertical' }}
      />
    </div>
  )
}

function DragDropQuestion({
  item,
  answers,
  draggingToken,
  onFill,
  onClear,
  onRemoveToken,
  onDragStart,
  onDragEnd
}) {
  const chosen = answers[item.task.id] || []
  const template = String(item.task.template || '')
  const slotTokens = template.match(/__\d+__|____/g) || []
  const sentenceParts = template.split(/__\d+__|____/g)
  const slotCount = slotTokens.length || (item.task.answer_order || []).length
  const availableOptions = (item.task.options || []).filter((option) => !chosen.includes(option))

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <p className="eyebrow" style={{ margin: 0 }}>{item.indexLabel}</p>
        <button type="button" onClick={() => onClear(item.task.id)} style={ghostButtonStyle}>Clear</button>
      </div>

      <h2 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: '#14223e', lineHeight: 1.35 }}>
        Fill in the blanks
      </h2>

      <div style={{ padding: 0 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, fontSize: 20, lineHeight: 2.1 }}>
          {Array.from({ length: slotCount }).map((_, index) => (
            <div key={index} style={{ display: 'contents' }}>
              <span>{sentenceParts[index] || ''}</span>
              <div
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault()
                  const option = event.dataTransfer.getData('text/plain')
                  if (option) onFill(item.task.id, option)
                  onDragEnd()
                }}
                style={{
                  minWidth: 150,
                  minHeight: 48,
                  display: 'grid',
                  placeItems: 'center',
                  padding: '0 16px',
                  borderRadius: 16,
                  border: '2px dashed #9fb0d1',
                  background: '#f7f9ff'
                }}
              >
                {chosen[index] ? (
                  <button type="button" onClick={() => onRemoveToken(item.task.id, index)} style={ghostButtonStyle}>
                    {chosen[index]}
                  </button>
                ) : '____'}
              </div>
            </div>
          ))}
          <span>{sentenceParts[slotCount] || ''}</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 18 }}>
          {availableOptions.map((option) => (
            <button
              key={option}
              type="button"
              draggable
              onDragStart={(event) => {
                event.dataTransfer.setData('text/plain', option)
                onDragStart(option)
              }}
              onDragEnd={onDragEnd}
              onClick={() => onFill(item.task.id, option)}
              style={draggingToken === option ? primaryButtonStyle : ghostButtonStyle}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function BlurOverlay({ reason }) {
  return (
    <div style={{
      position: 'absolute',
      inset: 0,
      zIndex: 20,
      display: 'grid',
      placeItems: 'center',
      borderRadius: 18,
      background: 'rgba(255, 255, 255, 0.8)',
      backdropFilter: 'blur(10px)'
    }}
    >
      <div style={{ textAlign: 'center' }}>
        <h3 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: '#14223e' }}>Assessment Locked</h3>
        <p style={{ margin: '8px 0 0', fontSize: 14, color: '#5d6b88' }}>{reason}</p>
      </div>
    </div>
  )
}

export default function VerbalExamPage() {
  const { candidateId, sectionId } = useParams()
  const navigate = useNavigate()
  const activeViolationRef = useRef(null)

  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [listeningAnswers, setListeningAnswers] = useState({})
  const [listeningQuestionIndexByBlock, setListeningQuestionIndexByBlock] = useState({})
  const [speakingResponses, setSpeakingResponses] = useState([])
  const [writingResponses, setWritingResponses] = useState([])
  const [dragDropAnswers, setDragDropAnswers] = useState({})
  const [draggingToken, setDraggingToken] = useState(null)
  const [recordingTaskId, setRecordingTaskId] = useState(null)
  const [recordingError, setRecordingError] = useState('')
  const [recorderState, setRecorderState] = useState({})
  const [toastMsg, setToastMsg] = useState('')
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
  const recognitionStateRef = useRef({})

  const security = useExamSecurity({
    candidateId,
    sectionId,
    enabled: Boolean(data),
    onViolationLimit: () => submit(true)
  })

  useEffect(() => {
    api(`/api/candidate/${candidateId}/sections/${sectionId}/exam`)
      .then((info) => {
        setData(info)
        const saved = info.saved_state || {}
        setListeningAnswers(saved.listening_answers || {})
        setListeningQuestionIndexByBlock(saved.listening_question_index_by_block || {})
        setSpeakingResponses(saved.speaking_responses || [])
        setWritingResponses(saved.writing_responses || [])
        setDragDropAnswers(saved.drag_drop_answers || {})
      })
      .catch((requestError) => setError(String(requestError?.message || 'Unable to load verbal section.')))
  }, [candidateId, sectionId])

  useEffect(() => {
    if (data && !security.fullscreenActive) {
      security.requestFullscreen()
    }
  }, [data, security.fullscreenActive])

  useEffect(() => {
    if (!toastMsg) return undefined
    const timer = window.setTimeout(() => setToastMsg(''), 2800)
    return () => window.clearTimeout(timer)
  }, [toastMsg])

  useEffect(() => {
    if (!security.warning?.message) return
    setToastMsg(security.warning.message)
    security.dismissWarning()
  }, [security.warning])

  const prompt = data?.prompt || {}
  const listeningBlocks = prompt.listening_blocks || []
  const speakingTasks = prompt.speaking_tasks || []
  const writingTasks = prompt.writing_tasks || []
  const dragDropQuestions = prompt.drag_drop_questions || []

  const questionItems = useMemo(() => {
    const items = []

    listeningBlocks.forEach((block, blockIndex) => {
      if (Array.isArray(block.questions) && block.questions.length) {
        items.push({
          id: block.id,
          type: 'listening',
          sectionLabel: `Listening ${blockIndex + 1}`,
          indexLabel: `Question 1 of ${block.questions.length}`,
          block,
          questions: block.questions
        })
      } else {
        items.push({
          id: block.id,
          type: 'listening_text',
          sectionLabel: `Listening ${blockIndex + 1}`,
          indexLabel: 'Written Response',
          block
        })
      }
    })

    speakingTasks.forEach((task, index) => {
      items.push({
        id: task.id,
        type: 'speaking',
        sectionLabel: `Speaking ${index + 1}`,
        indexLabel: `Prompt ${index + 1} of ${speakingTasks.length}`,
        task
      })
    })

    writingTasks.forEach((task, index) => {
      items.push({
        id: task.id,
        type: 'writing',
        sectionLabel: `Writing ${index + 1}`,
        indexLabel: `Prompt ${index + 1} of ${writingTasks.length}`,
        task
      })
    })

    dragDropQuestions.forEach((task, index) => {
      items.push({
        id: task.id,
        type: 'drag_drop',
        sectionLabel: `Fill In The Blanks ${index + 1}`,
        indexLabel: `Question ${index + 1} of ${dragDropQuestions.length}`,
        task
      })
    })

    return items
  }, [listeningBlocks, speakingTasks, writingTasks, dragDropQuestions])

  useEffect(() => {
    if (!data) return
    let next = null

    if (proctor.mobileDetected) next = { key: 'mobile_detected', message: 'Mobile phone detected in camera frame.' }
    else if (proctor.multipleFaces) next = { key: 'multiple_faces', message: 'Multiple faces detected in camera frame.' }
    else if (proctor.faces === 0) next = { key: 'no_face', message: 'No face detected.' }

    setActiveViolation(next)
    if (!next) {
      activeViolationRef.current = null
      return
    }
    if (activeViolationRef.current === next.key) return
    activeViolationRef.current = next.key
    security.raiseWarning(next.message, { increment: true, event: next.key, cooldownMs: 1500 })
    setToastMsg(next.message)
  }, [data, proctor.mobileDetected, proctor.multipleFaces, proctor.faces, security])

  useEffect(() => () => {
    Object.values(recognitionStateRef.current).forEach((recognition) => {
      try {
        recognition.stop()
      } catch {}
    })
  }, [])

  function handleListeningAnswer(id, value) {
    setListeningAnswers((previous) => ({ ...previous, [id]: value }))
  }

  function updateSpeaking(id, patch) {
    setSpeakingResponses((previous) => {
      const next = [...previous]
      const index = next.findIndex((item) => item.id === id)
      if (index >= 0) next[index] = { ...next[index], ...patch }
      else next.push({ id, ...patch })
      return next
    })
  }

  function updateWriting(id, text) {
    setWritingResponses((previous) => {
      const next = [...previous]
      const index = next.findIndex((item) => item.id === id)
      if (index >= 0) next[index] = { ...next[index], text }
      else next.push({ id, text })
      return next
    })
  }

  function fillDragDrop(id, option) {
    setDragDropAnswers((previous) => {
      const current = previous[id] || []
      const expected = dragDropQuestions.find((task) => task.id === id)?.answer_order?.length || 0
      if (expected && current.length >= expected) return previous
      return { ...previous, [id]: [...current, option] }
    })
  }

  function clearDragDrop(id) {
    setDragDropAnswers((previous) => ({ ...previous, [id]: [] }))
  }

  function removeDragToken(id, index) {
    setDragDropAnswers((previous) => ({
      ...previous,
      [id]: (previous[id] || []).filter((_, itemIndex) => itemIndex !== index)
    }))
  }

  async function startRecording(taskId) {
    try {
      setRecordingError('')
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const chunks = []
      const startedAt = Date.now()

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        const url = URL.createObjectURL(blob)
        const durationSeconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000))
        updateSpeaking(taskId, {
          audio_url: url,
          duration_seconds: durationSeconds,
          file_name: `recording-${taskId}.webm`
        })
        stream.getTracks().forEach((track) => track.stop())
        setRecorderState((previous) => {
          const next = { ...previous }
          delete next[taskId]
          return next
        })
        const recognition = recognitionStateRef.current[taskId]
        if (recognition) {
          try {
            recognition.stop()
          } catch {}
          delete recognitionStateRef.current[taskId]
        }
        setRecordingTaskId(null)
      }

      recorder.start()
      setRecorderState((previous) => ({ ...previous, [taskId]: recorder }))
      setRecordingTaskId(taskId)

      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition()
        recognition.continuous = true
        recognition.interimResults = true
        recognition.lang = 'en-US'
        recognition.onresult = (event) => {
          let transcript = ''
          for (let index = 0; index < event.results.length; index += 1) {
            transcript += `${event.results[index][0]?.transcript || ''} `
          }
          updateSpeaking(taskId, { transcript: transcript.trim() })
        }
        recognition.onerror = () => {}
        recognition.onend = () => {
          if (recognitionStateRef.current[taskId] === recognition) {
            delete recognitionStateRef.current[taskId]
          }
        }
        recognitionStateRef.current[taskId] = recognition
        try {
          recognition.start()
        } catch {}
      }
    } catch (requestError) {
      setRecordingError(String(requestError?.message || 'Microphone access failed.'))
    }
  }

  function stopRecording(taskId) {
    const recorder = recorderState[taskId]
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    const recognition = recognitionStateRef.current[taskId]
    if (recognition) {
      try {
        recognition.stop()
      } catch {}
    }
  }

  async function submit(auto = false) {
    setSubmitting(true)
    setError('')
    try {
      const response = await api(`/api/candidate/${candidateId}/sections/${sectionId}/submit-verbal`, {
        method: 'POST',
        body: JSON.stringify({
          listening_answers: listeningAnswers,
          listening_question_index_by_block: listeningQuestionIndexByBlock,
          speaking_responses: speakingResponses,
          writing_responses: writingResponses,
          drag_drop_answers: dragDropAnswers
        })
      })
      if (response.all_completed) {
        navigate(
          auto ? `/candidate/${candidateId}/completed` : `/candidate/${candidateId}/review`,
          auto ? { replace: true, state: { terminated: true } } : { replace: true }
        )
      } else {
        navigate(`/candidate/${candidateId}/sections/${encodeURIComponent(response.next_section_id)}/instructions`, { replace: true })
      }
    } catch (requestError) {
      setError(String(requestError?.message || 'Unable to submit verbal section.'))
      setSubmitting(false)
    }
  }

  function handleNext(autoAdvance = false) {
    const active = questionItems[Math.max(0, Math.min(currentIndex, Math.max(0, questionItems.length - 1)))]
    if (active?.type === 'listening' && Array.isArray(active.questions) && active.questions.length > 1) {
      const currentQuestionIndex = listeningQuestionIndexByBlock[active.block.id] || 0
      if (currentQuestionIndex < active.questions.length - 1) {
        setListeningQuestionIndexByBlock((previous) => ({
          ...previous,
          [active.block.id]: currentQuestionIndex + 1
        }))
        return
      }
    }
    if (currentIndex >= questionItems.length - 1) {
      submit(autoAdvance)
      return
    }
    setCurrentIndex((value) => Math.min(value + 1, Math.max(0, questionItems.length - 1)))
  }

  if (!data) return <LoadingPulse fullPage />

  const clampedIndex = Math.max(0, Math.min(currentIndex, Math.max(0, questionItems.length - 1)))
  const activeItem = questionItems[clampedIndex]
  const activeListeningQuestionIndex = activeItem?.type === 'listening'
    ? Math.max(0, Math.min(listeningQuestionIndexByBlock[activeItem.block.id] || 0, Math.max(0, (activeItem.questions || []).length - 1)))
    : 0
  const listeningBlockIsLastQuestion = activeItem?.type === 'listening'
    ? activeListeningQuestionIndex >= Math.max(0, (activeItem.questions || []).length - 1)
    : true
  const isLast = clampedIndex >= questionItems.length - 1
  const nextButtonIsSubmit = isLast && listeningBlockIsLastQuestion

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

  return (
    <main className="secure-exam-shell">
      <header className="exam-header" style={{ paddingInline: 24, paddingBlock: 12 }}>
        <div className="exam-header__title" style={{ fontWeight: 700 }}>{data.section.title}</div>
        <div className="exam-header__meta" style={{ fontSize: 14 }}>
          <span className="network-indicator">
            <span className={security.networkState.barClass}>
              {security.networkState.bars.map((active, index) => (
                <span key={index} className={`network-signal__bar${active ? ' network-signal__bar--active' : ''}`} />
              ))}
            </span>
          </span>
          {!security.fullscreenActive ? (
            <button type="button" onClick={security.requestFullscreen} style={{ ...ghostButtonStyle, padding: '8px 14px' }}>
              Resume Fullscreen
            </button>
          ) : null}
          <span>{data.candidate.full_name}</span>
        </div>
      </header>

      <section className="mcq-shell">
        <div className={`mcq-stage verbal-stage${shouldBlur ? ' verbal-stage--blurred' : ''}`} style={{ position: 'relative' }}>
          {shouldBlur ? <BlurOverlay reason={blurReason} /> : null}

          <div style={{ width: '100%', maxWidth: 1240, margin: '0 auto', padding: 16, display: 'grid', gap: 16 }}>
            {error ? (
              <div style={{ borderRadius: 14, border: '1px solid #f1c8c3', background: '#ffebe9', padding: '12px 16px', color: '#ba1a1a' }}>
                {error}
              </div>
            ) : null}

            {activeItem ? (
              <section
                key={activeItem.id}
                className="mcq-card question-transition"
              >
                <div className="question-meta-row">
                  <QuestionMeta sectionLabel={activeItem.sectionLabel} currentIndex={clampedIndex} total={questionItems.length} />
                </div>

                {(activeItem.type === 'listening' || activeItem.type === 'listening_text') ? (
                  <ListeningQuestion
                    item={{ ...activeItem, activeQuestionIndex: activeListeningQuestionIndex }}
                    answers={listeningAnswers}
                    onAnswer={handleListeningAnswer}
                  />
                ) : null}

                {activeItem.type === 'speaking' ? (
                  <SpeakingQuestion
                    item={activeItem}
                    responses={speakingResponses}
                    recordingTaskId={recordingTaskId}
                    recordingError={recordingError}
                    onStartRecording={startRecording}
                    onStopRecording={stopRecording}
                  />
                ) : null}

                {activeItem.type === 'writing' ? (
                  <WritingQuestion item={activeItem} responses={writingResponses} onUpdate={updateWriting} />
                ) : null}

                {activeItem.type === 'drag_drop' ? (
                  <DragDropQuestion
                    item={activeItem}
                    answers={dragDropAnswers}
                    draggingToken={draggingToken}
                    onFill={fillDragDrop}
                    onClear={clearDragDrop}
                    onRemoveToken={removeDragToken}
                    onDragStart={setDraggingToken}
                    onDragEnd={() => setDraggingToken(null)}
                  />
                ) : null}

                <div className="exam-footer-actions">
                  <button
                    type="button"
                    disabled={submitting || shouldBlur}
                    onClick={nextButtonIsSubmit ? () => submit(false) : () => handleNext(false)}
                    style={{ ...primaryButtonStyle, opacity: submitting || shouldBlur ? 0.5 : 1 }}
                  >
                    {submitting ? 'Submitting...' : nextButtonIsSubmit ? 'Submit Section' : 'Next'}
                  </button>
                </div>
              </section>
            ) : null}
          </div>
        </div>
      </section>

      <CameraPanel candidateId={candidateId} onProctorUpdate={setProctor} />
      <Toast open={Boolean(toastMsg)} message={toastMsg} />
    </main>
  )
}
