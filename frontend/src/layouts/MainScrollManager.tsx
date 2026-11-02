import { useEffect, useRef, type RefObject } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'

// MAIN is the scroll viewport. Keep positions in memory for this mounted shell,
// never in session storage and never by modifying the route's mounting key.
export default function MainScrollManager({ mainRef }: { mainRef: RefObject<HTMLElement | null> }) {
  const { key, pathname, search, hash } = useLocation()
  const navigationType = useNavigationType()
  const positions = useRef(new Map<string, { top: number; left: number }>())
  useEffect(() => {
    const main = mainRef.current
    if (!main) return
    const historyPositions = positions.current
    const saved = navigationType === 'POP' ? historyPositions.get(key) : undefined
    let waiting = Boolean(hash || saved)
    let lastPosition = saved ?? { top: 0, left: 0 }
    const storePosition = () => {
      historyPositions.set(key, lastPosition)
      if (historyPositions.size > 50) historyPositions.delete(historyPositions.keys().next().value!)
    }
    const remember = () => {
      lastPosition = { top: main.scrollTop, left: main.scrollLeft }
      storePosition()
    }
    const observer = new MutationObserver(() => restore())
    function stop() { waiting = false; observer.disconnect() }
    const restore = () => {
      if (!waiting) return
      if (hash) {
        let id = hash.slice(1)
        try { id = decodeURIComponent(id) } catch { /* Preserve literal fragment. */ }
        const target = document.getElementById(id)
        if (!target || (target !== main && !main.contains(target))) return
        target.scrollIntoView({ block: 'start', behavior: 'instant' })
        stop()
      } else if (saved) {
        // Async pages first render a loading state. Wait for sufficient content
        // instead of discarding a backward-navigation position at height zero.
        main.scrollTo({ top: saved.top, left: saved.left, behavior: 'instant' })
        if (main.scrollHeight - main.clientHeight >= saved.top) stop()
      }
    }
    const manualScroll = () => stop()
    const keyboardScroll = (event: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) stop()
    }
    if (waiting) { observer.observe(main, { childList: true, subtree: true, characterData: true }); restore() }
    else main.scrollTo({ top: 0, left: 0, behavior: 'instant' })
    main.addEventListener('scroll', remember, { passive: true })
    main.addEventListener('wheel', manualScroll, { passive: true })
    main.addEventListener('touchstart', manualScroll, { passive: true })
    main.addEventListener('pointerdown', manualScroll, { passive: true })
    main.addEventListener('keydown', keyboardScroll)
    main.addEventListener('focusin', manualScroll)
    main.addEventListener('load', restore, true)
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
      const focused = document.activeElement
      if (!(focused instanceof HTMLElement) || focused === main || !main.contains(focused)) return
      const bounds = main.getBoundingClientRect(), field = focused.getBoundingClientRect()
      if (field.top < bounds.top || field.bottom > bounds.bottom) {
        focused.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' })
      }
    })
    resizeObserver?.observe(main)
    return () => {
      // React may already have replaced a long page with a short loading state.
      // Keep the last scroll event, not the now-clamped DOM position.
      storePosition(); observer.disconnect(); resizeObserver?.disconnect()
      main.removeEventListener('scroll', remember)
      main.removeEventListener('wheel', manualScroll)
      main.removeEventListener('touchstart', manualScroll)
      main.removeEventListener('pointerdown', manualScroll)
      main.removeEventListener('keydown', keyboardScroll)
      main.removeEventListener('focusin', manualScroll)
      main.removeEventListener('load', restore, true)
    }
  }, [key, pathname, search, hash, navigationType, mainRef])
  return null
}
