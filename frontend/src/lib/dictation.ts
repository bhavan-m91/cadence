/** Web Speech API wrapper (FR-015). Live interim text, pause/resume, and a clear reason when it cannot run. */
type Rec = {
  continuous: boolean; interimResults: boolean; lang: string
  start(): void; stop(): void; abort(): void
  onresult: ((e: any) => void) | null; onerror: ((e: any) => void) | null; onend: (() => void) | null
}

const Ctor = (): (new () => Rec) | undefined => (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition

export const dictationSupported = () => typeof window !== 'undefined' && !!Ctor()

export type DictationError = 'not-allowed' | 'no-speech' | 'audio-capture' | 'network' | 'unsupported' | 'unknown'

export interface Dictation {
  start(): void
  /** Stop for good (the user pressed stop). */
  stop(): void
  /** Stop recognising but keep the session so `start()` resumes. */
  abort(): void
}

interface Handlers {
  lang?: string
  onFinal: (text: string) => void
  onInterim: (text: string) => void
  onError: (e: DictationError) => void
  onEnd: () => void
}

export function createDictation(h: Handlers): Dictation {
  const C = Ctor()
  let rec: Rec | null = null
  let wantRunning = false

  function build(): Rec {
    const r = new C!()
    r.continuous = true
    r.interimResults = true
    r.lang = h.lang ?? navigator.language ?? 'en-IN'
    r.onresult = (e: any) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]
        if (res.isFinal) h.onFinal(res[0].transcript.trim())
        else interim += res[0].transcript
      }
      h.onInterim(interim)
    }
    r.onerror = (e: any) => {
      const code = e?.error as string
      if (code === 'aborted') return
      wantRunning = false
      h.onError((['not-allowed', 'service-not-allowed'].includes(code) ? 'not-allowed' : code === 'no-speech' ? 'no-speech' : code === 'audio-capture' ? 'audio-capture' : code === 'network' ? 'network' : 'unknown') as DictationError)
    }
    // Chrome ends continuous recognition after a silence; restart while the person still wants to talk.
    r.onend = () => {
      if (wantRunning) {
        try { r.start() } catch { wantRunning = false; h.onEnd() }
      } else h.onEnd()
    }
    return r
  }

  return {
    start() {
      if (!C) return h.onError('unsupported')
      wantRunning = true
      rec = build()
      try { rec.start() } catch { wantRunning = false; h.onError('unknown') }
    },
    stop() { wantRunning = false; rec?.stop() },
    abort() { wantRunning = false; rec?.abort() },
  }
}

export const DICTATION_MESSAGES: Record<DictationError, string> = {
  'not-allowed': 'Microphone access is blocked. Allow it in your browser, or switch to typing. Your text so far is kept.',
  'no-speech': 'I did not hear anything. Tap the mic and try again.',
  'audio-capture': 'No microphone was found. You can type instead.',
  network: 'Speech recognition lost its connection. Your text so far is kept.',
  unsupported: 'This browser cannot do live dictation. Use Chrome, Edge or Safari, or type your entry.',
  unknown: 'Dictation stopped unexpectedly. Your text so far is kept.',
}
