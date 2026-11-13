import * as DM from '@radix-ui/react-dropdown-menu'
import clsx from 'clsx'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useLogout } from '@/api/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { Icon, Logo, type IconName } from '../ui/Icon'
import { OfflineBanner, Toaster } from '../ui/Feedback'

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/overview', label: 'Overview', icon: 'overview' },
  { to: '/journal', label: 'Journal', icon: 'journal' },
  { to: '/calendar', label: 'Calendar', icon: 'calendar' },
  { to: '/tasks', label: 'Tasks', icon: 'tasks' },
  { to: '/tags', label: 'Tags', icon: 'tag' },
  { to: '/ideal', label: 'Ideal Day & Week', icon: 'ideal' },
]

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join('') || '?'

function Sidebar() {
  const user = useAuthStore((s) => s.user)!
  const logout = useLogout()
  const nav = useNavigate()
  return (
    <aside className="sticky top-0 hidden h-screen w-[236px] flex-none flex-col gap-5 border-r border-line bg-card px-3.5 py-5 md:flex">
      <div className="flex items-center gap-2.5 px-2 py-1">
        <Logo />
        <div><b className="font-display text-[17px] font-bold tracking-tight">Cadence</b><small className="-mt-px block text-[11px] font-medium text-faint">Time intelligence</small></div>
      </div>
      <nav aria-label="Main" className="flex flex-col gap-0.5">
        <div className="px-2.5 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">Workspace</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} className={({ isActive }) => clsx('flex items-center gap-[11px] rounded-[9px] px-2.5 py-[9px] text-[13.5px] font-medium', isActive ? 'bg-tint font-semibold text-accent-ink' : 'text-muted hover:bg-line2 hover:text-ink')}>
            <Icon name={n.icon} size={18} />{n.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-1.5">
        <NavLink to="/settings" className={({ isActive }) => clsx('flex items-center gap-[11px] rounded-[9px] px-2.5 py-[9px] text-[13.5px] font-medium', isActive ? 'bg-tint font-semibold text-accent-ink' : 'text-muted hover:bg-line2 hover:text-ink')}>
          <Icon name="settings" size={18} />Settings
        </NavLink>
        <div className="flex items-center gap-2.5 rounded-[11px] border border-line p-2">
          <span className="flex size-8 flex-none items-center justify-center rounded-full bg-accent text-xs font-semibold text-white" aria-hidden>{initials(user.display_name)}</span>
          <div className="min-w-0 flex-1 leading-tight"><div className="truncate text-[13px] font-semibold">{user.display_name}</div><div className="truncate text-[11px] text-faint">{user.role_title ?? user.email}</div></div>
          <button type="button" aria-label="Sign out" title="Sign out" onClick={() => logout.mutate(false, { onSettled: () => nav('/login') })} className="flex size-8 flex-none items-center justify-center rounded-lg text-muted hover:bg-line2 hover:text-ink"><Icon name="logout" size={16} /></button>
        </div>
      </div>
    </aside>
  )
}

function BottomTabs() {
  const nav = useNavigate()
  const logout = useLogout()
  const tab = 'flex min-h-11 min-w-14 flex-col items-center justify-center gap-[3px] text-[9.5px] font-medium text-faint'
  const on = (active: boolean) => clsx(tab, active && 'font-semibold text-accent-ink')
  return (
    <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 flex h-[68px] items-center justify-around border-t border-line bg-card pb-1.5 md:hidden">
      <NavLink to="/overview" className={({ isActive }) => on(isActive)}><Icon name="overview" size={21} />Overview</NavLink>
      <NavLink to="/calendar" className={({ isActive }) => on(isActive)}><Icon name="calendar" size={21} />Calendar</NavLink>
      <NavLink to="/journal" aria-label="Journal" className={({ isActive }) => clsx('-mt-5 flex size-14 flex-col items-center justify-center rounded-2xl bg-accent text-white shadow-lg', isActive && 'ring-4 ring-accent/25')}><Icon name="journal" size={24} /></NavLink>
      <NavLink to="/ideal" className={({ isActive }) => on(isActive)}><Icon name="ideal" size={21} />Ideal</NavLink>
      <DM.Root>
        <DM.Trigger className={tab} aria-label="More"><Icon name="more" size={21} />More</DM.Trigger>
        <DM.Portal>
          <DM.Content side="top" align="end" sideOffset={10} className="z-50 min-w-44 rounded-xl border border-line bg-card p-1.5 shadow-xl">
            {[{ to: '/tasks', label: 'Tasks', icon: 'tasks' }, { to: '/tags', label: 'Tags', icon: 'tag' }, { to: '/settings', label: 'Settings', icon: 'settings' }].map((i) => (
              <DM.Item key={i.to} onSelect={() => nav(i.to)} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 text-sm outline-none data-[highlighted]:bg-line2"><Icon name={i.icon as IconName} size={17} />{i.label}</DM.Item>
            ))}
            <DM.Item onSelect={() => logout.mutate(false, { onSettled: () => nav('/login') })} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-3 text-sm text-bad outline-none data-[highlighted]:bg-line2"><Icon name="logout" size={17} />Sign out</DM.Item>
          </DM.Content>
        </DM.Portal>
      </DM.Root>
    </nav>
  )
}

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <OfflineBanner />
      <div className="flex flex-1">
        <Sidebar />
        <main className="min-w-0 flex-1 pb-24 md:pb-0"><Outlet /></main>
      </div>
      <BottomTabs />
      <Toaster />
    </div>
  )
}
