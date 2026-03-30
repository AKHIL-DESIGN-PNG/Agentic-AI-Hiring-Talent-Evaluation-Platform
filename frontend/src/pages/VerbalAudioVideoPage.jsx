import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, sanitizeMessage } from '../api'
import Toast from '../components/Toast'
import FormContainer from '../components/mcq/FormContainer'
import InputField from '../components/mcq/InputField'
import {
  VerbalDashboardCard,
  VerbalDashboardEmpty,
  VerbalDashboardShell,
  VerbalEditorModal
} from '../components/verbal/VerbalDashboard'
import {
  useVerbalEditorConfig,
  VerbalTopicLoading
} from './verbalTopicShared'

function createListeningQuestion(blockId, index) {
  return {
    id: `${blockId}-question-${Date.now()}-${index}`,
    prompt: '',
    options: ['', '', '', ''],
    answer: ''
  }
}

function createListeningBlock(index) {
  const id = `media-block-${Date.now()}-${index}`
  return {
    id,
    title: `Media Block ${index}`,
    media_type: 'audio',
    media_url: '',
    prompt: 'Write what you heard or answer the questions about the audio/video.',
    questions: []
  }
}

export default function VerbalAudioVideoPage() {
  const { assessmentSlug, sectionKey } = useParams()
  const navigate = useNavigate()
  const {
    config,
    setConfig,
    loading,
    saving,
    error,
    saveConfig
  } = useVerbalEditorConfig(assessmentSlug, sectionKey, 'Unable to load verbal listening blocks.')

  const [editingId, setEditingId] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [aiOpen, setAiOpen] = useState(false)
  const [aiTranscript, setAiTranscript] = useState('')
  const [aiCount, setAiCount] = useState('3')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const [toast, setToast] = useState('')
  const blocks = config?.listening_blocks || []
  const editingBlock = useMemo(
    () => blocks.find((item) => item.id === editingId) || null,
    [blocks, editingId]
  )
  const [draft, setDraft] = useState(createListeningBlock(1))
  const fileInputRef = useRef(null)

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(''), 2400)
    return () => window.clearTimeout(timer)
  }, [toast])

  if (loading) return <VerbalTopicLoading />

  function openAdd() {
    setDraft(createListeningBlock(blocks.length + 1))
    setEditingId('new')
    setUploadError('')
  }

  function openEdit(block) {
    setDraft({
      ...block,
      questions: Array.isArray(block.questions) ? block.questions : []
    })
    setEditingId(block.id)
    setUploadError('')
  }

  function closeEditor() {
    setEditingId(null)
    setDraft(createListeningBlock(blocks.length + 1))
    setUploading(false)
    setUploadError('')
    closeAiPanel()
  }

  function openAiPanel() {
    setAiOpen(true)
    setAiTranscript('')
    setAiCount('3')
    setAiError('')
  }

  function closeAiPanel() {
    setAiOpen(false)
    setAiTranscript('')
    setAiCount('3')
    setAiError('')
    setAiLoading(false)
  }

  async function uploadMedia(file) {
    if (!file) return
    const formData = new FormData()
    formData.append('media_file', file)

    try {
      setUploading(true)
      setUploadError('')
      const response = await api('/api/admin/verbal-media-upload', {
        method: 'POST',
        body: formData
      }, true)
      setDraft((current) => ({
        ...current,
        media_url: response.media_url || '',
        media_type: response.media_type || current.media_type
      }))
    } catch (requestError) {
      setUploadError(sanitizeMessage(requestError?.message || 'Unable to upload media.'))
    } finally {
      setUploading(false)
    }
  }

  function addQuestion() {
    setDraft((current) => ({
      ...current,
      questions: [...(current.questions || []), createListeningQuestion(current.id, (current.questions || []).length + 1)]
    }))
  }

  function updateQuestion(questionId, patch) {
    setDraft((current) => ({
      ...current,
      questions: (current.questions || []).map((item) => (
        item.id === questionId ? { ...item, ...patch } : item
      ))
    }))
  }

  function updateQuestionOption(questionId, optionIndex, value) {
    setDraft((current) => ({
      ...current,
      questions: (current.questions || []).map((item) => {
        if (item.id !== questionId) return item
        const nextOptions = [...(item.options || [])]
        nextOptions[optionIndex] = value
        return { ...item, options: nextOptions }
      })
    }))
  }

  function removeQuestion(questionId) {
    setDraft((current) => ({
      ...current,
      questions: (current.questions || []).filter((item) => item.id !== questionId)
    }))
  }

  function upsertBlock() {
    if (!draft.title.trim()) return

    const nextValue = {
      ...draft,
      title: draft.title.trim(),
      prompt: draft.prompt.trim() || 'Write what you heard or answer the questions about the audio/video.',
      media_url: draft.media_url.trim(),
      questions: (draft.questions || [])
        .map((item) => ({
          ...item,
          prompt: String(item.prompt || '').trim(),
          options: (item.options || []).map((option) => String(option || '').trim()).filter(Boolean),
          answer: String(item.answer || '').trim()
        }))
        .filter((item) => item.prompt)
    }

    setConfig((current) => {
      const nextBlocks = [...(current?.listening_blocks || [])]
      if (editingId === 'new') {
        nextBlocks.push(nextValue)
      } else {
        const index = nextBlocks.findIndex((item) => item.id === editingId)
        if (index >= 0) {
          nextBlocks[index] = nextValue
        }
      }

      return {
        ...current,
        listening_blocks: nextBlocks
      }
    })

    closeEditor()
  }

  function deleteBlock(blockId) {
    setConfig((current) => ({
      ...current,
      listening_blocks: (current?.listening_blocks || []).filter((item) => item.id !== blockId)
    }))
    if (editingId === blockId) {
      closeEditor()
    }
  }

  async function generateAiQuestions() {
    if (!aiTranscript.trim()) {
      setAiError('Transcript is required.')
      return
    }
    try {
      setAiLoading(true)
      setAiError('')
      const response = await api('/api/admin/verbal-ai/generate', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'audio_video',
          transcript: aiTranscript,
          count: Number(aiCount) || 1
        })
      }, true)

      const nextConfig = {
        ...config,
        listening_blocks: blocks.map((block) => (
          block.id === editingId
            ? { ...block, questions: [...(block.questions || []), ...(response.items || [])] }
            : block
        ))
      }
      setConfig(nextConfig)
      setDraft((current) => ({
        ...current,
        questions: [...(current.questions || []), ...(response.items || [])]
      }))
      await saveConfig(nextConfig)
      setToast('AI questions generated and saved.')
      closeAiPanel()
    } catch (requestError) {
      setAiError(sanitizeMessage(requestError?.message || 'Unable to generate questions.'))
      setAiLoading(false)
    }
  }

  async function handleSave() {
    const ok = await saveConfig(config)
    if (ok) navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)
  }

  return (
    <VerbalDashboardShell
      title="Audio / Video"
      countText={`${blocks.length} ${blocks.length === 1 ? 'block' : 'blocks'}`}
      error={error}
      saving={saving}
      onBack={() => navigate(`/admin/a/${assessmentSlug}/s/${sectionKey}/v`)}
      onSave={handleSave}
    >
      <FormContainer title="Listening Blocks" description="Each block keeps one uploaded media file and can contain multiple MCQ questions.">
        {blocks.length ? (
          <div className="verbal-dashboard-stack">
            <div className="verbal-dashboard-grid">
              {blocks.map((block, index) => (
                <VerbalDashboardCard
                  key={block.id}
                  index={index + 1}
                  title={block.title || `Media Block ${index + 1}`}
                  subtitle=""
                  details={[
                    { label: 'Media type', value: block.media_type },
                    { label: 'Questions', value: String((block.questions || []).length || 0) },
                    { label: 'Media', value: block.media_url ? 'Uploaded' : 'Missing' }
                  ]}
                  onEdit={() => openEdit(block)}
                  onDelete={() => deleteBlock(block.id)}
                />
              ))}
            </div>
            <button className="verbal-dashboard-add-tile" type="button" onClick={openAdd}>
              + Add Block
            </button>
          </div>
        ) : (
          <VerbalDashboardEmpty
            title="Audio / Video"
            description="Add your first listening block with one uploaded audio/video file and multiple MCQ questions."
            actionLabel="Add Block"
            onAction={openAdd}
          />
        )}
      </FormContainer>

      {editingId ? (
        <FormContainer
          title={editingId === 'new' ? 'Add Media Block' : `Edit ${editingBlock?.title || 'Media Block'}`}
          description="Keep title, media upload, and questions in one inline editor."
          actions={(
            <div className="verbal-inline-editor__actions">
              <button className="ghost-btn" type="button" onClick={closeEditor}>
                Cancel
              </button>
              <button className="ghost-btn" type="button" onClick={openAiPanel}>
                Use AI
              </button>
              <button className="primary" type="button" onClick={upsertBlock}>
                {editingId === 'new' ? 'Add Block' : 'Save Changes'}
              </button>
            </div>
          )}
        >
          <div className="verbal-media-inline-editor">
            <InputField label="Title" value={draft.title} onChange={(value) => setDraft((current) => ({ ...current, title: value }))} />
            <div className="mcq-edit-field">
              <span className="mcq-edit-field__label">Media Upload</span>
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*,video/*"
                className="hidden"
                onChange={(event) => uploadMedia(event.target.files?.[0])}
              />
              <button
                className="verbal-upload-dropzone verbal-upload-dropzone--compact"
                type="button"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault()
                  uploadMedia(event.dataTransfer.files?.[0])
                }}
              >
                <strong>{uploading ? 'Uploading media...' : 'Drag and drop audio/video here'}</strong>
                <span>{draft.media_url ? 'Media uploaded. Drop another file to replace it.' : 'or click to choose a file'}</span>
              </button>
              {draft.media_url ? (
                <div className="verbal-upload-preview">
                  <span className="pill">{draft.media_type}</span>
                  <a href={draft.media_url} target="_blank" rel="noreferrer">{draft.media_url}</a>
                </div>
              ) : null}
              {uploadError ? <p className="error">{uploadError}</p> : null}
            </div>

            <div className="verbal-question-actions verbal-question-actions--solo">
              <button className="mcq-edit-add-btn verbal-question-actions__add" type="button" onClick={addQuestion}>
                Add Question
              </button>
            </div>

            {(draft.questions || []).length ? (
              <div className="verbal-listening-question-list">
                {draft.questions.map((question, index) => (
                  <section key={question.id} className="verbal-listening-question-card">
                    <div className="heading-row">
                      <strong>Question {index + 1}</strong>
                      <button className="ghost-btn" type="button" onClick={() => removeQuestion(question.id)}>
                        Remove
                      </button>
                    </div>
                    <InputField
                      label="Question Prompt"
                      value={question.prompt}
                      multiline
                      onChange={(value) => updateQuestion(question.id, { prompt: value })}
                    />
                    <div className="verbal-mcq-options-grid">
                      {(question.options || []).map((option, optionIndex) => (
                        <InputField
                          key={`${question.id}-${optionIndex}`}
                          label={`Option ${optionIndex + 1}`}
                          value={option}
                          onChange={(value) => updateQuestionOption(question.id, optionIndex, value)}
                        />
                      ))}
                    </div>
                    <label className="mcq-edit-field">
                      <span className="mcq-edit-field__label">Correct Answer</span>
                      <select
                        className="mcq-edit-input"
                        value={question.answer}
                        onChange={(event) => updateQuestion(question.id, { answer: event.target.value })}
                      >
                        <option value="">Select correct option</option>
                        {(question.options || []).map((option, optionIndex) => (
                          <option key={`${question.id}-answer-${optionIndex}`} value={option}>
                            {option || `Option ${optionIndex + 1}`}
                          </option>
                        ))}
                      </select>
                    </label>
                  </section>
                ))}
              </div>
            ) : null}
          </div>
        </FormContainer>
      ) : null}

      <VerbalEditorModal
        open={aiOpen}
        title="Use AI For Questions"
        onClose={closeAiPanel}
        onSubmit={generateAiQuestions}
        submitLabel={aiLoading ? 'Generating...' : 'Generate Questions'}
      >
        <div className="verbal-inline-ai-panel__grid">
          <InputField
            label="Transcript"
            value={aiTranscript}
            multiline
            onChange={setAiTranscript}
          />
          <InputField
            label="Number Of Questions"
            value={aiCount}
            onChange={setAiCount}
          />
        </div>
        {aiError ? <p className="error">{aiError}</p> : null}
      </VerbalEditorModal>

      <Toast open={Boolean(toast)} message={toast} />
    </VerbalDashboardShell>
  )
}
