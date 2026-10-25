"""Shared stdlib immutable component pointer/journal transactions; no authority or service imports."""
from contextlib import contextmanager
import hashlib,json,os,re,time,uuid
from pathlib import Path


def _json(value):return json.dumps(value,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()
def _digest(value):return hashlib.sha256(value).hexdigest()
def _id(value):return isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value) is not None


def _fsync(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _write(path,blob,mode=0o600):
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    with os.fdopen(fd,"wb") as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path);_fsync(path.parent)


@contextmanager
def release_mutation_lock(path=Path('/run/lock/3mm-release-mutation.lock')):
    """Interoperate with the common installer and existing component helpers."""
    import fcntl
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if info.st_uid!=os.geteuid():raise ValueError('Release mutation lock owner is unsafe')
        os.fchmod(fd,0o600)
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)


class ComponentStore:
    def __init__(self,root,state):
        self.root=Path(root).absolute();self.state=Path(state).absolute()
        if self.root.is_symlink() or self.state.is_symlink():raise ValueError("Runtime roots cannot be symlinks")
        self.root.mkdir(parents=True,exist_ok=True,mode=0o755)
        self.state.mkdir(parents=True,exist_ok=True,mode=0o700)
        if self.state.stat().st_uid!=os.geteuid() or self.state.stat().st_mode&0o022:
            raise ValueError("Runtime update journal ownership is unsafe")
        self.releases=self.root/"releases";self.releases.mkdir(exist_ok=True,mode=0o755)
        if self.releases.is_symlink():raise ValueError("Runtime release root is unsafe")
        self.journal=self.state/"transaction.json"


    @contextmanager
    def locked(self):
        import fcntl
        fd=os.open(self.state/"update.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)


    def target(self,name):
        path=self.root/name
        if not path.exists() and not path.is_symlink():return None
        if not path.is_symlink():raise ValueError("Runtime pointer must be a symlink")
        target=path.resolve(strict=True)
        if target.parent!=self.releases.resolve() or not _id(target.name):raise ValueError("Runtime pointer escapes its release root")
        self.metadata(target.name)
        return target.name


    def link(self,name,identifier):
        path=self.root/name
        if path.exists() or path.is_symlink():self.target(name)
        if identifier is None:
            if path.is_symlink():path.unlink();_fsync(self.root)
            return
        self.metadata(identifier)
        temporary=self.root/("."+name+"-"+uuid.uuid4().hex)
        temporary.symlink_to(self.releases/identifier,target_is_directory=True)
        temporary.replace(path);_fsync(self.root)


    def pending(self):
        if not self.journal.exists():return None
        if self.journal.is_symlink() or self.journal.stat().st_size>8192:raise ValueError("Runtime update journal is invalid")
        value=json.loads(self.journal.read_bytes())
        if (set(value)!={"schema_version","phase","previous","previous_previous","candidate","was_active"}
                or value["schema_version"]!=1 or value["phase"] not in {"switching","committed"}
                or not _id(value["candidate"]) or type(value["was_active"]) is not bool
                or any(value[k] is not None and not _id(value[k]) for k in ("previous","previous_previous"))):
            raise ValueError("Runtime update journal is invalid")
        return value


    def clear(self):self.journal.unlink();_fsync(self.state)


    def recover(self,control,health):
        transaction=self.pending()
        if transaction is None:return
        if self.target("current") not in {transaction["previous"],transaction["candidate"]}:
            raise ValueError("Runtime pointer changed during pending update")
        if transaction["phase"]=="committed":
            if self.target("current")!=transaction["candidate"]:raise ValueError("Committed Runtime pointer changed")
            self.link("previous",transaction["previous"]);self.clear();return
        control.stop();self.link("current",transaction["previous"])
        self.link("previous",transaction["previous_previous"])
        if transaction["was_active"] and transaction["previous"] is not None:
            control.start();health(transaction["previous"])
        self.clear()


    def activate(self,blob,sha256,*,control,health,fingerprint):
        with self.locked():
            self.recover(control,health)
            candidate=self.stage(blob,sha256)
            previous=self.target("current");older=self.target("previous")
            before=fingerprint()  # No pointer/service mutation before compatibility and Core checks.
            active=control.active()
            if getattr(self,'requires_active',False) and not active:
                raise ValueError('Update requires an active component; cannot enable one')
            transaction={"schema_version":1,"phase":"switching","previous":previous,
                "previous_previous":older,"candidate":candidate,"was_active":active}
            _write(self.journal,_json(transaction))
            try:
                control.stop();self.link("current",candidate);control.start()
                result=health(candidate)
                after=fingerprint()
                if (after!=before or result.get("core_pid")!=before["pid"]
                        or result.get("core_process_generation")!=before["generation"]):
                    raise ValueError("Core continuity changed during Runtime update")
                transaction["phase"]="committed";_write(self.journal,_json(transaction))
                self.link("previous",previous);self.clear()
                return {"build_id":candidate,"status":"ready","core_pid":before["pid"]}
            except Exception:
                self.recover(control,health)
                raise


    def bootstrap(self,blob,sha256):
        with self.locked():
            if self.pending() is not None:raise ValueError("Resolve the pending Runtime update before bootstrap")
            if self.target("current") is not None:return self.target("current")
            identifier=self.stage(blob,sha256);self.link("current",identifier);return identifier
