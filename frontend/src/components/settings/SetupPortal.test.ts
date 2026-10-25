import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { JSDOM } from 'jsdom'
import { describe, expect, it } from 'vitest'

const html = readFileSync(resolve(process.cwd(), '../setup_service/static/setup.html'), 'utf8')
const script = html.split('<script>')[1].split('</script>')[0].replace('__READ_ONLY__', 'false')
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setTimeout(resolve, 0)) }

async function portal(options: { recovery?: boolean; wifi?: boolean; fail?: boolean; saved?: Record<string, string> } = {}) {
  const dom = new JSDOM(html, { url: 'http://device.local:8895/setup#access=console-test-code', runScripts: 'outside-only' })
  const requests: Array<{ path: string; init: RequestInit }> = []
  dom.window.fetch = async (url, init = {}) => {
    const path = String(url).split('/').pop()!
    requests.push({ path, init })
    if (path === 'configure' && options.fail) throw new Error('connection lost')
    const responses: Record<string, unknown> = {
      capabilities: { roles: ['standalone', 'hub', 'node'], network_modes: ['preserve', 'local', ...(options.wifi ? ['wifi'] : [])],
        interfaces: options.wifi ? [{ name: 'wlp2s0', access_point: false }] : [], recovery: options.recovery, pending: false },
      prefill: options.saved || {}, theme: {}, configure: { enrollment: null }, finish: {}, networks: { items: [] },
    }
    return { ok: true, json: async () => responses[path] } as Response
  }
  dom.window.eval(script)
  await settle()
  const form = dom.window.document.querySelector<HTMLFormElement>('#setup-form')!
  const field = (name: string) => form.elements.namedItem(name) as HTMLInputElement
  return { dom, form, field, requests, status: () => dom.window.document.querySelector('#status')!.textContent }
}

describe('Setup portal', () => {
  it('consumes a fragment code, preserves the host network and sends no stale Wi-Fi secrets', async () => {
    const page = await portal()
    expect(page.dom.window.location.hash).toBe('')
    expect(page.form.hidden).toBe(false)
    expect(page.field('network_mode').value).toBe('preserve')
    expect((page.form.querySelector('[value="wifi"]') as HTMLOptionElement).disabled).toBe(true)
    page.field('passphrase').value = 'stale-secret'
    page.field('administrator_email').value = 'admin@example.com'
    page.field('administrator_password').value = 'admin'
    page.form.dispatchEvent(new page.dom.window.Event('submit', { cancelable: true }))
    await settle()
    const submitted = page.requests.find(item => item.path === 'configure')!
    const body = JSON.parse(submitted.init.body as string)
    expect(body.network_mode).toBe('preserve')
    expect(body.passphrase).toBeUndefined()
    expect(body.network_interface).toBeUndefined()
    expect(page.status()).toContain('Setup saved')
    page.dom.window.close()
  })

  it('shows adapter selection and a Node Hub field without an administrator form', async () => {
    const page = await portal({ wifi: true })
    page.field('role').value = 'node'
    page.field('role').dispatchEvent(new page.dom.window.Event('change'))
    expect((page.form.querySelector('#admin-fields') as HTMLFieldSetElement).disabled).toBe(true)
    expect((page.form.querySelector('#hub-field') as HTMLElement).hidden).toBe(false)
    expect(page.field('network_interface').value).toBe('wlp2s0')
    page.field('network_mode').value = 'wifi'
    page.field('network_mode').dispatchEvent(new page.dom.window.Event('change'))
    expect((page.form.querySelector('#wifi-fields') as HTMLFieldSetElement).disabled).toBe(false)
    page.dom.window.close()
  })

  it('freezes recovery identity and offers cancellation', async () => {
    const page = await portal({ recovery: true, saved: { role: 'node', device_name: 'saved-node', hub_endpoint: 'https://hub.test' } })
    expect(page.field('role').disabled).toBe(true)
    expect(page.field('device_name').value).toBe('saved-node')
    expect(page.field('hub_endpoint').disabled).toBe(true)
    expect((page.form.querySelector('#finish') as HTMLButtonElement).hidden).toBe(false)
    page.dom.window.close()
  })

  it('preserves an unset legacy Hub during network recovery', async () => {
    const page = await portal({ recovery: true, saved: { role: 'node', device_name: 'saved-node' } })
    page.form.dispatchEvent(new page.dom.window.Event('submit', { cancelable: true }))
    await settle()
    const body = JSON.parse(page.requests.find(item => item.path === 'configure')!.init.body as string)
    expect(body.hub_endpoint).toBeNull()
    page.dom.window.close()
  })

  it('does not report success after a lost connection', async () => {
    const page = await portal({ fail: true })
    page.form.dispatchEvent(new page.dom.window.Event('submit', { cancelable: true }))
    await settle()
    expect(page.status()).toContain('result is unconfirmed')
    expect(page.status()).not.toContain('Setup saved')
    expect(page.requests.filter(item => item.path === 'configure')).toHaveLength(1)
    page.dom.window.close()
  })
})
