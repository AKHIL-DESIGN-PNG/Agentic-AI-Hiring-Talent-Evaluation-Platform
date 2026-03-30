import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import LoadingPulse from '../components/LoadingPulse'
import LoadingOverlay from '../components/LoadingOverlay'
import Modal from '../components/Modal'
import Toast from '../components/Toast'
import TopNav from '../components/TopNav'
import useMinimumDelay from '../hooks/useMinimumDelay'

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1 6h2v8h-2V9Zm4 0h2v8h-2V9ZM7 9h2v8H7V9Zm-1 11V8h12v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2Z" fill="currentColor" />
    </svg>
  )
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24">
      <path d="M9 9h10v12H9V9Zm-4-6h10v2H7v10H5V3Zm2 4h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z" fill="currentColor" />
    </svg>
  )
}

function formatInterviewStatus(interview) {
  return interview?.status || 'Invited'
}

function defaultScheduleDateTime() {
  const now = new Date(Date.now() + 60 * 60 * 1000)
  const yyyy = now.getFullYear()
  const mm = String(now.getMonth() + 1).padStart(2, '0')
  const dd = String(now.getDate()).padStart(2, '0')
  const hh = String(now.getHours()).padStart(2, '0')
  const min = String(now.getMinutes()).padStart(2, '0')
  return { date: `${yyyy}-${mm}-${dd}`, time: `${hh}:${min}` }
}

const getDecision = (text) => {
  if (!text) return 'Pending'
  if (text.includes('Selected')) return 'Selected'
  if (text.includes('Rejected')) return 'Rejected'
  if (text.includes('Strong fit')) return 'Strong Fit'
  if (text.includes('Moderate fit')) return 'Moderate Fit'
  if (text.includes('Weak fit')) return 'Weak Fit'
  if (text.includes('Not suitable')) return 'Not Suitable'
  return 'Unknown'
}

const getDecisionClass = (text) => {
  if (!text) return 'status-pill'
  if (text.includes('Selected')) return 'status-pill status-pill--completed'
  if (text.includes('Rejected')) return 'status-pill status-pill--error'
  if (text.includes('Strong fit')) return 'status-pill status-pill--completed'
  if (text.includes('Moderate fit')) return 'status-pill status-pill--pending'
  if (text.includes('Weak fit')) return 'status-pill status-pill--in_progress'
  if (text.includes('Not suitable')) return 'status-pill status-pill--error'
  return 'status-pill'
}

const getInviteExplanation = (invite) => {
  const profileStatus = invite?.profile_parser?.status
  if (profileStatus === 'failed') return 'Profile parsing failed for this candidate.'
  if (invite?.profile_parser?.explanation) return invite.profile_parser.explanation
  if (invite?.interview?.ai_summary) return invite.interview.ai_summary
  if (invite?.interview?.feedback) return invite.interview.feedback
  return 'No explanation available'
}

const getProfileCellValue = (invite, field) => {
  const status = invite?.profile_parser?.status
  if (!status || status === 'pending') return 'Pending'
  if (status === 'failed') return 'Failed'
  return invite?.profile_parser?.[field] ?? 'Pending'
}

const getInviteDecision = (invite) => {
  if (invite?.status === 'cheating') return 'Cheating'
  if (invite?.interview?.status === 'Completed' && invite?.interview?.result) {
    return getDecision(invite.interview.result)
  }
  const status = invite?.profile_parser?.status
  if (!status || status === 'pending') return 'Pending'
  if (status === 'failed') return 'Failed'
  if (invite?.profile_parser?.decision) return invite.profile_parser.decision
  return getDecision(invite?.profile_parser?.explanation)
}

const getInviteDecisionClass = (invite) => {
  if (invite?.status === 'cheating') return 'status-pill status-pill--cheating'
  if (invite?.interview?.status === 'Completed' && invite?.interview?.result) {
    return getDecisionClass(invite.interview.result)
  }
  const status = invite?.profile_parser?.status
  if (!status || status === 'pending') return 'status-pill'
  if (status === 'failed') return 'status-pill status-pill--error'
  if (invite?.profile_parser?.decision) return getDecisionClass(invite.profile_parser.decision)
  return getDecisionClass(invite?.profile_parser?.explanation)
}

function formatCheatingReason(reasonText, totalViolations) {
  const raw = String(reasonText || '').trim()
  if (!raw) {
    return {
      summary: `Violations: ${totalViolations || 0}`,
      details: []
    }
  }
  const [summaryPart, ...rest] = raw.split('. ')
  const details = rest
    .join('. ')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  return {
    summary: summaryPart.trim(),
    details
  }
}

function CheatingReasonCell({ reasonText, totalViolations }) {
  const reason = formatCheatingReason(reasonText, totalViolations)
  return (
    <div className="reason-cell">
      <strong className="reason-cell__summary">{reason.summary}</strong>
      {reason.details.length ? (
        <div className="reason-cell__details">
          {reason.details.join(' | ')}
        </div>
      ) : null}
    </div>
  )
}

const BACKEND_STACK_SKILLS = ['Java', 'Spring', 'Spring Boot', 'SQL', 'Python', 'FastAPI', 'Node.js', 'Express', 'Django', 'Flask', 'C#', 'Go']
const FRONTEND_STACK_SKILLS = ['React', 'Angular', 'Vue', 'JavaScript', 'TypeScript', 'HTML', 'CSS']
const CLOUD_STACK_SKILLS = ['Docker', 'Kubernetes', 'AWS', 'Azure', 'GCP']
const POSITIVE_SIGNAL_WORDS = ['strong', 'good', 'great', 'excellent', 'clear', 'confident', 'solid', 'well', 'knowledge', 'fit', 'proficient']
const NEGATIVE_SIGNAL_WORDS = ['weak', 'poor', 'lack', 'missing', 'concern', 'struggle', 'gap', 'limited', 'insufficient', 'risk']
const FRONTEND_MARKERS = ['react', 'angular', 'vue', 'javascript', 'typescript', 'html', 'css', 'frontend', 'ui', 'ux', 'tailwind', 'bootstrap']
const CLOUD_MARKERS = ['docker', 'kubernetes', 'aws', 'azure', 'gcp', 'cloud', 'devops', 'terraform', 'jenkins', 'ci/cd']
const BACKEND_MARKERS = ['java', 'spring', 'sql', 'api', 'rest', 'backend', 'python', 'fastapi', 'django', 'flask', 'node', 'express', 'database', 'microservice', 'service', 'c#', 'go', '.net', 'php', 'ruby']

function toNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Math.round(toNumber(value))))
}

function getAssessmentPercent(invite) {
  const total = toNumber(invite?.total_score)
  const max = toNumber(invite?.total_max_score)
  if (!max) return 0
  return clampPercent((total / max) * 100)
}

function getInterviewMetric(invite) {
  const rating = toNumber(invite?.interview?.rating)
  return rating > 0 ? `${rating}/5` : 'Pending'
}

function getCompositeAiScore(invite) {
  return toNumber(invite?.profile_parser?.ai_score).toFixed(2)
}

function getOverallScore(invite) {
  const finalScore = toNumber(invite?.profile_parser?.ai_score || invite?.profile_parser?.profile_score)
  return Math.round(finalScore)
}

function getLocation(invite) {
  return String(invite?.profile_parser?.location || '').trim()
}

function getPrimaryRole(detail) {
  return detail?.name ? `${detail.name} Candidate` : 'Candidate'
}

function getInterviewerFeedback(invite) {
  const feedback = String(invite?.interview?.feedback || '').trim()
  if (feedback) return feedback
  return 'No interviewer feedback submitted yet.'
}

function splitNarratives(text) {
  return String(text || '')
    .split(/\r?\n|(?<=[.!?])\s+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function extractExplanationLine(invite, label) {
  const explanation = getInviteExplanation(invite)
  const prefix = `${label}:`
  const line = splitNarratives(explanation).find((item) => item.startsWith(prefix))
  return line ? line.slice(prefix.length).trim() : ''
}

function classifyNarratives(text, signalWords) {
  return splitNarratives(text).filter((sentence) => {
    const lowered = sentence.toLowerCase()
    return signalWords.some((word) => lowered.includes(word))
  })
}

function dedupeNarratives(items) {
  const seen = new Set()
  return items.filter((item) => {
    const key = item.toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function dedupeSkills(skills) {
  const seen = new Set()
  return (skills || []).filter((skill) => {
    const value = String(skill || '').trim()
    if (!value) return false
    const key = value.toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function hasMarker(skill, markers) {
  const lowered = String(skill || '').toLowerCase()
  return markers.some((marker) => lowered.includes(marker))
}

function extractStrengthNarratives(invite) {
  return dedupeNarratives([
    ...classifyNarratives(extractExplanationLine(invite, 'Strengths'), POSITIVE_SIGNAL_WORDS),
    ...classifyNarratives(invite?.interview?.feedback, POSITIVE_SIGNAL_WORDS)
  ])
}

function extractConcernNarratives(invite) {
  return dedupeNarratives([
    ...classifyNarratives(extractExplanationLine(invite, 'Concerns'), NEGATIVE_SIGNAL_WORDS),
    ...classifyNarratives(invite?.interview?.feedback, NEGATIVE_SIGNAL_WORDS)
  ])
}

function buildStrengthCards(invite) {
  const matchedSkills = invite?.profile_parser?.jd_match?.must_match || []
  const candidateSkills = invite?.profile_parser?.skills || []
  const sourceSkills = matchedSkills.length
    ? [...matchedSkills].sort((left, right) => {
        if (left === 'Java') return -1
        if (right === 'Java') return 1
        return 0
      })
    : candidateSkills
  const narratives = extractStrengthNarratives(invite)
  return sourceSkills.slice(0, 2).map((skill) => ({
    title: skill,
    confidence: matchedSkills.includes(skill) ? 'High Confidence' : 'Signal',
    summary: narratives.find((item) => item.toLowerCase().includes(String(skill).toLowerCase()))
      || `Positive signal detected for ${skill} from the available profile and interview evidence.`
  }))
}

function buildConcernChips(invite) {
  return (invite?.profile_parser?.jd_match?.missing_must || []).slice(0, 4)
}

function buildGapSummary(invite) {
  const concerns = dedupeNarratives(extractConcernNarratives(invite))
  const missingSkills = buildConcernChips(invite)
  if (missingSkills.length && !concerns.some((item) => item.toLowerCase().includes('missing'))) {
    concerns.push(`Missing core stack alignment in ${missingSkills.join(', ')}.`)
  }
  const assessmentPercent = getAssessmentPercent(invite)
  if (assessmentPercent > 0 && assessmentPercent < 50 && !concerns.some((item) => item.toLowerCase().includes('assessment'))) {
    concerns.push('Assessment performance is below the preferred threshold.')
  }
  if (concerns.length) return concerns.join(' ')
  return 'No critical delivery risks were detected from the available profile and interview signals.'
}

function categoryCoverage(invite, skills) {
  const jdMust = invite?.profile_parser?.jd_match?.must_have || []
  const candidateSkills = new Set((invite?.profile_parser?.skills || []).map((skill) => String(skill).toLowerCase()))
  const relevant = jdMust.filter((skill) => skills.includes(skill))
  if (relevant.length) {
    const matched = relevant.filter((skill) => candidateSkills.has(String(skill).toLowerCase())).length
    return clampPercent((matched / relevant.length) * 100)
  }
  const owned = skills.filter((skill) => candidateSkills.has(String(skill).toLowerCase())).length
  return clampPercent((owned / skills.length) * 100)
}

function getCategorySkills(invite, skills) {
  const candidateSkills = invite?.profile_parser?.skills || []
  const candidateSet = new Set(candidateSkills.map((skill) => String(skill).toLowerCase()))
  return skills.filter((skill) => candidateSet.has(String(skill).toLowerCase()))
}

function getCandidateSkillSignals(invite) {
  const parserSkills = invite?.profile_parser?.skills || []
  const jdMatches = [
    ...(invite?.profile_parser?.jd_match?.must_match || []),
    ...(invite?.profile_parser?.jd_match?.good_match || [])
  ]
  const githubLanguages = invite?.profile_parser?.details?.github?.languages || []
  return dedupeSkills([...jdMatches, ...parserSkills, ...githubLanguages])
}

function getDynamicCategorySkills(invite, category) {
  const skills = getCandidateSkillSignals(invite)
  if (!skills.length) return []

  if (category === 'backend') {
    return skills.filter((skill) => (
      hasMarker(skill, BACKEND_MARKERS) && !hasMarker(skill, FRONTEND_MARKERS) && !hasMarker(skill, CLOUD_MARKERS)
    ))
  }

  if (category === 'frontend') {
    return skills.filter((skill) => hasMarker(skill, FRONTEND_MARKERS))
  }

  if (category === 'cloud') {
    return skills.filter((skill) => hasMarker(skill, CLOUD_MARKERS))
  }

  return []
}

function getCategoryEmptyState(category) {
  if (category === 'backend') return 'No backend skills identified'
  if (category === 'frontend') return 'No frontend skills identified'
  if (category === 'cloud') return 'No cloud or DevOps skills identified'
  return 'No skills identified'
}

export default function AssessmentDetailPage() {
  const { assessmentSlug } = useParams()
  const [detail, setDetail] = useState(null)
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [resultTarget, setResultTarget] = useState(null)
  const [scheduleTarget, setScheduleTarget] = useState(null)
  const [feedbackTarget, setFeedbackTarget] = useState(null)
  const [decisionTarget, setDecisionTarget] = useState(null)
  const [duplicateInviteTarget, setDuplicateInviteTarget] = useState(null)
  const [sendingInvite, setSendingInvite] = useState(false)
  const [file, setFile] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [scheduling, setScheduling] = useState(false)
  const [submittingFeedback, setSubmittingFeedback] = useState(false)
  const [sendingDecision, setSendingDecision] = useState(false)
  const [scheduleForm, setScheduleForm] = useState({
    date: '',
    time: '',
    interviewerEmail: '',
    duration: '30'
  })
  const [feedbackForm, setFeedbackForm] = useState({
    rating: '4',
    feedback: ''
  })
  const [selectedEcosystem, setSelectedEcosystem] = useState('backend')
  const [selectedStrength, setSelectedStrength] = useState('')
  const [minFinalScore, setMinFinalScore] = useState('0')
  const [sortMode, setSortMode] = useState('score_desc')
  const fileInputRef = useRef(null)

  const ready = useMinimumDelay(Boolean(detail))

  function syncInviteState(nextDetail) {
    const invites = Array.isArray(nextDetail?.invites) ? nextDetail.invites : []
    const findInvite = (inviteId) => invites.find((item) => item.id === inviteId) || null

    setResultTarget((current) => current ? findInvite(current.id) : current)
    setScheduleTarget((current) => current ? findInvite(current.id) : current)
    setFeedbackTarget((current) => current ? findInvite(current.id) : current)
    setDecisionTarget((current) => current ? findInvite(current.id) : current)
  }

  function getFinalScoreValue(invite) {
    if (!invite || (invite.status !== 'completed' && invite.status !== 'cheating')) return null
    if (!invite.profile_parser || invite.profile_parser.status !== 'completed') return null
    if (!invite.total_max_score) return null

    const profileScore = Number(invite.profile_parser.profile_score)
    const examScore = Number(invite.total_score)
    const examMax = Number(invite.total_max_score)

    if (!Number.isFinite(profileScore) || !Number.isFinite(examScore) || !Number.isFinite(examMax) || examMax <= 0) {
      return null
    }

    const examPercent = (examScore / examMax) * 100
    return (0.5 * profileScore) + (0.5 * examPercent)
  }

  function calculateFinalScore(invite) {
    const finalScore = getFinalScoreValue(invite)
    if (finalScore === null) return 'Pending'
    return finalScore.toFixed(2)
  }

  async function load() {
    const data = await api(`/api/admin/assessments/slug/${assessmentSlug}`, {}, true)
    setDetail(data)
    syncInviteState(data)
  }

  useEffect(() => {
    load().catch((requestError) => setError(requestError?.message || 'Unable to load assessment details.'))
  }, [assessmentSlug])

  useEffect(() => {
    let cancelled = false

    async function poll() {
      if (document.hidden) return
      try {
        const data = await api(`/api/admin/assessments/slug/${assessmentSlug}`, {}, true)
        if (cancelled) return
        setDetail((current) => {
          if (!current) return data
          return data
        })
        syncInviteState(data)
      } catch (requestError) {
        if (!cancelled) {
          console.error('assessment_detail_poll_failed', requestError)
        }
      }
    }

    const intervalId = setInterval(poll, 4000)
    return () => {
      cancelled = true
      clearInterval(intervalId)
    }
  }, [assessmentSlug])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(''), 2500)
    return () => clearTimeout(timer)
  }, [toast])

  function findDuplicateInviteByEmail(nextEmail) {
    const normalized = String(nextEmail || '').trim().toLowerCase()
    if (!normalized || !Array.isArray(detail?.invites)) return null
    return detail.invites.find((invite) => String(invite.email || '').trim().toLowerCase() === normalized) || null
  }

  async function sendInviteRequest() {
    setError('')
    setSendingInvite(true)
    try {
      await api(
        `/api/admin/assessments/${detail.id}/invite`,
        {
          method: 'POST',
          body: JSON.stringify({ full_name: name, email })
        },
        true
      )
      setToast('Email sent')
      setName('')
      setEmail('')
      setOpen(false)
      setDuplicateInviteTarget(null)
      load()
    } catch (requestError) {
      setError(requestError?.message || 'Unable to send invite.')
    }
    setSendingInvite(false)
  }

  async function invite(event) {
    event.preventDefault()
    const duplicateInvite = findDuplicateInviteByEmail(email)
    if (duplicateInvite && !duplicateInviteTarget) {
      setDuplicateInviteTarget(duplicateInvite)
      return
    }
    await sendInviteRequest()
  }

  async function uploadBulk() {
    if (!file) {
      setToast('Please select a file')
      return
    }
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      await api(
        `/api/admin/assessments/${detail.id}/bulk-invite`,
        {
          method: 'POST',
          body: formData
        },
        true
      )
      setToast('Email sent to Candidates successfully')
      setFile(null)
      setOpen(false)
      load()
    } catch (requestError) {
      console.error(requestError)
      setError('Bulk upload failed')
    }
    setUploading(false)
  }

  function handleFileSelection(nextFile) {
    if (!nextFile) return
    setFile(nextFile)
    setError('')
  }

  function handleDrop(event) {
    event.preventDefault()
    event.stopPropagation()
    setDragActive(false)
    handleFileSelection(event.dataTransfer.files?.[0] || null)
  }

  async function copyLink(link) {
    await navigator.clipboard.writeText(link)
    setToast('Link copied')
  }

  async function deleteInvite() {
    if (!deleteTarget) return
    await api(
      `/api/admin/assessments/${detail.id}/invites/${deleteTarget.id}`,
      { method: 'DELETE' },
      true
    )
    setDeleteTarget(null)
    setToast('Candidate deleted')
    load()
  }

  function openCandidateResult(invite) {
    if (invite.status !== 'completed' && invite.status !== 'cheating') {
      setToast('Candidate has not completed the assessment')
      return
    }
    setSelectedEcosystem('')
    setSelectedStrength('')
    setResultTarget(invite)
  }

  function openScheduleModal(invite) {
    const defaults = defaultScheduleDateTime()
    setScheduleTarget(invite)
    setScheduleForm({
      date: defaults.date,
      time: defaults.time,
      interviewerEmail: invite.interview?.interviewer_email || '',
      duration: String(invite.interview?.duration || 30)
    })
  }

  async function scheduleInterview(event) {
    event.preventDefault()
    if (!scheduleTarget) return
    setScheduling(true)
    setError('')
    try {
      await api(
        '/api/schedule-interview',
        {
          method: 'POST',
          body: JSON.stringify({
            assessment_id: detail.id,
            invite_id: scheduleTarget.id,
            candidate_name: scheduleTarget.full_name,
            candidate_email: scheduleTarget.email,
            interviewer_email: scheduleForm.interviewerEmail,
            interview_datetime: `${scheduleForm.date}T${scheduleForm.time}`,
            duration: Number(scheduleForm.duration)
          })
        },
        true
      )
      setScheduleTarget(null)
      setToast('Interview scheduled')
      await load()
    } catch (requestError) {
      setError(requestError.message || 'Unable to schedule interview.')
    } finally {
      setScheduling(false)
    }
  }

  function openFeedbackModal(invite) {
    setFeedbackTarget(invite)
    setFeedbackForm({
      rating: String(invite.interview?.rating || 4),
      feedback: invite.interview?.feedback || ''
    })
  }

  function openDecisionModal(invite) {
    if (!invite?.interview) return
    setDecisionTarget(invite)
  }

  async function submitFeedback(event) {
    event.preventDefault()
    if (!feedbackTarget?.interview) return
    setSubmittingFeedback(true)
    setError('')
    try {
      await api(
        '/api/submit-feedback',
        {
          method: 'POST',
          body: JSON.stringify({
            interview_id: feedbackTarget.interview.id,
            invite_id: feedbackTarget.id,
            candidate_email: feedbackTarget.email,
            rating: Number(feedbackForm.rating),
            feedback: feedbackForm.feedback
          })
        },
        true
      )
      setFeedbackTarget(null)
      setToast('Feedback submitted')
      await load()
    } catch (requestError) {
      setError(requestError.message || 'Unable to submit feedback.')
    } finally {
      setSubmittingFeedback(false)
    }
  }

  async function sendDecision(decision) {
    if (!decisionTarget?.interview) return
    setSendingDecision(true)
    setError('')
    try {
      await api(
        '/api/send-interview-decision',
        {
          method: 'POST',
          body: JSON.stringify({
            interview_id: decisionTarget.interview.id,
            invite_id: decisionTarget.id,
            candidate_email: decisionTarget.email,
            decision
          })
        },
        true
      )
      await load()
      setDecisionTarget(null)
      setToast(`Successfully sent a mail||${Date.now()}`)
    } catch (requestError) {
      const message = requestError.message || `Unable to send ${decision.toLowerCase()} email.`
      setError(message)
      setToast(`${message}||${Date.now()}`)
    } finally {
      setSendingDecision(false)
    }
  }

  function joinInterview(interview, event) {
    event.stopPropagation()
    if (!interview?.join_link) return
    window.open(interview.join_link, '_blank', 'noopener,noreferrer')
  }

  function toggleEcosystem(category) {
    setSelectedEcosystem((current) => current === category ? '' : category)
  }

  if (!detail || !ready) {
    return (
      <div>
        <TopNav />
        <LoadingPulse fullPage />
      </div>
    )
  }

  const minScoreNumber = Number(minFinalScore)
  const filteredInvites = [...detail.invites]
    .filter((invite) => {
      if (minScoreNumber <= 0) return true
      const finalScore = getFinalScoreValue(invite)
      return finalScore !== null && finalScore >= minScoreNumber
    })
    .sort((a, b) => {
      if (sortMode === 'recent') {
        const aDate = new Date(a.last_updated || a.created_at).getTime()
        const bDate = new Date(b.last_updated || b.created_at).getTime()
        return bDate - aDate
      }

      const aScore = getFinalScoreValue(a)
      const bScore = getFinalScoreValue(b)
      if (aScore === null && bScore === null) return 0
      if (aScore === null) return 1
      if (bScore === null) return -1
      return bScore - aScore
    })

  const evaluationLocation = getLocation(resultTarget)
  const evaluationStrengths = buildStrengthCards(resultTarget)
  const evaluationConcerns = buildConcernChips(resultTarget)
  const backendCoverage = categoryCoverage(resultTarget, BACKEND_STACK_SKILLS)
  const frontendCoverage = categoryCoverage(resultTarget, FRONTEND_STACK_SKILLS)
  const cloudCoverage = categoryCoverage(resultTarget, CLOUD_STACK_SKILLS)
  const activeStrength = selectedStrength
    ? evaluationStrengths.find((item) => item.title === selectedStrength) || null
    : null
  const ecosystemConfig = {
    backend: {
      label: 'Backend Skills',
      coverage: backendCoverage,
      skills: getDynamicCategorySkills(resultTarget, 'backend'),
      tone: 'default'
    },
    frontend: {
      label: 'Frontend Skills',
      coverage: frontendCoverage,
      skills: getDynamicCategorySkills(resultTarget, 'frontend'),
      tone: 'default'
    },
    cloud: {
      label: 'Cloud & DevOps',
      coverage: cloudCoverage,
      skills: getDynamicCategorySkills(resultTarget, 'cloud'),
      tone: 'danger'
    }
  }
  const activeEcosystem = selectedEcosystem ? ecosystemConfig[selectedEcosystem] : null

  return (
    <div>
      <TopNav />
      <Toast open={Boolean(toast)} message={toast} />

      <main className="page">
        <div className="heading-row">
          <div>
            <p className="muted">AITS &gt; Assessments</p>
            <h2>{detail.name}</h2>
            <div className="chip-row">
              {detail.sections.map(section => (
                <span key={section.id} className="pill">{section.title}</span>
              ))}
            </div>
          </div>
          <button className="primary" type="button" onClick={() => setOpen(true)}>
            Invite Candidates
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        <section className="panel">
          <h3>Invited Candidates</h3>
          <div className="score-filter-row">
            <label>
              Minimum Final Score
              <select
                value={minFinalScore}
                onChange={(event) => setMinFinalScore(event.target.value)}
              >
                <option value="0">All</option>
                <option value="50">50+</option>
                <option value="60">60+</option>
                <option value="70">70+</option>
                <option value="80">80+</option>
                <option value="90">90+</option>
              </select>
            </label>

            <label>
              Order
              <select
                value={sortMode}
                onChange={(event) => setSortMode(event.target.value)}
              >
                <option value="score_desc">Highest Score First</option>
                <option value="recent">Recently Updated</option>
              </select>
            </label>
          </div>
          <div className="table-container">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>GitHub</th>
                  <th>LeetCode</th>
                  <th>Resume</th>
                  <th>Profile Score</th>
                  <th>Last Updated</th>
                  <th>Status</th>
                  <th className="reason-col">Reason</th>
                  <th>Exam Score</th>
                  <th>Final Score</th>
                  <th>AI Decision</th>
                  <th>Explanation</th>
                  <th>Interview</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {filteredInvites.map(invite => {
                  const interviewStatus = formatInterviewStatus(invite.interview)
                  const isCompletedInterview = interviewStatus === 'Completed'
                  const hasFinalDecision = Boolean(invite.interview?.result)

                  return (
                    <tr key={invite.id}>
                      <td>{invite.full_name}</td>
                      <td>{invite.email}</td>
                      <td>{getProfileCellValue(invite, 'github_score')}</td>
                      <td>{getProfileCellValue(invite, 'leetcode_score')}</td>
                      <td>{getProfileCellValue(invite, 'resume_score')}</td>
                      <td>{getProfileCellValue(invite, 'profile_score')}</td>
                      <td>{new Date(invite.last_updated || invite.created_at).toLocaleDateString()}</td>

                      <td>
                        <span className={`status-pill status-pill--${invite.status}`}>
                          {invite.status.replace('_', ' ')}
                        </span>
                      </td>

                      <td className="reason-col">
                        {invite.status === 'cheating'
                          ? <CheatingReasonCell reasonText={invite.status_reason} totalViolations={invite.violation_total} />
                          : '-'}
                      </td>

                      <td>
                        {invite.status === 'completed' || invite.status === 'cheating'
                          ? `${invite.total_score}/${invite.total_max_score}`
                          : 'Pending'}
                      </td>

                      <td>
                        {invite.status === 'completed' || invite.status === 'cheating'
                          ? invite.profile_parser?.status === 'failed'
                            ? 'Failed'
                            : !invite.profile_parser || invite.profile_parser.status === 'pending'
                              ? 'Pending'
                              : calculateFinalScore(invite)
                          : 'Pending'}
                      </td>

                      <td>
                        <span className={getInviteDecisionClass(invite)}>
                          {getInviteDecision(invite)}
                        </span>
                      </td>

                      <td>
                        <button
                          className="primary"
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation()
                            openCandidateResult(invite)
                          }}
                        >
                          View
                        </button>
                      </td>

                      <td>
                        <span className="status-pill">{interviewStatus}</span>
                        <div className="muted">
                          {invite.interview?.interview_datetime
                            ? new Date(invite.interview.interview_datetime).toLocaleString()
                            : 'Not scheduled'}
                        </div>
                      </td>

                      <td className="table-actions">
                        {!invite.interview && (
                          <button
                            className="ghost-btn"
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              openScheduleModal(invite)
                            }}
                          >
                            Schedule Interview
                          </button>
                        )}

                        {invite.interview && !isCompletedInterview && (
                          <button
                            className="ghost-btn"
                            type="button"
                            onClick={(event) => joinInterview(invite.interview, event)}
                          >
                            Join Interview
                          </button>
                        )}

                        {invite.interview && !isCompletedInterview && (
                          <button
                            className="ghost-btn"
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              openFeedbackModal(invite)
                            }}
                          >
                            Submit Feedback
                          </button>
                        )}

                        {invite.interview && isCompletedInterview && !hasFinalDecision && (
                          <button
                            className="primary"
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              openDecisionModal(invite)
                            }}
                          >
                            Hire
                          </button>
                        )}

                        {invite.interview && isCompletedInterview && hasFinalDecision && (
                          <span className={getDecisionClass(invite.interview.result)}>
                            {getDecision(invite.interview.result)}
                          </span>
                        )}

                        <button
                          className="icon-action"
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation()
                            copyLink(invite.link)
                          }}
                        >
                          <CopyIcon />
                        </button>

                        <button
                          className="icon-action icon-action--danger"
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation()
                            setDeleteTarget(invite)
                          }}
                        >
                          <TrashIcon />
                        </button>
                      </td>
                    </tr>
                  )
                })}

                {filteredInvites.length === 0 && (
                  <tr>
                    <td colSpan="15">No candidates match this score filter.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      <Modal open={open} title="Invite Candidate" onClose={() => setOpen(false)}>
        <form onSubmit={invite} className="stack modal-body loading-overlay-host">
          <LoadingOverlay open={sendingInvite || uploading} label={sendingInvite ? 'Sending invite...' : 'Uploading candidates...'} />
          <p>Invite single candidate</p>
          <label>Candidate full name</label>
          <input value={name} onChange={(event) => setName(event.target.value)} required />
          <label>Candidate email</label>
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          <button className="primary" type="submit" disabled={sendingInvite || uploading}>Invite Candidate</button>
          <hr />
          <p>OR upload CSV / Excel for bulk invite</p>
          <input
            ref={fileInputRef}
            className="invite-upload-input"
            type="file"
            accept=".csv,.xlsx"
            onChange={(event) => handleFileSelection(event.target.files?.[0] || null)}
          />
          <button
            type="button"
            className={`invite-upload-dropzone ${dragActive ? 'invite-upload-dropzone--active' : ''}`}
            onClick={() => fileInputRef.current?.click()}
            onDragEnter={(event) => {
              event.preventDefault()
              event.stopPropagation()
              setDragActive(true)
            }}
            onDragOver={(event) => {
              event.preventDefault()
              event.stopPropagation()
              setDragActive(true)
            }}
            onDragLeave={(event) => {
              event.preventDefault()
              event.stopPropagation()
              setDragActive(false)
            }}
            onDrop={handleDrop}
          >
            <strong>Drag and drop CSV/XLSX here</strong>
            <span>or click to browse from your device</span>
            {file ? <small className="invite-upload-filename">Selected file: {file.name}</small> : null}
          </button>
          <button type="button" className="primary" onClick={uploadBulk} disabled={sendingInvite || uploading}>Upload Candidates</button>
        </form>
      </Modal>

      <Modal
        open={Boolean(duplicateInviteTarget)}
        title="Candidate Already Invited"
        onClose={() => setDuplicateInviteTarget(null)}
      >
        <div className="stack modal-body">
          <p>
            <strong>{duplicateInviteTarget?.email}</strong> already has an invite for this assessment.
            {' '}Send another invite anyway?
          </p>
          <div className="actions-row">
            <button
              className="ghost-btn"
              type="button"
              onClick={() => setDuplicateInviteTarget(null)}
              disabled={sendingInvite}
            >
              Cancel
            </button>
            <button
              className="primary"
              type="button"
              onClick={sendInviteRequest}
              disabled={sendingInvite}
            >
              {sendingInvite ? 'Sending...' : 'Send Another Invite'}
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(deleteTarget)}
        title="Delete Candidate"
        onClose={() => setDeleteTarget(null)}
      >
        <div className="stack modal-body">
          <p>Delete {deleteTarget?.full_name} permanently?</p>
          <div className="actions-row">
            <button type="button" onClick={() => setDeleteTarget(null)}>No</button>
            <button className="primary" type="button" onClick={deleteInvite}>Yes</button>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(resultTarget)}
        title="Candidate AI Evaluation"
        onClose={() => setResultTarget(null)}
        hideHeader
        className="candidate-eval-modal"
      >
        <div className="candidate-eval">
          <aside className="candidate-eval__sidebar">
            <div className="candidate-eval__sidebar-head">
              <h3>Candidate Evaluation</h3>
            </div>

            <div className="candidate-eval__profile">
              <div className="candidate-eval__avatar">
                {String(resultTarget?.full_name || '?').trim().charAt(0).toUpperCase()}
              </div>
              <h4>{resultTarget?.full_name}</h4>
              <p>{getPrimaryRole(detail)}</p>
              <div className="candidate-eval__meta">
                <span>{resultTarget?.email}</span>
                {evaluationLocation ? <span>{evaluationLocation}</span> : null}
              </div>
            </div>

            <div className="candidate-eval__summary-card">
              <div className="candidate-eval__summary-head">
                <div>
                  <p>Overall Score</p>
                  <div className="candidate-eval__summary-score">
                    <strong>{getOverallScore(resultTarget)}</strong>
                    <span>/100</span>
                  </div>
                </div>
                <span className={`candidate-eval__decision ${getInviteDecisionClass(resultTarget)}`}>
                  {getInviteDecision(resultTarget)}
                </span>
              </div>
            </div>

            <div className="candidate-eval__driver-card">
              <div className="candidate-eval__driver-head">
                <span>Interviewer Feedback</span>
              </div>
              <p className="candidate-eval__feedback-copy">{getInterviewerFeedback(resultTarget)}</p>
            </div>
          </aside>

          <section className="candidate-eval__content">
            <div className="candidate-eval__content-head">
              <div>
                <p className="candidate-eval__eyebrow">AI Performance Intelligence</p>
              </div>
              <button
                type="button"
                className="candidate-eval__close"
                onClick={() => setResultTarget(null)}
              >
                x
              </button>
            </div>

            <div className="candidate-eval__metrics">
              <article className="candidate-eval__metric-card">
                <p>JD Match</p>
                <strong>{clampPercent(resultTarget?.profile_parser?.jd_match?.must_coverage)}%</strong>
              </article>
              <article className="candidate-eval__metric-card">
                <p>Assessment</p>
                <strong>{getAssessmentPercent(resultTarget)}%</strong>
              </article>
              <article className="candidate-eval__metric-card">
                <p>Interview</p>
                <strong>{getInterviewMetric(resultTarget)}</strong>
              </article>
            </div>

            <div className="candidate-eval__ai-score">
              <div>
                <h4>Composite AI Score</h4>
                <p>Synthesized from profile fit, assessment performance, and interview signals.</p>
              </div>
              <strong>{getCompositeAiScore(resultTarget)}</strong>
            </div>

            <div className="candidate-eval__grid">
              <div className="candidate-eval__column">
                <h4 className="candidate-eval__section-title">Key Strengths</h4>
                <div className="candidate-eval__strength-list">
                  {evaluationStrengths.length ? evaluationStrengths.map((item) => (
                    <button
                      key={item.title}
                      type="button"
                      className={`candidate-eval__insight-card candidate-eval__insight-card--button ${activeStrength?.title === item.title ? 'candidate-eval__insight-card--active' : ''}`}
                      onClick={() => setSelectedStrength(item.title)}
                    >
                      <div className="candidate-eval__insight-head">
                        <span>{item.title}</span>
                        <small>{item.confidence}</small>
                      </div>
                    </button>
                  )) : (
                    <article className="candidate-eval__insight-card">
                      <div className="candidate-eval__insight-head">
                        <span>Awaiting richer signals</span>
                        <small>Pending</small>
                      </div>
                      <p>Strength highlights will appear once the profile parser and interview feedback are complete.</p>
                    </article>
                  )}
                </div>
              </div>

              <div className="candidate-eval__column">
                <h4 className="candidate-eval__section-title candidate-eval__section-title--danger">Critical Concerns</h4>
                <div className="candidate-eval__concerns">
                  {evaluationConcerns.length ? evaluationConcerns.map((item) => (
                    <span key={item} className="candidate-eval__concern-chip">Missing: {item}</span>
                  )) : (
                    <span className="candidate-eval__concern-chip candidate-eval__concern-chip--soft">No must-have gaps detected</span>
                  )}
                </div>
                <div className="candidate-eval__gap-card">
                  <strong>Performance Gap</strong>
                  <p>{buildGapSummary(resultTarget)}</p>
                </div>
              </div>
            </div>

            <div className="candidate-eval__ecosystem">
              <h4 className="candidate-eval__section-title">Technical Ecosystem Match</h4>

              <button
                type="button"
                className={`candidate-eval__bar-group candidate-eval__bar-group--button ${selectedEcosystem === 'backend' ? 'candidate-eval__bar-group--active' : ''}`}
                onClick={() => toggleEcosystem('backend')}
              >
                <div className="candidate-eval__bar-head">
                  <span>Backend Skills</span>
                  <strong>{backendCoverage}%</strong>
                </div>
                <div className="candidate-eval__bar-track">
                  <div className="candidate-eval__bar-fill" style={{ width: `${backendCoverage}%` }} />
                </div>
              </button>

              <button
                type="button"
                className={`candidate-eval__bar-group candidate-eval__bar-group--button ${selectedEcosystem === 'frontend' ? 'candidate-eval__bar-group--active' : ''}`}
                onClick={() => toggleEcosystem('frontend')}
              >
                <div className="candidate-eval__bar-head">
                  <span>Frontend Skills</span>
                  <strong>{frontendCoverage}%</strong>
                </div>
                <div className="candidate-eval__bar-track">
                  <div className="candidate-eval__bar-fill" style={{ width: `${frontendCoverage}%` }} />
                </div>
              </button>

              <button
                type="button"
                className={`candidate-eval__bar-group candidate-eval__bar-group--button ${selectedEcosystem === 'cloud' ? 'candidate-eval__bar-group--active' : ''}`}
                onClick={() => toggleEcosystem('cloud')}
              >
                <div className="candidate-eval__bar-head">
                  <span>Cloud &amp; DevOps</span>
                  <strong className="candidate-eval__bar-value--danger">{cloudCoverage}%</strong>
                </div>
                <div className="candidate-eval__bar-track">
                  <div className="candidate-eval__bar-fill candidate-eval__bar-fill--danger" style={{ width: `${cloudCoverage}%` }} />
                </div>
              </button>

            </div>
          </section>
          {activeEcosystem ? (
            <div className="candidate-eval__center-popup" onClick={() => setSelectedEcosystem('')}>
              <div className="candidate-eval__skill-popup candidate-eval__skill-popup--center" onClick={(event) => event.stopPropagation()}>
                <div className="candidate-eval__skill-panel-head">
                  <span>{activeEcosystem.label}</span>
                  <div className="candidate-eval__skill-panel-actions">
                    <strong>{activeEcosystem.coverage}% Match</strong>
                    <button
                      type="button"
                      className="candidate-eval__popup-close"
                      onClick={() => setSelectedEcosystem('')}
                      aria-label="Close skill details"
                    >
                      x
                    </button>
                  </div>
                </div>
                {activeEcosystem.skills.length ? (
                  <div className="candidate-eval__skill-chips">
                    {activeEcosystem.skills.map((skill) => (
                      <span
                        key={`${activeEcosystem.label}-${skill}`}
                        className={`candidate-eval__skill-chip ${activeEcosystem.tone === 'danger' ? 'candidate-eval__skill-chip--danger' : ''}`}
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="candidate-eval__skill-empty">{getCategoryEmptyState(selectedEcosystem)}</p>
                )}
              </div>
            </div>
          ) : null}
        </div>

      </Modal>

      <Modal
        open={Boolean(scheduleTarget)}
        title="Schedule Interview"
        onClose={() => setScheduleTarget(null)}
      >
        <form onSubmit={scheduleInterview} className="stack modal-body loading-overlay-host">
          <LoadingOverlay open={scheduling} label="Scheduling interview..." />
          <label>Candidate Name</label>
          <input value={scheduleTarget?.full_name || ''} disabled readOnly />

          <label>Candidate Email</label>
          <input value={scheduleTarget?.email || ''} disabled readOnly />

          <label>Interview Date</label>
          <input
            type="date"
            value={scheduleForm.date}
            onChange={(event) => setScheduleForm(form => ({ ...form, date: event.target.value }))}
            required
          />

          <label>Interview Time</label>
          <input
            type="time"
            value={scheduleForm.time}
            onChange={(event) => setScheduleForm(form => ({ ...form, time: event.target.value }))}
            required
          />

          <label>Interviewer Email</label>
          <input
            type="email"
            value={scheduleForm.interviewerEmail}
            onChange={(event) => setScheduleForm(form => ({ ...form, interviewerEmail: event.target.value }))}
            required
          />

          <label>Duration</label>
          <select
            value={scheduleForm.duration}
            onChange={(event) => setScheduleForm(form => ({ ...form, duration: event.target.value }))}
          >
            <option value="30">30 mins</option>
            <option value="45">45 mins</option>
            <option value="60">60 mins</option>
          </select>

          <button className="primary" type="submit" disabled={scheduling}>Schedule Interview</button>
        </form>
      </Modal>

      <Modal
        open={Boolean(feedbackTarget)}
        title="Submit Interview Feedback"
        onClose={() => setFeedbackTarget(null)}
      >
        <form onSubmit={submitFeedback} className="stack modal-body loading-overlay-host">
          <LoadingOverlay open={submittingFeedback} label="Submitting feedback..." />
          <label>Candidate</label>
          <input value={feedbackTarget?.full_name || ''} disabled readOnly />

          <label>Rating</label>
          <select
            value={feedbackForm.rating}
            onChange={(event) => setFeedbackForm(form => ({ ...form, rating: event.target.value }))}
          >
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4</option>
            <option value="5">5</option>
          </select>

          <label>Feedback</label>
          <textarea
            rows="5"
            value={feedbackForm.feedback}
            onChange={(event) => setFeedbackForm(form => ({ ...form, feedback: event.target.value }))}
            placeholder="Share your interview notes"
            required
          />

          {feedbackTarget?.interview?.ai_summary ? (
            <>
              <label>AI Summary</label>
              <div className="profile-review-card">
                <p>{feedbackTarget.interview.ai_summary}</p>
              </div>
            </>
          ) : null}

          <button className="primary" type="submit" disabled={submittingFeedback}>Submit Feedback</button>
        </form>
      </Modal>

      <Modal
        open={Boolean(decisionTarget)}
        title="Hiring Decision"
        onClose={() => setDecisionTarget(null)}
      >
        <div className="stack modal-body loading-overlay-host">
          <LoadingOverlay open={sendingDecision} label="Sending decision email..." />
          <h3>{decisionTarget?.full_name}</h3>
          <p>Choose the final interview decision to email this candidate.</p>
          <div className="actions-row actions-row--center">
            <button
              className="decision-btn decision-btn--reject"
              type="button"
              disabled={sendingDecision}
              onClick={() => sendDecision('Rejected')}
            >
              Reject
            </button>
            <button
              className="decision-btn decision-btn--select"
              type="button"
              disabled={sendingDecision}
              onClick={() => sendDecision('Selected')}
            >
              Select
            </button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
