import { useNavigate, useSearchParams } from 'react-router-dom'
import { useOverview } from '@/api/hooks/useAnalytics'
import { usePreferences } from '@/api/hooks/useSettings'
import { PageHeader, Segmented } from '@/components/layout/PageHeader'
import { Button, IconButton } from '@/components/ui/Button'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/Feedback'
import { addDays, dayAndMonth, greeting, rangeLabel, todayIn, weekdayLong, weekDates } from '@/lib/time'
import { useAuthStore } from '@/stores/authStore'
import { useTimeline } from '@/api/hooks/useActivities'
import { Banners, DayRhythm, DeadlinesCard, FocusCard, HeatmapCard, IdealCard, KpiRow, SleepCard, TagGoalsCard, TopTasksCard, TreemapCard, TrendCard, WorkPersonalCard } from './OverviewCards'
import { WeekColumns } from './WeekColumns'

export function OverviewPage() {
  const user = useAuthStore((s) => s.user)!
  const tz = user.timezone
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const { data: prefs } = usePreferences()
  const today = todayIn(tz)
  const scope = sp.get('scope') === 'week' ? 'week' : 'day' // the day is the default everywhere
  const date = sp.get('date') ?? today
  const weekStart = prefs?.week_start ?? 1
  const dates = scope === 'week' ? weekDates(date, weekStart) : [date]
  const fmt = prefs?.time_format ?? '12h'
  const { data: o, error, isLoading, isPlaceholderData, refetch } = useOverview(scope, date)
  const { data: days } = useTimeline({ from: dates[0], to: dates[dates.length - 1], ideal: false })
  const set = (k: string, v: string | null) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }
  const step = scope === 'week' ? 7 : 1
  const empty = !!o && o.kpis.logged_minutes === 0

  return (
    <>
      <PageHeader title={`${greeting(tz)}, ${user.display_name.split(' ')[0]}`} subtitle={scope === 'week' ? `Week of ${rangeLabel(dates[0], dates[6])}` : `${weekdayLong(date)}, ${dayAndMonth(date)}`}>
        <Segmented label="Scope" value={scope} onChange={(v) => set('scope', v === 'week' ? 'week' : null)} options={[{ value: 'day', label: 'Day' }, { value: 'week', label: 'Week' }]} />
        <div className="flex items-center gap-1.5">
          <IconButton icon="chevronLeft" label="Previous" onClick={() => set('date', addDays(date, -step))} />
          <Button onClick={() => set('date', null)} disabled={dates.includes(today)}>Today</Button>
          <IconButton icon="chevronRight" label="Next" onClick={() => set('date', addDays(date, step))} />
        </div>
        <Button variant="primary" icon="plus" className="max-md:hidden" onClick={() => nav('/calendar?log=1')}>Log time</Button>
      </PageHeader>

      <div className={`flex flex-col gap-4 p-4 transition-opacity md:px-7 md:py-5 ${isPlaceholderData ? 'opacity-60' : ''}`}>
        {error && <ErrorState error={error} onRetry={() => refetch()} />}
        {isLoading && <div className="grid gap-4 md:grid-cols-4"><Skeleton className="h-32" /><Skeleton className="h-32" /><Skeleton className="h-32" /><Skeleton className="h-32" /></div>}

        {o && (
          <>
            <Banners banners={o.banners} />
            {empty ? (
              <div className="card"><EmptyState icon="calendar" title="Nothing logged for this period yet" action={<Button variant="primary" icon="plus" onClick={() => nav('/calendar?log=1')}>Log your first activity</Button>}>
                Add what you did, or plan what is coming. Totals, gaps and your Ideal comparison fill in as you go.
              </EmptyState></div>
            ) : (
              <>
                <KpiRow o={o} scope={scope} />
                <div className="grid items-start gap-4 lg:grid-cols-3">
                  <IdealCard o={o} scope={scope} onOpen={(id) => nav(`/calendar?date=${dates[0]}&category=${id}`)} />
                  <WorkPersonalCard o={o} />
                </div>
                {scope === 'week' ? (
                  <>
                    {days && <WeekColumns days={days.filter((d) => dates.includes(d.date))} today={today} onOpen={(d) => nav(`/calendar?date=${d}&view=day`)} />}
                    <div className="grid items-start gap-4 lg:grid-cols-2"><SleepCard o={o} dates={dates} tz={tz} fmt={fmt} /><FocusCard o={o} dates={dates} /></div>
                    <TrendCard />
                    <HeatmapCard weekStart={weekStart} />
                    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                      <TreemapCard from={dates[0]} to={dates[6]} />
                      <div className="flex min-w-0 flex-col gap-4"><TopTasksCard o={o} /><TagGoalsCard o={o} /></div>
                    </div>
                    <DeadlinesCard o={o} />
                  </>
                ) : (
                  <>
                    {o.rhythm && <DayRhythm day={o.rhythm} tz={tz} fmt={fmt} />}
                    <div className="grid items-start gap-4 lg:grid-cols-2"><TopTasksCard o={o} /><DeadlinesCard o={o} /></div>
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </>
  )
}
