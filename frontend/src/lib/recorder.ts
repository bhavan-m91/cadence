/** Audio capture for browsers without a working Web Speech API (Firefox, Brave, app shells, older Safari). FR-016.
 *  The recording stays in memory, is uploaded once to /transcriptions, and is never stored. */
import type { DictationError } from './dictation'

export const MAX_SECONDS = 600 // 10 minutes
export const MAX_BYTES = 10 * 1024 * 1024
const BITS_PER_SECOND = 32_000 // speech is fine at 32 kbps: ten minutes is about 2.4 MB, well under the cap

export const recorderSupported = () => typeof window !== 'undefined' && typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

/** First container this browser can write: WebM/Opus (Chrome, Firefox, Edge, Brave), MP4/AAC (Safari), Ogg. */
export function pickMimeType(): string | undefined {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/ogg']
  return candidates.find((m) => MediaRecorder.isTypeSupported?.(m))
}

export class RecorderError extends Error {
  constructor(public code: DictationError, message: string) { super(message) }
}

export interface Recording { blob: Blob; seconds: number; mime: string }

export interface Recorder {
  start(): Promise<void>
  /** Stop and hand back what was recorded. */
  stop(): Promise<Recording>
  /** Stop and throw the audio away. */
  cancel(): void
}

export function createRecorder(opts: { onLimit?: () => void } = {}): Recorder {
  let stream: MediaStream | null = null
  let rec: MediaRecorder | null = null
  let chunks: Blob[] = []
  let bytes = 0
  let startedAt = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let limited = false

  const release = () => {
    if (timer) clearTimeout(timer)
    timer = null
    stream?.getTracks().forEach((t) => t.stop())
    stream = null
  }

  return {
    async start() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      } catch (e) {
        const name = (e as DOMException)?.name
        if (name === 'NotFoundError' || name === 'OverconstrainedError') throw new RecorderError('audio-capture', 'No microphone found')
        if (name === 'NotAllowedError' || name === 'SecurityError') throw new RecorderError('not-allowed', 'Microphone blocked')
        throw new RecorderError('unknown', String(e))
      }
      const mime = pickMimeType()
      try {
        rec = new MediaRecorder(stream, { ...(mime ? { mimeType: mime } : {}), audioBitsPerSecond: BITS_PER_SECOND })
      } catch (e) {
        release()
        throw new RecorderError('unsupported', String(e))
      }
      chunks = []; bytes = 0; limited = false
      rec.ondataavailable = (ev) => {
        if (!ev.data.size) return
        chunks.push(ev.data)
        bytes += ev.data.size
        if (bytes > MAX_BYTES * 0.95 && !limited) { limited = true; opts.onLimit?.() }
      }
      rec.start(1000) // a chunk a second, so the size is known before the end
      startedAt = Date.now()
      timer = setTimeout(() => { limited = true; opts.onLimit?.() }, MAX_SECONDS * 1000)
    },
    stop() {
      return new Promise<Recording>((resolve, reject) => {
        const r = rec
        if (!r || r.state === 'inactive') { release(); return reject(new RecorderError('unknown', 'Not recording')) }
        r.onstop = () => {
          const mime = r.mimeType || pickMimeType() || 'audio/webm'
          const seconds = Math.min(MAX_SECONDS, Math.round((Date.now() - startedAt) / 1000))
          release()
          resolve({ blob: new Blob(chunks, { type: mime }), seconds, mime })
        }
        r.stop()
      })
    },
    cancel() {
      if (rec && rec.state !== 'inactive') { rec.onstop = null; rec.stop() }
      release()
      chunks = []
    },
  }
}
