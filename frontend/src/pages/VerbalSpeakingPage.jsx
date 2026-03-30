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

function createSpeakingTask(index) {
  return {
    id: `speaking-${Date.now()}-${index}`,
    prompt: ''
  }
}

export default function VerbalSpeakingPage() {
  const { assessmentSlug, sectionKey } = useParams()
  const navigate = useNavigate()
  const {
    config,
    setConfig,
    loading,
    saving,
    error,
    saveConfig
  } = useVerbalEditorConfig(assessmentSlug, sectionKey, 'Unable to load speaking prompts.')

  const [editingId, setEditingId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [aiCount, setAiCount] = useState('3')
  const [aiOpen, setAiOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const [toast, setToast] = useState('')
  const prompts = config?.speaking_tasks || []
  const editingPrompt = useMemo(
    () => prompts.find((item) => item.id === editingId) || null,
    [prompts, editingId]
  )
  const [draft, setDraft] = useState(createSpeakingTask(1))

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(''), 2400)
    return () => window.clearTimeout(timer)
  }, [toast])

  if (loading) return <VerbalTopicLoading />

  function openAdd() {
    setDraft(createSpeakingTask(prompts.length + 1))
    setEditingId('new')
  }

  function openEdit(item) {
    setDraft({ id: item.id, prompt: item.prompt || '' })
    setEditingId(item.id)
  }

  function closeEditor() {
    setEditingId(null)
    setDraft(createSpeakingTask(prompts.length + 1))
  }

  function closeAiModal() {
    setAiOpen(false)
    setAiCount('3')
    setAiLoading(false)
    setAiError('')
  }

  function upsertPrompt() {
    if (!draft.prompt.trim()) return

    setConfig((current) => {
      const nextItems = [...(current?.speaking_tasks || [])]
      const nextValue = {
        ...draft,
        prompt: draft.prompt.trim()
      }

      if (editingId === 'new') {
        nextItems.push(nextValue)
      } else {
        const index = nextItems.findIndex((item) => item.id === editingId)
        if (index >= 0) nextItems[index] = nextValue
      }

      return {
        ...current,
        speaking_tasks: nextItems
      }
    })

    closeEditor()
  }

  function confirmDelete() {
    if (!deleteTarget) return
    setConfig((current) => ({
      ...current,
      speaking_tasks: (current?.speaking_tasks || []).filter((item) => item.id !== deleteTarget.id)
    }))
    setDeleteTarget(null)
  }

  async function generateAiPrompts() {
    try {
      setAiLoading(true)
      setAiError('')
      const response = await api('/api/admin/verbal-ai/generate', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'speaking',
          count: Number(aiCount) || 1
        })
      }, true)
      const nextConfig = {
        ...config,
        speaking_tasks: [...prompts, ...(response.items || [])]
      }
      setConfig(nextConfig)
      await saveConfig(nextConfig)
      setToast('AI questions generated and saved.')
      closeAiModal()
    } catch (requestError) {
      setAiError(sanitizeMessage(requestError?.message || 'Unable to generate speaking prompts.'))
      setAiLoading(false)
    }
  }

  async function handleSave() {
    const ok = await saveConfig(config)
    if (ok) navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)
  }

  return (
    <VerbalDashboardShell
      title="Speaking"
      countText={`${prompts.length} ${prompts.length === 1 ? 'prompt' : 'prompts'}`}
      error={error}
      saving={saving}
      onBack={() => navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)}
      onSave={handleSave}
    >
      <FormContainer title="Speaking Prompts" description="Manage multiple speaking prompts. Candidates respond only to the prompt uploaded by the admin.">
        {prompts.length ? (
          <div className="verbal-dashboard-stack">
            <div className="actions-row">
              <button className="ghost-btn" type="button" onClick={() => setAiOpen(true)}>
                Use AI
              </button>
            </div>
            <div className="verbal-dashboard-grid">
              {prompts.map((item, index) => (
                <VerbalDashboardCard
                  key={item.id}
                  index={index + 1}
                  title={`Prompt ${index + 1}`}
                  subtitle={item.prompt || 'No speaking prompt added yet.'}
                  details={[
                    { label: 'Prompt status', value: item.prompt ? 'Ready' : 'Missing' }
                  ]}
                  onEdit={() => openEdit(item)}
                  onDelete={() => setDeleteTarget(item)}
                />
              ))}
            </div>
            <button className="verbal-dashboard-add-tile" type="button" onClick={openAdd}>
              + Add Prompt
            </button>
          </div>
        ) : (
          <VerbalDashboardEmpty
            title="Speaking"
            description="Add your first speaking prompt. Candidates will speak only to what the admin uploads here."
            actionLabel="Add Prompt"
            onAction={openAdd}
            secondaryActionLabel="Use AI"
            onSecondaryAction={() => setAiOpen(true)}
          />
        )}
      </FormContainer>

      <VerbalEditorModal
        open={!!editingId}
        title={editingId === 'new' ? 'Add Speaking Prompt' : `Edit ${editingPrompt?.prompt ? 'Speaking Prompt' : `Prompt ${prompts.findIndex((item) => item.id === editingId) + 1}`}`}
        onClose={closeEditor}
        onSubmit={upsertPrompt}
        submitLabel={editingId === 'new' ? 'Add Prompt' : 'Save Changes'}
      >
        <InputField label="Prompt" value={draft.prompt} multiline onChange={(value) => setDraft((current) => ({ ...current, prompt: value }))} />
      </VerbalEditorModal>

      <VerbalDeleteModal
        open={!!deleteTarget}
        title={deleteTarget?.prompt || 'this prompt'}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />

      <VerbalEditorModal
        open={aiOpen}
        title="Use AI For Speaking"
        onClose={closeAiModal}
        onSubmit={generateAiPrompts}
        submitLabel={aiLoading ? 'Generating...' : 'Generate'}
      >
        <InputField label="Number Of Questions" value={aiCount} onChange={setAiCount} />
        {aiError ? <p className="error">{aiError}</p> : null}
      </VerbalEditorModal>
      <Toast open={Boolean(toast)} message={toast} />
    </VerbalDashboardShell>
  )
}
