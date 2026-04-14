/**
 * Normalize Axios / API failures into a single user-facing string.
 * Handles JSON bodies, `details` from consistency checks, and logical rejections
 * where we attach a synthetic `response` on the Error.
 */
export function extractApiError(error) {
  const d = error?.response?.data
  if (d == null || d === '') {
    return error?.message || 'Unknown error'
  }
  if (typeof d === 'string') {
    return d.length > 500 ? `${d.slice(0, 500)}…` : d
  }
  if (typeof d === 'object') {
    const nested = d.details
    if (nested && typeof nested === 'object' && Array.isArray(nested.errors) && nested.errors.length) {
      return nested.errors.map(String).join('; ')
    }
    if (Array.isArray(d.errors) && d.errors.length) {
      return d.errors.map(String).join('; ')
    }
    if (d.error != null && String(d.error).trim()) {
      return String(d.error)
    }
    if (d.message != null && String(d.message).trim()) {
      return String(d.message)
    }
  }
  return error?.message || 'Unknown error'
}
