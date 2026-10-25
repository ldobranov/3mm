import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({
  getToken: vi.fn(() => 'test-token'),
  refreshToken: vi.fn(async () => true),
  clearAuth: vi.fn(),
}))
vi.mock('@/utils/auth', () => auth)
vi.mock('@/utils/compiled-ui', () => ({
  getCompiledUiCatalog: vi.fn(async () => []),
  loadCompiledComponent: vi.fn(),
}))

const json = (data: unknown, status = 200) => ({
  ok: status === 200,
  status,
  json: async () => data,
})
let fetcher: ReturnType<typeof vi.fn>
beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  auth.getToken.mockReturnValue('test-token')
  localStorage.clear()
  fetcher = vi.fn(async (url: string) =>
    json(url === '/runtime-config.json' ? { backend_url: '' } : { items: [] }),
  )
  vi.stubGlobal('fetch', fetcher)
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('shared bootstrap data and authentication transport', () => {
  it('bootstraps a fresh HTTPS browser from the proxy config without guessing public :8887', async () => {
    vi.stubGlobal('location', { protocol: 'https:', hostname: '3mm.example.test' })
    fetcher.mockResolvedValue(json({ backend_url: 'https://api.3mm.example.test/' }))
    const { getBackendUrl } = await import('./runtime-config')
    expect(await getBackendUrl()).toBe('https://api.3mm.example.test')
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/runtime-config.json'])
  })

  it('does not consult a stored Core URL when the shipped port config already resolved', async () => {
    vi.stubGlobal('location', { protocol: 'https:', hostname: '3mm.example.test' })
    fetcher.mockImplementation(async (url: string) =>
      json(
        url === '/runtime-config.json'
          ? { backend_port: 8887 }
          : { backend_url: 'https://api.3mm.example.test' },
      ),
    )
    const { getBackendUrl } = await import('./runtime-config')
    expect(await getBackendUrl()).toBe('https://3mm.example.test:8887')
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual(['/runtime-config.json'])
  })

  it('uses the stored URL fallback only when runtime config is unavailable', async () => {
    vi.stubGlobal('location', { protocol: 'https:', hostname: '3mm.example.test' })
    fetcher.mockImplementation(async (url: string) =>
      url === '/runtime-config.json'
        ? json({}, 404)
        : json({ backend_url: 'https://api.3mm.example.test' }),
    )
    const { getBackendUrl } = await import('./runtime-config')
    expect(await getBackendUrl()).toBe('https://api.3mm.example.test')
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      '/runtime-config.json',
      '/frontend-config',
    ])
  })

  it('keeps a browser override ahead of the proxy config until explicitly cleared', async () => {
    vi.stubGlobal('location', { protocol: 'https:', hostname: '3mm.example.test' })
    localStorage.setItem('mm_backend_url_override', 'https://old.example.test/')
    fetcher.mockResolvedValue(json({ backend_url: 'https://api.3mm.example.test' }))
    const { getBackendUrl, clearBackendOverride } = await import('./runtime-config')
    expect(await getBackendUrl()).toBe('https://old.example.test')
    expect(fetcher).not.toHaveBeenCalled()
    clearBackendOverride()
    expect(await getBackendUrl()).toBe('https://api.3mm.example.test')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('does no discovery from ordinary requests, preserves bearer auth and Unicode', async () => {
    const { default: http } = await import('./dynamic-http')
    const adapter = vi.fn(async (config: any) => ({
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }))
    await Promise.all(Array.from({ length: 30 }, () => http.get('/private', { adapter })))
    await http.post('/private', { name: 'Български' }, { adapter })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(adapter).toHaveBeenCalledTimes(31)
    expect(adapter.mock.calls[30][0].headers.Authorization).toBe('Bearer test-token')
    expect(JSON.parse(adapter.mock.calls[30][0].data).name).toBe('Български')
  })

  it('bounds repeated GET network failures and does not replay uncertain POSTs', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { default: http } = await import('./dynamic-http')
    const adapter = vi.fn(async (config: any) => {
      throw Object.assign(new Error('offline'), { code: 'ERR_NETWORK', config })
    })
    await expect(http.get('/private', { adapter })).rejects.toThrow('offline')
    expect(adapter).toHaveBeenCalledTimes(2)
    adapter.mockClear()
    await expect(http.post('/commands', {}, { adapter })).rejects.toThrow('offline')
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(auth.clearAuth).not.toHaveBeenCalled()
  })

  it('does not refresh or log out on authorization denial or anonymous 401', async () => {
    const { default: http } = await import('./dynamic-http')
    const adapter = vi.fn(async (config: any) => {
      throw Object.assign(new Error('denied'), { response: { status: 403 }, config })
    })
    await expect(http.get('/private', { adapter })).rejects.toThrow('denied')
    adapter.mockImplementation(async (config: any) => {
      throw Object.assign(new Error('unauthorized'), { response: { status: 401 }, config })
    })
    auth.getToken.mockReturnValue('')
    await expect(http.get('/private', { adapter })).rejects.toThrow('unauthorized')
    expect(auth.refreshToken).not.toHaveBeenCalled()
    expect(auth.clearAuth).not.toHaveBeenCalled()
  })

  it('still refreshes an authenticated expired session once', async () => {
    const { default: http } = await import('./dynamic-http')
    let count = 0
    const adapter = vi.fn(async (config: any) => {
      if (++count === 1)
        throw Object.assign(new Error('expired'), { response: { status: 401 }, config })
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    })
    await http.get('/private', { adapter })
    expect(auth.refreshToken).toHaveBeenCalledTimes(1)
    expect(adapter).toHaveBeenCalledTimes(2)
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('aborts stalled bootstrap fetches within five seconds', async () => {
    vi.useFakeTimers()
    const { bootstrapJson } = await import('./bootstrap-cache')
    fetcher.mockImplementation(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          options.signal?.addEventListener('abort', () => reject(new Error('aborted')))
        }),
    )
    const request = expect(bootstrapJson('/stalled')).rejects.toThrow('aborted')
    await vi.advanceTimersByTimeAsync(5000)
    await request
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('retains a verified backend URL during outage and retries after shared cooldown', async () => {
    vi.useFakeTimers()
    const { getBackendUrl } = await import('./runtime-config')
    fetcher.mockResolvedValue(json({ backend_url: 'https://api.example.test' }))
    expect(await getBackendUrl()).toBe('https://api.example.test')
    vi.advanceTimersByTime(5 * 60_000 + 1)
    fetcher.mockRejectedValue(new Error('offline'))
    expect(await Promise.all(Array.from({ length: 20 }, () => getBackendUrl()))).toEqual(
      Array(20).fill('https://api.example.test'),
    )
    await Promise.all(Array.from({ length: 20 }, () => getBackendUrl()))
    expect(fetcher).toHaveBeenCalledTimes(3)
    vi.advanceTimersByTime(30_001)
    fetcher.mockResolvedValue(json({ backend_url: 'https://recovered.example.test' }))
    expect(await getBackendUrl()).toBe('https://recovered.example.test')
    expect(fetcher).toHaveBeenCalledTimes(4)
  })


})
