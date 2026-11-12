import { describe, expect, it } from 'vitest'
import source from '../../../config_templates/product.json'
import { parseProductMetadata, renderProductHead } from './product'

describe('cosmetic product metadata', () => {
  it('renders an alternate brand as text, not executable markup', () => {
    const title = 'Alternate </title><script>window.bad=true</script> & "name"'
    const alternate = parseProductMetadata({ ...source, name: 'Alternate', display_name: title,
      welcome_message: 'Hello from another product', default_logo_url: '/brand/logo.svg',
      favicon_url: '/brand/favicon.svg' })
    const rendered = renderProductHead('<html><head><title>__PRODUCT_TITLE__</title>' +
      '<link rel="icon" href="__PRODUCT_FAVICON__"></head><body></body></html>', alternate)
    const parsed = new DOMParser().parseFromString(rendered, 'text/html')
    expect(parsed.title).toBe(title)
    expect(parsed.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe('/brand/favicon.svg')
    expect(parsed.querySelector('script')).toBeNull()
    expect(parsed.body.children).toHaveLength(0)
    expect(alternate.welcome_message).toBe('Hello from another product')
    expect(alternate.default_logo_url).toBe('/brand/logo.svg')
    expect(source.display_name).not.toBe(title)
  })

  it.each([null, {}, { ...source, schema_version: 2 }, { ...source, setup: null },
    { ...source, favicon_url: 'javascript:alert(1)' }, { ...source, favicon_url: '//foreign.test/icon' },
    { ...source, default_logo_url: '/../private' }, { ...source, name: 'bad\nname' },
    { ...source, name: 'bad\ud800name' }])(
    'uses independent neutral defaults for absent or malformed metadata', value => {
      const result = parseProductMetadata(value)
      expect(result.display_name).toBe('Device platform')
      expect(result.favicon_url).toBe('/favicon.ico')
      result.setup.labels.en.title = 'Changed locally'
      expect(parseProductMetadata(null).setup.labels.en.title).toBe('Set up this device')
    })
})
