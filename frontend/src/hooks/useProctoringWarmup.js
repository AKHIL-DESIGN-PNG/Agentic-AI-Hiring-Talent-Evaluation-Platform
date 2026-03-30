import { useEffect } from 'react'
import { API_BASE } from '../api'

export default function useProctoringWarmup(enabled = true) {
  useEffect(() => {
    if (!enabled) return undefined
    let active = true
    let retryTimer = null
    let retried = false

    async function warm() {
      try {
        const response = await fetch(`${API_BASE}/api/proctoring/warmup`)
        const data = await response.json()
        if (!active) return
        if (data?.status !== 'ready' && !retried) {
          retried = true
          retryTimer = window.setTimeout(warm, 1200)
        }
      } catch (error) {
        console.error('proctoring_warmup_failed', error)
        if (active && !retried) {
          retried = true
          retryTimer = window.setTimeout(warm, 1800)
        }
      }
    }

    warm()

    return () => {
      active = false
      if (retryTimer) {
        window.clearTimeout(retryTimer)
      }
    }
  }, [enabled])
}
