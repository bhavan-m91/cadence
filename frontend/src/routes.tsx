import { lazy, Suspense } from 'react'
import { Navigate, createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { PublicOnly, RouteGuard, Splash } from '@/components/layout/RouteGuard'
import { EmptyState } from '@/components/ui/Feedback'
import { ForgotPasswordPage, LoginPage, RegisterPage, ResetPasswordPage, VerifyEmailPage } from '@/features/auth/pages'
import { OnboardingPage } from '@/features/onboarding/OnboardingPage'

// Feature pages are code-split so the first load stays small (charts and the calendar are the heavy parts).
const OverviewPage = lazy(() => import('@/features/overview/OverviewPage').then((m) => ({ default: m.OverviewPage })))
const CalendarPage = lazy(() => import('@/features/calendar/CalendarPage').then((m) => ({ default: m.CalendarPage })))
const TasksPage = lazy(() => import('@/features/tasks/TasksPage').then((m) => ({ default: m.TasksPage })))
const TagsPage = lazy(() => import('@/features/tags/TagsPage').then((m) => ({ default: m.TagsPage })))
const SettingsPage = lazy(() => import('@/features/settings/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const JournalPage = lazy(() => import('@/features/journal/JournalPage').then((m) => ({ default: m.JournalPage })))
const ReviewPage = lazy(() => import('@/features/review/ReviewPage').then((m) => ({ default: m.ReviewPage })))
const JournalHistoryPage = lazy(() => import('@/features/journal/HistoryPage').then((m) => ({ default: m.HistoryPage })))
const EntryPage = lazy(() => import('@/features/journal/EntryPage').then((m) => ({ default: m.EntryPage })))
const IdealPage = lazy(() => import('@/features/ideal/IdealPage').then((m) => ({ default: m.IdealPage })))

const page = (el: React.ReactNode) => <Suspense fallback={<Splash />}>{el}</Suspense>

export const router = createBrowserRouter([
  { element: <PublicOnly />, children: [
    { path: '/login', element: <LoginPage /> },
    { path: '/register', element: <RegisterPage /> },
    { path: '/forgot-password', element: <ForgotPasswordPage /> },
  ] },
  // Reset and verify links work whether or not someone is signed in.
  { path: '/reset-password', element: <ResetPasswordPage /> },
  { path: '/verify-email', element: <VerifyEmailPage /> },
  { element: <RouteGuard />, children: [
    { path: '/onboarding', element: <OnboardingPage /> },
    { element: <AppShell />, children: [
      { path: '/', element: <Navigate to="/overview" replace /> },
      { path: '/overview', element: page(<OverviewPage />) },
      { path: '/journal', element: page(<JournalPage />) },
      { path: '/journal/history', element: page(<JournalHistoryPage />) },
      { path: '/journal/:entryId', element: page(<EntryPage />) },
      { path: '/journal/:entryId/review', element: page(<ReviewPage />) },
      { path: '/calendar', element: page(<CalendarPage />) },
      { path: '/activities/:activityId', element: page(<CalendarPage />) },
      { path: '/tasks', element: page(<TasksPage />) },
      { path: '/tasks/:taskId', element: page(<TasksPage />) },
      { path: '/tags', element: page(<TagsPage />) },
      { path: '/ideal', element: page(<IdealPage />) },
      { path: '/settings', element: <Navigate to="/settings/profile" replace /> },
      { path: '/settings/:section', element: page(<SettingsPage />) },
      { path: '*', element: <EmptyState icon="info" title="Page not found">That page does not exist.</EmptyState> },
    ] },
  ] },
  { path: '*', element: <Navigate to="/overview" replace /> },
])
