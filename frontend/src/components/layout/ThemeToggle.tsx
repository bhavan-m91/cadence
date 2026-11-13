import { useUpdateProfile } from '@/api/hooks/useSettings'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { IconButton } from '../ui/Button'

export function ThemeToggle() {
  const resolved = useThemeStore((s) => s.resolved)
  const toggle = useThemeStore((s) => s.toggle)
  const authed = useAuthStore((s) => s.status === 'authed')
  const update = useUpdateProfile()
  return (
    <IconButton
      icon={resolved === 'dark' ? 'sun' : 'moon'} label={resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={() => {
        const next = toggle()
        if (authed) update.mutate({ theme: next }) // remember it on the account; failure is harmless
      }}
    />
  )
}
