import type { Config } from 'tailwindcss'

const v = (name: string) => `var(--${name})`
/** Colours that take an opacity modifier (bg-bad/10): the token stays a CSS variable so dark mode keeps working. */
const va = (name: string) => `color-mix(in srgb, var(--${name}) calc(<alpha-value> * 100%), transparent)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        ink: va('ink'), muted: v('muted'), faint: v('faint'), line: v('line'), line2: v('line2'), card: v('card'), paper: v('paper'),
        ghost: v('ghost'), ghostline: v('ghostline'), accent: va('accent'), 'accent-ink': v('accentInk'), tint: v('tintA'), tint2: v('tintA2'),
        sleep: v('sleep'), violet: v('violet'), teal: v('teal'), sky: v('sky'), rose: v('rose'), good: va('good'), warn: va('warn'), bad: va('bad'),
      },
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'], display: ['"Space Grotesk"', 'sans-serif'] },
      boxShadow: { card: 'var(--shadow)' },
      letterSpacing: { tightish: '-0.01em', tighter2: '-0.025em' },
    },
  },
  plugins: [],
} satisfies Config
