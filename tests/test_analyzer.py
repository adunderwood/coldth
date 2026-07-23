import numpy as np

from coldth.analyzer import LocalSpectrumAnalyzer, analyze_pcm


def stereo_tone(frequency, samplerate=44100, frames=4096, amplitude=0.5):
    time = np.arange(frames) / samplerate
    mono = np.sin(2 * np.pi * frequency * time) * amplitude
    stereo = np.column_stack((mono, mono))
    return (stereo * 32767).astype("<i2").tobytes()


def test_one_kilohertz_tone_lands_in_one_kilohertz_band():
    levels = analyze_pcm(stereo_tone(1000))

    assert levels is not None
    assert levels.index(max(levels)) == 5
    assert levels[5] > levels[4] + 15
    assert levels[5] > levels[6] + 15


def test_silence_reports_meter_floor():
    levels = analyze_pcm(bytes(4096 * 2 * 2))

    assert levels == [-1000.0] * 10


def test_disabled_analyzer_stays_off():
    analyzer = LocalSpectrumAnalyzer(None)

    analyzer.start()

    assert analyzer.levels() is None
