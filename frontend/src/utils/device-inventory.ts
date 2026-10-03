/** Generic inventory presentation. Metadata never decides device behavior. */
export interface DeviceInventory {
  schema_version?: number
  hostname?: string | null
  model?: string | null
  architecture?: string | null
  platform?: Record<string, unknown>
  runtime?: Record<string, unknown>
  resources?: Record<string, unknown>
  network?: Record<string, unknown>
  [key: string]: unknown
}

export interface InventoryRow { key: string; label: string; value: string }

const legacyPaths: Record<string, ['network' | 'platform' | 'resources', string]> = {
  hostname: ['network', 'hostname'], model: ['platform', 'model'],
  architecture: ['platform', 'architecture'], operating_system: ['platform', 'system'],
  operating_system_version: ['platform', 'version'],
  logical_cpu_count: ['resources', 'logical_cpu_count'],
  memory_total_bytes: ['resources', 'memory_total_bytes'],
  root_total_bytes: ['resources', 'storage_total_bytes'],
  root_free_bytes: ['resources', 'storage_free_bytes'],
}

export function inventoryValue(inventory: DeviceInventory | null, field: string): unknown {
  if (!inventory) return null
  if (inventory.schema_version === undefined) return inventory[field] ?? null
  if (inventory.schema_version !== 2) return null
  const path = legacyPaths[field]
  return path ? inventory[path[0]]?.[path[1]] ?? null : null
}

export function inventoryText(inventory: DeviceInventory | null, field: string): string {
  const value = inventoryValue(inventory, field)
  return typeof value === 'string' ? value : ''
}

function bytes(value: unknown): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null
  const unit = value >= 1024 ** 3 ? 3 : value >= 1024 ** 2 ? 2 : value >= 1024 ? 1 : 0
  return `${Number((value / 1024 ** unit).toFixed(1))} ${['B', 'KiB', 'MiB', 'GiB'][unit]}`
}

export function inventoryRows(inventory: DeviceInventory | null): InventoryRow[] {
  if (!inventory || (inventory.schema_version !== undefined && inventory.schema_version !== 2)) return []
  const rows: InventoryRow[] = []
  const add = (key: string, label: string, value: unknown, size = false) => {
    const formatted = size ? bytes(value) : typeof value === 'string' || typeof value === 'number' ? String(value) : null
    if (formatted !== null && formatted !== '') rows.push({ key, label, value: formatted })
  }
  add('hostname', 'Hostname', inventoryValue(inventory, 'hostname'))
  add('model', 'Model', inventoryValue(inventory, 'model'))
  add('platform', 'Platform', inventoryValue(inventory, 'operating_system'))
  add('platformVersion', 'Platform version', inventoryValue(inventory, 'operating_system_version'))
  add('architecture', 'Architecture', inventoryValue(inventory, 'architecture'))
  if (inventory.schema_version === 2) {
    add('family', 'Platform family', inventory.platform?.family)
    add('runtime', 'Runtime', inventory.runtime?.name)
    add('runtimeVersion', 'Runtime version', inventory.runtime?.version)
    add('memoryFree', 'Available memory', inventory.resources?.memory_free_bytes, true)
    add('flash', 'Flash', inventory.resources?.flash_total_bytes, true)
    add('flashFree', 'Free flash', inventory.resources?.flash_free_bytes, true)
  }
  add('cpu', 'Logical CPUs', inventoryValue(inventory, 'logical_cpu_count'))
  add('memory', 'Memory', inventoryValue(inventory, 'memory_total_bytes'), true)
  add('storage', 'Storage', inventoryValue(inventory, 'root_total_bytes'), true)
  add('storageFree', 'Free storage', inventoryValue(inventory, 'root_free_bytes'), true)
  return rows
}
