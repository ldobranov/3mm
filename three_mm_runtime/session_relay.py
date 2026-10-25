"""Local fixed-target byte relay; TLS remains end-to-end Hub <-> Node.

No identity, tickets, session open, command interpretation or reconnect. This
local acceptance relay deliberately binds loopback only; it is not a public
Cloud relay, enrollment service or an authorization boundary.
"""
import argparse
import asyncio
import ipaddress


class SessionByteRelay:
    def __init__(self, host, port, *, max_connections=4):
        if not 1 <= max_connections <= 4 or not 1 <= port <= 65535:
            raise ValueError("Relay resource bound is invalid")
        self.host, self.port, self.limit = host, port, max_connections
        self.tasks = set()

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self.tasks) >= self.limit:
            writer.close()
            await writer.wait_closed()
            return
        self.tasks.add(task)
        other = None
        pumps = []
        async def copy(source, target):
            while True:
                data = await asyncio.wait_for(source.read(16384), 120)
                if not data:
                    return
                target.write(data)
                await asyncio.wait_for(target.drain(), 5)
        try:
            peer, other = await asyncio.wait_for(asyncio.open_connection(self.host, self.port, limit=32768), 5)
            pumps = [asyncio.create_task(copy(reader, other)), asyncio.create_task(copy(peer, writer))]
            await asyncio.wait(pumps, timeout=900, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            for output in (writer, other):
                if output is not None:
                    output.close()
                    try:
                        await output.wait_closed()
                    except (ConnectionError, OSError):
                        pass
            self.tasks.discard(task)

    async def close(self):
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run(args):
    if not ipaddress.ip_address(args.listen).is_loopback:
        raise ValueError("Local session relay must bind loopback")
    relay = SessionByteRelay(args.target_host, args.target_port)
    server = await asyncio.start_server(relay.handle, args.listen, args.port, limit=32768)
    from three_mm_runtime.component_identity import component_health
    identity=component_health()
    async def readiness():
        from pathlib import Path
        import json,time
        path=Path('/run/3mm-session-relay/identity.json')
        while True:
            value={**identity,'expires_at':time.time()+8}
            temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(value))
            temporary.replace(path)
            await asyncio.sleep(2)
    reporter=asyncio.create_task(readiness()) if identity is not None else None
    try:
        async with server:
            await server.serve_forever()
    finally:
        if reporter is not None:
            reporter.cancel()
            await asyncio.gather(reporter,return_exceptions=True)
        await relay.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
