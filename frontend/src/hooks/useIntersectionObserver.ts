import { useEffect, useRef, useCallback } from 'react'

export function useSceneObserver(onSceneChange: (index: number) => void) {
  const containerRef = useRef<HTMLDivElement>(null)
  const sceneRefs = useRef<Map<number, HTMLDivElement>>(new Map())

  const setSceneRef = useCallback((index: number, el: HTMLDivElement | null) => {
    if (el) sceneRefs.current.set(index, el)
    else sceneRefs.current.delete(index)
  }, [])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
            const index = Number(entry.target.getAttribute('data-scene-index'))
            if (!isNaN(index)) onSceneChange(index)
          }
        }
      },
      { threshold: 0.5 }
    )

    sceneRefs.current.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [onSceneChange])

  return { containerRef, setSceneRef, sceneRefs }
}
