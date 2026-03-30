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

function createFillBlank(index) {
  return {
    id: `drag-drop-${Date.now()}-${index}`,
    template: '',
    options: [],
    answer_order: []
  }
}

function joinItems(items) {
  return (items || []).join(', ')
}

export default function VerbalFillBlanksPage() {
  const { assessmentSlug, sectionKey } = useParams()
  const navigate = useNavigate()
  const {
    config,
    setConfig,
    loading,
    saving,
    error,
    saveConfig
  } = useVerbalEditorConfig(assessmentSlug, sectionKey, 'Unable to load fill-in-the-blanks questions.')

  const [editingId, setEditingId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [aiCount, setAiCount] = useState('3')
  const [aiOpen, setAiOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const [toast, setToast] = useState('')
  const items = config?.drag_drop_questions || []
  const editingItem = useMemo(
    () => items.find((item) => item.id === editingId) || null,
    [items, editingId]
  )
  const [draft, setDraft] = useState({
    ...createFillBlank(1),
    optionsText: '',
    answerOrderText: ''
  })

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(''), 2400)
    return () => window.clearTimeout(timer)
  }, [toast])

  if (loading) return <VerbalTopicLoading />

  function openAdd() {
    setDraft({
      ...createFillBlank(items.length + 1),
      optionsText: '',
      answerOrderText: ''
    })
    setEditingId('new')
  }

  function openEdit(item) {
    setDraft({
      ...item,
      optionsText: joinItems(item.options),
      answerOrderText: joinItems(item.answer_order)
    })
    setEditingId(item.id)
  }

  function closeEditor() {
    setEditingId(null)
    setDraft({
      ...createFillBlank(items.length + 1),
      optionsText: '',
      answerOrderText: ''
    })
  }

  function closeAiModal() {
    setAiOpen(false)
    setAiCount('3')
    setAiLoading(false)
    setAiError('')
  }

  function parseCsv(value) {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
  }

  function upsertItem() {
    if (!draft.template.trim()) return

    setConfig((current) => {
      const nextItems = [...(current?.drag_drop_questions || [])]
      const nextValue = {
        id: draft.id,
        template: draft.template.trim(),
        options: parseCsv(draft.optionsText),
        answer_order: parseCsv(draft.answerOrderText)
      }

      if (editingId === 'new') {
        nextItems.push(nextValue)
      } else {
        const index = nextItems.findIndex((item) => item.id === editingId)
        if (index >= 0) nextItems[index] = nextValue
      }

      return {
        ...current,
        drag_drop_questions: nextItems
      }
    })

    closeEditor()
  }

  function confirmDelete() {
    if (!deleteTarget) return
    setConfig((current) => ({
      ...current,
      drag_drop_questions: (current?.drag_drop_questions || []).filter((item) => item.id !== deleteTarget.id)
    }))
    setDeleteTarget(null)
  }

  async function generateAiItems() {
    try {
      setAiLoading(true)
      setAiError('')
      const response = await api('/api/admin/verbal-ai/generate', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'fill_blanks',
          count: Number(aiCount) || 1
        })
      }, true)
      const nextConfig = {
        ...config,
        drag_drop_questions: [...items, ...(response.items || [])]
      }
      setConfig(nextConfig)
      await saveConfig(nextConfig)
      setToast('AI questions generated and saved.')
      closeAiModal()
    } catch (requestError) {
      setAiError(sanitizeMessage(requestError?.message || 'Unable to generate fill-in-the-blanks items.'))
      setAiLoading(false)
    }
  }

  async function handleSave() {
    const ok = await saveConfig(config)
    if (ok) navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)
  }

  return (
    <VerbalDashboardShell
      title="Fill In The Blanks"
      countText={`${items.length} ${items.length === 1 ? 'item' : 'items'}`}
      addLabel="Add Question"
      error={error}
      saving={saving}
      onAdd={openAdd}
      onBack={() => navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)}
      onSave={handleSave}
    >
      <FormContainer title="Fill-In-The-Blanks" description="Manage multiple drag-drop items using the imported dashboard interaction pattern.">
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
                  title={`Question ${index + 1}`}
                  subtitle={item.template || 'No template added yet.'}
                  details={[
                    { label: 'Options', value: `${(item.options || []).length}` },
                    { label: 'Answer order', value: joinItems(item.answer_order) || 'Not set' }
                  ]}
                  onEdit={() => openEdit(item)}
                  onDelete={() => setDeleteTarget(item)}
                />
              ))}
            </div>
          </div>
        ) : (
          <VerbalDashboardEmpty
            title="Fill In The Blanks"
            description="Add your first drag-drop sentence, option bank, and expected answer order."
            actionLabel="Add Question"
            onAction={openAdd}
            secondaryActionLabel="Use AI"
            onSecondaryAction={() => setAiOpen(true)}
          />
        )}
      </FormContainer>

      <VerbalEditorModal
        open={!!editingId}
        title={editingId === 'new' ? 'Add Fill-In-The-Blanks Question' : `Edit Question ${items.findIndex((item) => item.id === editingId) + 1}`}
        onClose={closeEditor}
        onSubmit={upsertItem}
        submitLabel={editingId === 'new' ? 'Add Question' : 'Save Changes'}
      >
        <InputField label="Template" value={draft.template} multiline onChange={(value) => setDraft((current) => ({ ...current, template: value }))} />
        <InputField
          label="Options (comma separated)"
          value={draft.optionsText}
          onChange={(value) => setDraft((current) => ({ ...current, optionsText: value }))}
        />
        <InputField
          label="Answer Order (comma separated)"
          value={draft.answerOrderText}
          onChange={(value) => setDraft((current) => ({ ...current, answerOrderText: value }))}
        />
      </VerbalEditorModal>

      <VerbalDeleteModal
        open={!!deleteTarget}
        title={deleteTarget?.template || 'this question'}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
      />

      <VerbalEditorModal
        open={aiOpen}
        title="Use AI For Fill In The Blanks"
        onClose={closeAiModal}
        onSubmit={generateAiItems}
        submitLabel={aiLoading ? 'Generating...' : 'Generate'}
      >
        <InputField label="Number Of Questions" value={aiCount} onChange={setAiCount} />
        {aiError ? <p className="error">{aiError}</p> : null}
      </VerbalEditorModal>
      <Toast open={Boolean(toast)} message={toast} />
    </VerbalDashboardShell>
  )
}
