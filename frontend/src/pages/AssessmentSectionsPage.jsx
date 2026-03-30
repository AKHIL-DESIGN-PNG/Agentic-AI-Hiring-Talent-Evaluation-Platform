import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, sanitizeMessage } from '../api'
import TopNav from '../components/TopNav'

export default function AssessmentSectionsPage() {
  const { assessmentSlug } = useParams()
  const navigate = useNavigate()
  const [assessment, setAssessment] = useState(null)
  const [sections, setSections] = useState([])
  const [selected, setSelected] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function load() {
      const [availableSections, detail] = await Promise.all([
        api('/api/admin/sections', {}, true),
        api(`/api/admin/assessments/slug/${assessmentSlug}`, {}, true)
      ])
      setSections(availableSections)
      setAssessment(detail)
      setSelected(detail.sections.map((section) => section.id))
      setError('')
    }

    load().catch((requestError) => {
      setError(sanitizeMessage(requestError?.message || 'Unable to load section dashboard.'))
    })
  }, [assessmentSlug])

  const selectedSet = useMemo(() => new Set(selected), [selected])

  function toggleSection(sectionId) {
    setSelected((current) => (
      current.includes(sectionId)
        ? current.filter((id) => id !== sectionId)
        : [...current, sectionId]
    ))
  }

  async function saveSections() {
    if (selected.length === 0) {
      setError('Select at least one section.')
      return
    }

    try {
      setSaving(true)
      setError('')
      await api(
        `/api/admin/assessments/${assessment.id}/sections`,
        {
          method: 'PUT',
          body: JSON.stringify({ section_ids: selected })
        },
        true
      )
      navigate(`/admin/assessments/${assessment.slug}#overview`)
    } catch (requestError) {
      setError(sanitizeMessage(requestError?.message || 'Unable to save assigned sections.'))
      setSaving(false)
    }
  }

  function openSection(section) {
    if (!selectedSet.has(section.id)) return
    if (section.key === 'coding_section') return
    if (section.section_type === 'verbal') {
      navigate(`/admin/a/${assessment.slug}/s/${section.key}/v`)
      return
    }
    if (section.section_type === 'mcq') {
      navigate(`/admin/assessments/${assessment.slug}/sections/${section.key}/mcq-edit#edit-mcq`)
    }
  }

  function handleCardClick(section) {
    if (!selectedSet.has(section.id)) {
      toggleSection(section.id)
      return
    }
    openSection(section)
  }

  return (
    <div>
      <TopNav />
      <main className="page">
        <div className="heading-row">
          <div>
            <p className="muted">AITS &gt; Assessments</p>
            <h2>Section Dashboard</h2>
            <p className="muted">
              Click any card to assign it. Assigned verbal and MCQ sections open directly into their editor.
            </p>
            {assessment && <p className="pill">{assessment.name}</p>}
          </div>
          <div className="actions-row">
            <button className="ghost-btn" type="button" onClick={() => navigate(`/admin/assessments/${assessment.slug}#overview`)}>
              Back
            </button>
            <button className="primary" type="button" onClick={saveSections} disabled={saving}>
              {saving ? 'Saving...' : 'Save Sections'}
            </button>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="cards-grid">
          {sections.map((section) => {
            const assigned = selectedSet.has(section.id)

            return (
              <article
                key={section.id}
                className={`section-card section-card--dashboard section-card--interactive${assigned ? ' section-card--assigned' : ''}`}
              >
                <div
                  className="section-card__surface"
                  onClick={() => handleCardClick(section)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      handleCardClick(section)
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <div className="heading-row">
                    <h3 style={{ margin: 0 }}>{section.title}</h3>
                    <button
                      className={`status-pill section-card__status-toggle status-pill--${assigned ? 'completed' : 'invited'}`}
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        toggleSection(section.id)
                      }}
                    >
                      {assigned ? 'tap to unassign' : 'tap to assign'}
                    </button>
                  </div>
                  <p>{section.description}</p>
                  <p className="muted">{section.duration_minutes} mins</p>
                  <div className="section-card__meta">
                    <span className="pill">{section.section_type}</span>
                    <span className="section-card__hint">
                      {assigned
                        ? section.key === 'coding_section'
                          ? 'Default question bank'
                          : ''
                        : 'Not in this assessment'}
                    </span>
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      </main>
    </div>
  )
}
