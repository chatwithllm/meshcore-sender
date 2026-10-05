# MeshCore Sender App

Enter the companion radio's **Linux Bluetooth MAC address** in Configuration, start
the App, and open Web UI to create a passphrase. Enable Start on boot and Watchdog.
The radio needs to be in range of the host's local Bluetooth adapter. Quit the Mac
app before connecting so it releases the radio.

Full setup, dashboard integration and test checklist:
https://github.com/chatwithllm/meshcore-sender/blob/main/homeassistant.md

This experimental version runs independently of Mac login. It keeps its settings
in App storage. Active range tests stop if the App restarts and need to be restarted.
