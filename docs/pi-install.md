# Raspberry Pi 4 installation notes

These are intentionally still manual while the audio path is being verified on
the first target Pi. They should become an idempotent installer only after the
device names and Shairport build are confirmed.

## Assumptions

- Raspberry Pi 4
- 64-bit Raspberry Pi OS Lite
- Built-in 3.5 mm headphone jack
- Shairport Sync is already installed and can receive an AirPlay stream

## Inspect the Pi first

Record:

```sh
cat /etc/os-release
uname -m
shairport-sync -V
aplay -L
```

The expected headphone identifier is `hw:Headphones,0`, but use the value shown
by `aplay -L`. Test it directly before adding Coldth.

## Components

1. Install the CamillaDSP aarch64 prebuilt binary as
   `/usr/local/bin/camilladsp`.
2. Create a locked-down `coldth` system user and add it to the `audio` group.
3. Copy the repository to `/opt/coldth`, create a virtual environment, and
   install the package.
4. Create `/var/lib/coldth`, owned by `coldth:coldth`.
5. Copy [snd-aloop.conf](../deploy/snd-aloop.conf) to
   `/etc/modules-load.d/snd-aloop.conf`, then load it with
   `sudo modprobe snd-aloop`.
6. Merge [shairport-sync.conf.example](../deploy/shairport-sync.conf.example)
   into the installed Shairport configuration.
7. Install the two service units from `deploy/` in `/etc/systemd/system/`.
8. Add a Shairport service override:

   ```ini
   [Unit]
   After=camilladsp.service
   Requires=camilladsp.service
   ```

9. Reload systemd and enable Coldth, CamillaDSP, and Shairport Sync.

### Home-directory checkout

The supplied service uses `/opt/coldth` and `/var/lib/coldth`. A checkout in a
user's home directory also works, but all of these unit settings must agree
with the actual paths:

```ini
User=livingroom
Group=livingroom
WorkingDirectory=/home/livingroom/coldth
Environment=COLDTH_DATA_DIR=/home/livingroom/coldth/data
ExecStart=/home/livingroom/coldth/venv/bin/coldth
ProtectHome=read-only
ReadWritePaths=/home/livingroom/coldth
```

Do not use `ProtectHome=true` with an executable under `/home`; systemd will
hide the executable from the service and exit with status `203/EXEC`.

## First audio test

Before testing AirPlay, verify each boundary separately:

1. Confirm `snd-aloop` appears in `aplay -l` and `arecord -l`.
2. Start Coldth once and confirm it creates
   `/var/lib/coldth/camilladsp.json`.
3. Validate that file with `camilladsp --check`.
4. Start CamillaDSP and inspect `journalctl -u camilladsp`.
5. Send a known 44.1 kHz stereo PCM signal into the loopback.
6. Only then start Shairport Sync and stream from Apple Music.

Do not raise speaker or amplifier volume until the flat path has played cleanly
without underruns, stalls, or unexpectedly high level.
