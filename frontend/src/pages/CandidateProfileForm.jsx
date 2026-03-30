import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import CandidatePortalHeader from '../components/CandidatePortalHeader'
import LoadingOverlay from '../components/LoadingOverlay'
import LoadingPulse from '../components/LoadingPulse'
import useMinimumDelay from '../hooks/useMinimumDelay'

const githubPattern = /^https?:\/\/(www\.)?github\.com\/[^/]+\/?$/i
const googleDrivePattern = /^https?:\/\/(www\.)?(drive|docs)\.google\.com\/.+$/i

function isValidLeetCodeUrl(value) {
  try {
    const parsed = new URL(value.trim())
    if (!['http:', 'https:'].includes(parsed.protocol)) return false
    if (!['leetcode.com', 'www.leetcode.com'].includes(parsed.hostname.toLowerCase())) return false
    const parts = parsed.pathname.split('/').filter(Boolean)
    if (parts.length === 0) return false
    if (parts[0] === 'u' || parts[0] === 'profile') {
      return parts.length > 1
    }
    return parts.length === 1
  } catch {
    return false
  }
}

export default function CandidateProfileForm() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [githubUrl, setGithubUrl] = useState('')
  const [leetcodeUrl, setLeetcodeUrl] = useState('')
  const [resumePdf, setResumePdf] = useState(null)
  const [resumeDriveLink, setResumeDriveLink] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const ready = useMinimumDelay(Boolean(data))

  useEffect(() => {
    async function load() {
      const info = await api(`/api/candidate/${candidateId}/profile`)
      const [first = '', ...rest] = (info.candidate.full_name || '').trim().split(/\s+/)
      setFirstName(first)
      setLastName(rest.join(' '))
      setData(info)
    }

    load().catch((requestError) => {
      console.error('candidate_profile_load_failed', requestError)
      setError(requestError.message)
    })
  }, [candidateId])

  function setPdfResume(file) {
    setResumePdf(file)
  }

  function validate() {
    if (!firstName.trim() || !lastName.trim()) {
      return 'First name and last name are required.'
    }
    if (!githubPattern.test(githubUrl.trim())) {
      return 'Enter a valid GitHub profile URL.'
    }
    if (!isValidLeetCodeUrl(leetcodeUrl)) {
      return 'Enter a valid LeetCode profile URL.'
    }
    if (!resumePdf && !resumeDriveLink.trim()) {
      return 'Add a resume PDF or a Google Drive link.'
    }
    if (resumePdf && resumePdf.type && resumePdf.type !== 'application/pdf') {
      return 'Resume upload must be a PDF.'
    }
    if (resumeDriveLink.trim() && !googleDrivePattern.test(resumeDriveLink.trim())) {
      return 'Resume link must be a valid Google Drive URL.'
    }
    return ''
  }

  async function submit(event) {
    event.preventDefault()
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }

    setSubmitting(true)
    setError('')
    const formData = new FormData()
    formData.append('candidate_id', candidateId)
    formData.append('first_name', firstName.trim())
    formData.append('last_name', lastName.trim())
    formData.append('github_url', githubUrl.trim())
    formData.append('leetcode_url', leetcodeUrl.trim())
    if (resumePdf) {
      formData.append('resume_pdf', resumePdf)
    } else if (resumeDriveLink.trim()) {
      formData.append('resume_drive_link', resumeDriveLink.trim())
    }

    try {
      const result = await api('/candidate/profile', {
        method: 'POST',
        body: formData
      })
      if (result.next_section_id) {
        navigate(`/candidate/${candidateId}/sections/${result.next_section_id}/instructions`, { replace: true })
        return
      }
      navigate(`/candidate/${candidateId}/review`, { replace: true })
    } catch (requestError) {
      console.error('candidate_profile_submit_failed', requestError)
      setError(requestError.message)
      setSubmitting(false)
    }
  }

  if (!data || !ready) {
    return <LoadingPulse fullPage />
  }

  return (
    <div className="candidate-journey">
      <CandidatePortalHeader status="Draft Saved" statusTone="ok" candidateName={data.candidate.full_name} />

      <main className="candidate-profile-page">
        <div className="candidate-profile-shell">
          <section className="candidate-profile-hero">
            <div>
              <p className="eyebrow">{data.assessment.name}</p>
              <h1>Complete Profile</h1>
              <p>Complete the details below before entering the assessment flow.</p>
            </div>
          </section>

          <form onSubmit={submit} className="candidate-profile-form loading-overlay-host">
            <LoadingOverlay open={submitting} label="Saving profile..." />
            <section className="candidate-profile-section">
              <div className="candidate-profile-section__head">
                <span className="candidate-profile-section__icon">P</span>
                <h2>Personal Information</h2>
              </div>
              <div className="candidate-profile-grid">
                <div className="candidate-profile-field">
                  <label htmlFor="candidate-first-name">First Name</label>
                  <input id="candidate-first-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} placeholder="e.g. Alex" required />
                </div>
                <div className="candidate-profile-field">
                  <label htmlFor="candidate-last-name">Last Name</label>
                  <input id="candidate-last-name" value={lastName} onChange={(event) => setLastName(event.target.value)} placeholder="e.g. Rivera" required />
                </div>
                <div className="candidate-profile-field candidate-profile-field--wide">
                  <label htmlFor="candidate-email">Email Address</label>
                  <div className="candidate-profile-field__locked">
                    <input id="candidate-email" type="email" value={data.candidate.email} disabled />
                    <span>LOCKED</span>
                  </div>
                </div>
              </div>
            </section>

            <section className="candidate-profile-section">
              <div className="candidate-profile-section__head">
                <span className="candidate-profile-section__icon">DEV</span>
                <h2>Technical Presence</h2>
              </div>
              <div className="candidate-profile-stack">
                <div className="candidate-profile-field">
                  <label htmlFor="candidate-github">GitHub Profile URL</label>
                  <input id="candidate-github" type="url" value={githubUrl} onChange={(event) => setGithubUrl(event.target.value)} placeholder="https://github.com/username" required />
                </div>
                <div className="candidate-profile-field">
                  <label htmlFor="candidate-leetcode">LeetCode Profile URL</label>
                  <input id="candidate-leetcode" type="url" value={leetcodeUrl} onChange={(event) => setLeetcodeUrl(event.target.value)} placeholder="https://leetcode.com/username" required />
                </div>
              </div>
            </section>

            <section className="candidate-profile-section">
              <div className="candidate-profile-section__head">
                <span className="candidate-profile-section__icon">CV</span>
                <h2>Professional Resume</h2>
              </div>

              <div className="candidate-profile-resume-input">
                <div className="candidate-profile-field">
                  <label htmlFor="candidate-resume-pdf">Resume PDF</label>
                  <input
                    id="candidate-resume-pdf"
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0] || null
                      setPdfResume(file)
                    }}
                  />
                  <label
                    htmlFor="candidate-resume-pdf"
                    className={`candidate-profile-upload-dropzone ${resumePdf ? 'candidate-profile-upload-dropzone--active' : ''}`}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault()
                      const file = event.dataTransfer.files?.[0] || null
                      setPdfResume(file)
                    }}
                  >
                    <strong>{resumePdf ? resumePdf.name : 'Drag and drop PDF here'}</strong>
                    <span>{resumePdf ? 'PDF selected. Click or drop another file to replace it.' : 'or click to choose a PDF file'}</span>
                  </label>
                </div>

                <div className="candidate-profile-field">
                  <label htmlFor="candidate-resume-drive">Paste Link (Optional)</label>
                  <input
                    id="candidate-resume-drive"
                    type="url"
                    value={resumeDriveLink}
                    onChange={(event) => {
                      setResumeDriveLink(event.target.value)
                    }}
                    placeholder="https://drive.google.com/..."
                  />
                </div>
              </div>
            </section>

            <footer className="candidate-profile-actions">
              {error && <p className="error">{error}</p>}
              <button className="primary candidate-profile-actions__submit" type="submit" disabled={submitting}>
                {submitting ? 'Saving profile...' : 'Save Profile and Start Assessment'}
              </button>
              <p>The assessment starts immediately after this step.</p>
            </footer>
          </form>
        </div>
      </main>
    </div>
  )
}
