export const PALETTE = ['#3E86D4', '#1C9C8D', '#8A6CE6', '#DB5E86', '#C27C22', '#2E9E6B', '#5E6582', '#4C63E6']

/** A translucent tint of a category/tag colour that stays readable in both themes. */
export const tint = (hex: string, pct = 16) => `color-mix(in srgb, ${hex} ${pct}%, var(--card))`
export const edge = (hex: string, pct = 55) => `color-mix(in srgb, ${hex} ${pct}%, var(--card))`
