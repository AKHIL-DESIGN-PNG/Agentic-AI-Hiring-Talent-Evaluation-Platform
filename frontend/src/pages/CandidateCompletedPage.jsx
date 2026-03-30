import { useLocation } from 'react-router-dom'

export default function CandidateCompletedPage() {
  const location = useLocation()
  const timedOut = Boolean(location.state?.timedOut)

  return (
    <main className="candidate-page candidate-page--centered">
      <section className="candidate-card candidate-card--narrow">
        <p className="eyebrow">Assessment Submitted</p>
        <h1>Thank you for taking assessment.</h1>
        <p className="muted">
          {timedOut
            ? 'If you have any queries mail us at balajichanda797@gmail.com.'
            : 'Your responses have been recorded successfully.'}
        </p>
      </section>
    </main>
  )
}
