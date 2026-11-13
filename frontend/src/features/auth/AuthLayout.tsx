import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon, Logo } from '@/components/ui/Icon'
import { ThemeToggle } from '@/components/layout/ThemeToggle'

function Pitch() {
  return (
    <section className="relative flex flex-1 basis-[520px] flex-col gap-8 overflow-hidden bg-[var(--panel)] px-6 py-8 text-[var(--panelInk)] md:gap-10 md:px-14 md:py-12 max-lg:hidden">
      <div className="flex items-center gap-[11px]"><Logo size={34} /><b className="font-display text-[19px] font-bold tracking-tight">Cadence</b></div>
      <div>
        <h1 className="m-0 max-w-[520px] font-display text-[44px] font-semibold leading-[1.08] tracking-[-0.035em]">Know where every <em className="not-italic" style={{ color: 'color-mix(in srgb, var(--accent) 55%, #fff)' }}>hour</em> went.</h1>
        <p className="mt-3.5 max-w-[470px] text-[15px] leading-[1.55] text-[var(--panelMuted)]">Talk or type through your day. Cadence turns it into tagged activities and shows how it compares with your ideal day and week: work, sleep, fitness, scrolling, all of it.</p>
      </div>
      <div className="flex max-w-[500px] flex-col gap-3.5 rounded-2xl border border-white/10 bg-white/5 p-[18px]" aria-label="Example: a journal sentence becomes tagged activities">
        <div className="flex items-start gap-2.5 text-[13px] leading-[1.55] text-[#E7E8EB]">
          <span className="flex size-7 flex-none items-center justify-center rounded-full bg-accent"><Icon name="journal" size={14} strokeWidth={2} /></span>
          <span>“10 to 1 was fixing the sync bug in Product B, that was the P0. Then wasted half an hour on Twitter…”</span>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.07em] text-[var(--panelMuted)]"><i className="h-px flex-1 bg-white/10" />Becomes<i className="h-px flex-1 bg-white/10" /></div>
        {[
          { time: '10:00 – 1:00pm', title: 'Fix sync bug', cat: 'Work', tint: 'var(--accent)', tags: ['product-b', 'p0'] },
          { time: '3:00 – 3:30pm', title: 'Twitter', cat: 'Personal', tint: 'var(--warn)', tags: ['social-media'] },
        ].map((r) => (
          <div key={r.title} className="flex items-center gap-2.5 rounded-[10px] bg-white/[.04] px-[11px] py-[9px]">
            <span className="num w-[84px] flex-none text-[11px] text-[var(--panelMuted)]">{r.time}</span>
            <span className="min-w-0 flex-1 text-[12.5px] font-semibold">{r.title}</span>
            <span className="rounded-full px-2 py-0.5 text-[10.5px] font-semibold text-white" style={{ background: `color-mix(in srgb, ${r.tint} 35%, transparent)` }}>{r.cat}</span>
            {r.tags.map((t) => <span key={t} className="rounded-full border border-white/20 px-2 py-0.5 text-[10.5px] font-semibold">#{t}</span>)}
          </div>
        ))}
      </div>
      <div className="mt-auto grid max-w-[560px] grid-cols-3 gap-[18px]">
        {([['journal', 'Dictate or type', 'A few sentences for the day, or a couple of hours.'], ['tag', 'Everything tagged', 'Work, personal, sleep, with tags you can chart.'], ['ideal', 'Against your ideal', 'Daily vs ideal day, weekly vs ideal week.']] as const).map(([i, t, d]) => (
          <div key={t}><span className="flex size-[30px] items-center justify-center rounded-[9px] bg-white/[.08]"><Icon name={i} size={16} /></span><b className="mb-[3px] mt-2 block text-[13px] font-semibold">{t}</b><span className="text-xs leading-[1.45] text-[var(--panelMuted)]">{d}</span></div>
        ))}
      </div>
    </section>
  )
}

export function AuthLayout({ title, subtitle, children, aside }: { title: string; subtitle?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-wrap bg-paper">
      <Pitch />
      <section className="flex min-w-0 flex-1 basis-[440px] flex-col px-4 py-5 md:px-10 md:py-7">
        <div className="flex items-center justify-between gap-3">
          <Link to="/login" className="flex items-center gap-2.5 lg:invisible"><Logo size={30} /><b className="font-display text-[17px] font-bold">Cadence</b></Link>
          <div className="flex items-center gap-3 text-[12.5px] text-muted">{aside}<ThemeToggle /></div>
        </div>
        <div className="flex flex-1 items-center justify-center py-8">
          <div className="flex w-full max-w-[380px] flex-col gap-4">
            <h2 className="m-0 font-display text-[28px] font-semibold tracking-tighter2">{title}</h2>
            {subtitle && <p className="-mt-2 text-[13.5px] text-muted">{subtitle}</p>}
            {children}
          </div>
        </div>
      </section>
    </div>
  )
}
