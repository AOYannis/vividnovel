import { useState, useRef, useCallback, type ReactNode } from 'react'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  children: ReactNode
  initialHeight?: string  // e.g. '60vh'
}

export default function BottomSheet({ open, onClose, children, initialHeight = '60vh' }: BottomSheetProps) {
  const [dragOffset, setDragOffset] = useState(0)
  const startY = useRef(0)
  const dragging = useRef(false)

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    startY.current = e.clientY
    dragging.current = true
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }, [])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragging.current) return
    const dy = e.clientY - startY.current
    setDragOffset(Math.max(0, dy))  // only allow dragging down
  }, [])

  const onPointerUp = useCallback(() => {
    dragging.current = false
    if (dragOffset > 100) {
      onClose()
    }
    setDragOffset(0)
  }, [dragOffset, onClose])

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 transition-opacity"
        onClick={onClose}
      />
      {/* Sheet */}
      <div
        className="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl glass flex flex-col overflow-hidden"
        style={{
          height: initialHeight,
          transform: `translateY(${dragOffset}px)`,
          transition: dragging.current ? 'none' : 'transform 0.3s ease-out',
        }}
      >
        {/* Drag handle */}
        <div
          className="shrink-0 flex items-center justify-center py-3 cursor-grab active:cursor-grabbing touch-none"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <div className="w-10 h-1 rounded-full bg-neutral-600" />
        </div>
        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {children}
        </div>
      </div>
    </>
  )
}
