import clsx from 'clsx'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, request } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useTimeline } from '@/api/hooks/useActivities'
import { useAiStatus, useCreateEntry, useJournalStats, usePatchEntry, useProcessEntry, useRecentEntries } from '@/api/hooks/useJournal'
import { useTags } from '@/api/hooks/useTaxonomy'
import { useRules } from '@/api/hooks/useTaxonomy'
import type { EntryOut, EntrySummary } from '@/api/types'
import { TagChip } from '@/components/domain/Chips'
import { CoverageStrip24h } from '@/components/domain/CoverageStrip24h'
import { isoToRange, rangeToIso, TimeRangeInput, type RangeValue } from '@/components/domain/TimeRangeInput'
import { PageHeader, Segmented } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Feedback'
import { Icon, type IconName } from '@/components/ui/Icon'
import { usePrefersReducedMotion } from '@/lib/a11y'
import { BLOCKED_MESSAGES, checkMicrophone, createDictation, DICTATION_MESSAGES, dictationBlockedReason, dictationSupported, type Dictation, type DictationError } from '@/lib/dictation'
import { approxActivities, phraseIn, wordCount } from '@/lib/heuristics'
import { idbDelete, idbGet, idbSet } from '@/lib/idb'
import { dayAndMonth, formatClock, hm, isoToLocal, minutesBetween, todayIn, weekdayShort } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'

type Mode = 'dictate' | 'type'
type Preset = 'today' | 'morning' | 'afternoon' | 'since' | 'custom'
interface Draft { text: string; covers: RangeValue; preset: Preset; mode: Mode; seconds: number; entryId?: string; version?: number; dictated: boolean }

const MAX_CHARS = 10_000
const draftKey = (uid: string) => `journal-draft:${uid}`
const STATUS_LABEL: Record<string, string> = { draft: 'Draft', processing: 'Reading…', review: 'Needs review', failed: 'Failed', manual: 'Manual' }

function useNow(everyMs = 30_000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), everyMs); return () => clearInterval(t) }, [everyMs])
  return now
}

function Waveform({ active }: { active: boolean }) {
  const reduced = usePrefersReducedMotion()
  return (
    <div aria-hidden className="flex h-11 items-center justify-center gap-[3px]">
      {Array.from({ length: 28 }, (_, i) => (
        <i key={i} className="block w-1 rounded-sm bg-accent/70 transition-[height]"
          style={{ height: active && !reduced ? undefined : 6, animation: active && !reduced ? `wave ${0.7 + (i % 7) * 0.09}s ease-in-out ${(i % 5) * 0.08}s infinite alternate` : undefined, minHeight: 4, opacity: active ? 1 : 0.35 }} />
      ))}
    </div>
  )
}

const fmtTimer = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`

export function JournalPage() {
  const user = useAuthStore((s) => s.user)!
  const tz = user.timezone
  const nav = useNavigate()
  const now = useNow()
  const today = todayIn(tz, now)
  const nowTime = isoToLocal(new Date(now).toISOString(), tz).time
  const { data: ai } = useAiStatus()
  const { data: stats } = useJournalStats()
  const { data: recent, isLoading: loadingRecent } = useRecentEntries(5)
  const { data: days } = useTimeline({ from: today, to: today })
  const { data: rules } = useRules()
  const { data: tags } = useTags()
  const create = useCreateEntry(), patch = usePatchEntry(), process = useProcessEntry()
  const supported = dictationSupported()
  const blockedWhy = dictationBlockedReason()

  const [mode, setMode] = useState<Mode>(supported ? 'dictate' : 'type')
  const [text, setText] = useState('')
  const [interim, setInterim] = useState('')
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [dictated, setDictated] = useState(false)
  const [micError, setMicError] = useState<DictationError>()
  const [micRaw, setMicRaw] = useState<string>()
  const [preset, setPreset] = useState<Preset>('today')
  const [covers, setCovers] = useState<RangeValue>({ date: today, start: '00:00', end: nowTime })
  const [entryId, setEntryId] = useState<string>()
  const [version, setVersion] = useState<number>()
  const [savedAt, setSavedAt] = useState<number>()
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string>()
  const [submitting, setSubmitting] = useState(false)
  const [restored, setRestored] = useState(false)
  const dict = useRef<Dictation | null>(null)
  const cancelStart = useRef(false)
  const keys = useRef(new Map<string, string>())
  const textRef = useRef(text)
  textRef.current = text

  // ---- the window (what time span this entry covers)
  const win = useMemo(() => { try { return rangeToIso(covers, tz) } catch { return null } }, [covers, tz])
  const winMinutes = win ? minutesBetween(win.start_at, win.end_at) : 0
  const winError = !win ? 'Enter a valid window.' : winMinutes <= 0 ? 'The window must end after it starts.' : winMinutes > 1440 ? 'A window can cover at most 24 hours.' : Date.parse(win.end_at) > now + 60_000 ? 'The window cannot end in the future.' : undefined

  const lastEnd = recent?.find((e) => e.status !== 'draft')?.covers_end_at
  const choosePreset = (p: Preset) => {
    setPreset(p); setDirty(true)
    if (p === 'today') setCovers({ date: today, start: '00:00', end: nowTime })
    if (p === 'morning') setCovers({ date: today, start: '00:00', end: nowTime < '12:00' ? nowTime : '12:00' })
    if (p === 'afternoon') setCovers({ date: today, start: '12:00', end: nowTime < '18:00' ? nowTime : '18:00' })
    if (p === 'since' && lastEnd) { const a = isoToRange(lastEnd, new Date(now).toISOString(), tz); setCovers(a) }
  }

  // ---- restore a local draft (offline-safe, FR-014)
  useEffect(() => {
    let live = true
    ;(async () => {
      const d = await idbGet<Draft>(draftKey(user.id))
      if (!live || !d) return setRestored(true)
      if (d.entryId) {
        try {
          const e = await request<EntryOut>(`/journal-entries/${d.entryId}`)
          if (e.data.status !== 'draft') throw new Error('stale')
          d.version = e.data.version
        } catch (err) {
          if (err instanceof ApiError && err.status !== 404) { /* offline or transient: keep the local text, drop the link */ }
          d.entryId = undefined; d.version = undefined
        }
      }
      if (!live) return
      setText(d.text); setCovers(d.covers); setPreset(d.preset); setMode(d.mode === 'dictate' && !supported ? 'type' : d.mode)
      setSeconds(d.seconds); setDictated(d.dictated); setEntryId(d.entryId); setVersion(d.version)
      setRestored(true)
      if (d.text.trim()) toast.success('Restored your unsaved draft.')
    })()
    return () => { live = false }
  }, [user.id, supported])

  useEffect(() => {
    if (!restored) return
    const t = setTimeout(() => {
      if (!text && !entryId) idbDelete(draftKey(user.id))
      else idbSet(draftKey(user.id), { text, covers, preset, mode, seconds, entryId, version, dictated } satisfies Draft)
    }, 400)
    return () => clearTimeout(t)
  }, [text, covers, preset, mode, seconds, entryId, version, dictated, restored, user.id])

  // ---- saving
  const persist = useCallback(async (): Promise<EntryOut | null> => {
    if (!win || winError || !textRef.current.trim()) return null
    const body = { raw_text: textRef.current.trim(), covers_start_at: win.start_at, covers_end_at: win.end_at }
    const saved = entryId && version !== undefined
      ? await patch.mutateAsync({ id: entryId, version, ...body })
      : await create.mutateAsync({ ...body, timezone: tz, input_method: dictated ? 'dictated' : 'typed', dictation_seconds: dictated ? seconds : null })
    setEntryId(saved.id); setVersion(saved.version); setSavedAt(Date.now()); setDirty(false)
    return saved
  }, [win, winError, entryId, version, patch, create, tz, dictated, seconds])

  const persistRef = useRef(persist)
  persistRef.current = persist
  useEffect(() => {
    if (!dirty || recording || submitting || !text.trim() || winError || !navigator.onLine) return
    const t = setTimeout(() => { persistRef.current().catch(() => undefined) }, 5000)
    return () => clearTimeout(t)
  }, [dirty, text, covers, recording, submitting, winError])

  const saveDraft = async () => {
    setError(undefined)
    try { if (await persist()) toast.success('Draft saved.') } catch (e) { setError(errorMessage(e)) }
  }

  const submit = async () => {
    setError(undefined)
    if (!text.trim()) return setError('Write or dictate something first.')
    if (winError) return setError(winError)
    setSubmitting(true)
    try {
      if (recording) stopRec()
      const saved = (dirty || !entryId ? await persist() : null) ?? (entryId && version !== undefined ? ({ id: entryId, revision: 0 } as EntryOut) : null)
      if (!saved) return
      const id = saved.id
      const k = `${id}:${saved.revision}:${textRef.current.length}`
      if (!keys.current.has(k)) keys.current.set(k, crypto.randomUUID())
      const job = await process.mutateAsync({ id, key: keys.current.get(k)! })
      await idbDelete(draftKey(user.id))
      nav(`/journal/${id}/review?job=${job.job_id}`)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'AI_DISABLED') {
        await idbDelete(draftKey(user.id))
        toast.success('Entry saved. AI is off, so add the activities by hand.')
        nav('/calendar?log=1')
      } else if (e instanceof ApiError && e.code === 'ENTRY_BUSY' && e.details?.job_id && entryId) nav(`/journal/${entryId}/review?job=${e.details.job_id}`)
      else setError(errorMessage(e))
    } finally { setSubmitting(false) }
  }

  const loadDraft = async (e: EntrySummary) => {
    try {
      const { data } = await request<EntryOut>(`/journal-entries/${e.id}`)
      setText(data.raw_text); setEntryId(data.id); setVersion(data.version); setMode('type'); setPreset('custom')
      setCovers(isoToRange(data.covers_start_at, data.covers_end_at, tz)); setDictated(data.input_method === 'dictated'); setDirty(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) { toast.error(errorMessage(err)) }
  }

  const reset = () => { setText(''); setInterim(''); setEntryId(undefined); setVersion(undefined); setSeconds(0); setDictated(false); setDirty(false); setSavedAt(undefined); idbDelete(draftKey(user.id)) }

  // ---- dictation
  useEffect(() => {
    if (!recording) return
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [recording])
  useEffect(() => () => dict.current?.abort(), [])

  const startRec = async () => {
    setMicError(undefined); setMicRaw(undefined)
    cancelStart.current = false
    setRecording(true) // show the listening state at once; the permission prompt can take a moment
    const blocked = await checkMicrophone()
    if (cancelStart.current) return // stopped while the permission prompt was open
    if (blocked) { setMicError(blocked); setRecording(false); return }
    dict.current = createDictation({
      onFinal: (t) => { if (t) { setText((p) => (p && !/\s$/.test(p) ? `${p} ` : p) + t); setDirty(true); setDictated(true) } },
      onInterim: setInterim,
      onError: (e, raw) => { setMicError(e); setMicRaw(raw); setRecording(false); setInterim('') },
      onEnd: () => { setRecording(false); setInterim('') },
    })
    dict.current.start()
  }
  const stopRec = () => { cancelStart.current = true; dict.current?.stop(); setRecording(false); setInterim('') }

  // ---- derived UI
  const words = wordCount(text)
  const approx = approxActivities(text)
  const dayData = days?.[0]
  const yGap = stats?.yesterday_gap
  const detectedTags = useMemo(() => {
    const out: { name: string; color: string }[] = []
    for (const r of rules ?? []) {
      if (r.target_type !== 'tag' || !r.phrase || !phraseIn(text, r.phrase)) continue
      const t = tags?.find((x) => x.id === r.target_id)
      if (t && !out.some((o) => o.name === t.name)) out.push({ name: t.name, color: t.color })
    }
    return out.slice(0, 6)
  }, [rules, tags, text])
  const coveredPct = winMinutes > 0 ? Math.min(100, Math.round((Math.min(approx * 45, winMinutes) / winMinutes) * 100)) : 0
  const presets: { id: Preset; label: string; off?: boolean }[] = [
    { id: 'today', label: 'Today so far' }, { id: 'morning', label: 'This morning' }, { id: 'afternoon', label: 'This afternoon', off: nowTime < '12:00' },
    { id: 'since', label: 'Since my last entry', off: !lastEnd }, { id: 'custom', label: 'Custom' },
  ]
  const fullScreen = recording
  const canSubmit = !submitting && !!text.trim() && !winError

  const dictateBox = (
    <div className={clsx(fullScreen && 'max-md:flex max-md:min-h-0 max-md:flex-1 max-md:flex-col')}>
      <div className="flex flex-col items-center gap-3.5 pb-3.5 pt-1.5">
        <div className="relative flex size-24 items-center justify-center">
          {recording && <>
            <i aria-hidden className="absolute inset-0 rounded-full bg-bad/15 motion-safe:animate-[ring_1.8s_ease-out_infinite]" />
            <i aria-hidden className="absolute inset-0 rounded-full bg-bad/10 motion-safe:animate-[ring_1.8s_ease-out_.6s_infinite]" />
          </>}
          <button type="button" onClick={recording ? stopRec : startRec} aria-label={recording ? 'Stop dictation' : 'Start dictation'} aria-pressed={recording}
            className={clsx('relative flex size-[76px] items-center justify-center rounded-full text-white shadow-lg transition', recording ? 'bg-bad' : 'bg-accent hover:brightness-95')}>
            <Icon name={recording ? 'stop' : 'journal'} size={30} strokeWidth={2} />
          </button>
        </div>
        <div className="text-[13px] font-medium text-muted" aria-live="polite">
          {recording ? <span className="inline-flex items-center gap-2"><i className="size-2 rounded-full bg-bad motion-safe:animate-pulse" />Listening <b className="num font-semibold text-ink">{fmtTimer(seconds)}</b></span> : text ? 'Tap the mic to keep talking' : 'Tap the mic and tell me about your day'}
        </div>
        <Waveform active={recording} />
      </div>
      {micError && <p role="alert" className="mb-3 rounded-[10px] border border-warn/40 bg-warn/10 px-3 py-2 text-[12.5px] text-ink">{DICTATION_MESSAGES[micError]}{micRaw && <span className="mt-1 block text-[11px] text-faint">Browser said: {micRaw}</span>}</p>}
      {recording ? (
        <div className="min-h-[150px] flex-1 overflow-y-auto rounded-xl bg-line2 p-3.5 text-sm leading-[1.6] max-md:min-h-0" aria-label="Live transcript">
          {text}{interim && <span className="text-faint"> {interim}</span>}<span aria-hidden className="ml-0.5 inline-block h-[1.1em] w-0.5 translate-y-[3px] bg-accent motion-safe:animate-pulse" />
        </div>
      ) : (
        <textarea aria-label="Transcript" value={text} maxLength={MAX_CHARS} placeholder="Your words appear here as you speak. You can edit them before continuing."
          onChange={(e) => { setText(e.target.value); setDirty(true) }}
          className="block min-h-[150px] w-full resize-y rounded-xl border border-transparent bg-line2 p-3.5 text-sm leading-[1.6] outline-none placeholder:text-faint focus:border-accent" />
      )}
      {fullScreen && <Button variant="primary" size="lg" className="mt-4 w-full md:hidden" onClick={stopRec}>Done talking</Button>}
    </div>
  )

  return (
    <>
      <PageHeader title="Journal" subtitle="Dictate or type your day · Cadence turns it into reviewed activities">
        <Button icon="history" onClick={() => nav('/journal/history')}>History</Button>
      </PageHeader>

      <div className="grid items-start gap-4 p-4 md:px-7 md:py-[22px] md:pb-10 lg:grid-cols-[minmax(0,1.75fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <section aria-labelledby="composer" className={clsx('card p-[18px]', fullScreen && 'max-md:fixed max-md:inset-0 max-md:z-40 max-md:flex max-md:flex-col max-md:rounded-none max-md:border-0 max-md:p-5')}>
            <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
              <h2 id="composer" className="m-0 font-display text-xl font-semibold tracking-tight">How did your day go?</h2>
              <Segmented label="Input method" value={mode} onChange={(m) => { if (recording) stopRec(); setMode(m) }}
                options={[{ value: 'dictate', label: supported ? 'Dictate' : 'Dictate (unavailable)' }, { value: 'type', label: 'Type' }]} />
            </div>

            {ai?.demo && <p className="mb-3 flex items-start gap-2 rounded-[10px] bg-tint px-3 py-2 text-[12.5px] leading-snug text-muted"><Icon name="info" size={15} className="mt-px flex-none text-accent-ink" /><span><b className="font-semibold text-ink">Demo mode.</b> No AI key is set on this server, so a simple offline reader handles your text. Expect rougher results.</span></p>}
            {ai && !ai.enabled && <p role="status" className="mb-3 flex items-start gap-2 rounded-[10px] bg-warn/10 px-3 py-2 text-[12.5px] leading-snug"><Icon name="alert" size={15} className="mt-px flex-none text-warn" /><span>AI is turned off. Your entry is saved, then you add the activities by hand on the Calendar.</span></p>}

            <div className={clsx('mb-3.5', fullScreen && 'max-md:hidden')}>
              <div className="mb-2 text-xs font-semibold text-muted" id="covers-label">This entry covers</div>
              <div role="radiogroup" aria-labelledby="covers-label" className="flex flex-wrap gap-2">
                {presets.map((p) => (
                  <button key={p.id} type="button" role="radio" aria-checked={preset === p.id} disabled={p.off} onClick={() => choosePreset(p.id)}
                    className={clsx('h-8 rounded-full border px-3.5 text-[12.5px] font-medium transition disabled:cursor-not-allowed disabled:opacity-45', preset === p.id ? 'border-accent bg-tint font-semibold text-accent-ink' : 'border-line bg-card text-muted hover:border-ghostline hover:text-ink')}>{p.label}</button>
                ))}
              </div>
              {preset === 'custom'
                ? <div className="mt-3 max-w-md"><TimeRangeInput value={covers} onChange={(v) => { setCovers(v); setDirty(true) }} tz={tz} error={winError} /></div>
                : <p className={clsx('mt-2 text-xs', winError ? 'text-bad' : 'text-faint')}>{winError ?? (win && <>{dayAndMonth(covers.date)} · {formatClock(win.start_at, tz, '12h')} – {formatClock(win.end_at, tz, '12h')} · {hm(winMinutes)}</>)}</p>}
            </div>

            {mode === 'dictate' && supported ? dictateBox : (
              <>
                {mode === 'dictate' && <p role="status" className="mb-3 rounded-[10px] border border-warn/40 bg-warn/10 px-3 py-2 text-[12.5px]">{blockedWhy ? BLOCKED_MESSAGES[blockedWhy] : DICTATION_MESSAGES.unsupported}</p>}
                <textarea aria-label="Your entry" value={text} maxLength={MAX_CHARS} placeholder="Worked on the proposal from 9 to 11, then standup until 11:30. Lunch for half an hour…"
                  onChange={(e) => { setText(e.target.value); setDirty(true) }}
                  className="block min-h-[290px] w-full resize-y rounded-xl border border-line bg-card p-3.5 text-sm leading-[1.6] outline-none placeholder:text-faint focus:border-accent focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)]" />
              </>
            )}

            <div className={clsx('mt-3.5 flex flex-col gap-2 rounded-xl bg-tint px-3.5 py-3', fullScreen && 'max-md:hidden')} aria-live="polite">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-muted">
                <span><b className="num font-semibold text-ink">~{approx}</b> {approx === 1 ? 'activity' : 'activities'} found so far</span>
                <span><b className="num font-semibold text-ink">~{coveredPct}%</b> of the window mentioned</span>
                <span className="text-faint">{words} words</span>
                <span className="ml-auto text-[11.5px] text-faint">Estimates. The real count comes after reading.</span>
              </div>
              {detectedTags.length > 0 && <div className="flex flex-wrap gap-1.5">{detectedTags.map((t) => <TagChip key={t.name} name={t.name} color={t.color} source="rule" />)}</div>}
            </div>

            {error && <p role="alert" className="mt-3 rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{error}</p>}

            <div className={clsx('mt-4 flex flex-wrap items-center gap-3', fullScreen && 'max-md:hidden')}>
              <p className="m-0 mr-auto flex min-w-[200px] items-center gap-1.5 text-xs text-faint"><Icon name="shield" size={13} />Private to you.{savedAt ? ` Draft saved ${formatClock(new Date(savedAt).toISOString(), tz)}.` : ' Autosaves every few seconds.'}</p>
              {text && <Button variant="subtle" onClick={reset}>Clear</Button>}
              <Button onClick={saveDraft} disabled={!canSubmit || !dirty} loading={create.isPending || patch.isPending}>Save draft</Button>
              <Button variant="primary" icon="sparkle" onClick={submit} disabled={!canSubmit} loading={submitting}>{ai && !ai.enabled ? 'Save & log by hand' : 'Create activities'}</Button>
            </div>
          </section>

          <section className="card p-[18px]" aria-labelledby="recent">
            <div className="mb-2 flex items-baseline justify-between"><h3 id="recent" className="m-0 text-sm font-semibold">Recent entries</h3><button className="text-xs font-semibold text-accent-ink hover:underline" onClick={() => nav('/journal/history')}>View all</button></div>
            {loadingRecent && <Skeleton className="h-16" />}
            {recent && recent.length === 0 && <p className="m-0 py-4 text-[13px] text-muted">Nothing yet. Your first entry will show up here.</p>}
            <ul className="m-0 list-none p-0">
              {recent?.map((e) => {
                const icon: IconName = e.input_method === 'dictated' ? 'journal' : 'keyboard'
                const go = () => (e.status === 'draft' ? loadDraft(e) : nav(e.status === 'review' || e.status === 'processing' ? `/journal/${e.id}/review` : `/journal/${e.id}`))
                return (
                  <li key={e.id} className="border-t border-line2 first:border-t-0">
                    <button type="button" onClick={go} className="flex w-full items-center gap-3 rounded-lg px-1 py-2.5 text-left hover:bg-line2/60">
                      <span className="flex size-8 flex-none items-center justify-center rounded-[9px] bg-tint text-accent-ink"><Icon name={icon} size={16} /></span>
                      <span className="min-w-0 flex-1">
                        <b className="block truncate text-[12.5px] font-semibold">{e.title}</b>
                        <span className="block text-[11px] text-faint">{weekdayShort(e.entry_date)} {dayAndMonth(e.entry_date)} · {e.word_count} words{e.status === 'confirmed' ? ` · ${e.activity_count} activities` : ''}</span>
                        {e.tags.length > 0 && <span className="mt-1.5 flex flex-wrap gap-1">{e.tags.slice(0, 3).map((t) => <TagChip key={t.name} name={t.name} color={t.color} />)}</span>}
                      </span>
                      <span className="flex-none text-right">
                        {e.status === 'confirmed' ? <span className="num text-xs font-semibold text-muted">{hm(e.covered_minutes)}<small className="block text-[10.5px] font-medium text-faint">covered</small></span>
                          : <span className={clsx('rounded-full px-2 py-0.5 text-[11px] font-semibold', e.status === 'failed' ? 'bg-bad/15 text-bad' : e.status === 'review' ? 'bg-warn/15 text-warn' : 'bg-line2 text-muted')}>{STATUS_LABEL[e.status] ?? e.status}</span>}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
        </div>

        <aside className="flex min-w-0 flex-col gap-4" aria-label="Today at a glance">
          <section className="card p-[18px]">
            <h3 className="m-0 mb-3 text-sm font-semibold">Today&apos;s 24 hours</h3>
            {dayData ? <>
              <CoverageStrip24h day={dayData} tz={tz} height={14} />
              <div className="mt-1.5 flex justify-between text-[10.5px] font-medium text-faint" aria-hidden><span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>12am</span></div>
              <dl className="m-0 mt-3.5 flex flex-col gap-2 text-[12.5px]">
                <div className="flex justify-between"><dt className="text-muted">Logged</dt><dd className="num m-0 font-semibold">{hm(dayData.coverage.logged)}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">This entry spans</dt><dd className="num m-0 font-semibold">{winError ? '–' : hm(winMinutes)}</dd></div>
                <div className="flex justify-between"><dt className="text-muted">Still to log</dt><dd className="num m-0 font-semibold">{hm(dayData.coverage.unlogged)}</dd></div>
              </dl>
            </> : <Skeleton className="h-24" />}
            {yGap && yGap.minutes >= 60 && (
              <div className="mt-3.5 flex items-center gap-2.5 rounded-[10px] border border-dashed border-bad/50 bg-bad/[.06] px-3 py-2.5 text-xs">
                <span className="flex-1 leading-snug"><b className="font-semibold">Yesterday is {hm(yGap.minutes)} short.</b> Add what you remember.</span>
                <Button size="sm" onClick={() => { setPreset('custom'); setCovers(isoToRange(yGap.start_at, yGap.end_at, tz)); setDirty(true); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>Add</Button>
              </div>
            )}
          </section>

          <section className="card p-[18px]">
            <h3 className="m-0 mb-1 text-sm font-semibold">Cadence listens for</h3>
            <p className="m-0 mb-3 text-xs text-muted">Words you use often become tags automatically.</p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {(rules ?? []).filter((r) => r.target_type === 'tag').slice(0, 4).map((r) => {
                const t = tags?.find((x) => x.id === r.target_id)
                return t && <li key={r.id} className="flex items-center justify-between gap-2 text-[12.5px]"><q className="truncate text-muted">{r.phrase}</q><Icon name="arrowRight" size={13} className="flex-none text-faint" /><TagChip name={t.name} color={t.color} source="rule" /></li>
              })}
              {!(rules ?? []).some((r) => r.target_type === 'tag') && <li className="text-[12.5px] text-muted">No keyword rules yet. Add some on a tag&apos;s page and they will apply here.</li>}
            </ul>
          </section>

          <section className="card p-[18px]">
            <h3 className="m-0 mb-3 text-sm font-semibold">Journal habit</h3>
            <div className="grid grid-cols-3 gap-2 text-center">
              {[
                { v: stats ? `${stats.streak_days}` : '–', l: 'day streak' },
                { v: stats ? stats.entries_per_day_30d.toFixed(1) : '–', l: 'entries / day' },
                { v: stats?.full_days_pct_30d != null ? `${Math.round(stats.full_days_pct_30d)}%` : '–', l: 'days at 24h' },
              ].map((s) => <div key={s.l} className="rounded-[10px] bg-line2 px-1 py-2.5"><div className="num text-[22px] font-semibold leading-none">{s.v}</div><div className="mt-1.5 text-[10.5px] font-medium text-faint">{s.l}</div></div>)}
            </div>
          </section>
        </aside>
      </div>
    </>
  )
}
