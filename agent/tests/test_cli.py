from agent.cli import build_parser


def test_cli_preserves_gpio_environment_settings(monkeypatch):
    monkeypatch.setenv("THREE_MM_GPIO_DRIVER", "gpiod")
    monkeypatch.setenv("THREE_MM_GPIO_INPUTS", "gpio.input.1:17")
    monkeypatch.setenv("THREE_MM_GPIO_OUTPUTS", "gpio.output.1:27")
    monkeypatch.setenv("THREE_MM_IDENTIFIER_DRIVER", "mock")
    monkeypatch.setenv("THREE_MM_IDENTIFIER_READER_ID", "reader.mock.2")

    arguments = build_parser().parse_args([])

    assert arguments.gpio_driver == "gpiod"
    assert arguments.gpio_inputs == {"gpio.input.1": 17}
    assert arguments.gpio_outputs == {"gpio.output.1": 27}
    assert arguments.identifier_driver == "mock"
    assert arguments.identifier_reader_id == "reader.mock.2"


def test_cli_does_not_turn_environment_flags_into_hardware_consent(monkeypatch, tmp_path):
    import agent.cli as cli

    monkeypatch.setenv("THREE_MM_CHARACTER_DISPLAY_DRIVER", "pcf8574")
    monkeypatch.setenv("THREE_MM_CHARACTER_DISPLAY_APPROVED_PROFILE", "a" * 64)
    captured = []
    monkeypatch.setattr(cli, "create_app", lambda settings: captured.append(settings) or object())
    monkeypatch.setattr(cli.uvicorn, "run", lambda *args, **kwargs: None)
    cli.main(["--data-dir", str(tmp_path)])
    assert not hasattr(captured[0], 'character_display_driver')
    assert not hasattr(captured[0], 'character_display_approved_profile')
