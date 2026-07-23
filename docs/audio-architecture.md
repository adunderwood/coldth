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

The ten frequency-band lamps use a separate, optional raw-audio feed:

```text
mirrored program audio → Coldth arecord worker
                       → small real FFT
                       → ten geometric buckets
```

The analyzer is kept outside the playback instance so an analyzer crash or
excess CPU load cannot interrupt listening. If the second ALSA feed is missing,
the web interface shows the analyzer as standing by and does not invent
movement.

The base Pi deployment does not enable this second instance. The experimental
setup duplicates Shairport audio into two ALSA Loopback substreams before
either DSP instance; see [analyzer.md](analyzer.md). This keeps the analyzer
outside the playback path while its clock stability is validated. Stereo
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

1. Shairport Sync build (AirPlay 1 or AirPlay 2) and whether forcing 44.1 kHz is
   acceptable for that build.
2. Long-session buffer stability and AirPlay synchronization after the
   loopback handoff.
3. Whether the headphone jack's noise floor is acceptable for the intended
   speakers; a USB or I2S DAC can replace only the final ALSA device later.
4. Long-session clock behavior of the experimental two-substream analyzer
   fan-out.
