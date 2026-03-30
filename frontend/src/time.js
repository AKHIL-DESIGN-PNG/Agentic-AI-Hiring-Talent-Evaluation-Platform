export function parseServerDate(value) {
  if (!value) return null
  if (value instanceof Date) return value
  if (typeof value !== 'string') return null

  // Backend sends UTC-naive string (e.g. 2026-03-12T16:11:27.067216).
  // Treat it explicitly as UTC to avoid local timezone drift.
  const normalized = /Z$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return null
  return date
}

export function secondsLeft(deadline) {
  const date = parseServerDate(deadline)
  if (!date) return null
  return Math.max(0, Math.floor((date.getTime() - Date.now()) / 1000))
}

