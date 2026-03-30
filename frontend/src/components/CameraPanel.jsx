import { useEffect, useMemo, useRef, useState } from 'react'
import useProctoring from '../hooks/useProctoring'

const CAMERA_POSITION_STORAGE_KEY = 'exam_camera_panel_position'
const CAMERA_EDGE_GAP = 10

export default function CameraPanel({
  candidateId,
  onProctorUpdate,
  visiblePreview = true,
  enabled = true
}) {
  const proctor = useProctoring({ candidateId, visiblePreview, enabled })
  const panelRef = useRef(null)
  const [hasCustomPosition, setHasCustomPosition] = useState(false)
  const [position, setPosition] = useState(() => {
    if (typeof window === 'undefined') {
      return { x: 24, y: 92 }
    }
    try {
      const saved = window.localStorage.getItem(CAMERA_POSITION_STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        if (parsed?.custom && Number.isFinite(parsed?.x) && Number.isFinite(parsed?.y)) {
          return { x: Number(parsed.x), y: Number(parsed.y) }
        }
      }
    } catch {
      // ignore storage parse issues and fall back to default bottom-right
    }
    const assumedWidth = 300
    const assumedHeight = 220
    return {
      x: Math.max(8, window.innerWidth - assumedWidth - 20),
      y: Math.max(8, window.innerHeight - assumedHeight - 20),
    }
  })
  const [dragArmed, setDragArmed] = useState(false)
  const dragRef = useRef({
    active: false,
    pointerId: null,
    offsetX: 0,
    offsetY: 0
  })

  const panelClass = useMemo(
    () => `camera-panel camera-panel--floating ${dragArmed ? 'camera-panel--armed' : ''}`,
    [dragArmed]
  )

  useEffect(() => {
    if (typeof onProctorUpdate === 'function') {
      onProctorUpdate(proctor)
    }
  }, [
    onProctorUpdate,
    proctor.blocked,
    proctor.faceVisible,
    proctor.gadgetDetected,
    proctor.status,
    proctor.streamReady,
    proctor.faces,
    proctor.multipleFaces,
    proctor.mobileDetected
  ])

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(CAMERA_POSITION_STORAGE_KEY)
      if (!saved) return
      const parsed = JSON.parse(saved)
      if (parsed?.custom) {
        setHasCustomPosition(true)
      }
    } catch {
      // ignore storage parse issues
    }
  }, [])

  if (!visiblePreview) {
    return (
      <div className="hidden-proctoring">
        <video ref={proctor.videoRef} autoPlay muted playsInline className="hidden" />
        <canvas ref={proctor.canvasRef} className="hidden" />
      </div>
    )
  }

  function clampPosition(nextX, nextY) {
    const panel = panelRef.current
    const panelWidth = panel?.offsetWidth || 300
    const panelHeight = panel?.offsetHeight || 220
    const maxX = Math.max(CAMERA_EDGE_GAP, window.innerWidth - panelWidth - CAMERA_EDGE_GAP)
    const maxY = Math.max(CAMERA_EDGE_GAP, window.innerHeight - panelHeight - CAMERA_EDGE_GAP)
    return {
      x: Math.min(Math.max(CAMERA_EDGE_GAP, nextX), maxX),
      y: Math.min(Math.max(CAMERA_EDGE_GAP, nextY), maxY)
    }
  }

  function armDrag() {
    setDragArmed(true)
  }

  function onPointerDown(event) {
    if (!dragArmed || event.button !== 0) return
    const panel = panelRef.current
    if (!panel) return
    const rect = panel.getBoundingClientRect()
    dragRef.current = {
      active: true,
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top
    }
    panel.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event) {
    if (!dragRef.current.active || dragRef.current.pointerId !== event.pointerId) return
    const nextX = event.clientX - dragRef.current.offsetX
    const nextY = event.clientY - dragRef.current.offsetY
    setPosition(clampPosition(nextX, nextY))
  }

  function stopDragging(event) {
    if (dragRef.current.pointerId !== event.pointerId) return
    const wasDragging = dragRef.current.active
    dragRef.current.active = false
    dragRef.current.pointerId = null
    setDragArmed(false)
    if (wasDragging) {
      setHasCustomPosition(true)
    }
  }

  useEffect(() => {
    function handleResize() {
      setPosition((current) => clampPosition(current.x, current.y))
    }
    setPosition((current) => clampPosition(current.x, current.y))
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (!hasCustomPosition) return
    try {
      window.localStorage.setItem(CAMERA_POSITION_STORAGE_KEY, JSON.stringify({ ...position, custom: true }))
    } catch {
      // no-op if storage is not available
    }
  }, [position, hasCustomPosition])

  return (
    <aside
      ref={panelRef}
      className={panelClass}
      style={{ left: `${position.x}px`, top: `${position.y}px` }}
      onDoubleClick={armDrag}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={stopDragging}
      onPointerCancel={stopDragging}
      title="Double-click then drag to move"
    >
      <video ref={proctor.videoRef} autoPlay muted playsInline className="camera-view" />
      <canvas ref={proctor.canvasRef} className="hidden" />
    </aside>
  )
}
