const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export const googleClientId =
  import.meta.env.VITE_GOOGLE_CLIENT_ID ||
  '1000371775549-m8q7ll6e67uq63a1u23cveu11u04uc3r.apps.googleusercontent.com'

export function getAdminToken() {
  return localStorage.getItem('admin_token') || sessionStorage.getItem('admin_token')
}

function handleExpiredAdminSession() {
  localStorage.removeItem('admin_token')
  localStorage.removeItem('admin_profile')
  sessionStorage.removeItem('admin_token')
  sessionStorage.removeItem('admin_profile')
  if (window.location.pathname !== '/admin/auth') {
    window.location.assign('/admin/auth')
  }
}

function sanitizeMessage(message) {
  if (!message) return 'Request failed'
  const lowered = String(message).toLowerCase()

  if (lowered.includes('failed to fetch') || lowered.includes('networkerror')) {
    return 'Backend is unreachable. Check that the API server is running and CORS is configured.'
  }

  if (
    lowered.includes('proctoring_') ||
    lowered.includes('traceback') ||
    lowered.includes('site-packages') ||
    lowered.includes('python=') ||
    lowered.includes('google.protobuf')
  ) {
    return 'Security monitoring is unavailable.'
  }

  return String(message)
}

export async function api(path, options = {}, useAuth = false) {

  const headers = {
    ...(options.headers || {})
  }

  if (useAuth) {
    const token = getAdminToken()
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
  }

  // Only add JSON header if body is NOT FormData
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers
    })
  } catch (error) {
    throw new Error(sanitizeMessage(error?.message || 'Failed to fetch'))
  }

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: 'Request failed' }))
    if (useAuth && response.status === 401) {
      handleExpiredAdminSession()
      throw new Error('Session expired. Please log in again.')
    }

    throw new Error(sanitizeMessage(error.detail || 'Request failed'))
  }

  return response.json()
}

export { API_BASE, sanitizeMessage }
