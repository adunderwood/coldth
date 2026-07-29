from __future__ import annotations

import subprocess
from pathlib import Path


HELPER = Path(__file__).parents[1] / "scripts" / "lib" / "audio-device.sh"


def detect_usb_devices(aplay_output: str) -> list[str]:
    result = subprocess.run(
        ["bash", "-c", f"source {HELPER!s}; coldth_usb_playback_devices"],
        input=aplay_output,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def test_detects_stable_usb_playback_device_and_ignores_hdmi_and_loopback():
    assert detect_usb_devices(
        """\
**** List of PLAYBACK Hardware Devices ****
card 0: vc4hdmi [vc4-hdmi], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
card 1: A [USB-C to 3.5mm Headphone Jack A], device 0: USB Audio [USB Audio]
card 2: Loopback [Loopback], device 0: Loopback PCM [Loopback PCM]
"""
    ) == ["hw:CARD=A,DEV=0"]


def test_reports_each_usb_playback_endpoint_once():
    assert detect_usb_devices(
        """\
card 3: DAC [USB DAC], device 0: USB Audio [USB Audio]
card 3: DAC [USB DAC], device 0: USB Audio [USB Audio]
card 4: Conference [USB Conference], device 1: USB Audio [USB Audio]
"""
    ) == ["hw:CARD=DAC,DEV=0", "hw:CARD=Conference,DEV=1"]
