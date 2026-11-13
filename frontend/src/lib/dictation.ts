/** Web Speech API wrapper (FR-015). Live interim text, resilient restarts, and a clear reason when it cannot run. */
type Rec = {
  continuous: boolean; interimResults: boolean; lang: string
  start(): void; stop(): void; abort(): void
  onresult: ((e: any) => void) | null; onerror: ((e: any) => void) | null; onend: (() => void) | null
}

const Ctor = (): (new () => Rec) | undefined => (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition

/** Some shells expose the API but ship no speech service, so it fails the moment it starts (Electron apps, Brave). */
export function dictationBlockedReason(): 'embedded' | 'brave' | null {
  if (typeof navigator === 'undefined') return null
  if (/Electron\/|\sClaude\//.test(navigator.userAgent)) return 'embedded'
  if ((navigator as any).brave) return 'brave'
  return null
}

export const dictationSupported = () => typeof window !== 'undefined' && !!Ctor() && dictationBlockedReason() === null

export type DictationError = 'not-allowed' | 'no-speech' | 'audio-capture' | 'network' | 'unsupported' | 'unknown'

/** Ask for the microphone first so a blocked or missing one is reported plainly instead of as a silent stop. */
export async function checkMicrophone(): Promise<DictationError | null> {
  if (!navigator.mediaDevices?.getUserMedia) return null // let the recogniser try; it reports its own error
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach((t) => t.stop())
    return null
  } catch (e) {
    const name = (e as DOMException)?.name
    if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'audio-capture'
    if (name === 'NotAllowedError' || name === 'SecurityError') return 'not-allowed'
    return 'unknown'
  }
}

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
  /** `raw` is the browser's own error code, kept for the on-screen detail and the console. */
  onError: (e: DictationError, raw?: string) => void
  onEnd: () => void
}

const SILENT_SESSIONS_BEFORE_GIVING_UP = 3 // Chrome ends a session after a few quiet seconds; keep listening through that
const FAST_ENDS_BEFORE_GIVING_UP = 3 // a session that ends at once, again and again, is broken rather than quiet

export function createDictation(h: Handlers): Dictation {
  const C = Ctor()
  let rec: Rec | null = null
  let wantRunning = false
  let startedAt = 0
  let gotResult = false
  let heardNothing = false
  let silent = 0
  let fast = 0

  const fail = (e: DictationError, raw?: string) => {
    wantRunning = false
    console.warn('[dictation]', e, raw ?? '')
    h.onError(e, raw)
  }

  function begin() {
    rec = build()
    startedAt = Date.now()
    gotResult = false
    heardNothing = false
    rec.start()
  }

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
      gotResult = true
      silent = 0
      fast = 0
      h.onInterim(interim)
    }
    r.onerror = (e: any) => {
      const code = (e?.error as string) ?? 'unknown'
      if (code === 'aborted') return
      if (code === 'no-speech') { heardNothing = true; return } // not fatal: onend decides whether to keep listening
      if (code === 'not-allowed' || code === 'service-not-allowed') return fail('not-allowed', code)
      if (code === 'audio-capture') return fail('audio-capture', code)
      if (code === 'network') return fail('network', code)
      fail('unknown', code)
    }
    r.onend = () => {
      if (!wantRunning) return h.onEnd()
      if (!gotResult) {
        if (heardNothing) silent += 1
        else if (Date.now() - startedAt < 1200) fast += 1
      }
      if (silent >= SILENT_SESSIONS_BEFORE_GIVING_UP) return fail('no-speech')
      if (fast >= FAST_ENDS_BEFORE_GIVING_UP) return fail('unknown', 'ended-immediately')
      // Chrome ends continuous recognition after a silence; restart while the person still wants to talk.
      setTimeout(() => {
        if (!wantRunning) return h.onEnd()
        try { begin() } catch { fail('unknown', 'restart-failed') }
      }, 150)
    }
    return r
  }

  return {
    start() {
      if (!C) return h.onError('unsupported')
      wantRunning = true
      silent = 0
      fast = 0
      try { begin() } catch { fail('unknown', 'start-failed') }
    },
    stop() { wantRunning = false; rec?.stop() },
    abort() { wantRunning = false; rec?.abort() },
  }
}

export const DICTATION_MESSAGES: Record<DictationError, string> = {
  'not-allowed': 'Microphone access is blocked. Allow it for this site in your browser (the lock icon in the address bar), or switch to typing. Your text so far is kept.',
  'no-speech': 'I did not hear anything. Check that the right microphone is selected, then tap the mic and try again.',
  'audio-capture': 'No microphone was found. Plug one in or choose one in your system settings, or type instead.',
  network: 'Speech recognition could not reach its service. It needs an internet connection, and does not work in Brave or in app-embedded browsers. Use Chrome, Edge or Safari, or type. Your text so far is kept.',
  unsupported: 'This browser cannot do live dictation. Use Chrome, Edge or Safari, or type your entry.',
  unknown: 'Dictation stopped unexpectedly. Your text so far is kept.',
}

export const BLOCKED_MESSAGES = {
  embedded: 'Live dictation does not work inside an app-embedded browser. Open Cadence in Chrome, Edge or Safari to dictate, or type your entry.',
  brave: 'Live dictation does not work in Brave, which blocks the speech service. Use Chrome, Edge or Safari to dictate, or type your entry.',
}
