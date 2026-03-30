import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../api'

function friendlyMessage(status) {
  switch (status) {
    case 'face_detected':
      return 'Face detected.'
    case 'mobile_detected':
      return 'Mobile phone detected.'
    case 'multiple_faces':
      return 'Multiple faces detected.'
    case 'no_face':
      return 'Face not detected.'
    case 'camera_denied':
      return 'Camera access is required.'
    case 'unavailable':
    case 'error':
      return 'Security monitoring is unavailable.'
    default:
      return 'Security monitoring is starting.'
  }
}

export default function useProctoring({
  candidateId,
  visiblePreview = false,
  enabled = true,
  pollInterval = 2000
}) {
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const timerRef = useRef(null)
  const busyRef = useRef(false)
  const requestRef = useRef(null)
  const consecutiveErrorsRef = useRef(0)
  const [state, setState] = useState({
    streamReady: false,
    faceVisible: false,
    gadgetDetected: false,
    mobileDetected: false,
    multipleFaces: false,
    faces: 0,
    noFaceDurationSec: 0,
    blocked: true,
    status: 'initializing',
    message: friendlyMessage('initializing')
  })

  useEffect(() => {
    if (!enabled) return undefined
    let active = true

    function clearTimer() {
      if (timerRef.current) {
        window.clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }

    function scheduleNext(delay = pollInterval) {
      clearTimer()
      if (!active) return
      timerRef.current = window.setTimeout(runCheck, delay)
    }

    async function runCheck() {
      if (!active || busyRef.current || !videoRef.current || !canvasRef.current) {
        scheduleNext()
        return
      }

      if (document.visibilityState !== 'visible' || !navigator.onLine) {
        scheduleNext(Math.max(pollInterval, 2200))
        return
      }

      const video = videoRef.current
      const canvas = canvasRef.current
      if (!video.videoWidth || !video.videoHeight || video.readyState < 2) {
        scheduleNext(700)
        return
      }

      busyRef.current = true
      const targetWidth = 640
      const targetHeight = Math.max(360, Math.round((video.videoHeight / video.videoWidth) * targetWidth))
      canvas.width = targetWidth
      canvas.height = targetHeight
      const ctx = canvas.getContext('2d', { alpha: false, willReadFrequently: false })
      if (!ctx) {
        busyRef.current = false
        scheduleNext()
        return
      }

      ctx.drawImage(video, 0, 0, targetWidth, targetHeight)
      const image = canvas.toDataURL('image/jpeg', 0.68)
      const controller = new AbortController()
      requestRef.current = controller

      try {
        const response = await fetch(`${API_BASE}/api/proctor/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image, candidate_id: candidateId }),
          signal: controller.signal
        })
        const data = await response.json()
        const faces = Number.isFinite(data?.faces) ? Math.max(0, Number(data.faces)) : 0
        const multipleFaces = Boolean(data?.multiple_faces)
        const mobileDetected = Boolean(data?.mobile)
        const noFaceDurationSec = faces === 0 ? pollInterval / 1000 : 0
        let status = 'face_detected'
        if (mobileDetected) {
          status = 'mobile_detected'
        } else if (multipleFaces) {
          status = 'multiple_faces'
        } else if (faces === 0) {
          status = 'no_face'
        }

        const blocked = mobileDetected || multipleFaces || faces === 0
        consecutiveErrorsRef.current = 0
        setState({
          streamReady: true,
          faceVisible: faces > 0,
          gadgetDetected: mobileDetected,
          mobileDetected,
          multipleFaces,
          faces,
          noFaceDurationSec,
          blocked,
          status,
          message: friendlyMessage(status)
        })
        scheduleNext()
      } catch (error) {
        if (error?.name !== 'AbortError') {
          console.error('proctoring_poll_failed', error)
          consecutiveErrorsRef.current += 1
          setState((current) => ({
            ...current,
            streamReady: true,
            blocked: consecutiveErrorsRef.current >= 3,
            status: consecutiveErrorsRef.current >= 3 ? 'error' : current.status,
            message: consecutiveErrorsRef.current >= 3 ? friendlyMessage('error') : current.message
          }))
        }
        scheduleNext(Math.min(5000, pollInterval + consecutiveErrorsRef.current * 900))
      } finally {
        requestRef.current = null
        busyRef.current = false
      }
    }

    async function boot() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: 'user',
            width: { ideal: visiblePreview ? 960 : 640, max: 1280 },
            height: { ideal: visiblePreview ? 540 : 360, max: 720 },
            frameRate: { ideal: 15, max: 24 }
          },
          audio: false
        })
        if (!active) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }

        setState((current) => ({
          ...current,
          streamReady: true,
          blocked: true,
          status: 'initializing',
          message: friendlyMessage('initializing')
        }))

        scheduleNext(450)
      } catch (error) {
        console.error('camera_boot_failed', error)
        setState({
          streamReady: false,
          faceVisible: false,
          gadgetDetected: false,
          mobileDetected: false,
          multipleFaces: false,
          faces: 0,
          noFaceDurationSec: 0,
          blocked: true,
          status: 'camera_denied',
          message: friendlyMessage('camera_denied')
        })
      }
    }

    boot()

    return () => {
      active = false
      clearTimer()
      if (requestRef.current) {
        requestRef.current.abort()
        requestRef.current = null
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
        streamRef.current = null
      }
    }
  }, [candidateId, enabled, pollInterval, visiblePreview])

  return {
    ...state,
    videoRef,
    canvasRef,
    visiblePreview
  }
}
