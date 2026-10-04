"""Reference provider contract, outside Core. No claim of physical GPIO support."""

from three_mm_protocol.capability_contracts import CapabilityContractV1


def object_schema(properties, required=()):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


def control_contract():
    channel = "gpio.output.1"
    boolean = {"type": "boolean"}
    state = object_schema({channel: boolean}, [channel])
    return CapabilityContractV1(
        capability_id="gpio.digital.control",
        contract_version="1.0",
        actions={
            "set_output": {
                "arguments_schema": object_schema(
                    {
                        "channel": {
                            "type": "string",
                            "maxLength": 32,
                            "enum": [channel],
                        },
                        "value": boolean,
                    },
                    ["channel", "value"],
                ),
                "result_schema": object_schema(
                    {
                        "outputs": state,
                        "inputs": object_schema({"gpio.input.1": boolean}),
                        "mock": boolean,
                    },
                    ["outputs"],
                ),
            }
        },
        state_schema=state,
        events={
            "gpio.output.changed": object_schema(
                {
                    "capability_id": {
                        "type": "string",
                        "maxLength": 160,
                        "enum": ["gpio.digital.control"],
                    },
                    "channel": {"type": "string", "maxLength": 32, "enum": [channel]},
                    "value": boolean,
                    "reason": {"type": "string", "maxLength": 32},
                    "mock": boolean,
                    "command_id": {"type": "string", "maxLength": 36},
                },
                ["capability_id", "channel", "value", "reason"],
            )
        },
    )
