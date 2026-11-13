import clsx from 'clsx'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/errors'
import { useOnboarding } from '@/api/hooks/useSettings'
import { Button } from '@/components/ui/Button'
import { Field, Select } from '@/components/ui/Field'
import { Icon, Logo } from '@/components/ui/Icon'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { allTimezones, browserTimezone } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'

const WORK = ['Deep work', 'Meetings', 'Sales & clients', 'Admin', 'Learning']
const PERSONAL = ['Health', 'Family & friends', 'Meals & chores', 'Commute', 'Entertainment', 'Transitions']
const IDEAL: [string, string][] = [['Sleep', '7h 30m'], ['Deep work', '4h 30m'], ['Family & friends', '2h 30m'], ['Meals & chores', '2h'], ['Entertainment', '1h 30m'], ['Everything else', '6h']]

function Option({ selected, onSelect, title, children }: { selected: boolean; onSelect: () => void; title: string; children: React.ReactNode }) {
  return (
    <button type="button" role="radio" aria-checked={selected} onClick={onSelect}
      className={clsx('flex w-full flex-col gap-2 rounded-2xl border p-4 text-left transition', selected ? 'border-accent bg-tint' : 'border-line bg-card hover:border-ghostline')}>
      <span className="flex items-center justify-between text-sm font-semibold">{title}{selected && <Icon name="check" size={16} className="text-accent-ink" />}</span>
      <span className="text-[13px] leading-relaxed text-muted">{children}</span>
    </button>
  )
}

const chip = 'rounded-full border border-line bg-card px-2.5 py-0.5 text-[11px] font-semibold'

export function OnboardingPage() {
  const nav = useNavigate()
  const user = useAuthStore((s) => s.user)!
  const [step, setStep] = useState(0)
  const [tz, setTz] = useState(user.timezone && user.timezone !== 'Asia/Kolkata' ? user.timezone : browserTimezone())
  const [seed, setSeed] = useState<'default' | 'empty'>('default')
  const [ideal, setIdeal] = useState<'balanced' | 'none'>('balanced')
  const onboard = useOnboarding()
  const zones = allTimezones()
  const steps = ['Timezone', 'Categories', 'Ideal day']

  return (
    <div className="min-h-screen bg-paper">
      <header className="flex items-center justify-between px-5 py-4 md:px-10"><div className="flex items-center gap-2.5"><Logo size={30} /><b className="font-display text-[17px]">Cadence</b></div><ThemeToggle /></header>
      <main className="mx-auto flex max-w-xl flex-col gap-6 px-4 pb-16 pt-4">
        <div>
          <h1 className="m-0 font-display text-[28px] font-semibold tracking-tighter2">Welcome, {user.display_name.split(' ')[0]}</h1>
          <p className="mt-1 text-sm text-muted">Three quick choices. You can change all of them later.</p>
        </div>
        <ol className="flex gap-2" aria-label="Progress">
          {steps.map((s, i) => (
            <li key={s} aria-current={i === step ? 'step' : undefined} className={clsx('flex flex-1 items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold', i === step ? 'border-accent bg-tint text-accent-ink' : i < step ? 'border-line bg-card text-ink' : 'border-line bg-card text-faint')}>
              <span className="num flex size-5 items-center justify-center rounded-full bg-line2 text-[11px]">{i < step ? <Icon name="check" size={11} /> : i + 1}</span>{s}
            </li>
          ))}
        </ol>

        <section className="card flex flex-col gap-4 p-5" aria-live="polite">
          {step === 0 && (
            <>
              <h2 className="m-0 text-base font-semibold">Where are you?</h2>
              <p className="-mt-2 text-[13px] text-muted">A day runs from your local midnight to the next. Each activity remembers its own timezone, so travelling later never rewrites history.</p>
              <Field label="Timezone">{(id) => <Select id={id} value={tz} onChange={(e) => setTz(e.target.value)}>{(zones.includes(tz) ? zones : [tz, ...zones]).map((z) => <option key={z}>{z}</option>)}</Select>}</Field>
            </>
          )}
          {step === 1 && (
            <>
              <h2 className="m-0 text-base font-semibold">Start with a suggested set of categories?</h2>
              <p className="-mt-2 text-[13px] text-muted">Every activity gets exactly one category, so your 24 hours always add up. Work, Personal and Sleep are built in.</p>
              <div role="radiogroup" aria-label="Categories" className="flex flex-col gap-2.5">
                <Option selected={seed === 'default'} onSelect={() => setSeed('default')} title="Use the suggested set">
                  <span className="mb-1.5 block"><b className="text-ink">Work</b> <span className="mt-1 flex flex-wrap gap-1.5">{WORK.map((c) => <span key={c} className={chip}>{c}</span>)}</span></span>
                  <span className="block"><b className="text-ink">Personal</b> <span className="mt-1 flex flex-wrap gap-1.5">{PERSONAL.map((c) => <span key={c} className={chip}>{c}</span>)}</span></span>
                  <span className="mt-2 block">Plus a few example tags (#research, #meetings, #social-media with a weekly cap) and keyword rules you can delete.</span>
                </Option>
                <Option selected={seed === 'empty'} onSelect={() => { setSeed('empty'); setIdeal('none') }} title="Start empty">Only Work, Personal and Sleep. You build the rest.</Option>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <h2 className="m-0 text-base font-semibold">Set a starting Ideal Day?</h2>
              <p className="-mt-2 text-[13px] text-muted">Your Ideal Day is the target your real days are compared with. It must add up to exactly 24 hours.</p>
              <div role="radiogroup" aria-label="Ideal day" className="flex flex-col gap-2.5">
                <Option selected={ideal === 'balanced'} onSelect={() => setIdeal('balanced')} title="A balanced day">
                  <span className="mt-1 flex flex-wrap gap-1.5">{IDEAL.map(([n, h]) => <span key={n} className={chip}>{n} · {h}</span>)}</span>
                  <span className="mt-2 block">24h in total. Edit it any time.</span>
                </Option>
                <Option selected={ideal === 'none'} onSelect={() => setIdeal('none')} title="I will set it later">No comparison until you add one.</Option>
              </div>
            </>
          )}
          {onboard.error && <p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{errorMessage(onboard.error)}</p>}
          <div className="flex justify-between pt-1">
            <Button variant="subtle" onClick={() => setStep(step - 1)} disabled={step === 0}>Back</Button>
            {step < 2 ? <Button variant="primary" onClick={() => setStep(step + 1)}>Continue</Button>
              : <Button variant="primary" loading={onboard.isPending} onClick={() => onboard.mutate({ timezone: tz, seed, ideal_day_preset: seed === 'empty' ? 'none' : ideal }, { onSuccess: () => nav('/overview', { replace: true }) })}>Finish setup</Button>}
          </div>
        </section>
      </main>
    </div>
  )
}
