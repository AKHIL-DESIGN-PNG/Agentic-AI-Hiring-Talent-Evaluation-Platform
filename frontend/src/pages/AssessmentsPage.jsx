import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import LoadingOverlay from '../components/LoadingOverlay'
import Modal from '../components/Modal'
import TopNav from '../components/TopNav'

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1 6h2v8h-2V9Zm4 0h2v8h-2V9ZM7 9h2v8H7V9Zm-1 11V8h12v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2Z" fill="currentColor" />
    </svg>
  )
}

export default function AssessmentsPage() {
  const navigate = useNavigate()
  const [assessments, setAssessments] = useState([])
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [jdFile, setJdFile] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [creatingAssessment, setCreatingAssessment] = useState(false)
  const [error, setError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState(null)
  const jdFileInputRef = useRef(null)

  async function load() {
    const data = await api('/api/admin/assessments', {}, true)
    setAssessments(data)
  }

  useEffect(() => {
    load().catch((requestError) => {
      console.error('assessments_load_failed', requestError)
      setError('Unable to load assessments.')
    })
  }, [])

  async function createAssessment(event) {
    event.preventDefault()
    setError('')

    if (!name.trim()) {
      setError('Assessment name is required.')
      return
    }

    try {
      setCreatingAssessment(true)
      const formData = new FormData()
      formData.append('name', name)
      if (jdFile) formData.append('jd_file', jdFile)
      const data = await api(
        '/api/admin/assessments',
        {
          method: 'POST',
          body: formData
        },
        true
      )
      setOpen(false)
      setName('')
      setJdFile(null)
      navigate(`/admin/assessments/${data.slug}/sections#edit-sections`)
    } catch (requestError) {
      console.error('assessment_create_failed', requestError)
      setError(String(requestError?.message || 'Unable to create assessment.'))
      setCreatingAssessment(false)
    }
  }

  async function deleteAssessment() {
    if (!deleteTarget) return
    try {
      await api(`/api/admin/assessments/${deleteTarget.id}`, { method: 'DELETE' }, true)
      setDeleteTarget(null)
      load()
    } catch (requestError) {
      console.error('assessment_delete_failed', requestError)
      const message = String(requestError?.message || '')
      if (message.includes('Assessment not found')) {
        setAssessments((items) => items.filter((item) => item.id !== deleteTarget.id))
        setDeleteTarget(null)
        setError('Assessment already deleted.')
        return
      }
      setError(message || 'Unable to delete assessment.')
    }
  }

  function handleJdFileSelection(file) {
    setJdFile(file)
  }

  function handleJdDrop(event) {
    event.preventDefault()
    event.stopPropagation()
    setDragActive(false)
    handleJdFileSelection(event.dataTransfer.files?.[0] || null)
  }

  const filtered = assessments.filter((item) => item.name.toLowerCase().includes(query.toLowerCase()))

  return (
    <div>
      <TopNav />
      <main className="page">
        <div className="heading-row">
          <div>
            <p className="muted">AITS</p>
            <h2>Assessments</h2>
          </div>
          <button className="primary" onClick={() => setOpen(true)}>+ Create Assessment</button>
        </div>

        <div className="search-row">
          <input placeholder="Search assessments" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>

        {error && <p className="error">{error}</p>}

        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Candidates</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.id}>
                <td className="table-cell--clickable" onClick={() => navigate(`/admin/assessments/${item.slug}#overview`)}>{item.name}</td>
                <td className="table-cell--clickable" onClick={() => navigate(`/admin/assessments/${item.slug}#overview`)}>{item.candidate_count}</td>
                <td className="table-cell--clickable" onClick={() => navigate(`/admin/assessments/${item.slug}#overview`)}>{new Date(item.created_at).toLocaleDateString()}</td>
                <td className="table-actions">
                  <button
                    className="icon-action icon-action--danger"
                    type="button"
                    aria-label={`Delete ${item.name}`}
                    onClick={() => setDeleteTarget(item)}
                  >
                    <TrashIcon />
                  </button>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan="4">No assessments found.</td>
              </tr>
            )}
          </tbody>
        </table>
      </main>

      <Modal open={open} title="Create an assessment" onClose={() => setOpen(false)}>
        <form onSubmit={createAssessment} className="stack modal-body loading-overlay-host">
          <LoadingOverlay open={creatingAssessment} label="Creating assessment..." />
          <label>Name of your assessment</label>
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Engineering, Content Editor, Marketing"
          />
          <label>Upload Job Description (Optional)</label>
          <input
            ref={jdFileInputRef}
            className="assessment-jd-input"
            type="file"
            accept=".pdf,.doc,.docx,.txt"
            onChange={(event) => handleJdFileSelection(event.target.files?.[0] || null)}
          />
          <button
            type="button"
            className={`assessment-jd-dropzone ${dragActive ? 'assessment-jd-dropzone--active' : ''}`}
            onClick={() => jdFileInputRef.current?.click()}
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
            onDrop={handleJdDrop}
          >
            <strong>Drag and drop JD here</strong>
            <span>or click to browse PDF, DOC, DOCX, or TXT</span>
            {jdFile ? <small className="assessment-jd-filename">Selected file: {jdFile.name}</small> : null}
          </button>
          <button className="primary" type="submit" disabled={creatingAssessment}>Create Assessment</button>
        </form>
      </Modal>

      <Modal
        open={Boolean(deleteTarget)}
        title="Delete Assessment"
        onClose={() => setDeleteTarget(null)}
        disableBackdropClose
      >
        <div className="stack modal-body">
          <p>Delete {deleteTarget?.name}? Candidates will lose access permanently.</p>
          <div className="actions-row">
            <button className="ghost-btn" type="button" onClick={() => setDeleteTarget(null)}>No</button>
            <button className="primary" type="button" onClick={deleteAssessment}>Yes</button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
