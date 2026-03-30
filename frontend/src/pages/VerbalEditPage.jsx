import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, sanitizeMessage } from '../api'
import LoadingPulse from '../components/LoadingPulse'
import TopNav from '../components/TopNav'
import FormContainer from '../components/mcq/FormContainer'
import VerbalTopicCard from '../components/verbal/VerbalTopicCard'
import { VERBAL_TOPICS } from './verbalTopicShared'

export default function VerbalEditPage() {
  const { assessmentSlug, sectionKey } = useParams()
  const navigate = useNavigate()
  const [section, setSection] = useState(null)
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/api/admin/assessments/slug/${assessmentSlug}`, {}, true)
      .then((detail) => {
        const targetSection = (detail.sections || []).find((item) => item.key === sectionKey)
        if (!targetSection) throw new Error('Section not found')
        return api(`/api/admin/assessments/${detail.id}/sections/${targetSection.id}/verbal-config`, {}, true)
      })
      .then((response) => {
        setSection(response.section)
        setConfig(response.config || {})
        setLoading(false)
      })
      .catch((requestError) => {
        setError(sanitizeMessage(requestError?.message || 'Unable to load verbal editor.'))
        setLoading(false)
      })
  }, [assessmentSlug, sectionKey])

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
      <main className="mcq-edit-page">
        <header className="mcq-edit-header">
          <div>
            <p className="muted">AITS &gt; Assessments &gt; Verbal Editor</p>
            <h1>{section?.title || 'Verbal Editor'}</h1>
          </div>
          <div className="actions-row">
            <button className="ghost-btn" type="button" onClick={() => navigate(`/admin/assessments/${assessmentSlug}/sections`)}>
              Back
            </button>
          </div>
        </header>
        {error && <p className="error">{error}</p>}

        <FormContainer title="Verbal Topics" description="Open a topic first. Each topic opens on a separate page and shows all of its questions there.">
          <div className="cards-grid">
            {VERBAL_TOPICS.map((topic) => (
              <VerbalTopicCard
                key={topic.routeKey}
                title={topic.title}
                description={topic.description}
                count={config?.[topic.configKey]?.length || 0}
                itemLabel={topic.itemLabel}
                onOpen={() => navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v/${topic.routeKey}`)}
              />
            ))}
          </div>
        </FormContainer>
      </main>
    </div>
  )
}
