import { useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE } from '../api'

function getNetworkState() {
  const online = navigator.onLine
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection
  if (!online) {
    return { tone: 'offline', label: 'offline', bars: 0, strengthLabel: '0/4' }
  }
  const slowTypes = ['slow-2g', '2g', '3g']
  if (connection && (slowTypes.includes(connection.effectiveType) || connection.saveData)) {
    const effective = String(connection.effectiveType || '').toLowerCase()
    const bars = effective === 'slow-2g' ? 1 : effective === '2g' ? 1 : 2
    return { tone: 'warning', label: 'connected', bars, strengthLabel: `${bars}/4` }
  }
  return { tone: 'good', label: 'connected', bars: 4, strengthLabel: '4/4' }
}

export default function useExamSecurity({ candidateId, sectionId, enabled = true, onViolationLimit, violationLimit = 10 }) {
  const [warning, setWarning] = useState(null)
  const [violations, setViolations] = useState(0)
  const [fullscreenActive, setFullscreenActive] = useState(Boolean(document.fullscreenElement))
  const [tabHidden, setTabHidden] = useState(document.visibilityState !== 'visible')
  const [networkState, setNetworkState] = useState(getNetworkState())
  const [captureDeviceBlocked, setCaptureDeviceBlocked] = useState(false)
  const warningTimesRef = useRef({})

  function logEvent(event, detail = '') {
    fetch(`${API_BASE}/api/proctoring/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId, section_id: sectionId, event, detail })
    }).catch(() => {})
  }

  function raiseWarning(message, options = {}) {
    const { increment = true, event = 'warning', cooldownMs = 2500 } = options
    const now = Date.now()
    if (warningTimesRef.current[event] && now - warningTimesRef.current[event] < cooldownMs) {
      return
    }
    warningTimesRef.current[event] = now
    setWarning({ id: `${event}-${now}`, message, event })
    logEvent(event, message)
    if (increment) {
      setViolations((current) => current + 1)
    }
  }

  async function requestFullscreen() {
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen()
      }
    } catch (error) {
      console.error('fullscreen_request_failed', error)
    }
  }

  useEffect(() => {
    if (!enabled) return undefined
    let securityInterval = null

    function syncNetwork() {
      setNetworkState(getNetworkState())
    }

    function scanCaptureDevices() {
      return navigator.mediaDevices?.enumerateDevices?.()
        .then((devices) => {
          const suspiciousTerms = [
            'obs',
            'virtual',
            'manycam',
            'snap camera',
            'droidcam',
            'zoom',
            'meet',
            'teams',
            'xsplit',
            'vmix',
            'screen capture',
            'screen share'
          ]
          const blocked = devices.some((device) => {
            const label = String(device.label || '').toLowerCase()
            return suspiciousTerms.some((term) => label.includes(term))
          })
          setCaptureDeviceBlocked(blocked)
          if (blocked) {
            raiseWarning('Close Zoom/Meet/screen-sharing or virtual camera apps to continue.', {
              event: 'background_capture',
              cooldownMs: 3500
            })
          }
        })
        .catch((error) => {
          console.error('device_enumeration_failed', error)
        })
    }

    function handleFullscreen() {
      const active = Boolean(document.fullscreenElement)
      setFullscreenActive(active)
      if (active) {
        setWarning((current) =>
          current?.event === 'fullscreen_exit' || current?.event === 'fullscreen_required' ? null : current
        )
      } else {
        const now = Date.now()
        warningTimesRef.current.fullscreen_exit = now
        setWarning({
          id: `fullscreen_exit-${now}`,
          message: 'Go back to fullscreen to continue the assessment.',
          event: 'fullscreen_exit'
        })
        logEvent('fullscreen_exit', 'Go back to fullscreen to continue the assessment.')
        setViolations((current) => current + 1)
      }
    }

    function handleVisibility() {
      if (document.hidden) {
        setTabHidden(true)
        raiseWarning('To continue the exam go to fullscreen.', {
          event: 'tab_switch',
          cooldownMs: 0
        })
        return
      }
      setTabHidden(false)
    }

    function handleWindowBlur() {
      if (document.visibilityState === 'visible') {
        setTabHidden(true)
        raiseWarning('To continue the exam go to fullscreen.', {
          event: 'tab_switch',
          cooldownMs: 0
        })
      }
    }

    function handleWindowFocus() {
      if (document.visibilityState === 'visible') {
        setTabHidden(false)
      }
    }

    function handleContextMenu(event) {
      event.preventDefault()
      raiseWarning('Right-click is disabled during the assessment.', {
        event: 'right_click'
      })
    }

    function handleKeyDown(event) {
      const key = event.key.toLowerCase()
      const screenshotCombo =
        key === 'printscreen' ||
        (event.metaKey && event.shiftKey && ['3', '4', '5'].includes(key))
      const blockedCombo =
        screenshotCombo ||
        (event.ctrlKey && ['c', 'v', 'x', 'a'].includes(key)) ||
        key === 'f12' ||
        (event.ctrlKey && event.shiftKey && ['i', 'j', 'c'].includes(key))
      if (!blockedCombo) return
      event.preventDefault()
      raiseWarning(
        screenshotCombo
          ? 'Screenshots are blocked during the assessment.'
          : 'This keyboard shortcut is disabled during the assessment.',
        {
          event: screenshotCombo ? 'screenshot_attempt' : 'blocked_shortcut'
        }
      )
    }

    function handleBeforeUnload(event) {
      event.preventDefault()
      event.returnValue = ''
    }

    function blockClipboard(event) {
      event.preventDefault()
      raiseWarning('Copy and paste are disabled during the assessment.', {
        event: 'clipboard_blocked'
      })
    }

    document.addEventListener('fullscreenchange', handleFullscreen)
    document.addEventListener('visibilitychange', handleVisibility)
    document.addEventListener('contextmenu', handleContextMenu)
    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('copy', blockClipboard)
    document.addEventListener('cut', blockClipboard)
    document.addEventListener('paste', blockClipboard)
    window.addEventListener('beforeunload', handleBeforeUnload)
    window.addEventListener('blur', handleWindowBlur)
    window.addEventListener('focus', handleWindowFocus)
    window.addEventListener('online', syncNetwork)
    window.addEventListener('offline', syncNetwork)

    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection
    connection?.addEventListener?.('change', syncNetwork)

    scanCaptureDevices()
    securityInterval = window.setInterval(() => {
      if (!document.fullscreenElement) {
        raiseWarning('Go back to fullscreen to continue the assessment.', {
          increment: false,
          event: 'fullscreen_required',
          cooldownMs: 2200
        })
      }
      scanCaptureDevices()
    }, 2200)

    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreen)
      document.removeEventListener('visibilitychange', handleVisibility)
      document.removeEventListener('contextmenu', handleContextMenu)
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('copy', blockClipboard)
      document.removeEventListener('cut', blockClipboard)
      document.removeEventListener('paste', blockClipboard)
      window.removeEventListener('beforeunload', handleBeforeUnload)
      window.removeEventListener('blur', handleWindowBlur)
      window.removeEventListener('focus', handleWindowFocus)
      window.removeEventListener('online', syncNetwork)
      window.removeEventListener('offline', syncNetwork)
      connection?.removeEventListener?.('change', syncNetwork)
      if (securityInterval) {
        window.clearInterval(securityInterval)
      }
    }
  }, [candidateId, enabled, sectionId])

  useEffect(() => {
    if (!enabled) return
    if (violations > violationLimit && typeof onViolationLimit === 'function') {
      onViolationLimit()
    }
  }, [enabled, onViolationLimit, violationLimit, violations])

  const headerNetwork = useMemo(
    () => ({
      barClass:
        networkState.tone === 'good'
          ? 'network-signal network-signal--good'
          : networkState.tone === 'warning'
            ? 'network-signal network-signal--warning'
            : 'network-signal network-signal--offline',
      label: networkState.label,
      bars: Array.from({ length: 4 }, (_, index) => index < (networkState.bars || 0)),
      strengthLabel: networkState.strengthLabel || '0/4'
    }),
    [networkState]
  )

  return {
    warning,
    dismissWarning: () => setWarning(null),
    raiseWarning,
    violations,
    fullscreenActive,
    tabHidden,
    requestFullscreen,
    networkState: headerNetwork,
    securityLocked: enabled && (!fullscreenActive || tabHidden || captureDeviceBlocked)
  }
}
