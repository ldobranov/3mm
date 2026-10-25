"""Ephemeral optional-executor support; never provider grants or execution trust."""
from pathlib import Path
import json
import os
import stat
import time

SUPPORT = Path('/run/3mm-session-node/support.json')


def session_link_available(device_id):
    try:
        for path in (SUPPORT, SUPPORT.parent):
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                return False
        with SUPPORT.open('rb') as stream:
            data = stream.read(4097)
        if len(data) > 4096:
            return False
        value = json.loads(data)
        now = time.time()
        return (set(value) == {'version','device_id','generation','expires_at','component','build_id','pid'}
            and type(value['version']) is int and value['version'] == 1
            and value['device_id'] == device_id
            and value['component'] == 'session-node' and type(value['build_id']) is str and len(value['build_id']) == 64
            and type(value['pid']) is int and value['pid'] > 0
            and type(value['generation']) is str and len(value['generation']) == 32
            and type(value['expires_at']) in (int,float)
            and now < value['expires_at'] <= now + 12)
    except (ValueError,OSError,TypeError,KeyError):
        return False
