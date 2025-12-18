export type CurrencyPosition = 'prefix' | 'suffix'

export type CurrencyFormat = {
  label: string
  position: CurrencyPosition
}

export const DEFAULT_CURRENCY_FORMATS: Record<string, CurrencyFormat> = {
  USD: { label: '$', position: 'prefix' },
  EUR: { label: '€', position: 'prefix' },
  GBP: { label: '£', position: 'prefix' },
  BGN: { label: 'лв', position: 'suffix' },
  JPY: { label: '¥', position: 'prefix' },
  CAD: { label: 'C$', position: 'prefix' },
  AUD: { label: 'A$', position: 'prefix' }
}

export function formatCurrency(
  amount: unknown,
  currencyCode: string = 'USD',
  currencyFormats?: Record<string, CurrencyFormat>
): string {
  const code = (currencyCode || 'USD').toString().trim().toUpperCase()

  const fmt = (currencyFormats && currencyFormats[code]) || DEFAULT_CURRENCY_FORMATS[code]

  const label = (fmt?.label || DEFAULT_CURRENCY_FORMATS[code]?.label || code).toString()
  const position = (fmt?.position || DEFAULT_CURRENCY_FORMATS[code]?.position || 'prefix') as CurrencyPosition

  const amountStr = (() => {
    if (amount === null || amount === undefined) return '0'
    if (typeof amount === 'number') return `${amount}`
    if (typeof amount === 'string') return amount
    // e.g. Decimal-like objects
    try {
      return `${amount as any}`
    } catch {
      return '0'
    }
  })()

  if (position === 'suffix') return `${amountStr} ${label}`.trim()
  return `${label}${amountStr}`.trim()
}

