"""Key-owned failures stay private; callers retain their original failure type."""
from contextlib import contextmanager
import os
import traceback

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.applications.authority import keys
from backend.applications.runtime.gateway import ApplicationGatewayError
from backend.tests.test_application_authority_keys import installed
from components.system_runtime.application_transport import ApplicationTransportError

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Real POSIX key resource cleanup')
PRIVATE = 'Bearer PRIVATE_KEY_TEST_VALUE never expose internal key failure'


@pytest.mark.parametrize('read_only', [False, True])
@pytest.mark.parametrize('kind', [RuntimeError, ValueError, TypeError, OSError,
    SQLAlchemyError, ApplicationGatewayError, ApplicationTransportError, KeyboardInterrupt])
def test_lease_preserves_caller_exception_and_releases_real_resources(installed, read_only, kind):
    _, store, directory = installed
    identity = store.provision()
    content = (directory / keys.KEY_NAME).read_bytes()
    failure = kind(PRIVATE)
    adapter = None
    with pytest.raises(kind) as error:
        with (store.read_locked() if read_only else store.locked()) as adapter:
            raise failure
    assert error.value is failure
    assert adapter is not None and adapter.active is False
    # A new real exclusive lease and unchanged identity prove no lock/repair leak.
    with store.locked():
        pass
    assert store.identity() == identity
    assert (directory / keys.KEY_NAME).read_bytes() == content


@pytest.mark.parametrize('read_only', [False, True])
def test_missing_record_is_still_a_key_error_without_implicit_repair(installed, read_only):
    _, store, directory = installed
    store.provision()
    (directory / keys.KEY_NAME).unlink()
    with pytest.raises(keys.AuthorityReviewKeyError):
        with (store.read_locked() if read_only else store.locked()):
            pytest.fail('Missing key was admitted')
    assert not (directory / keys.KEY_NAME).exists()


def test_partial_acquisition_closes_directory_and_redacts_its_own_failure(installed, monkeypatch):
    _, store, _ = installed
    identity = store.provision()
    descriptors = []
    original = keys._private_directory
    @contextmanager
    def directory(*args, **kwargs):
        with original(*args, **kwargs) as descriptor:
            descriptors.append(descriptor)
            yield descriptor
    @contextmanager
    def unavailable_lock(*args, **kwargs):
        raise OSError(PRIVATE)
        yield  # Context-manager protocol; acquisition never reaches its caller.
    with monkeypatch.context() as patch:
        patch.setattr(keys, '_private_directory', directory)
        patch.setattr(keys, '_key_lock', unavailable_lock)
        with pytest.raises(keys.AuthorityReviewKeyError) as error:
            with store.read_locked():
                pytest.fail('Failed acquisition yielded a key')
    assert PRIVATE not in ''.join(traceback.format_exception(error.value))
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    assert store.identity() == identity


def test_key_cleanup_failure_stays_denied_and_does_not_leave_an_active_adapter(installed, monkeypatch):
    _, store, _ = installed
    identity = store.provision()
    original = keys._key_lock
    @contextmanager
    def broken_cleanup(*args, **kwargs):
        with original(*args, **kwargs):
            yield
        raise OSError(PRIVATE)
    adapter = None
    with monkeypatch.context() as patch:
        patch.setattr(keys, '_key_lock', broken_cleanup)
        with pytest.raises(keys.AuthorityReviewKeyError) as error:
            with store.read_locked() as adapter:
                pass
    assert adapter is not None and adapter.active is False
    assert PRIVATE not in ''.join(traceback.format_exception(error.value))
    assert store.identity() == identity
