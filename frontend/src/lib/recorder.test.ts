import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRecorder, MAX_SECONDS, pickMimeType, RecorderError } from './recorder'

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = []
  static supported = ['audio/webm;codecs=opus']
  static isTypeSupported = (m: string) => FakeMediaRecorder.supported.includes(m)
  state = 'inactive'; mimeType: string
  ondataavailable: ((e: { data: Blob }) => void) | null = null; onstop: (() => void) | null = null
  constructor(public stream: unknown, public opts: { mimeType?: string }) { this.mimeType = opts.mimeType ?? ''; FakeMediaRecorder.instances.push(this) }
  start() { this.state = 'recording' }
  stop() { this.state = 'inactive'; this.onstop?.() }
  emit(bytes: number) { this.ondataavailable?.({ data: new Blob([new Uint8Array(bytes)]) }) }
}

const last = () => FakeMediaRecorder.instances[FakeMediaRecorder.instances.length - 1]
const track = { stop: vi.fn() }

beforeEach(() => {
  vi.useFakeTimers()
  track.stop.mockClear()
  FakeMediaRecorder.instances = []
  ;(globalThis as any).MediaRecorder = FakeMediaRecorder
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } })
})
afterEach(() => { vi.useRealTimers(); delete (globalThis as any).MediaRecorder })

describe('recorder', () => {
  it('picks the first container the browser can write', () => {
    expect(pickMimeType()).toBe('audio/webm;codecs=opus')
    FakeMediaRecorder.supported = ['audio/mp4'] // Safari
    expect(pickMimeType()).toBe('audio/mp4')
    FakeMediaRecorder.supported = ['audio/webm;codecs=opus']
  })

  it('records, hands back the audio, and lets go of the microphone', async () => {
    const r = createRecorder()
    await r.start()
    last().emit(4000); last().emit(4000)
    vi.advanceTimersByTime(7400)
    const out = await r.stop()
    expect(out.blob.size).toBe(8000)
    expect(out.seconds).toBe(7)
    expect(out.mime).toBe('audio/webm;codecs=opus')
    expect(track.stop).toHaveBeenCalled()
  })

  it('says why when the microphone is blocked or missing', async () => {
    const gum = navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>
    gum.mockRejectedValueOnce(Object.assign(new Error('x'), { name: 'NotAllowedError' }))
    await expect(createRecorder().start()).rejects.toMatchObject({ code: 'not-allowed' })
    gum.mockRejectedValueOnce(Object.assign(new Error('x'), { name: 'NotFoundError' }))
    await expect(createRecorder().start()).rejects.toBeInstanceOf(RecorderError)
  })

  it('asks to stop at ten minutes, and again if the size nears the 10 MB cap', async () => {
    const onLimit = vi.fn()
    await createRecorder({ onLimit }).start()
    vi.advanceTimersByTime(MAX_SECONDS * 1000 + 10)
    expect(onLimit).toHaveBeenCalledTimes(1)
    const big = vi.fn()
    await createRecorder({ onLimit: big }).start()
    last().emit(10 * 1024 * 1024)
    expect(big).toHaveBeenCalledTimes(1)
  })

  it('throws the audio away on cancel', async () => {
    const r = createRecorder()
    await r.start()
    r.cancel()
    expect(track.stop).toHaveBeenCalled()
    await expect(r.stop()).rejects.toBeInstanceOf(RecorderError)
  })
})
