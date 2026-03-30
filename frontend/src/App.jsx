import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import LoadingPulse from './components/LoadingPulse'
import AdminAuthPage from './pages/AdminAuthPage'
import AdminSignupPage from './pages/AdminSignupPage'
import AdminForgotPasswordPage from './pages/AdminForgotPasswordPage'
import AdminResetPasswordPage from './pages/AdminResetPasswordPage'
import AssessmentsPage from './pages/AssessmentsPage'
import AssessmentDetailPage from './pages/AssessmentDetailPage'
import AssessmentSectionsPage from './pages/AssessmentSectionsPage'
import McqEditPage from './pages/McqEditPage'
import VerbalEditPage from './pages/VerbalEditPage'
import VerbalAudioVideoPage from './pages/VerbalAudioVideoPage'
import VerbalSpeakingPage from './pages/VerbalSpeakingPage'
import VerbalWritingPage from './pages/VerbalWritingPage'
import VerbalFillBlanksPage from './pages/VerbalFillBlanksPage'
import CandidateInvitePage from './pages/CandidateInvitePage'
import CandidateProfileForm from './pages/CandidateProfileForm'
import CandidateDashboardPage from './pages/CandidateDashboardPage'
import SectionInstructionsPage from './pages/SectionInstructionsPage'
import McqExamPage from './pages/McqExamPage'
import CodingExamPage from './pages/CodingExamPage'
import VerbalExamPage from './pages/VerbalExamPage'
import CandidateReviewPage from './pages/CandidateReviewPage'
import CandidateCompletedPage from './pages/CandidateCompletedPage'
import InterviewPage from './pages/InterviewPage'

function AdminRoute({ children }) {
  const token = localStorage.getItem('admin_token') || sessionStorage.getItem('admin_token')
  if (!token) return <Navigate to="/admin/auth" replace />
  return children
}

function LegacyVerbalRedirect({ topic = '' }) {
  const { assessmentSlug, sectionKey } = useParams()
  const suffix = topic ? `/${topic}` : ''
  return <Navigate to={`/admin/a/${assessmentSlug}/s/${sectionKey}/v${suffix}`} replace />
}

export default function App() {
  const [reloadReady, setReloadReady] = useState(false)

  useEffect(() => {
    const navEntry = performance.getEntriesByType?.('navigation')?.[0]
    const legacyNav = performance.navigation
    const shouldDelay =
      navEntry?.type === 'reload' ||
      legacyNav?.type === 1

    if (!shouldDelay) {
      setReloadReady(true)
      return undefined
    }

    const timer = setTimeout(() => {
      setReloadReady(true)
    }, 1500)

    return () => {
      clearTimeout(timer)
    }
  }, [])

  if (!reloadReady) {
    return <LoadingPulse fullPage />
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/admin/assessments" replace />} />
      <Route path="/admin/auth" element={<AdminAuthPage />} />
      <Route path="/admin/signup" element={<AdminSignupPage />} />
      <Route path="/admin/forgot-password" element={<AdminForgotPasswordPage />} />
      <Route path="/admin/reset-password" element={<AdminResetPasswordPage />} />
      <Route
        path="/admin/assessments"
        element={
          <AdminRoute>
            <AssessmentsPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/assessments/:assessmentSlug/sections"
        element={
          <AdminRoute>
            <AssessmentSectionsPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/assessments/:assessmentSlug/sections/:sectionKey/mcq-edit"
        element={
          <AdminRoute>
            <McqEditPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/a/:assessmentSlug/s/:sectionKey/v"
        element={
          <AdminRoute>
            <VerbalEditPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/a/:assessmentSlug/s/:sectionKey/v/audio-video"
        element={
          <AdminRoute>
            <VerbalAudioVideoPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/a/:assessmentSlug/s/:sectionKey/v/speaking"
        element={
          <AdminRoute>
            <VerbalSpeakingPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/a/:assessmentSlug/s/:sectionKey/v/writing"
        element={
          <AdminRoute>
            <VerbalWritingPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/a/:assessmentSlug/s/:sectionKey/v/fill-in-the-blanks"
        element={
          <AdminRoute>
            <VerbalFillBlanksPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/assessments/:assessmentSlug/sections/:sectionKey/verbal-edit"
        element={<LegacyVerbalRedirect />}
      />
      <Route
        path="/admin/assessments/:assessmentSlug/sections/:sectionKey/verbal-edit/audio-video"
        element={<LegacyVerbalRedirect topic="audio-video" />}
      />
      <Route
        path="/admin/assessments/:assessmentSlug/sections/:sectionKey/verbal-edit/speaking"
        element={<LegacyVerbalRedirect topic="speaking" />}
      />
      <Route
        path="/admin/assessments/:assessmentSlug/sections/:sectionKey/verbal-edit/writing"
        element={<LegacyVerbalRedirect topic="writing" />}
      />
      <Route
        path="/admin/assessments/:assessmentSlug/sections/:sectionKey/verbal-edit/fill-in-the-blanks"
        element={<LegacyVerbalRedirect topic="fill-in-the-blanks" />}
      />
      <Route
        path="/admin/assessments/:assessmentSlug"
        element={
          <AdminRoute>
            <AssessmentDetailPage />
          </AdminRoute>
        }
      />

      <Route path="/candidate/invite" element={<CandidateInvitePage />} />
      <Route path="/candidate/invite/:token" element={<CandidateInvitePage />} />
      <Route path="/candidate/:candidateId/profile" element={<CandidateProfileForm />} />
      <Route path="/candidate/:candidateId/dashboard" element={<CandidateDashboardPage />} />
      <Route path="/candidate/:candidateId/review" element={<CandidateReviewPage />} />
      <Route path="/candidate/:candidateId/completed" element={<CandidateCompletedPage />} />
      <Route path="/candidate/:candidateId/sections/:sectionId/instructions" element={<SectionInstructionsPage />} />
      <Route path="/candidate/:candidateId/sections/:sectionId/mcq" element={<McqExamPage />} />
      <Route path="/candidate/:candidateId/sections/:sectionId/verbal" element={<VerbalExamPage />} />
      <Route path="/candidate/:candidateId/sections/:sectionId/coding" element={<CodingExamPage />} />
      <Route path="/interview/:meetingId" element={<InterviewPage />} />
    </Routes>
  )
}
