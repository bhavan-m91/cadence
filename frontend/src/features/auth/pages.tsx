import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { useForgotPassword, useLogin, useRegister, useResetPassword, useVerifyEmail } from '@/api/hooks/useAuth'
import { errorMessage, fieldErrors } from '@/api/errors'
import { Button } from '@/components/ui/Button'
import { Field, Input } from '@/components/ui/Field'
import { Icon } from '@/components/ui/Icon'
import { browserTimezone } from '@/lib/time'
import { AuthLayout } from './AuthLayout'

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
const safeNext = (n: string | null) => (n && n.startsWith('/') && !n.startsWith('//') ? n : '/overview')

function GoogleButton({ next }: { next: string }) {
  const [err, setErr] = useState<string>()
  async function go() {
    setErr(undefined)
    try {
      // The server answers 302 when Google is configured and 501 JSON otherwise.
      const r = await fetch(`${BASE}/api/v1/auth/google/start?redirect=${encodeURIComponent(next)}`, { redirect: 'manual' })
      if (r.type === 'opaqueredirect' || r.status === 0 || r.status === 302) window.location.href = `${BASE}/api/v1/auth/google/start?redirect=${encodeURIComponent(next)}`
      else setErr('Google sign-in is not set up on this server.')
    } catch {
      setErr('Cannot reach the server.')
    }
  }
  return (
    <>
      <button type="button" onClick={go} className="flex h-[46px] items-center justify-center gap-2.5 rounded-[11px] border border-line bg-card text-[13.5px] font-semibold hover:border-ghostline">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden><path fill="#4285F4" d="M22.5 12.2c0-.8-.1-1.5-.2-2.2H12v4.2h5.9a5 5 0 0 1-2.2 3.3v2.7h3.5c2.1-1.9 3.3-4.7 3.3-8z" /><path fill="#34A853" d="M12 23c3 0 5.4-1 7.2-2.7l-3.5-2.7c-1 .7-2.2 1.1-3.7 1.1-2.9 0-5.3-1.9-6.2-4.5H2.2v2.8A11 11 0 0 0 12 23z" /><path fill="#FBBC05" d="M5.8 14.2a6.6 6.6 0 0 1 0-4.3V7.1H2.2a11 11 0 0 0 0 9.9z" /><path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.1-3.1A11 11 0 0 0 2.2 7.1l3.6 2.8C6.7 7.3 9.1 5.4 12 5.4z" /></svg>
        Continue with Google
      </button>
      {err && <p role="alert" className="-mt-2 text-xs text-bad">{err}</p>}
    </>
  )
}

const Or = () => <div className="flex items-center gap-3 text-[11.5px] text-faint"><i className="h-px flex-1 bg-line" />or with email<i className="h-px flex-1 bg-line" /></div>

// ---------------------------------------------------------------------------------------------------- login
const loginSchema = z.object({ email: z.string().email('Enter a valid email'), password: z.string().min(1, 'Enter your password'), remember: z.boolean() })

export function LoginPage() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const nav = useNavigate()
  const login = useLogin()
  const [show, setShow] = useState(false)
  const { register, handleSubmit, formState: { errors } } = useForm<z.infer<typeof loginSchema>>({ resolver: zodResolver(loginSchema), defaultValues: { remember: true } })
  const submit = handleSubmit((v) => login.mutate(v, { onSuccess: () => nav(next, { replace: true }) }))
  return (
    <AuthLayout title="Welcome back" subtitle="Sign in to log your day." aside={<span>New to Cadence? <Link to="/register" className="font-semibold text-accent-ink">Create an account</Link></span>}>
      <GoogleButton next={next} />
      <Or />
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <Field label="Email" error={errors.email?.message}>{(id, d) => <Input id={id} aria-describedby={d} type="email" autoComplete="email" placeholder="you@example.com" invalid={!!errors.email} {...register('email')} />}</Field>
        <Field label="Password" error={errors.password?.message} action={<Link to="/forgot-password" className="font-semibold text-accent-ink">Forgot?</Link>}>
          {(id, d) => (
            <div className="relative">
              <Input id={id} aria-describedby={d} type={show ? 'text' : 'password'} autoComplete="current-password" className="pr-11" invalid={!!errors.password} {...register('password')} />
              <button type="button" aria-label={show ? 'Hide password' : 'Show password'} onClick={() => setShow(!show)} className="absolute right-1.5 top-1.5 flex size-8 items-center justify-center rounded-lg text-muted hover:text-ink"><Icon name={show ? 'eyeOff' : 'eye'} size={17} /></button>
            </div>
          )}
        </Field>
        <label className="flex items-center gap-2 text-[12.5px] text-muted"><input type="checkbox" className="size-4 accent-[var(--accent)]" {...register('remember')} />Keep me signed in on this device</label>
        {login.error && <p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{errorMessage(login.error)}</p>}
        <Button type="submit" variant="primary" size="lg" loading={login.isPending}>Sign in <Icon name="arrowRight" size={16} strokeWidth={2.2} /></Button>
      </form>
      <p className="text-center text-[11px] leading-normal text-faint">Your journal stays private. It is never shared.</p>
    </AuthLayout>
  )
}

// ---------------------------------------------------------------------------------------------------- register
const registerSchema = z.object({
  display_name: z.string().trim().min(1, 'Tell us what to call you').max(80),
  email: z.string().email('Enter a valid email'),
  password: z.string().min(10, 'Use at least 10 characters'),
})

export function RegisterPage() {
  const nav = useNavigate()
  const reg = useRegister()
  const { register, handleSubmit, setError, formState: { errors } } = useForm<z.infer<typeof registerSchema>>({ resolver: zodResolver(registerSchema) })
  const submit = handleSubmit((v) =>
    reg.mutate({ ...v, timezone: browserTimezone() }, {
      onSuccess: () => nav('/onboarding', { replace: true }),
      onError: (e) => { const f = fieldErrors(e); if (f.password) setError('password', { message: errorMessage(e) }) },
    }))
  return (
    <AuthLayout title="Create your account" subtitle="Two minutes to set up, then log your day." aside={<span>Have an account? <Link to="/login" className="font-semibold text-accent-ink">Sign in</Link></span>}>
      <GoogleButton next="/overview" />
      <Or />
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <Field label="Name" error={errors.display_name?.message}>{(id, d) => <Input id={id} aria-describedby={d} autoComplete="name" invalid={!!errors.display_name} {...register('display_name')} />}</Field>
        <Field label="Email" error={errors.email?.message}>{(id, d) => <Input id={id} aria-describedby={d} type="email" autoComplete="email" invalid={!!errors.email} {...register('email')} />}</Field>
        <Field label="Password" hint="At least 10 characters." error={errors.password?.message}>{(id, d) => <Input id={id} aria-describedby={d} type="password" autoComplete="new-password" invalid={!!errors.password} {...register('password')} />}</Field>
        {reg.error && !errors.password && <p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{errorMessage(reg.error)}</p>}
        <Button type="submit" variant="primary" size="lg" loading={reg.isPending}>Create account <Icon name="arrowRight" size={16} strokeWidth={2.2} /></Button>
      </form>
    </AuthLayout>
  )
}

// ---------------------------------------------------------------------------------------------------- forgot / reset / verify
export function ForgotPasswordPage() {
  const forgot = useForgotPassword()
  const { register, handleSubmit, formState: { errors } } = useForm<{ email: string }>({ resolver: zodResolver(z.object({ email: z.string().email('Enter a valid email') })) })
  return (
    <AuthLayout title="Reset your password" subtitle="We will email you a link that works once for an hour." aside={<Link to="/login" className="font-semibold text-accent-ink">Back to sign in</Link>}>
      {forgot.isSuccess ? (
        <p role="status" className="rounded-xl bg-tint p-4 text-[13.5px] leading-relaxed">If that email has an account, a reset link is on its way. Check your inbox.</p>
      ) : (
        <form onSubmit={handleSubmit((v) => forgot.mutate(v.email))} noValidate className="flex flex-col gap-4">
          <Field label="Email" error={errors.email?.message}>{(id, d) => <Input id={id} aria-describedby={d} type="email" autoComplete="email" invalid={!!errors.email} {...register('email')} />}</Field>
          {forgot.error && <p role="alert" className="text-[13px] text-bad">{errorMessage(forgot.error)}</p>}
          <Button type="submit" variant="primary" size="lg" loading={forgot.isPending}>Send reset link</Button>
        </form>
      )}
    </AuthLayout>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const reset = useResetPassword()
  const nav = useNavigate()
  const { register, handleSubmit, formState: { errors } } = useForm<{ password: string }>({ resolver: zodResolver(z.object({ password: z.string().min(10, 'Use at least 10 characters') })) })
  return (
    <AuthLayout title="Choose a new password" subtitle="You will be signed out of other devices.">
      {reset.isSuccess ? (
        <div className="flex flex-col gap-3"><p role="status" className="rounded-xl bg-tint p-4 text-[13.5px]">Password updated.</p><Button variant="primary" size="lg" onClick={() => nav('/login')}>Sign in</Button></div>
      ) : (
        <form onSubmit={handleSubmit((v) => reset.mutate({ token, password: v.password }))} noValidate className="flex flex-col gap-4">
          <Field label="New password" hint="At least 10 characters." error={errors.password?.message}>{(id, d) => <Input id={id} aria-describedby={d} type="password" autoComplete="new-password" invalid={!!errors.password} {...register('password')} />}</Field>
          {reset.error && <p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{errorMessage(reset.error)}</p>}
          <Button type="submit" variant="primary" size="lg" loading={reset.isPending} disabled={!token}>Update password</Button>
        </form>
      )}
    </AuthLayout>
  )
}

export function VerifyEmailPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const verify = useVerifyEmail()
  useEffect(() => { if (token) verify.mutate(token) }, [token]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <AuthLayout title="Verifying your email">
      {verify.isPending && <p role="status" className="text-sm text-muted">One moment…</p>}
      {verify.isSuccess && <><p role="status" className="rounded-xl bg-tint p-4 text-[13.5px]">Your email is verified.</p><Link to="/overview" className="text-center text-sm font-semibold text-accent-ink">Continue to Cadence</Link></>}
      {(verify.isError || !token) && <><p role="alert" className="rounded-lg bg-bad/10 px-3 py-2 text-[13px] text-bad">{token ? errorMessage(verify.error) : 'This link is incomplete.'}</p><Link to="/settings/profile" className="text-center text-sm font-semibold text-accent-ink">Send a new link from Settings</Link></>}
    </AuthLayout>
  )
}
