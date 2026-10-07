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
  it('shares exactly one config and catalog request across router, i18n and relationships', async () => {
    const { getExtensionCatalog } = await import('./extension-catalog')
    const { i18n } = await import('./i18n')
    const { extensionRelationships } = await import('./extension-relationships')
    const { createRouterWithDynamicRoutes } = await import('@/router')
    await Promise.all([
      ...Array.from({ length: 30 }, () => getExtensionCatalog()),
      i18n.loadExtensionTranslationsForEnabledExtensions(),
      extensionRelationships.initialize(),
      createRouterWithDynamicRoutes(),
    ])
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      '/runtime-config.json',
      '/api/extensions/public',
    ])
    expect(extensionRelationships.getDiscoveredExtensions()).toEqual([])
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

  it('does not refresh or log out on authorization denial or anonymous/public 401', async () => {
    const { default: http } = await import('./dynamic-http')
    const adapter = vi.fn(async (config: any) => {
      throw Object.assign(new Error('denied'), { response: { status: 403 }, config })
    })
    await expect(http.get('/private', { adapter })).rejects.toThrow('denied')
    adapter.mockImplementation(async (config: any) => {
      throw Object.assign(new Error('unauthorized'), { response: { status: 401 }, config })
    })
    await expect(http.get('/api/extensions/public', { adapter })).rejects.toThrow('unauthorized')
    expect(adapter.mock.calls[1][0].headers.Authorization).toBeUndefined()
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

  it('uses a shared failure backoff and retains verified catalog until recovery', async () => {
    vi.useFakeTimers()
    const { getExtensionCatalog } = await import('./extension-catalog')
    await getExtensionCatalog()
    vi.advanceTimersByTime(10 * 60_000 + 1)
    fetcher.mockRejectedValue(new Error('offline'))
    await Promise.all(Array.from({ length: 30 }, () => getExtensionCatalog()))
    const attempts = fetcher.mock.calls.length
    await Promise.all(Array.from({ length: 30 }, () => getExtensionCatalog(true)))
    expect(fetcher).toHaveBeenCalledTimes(attempts)
    vi.advanceTimersByTime(30_001)
    fetcher.mockResolvedValue(json({ items: [{ name: 'generic', version: '2.0.0' }] }))
    expect(await getExtensionCatalog()).toMatchObject([{ name: 'generic', version: '2.0.0' }])
  })

  it('coalesces malformed/failed first catalog reads instead of hammering the server', async () => {
    const { getExtensionCatalog } = await import('./extension-catalog')
    fetcher.mockImplementation(async (url: string) =>
      json(url === '/runtime-config.json' ? { backend_url: '' } : { items: 'invalid' }),
    )
    await Promise.allSettled(Array.from({ length: 20 }, () => getExtensionCatalog()))
    await Promise.allSettled(Array.from({ length: 20 }, () => getExtensionCatalog()))
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('rejects malformed route metadata without breaking synchronous auth decisions', async () => {
    const { getExtensionCatalog, isPublicEndpoint } = await import('./extension-catalog')
    fetcher.mockImplementation(async (url: string) =>
      json(
        url === '/runtime-config.json'
          ? { backend_url: '' }
          : [{ name: 'generic', version: '1.0.0', frontend_routes: {} }],
      ),
    )
    await expect(getExtensionCatalog()).rejects.toThrow('Invalid public extension catalog')
    expect(isPublicEndpoint('/private')).toBe(false)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it.each([false, true])(
    'ignores a stale catalog response/failure after URL changes (%s)',
    async (lateFailure) => {
      const { default: http } = await import('./dynamic-http')
      const { getExtensionCatalog } = await import('./extension-catalog')
      let finish!: (data: ReturnType<typeof json>) => void
      fetcher.mockImplementation((url: string) =>
        url === '/api/extensions/public'
          ? new Promise((resolve, reject) => {
              finish = (data) =>
                lateFailure ? reject(new Error('old backend offline')) : resolve(data)
            })
          : Promise.resolve(
              json(
                url === '/runtime-config.json'
                  ? { backend_url: '' }
                  : [{ name: 'new', version: '1.0.0' }],
              ),
            ),
      )
      const old = getExtensionCatalog()
      await vi.waitFor(() => expect(finish).toBeDefined())
      await http.setBackendUrlOverride('https://new.example.test')
      const current = getExtensionCatalog()
      finish(json([{ name: 'old', version: '1.0.0' }]))
      expect(await old).toEqual(await current)
      expect(await current).toMatchObject([{ name: 'new' }])
      expect(fetcher).toHaveBeenCalledTimes(3)
    },
  )

  it('reflects enable/disable and version rollback from the shared authoritative catalog', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { extensionRelationships } = await import('./extension-relationships')
    let items = [{ name: 'generic', version: '2.0.0' }]
    fetcher.mockImplementation(async (url: string) =>
      json(url === '/runtime-config.json' ? { backend_url: '' } : { items }),
    )
    await extensionRelationships.initialize()
    expect(extensionRelationships.getExtensionVersion('generic')).toBe('2.0.0')
    items = [{ name: 'generic', version: '1.0.0' }]
    await extensionRelationships.refreshExtensions()
    expect(extensionRelationships.getExtensionVersion('generic')).toBe('1.0.0')
    items = []
    await extensionRelationships.refreshExtensions()
    expect(extensionRelationships.getDiscoveredExtensions()).toEqual([])
    expect(fetcher).toHaveBeenCalledTimes(4)
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

  it('preserves empty same-origin override and invalidates discovery on URL changes', async () => {
    const { default: http } = await import('./dynamic-http')
    const { getExtensionCatalog } = await import('./extension-catalog')
    await getExtensionCatalog()
    await http.setBackendUrlOverride('https://new.example.test/')
    expect(await http.getCurrentBackendUrl()).toBe('https://new.example.test')
    await getExtensionCatalog()
    expect(fetcher.mock.calls.at(-1)?.[0]).toBe('https://new.example.test/api/extensions/public')
    await http.setBackendUrlOverride('')
    expect(await http.getCurrentBackendUrl()).toBe('')
    expect(fetcher.mock.calls.filter(([url]) => url === '/runtime-config.json')).toHaveLength(1)
    await http.clearBackendUrlOverride()
    expect(await http.getCurrentBackendUrl()).toBe('')
    expect(fetcher.mock.calls.filter(([url]) => url === '/runtime-config.json')).toHaveLength(2)
  })

  it('matches cached public routes by path boundary, without concrete module-name heuristics', async () => {
    const { getExtensionCatalog, isPublicEndpoint } = await import('./extension-catalog')
    fetcher.mockImplementation(async (url: string) =>
      json(
        url === '/runtime-config.json'
          ? { backend_url: '' }
          : {
              items: [
                {
                  name: 'generic',
                  version: '1.0.0',
                  frontend_routes: [{ path: '/extension/info', meta: { requiresAuth: false } }],
                },
              ],
            },
      ),
    )
    await getExtensionCatalog()
    expect(isPublicEndpoint('/api/extension/generic/info?x=1')).toBe(true)
    expect(isPublicEndpoint('/api/extension/generic/info/details')).toBe(true)
    expect(isPublicEndpoint('/api/extension/generic/information')).toBe(false)
    expect(isPublicEndpoint('/api/market/admin')).toBe(false)
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})
