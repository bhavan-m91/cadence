import { ApiError } from './client'

/** Plain-language messages for error codes (PRD 4.12). Falls back to the server message. */
const MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: 'Email or password is incorrect.',
  RATE_LIMITED: 'Too many attempts. Please wait a moment and try again.',
  EMAIL_TAKEN: 'An account with that email already exists.',
  WEAK_PASSWORD: 'Choose a longer, less common password (at least 10 characters).',
  ACTIVITY_OVERLAP: 'That overlaps another activity.',
  VERSION_CONFLICT: 'This was changed somewhere else. Reload and try again.',
  NAME_TAKEN: 'That name is already in use.',
  CATEGORY_IN_USE: 'This category has activities. Merge it into another one instead.',
  CATEGORY_ALLOCATED: 'An Ideal Day or Week uses this category.',
  CATEGORY_SYSTEM: 'Work, Personal and Sleep are built in and cannot be changed this way.',
  CATEGORY_HAS_CHILDREN: 'Move or delete the child categories first.',
  CATEGORY_DEPTH_EXCEEDED: 'Categories can be at most three levels deep.',
  CROSS_ROOT_MOVE: 'A category with activities cannot move to a different root.',
  CROSS_ROOT_MERGE: 'Categories can only be merged within Work, Personal or Sleep.',
  TAG_IN_USE: 'This tag is used by activities. Merge or archive it instead.',
  ALIAS_TAKEN: 'That alias is already used.',
  SPLIT_POINT_INVALID: 'Pick a time that leaves at least 5 minutes on each side.',
  MERGE_NOT_CONTIGUOUS: 'Only back-to-back activities can be merged.',
  CATEGORY_REQUIRED: 'Choose a category for the merged activity.',
  EMAIL_NOT_VERIFIED: 'Verify your email first.',
  INVALID_TOKEN: 'This link is invalid or has expired.',
  OAUTH_NOT_CONFIGURED: 'Google sign-in is not set up on this server.',
  OAUTH_FAILED: 'Google sign-in did not complete.',
  DURATION_EXCEEDS_WINDOW: 'The duration does not fit inside that window.',
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'RATE_LIMITED' && e.retryAfter) return `Too many attempts. Try again in ${Math.ceil(e.retryAfter / 60) || 1} min.`
    return MESSAGES[e.code] ?? e.message
  }
  if (e instanceof TypeError) return 'Cannot reach the server. Check your connection.'
  return 'Something went wrong.'
}

/** Field-level messages from a 422 so forms can show them inline. */
export function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ApiError)) return {}
  const fields = (e.details?.fields ?? []) as { path: string; message: string }[]
  return Object.fromEntries(fields.map((f) => [f.path, f.message]))
}
