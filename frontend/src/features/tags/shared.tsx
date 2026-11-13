import { useState } from 'react'
import { errorMessage } from '@/api/errors'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { Field, Select } from '@/components/ui/Field'
import { PALETTE } from '@/lib/colors'
import { toast } from '@/stores/toastStore'

export function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  const colors = PALETTE.includes(value.toUpperCase()) || PALETTE.includes(value) ? PALETTE : [value, ...PALETTE]
  return (
    <div role="radiogroup" aria-label="Colour" className="flex flex-wrap items-center gap-1.5">
      {colors.map((c) => (
        <button key={c} type="button" role="radio" aria-checked={c.toLowerCase() === value.toLowerCase()} aria-label={c} onClick={() => onChange(c)}
          className="size-7 rounded-lg ring-offset-2 ring-offset-card transition aria-checked:ring-2 aria-checked:ring-ink" style={{ background: c }} />
      ))}
      <label className="ml-1 flex items-center gap-1.5 text-xs text-muted">Custom<input type="color" value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} className="h-7 w-9 cursor-pointer rounded border border-line bg-card p-0.5" /></label>
    </div>
  )
}

interface MergeProps {
  open: boolean
  onOpenChange: (v: boolean) => void
  title: string
  description: string
  options: { id: string; label: string }[]
  preview: (targetId: string) => Promise<string>
  confirm: (targetId: string) => Promise<unknown>
  confirmLabel: string
}

/** Merge is irreversible, so it always shows what will move before the user confirms (FR-089, FR-097). */
export function MergeDialog({ open, onOpenChange, title, description, options, preview, confirm, confirmLabel }: MergeProps) {
  const [target, setTarget] = useState('')
  const [summary, setSummary] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const pick = async (id: string) => {
    setTarget(id); setSummary(undefined); setError(undefined)
    if (!id) return
    try { setSummary(await preview(id)) } catch (e) { setError(errorMessage(e)) }
  }
  const go = async () => {
    setBusy(true)
    try { await confirm(target); toast.success('Merged'); onOpenChange(false); setTarget(''); setSummary(undefined) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) { setTarget(''); setSummary(undefined); setError(undefined) } }} title={title} description={description}
      footer={<><Button variant="subtle" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="danger" disabled={!target || !summary} loading={busy} onClick={go}>{confirmLabel}</Button></>}>
      <div className="flex flex-col gap-3">
        <Field label="Merge into">{(id) => <Select id={id} dense value={target} onChange={(e) => pick(e.target.value)}><option value="">Choose a target…</option>{options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</Select>}</Field>
        {summary && <p role="status" className="m-0 rounded-lg bg-warn/10 px-3 py-2 text-[13px] text-ink">{summary} This cannot be undone.</p>}
        {error && <p role="alert" className="m-0 text-[13px] text-bad">{error}</p>}
      </div>
    </Dialog>
  )
}
