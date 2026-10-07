/** One bounded request per resource, including during outages and concurrent startup. */
export class BootstrapCache<T> {
  private value: T | undefined
  private expires = 0
  private retryAfter = 0
  private failure: unknown
  private pending: Promise<T> | null = null
  private generation = 0

  constructor(
    private ttl: number,
    private backoff = 30_000,
  ) {}

  peek(): T | undefined {
    return this.value
  }

  invalidate() {
    ++this.generation
    this.value = undefined
    this.expires = this.retryAfter = 0
    this.pending = null
  }

  load(loader: () => Promise<T>, refresh = false): Promise<T> {
    if (this.pending) return this.pending
    if (Date.now() < this.retryAfter) {
      return this.value !== undefined ? Promise.resolve(this.value) : Promise.reject(this.failure)
    }
    if (!refresh && this.value !== undefined && Date.now() < this.expires)
      return Promise.resolve(this.value)
    const generation = this.generation
    const request = Promise.resolve()
      .then(loader)
      .then((value) => {
        if (generation === this.generation) {
          this.value = value
          this.expires = Date.now() + this.ttl
          this.retryAfter = 0
        }
        return value
      })
      .catch((error) => {
        if (generation === this.generation) {
          this.failure = error
          this.retryAfter = Date.now() + this.backoff
          if (this.value !== undefined) return this.value
        }
        throw error
      })
      .finally(() => {
        if (this.pending === request) this.pending = null
      })
    this.pending = request
    return request
  }
}

export async function bootstrapJson(url: string): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal })
    if (!response.ok) throw new Error(`Bootstrap request failed (${response.status})`)
    return await response.json()
  } finally {
    clearTimeout(timer)
  }
}
