/** Call only for a reviewed diagnostic projection, following an explicit operator action. */
export function saveDiagnosticJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  try {
    const link = document.createElement('a')
    link.href = url; link.download = filename; link.click()
  } finally { URL.revokeObjectURL(url) }
}
