"""
Inter-Extension Communication System
"""

from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor

class MessagePriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

class MessageType(Enum):
    EVENT = "event"
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    COMMAND = "command"

@dataclass
class ExtensionMessage:
    """Message structure for inter-extension communication"""
    message_id: str
    sender: str
    recipient: str  # "*" for broadcast
    message_type: MessageType
    priority: MessagePriority
    topic: str
    payload: Dict[str, Any]
    timestamp: float
    correlation_id: Optional[str] = None
    ttl: int = 300  # Time to live in seconds

@dataclass
class MessageHandler:
    """Handler for processing messages"""
    extension_id: str
    topics: List[str]
    handler_function: Callable
    priority: int = 0

class ExtensionEventBus:
    """Central event bus for inter-extension communication"""

    def __init__(self):
        self.handlers: Dict[str, List[MessageHandler]] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def start(self):
        """Start the event bus processing"""
        self.running = True
        asyncio.create_task(self._process_messages())

    async def stop(self):
        """Stop the event bus processing"""
        self.running = False
        self.executor.shutdown(wait=True)

    def register_handler(self, handler: MessageHandler):
        """Register a message handler"""
        for topic in handler.topics:
            if topic not in self.handlers:
                self.handlers[topic] = []
            self.handlers[topic].append(handler)
            # Sort by priority (higher priority first)
            self.handlers[topic].sort(key=lambda h: h.priority, reverse=True)

    def unregister_handler(self, extension_id: str, topic: str = None):
        """Unregister message handlers"""
        if topic:
            if topic in self.handlers:
                self.handlers[topic] = [
                    h for h in self.handlers[topic]
                    if h.extension_id != extension_id
                ]
        else:
            # Remove from all topics
            for topic_handlers in self.handlers.values():
                topic_handlers[:] = [
                    h for h in topic_handlers
                    if h.extension_id != extension_id
                ]

    async def publish(self, message: ExtensionMessage) -> bool:
        """Publish a message to the event bus"""
        try:
            await self.message_queue.put(message)
            return True
        except Exception:
            return False

    async def _process_messages(self):
        """Process messages from the queue"""
        while self.running:
            try:
                message = await self.message_queue.get()

                # Check TTL
                import time
                if time.time() - message.timestamp > message.ttl:
                    continue

                # Find handlers
                handlers = []
                if message.recipient == "*":
                    # Broadcast message
                    if message.topic in self.handlers:
                        handlers = self.handlers[message.topic]
                else:
                    # Direct message
                    if message.topic in self.handlers:
                        handlers = [
                            h for h in self.handlers[message.topic]
                            if h.extension_id == message.recipient
                        ]

                # Process handlers
                for handler in handlers:
                    try:
                        # Run handler in thread pool to avoid blocking
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            self.executor,
                            handler.handler_function,
                            message
                        )
                    except Exception as e:
                        print(f"Error in message handler {handler.extension_id}:{message.topic}: {e}")

                self.message_queue.task_done()

            except Exception as e:
                print(f"Error processing message: {e}")

class ExtensionServiceRegistry:
    """Registry for extension-provided services"""

    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}
        self.service_providers: Dict[str, str] = {}  # service_name -> extension_id

    def register_service(self, extension_id: str, service_name: str, service_info: Dict[str, Any]):
        """Register a service provided by an extension"""
        self.services[service_name] = {
            "provider": extension_id,
            "info": service_info,
            "registered_at": asyncio.get_event_loop().time()
        }
        self.service_providers[service_name] = extension_id

    def unregister_service(self, extension_id: str, service_name: str = None):
        """Unregister services provided by an extension"""
        if service_name:
            if service_name in self.services and self.services[service_name]["provider"] == extension_id:
                del self.services[service_name]
                del self.service_providers[service_name]
        else:
            # Unregister all services from this extension
            services_to_remove = [
                name for name, info in self.services.items()
                if info["provider"] == extension_id
            ]
            for service_name in services_to_remove:
                del self.services[service_name]
                del self.service_providers[service_name]

    def discover_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Discover a service by name"""
        return self.services.get(service_name)

    def list_services(self, provider: str = None) -> Dict[str, Dict[str, Any]]:
        """List all registered services"""
        if provider:
            return {
                name: info for name, info in self.services.items()
                if info["provider"] == provider
            }
        return self.services.copy()

class ExtensionDataSharing:
    """System for extensions to share data securely"""

    def __init__(self):
        self.shared_data: Dict[str, Dict[str, Any]] = {}
        self.access_permissions: Dict[str, List[str]] = {}  # data_key -> allowed_extensions

    def share_data(self, extension_id: str, data_key: str, data: Any, allowed_extensions: List[str] = None):
        """Share data from one extension to others"""
        self.shared_data[data_key] = {
            "provider": extension_id,
            "data": data,
            "shared_at": asyncio.get_event_loop().time(),
            "access_count": 0
        }
        self.access_permissions[data_key] = allowed_extensions or ["*"]  # "*" means all extensions

    def access_data(self, requesting_extension: str, data_key: str) -> Optional[Any]:
        """Access shared data (with permission check)"""
        if data_key not in self.shared_data:
            return None

        data_info = self.shared_data[data_key]
        allowed = self.access_permissions.get(data_key, [])

        if "*" not in allowed and requesting_extension not in allowed:
            return None

        # Update access count
        data_info["access_count"] += 1

        return data_info["data"]

    def revoke_data_access(self, extension_id: str, data_key: str = None):
        """Revoke access to shared data"""
        if data_key:
            if data_key in self.shared_data and self.shared_data[data_key]["provider"] == extension_id:
                del self.shared_data[data_key]
                if data_key in self.access_permissions:
                    del self.access_permissions[data_key]
        else:
            # Revoke all data shared by this extension
            keys_to_remove = [
                key for key, info in self.shared_data.items()
                if info["provider"] == extension_id
            ]
            for key in keys_to_remove:
                del self.shared_data[key]
                if key in self.access_permissions:
                    del self.access_permissions[key]

# Global instances
event_bus = ExtensionEventBus()
service_registry = ExtensionServiceRegistry()
data_sharing = ExtensionDataSharing()

# Helper functions for extensions
def send_message(recipient: str, topic: str, payload: Dict[str, Any],
                message_type: MessageType = MessageType.EVENT,
                priority: MessagePriority = MessagePriority.NORMAL) -> str:
    """Helper function to send messages"""
    import uuid
    import time

    message = ExtensionMessage(
        message_id=str(uuid.uuid4()),
        sender="current_extension",  # Would be set by context
        recipient=recipient,
        message_type=message_type,
        priority=priority,
        topic=topic,
        payload=payload,
        timestamp=time.time()
    )

    # This would be called asynchronously
    asyncio.create_task(event_bus.publish(message))
    return message.message_id

def register_message_handler(extension_id: str, topics: List[str], handler: Callable, priority: int = 0):
    """Helper function to register message handlers"""
    message_handler = MessageHandler(
        extension_id=extension_id,
        topics=topics,
        handler_function=handler,
        priority=priority
    )
    event_bus.register_handler(message_handler)

def register_service(extension_id: str, service_name: str, service_info: Dict[str, Any]):
    """Helper function to register services"""
    service_registry.register_service(extension_id, service_name, service_info)

def share_data(extension_id: str, data_key: str, data: Any, allowed_extensions: List[str] = None):
    """Helper function to share data"""
    data_sharing.share_data(extension_id, data_key, data, allowed_extensions)