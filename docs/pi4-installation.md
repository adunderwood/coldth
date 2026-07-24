# Raspberry Pi 4 installation

This guide describes the configuration proven on a dedicated Raspberry Pi 4
running Raspberry Pi OS and CamillaDSP 3.0.1. Device names can differ between
images and audio hardware, so run the discovery commands instead of copying a
device name blindly.

The required audio path is:

```text
AirPlay → Shairport Sync → ALSA Loopback → CamillaDSP :1234
                                              ↓
                                      Pi headphones
```

The optional ten-band analyzer is described in
[analyzer.md](analyzer.md). Get the base path working first.

## Recommended: automated installation

From a fresh clone, run:

```sh
./scripts/install-pi.sh
```

For the exact setup including the experimental ten-band display:

```sh
./scripts/install-pi.sh --with-analyzer
```

The installer performs the steps in this guide, derives the service account
and repository paths, backs up replaced configuration with a
`.coldth-before` suffix, and runs `scripts/verify-pi.sh`. It can be re-run to
repair or update the installation.

Use the remaining sections for understanding, manual installation, and
troubleshooting.

## 1. Install system packages

```sh
sudo apt update
sudo apt install git python3-venv alsa-utils shairport-sync
```

Install an ARM build of CamillaDSP with WebSocket and ALSA support. On a
64-bit Raspberry Pi OS image, use the official `aarch64` build from the
[CamillaDSP releases](https://github.com/HEnquist/camilladsp/releases). Put the
binary at `/usr/local/bin/camilladsp` and confirm:

```sh
command -v camilladsp
camilladsp --version
```

Coldth has been exercised with CamillaDSP 3.0.1. Newer versions should work,
but generated configuration must always be validated on the target:

```sh
camilladsp -c /home/livingroom/coldth/data/camilladsp.json
```

Replace `livingroom` in this guide with the account that owns the checkout.

## 2. Install Coldth

```sh
cd /home/livingroom
git clone YOUR_COLDTH_REPOSITORY_URL coldth
cd coldth
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install .
```

Create the persistent data directory:

```sh
mkdir -p /home/livingroom/coldth/data
mkdir -p /home/livingroom/camilladsp
```

For development, install with `venv/bin/pip install -e ".[dev]"`.

## 3. Enable ALSA Loopback

Copy the module-load file:

```sh
sudo install -m 0644 deploy/snd-aloop.conf /etc/modules-load.d/snd-aloop.conf
sudo modprobe snd-aloop
```

Confirm that the card exists:

```sh
aplay -l
arecord -l
```

The normal pair is:

- writer: `hw:Loopback,0,0`
- reader: `hw:Loopback,1,0`

## 4. Configure Shairport Sync

Back up `/etc/shairport-sync.conf`, then configure its active `general` and
`alsa` sections:

```conf
general = {
    name = "Coldth";
    output_backend = "alsa";
};

alsa = {
    output_device = "hw:Loopback,0,0";
    output_rate = 44100;
    output_format = "S16";
};

metadata = {
    enabled = "yes";
    include_cover_art = "no";
    pipe_name = "/tmp/shairport-sync-metadata";
};
```

Make sure another active `output_device` does not still point directly to
`hw:Headphones`. Confirm that the installed build supports metadata:

```sh
shairport-sync -V
```

Its version string must include `metadata`. Track information travels through
the named pipe independently of audio. Artwork solicitation is deliberately
off by default.

Restart Shairport and reconnect the AirPlay sender:

```sh
sudo systemctl restart shairport-sync
```

If it cannot open the loopback device, inspect:

```sh
journalctl -u shairport-sync -n 50 --no-pager
id shairport-sync
```

The Shairport service account may need membership in the `audio` group.

## 5. Configure CamillaDSP

The distribution service used during development starts CamillaDSP in
WebSocket wait mode on port 1234. Coldth supplies the generated configuration.
It must start at unity gain; a packaged `-g-40` argument attenuates playback by
40 dB and can make the output and meters appear dead.

Do not edit `/usr/lib/systemd/system/camilladsp.service`. Create a drop-in:

```sh
sudo systemctl edit camilladsp
```

Use:

```ini
[Service]
ExecStart=
ExecStart=/usr/local/bin/camilladsp -s /home/livingroom/camilladsp/statefile.yml -w -g0 -o /home/livingroom/camilladsp/camilladsp.log -p 1234
```

The empty `ExecStart=` removes the command inherited from the packaged unit.
The second line supplies its replacement.

Verify that the drop-in was saved:

```sh
sudo systemctl daemon-reload
systemctl cat camilladsp --no-pager
systemctl show camilladsp -p ExecStart --no-pager
```

The resolved command must use `/usr/local/bin/camilladsp` and `-g0`.

If no CamillaDSP service was installed by the OS package, customize and install
the repository's standalone `deploy/camilladsp.service` instead:

```sh
sudo install -m 0644 deploy/camilladsp.service \
  /etc/systemd/system/camilladsp.service
```

## 6. Install the Coldth service

The repository service matches a checkout owned by `livingroom` with a virtual
environment named `venv`. Install it with:

```sh
sudo install -m 0644 deploy/coldth.service \
  /etc/systemd/system/coldth.service
```

Its complete contents are:

```ini
[Unit]
Description=Coldth web equalizer
Wants=network-online.target camilladsp.service
After=network-online.target camilladsp.service

[Service]
Type=simple
User=livingroom
Group=livingroom
SupplementaryGroups=audio
WorkingDirectory=/home/livingroom/coldth
Environment=COLDTH_DATA_DIR=/home/livingroom/coldth/data
Environment=COLDTH_HOST=0.0.0.0
Environment=COLDTH_PORT=8080
Environment=COLDTH_CAMILLADSP_URL=ws://127.0.0.1:1234
Environment=COLDTH_SHAIRPORT_METADATA_PIPE=/tmp/shairport-sync-metadata
Environment=COLDTH_SHAIRPORT_ARTWORK_AVAILABLE=false
# Optional; omit until docs/analyzer.md has been completed:
Environment=COLDTH_ANALYZER_DEVICE=hw:Loopback,1,1
Environment=COLDTH_CAPTURE_DEVICE=hw:Loopback,1,0
Environment=COLDTH_PLAYBACK_DEVICE=hw:Headphones,0
Environment=COLDTH_CAPTURE_FORMAT=S16LE
Environment=COLDTH_PLAYBACK_FORMAT=S16LE
ExecStart=/home/livingroom/coldth/venv/bin/coldth
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
# Coldth and Shairport Sync must see the same metadata FIFO in /tmp.
PrivateTmp=false
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/livingroom/coldth

[Install]
WantedBy=multi-user.target
```

The Pi headphone device rejects `S32LE` on the tested installation. Keep
`S16LE` unless `aplay` proves another format works.

Enable and start:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now camilladsp coldth shairport-sync
sudo systemctl restart camilladsp
sleep 2
sudo systemctl restart coldth
```

Coldth also watches for an inactive CamillaDSP and reapplies the saved
configuration after an engine restart.

`PrivateTmp=false` is intentional. Shairport and Coldth are different systemd
services and must see the same `/tmp/shairport-sync-metadata` FIFO. With
`PrivateTmp=true`, Coldth sees a private path and track metadata never arrives.

Open `/settings` to control whether Coldth accepts track information and album
artwork. Track information defaults on. Artwork defaults off and is retained
only in memory.

### Opt in to album artwork

Artwork requires explicit system-level and user-level consent. Change
Shairport's metadata block to:

```conf
include_cover_art = "yes";
```

Then change the Coldth service environment to:

```ini
Environment=COLDTH_SHAIRPORT_ARTWORK_AVAILABLE=true
```

Reload and restart both services:

```sh
sudo systemctl daemon-reload
sudo systemctl restart coldth shairport-sync
```

Finally enable **Use album artwork** at `/settings`. Shairport's
`include_cover_art` option controls whether it solicits artwork from the
sender; the browser setting controls whether Coldth retains and serves it.
To stop artwork transfer entirely, set `include_cover_art` back to `"no"` and
restart Shairport.

## 7. Verify the complete path

Open `http://PI_ADDRESS:8080` or `http://coldth.local:8080` if mDNS is
available. While AirPlay is playing, verify:

```sh
cat /proc/asound/Loopback/pcm0p/sub0/status
cat /proc/asound/Loopback/pcm1c/sub0/status
```

Both should say `RUNNING`. Query CamillaDSP:

```sh
venv/bin/python -c 'import json,websocket; w=websocket.create_connection("ws://127.0.0.1:1234"); [(w.send(json.dumps(c)),print(c,w.recv())) for c in ("GetVolume","GetState","GetCaptureSignalRms","GetPlaybackSignalRms")]'
```

Expected:

- volume `0.0`
- state `Running`
- two finite capture RMS values
- two finite playback RMS values

Digital silence is reported as `-1000.0`. Empty vectors indicate that
CamillaDSP is inactive or has not started an audio configuration.

## Updating

```sh
cd /home/livingroom/coldth
git pull
venv/bin/pip install .
sudo systemctl restart coldth
```

When dependencies or the virtual environment have not changed, reinstalling
the package is still recommended because the systemd service executes the
installed console entry point.

## Troubleshooting

### `status=203/EXEC`

The `ExecStart` path does not exist or is not executable. A virtual environment
named `venv` is different from `.venv`.

```sh
test -x /home/livingroom/coldth/venv/bin/coldth
```

### CamillaDSP is `Inactive`

Coldth has not supplied a configuration, or the audio device rejected it:

```sh
curl -s http://127.0.0.1:8080/api/state | venv/bin/python -m json.tool
tail -n 80 /home/livingroom/camilladsp/camilladsp.log
camilladsp -c /home/livingroom/coldth/data/camilladsp.json
```

### Audio works but meters show silence

If Shairport still outputs directly to `hw:Headphones`, it bypasses both
Coldth and CamillaDSP. Check:

```sh
sudo grep -R -nE 'output_backend|output_device|output_rate|output_format' \
  /etc/shairport-sync.conf /etc/shairport-sync.conf.d 2>/dev/null
```

### Audio is almost inaudible

Read CamillaDSP's global volume:

```sh
venv/bin/python -c 'import json,websocket; w=websocket.create_connection("ws://127.0.0.1:1234"); w.send(json.dumps("GetVolume")); print(w.recv())'
```

If it is `-40.0`, verify the systemd override uses `-g0`. Before raising gain,
turn down the physical amplifier to avoid a sudden volume jump.

## Backup and rollback

Back up these files:

- `/etc/shairport-sync.conf`
- `/etc/modules-load.d/snd-aloop.conf`
- `/etc/systemd/system/coldth.service`
- `/etc/systemd/system/camilladsp.service.d/override.conf`
- `/home/livingroom/coldth/data/state.json`

To bypass Coldth temporarily, restore Shairport's output device to
`hw:Headphones` and restart Shairport. Do not delete the Coldth data directory;
it contains the EQ, balance, and user presets.
