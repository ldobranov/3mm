/**
 * Frontend Extension Relationships System
 * Provides inter-extension communication, component sharing, and API integration for the frontend.
 */

import { ref, reactive, markRaw } from 'vue'
import http from '@/utils/dynamic-http'
import { i18n } from '@/utils/i18n'
import { getToken } from '@/utils/auth'

// Extension manifests are loaded dynamically from files

// Function to get all available extensions (dynamically discovered)
export function getAvailableExtensions(): string[] {
  try {
    const discovered = extensionRelationships.getDiscoveredExtensions()
    return discovered
  } catch (error) {
    // Return empty array if extension system not initialized yet
    console.log('Extension system not ready, returning empty array')
    return []
  }
}

interface ComponentDefinition {
  name: string
  component: any
  config?: Record<string, any>
  extension: string
}

interface ApiEndpoint {
  name: string
  handler: Function
  config?: Record<string, any>
  extension: string
}

interface ExtensionRelationship {
  provider: string
  consumer: string
  type: 'component' | 'api' | 'data' | 'service'
  resource: string
  config?: Record<string, any>
}

interface ManifestCapabilities {
  capabilities?: Record<string, string[]>
  provides?: Record<string, Record<string, string[]>>
  consumes?: Record<string, Record<string, string[]>>
  frontend_routes?: any[]
  [key: string]: any // Allow other properties
}

class FrontendExtensionRelationships {
  private components = reactive<Map<string, ComponentDefinition>>(new Map())
  private apiEndpoints = reactive<Map<string, ApiEndpoint>>(new Map())
  private relationships = ref<ExtensionRelationship[]>([])
  private eventListeners = new Map<string, Function[]>()
  private manifestCache = ref<Record<string, ManifestCapabilities>>({})
  private discoveredExtensions: string[] = []

  // Component Registry
  registerComponent(extensionName: string, componentName: string,
                    component: any, config?: Record<string, any>) {
    const key = `${extensionName}.${componentName}`
    console.log(`Registering component: ${key}`, component)
    this.components.set(key, {
      name: componentName,
      component: markRaw(component), // Prevent component from becoming reactive
      config: config || {},
      extension: extensionName
    })
    console.log(`Component registered. Total components: ${this.components.size}`)
  }

  async getComponent(extensionName: string, componentName: string): Promise<any> {
    const key = `${extensionName}.${componentName}`

    // First check if component is already registered
    const definition = this.components.get(key)
    if (definition) {
      console.log(`getComponent(${extensionName}, ${componentName}): Found in registry`)
      return definition.component
    }

    // If not registered, try to load it dynamically
    console.log(`getComponent(${extensionName}, ${componentName}): Not in registry, trying to load dynamically`)
    try {
      const component = await this.loadComponentFromExtension(extensionName, componentName)
      if (component) {
        // Register the component for future use
        this.registerComponent(extensionName, componentName, component)
        console.log(`getComponent(${extensionName}, ${componentName}): Loaded and registered successfully`)
        return component
      }
    } catch (error) {
      console.error(`getComponent(${extensionName}, ${componentName}): Failed to load:`, error)
    }

    console.log(`getComponent(${extensionName}, ${componentName}): Not found`)
    return null
  }

  getComponentConfig(extensionName: string, componentName: string): Record<string, any> | undefined {
    const key = `${extensionName}.${componentName}`
    const definition = this.components.get(key)
    return definition?.config
  }

  // API Endpoints Registry
  registerApiEndpoint(extensionName: string, endpointName: string,
                      handler: Function, config?: Record<string, any>) {
    const key = `${extensionName}.${endpointName}`
    this.apiEndpoints.set(key, {
      name: endpointName,
      handler,
      config: config || {},
      extension: extensionName
    })
  }

  async callApiEndpoint(extensionName: string, endpointName: string, params?: Record<string, any>): Promise<any> {
    const key = `${extensionName}.${endpointName}`
    const endpoint = this.apiEndpoints.get(key)

    if (endpoint) {
      try {
        return await endpoint.handler(params)
      } catch (error) {
        console.error(`Error calling API endpoint ${key}:`, error)
        return null
      }
    }

    // Try calling backend API
    try {
      const response = await http.get(`/api/extension/${extensionName}/${endpointName}`, { params })
      return response.data
    } catch (error) {
      console.error(`Failed to call backend API for ${key}:`, error)
      return null
    }
  }

  // Event System
  emit(eventName: string, data?: any) {
    const listeners = this.eventListeners.get(eventName)
    if (listeners) {
      listeners.forEach(listener => {
        try {
          listener(data)
        } catch (error) {
          console.error(`Error in event listener for ${eventName}:`, error)
        }
      })
    }
  }

  on(eventName: string, listener: Function) {
    if (!this.eventListeners.has(eventName)) {
      this.eventListeners.set(eventName, [])
    }
    this.eventListeners.get(eventName)!.push(listener)
  }

  off(eventName: string, listener: Function) {
    const listeners = this.eventListeners.get(eventName)
    if (listeners) {
      const index = listeners.indexOf(listener)
      if (index > -1) {
        listeners.splice(index, 1)
      }
    }
  }

  // Relationship Management
  registerRelationship(provider: string, consumer: string, type: string, resource: string, config?: Record<string, any>) {
    console.log(`Registering relationship: ${provider} -> ${consumer} (${type}: ${resource})`);
    this.relationships.value.push({
      provider,
      consumer,
      type: type as any,
      resource,
      config: config || {}
    })
    console.log(`Total relationships after registration: ${this.relationships.value.length}`);
    console.log(`Current relationships:`, Array.from(this.relationships.value));
  }

  getRelationshipsForExtension(extensionName: string): ExtensionRelationship[] {
    return this.relationships.value.filter(
      rel => rel.provider === extensionName || rel.consumer === extensionName
    )
  }

  getAvailableComponents(): string[] {
    return Array.from(this.components.keys())
  }

  getAvailableApiEndpoints(): string[] {
    return Array.from(this.apiEndpoints.keys())
  }

  getDiscoveredExtensions(): string[] {
    return this.discoveredExtensions
  }

  // Get cached manifest for an extension
  getManifest(extensionName: string) {
    return this.manifestCache.value[extensionName]
  }

  // Dynamic Component Loading
  async loadComponentFromExtension(extensionName: string, componentName: string): Promise<any> {
    try {
      // Try to dynamically import the component
      const module = await import(`../extensions/${extensionName}_1.0.0/${componentName}.vue`)
      return module.default
    } catch (error) {
      console.warn(`Failed to load component ${extensionName}.${componentName}:`, error)
      return null
    }
  }

  // Utility method to check if an extension provides a specific resource
  async extensionProvides(extensionName: string, resourceType: string, resourceName: string): Promise<boolean> {
    console.log(`🔍 extensionProvides called with: ${extensionName}, ${resourceType}, ${resourceName}`)
    console.log(`🔍 Current language:`, i18n.getCurrentLanguage())
    console.log(`🔍 Discovered extensions:`, this.discoveredExtensions)

    // First check runtime relationships (for dynamically registered components)
    const runtimeResult = this.relationships.value.some(
      rel => rel.provider === extensionName &&
             rel.type === resourceType &&
             rel.resource === resourceName
    )

    if (runtimeResult) {
      console.log(`extensionProvides(${extensionName}, ${resourceType}, ${resourceName}): true (runtime)`)
      return true
    }

    // Fallback: Check manifest capabilities (for statically declared capabilities)
    const manifestResult = await this.checkManifestCapabilities(extensionName, resourceType, resourceName)
    console.log(`extensionProvides(${extensionName}, ${resourceType}, ${resourceName}): ${manifestResult} (manifest)`)
    return manifestResult
  }

  // Preload manifest capabilities for an extension
  async preloadManifest(extensionName: string): Promise<void> {
    if (this.manifestCache.value[extensionName]) {
      return // Already loaded
    }

    try {

      // Load manifest from file
      const manifestModule = await import(`../extensions/${extensionName}_1.0.0/manifest.json`)
      const manifest = manifestModule.default

      if (manifest) {
        this.manifestCache.value[extensionName] = {
          capabilities: manifest.capabilities,
          provides: manifest.provides,
          consumes: manifest.consumes,
          frontend_routes: manifest.frontend_routes
        }
      } else {
        console.warn(`No manifest available for ${extensionName}`)
        this.manifestCache.value[extensionName] = {}
      }
    } catch (error) {
      console.warn(`Failed to preload manifest for ${extensionName}:`, error)
      this.manifestCache.value[extensionName] = {}
    }
  }

  // Check manifest relationships for declared provider-consumer contracts (asynchronous)
  private async checkManifestCapabilities(extensionName: string, resourceType: string, resourceName: string): Promise<boolean> {
    console.log(`🔍 Checking if ${extensionName} provides ${resourceType}:${resourceName}...`)

    try {
      // First try to get from cache
      const cachedManifest = this.manifestCache.value[extensionName]
      if (cachedManifest && cachedManifest.provides) {
        console.log(`🔍 Using cached manifest for ${extensionName}`)
        return this.checkManifestProvides(cachedManifest.provides, resourceType, resourceName, extensionName)
      }

      // Load the actual manifest file
      console.log(`🔍 Loading manifest file for ${extensionName}...`)
      const manifestModule = await import(`../extensions/${extensionName}_1.0.0/manifest.json`)
      const manifest = manifestModule.default

      if (!manifest) {
        console.log(`❌ No manifest found for ${extensionName}`)
        return false
      }

      console.log(`✅ Loaded manifest for ${extensionName}:`, manifest)

      // Check if extension declares it provides this resource to any consumer
      if (manifest.provides) {
        return this.checkManifestProvides(manifest.provides, resourceType, resourceName, extensionName)
      }

      console.log(`❌ ${extensionName} manifest has no 'provides' section`)
      return false
    } catch (error) {
      console.warn(`❌ Failed to load manifest for ${extensionName}:`, error)
      return false
    }
  }

  // Helper method to check manifest provides section
  private checkManifestProvides(provides: any, resourceType: string, resourceName: string, extensionName: string): boolean {
    console.log(`🔍 Checking provides section:`, provides)
    for (const [consumerName, consumerResources] of Object.entries(provides)) {
      console.log(`🔍 Checking consumer ${consumerName}:`, consumerResources)
      const resources = consumerResources as Record<string, string[]>
      console.log(`🔍 Resources for ${resourceType}:`, resources[resourceType])
      if (resources[resourceType] && resources[resourceType].includes(resourceName)) {
        console.log(`✅ ${extensionName} declares it provides ${resourceType}:${resourceName} to ${consumerName}`)
        return true
      }
    }

    console.log(`❌ ${extensionName} does not declare providing ${resourceType}:${resourceName} to any consumer`)
    return false
  }

  // Discover available extensions dynamically using Vite's import.meta.glob
  private async discoverExtensions(): Promise<string[]> {
    try {
      // Use Vite's import.meta.glob to find all manifest.json files
      const manifestModules = import.meta.glob('../extensions/*/manifest.json', { eager: true })

      const filesystemExtensions: string[] = []

      for (const path in manifestModules) {
        // Extract extension name from path: '../extensions/ExtensionName_1.0.0/manifest.json' -> 'ExtensionName'
        const match = path.match(/\/extensions\/([^\/]+)_[^\/]+\/manifest\.json$/)
        if (match) {
          filesystemExtensions.push(match[1])
        }
      }

      // Check if user is authenticated before trying to call the API
      const token = getToken()
      if (!token) {
        console.log('User not authenticated, using filesystem discovery only')
        // Cache the discovered extensions
        this.discoveredExtensions = filesystemExtensions
        return filesystemExtensions
      }

      // Now check which extensions are installed and enabled in the database
      const enabledExtensions: string[] = []

      try {
        const response = await http.get('/api/extensions')
        const installedExtensions = response.data.items || []

        for (const ext of filesystemExtensions) {
          const installedExt = installedExtensions.find((installed: any) =>
            installed.name === ext && installed.is_enabled
          )
          if (installedExt) {
            enabledExtensions.push(ext)
          }
        }

      } catch (error) {
        console.warn('Failed to check extension status from database, falling back to filesystem discovery:', error)
        // Fallback to filesystem discovery if database check fails
        enabledExtensions.push(...filesystemExtensions)
      }

      // Cache the discovered extensions
      this.discoveredExtensions = enabledExtensions

      return enabledExtensions
    } catch (error) {
      console.warn('Failed to dynamically discover extensions:', error)
      // Return empty array if dynamic discovery fails
      this.discoveredExtensions = []
      return []
    }
  }


  // Initialize the extension relationships system
  async initialize(): Promise<void> {

    // Dynamically discover available extensions using Vite's import.meta.glob
    const availableExtensions = await this.discoverExtensions()

    // Preload manifests for discovered extensions
    await Promise.all(availableExtensions.map(ext => this.preloadManifest(ext)))

  }

  // Get all extensions that provide a specific resource
  getProvidersOf(resourceType: string, resourceName: string): string[] {
    return [...new Set(
      this.relationships.value
        .filter(rel => rel.type === resourceType && rel.resource === resourceName)
        .map(rel => rel.provider)
    )]
  }

  // Get all content embedders from all extensions
  getContentEmbedders(): Record<string, any> {
    const embedders: Record<string, any> = {}

    for (const extensionName of this.discoveredExtensions) {
      const manifest = this.manifestCache.value[extensionName]
      if (manifest?.provides?.content_embedders) {
        for (const [embedderType, embedderConfig] of Object.entries(manifest.provides.content_embedders)) {
          embedders[`${extensionName}.${embedderType}`] = {
            extension: extensionName,
            type: embedderType,
            ...embedderConfig
          }
        }
      }
    }

    return embedders
  }

  // Refresh extension discovery (useful when extensions are enabled/disabled)
  async refreshExtensions(): Promise<void> {
    console.log('Refreshing extension discovery...')
    await this.discoverExtensions()
    // Re-preload manifests for newly discovered extensions
    await Promise.all(this.discoveredExtensions.map(ext => this.preloadManifest(ext)))
    console.log('Extension discovery refreshed')
  }
}

// Global instance
export const extensionRelationships = new FrontendExtensionRelationships()

// Direct exports for non-Vue code (like router)
export function getManifest(extensionName: string) {
  return extensionRelationships.getManifest(extensionName)
}

// Helper functions for components to use
export function registerComponent(extensionName: string, componentName: string, component: any, config?: Record<string, any>) {
  extensionRelationships.registerComponent(extensionName, componentName, component, config)
}

export function registerRelationship(provider: string, consumer: string, type: string, resource: string, config?: Record<string, any>) {
  extensionRelationships.registerRelationship(provider, consumer, type, resource, config)
}

export async function getComponent(extensionName: string, componentName: string): Promise<any> {
  return extensionRelationships.getComponent(extensionName, componentName)
}

export function registerApiEndpoint(extensionName: string, endpointName: string, handler: Function, config?: Record<string, any>) {
  extensionRelationships.registerApiEndpoint(extensionName, endpointName, handler, config)
}

export function callApiEndpoint(extensionName: string, endpointName: string, params?: Record<string, any>): Promise<any> {
  return extensionRelationships.callApiEndpoint(extensionName, endpointName, params)
}

export function emitEvent(eventName: string, data?: any) {
  extensionRelationships.emit(eventName, data)
}

export function onEvent(eventName: string, listener: Function) {
  extensionRelationships.on(eventName, listener)
}

export function offEvent(eventName: string, listener: Function) {
  extensionRelationships.off(eventName, listener)
}

// Vue composable for using extension relationships in components
export function useExtensionRelationships() {
  return {
    registerComponent,
    getComponent,
    registerApiEndpoint,
    callApiEndpoint,
    emitEvent,
    onEvent,
    offEvent,
    registerRelationship: (provider: string, consumer: string, type: string, resource: string, config?: Record<string, any>) =>
      extensionRelationships.registerRelationship(provider, consumer, type, resource, config),
    extensionProvides: (ext: string, type: string, resource: string) =>
      extensionRelationships.extensionProvides(ext, type, resource),
    getProvidersOf: (type: string, resource: string) =>
      extensionRelationships.getProvidersOf(type, resource),
    getRelationshipsForExtension: (extensionName: string) =>
      extensionRelationships.getRelationshipsForExtension(extensionName),
    loadComponentFromExtension: (ext: string, comp: string) =>
      extensionRelationships.loadComponentFromExtension(ext, comp),
    getManifest: (extensionName: string) =>
      extensionRelationships.getManifest(extensionName),
    getContentEmbedders: () =>
      extensionRelationships.getContentEmbedders(),
    refreshExtensions: () =>
      extensionRelationships.refreshExtensions()
  }
}