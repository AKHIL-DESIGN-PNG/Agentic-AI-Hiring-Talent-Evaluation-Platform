import { useEffect, useState } from 'react'
import { api, sanitizeMessage } from '../api'
import LoadingPulse from '../components/LoadingPulse'
import TopNav from '../components/TopNav'

export function createDefaultVerbalConfig(sectionTitle) {
  return {
    section: sectionTitle || 'Verbal Ability',
    listening_blocks: Array.from({ length: 3 }, (_, index) => ({
      id: `media-block-${index + 1}`,
      title: `Media Block ${index + 1}`,
      media_type: 'audio',
      media_url: '',
      prompt: 'Write what you heard or answer the questions about the audio/video.',
      questions: []
    })),
    speaking_tasks: [
      { id: 'speaking-1', prompt: '' }
    ],
    writing_tasks: [
      { id: 'writing-1', topic: '', min_words: 80 }
    ],
    drag_drop_questions: [
      { id: 'drag-drop-1', template: '', options: ['', '', '', ''], answer_order: [] }
    ]
  }
}

export const VERBAL_TOPICS = [
  {
    routeKey: 'audio-video',
    title: 'Audio / Video',
    description: 'Open a dedicated page for all listening questions.',
    configKey: 'listening_blocks',
    itemLabel: 'block'
  },
  {
    routeKey: 'speaking',
    title: 'Speaking',
    description: 'Open a dedicated page for all speaking prompts.',
    configKey: 'speaking_tasks',
    itemLabel: 'prompt'
  },
  {
    routeKey: 'writing',
    title: 'Writing',
    description: 'Open a dedicated page for all writing prompts.',
    configKey: 'writing_tasks',
    itemLabel: 'topic'
  },
  {
    routeKey: 'fill-in-the-blanks',
    title: 'Fill In The Blanks',
    description: 'Open a dedicated page for all fill-in-the-blanks questions.',
    configKey: 'drag_drop_questions',
    itemLabel: 'item'
  }
]

export function useVerbalEditorConfig(assessmentSlug, sectionKey, loadMessage) {
  const [assessment, setAssessment] = useState(null)
  const [section, setSection] = useState(null)
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/api/admin/assessments/slug/${assessmentSlug}`, {}, true)
      .then((detail) => {
        const targetSection = (detail.sections || []).find((item) => item.key === sectionKey)
        if (!targetSection) throw new Error('Section not found')
        setAssessment(detail)
        return api(`/api/admin/assessments/${detail.id}/sections/${targetSection.id}/verbal-config`, {}, true)
      })
      .then((response) => {
        setSection(response.section)
        setConfig(response.config || createDefaultVerbalConfig(response.section?.title))
        setLoading(false)
      })
      .catch((requestError) => {
        setError(sanitizeMessage(requestError?.message || loadMessage))
        setLoading(false)
      })
  }, [assessmentSlug, sectionKey, loadMessage])

  async function saveConfig(nextConfig) {
    try {
      setSaving(true)
      setError('')
      await api(`/api/admin/assessments/${assessment.id}/sections/${section.id}/verbal-config`, {
        method: 'PUT',
        body: JSON.stringify({ config: nextConfig })
      }, true)
      setSaving(false)
      return true
    } catch (requestError) {
      setError(sanitizeMessage(requestError?.message || 'Unable to save verbal config.'))
      setSaving(false)
      return false
    }
  }

  return {
    assessment,
    section,
    config,
    setConfig,
    loading,
    saving,
    error,
    setError,
    saveConfig
  }
}

export function VerbalTopicLoading() {
  return (
    <div>
      <TopNav />
      <LoadingPulse fullPage />
    </div>
  )
}
