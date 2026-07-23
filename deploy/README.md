# Deployment files

These are inputs and reference templates for system integration. Coldth does
not automatically read files from this directory at runtime.

For a new Raspberry Pi, use `scripts/install-pi.sh`; it detects the actual
checkout path and account and generates the installed configuration.

- `coldth.service` — example Coldth service for the original `livingroom`
  installation.
- `camilladsp.service` — standalone CamillaDSP service for a machine that does
  not already have a suitable packaged unit.
- `snd-aloop.conf` — persistent kernel-module loading.
- `shairport-sync.conf.example` — minimal settings to merge into Shairport.
- `asound-analyzer.conf.example` — optional, experimental two-substream ALSA
  fan-out for the ten-band FFT.

Do not copy every file blindly. In particular, do not replace a working
packaged CamillaDSP service merely because an example exists here.
