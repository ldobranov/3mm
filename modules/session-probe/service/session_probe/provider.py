"""Only the public SDK; no Core/runtime import, shell, network or credentials."""
import asyncio
import json
import os
import socket
from three_mm_application_sdk.session import require_isolated_session_process

class Provider:
    provider_id='org.3mm.session-probe'
    contract_version='1.0'
    capability_ids=('org.3mm.session-probe.echo',)
    control_actions=('resize',)
    def __init__(self):
        self.queue=asyncio.Queue(maxsize=1)
        self.delayed=None
        self.size={}
    async def open(self, context):
        self.context=context
        self.queue.put_nowait(b'probe ready\n')
        async def later():
            await asyncio.sleep(.2)
            await self.queue.put(b'probe delayed\n')
        self.delayed=asyncio.create_task(later())
    async def read_output(self, sid):return await self.queue.get()
    async def receive(self, sid, data):
        if data!=b'facts':return data
        denied={}
        for name,family in [('ipv4',socket.AF_INET),('ipv6',socket.AF_INET6)]:
            try:
                channel=socket.socket(family);channel.close();denied[name]=False
            except OSError:denied[name]=True
        return json.dumps({'uid':os.geteuid(),'device_id':self.context['device_id'],
            'private_paths_denied':all(not os.access(p,os.R_OK) for p in ('/etc/3mm','/var/lib/3mm','/home/raspberry','/mnt/c')),
            'network_denied':denied,'secret_environment':any('KEY' in k or 'TOKEN' in k or 'PASSWORD' in k or 'DATABASE' in k for k in os.environ),
            'resize':self.size},sort_keys=True).encode()
    async def control(self, sid, message):
        if message['action']!='resize':raise ValueError('Unknown probe control')
        self.size=dict(message['arguments'])
    async def close(self, sid, reason):
        if self.delayed is not None:
            self.delayed.cancel()
            await asyncio.gather(self.delayed,return_exceptions=True)

def create_provider():
    require_isolated_session_process()
    return Provider()
