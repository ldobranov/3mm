"""
Extension Relationships System
Provides inter-extension communication, component sharing, and API integration.
"""

from typing import Dict, List, Any, Optional, Callable
import importlib
import os
from pathlib import Path

class ExtensionRelationship:
    """Represents a relationship between extensions"""

    def __init__(self, provider_extension: str, consumer_extension: str,
                 relationship_type: str, resource_name: str, config: Dict[str, Any]):
        self.provider_extension = provider_extension
        self.consumer_extension = consumer_extension
        self.relationship_type = relationship_type  # 'component', 'api', 'data', 'service'
        self.resource_name = resource_name
        self.config = config
        self.active = False

class ComponentRegistry:
    """Registry for shared components between extensions"""

    def __init__(self):
        self.components: Dict[str, Dict[str, Any]] = {}
        self.component_instances: Dict[str, Any] = {}

    def register_component(self, extension_name: str, component_name: str,
                          component_class: Any, config: Dict[str, Any] = None):
        """Register a component that other extensions can use"""
        if extension_name not in self.components:
            self.components[extension_name] = {}

        self.components[extension_name][component_name] = {
            'class': component_class,
            'config': config or {},
            'extension': extension_name
        }

    def get_component(self, extension_name: str, component_name: str) -> Optional[Any]:
        """Get a component class from the registry"""
        if extension_name in self.components and component_name in self.components[extension_name]:
            return self.components[extension_name][component_name]['class']
        return None

    def get_component_config(self, extension_name: str, component_name: str) -> Optional[Dict[str, Any]]:
        """Get component configuration"""
        if extension_name in self.components and component_name in self.components[extension_name]:
            return self.components[extension_name][component_name]['config']
        return None

    def instantiate_component(self, extension_name: str, component_name: str, **kwargs) -> Optional[Any]:
        """Create an instance of a registered component"""
        component_class = self.get_component(extension_name, component_name)
        if component_class:
            config = self.get_component_config(extension_name, component_name) or {}
            # Merge config with kwargs
            init_kwargs = {**config, **kwargs}
            try:
                instance = component_class(**init_kwargs)
                instance_key = f"{extension_name}.{component_name}"
                self.component_instances[instance_key] = instance
                return instance
            except Exception as e:
                print(f"Failed to instantiate component {extension_name}.{component_name}: {e}")
                return None
        return None

class ExtensionRelationshipsManager:
    """Manages relationships between extensions"""

    def __init__(self):
        self.relationships: List[ExtensionRelationship] = []
        self.component_registry = ComponentRegistry()
        self.api_endpoints: Dict[str, Dict[str, Any]] = {}
        self.event_listeners: Dict[str, List[Callable]] = {}

    def register_relationship(self, provider_extension: str, consumer_extension: str,
                            relationship_type: str, resource_name: str, config: Dict[str, Any] = None):
        """Register a relationship between extensions"""
        relationship = ExtensionRelationship(
            provider_extension, consumer_extension, relationship_type, resource_name, config or {}
        )
        self.relationships.append(relationship)

    def get_relationships_for_extension(self, extension_name: str) -> List[ExtensionRelationship]:
        """Get all relationships for a specific extension"""
        return [r for r in self.relationships
                if r.provider_extension == extension_name or r.consumer_extension == extension_name]

    def get_consumers_of_resource(self, provider_extension: str, resource_name: str) -> List[str]:
        """Get list of extensions that consume a specific resource"""
        return [r.consumer_extension for r in self.relationships
                if r.provider_extension == provider_extension and r.resource_name == resource_name]

    def get_provided_resources(self, extension_name: str) -> List[str]:
        """Get list of resources provided by an extension"""
        return list(set([r.resource_name for r in self.relationships
                        if r.provider_extension == extension_name]))

    def register_api_endpoint(self, extension_name: str, endpoint_name: str,
                            handler: Callable, config: Dict[str, Any] = None):
        """Register an API endpoint that other extensions can call"""
        if extension_name not in self.api_endpoints:
            self.api_endpoints[extension_name] = {}

        self.api_endpoints[extension_name][endpoint_name] = {
            'handler': handler,
            'config': config or {}
        }

    def call_api_endpoint(self, extension_name: str, endpoint_name: str, **kwargs) -> Any:
        """Call an API endpoint from another extension"""
        if (extension_name in self.api_endpoints and
            endpoint_name in self.api_endpoints[extension_name]):
            handler = self.api_endpoints[extension_name][endpoint_name]['handler']
            try:
                return handler(**kwargs)
            except Exception as e:
                print(f"Error calling API endpoint {extension_name}.{endpoint_name}: {e}")
                return None
        return None

    def emit_event(self, event_name: str, data: Any = None):
        """Emit an event to all registered listeners"""
        if event_name in self.event_listeners:
            for listener in self.event_listeners[event_name]:
                try:
                    listener(data)
                except Exception as e:
                    print(f"Error in event listener for {event_name}: {e}")

    def on_event(self, event_name: str, listener: Callable):
        """Register an event listener"""
        if event_name not in self.event_listeners:
            self.event_listeners[event_name] = []
        self.event_listeners[event_name].append(listener)

    def remove_event_listener(self, event_name: str, listener: Callable):
        """Remove an event listener"""
        if event_name in self.event_listeners:
            self.event_listeners[event_name].remove(listener)

# Global instance
extension_relationships = ExtensionRelationshipsManager()

# Extension capabilities registry
extension_capabilities: Dict[str, Dict[str, Any]] = {}

def declare_extension_capabilities(extension_name: str, capabilities: Dict[str, Any]):
    """Declare what an extension provides and consumes"""
    extension_capabilities[extension_name] = capabilities

    # Auto-register components
    if 'provides' in capabilities:
        provides = capabilities['provides']
        if 'components' in provides:
            for component_name, component_config in provides['components'].items():
                # Components will be registered when they're actually loaded
                pass

        if 'apis' in provides:
            for api_name, api_config in provides['apis'].items():
                # APIs will be registered when the extension initializes
                pass

def register_extension_resources(extension_name: str, router_functions: Dict[str, Callable]):
    """Register extension resources (APIs, components) dynamically"""
    if extension_name not in extension_capabilities:
        return

    capabilities = extension_capabilities[extension_name]

    # Register APIs
    if 'provides' in capabilities and 'apis' in capabilities['provides']:
        for api_name, api_config in capabilities['provides']['apis'].items():
            if api_name in router_functions:
                register_api_endpoint(extension_name, api_name, router_functions[api_name], api_config)

    # Register components (frontend components are handled separately)
    if 'provides' in capabilities and 'components' in capabilities['provides']:
        for component_name, component_config in capabilities['provides']['components'].items():
            # Components are registered on the frontend
            pass

# Helper functions for extensions to use
def register_component(extension_name: str, component_name: str, component_class: Any, config: Dict[str, Any] = None):
    """Helper function to register a component"""
    extension_relationships.component_registry.register_component(
        extension_name, component_name, component_class, config
    )

def get_component(extension_name: str, component_name: str) -> Optional[Any]:
    """Helper function to get a component"""
    return extension_relationships.component_registry.get_component(extension_name, component_name)

def instantiate_component(extension_name: str, component_name: str, **kwargs) -> Optional[Any]:
    """Helper function to instantiate a component"""
    return extension_relationships.component_registry.instantiate_component(
        extension_name, component_name, **kwargs
    )

def register_api_endpoint(extension_name: str, endpoint_name: str, handler: Callable, config: Dict[str, Any] = None):
    """Helper function to register an API endpoint"""
    extension_relationships.register_api_endpoint(extension_name, endpoint_name, handler, config)

def call_api_endpoint(extension_name: str, endpoint_name: str, **kwargs) -> Any:
    """Helper function to call an API endpoint"""
    return extension_relationships.call_api_endpoint(extension_name, endpoint_name, **kwargs)

def emit_event(event_name: str, data: Any = None):
    """Helper function to emit an event"""
    extension_relationships.emit_event(event_name, data)

def on_event(event_name: str, listener: Callable):
    """Helper function to listen for events"""
    extension_relationships.on_event(event_name, listener)