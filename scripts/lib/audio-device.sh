#!/usr/bin/env bash

# Parse `aplay -l` and emit stable ALSA hardware names for USB playback
# devices, one per line. Card IDs are preferred over numeric indexes because
# indexes can change when HDMI, USB, or loopback devices appear in a different
# order at boot.
coldth_usb_playback_devices() {
  LC_ALL=C awk '
    /^card [0-9]+:/ && /device [0-9]+:/ && /USB Audio/ {
      card = $3
      device = ""
      for (field = 1; field <= NF; field++) {
        if ($field == "device" && field < NF) {
          device = $(field + 1)
          sub(/:$/, "", device)
          break
        }
      }
      if (card != "" && device ~ /^[0-9]+$/) {
        endpoint = "hw:CARD=" card ",DEV=" device
        if (!seen[endpoint]++) {
          print endpoint
        }
      }
    }
  '
}
