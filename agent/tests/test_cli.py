from agent.cli import build_parser


def test_cli_preserves_gpio_environment_settings(monkeypatch):
    monkeypatch.setenv("THREE_MM_GPIO_DRIVER", "gpiod")
    monkeypatch.setenv("THREE_MM_GPIO_INPUTS", "gpio.input.1:17")
    monkeypatch.setenv("THREE_MM_GPIO_OUTPUTS", "gpio.output.1:27")

    arguments = build_parser().parse_args([])

    assert arguments.gpio_driver == "gpiod"
    assert arguments.gpio_inputs == {"gpio.input.1": 17}
    assert arguments.gpio_outputs == {"gpio.output.1": 27}
