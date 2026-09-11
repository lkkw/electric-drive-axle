/**
 * Resolve a shadcn-vue CSS variable into a canvas-safe color for ECharts.
 * ECharts renders on canvas, so CSS var(...) values cannot be passed through
 * reliably as series or axis colors.
 */
export function resolveCssColor(variable: string, fallback: string, alpha = 1): string {
  if (typeof document === 'undefined') {
    return fallback
  }

  const styles = getComputedStyle(document.documentElement)
  const cssColor = styles.getPropertyValue(variable).trim()
  if (!cssColor) {
    return fallback
  }

  const canvas = document.createElement('canvas')
  canvas.width = 1
  canvas.height = 1
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) {
    return fallback
  }

  try {
    context.clearRect(0, 0, 1, 1)
    context.fillStyle = cssColor
    context.fillRect(0, 0, 1, 1)
    const [red, green, blue, sourceAlpha] = context.getImageData(0, 0, 1, 1).data
    const resolvedAlpha = Math.min(alpha, sourceAlpha / 255)
    return `rgba(${red}, ${green}, ${blue}, ${resolvedAlpha})`
  } catch {
    return fallback
  }
}
