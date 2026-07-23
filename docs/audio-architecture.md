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

## Initial audio choices

- 44.1 kHz, stereo, 16-bit capture from Shairport Sync.
- 32-bit playback into ALSA.
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
