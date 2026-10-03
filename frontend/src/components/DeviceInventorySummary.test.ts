import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import DeviceInventorySummary from './DeviceInventorySummary.vue'
import { inventoryText, inventoryValue } from '@/utils/device-inventory'
import english from '@/extensions/MainServerExtension_1.0.0/locales/en.json'
import bulgarian from '@/extensions/MainServerExtension_1.0.0/locales/bg.json'

describe('platform-neutral inventory presentation', () => {
  it('shows embedded measurements without invented Linux fields', () => {
    const inventory = { schema_version: 2,
      platform: { family: 'embedded', system: 'mock-embedded', model: 'Test board' },
      runtime: { name: 'test-runtime', version: '0.1.0' },
      resources: { memory_total_bytes: 409600, flash_total_bytes: 4194304, flash_free_bytes: 0 },
      platform_metadata: { note: '<script>not executable</script>' },
    }
    const wrapper = mount(DeviceInventorySummary, { props: { inventory } })
    expect(wrapper.text()).toContain('mock-embedded')
    expect(wrapper.text()).toContain('400 KiB')
    expect(wrapper.text()).toContain('4 MiB')
    expect(wrapper.text()).toContain('0 B')
    expect(wrapper.text()).not.toMatch(/Python|Kernel|NetworkManager|Storage|Hostname/)
    expect(wrapper.find('script').exists()).toBe(false)
  })

  it.each([
    { hostname: 'pi', model: 'Pi', architecture: 'armv6l', root_free_bytes: 0, memory_total_bytes: 1024 },
    { schema_version: 2, network: { hostname: 'pi' }, platform: { model: 'Pi', architecture: 'armv6l' },
      resources: { storage_free_bytes: 0, memory_total_bytes: 1024 } },
  ])('supports old and new Linux reports including zero bytes', (inventory) => {
    const wrapper = mount(DeviceInventorySummary, { props: { inventory } })
    expect(inventoryText(inventory, 'hostname')).toBe('pi')
    expect(inventoryValue(inventory, 'architecture')).toBe('armv6l')
    expect(wrapper.text()).toContain('Pi')
    expect(wrapper.text()).toContain('1 KiB')
    expect(wrapper.text()).toContain('0 B')
  })

  it('honestly renders unknown inventory and switches translated labels', async () => {
    const inventory = { schema_version: 2, platform: { model: 'Test board' }, resources: { memory_total_bytes: 1024 } }
    const translations = (values: Record<string, string>) => (key: string, fallback: string) => values[key] || fallback
    const wrapper = mount(DeviceInventorySummary, { props: { inventory, translate: translations(english.mainServer.inventory) } })
    expect(wrapper.text()).toContain('Memory')
    await wrapper.setProps({ translate: translations(bulgarian.mainServer.inventory) })
    expect(wrapper.text()).toContain('Памет')
    await wrapper.setProps({ inventory: null })
    expect(wrapper.text()).toContain('Липсва информация')
    await wrapper.setProps({ inventory: { schema_version: 99 } })
    expect(wrapper.find('dl').exists()).toBe(false)
  })
})
