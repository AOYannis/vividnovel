import { useCallback, useRef } from 'react'
import { streamSequence } from '../api/client'
import { useGameStore } from '../stores/gameStore'

export function useStoryStream() {
  const store = useGameStore()
  const abortRef = useRef<AbortController | null>(null)

  const startSequence = useCallback(
    async (
      choiceId?: string,
      choiceText?: string,
      choiceTargetLocationId?: string | null,
      choiceTargetAdvanceTime?: boolean | null,
      choiceTargetCompanions?: string[] | null,
    ) => {
      if (!store.sessionId) return

      store.startStreaming()

      try {
        await streamSequence(
          store.sessionId,
          choiceId,
          choiceText,
          (event) => {
            store.handleSSEEvent(event)
          },
          choiceTargetLocationId ?? null,
          choiceTargetAdvanceTime ?? null,
          choiceTargetCompanions ?? null,
        )
      } catch (err) {
        console.error('Stream error:', err)
        store.handleSSEEvent({
          type: 'error',
          message: err instanceof Error ? err.message : 'Stream failed',
        })
      }
    },
    [store.sessionId],
  )

  const abort = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { startSequence, abort }
}
