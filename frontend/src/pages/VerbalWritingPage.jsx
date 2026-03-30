import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, sanitizeMessage } from '../api'
import Toast from '../components/Toast'
import FormContainer from '../components/mcq/FormContainer'
import InputField from '../components/mcq/InputField'
import {
  VerbalDashboardCard,
  VerbalDashboardEmpty,
  VerbalDashboardShell,
  VerbalDeleteModal,
  VerbalEditorModal
} from '../components/verbal/VerbalDashboard'
import {
  useVerbalEditorConfig,
  VerbalTopicLoading
} from './verbalTopicShared'

function createWritingTask(index) {
  return {
    id: `writing-${Date.now()}-${index}`,
    topic: '',
    min_words: 80
  }
}

export default function VerbalWritingPage() {
  const { assessmentSlug, sectionKey } = useParams()
  const navigate = useNavigate()
  const {
    config,
    setConfig,
    loading,
    saving,
    error,
    saveConfig
  } = useVerbalEditorConfig(assessmentSlug, sectionKey, 'Unable to load writing prompts.')

  const [editingId, setEditingId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [aiCount, setAiCount] = useState('3')
  const [aiOpen, setAiOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const [toast, setToast] = useState('')
  const items = config?.writing_tasks || []
  const editingItem = useMemo(
    () => items.find((item) => item.id === editingId) || null,
    [items, editingId]
  )
  const [draft, setDraft] = useState(createWritingTask(1))

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(''), 2400)
    return () => window.clearTimeout(timer)
  }, [toast])

  if (loading) return <VerbalTopicLoading />

  function openAdd() {
    setDraft(createWritingTask(items.length + 1))
    setEditingId('new')
  }

  function openEdit(item) {
    setDraft({ ...item })
    setEditingId(item.id)
  }

  function closeEditor() {
    setEditingId(null)
    setDraft(createWritingTask(items.length + 1))
  }

  function closeAiModal() {
    setAiOpen(false)
    setAiCount('3')
    setAiLoading(false)
    setAiError('')
  }

  function upsertItem() {
    if (!draft.topic.trim()) return

    setConfig((current) => {
      const nextItems = [...(current?.writing_tasks || [])]
      const nextValue = {
        ...draft,
        topic: draft.topic.trim(),
        min_words: Number(draft.min_words) || 0
      }

      if (editingId === 'new') {
        nextItems.push(nextValue)
      } else {
        const index = nextItems.findIndex((item) => item.id === editingId)
        if (index >= 0) nextItems[index] = nextValue
      }

      return {
        ...current,
        writing_tasks: nextItems
      }
    })

    closeEditor()
  }

  function confirmDelete() {
    if (!deleteTarget) return
    setConfig((current) => ({
      ...current,
      writing_tasks: (current?.writing_tasks || []).filter((item) => item.id !== deleteTarget.id)
    }))
    setDeleteTarget(null)
  }

  async function generateAiTopics() {
    try {
      setAiLoading(true)
      setAiError('')
      const response = await api('/api/admin/verbal-ai/generate', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'writing',
          count: Number(aiCount) || 1
        })
      }, true)
      const nextConfig = {
        ...config,
        writing_tasks: [...items, ...(response.items || [])]
      }
      setConfig(nextConfig)
      await saveConfig(nextConfig)
      setToast('AI questions generated and saved.')
      closeAiModal()
    } catch (requestError) {
      setAiError(sanitizeMessage(requestError?.message || 'Unable to generate writing topics.'))
      setAiLoading(false)
    }
  }

  async function handleSave() {
    const ok = await saveConfig(config)
    if (ok) navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)
  }

  return (
    <VerbalDashboardShell
      title="Writing"
      countText={`${items.length} ${items.length === 1 ? 'topic' : 'topics'}`}
      addLabel="Add Topic"
      error={error}
      saving={saving}
      onAdd={openAdd}
      onBack={() => navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)}
      onSave={handleSave}
    >
      <FormContainer title="Writing Topics" description="Use the imported card-based topic dashboard to manage multiple writing prompts and limits.">
        {items.length ? (
          <div className="verbal-dashboard-stack">
            <div className="actions-row">
              <button className="ghost-btn" type="button" onClick={() => setAiOpen(true)}>
                Use AI
              </button>
            </div>
            <div className="verbal-dashboard-grid">
              {items.map((item, index) => (
                <VerbalDashboardCard
                  key={item.id}
                  index={index + 1}
                  title={item.topic || `Writing Topic ${index + 1}`}
                  subtitle="Candidate writing prompt"
                  details={[
                    { label: 'Minimum words', value: String(item.min_words || 0) }
                  ]}
                  onEdit={() => openEdit(item)}
                  onDelete={() => setDeleteTarget(item)}
                />
              ))}
            </div>
          </div>
        ) : (
          <VerbalDashboardEmpty
            title="Writing"
            description="Add your first writing topic and set the minimum word requirement."
            actionLabel="Add Topic"
            onAction={openAdd}
            secondaryActionLabel="Use AI"
            onSecondaryAction={() => setAiOpen(true)}
          />
        )}
      </FormContainer>

      <VerbalEditorModal
        open={!!editingId}
        title={editingId === 'new' ? 'Add Writing Topic' : `Edit ${editingItem?.topic || 'Writing Topic'}`}
        onClose={closeEditor}
        onSubmit={upsertItem}
        submitLabel={editingId === 'new' ? 'Add Topic' : 'Save Changes'}
      >
        <InputField label="Topic" value={draft.topic} multiline onChange={(value) => setDraft((current) => ({ ...current, topic: value }))} />
        <InputField
          label="Minimum Words"
          value={String(draft.min_words ?? 80)}
          onChange={(value) => setDraft((current) => ({ ...current, min_words: value }))}
        />
      </VerbalEditorModal>

      <VerbalDeleteModal
        open={!!deleteTarget}
        title={deleteTarget?.topic || 'this topic'}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />

      <VerbalEditorModal
        open={aiOpen}
        title="Use AI For Writing"
        onClose={closeAiModal}
        onSubmit={generateAiTopics}
        submitLabel={aiLoading ? 'Generating...' : 'Generate'}
      >
        <InputField label="Number Of Questions" value={aiCount} onChange={setAiCount} />
        {aiError ? <p className="error">{aiError}</p> : null}
      </VerbalEditorModal>
      <Toast open={Boolean(toast)} message={toast} />
    </VerbalDashboardShell>
  )
}
