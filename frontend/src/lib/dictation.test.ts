import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createDictation, dictationBlockedReason, dictationSupported } from './dictation'

class FakeRec {
  static instances: FakeRec[] = []
  continuous = false; interimResults = false; lang = ''
  onresult: ((e: any) => void) | null = null; onerror: ((e: any) => void) | null = null; onend: (() => void) | null = null
  started = 0
  constructor() { FakeRec.instances.push(this) }
  start() { this.started += 1 }
  stop() { this.onend?.() }
  abort() { this.onend?.() }
}

const handlers = () => ({ onFinal: vi.fn(), onInterim: vi.fn(), onError: vi.fn(), onEnd: vi.fn() })

beforeEach(() => {
  vi.useFakeTimers()
  FakeRec.instances = []
  ;(window as any).webkitSpeechRecognition = FakeRec
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => { vi.useRealTimers(); delete (window as any).webkitSpeechRecognition; vi.restoreAllMocks() })

describe('dictation', () => {
  it('keeps listening through a quiet spell instead of switching itself off', () => {
    const h = handlers()
    createDictation(h).start()
    FakeRec.instances[0].onerror?.({ error: 'no-speech' })
    FakeRec.instances[0].onend?.()
    vi.advanceTimersByTime(200)
    expect(h.onError).not.toHaveBeenCalled()
    expect(FakeRec.instances).toHaveLength(2) // a fresh session took over
    expect(FakeRec.instances[1].started).toBe(1)
  })

  it('gives up with a clear message after three silent sessions in a row', () => {
    const h = handlers()
    createDictation(h).start()
    for (let i = 0; i < 3; i++) {
      const r = FakeRec.instances[FakeRec.instances.length - 1]
      r.onerror?.({ error: 'no-speech' })
      r.onend?.()
      vi.advanceTimersByTime(200)
    }
    expect(h.onError).toHaveBeenCalledWith('no-speech', undefined)
  })

  it('does not loop forever when sessions end the instant they start', () => {
    const h = handlers()
    createDictation(h).start()
    for (let i = 0; i < 3; i++) {
      FakeRec.instances[FakeRec.instances.length - 1].onend?.()
      vi.advanceTimersByTime(200)
    }
    expect(h.onError).toHaveBeenCalledWith('unknown', 'ended-immediately')
  })

  it('resets the quiet counter once something is heard and passes final and interim text on', () => {
    const h = handlers()
    createDictation(h).start()
    const r = FakeRec.instances[0]
    r.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: ' hello there ' } }, { isFinal: false, 0: { transcript: 'and then' } }] })
    expect(h.onFinal).toHaveBeenCalledWith('hello there')
    expect(h.onInterim).toHaveBeenCalledWith('and then')
    r.onend?.()
    vi.advanceTimersByTime(200)
    expect(FakeRec.instances).toHaveLength(2)
  })

  it('reports permission and network failures with the browser code and stops', () => {
    const h = handlers()
    createDictation(h).start()
    FakeRec.instances[0].onerror?.({ error: 'not-allowed' })
    FakeRec.instances[0].onend?.()
    vi.advanceTimersByTime(500)
    expect(h.onError).toHaveBeenCalledWith('not-allowed', 'not-allowed')
    expect(FakeRec.instances).toHaveLength(1) // no restart after a fatal error
  })

  it('treats app-embedded browsers and Brave as unable to dictate', () => {
    const ua = vi.spyOn(navigator, 'userAgent', 'get')
    ua.mockReturnValue('Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Claude/5.11 Chrome/156 Safari/537.36')
    expect(dictationBlockedReason()).toBe('embedded')
    expect(dictationSupported()).toBe(false)
    ua.mockReturnValue('Mozilla/5.0 (Macintosh) Chrome/150 Safari/537.36')
    expect(dictationBlockedReason()).toBeNull()
    expect(dictationSupported()).toBe(true)
  })
})
