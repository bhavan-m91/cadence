import type { Config } from 'tailwindcss'

const v = (name: string) => `var(--${name})`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        ink: v('ink'), muted: v('muted'), faint: v('faint'), line: v('line'), line2: v('line2'), card: v('card'), paper: v('paper'),
        ghost: v('ghost'), ghostline: v('ghostline'), accent: v('accent'), 'accent-ink': v('accentInk'), tint: v('tintA'), tint2: v('tintA2'),
        sleep: v('sleep'), violet: v('violet'), teal: v('teal'), sky: v('sky'), rose: v('rose'), good: v('good'), warn: v('warn'), bad: v('bad'),
      },
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'], display: ['"Space Grotesk"', 'sans-serif'] },
      boxShadow: { card: 'var(--shadow)' },
      letterSpacing: { tightish: '-0.01em', tighter2: '-0.025em' },
    },
  },
  plugins: [],
} satisfies Config
