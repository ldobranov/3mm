"""Package-specific inert proof must supersede historical connector registration.

These pure routing regressions do not replace the POSIX seal/consent integration
suite. Every selected proof is still verified by its original verifier.
"""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.services import application_authority_sources as sources
from backend.services import application_configuration_provenance as provenance
from backend.services import application_package_staging as staging
from backend.services.application_authority_management import AuthorityManagementError


class RegistrationPriorityTests(unittest.TestCase):
    def setUp(self):
        stack=ExitStack();self.addCleanup(stack.close)
        self.records={'initial':object(),'candidate':object()}
        self.db=Mock();self.db.get.side_effect=lambda _model,identifier,**kw:self.records.get(identifier)
        self.pin=SimpleNamespace(active_version=None,module_package_id=3,sha256='b'*64)
        self.package=object();self.key=object()
        def replace(target,**kwargs):return stack.enter_context(patch(target,**kwargs))
        replace('backend.services.application_authority_sources._package_pin',return_value=self.pin)
        replace('backend.services.application_authority_sources.read_authority_guard',return_value=object())
        replace('backend.services.application_authority_sources._core_identity',return_value='inst_'+'1'*32)
        replace('backend.services.application_authority_sources.read_application_authority',return_value=SimpleNamespace(
            incarnation='2'*32,module_id='org.example.monitor'))
        replace('backend.services.application_configuration_provenance.registration_id',return_value='initial')
        replace('backend.services.application_package_staging.registration_id',return_value='candidate')
        self.initial_verify=replace('backend.services.application_configuration_provenance.verify_registration')
        self.candidate_verify=replace('backend.services.application_package_staging.verify_registration')
        self.load=replace('backend.services.application_authority_management._load',return_value={'revision':'3'*32})
        self.initial_binding=replace('backend.services.application_configuration_provenance._binding',return_value='initial-binding')
        self.candidate_binding=replace('backend.services.application_package_staging._binding',return_value='candidate-binding')

    def code_identity(self):
        return sources._resolve_code_identity(self.db,1,self.pin,self.package,registration_key=self.key)

    def configuration(self):
        return provenance.current_registration(self.db,self.key,1,self.pin,self.package)

    def test_code_identity_uses_current_candidate_despite_stale_initial_registration(self):
        self.initial_verify.side_effect=AuthorityManagementError('registration_unavailable')
        self.code_identity()
        self.candidate_verify.assert_called_once_with(self.db,self.key,1,self.pin,self.package)
        self.initial_verify.assert_not_called()

    def test_connector_transition_uses_current_candidate_binding(self):
        self.initial_verify.side_effect=AuthorityManagementError('registration_unavailable')
        marker,_proof,binding=self.configuration()
        self.assertEqual(marker,'candidate')
        self.assertEqual(binding(),'candidate-binding')
        self.initial_verify.assert_not_called()
        self.candidate_verify.assert_called_once_with(self.db,self.key,1,self.pin,self.package)

    def test_code_identity_rejects_invalid_candidate_without_fallback(self):
        self.candidate_verify.side_effect=AuthorityManagementError('registration_unavailable')
        with self.assertRaises(AuthorityManagementError):self.code_identity()
        self.initial_verify.assert_not_called()

    def test_connector_transition_rejects_invalid_candidate_without_fallback(self):
        self.candidate_verify.side_effect=AuthorityManagementError('registration_unavailable')
        with self.assertRaises(AuthorityManagementError):self.configuration()
        self.initial_verify.assert_not_called()

    def test_first_registration_still_works_without_candidate(self):
        self.records.pop('candidate')
        self.code_identity()
        marker,_proof,binding=self.configuration()
        self.assertEqual(marker,'initial')
        self.assertEqual(binding(),'initial-binding')
        self.assertEqual(self.initial_verify.call_count,2)
        self.candidate_verify.assert_not_called()

    def test_bad_first_registration_without_candidate_is_refused(self):
        self.records.pop('candidate')
        self.initial_verify.side_effect=AuthorityManagementError('registration_unavailable')
        with self.assertRaises(AuthorityManagementError):self.code_identity()
        with self.assertRaises(AuthorityManagementError):self.configuration()
        self.candidate_verify.assert_not_called()


if __name__=='__main__':unittest.main()
