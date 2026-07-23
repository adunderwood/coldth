# Optional ten-band analyzer

Coldth's L/R meters come from CamillaDSP's playback peak and RMS telemetry.
Those numbers contain no frequency information. The ten-band display therefore
needs a copy of the raw PCM audio.

Coldth implements a deliberately inexpensive analyzer:

```text
second ALSA Loopback feed
        ↓
arecord (S16LE stereo, 44.1 kHz)
        ↓
2,048-frame Hann window
        ↓
NumPy real FFT
        ↓
ten geometric frequency buckets
        ↓
existing Coldth meter WebSocket
```

It is a visual aid in the spirit of a late-1980s receiver, not a
measurement-grade FFT. It uses real samples and never invents movement.

## Safety boundary

The analyzer does not sit in the speaker path. Shairport's audio is duplicated
before the main CamillaDSP instance:

```text
Shairport Sync
      ↓
ALSA coldth_fanout
   ↙               ↘
Loopback sub 0     Loopback sub 1
   ↓                   ↓
CamillaDSP :1234   Coldth arecord worker
   ↓
headphones
```

If `arecord`, NumPy, or the analyzer thread fails, Coldth shows “analyzer
standby” and retries. The main CamillaDSP path remains separate.

There is no analyzer network port and no second CamillaDSP process.

## Enable it on a Pi

The base installation must already be working. Confirm that ALSA Loopback
offers at least two subdevices:

```sh
aplay -l
arecord -l
```

Install the fan-out:

```sh
sudo install -m 0644 deploy/asound-analyzer.conf.example /etc/asound.conf
```

Change Shairport's active ALSA section to:

```conf
alsa = {
    output_device = "coldth_fanout";
    output_rate = 44100;
    output_format = "S16";
};
```

Add this to the Coldth service:

```ini
Environment=COLDTH_ANALYZER_DEVICE=hw:Loopback,1,1
```

Ensure the service user belongs to the `audio` group and that `arecord` is
installed:

```sh
command -v arecord
id livingroom
```

Then:

```sh
sudo systemctl daemon-reload
sudo systemctl restart shairport-sync
sudo systemctl restart coldth
```

Disconnect and reconnect AirPlay. During playback, all four endpoints should
be active:

```sh
cat /proc/asound/Loopback/pcm0p/sub0/status
cat /proc/asound/Loopback/pcm0p/sub1/status
cat /proc/asound/Loopback/pcm1c/sub0/status
cat /proc/asound/Loopback/pcm1c/sub1/status
```

Substream 0 carries the listening path. Substream 1 carries the analyzer copy.
The UI changes from “10-band analyzer standby” to “10-band analyzer live” as
soon as complete PCM windows arrive.

## Test the analyzer feed directly

This records one second from the analyzer substream and throws it away:

```sh
arecord -q -D hw:Loopback,1,1 -f S16_LE -c 2 -r 44100 \
  -d 1 -t raw > /dev/null
```

If it fails, inspect:

```sh
journalctl -u shairport-sync -u coldth -n 80 --no-pager
```

## Disable or roll back

Remove or comment out `COLDTH_ANALYZER_DEVICE` to disable only the FFT worker.

To remove the ALSA fan-out completely:

1. restore Shairport's `output_device` to `hw:Loopback,0,0`;
2. remove `/etc/asound.conf` if it contains only the Coldth fan-out;
3. restart Shairport and Coldth; and
4. reconnect AirPlay.

The EQ and stereo meters do not require the ten-band analyzer.

## Status

The FFT implementation is tested with generated PCM tones. The two-substream
ALSA fan-out remains experimental until it completes a long playback session
on the target Pi without underruns or clock drift.
