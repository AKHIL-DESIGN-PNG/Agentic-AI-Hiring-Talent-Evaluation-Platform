import { useEffect, useMemo, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import CameraPanel from '../components/CameraPanel'
import LoadingPulse from '../components/LoadingPulse'
import Modal from '../components/Modal'
import Toast from '../components/Toast'
import useExamSecurity from '../hooks/useExamSecurity'
import useMinimumDelay from '../hooks/useMinimumDelay'

const SECTION_TIME_SECONDS = 60 * 60

const LANGUAGE_OPTIONS = [
  { value: 'java', label: 'Java', editor: 'java' },
  { value: 'python', label: 'Python', editor: 'python' },
  { value: 'cpp', label: 'C++', editor: 'cpp' },
  { value: 'javascript', label: 'JavaScript', editor: 'javascript' },
  { value: 'typescript', label: 'TypeScript', editor: 'typescript' },
  { value: 'c', label: 'C', editor: 'c' },
  { value: 'csharp', label: 'C#', editor: 'csharp' },
  { value: 'go', label: 'Go', editor: 'go' }
]

function formatClock(remaining) {
  const m = Math.floor(remaining / 60)
  const s = remaining % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function starterCodeFor(problem, language) {
  return problem?.starter_code_by_language?.[language] || problem?.starter_code || ''
}

function normalizeProblemState(problem) {
  const supported = Array.isArray(problem?.supported_languages) && problem.supported_languages.length
    ? problem.supported_languages
    : ['java']
  const language = supported[0]
  const languageDrafts = Object.fromEntries(
    supported.map((item) => [item, starterCodeFor(problem, item)])
  )
  return {
    language,
    code: languageDrafts[language] || '',
    languageDrafts,
    testcases: Array.isArray(problem?.testcases) ? problem.testcases : [],
    active_case: 0,
    active_tab: 'testcase',
    result: null
  }
}

export default function CodingExamPage() {
  const { candidateId, sectionId } = useParams()
  const navigate = useNavigate()
  const localKey = `coding-progress:${candidateId}:${sectionId}`
  const activeViolationRef = useRef(null)
  const [data, setData] = useState(null)
  const [problemStates, setProblemStates] = useState([])
  const [activeProblem, setActiveProblem] = useState(0)
  const [sectionRemaining, setSectionRemaining] = useState(SECTION_TIME_SECONDS)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
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
  const ready = useMinimumDelay(Boolean(data))

  const security = useExamSecurity({
    candidateId,
    sectionId,
    enabled: Boolean(data),
    onViolationLimit: () => submitCode(true)
  })

  const problems = useMemo(() => {
    const incoming = data?.prompt?.problems
    return Array.isArray(incoming) ? incoming : (data?.prompt ? [data.prompt] : [])
  }, [data])

  const currentProblem = problems[Math.max(0, Math.min(activeProblem, Math.max(0, problems.length - 1)))]
  const currentState = problemStates[activeProblem] || normalizeProblemState(currentProblem)
  const availableLanguages = useMemo(() => {
    const supported = currentProblem?.supported_languages
    if (!Array.isArray(supported) || supported.length === 0) return LANGUAGE_OPTIONS
    return LANGUAGE_OPTIONS.filter((item) => supported.includes(item.value))
  }, [currentProblem])
  const runtimeInfo = data?.runtime_availability?.[currentState.language]
  const safeActiveCase = Math.max(0, Math.min(currentState.active_case || 0, Math.max(0, (currentState.testcases || []).length - 1)))
  const currentCase = currentState.testcases?.[safeActiveCase]
  const editorLanguage = availableLanguages.find((item) => item.value === currentState.language)?.editor || 'java'
  const isLastFiveSeconds = sectionRemaining <= 5

  useEffect(() => {
    async function load() {
      const info = await api(`/api/candidate/${candidateId}/sections/${sectionId}/exam`)
      const localSaved = JSON.parse(localStorage.getItem(localKey) || '{}')
      const savedState = info.saved_state || {}
      const sourceProblems = Array.isArray(info.prompt?.problems) ? info.prompt.problems : [info.prompt]
      const baseStates = sourceProblems.map((problem) => normalizeProblemState(problem))
      const mergedStates = baseStates.map((item, index) => {
        const incoming = localSaved.problem_states?.[index] || savedState.problem_states?.[index] || {}
        return {
          ...item,
          ...incoming,
          language: incoming.language || item.language,
          languageDrafts: {
            ...(item.languageDrafts || {}),
            ...(incoming.languageDrafts || {})
          },
          code: (incoming.languageDrafts || item.languageDrafts || {})[incoming.language || item.language] || incoming.code || item.code,
          testcases: Array.isArray(incoming.testcases) && incoming.testcases.length ? incoming.testcases : item.testcases
        }
      })

      setData(info)
      setProblemStates(mergedStates)
      setActiveProblem(Number.isInteger(localSaved.active_problem) ? localSaved.active_problem : (savedState.active_problem || 0))
      setSectionRemaining(SECTION_TIME_SECONDS)
    }

    load().catch((error) => {
      console.error('coding_exam_load_failed', error)
      navigate(`/candidate/${candidateId}/dashboard`, { replace: true })
    })
  }, [candidateId, sectionId, navigate, localKey])

  useEffect(() => {
    if (!data || data.generated_count >= data.expected_count) return undefined
    const id = window.setInterval(async () => {
      try {
        const info = await api(`/api/candidate/${candidateId}/sections/${sectionId}/exam`)
        const sourceProblems = Array.isArray(info.prompt?.problems) ? info.prompt.problems : [info.prompt].filter(Boolean)
        setData((current) => current ? { ...current, ...info } : info)
        setProblemStates((current) => {
          if (sourceProblems.length <= current.length) return current
          return [
            ...current,
            ...sourceProblems.slice(current.length).map((problem) => normalizeProblemState(problem))
          ]
        })
      } catch (error) {
        console.error('coding_exam_poll_failed', error)
      }
    }, 3000)
    return () => window.clearInterval(id)
  }, [data, candidateId, sectionId])

  useEffect(() => {
    if (!data || isSubmitting) return undefined
    const timer = setInterval(() => {
      setSectionRemaining((value) => {
        if (value <= 1) {
          window.setTimeout(() => submitCode(true, 'timeout'), 0)
          return 0
        }
        return value - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [data, isSubmitting])

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
    if (!data) return undefined
    const autosave = async () => {
      const payload = { problem_states: problemStates, active_problem: activeProblem }
      localStorage.setItem(localKey, JSON.stringify(payload))
      if (!navigator.onLine) return
      try {
        await api(`/api/candidate/${candidateId}/sections/${sectionId}/save-coding`, {
          method: 'POST',
          body: JSON.stringify(payload)
        })
      } catch (error) {
        console.error('coding_autosave_failed', error)
      }
    }

    const id = setInterval(autosave, 4000)
    return () => clearInterval(id)
  }, [activeProblem, candidateId, data, localKey, problemStates, sectionId])

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
    setToast(next.message)
  }, [data, proctor.mobileDetected, proctor.multipleFaces, proctor.faces, security])

  function updateCurrentState(updater) {
    setProblemStates((items) => items.map((item, index) => (index === activeProblem ? updater(item) : item)))
  }

  function changeLanguage(nextLanguage) {
    updateCurrentState((current) => ({
      ...current,
      languageDrafts: {
        ...(current.languageDrafts || {}),
        [current.language]: current.code,
        [nextLanguage]: (current.languageDrafts || {})[nextLanguage] || starterCodeFor(currentProblem, nextLanguage)
      },
      language: nextLanguage,
      result: null,
      code: (current.languageDrafts || {})[nextLanguage] || starterCodeFor(currentProblem, nextLanguage)
    }))
  }

  function updateCase(value) {
    updateCurrentState((current) => ({
      ...current,
      testcases: (current.testcases || []).map((item, index) => (
        index === safeActiveCase ? { ...item, input: value, output: '' } : item
      ))
    }))
  }

  function addCase() {
    updateCurrentState((current) => {
      const nextItems = [
        ...(current.testcases || []),
        {
          label: `Case ${(current.testcases || []).length + 1}`,
          input_label: currentCase?.input_label || 'input',
          input: '""',
          output: ''
        }
      ]
      return { ...current, testcases: nextItems, active_case: nextItems.length - 1, result: null }
    })
  }

  async function runCode() {
    if (isRunning) return
    setIsRunning(true)
    try {
      const result = await api(`/api/candidate/${candidateId}/sections/${sectionId}/run-coding`, {
        method: 'POST',
        body: JSON.stringify({
          problem_index: activeProblem,
          code: currentState.code,
          language: currentState.language,
          testcases: currentState.testcases
        })
      })
      updateCurrentState((current) => ({
        ...current,
        active_tab: 'result',
        result: {
          passed: result.summary.passed,
          total: result.summary.total,
          hiddenSummary: result.hidden_summary || null,
          cases: result.cases,
          error: result.summary.error
        },
        testcases: (current.testcases || []).map((item, index) => ({
          ...item,
          output: result.cases?.[index]?.expected || item.output || ''
        }))
      }))
    } catch (error) {
      console.error('coding_run_failed', error)
      updateCurrentState((current) => ({
        ...current,
        active_tab: 'result',
        result: { passed: 0, total: current.testcases?.length || 0, hiddenSummary: null, cases: [], error: error.message }
      }))
    } finally {
      setIsRunning(false)
    }
  }

  async function submitCode(auto = false, reason = 'timeout') {
    if (isSubmitting) return
    setIsSubmitting(true)
    try {
      const result = await api(`/api/candidate/${candidateId}/sections/${sectionId}/submit-coding`, {
        method: 'POST',
        body: JSON.stringify({ problem_states: problemStates })
      })
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
      console.error('coding_submit_failed', error)
      if (!auto) {
        security.raiseWarning('Unable to submit right now. Your latest code remains saved.', {
          increment: false,
          event: 'submit_failed'
        })
      }
      setIsSubmitting(false)
    }
  }

  function advanceProblem(autoAdvance = false) {
    if (activeProblem >= problems.length - 1) {
      if (data?.generated_count < data?.expected_count || data?.generation_status === 'generating') {
        setToast('Waiting for the next generated coding problem.')
        return
      }
      submitCode(autoAdvance, 'timeout')
      return
    }
    setActiveProblem((value) => Math.min(value + 1, problems.length - 1))
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

  if (!data || !ready || !currentProblem) {
    return <LoadingPulse fullPage />
  }

  const complexityTime = currentProblem.time_complexity || 'Not specified'
  const complexitySpace = currentProblem.space_complexity || 'Not specified'

  return (
    <main className="secure-exam-shell">
      <header className="exam-header">
        <div>
          <div className="exam-header__title">{data.section.title || 'Coding Section'}</div>
        </div>
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

      <section className={`coding-shell ${shouldBlur ? 'coding-shell--blurred' : ''}`}>
        <aside className="problem-panel">
          <div className="problem-panel__inner">
            <div className="question-meta-row">
              <p className="eyebrow">Coding Problem</p>
              <span className={`question-timer ${isLastFiveSeconds ? 'question-timer--danger' : 'question-timer--safe'}`}>
                {formatClock(sectionRemaining)}
              </span>
            </div>
            <div className="problem-title-row">
              <h1>{currentProblem.title}</h1>
            </div>
            <div className="problem-copy">
              <section className="problem-detail-card">
                <h3>Problem Statement</h3>
                <p className="problem-description">{currentProblem.statement || currentProblem.description}</p>
              </section>
              {currentProblem.constraints ? (
                <section className="problem-detail-card">
                  <h3>Constraints</h3>
                  <pre className="problem-detail-pre">{currentProblem.constraints}</pre>
                </section>
              ) : null}
              {(currentProblem.sample_input || currentProblem.sample_output) ? (
                <section className="problem-detail-card problem-detail-card--split">
                  <div>
                    <h3>Sample Input</h3>
                    <pre className="problem-detail-pre">{currentProblem.sample_input || 'Not specified'}</pre>
                  </div>
                  <div>
                    <h3>Sample Output</h3>
                    <pre className="problem-detail-pre">{currentProblem.sample_output || 'Not specified'}</pre>
                  </div>
                </section>
              ) : null}
            </div>
            {(currentProblem.examples || []).map((example) => (
              <section key={example.title} className="example-card">
                <h3>{example.title}</h3>
                <p><strong>Input:</strong> {example.input}</p>
                <p><strong>Output:</strong> {example.output}</p>
                <p><strong>Explanation:</strong> {example.explanation}</p>
              </section>
            ))}
          </div>
        </aside>

        <section className={`coding-stage ${shouldBlur ? 'coding-stage--blurred' : ''}`}>
          {shouldBlur && (
            <div className="security-overlay">
              <h3>Assessment Locked</h3>
              <p>{blurReason}</p>
            </div>
          )}
          <div className="editor-panel">
            <div className="editor-toolbar editor-toolbar--split">
              <div className="editor-toolbar__left">
                <select value={currentState.language} onChange={(event) => changeLanguage(event.target.value)} className="language-select">
                  {availableLanguages.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}{data.runtime_availability?.[item.value]?.available === false ? ' (Unavailable)' : ''}
                    </option>
                  ))}
                </select>
                {runtimeInfo?.available === false ? (
                  <span className="coding-runtime-note">Default code is available for this language, but running is disabled on this server.</span>
                ) : null}
              </div>
              <div className="editor-actions">
                <button className="ghost-btn" type="button" onClick={runCode} disabled={isRunning || security.securityLocked || shouldBlur || runtimeInfo?.available === false}>
                  {isRunning ? 'Running...' : 'Run Code'}
                </button>
                <button className="primary" type="button" onClick={() => advanceProblem(false)} disabled={isSubmitting || security.securityLocked || shouldBlur}>
                  {activeProblem === problems.length - 1
                    ? (data?.generated_count < data?.expected_count || data?.generation_status === 'generating'
                        ? 'Waiting for Next Batch'
                        : (isSubmitting ? 'Submitting...' : 'Submit Section'))
                    : 'Submit Problem'}
                </button>
              </div>
            </div>
            <div className="editor-frame">
              <Editor
                height="100%"
                defaultLanguage="java"
                language={editorLanguage}
                theme="vs-dark"
                value={currentState.code}
                onChange={(value) => updateCurrentState((current) => ({
                  ...current,
                  code: value || '',
                  languageDrafts: {
                    ...(current.languageDrafts || {}),
                    [current.language]: value || ''
                  }
                }))}
                options={{
                  minimap: { enabled: false },
                  fontSize: 15,
                  lineNumbers: 'on',
                  automaticLayout: true,
                  autoClosingBrackets: 'always',
                  autoIndent: 'advanced',
                  scrollBeyondLastLine: false,
                  padding: { top: 16 }
                }}
              />
            </div>
          </div>

          <div className="testcase-panel">
            <div className="testcase-tabs">
              <button className={currentState.active_tab === 'testcase' ? 'tab-btn active' : 'tab-btn'} type="button" onClick={() => updateCurrentState((current) => ({ ...current, active_tab: 'testcase' }))}>
                Testcase
              </button>
              <button className={currentState.active_tab === 'result' ? 'tab-btn active' : 'tab-btn'} type="button" onClick={() => updateCurrentState((current) => ({ ...current, active_tab: 'result' }))}>
                Test Result
              </button>
            </div>

            <div className="testcase-panel__body">
              {currentState.active_tab === 'testcase' ? (
                <>
                  <div className="case-tabs">
                    {(currentState.testcases || []).map((item, index) => (
                      <button key={item.label || index} type="button" className={safeActiveCase === index ? 'case-chip active' : 'case-chip'} onClick={() => updateCurrentState((current) => ({ ...current, active_case: index }))}>
                        {item.label || `Case ${index + 1}`}
                      </button>
                    ))}
                    <button type="button" className="case-chip case-chip--add" onClick={addCase}>+</button>
                  </div>
                  {currentCase && (
                    <div className="case-editor">
                      <label>{currentCase.input_label || 'input'} =</label>
                      <textarea value={currentCase.input} onChange={(event) => updateCase(event.target.value)} />
                    </div>
                  )}
                </>
              ) : currentState.result ? (
                <div className="result-panel">
                  <div className="result-summary">Passed {currentState.result.passed}/{currentState.result.total}</div>
                  {currentState.result.hiddenSummary?.total ? (
                    <div className="result-summary">
                      Hidden tests: {currentState.result.hiddenSummary.passed}/{currentState.result.hiddenSummary.total}
                    </div>
                  ) : null}
                  {currentState.result.error && <p className="error">{currentState.result.error}</p>}
                  {(currentState.result.cases || []).map((item) => (
                    <article key={item.label} className={`result-case result-case--${item.status}`}>
                      <div className="result-case__head">
                        <strong>{item.label}</strong>
                        <span className={`result-status result-status--${item.status}`}>{item.status}</span>
                      </div>
                      <p><strong>Output:</strong> {item.output}</p>
                      <p><strong>Execution time:</strong> {item.execution_time}</p>
                      <p><strong>Memory usage:</strong> {item.memory_usage}</p>
                      <p><strong>Time Complexity:</strong> {complexityTime}</p>
                      <p><strong>Space Complexity:</strong> {complexitySpace}</p>
                      <p><strong>Error logs:</strong> {item.error || 'None'}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-result">Run code to view output, execution time, memory usage, time complexity, space complexity, and error logs.</div>
              )}
            </div>
          </div>
        </section>
      </section>

      <CameraPanel candidateId={candidateId} onProctorUpdate={setProctor} />
      <Toast open={Boolean(toast)} message={toast} />

      <Modal open={Boolean(nextPrompt)} title="Next Section" onClose={() => setNextPrompt(null)} disableBackdropClose hideCloseButton>
        <div className="stack modal-body">
          <p>Move to next section {nextPrompt?.sectionName}?</p>
          <div className="actions-row">
            <button className="ghost-btn" type="button" onClick={() => navigate(`/candidate/${candidateId}/review`, { replace: true })}>No</button>
            <button className="primary" type="button" onClick={() => navigate(`/candidate/${candidateId}/sections/${encodeURIComponent(nextPrompt.sectionId)}/instructions`, { replace: true })}>Yes</button>
          </div>
        </div>
      </Modal>
    </main>
  )
}
