import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import TopNav from '../components/TopNav'

export default function InterviewPage() {
  const { meetingId } = useParams()

  const normalizedMeetingId = useMemo(() => {
    const raw = (meetingId || '').trim()
    if (!raw) return ''
    return raw.replace(/[^a-zA-Z0-9-_]/g, '')
  }, [meetingId])

  const jitsiUrl = normalizedMeetingId
    ? `https://meet.jit.si/${normalizedMeetingId}#config.prejoinPageEnabled=true`
    : ''

  if (!normalizedMeetingId) {
    return (
      <div>
        <TopNav />
        <main className="interview-shell">
          <div className="panel interview-shell__header">
            <h2>Invalid Interview Link</h2>
            <p className="muted">The meeting ID is missing or invalid.</p>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div>
      <TopNav />

      <main className="interview-page">
        <div className="interview-header">
          <div>
            <h2>Interview Room</h2>
            <p>Meeting ID: <strong>{normalizedMeetingId}</strong></p>
          </div>

          <a
            className="join-btn"
            href={jitsiUrl}
            target="_blank"
            rel="noreferrer"
          >
            Open Fullscreen
          </a>
        </div>

        <div className="interview-video-wrapper">
          <iframe
            title="Interview Meeting"
            src={jitsiUrl}
            allow="camera; microphone; fullscreen; display-capture"
          />
        </div>
      </main>
    </div>
  )
}
