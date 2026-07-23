# Audio architecture

## MVP path

Coldth targets a Raspberry Pi 4 running 64-bit Raspberry Pi OS Lite:

```text
Shairport Sync
  output: hw:Loopback,0,0
       ↓
snd-aloop kernel device
       ↓
CamillaDSP
  capture:  hw:Loopback,1,0
  playback: hw:Headphones,0
       ↓
Pi 4 3.5 mm headphone jack
```

The exact hardware device identifier must be confirmed with `aplay -L` on the
target Pi. Coldth therefore makes both device names configurable.

## Responsibilities

- **Shairport Sync** owns AirPlay, stream timing, and source volume.
- **ALSA loopback** creates a stable handoff between the receiver and processor.
- **CamillaDSP** owns the real-time audio threads and ten peaking filters.
- **Coldth** owns persistent EQ intent, presets, configuration generation, and
  the web interface.

CamillaDSP listens on `127.0.0.1:1234`; it is not exposed to the LAN. Coldth
sends `SetConfigJson` when a setting changes. A copy of the generated
configuration is written atomically so CamillaDSP can start with the last saved
shape after a reboot.

## Metering and optional analyzer

Coldth reads the main CamillaDSP instance's playback peak and RMS values for
the two stereo meters. This is control-plane telemetry only; it does not add a
stage to the audio pipeline.

The ten frequency-band lamps have a separate, optional contract:

```text
mirrored program audio → analyzer-only CamillaDSP (:1235)
                       → ten band-pass channels
                       → playback RMS telemetry → Coldth
```

The analyzer is kept outside the playback instance so an analyzer crash,
configuration error, or excess CPU load cannot interrupt listening. Coldth
expects exactly ten values in EQ order (31 Hz through 16 kHz) from
`GetPlaybackSignalRms`. If the second instance is missing, the web interface
shows the analyzer as standing by and does not invent movement.

The Pi deployment does not enable this second instance yet. Its audio mirror
must first be tested against the Pi's real ALSA topology; sharing the current
loopback capture naively could disturb CamillaDSP's rate adjustment. Stereo
meters work without it.

## Initial audio choices

- 44.1 kHz, stereo, 16-bit capture from Shairport Sync (`S16LE`).
- 16-bit playback into ALSA by default. The Pi 4 headphone device may reject
  32-bit samples; the format remains configurable for USB or I2S DACs.
- 1024-frame processing chunks.
- CamillaDSP rate adjustment enabled. ALSA Loopback supports capture clock
  tuning, which is preferred over continuously filling or draining a buffer.
- Ten peaking biquads with a fixed Q of 1.4. This is an internal graphic-EQ
  implementation choice, not a user-facing control.
- Automatic pre-gain equal to the largest positive band gain. This is
  conservative but prevents an ordinary boosted curve from immediately
  clipping full-scale input.

## Unknowns to verify on hardware

1. The Pi's actual headphone ALSA identifier and accepted sample formats.
2. Shairport Sync build (AirPlay 1 or AirPlay 2) and whether forcing 44.1 kHz is
   acceptable for that build.
3. Buffer stability and AirPlay synchronization after the loopback handoff.
4. Startup ordering when no AirPlay stream is active.
5. Whether the headphone jack's noise floor is acceptable for the intended
   speakers; a USB or I2S DAC can replace only the final ALSA device later.
6. The safest analyzer audio mirror on the target Pi, without sharing or
   blocking the main capture device.
