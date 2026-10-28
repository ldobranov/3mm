"""Unprivileged client for the local, narrowly scoped privileged helper."""

from __future__ import annotations

import json
import socket
from pathlib import Path

MAX_RESPONSE_BYTES = 1024 * 1024
# Ordinary activation also validates/stages a package, snapshots data and waits
# for systemd enable/restart. Its transport budget must include that setup in
# addition to the manifest's separate health deadline. A lost/late reply still
# leaves execution unconfirmed; this budget never authorizes a retry or recovery.
APPLICATION_ACTIVATION_SETUP_BUDGET_SECONDS = 120


class UpdateHelperError(RuntimeError):
    """Raised when the privileged update helper rejects or misses a request."""


class UpdateHelperClient:
    def __init__(self, socket_path: Path, timeout_seconds: float = 10.0) -> None:
        self._socket_path = socket_path
        self._timeout_seconds = timeout_seconds

    def schedule(
        self,
        release_id: str,
        approval_nonce: str,
        requested_by_user_id: int,
    ) -> None:
        payload = {
            "action": "apply",
            "release_id": release_id,
            "approval_nonce": approval_nonce,
            "requested_by_user_id": requested_by_user_id,
        }
        self._request(payload)

    def request_access_point(self, action: str, user_id: int, identifier: str, *, interface=None, duration=300):
        if action not in {"start", "stop"}:
            raise ValueError("Invalid access point action")
        payload = {"action": action + "_access_point", "requested_by_user_id": user_id, "id": identifier}
        if action == "start":
            payload.update(interface=interface, duration=duration)
        self._request(payload)

    def request_network_setup(self, requested_by_user_id: int) -> None:
        self._request(
            {
                "action": "start_network_setup",
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_system_action(
        self,
        action: str,
        requested_by_user_id: int,
    ) -> None:
        if action not in {"restart_device", "factory_reset"}:
            raise ValueError("Unsupported system action")
        self._request(
            {
                "action": action,
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_backup(self, requested_by_user_id: int) -> None:
        self._request(
            {
                "action": "create_backup",
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_backup_preview(self, requested_by_user_id: int) -> dict[str, object]:
        result = self._request(
            {
                "action": "preview_backup",
                "requested_by_user_id": requested_by_user_id,
            },
            expected_status="inspected",
        )
        preview = result.get("preview")
        if not isinstance(preview, dict):
            raise UpdateHelperError("The backup preview response is invalid")
        return preview

    def activate_application_extension(
        self,
        sha256: str,
        requested_by_user_id: int,
        configuration: dict[str, object] | None = None,
        lifecycle: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return self._request(
            {
                "action": "activate_application_extension",
                "sha256": sha256,
                "requested_by_user_id": requested_by_user_id,
                "configuration": configuration or {},
                "lifecycle": lifecycle,
            },
            expected_status="active",
        )

    def prepare_application_relational(self, installation_id, actor_token,
        expected_grant_record_revision, *, confirm_fresh_owned_namespace,
        confirm_owned_business_migrations):
        from three_mm_runtime.application_relational_control import preparation_request
        payload = preparation_request({
            "action": "prepare_application_relational", "installation_id": installation_id,
            "actor_token": actor_token, "expected_grant_record_revision": expected_grant_record_revision,
            "confirm_fresh_owned_namespace": confirm_fresh_owned_namespace,
            "confirm_owned_business_migrations": confirm_owned_business_migrations,
        })
        response = self._request(payload, expected_status="prepared_not_started")
        result = response.get("preparation")
        if type(result) is not dict or set(result) != {"namespace", "database"}:
            raise UpdateHelperError("Relational preparation completion is unconfirmed")
        from three_mm_application_sdk.relational_wire import (
            _RelationalNamespacePreparationResult, _RelationalPreparationResult,
        )
        try:
            return {
                "namespace": _RelationalNamespacePreparationResult.model_validate(result["namespace"]).model_dump(mode="json"),
                "database": _RelationalPreparationResult.model_validate(result["database"]).model_dump(mode="json"),
            }
        except ValueError:
            raise UpdateHelperError("Relational preparation completion is unconfirmed") from None

    def disable_application_extension(
        self,
        instance_id: str,
        requested_by_user_id: int,
        lifecycle: dict[str, object] | None = None,
    ) -> None:
        self._request(
            {
                "action": "disable_application_extension",
                "instance_id": instance_id,
                "requested_by_user_id": requested_by_user_id,
                "lifecycle": lifecycle,
            },
            expected_status="disabled",
        )

    def activate_application_relational(self, installation_id, actor_token,
        expected_grant_record_revision, *, source_preparation_id, request_id,
        confirm_start_prepared_service):
        from three_mm_runtime.application_relational_control import activation_request
        from three_mm_application_sdk.relational_wire import _RelationalActivationResult
        payload = activation_request({
            "action": "activate_application_relational", "installation_id": installation_id,
            "actor_token": actor_token, "expected_grant_record_revision": expected_grant_record_revision,
            "source_preparation_id": source_preparation_id, "request_id": request_id,
            "confirm_start_prepared_service": confirm_start_prepared_service,
        })
        try:
            response = self._request(payload, expected_status="active_review_required")
        except UpdateHelperError:
            raise UpdateHelperError("Relational activation completion is unconfirmed. Do not retry; preserve evidence.") from None
        try:
            if set(response) != {"ok", "status", "activation"}:
                raise ValueError("Invalid activation response")
            result = _RelationalActivationResult.model_validate(response["activation"]).model_dump(mode="json")
            if result["preparation_id"] != request_id:
                raise ValueError("Activation response identity changed")
            return result
        except (ValueError, KeyError, TypeError):
            raise UpdateHelperError("Relational activation completion is unconfirmed. Do not retry.") from None

    def uninstall_application_extension(
        self,
        instance_id: str,
        requested_by_user_id: int,
        lifecycle: dict[str, object] | None = None,
    ) -> None:
        self._request(
            {
                "action": "uninstall_application_extension",
                "instance_id": instance_id,
                "requested_by_user_id": requested_by_user_id,
                "lifecycle": lifecycle,
            },
            expected_status="uninstalled",
        )

    def reactivate_application_relational(self, installation_id, actor_token,
        expected_grant_record_revision, *, source_recovery_id, expected_recovery_revision,
        request_id, confirm_restart_stopped_prepared_service):
        from three_mm_runtime.application_relational_control import reactivation_request
        from three_mm_application_sdk.relational_wire import _RelationalActivationResult
        payload = reactivation_request({
            "action": "reactivate_application_relational", "installation_id": installation_id,
            "actor_token": actor_token, "expected_grant_record_revision": expected_grant_record_revision,
            "source_recovery_id": source_recovery_id, "expected_recovery_revision": expected_recovery_revision,
            "request_id": request_id, "confirm_restart_stopped_prepared_service": confirm_restart_stopped_prepared_service,
        })
        try:
            response = self._request(payload, expected_status="active_review_required")
            if type(response) is not dict or set(response) != {"ok", "status", "reactivation"}:
                raise ValueError("Invalid reactivation response")
            result = _RelationalActivationResult.model_validate(response["reactivation"]).model_dump(mode="json")
            if result["preparation_id"] != request_id:
                raise ValueError("Reactivation response identity changed")
            return result
        except (UpdateHelperError, ValueError, KeyError, TypeError, RecursionError):
            raise UpdateHelperError("Relational reactivation is unconfirmed. Do not retry; preserve evidence for fresh local review.") from None

    def enable_application_relational_boot(self, installation_id, actor_token,
        expected_grant_record_revision, *, source_activation_id, expected_activation_revision,
        request_id, confirm_enable_prepared_boot):
        from three_mm_runtime.application_relational_control import boot_enable_request
        from three_mm_application_sdk.relational_wire import _RelationalBootEnableResult
        payload = boot_enable_request({
            "action": "enable_application_relational_boot", "installation_id": installation_id,
            "actor_token": actor_token, "source_activation_id": source_activation_id,
            "expected_activation_revision": expected_activation_revision,
            "expected_grant_record_revision": expected_grant_record_revision,
            "request_id": request_id, "confirm_enable_prepared_boot": confirm_enable_prepared_boot,
        })
        try:
            response = self._request(payload, expected_status="boot_enabled_not_started")
            if type(response) is not dict or set(response) != {"ok", "status", "boot"}:
                raise ValueError("Invalid boot enable response")
            result = _RelationalBootEnableResult.model_validate(response["boot"]).model_dump(mode="json")
            if result["preparation_id"] != request_id or result["source_activation_id"] != source_activation_id:
                raise ValueError("Boot enable response identity changed")
            return result
        except (UpdateHelperError, ValueError, KeyError, TypeError, RecursionError):
            raise UpdateHelperError("Relational boot enable is unconfirmed. Do not retry; preserve evidence for explicit stop/review.") from None

    def recover_application_relational_start(self, installation_id, actor_token,
        expected_activation_revision, *, source_activation_id, request_id,
        confirm_stop_preserve_prepared_state):
        from three_mm_runtime.application_relational_control import activation_recovery_request
        from three_mm_application_sdk.relational_wire import _RelationalActivationRecoveryResult
        payload = activation_recovery_request({
            "action": "recover_application_relational_start", "installation_id": installation_id,
            "actor_token": actor_token, "source_activation_id": source_activation_id,
            "expected_activation_revision": expected_activation_revision, "request_id": request_id,
            "confirm_stop_preserve_prepared_state": confirm_stop_preserve_prepared_state,
        })
        try:
            response = self._request(payload, expected_status="stopped_review_required")
            if type(response) is not dict or set(response) != {"ok", "status", "recovery"}:
                raise ValueError("Invalid recovery response")
            result = _RelationalActivationRecoveryResult.model_validate(response["recovery"]).model_dump(mode="json")
            if result["preparation_id"] != request_id or result["source_activation_id"] != source_activation_id:
                raise ValueError("Recovery response identity changed")
            return result
        except (UpdateHelperError, ValueError, KeyError, TypeError, RecursionError):
            raise UpdateHelperError("Relational start recovery is unconfirmed. Do not retry; retain evidence for fresh local review.") from None

    def recover_application_extension(
        self, instance_id: str, requested_by_user_id: int, lifecycle: dict[str, object],
    ) -> dict[str, object]:
        return self._request(
            {"action": "recover_application_extension", "instance_id": instance_id,
             "requested_by_user_id": requested_by_user_id, "lifecycle": lifecycle},
            expected_status="disabled",
        )

    def reconcile_relational_preparation(self, payload):
        from three_mm_runtime.application_relational_preparation_recovery_control import preparation_recovery_request
        from three_mm_application_sdk.relational_preparation_recovery_wire import _EmptyPreparationRecoveryResult
        from three_mm_application_sdk.relational_wire import _RelationalPreparationResult
        payload = preparation_recovery_request(payload)
        resume = payload["action"] == "resume_application_relational_preparation"
        try:
            response = self._request(payload, expected_status="prepared_not_started" if resume else "restored_empty_not_started")
            name = "preparation" if resume else "recovery"
            if type(response) is not dict or set(response) != {"ok", "status", name}:
                raise ValueError("Invalid preparation recovery response")
            model = _RelationalPreparationResult if resume else _EmptyPreparationRecoveryResult
            result = model.model_validate(response[name]).model_dump(mode="json")
            if result["preparation_id"] != payload["request_id"]:
                raise ValueError("Preparation recovery response identity changed")
            return result
        except (UpdateHelperError, ValueError, KeyError, TypeError, RecursionError):
            raise UpdateHelperError("Preparation reconciliation is unconfirmed. Do not retry; retain evidence for fresh local review.") from None

    def erase_application_extension_data(
        self,
        instance_id: str,
        requested_by_user_id: int,
        *, module_id: str, guard_generation: str, guard_revision: int,
    ) -> None:
        self._request(
            {
                "action": "erase_application_extension_data",
                "instance_id": instance_id,
                "module_id": module_id, "guard_generation": guard_generation,
                "guard_revision": guard_revision,
                "requested_by_user_id": requested_by_user_id,
            },
            expected_status="erased",
        )

    def application_relational_upgrade(self, payload):
        from three_mm_runtime.application_relational_upgrade_control import upgrade_request, response_model, response_status
        payload = upgrade_request(payload)
        try:
            response = self._request(payload, expected_status=response_status(payload["action"]))
            if type(response) is not dict or set(response) != {"ok", "status", "upgrade"}:
                raise ValueError("Invalid local upgrade response")
            result = response_model(payload["action"]).model_validate(response["upgrade"]).model_dump(mode="json")
            if (result["preparation_id"] != payload["request_id"]
                or "source_upgrade_id" in result and result["source_upgrade_id"] != payload["source_action_id"]):
                raise ValueError("Upgrade response identity changed")
            return result
        except (UpdateHelperError, ValueError, KeyError, TypeError, RecursionError):
            raise UpdateHelperError("Relational upgrade/reconciliation is unconfirmed. Do not retry; retain evidence for fresh local review.") from None

    def request_restore(self, backup_id: str, requested_by_user_id: int) -> None:
        self._request(
            {
                "action": "restore_backup",
                "backup_id": backup_id,
                "requested_by_user_id": requested_by_user_id,
            }
        )

    def request_portable_export(
        self,
        backup_id: str,
        passphrase: str,
        requested_by_user_id: int,
    ) -> dict[str, object]:
        result = self._request(
            {
                "action": "export_backup",
                "backup_id": backup_id,
                "passphrase": passphrase,
                "requested_by_user_id": requested_by_user_id,
            },
            expected_status="ready",
        )
        if not all(
            isinstance(result.get(field), str)
            for field in ("export_id", "backup_id", "filename")
        ):
            raise UpdateHelperError("The recovery export response is invalid")
        return result

    def request_portable_restore(
        self,
        upload_id: str,
        passphrase: str,
        requested_by_user_id: int,
    ) -> str:
        result = self._request(
            {
                "action": "restore_portable_backup",
                "upload_id": upload_id,
                "passphrase": passphrase,
                "requested_by_user_id": requested_by_user_id,
            }
        )
        backup_id = result.get("backup_id")
        if not isinstance(backup_id, str):
            raise UpdateHelperError("The portable restore response is invalid")
        return backup_id

    def _request(
        self,
        payload: dict[str, object],
        *,
        expected_status: str = "queued",
    ) -> dict[str, object]:
        request = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self._timeout_seconds)
                client.connect(str(self._socket_path))
                client.sendall(request)
                response = b""
                while len(response) <= MAX_RESPONSE_BYTES:
                    chunk = client.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    if b"\n" in response:
                        break
            if len(response) > MAX_RESPONSE_BYTES:
                raise ValueError("response_too_large")
            from three_mm_runtime.application_relational_upgrade_control import ACTIONS as UPGRADE_ACTIONS
            if payload.get("action") in {"prepare_application_relational", "activate_application_relational", "recover_application_relational_start", "reactivate_application_relational", "enable_application_relational_boot", "recover_application_relational_preparation", "resume_application_relational_preparation"} | UPGRADE_ACTIONS:
                from backend.services.application_authority_context import _unique_object
                result = json.loads(response.split(b"\n", 1)[0], object_pairs_hook=_unique_object)
            else:
                result = json.loads(response.split(b"\n", 1)[0])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise UpdateHelperError("The system update helper is unavailable") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            if (isinstance(result, dict)
                    and result.get("error") == "portable_restore_incompatible"
                    and isinstance(result.get("message"), str)):
                raise UpdateHelperError(result["message"])
            messages = {
                "relational_empty_preparation_unconfirmed": "Preparation reconciliation is unconfirmed. Do not retry; retain evidence for fresh local review.",
                "relational_boot_enable_unconfirmed": "Relational boot enable is unconfirmed. Do not retry; retain evidence for explicit stop/review.",
                "relational_preparation_unconfirmed": "Relational preparation is unconfirmed. Do not retry; preserve evidence and review recovery.",
                "relational_activation_unconfirmed": "Relational activation is unconfirmed. Do not retry; preserve evidence and review recovery.",
                "relational_reactivation_unconfirmed": "Relational reactivation is unconfirmed. Do not retry; preserve evidence and review recovery.",
                "relational_start_recovery_unconfirmed": "Relational start recovery is unconfirmed. Do not retry; retain evidence for fresh local review.",
                "portable_restore_storage_failed": "Recovery storage could not be accessed. Check the device recovery logs.",
                "portable_restore_validation_failed": "The recovery file could not be validated. Check the export password and file.",
                "portable_restore_failed": "Recovery import or scheduling failed. Check the device recovery logs.",
            }
            if isinstance(result, dict) and isinstance(result.get("error"), str):
                message = messages.get(result["error"])
                if message:
                    raise UpdateHelperError(message)
            raise UpdateHelperError("The system update helper rejected the request")
        if result.get("status") != expected_status:
            raise UpdateHelperError("The system update helper response is invalid")
        return result
