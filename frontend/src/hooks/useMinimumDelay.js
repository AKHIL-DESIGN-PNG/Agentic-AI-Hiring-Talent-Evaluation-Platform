import { useEffect, useState } from 'react'

export default function useMinimumDelay(ready, delayMs = 0) {
  const [displayReady, setDisplayReady] = useState(false)

  useEffect(() => {
    if (!ready) {
      setDisplayReady(false)
      return undefined
    }
    const timer = setTimeout(() => setDisplayReady(true), delayMs)
    return () => clearTimeout(timer)
  }, [ready, delayMs])

  return displayReady
}
