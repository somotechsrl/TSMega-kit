# TSMega-kit

TSMega-kit turns an Ubuntu PC into a standalone guitar rig using a **Tone Shifter pedalboard/audio interface, ToneLib GFX and SooperLooper**. It is designed for practice and live performance, with hardware control of presets, effects and loops.

The current audio and MIDI profile was tested with a **MeloAudio Tone Shifter Mega** and an **M-Wave Chocolate connected over USB**. Other Tone Shifter models need their audio ports and MIDI messages checked before using this profile.

## Local packages and installation

Version **1.0.11** renames the application to **TSMega-kit**, including its repository, launchers and user-data directory. The Ardour destination remains **TSMA-Kit**. Keyboard focus and pointer bounds are corrected for embedded and maximized windows.

Build AppImage, DEB and RPM locally using `packaging/README.md`. The generated files are in `dist/`: `TSMega-kit-1.0.11-x86_64.AppImage`, `tsmega-kit_1.0.11_amd64.deb` and `tsmega-kit-1.0.11-1.x86_64.rpm`. The sources are versioned on GitHub; the workflows run only when manually requested.

A 64-bit desktop with **glibc 2.35 or newer**, systemd user services, D-Bus and X11/XWayland is required. This covers Ubuntu 22.04+, Mint 21+, Debian 12+ and recent Fedora releases. Runtime checks have passed on Ubuntu 22.04/24.04, Debian 12 and Fedora 44; audio hardware and live latency still need validation on each PC. ARM and older glibc releases are not supported.

On Wayland desktops, the kit window automatically uses XWayland: its embedded Xephyr display requires X11 window IDs. XWayland must be enabled in the desktop session.

```bash
# Ubuntu / Mint / Debian
sudo apt install ./tsmega-kit_1.0.11_amd64.deb

# Fedora
sudo dnf install ./tsmega-kit-1.0.11-1.x86_64.rpm

# Portable bundle
chmod +x TSMega-kit-1.0.11-x86_64.AppImage
./TSMega-kit-1.0.11-x86_64.AppImage
```

The native packages add an application-menu entry and a desktop shortcut. For another desktop user, the shortcut is created at login or with `tsmega-kit --install-desktop`. The AppImage creates its shortcut on first use. If FUSE is unavailable, run the AppImage with `--appimage-extract-and-run`; native packages use an extraction cache and do not require FUSE.

**No author license, registration, credentials or personal backing tracks are included.** On first use, if ToneLib GFX is not already installed, the kit offers to download the official trial directly from tonelib.net. Each user can use that trial or activate it with their own license. Internet is only needed for that initial download; regular use can be offline.

User data lives in **`~/.local/share/tsmega-kit/kit`** (or `$XDG_DATA_HOME/tsmega-kit/kit`). Presets, loop audio and local backing tracks remain separate from the installed package and are preserved across upgrades. `TSMA_KIT_HOME` can select another writable data folder.

### Local drum backing tracks

Use the **Drums** button in the kit header to browse by style and BPM and load a file into ToneLib's Backing track player. After ToneLib finishes its audio-file analysis, playback starts automatically. Loading runs in the background so the host window stays responsive. Files are local to the user, not added to ToneLib's fixed built-in Rhythm Player patterns.

The importer extracts audio from local videos, keeps the originals and writes concise names such as `Jazz/Swing/120 BPM.flac` and `Bossa Nova/Brushes/070 BPM.flac`. FLAC 16-bit stereo at 48 kHz is the default; `--format wav` is available in the source script.

```bash
# Installed package: import your own local collection
 tsmega-kit --import-drums "$HOME/Desktop/GUITAR/Backtracks/Drums"

# Source checkout
./import-drums /path/to/drum-videos ./BackingTracks/Drums
```

FLAC files are loaded directly, without temporary WAV conversion. The generated library is stored under `BackingTracks/Drums` in the user-data folder. Personal audio is ignored by Git and is never shipped in public releases.

## How it works

```text
Guitar → Tone Shifter input L → ToneLib GFX → SooperLooper → Tone Shifter outputs
```

The launcher starts JACK if needed and opens a single **TSMega-kit** window: **ToneLib on top, SooperLooper below**, aligned to the same width without internal title bars. The window can be moved, resized and minimized as one application. Keyboard focus follows entry into the embedded applications while the kit is active; header controls, dialogs and other applications keep their own focus. After resizing or maximizing, the private display refreshes its pointer limits so clicks remain aligned throughout the enlarged window. On closing, its actual size and position are saved in `$XDG_CONFIG_HOME/tsmega-kit/window.json` (default: `~/.config/tsmega-kit/window.json`) and restored as a normal window at the next launch, even if it was maximized when closed. If a monitor is disconnected, the window is brought back onto an available screen.

ToneLib handles the sound; SooperLooper records, plays and overdubs loops. The kit reconnects its audio and MIDI paths when devices or applications return. It uses 48 kHz audio, a 256-frame JACK buffer and one stereo loop with up to 300 seconds of memory per channel.

**Ardour is optional and is never launched by the kit.** If an already-running Ardour session exposes the stereo inputs of a track named `TSMA-Kit`, the kit routes its output to that track. Otherwise it monitors through the Tone Shifter outputs. The Ardour session must provide its own monitoring/output routing.

The kit also displays a **live MIDImix fader legend**: eight numbered cells show the Ardour track/bus controlled by each fader. Bank Left/Right updates the legend immediately; track renames, visibility and ordering refresh from the running Ardour session within one second. The last moved fader is highlighted briefly. Each cell also contains two horizontal bars: **Vol** shows the actual fader gain in dB, and **VU** shows Ardour’s audio peak level, refreshing up to 25 times per second (green, amber above −6 dB, red at 0 dB). A **MUTE** badge lights up when the corresponding Ardour strip is muted. The volume bars have a **0 dB unity mark**: physical track faders snap to exactly 0 dB within ±0.45 dB and release beyond ±0.9 dB, preventing jitter while preserving native MIDI control outside the detent. The master fader retains its existing assignment.

Setup is automatic for **Ardour 8**: TSMega-kit installs its `Akai MidiMix TSMA Live` map and enables OSC while Ardour is closed, keeping a backup of the original preferences at `~/.config/ardour8/config.before-tsma-midimix`. If Ardour is already open during the first setup, the kit waits for it to close instead of interrupting a session. The next launch uses the prepared configuration; no manual MIDI/OSC setup is needed. The OSC port defaults to 3819 (`TSMA_ARDOUR_OSC_PORT` can override it).

While connected, the kit owns the MIDImix bank, starting at bank 1. Use the controller's Bank Left/Right buttons or the panel’s ‹/› buttons to change it. The proxy forwards faders, mute/solo/record buttons and other MIDI messages unchanged to Generic MIDI; bank buttons become absolute bank selections, and the unity detent sets exactly 0 dB only while a physical track fader is being moved near unity. Existing MIDI Learn controls are retained. Closing the kit, losing OSC or unplugging the controller restores its original direct JACK connection; the worker also restores it if the host window process crashes. When names or synchronization are unavailable, the cells show **—** rather than stale assignments. No audio routing or track volume is changed to discover names.

When Ardour is closed, the kit also sends its final stereo mix (guitar, loops and backing tracks) to the existing PipeWire JACK bridge, if available. In OBS, add **Audio Input Capture (PulseAudio)** and select **JACK Source** (`jack_source`). The Tone Shifter listening outputs remain connected. Opening Ardour disconnects this extra feed, including when its session has no `TSMega-kit` track; closing Ardour restores it automatically. This requires PipeWire's JACK tunnel (`PipeWire:capture_FL/FR`); the kit leaves unrelated PipeWire connections and desktop audio settings intact.

## Pedal controls

| Controller | Button | Action |
|---|---|---|
| Tone Shifter Mega | 1 / 2 | Previous / next ToneLib preset |
| Tone Shifter Mega | 3 / 4 (arrows) | Previous / next hardware bank; A–D confirms the pending selection |
| Tone Shifter Mega | A–D | Toggle the corresponding effect on the selected page |
| M-Wave Chocolate | A | Record an empty loop; press again to finish and play. With an existing loop, play/retrigger it. |
| M-Wave Chocolate | B | Overdub on/off |
| M-Wave Chocolate | C | Pause/resume |
| M-Wave Chocolate | D | Clear the loop |

To record a replacement loop: **D → A → play your guitar → A**. Page selection on the TS Mega is reported by the next A–D message. The current mapping controls up to eight effects in chain order.

Beside **Drums** and **Check**, the header shows the last confirmed effect group and the relative/absolute effect number, for example **Banco: 5–8 · Effetto: 1 → 5**. It covers all 128 Program Change positions in groups of four, including 9–12, 13–16 and so on. It shows **—** before the first message or after a disconnection. In the pedal's waiting bank mode, 3/4 change the flashing bank prefix locally; A–D confirms it and sends MIDI, updating the indicator. The indicator represents the confirmed effect group and last pressed effect, not the pending flashing prefix or an effect's on/off state.

Starting with 1.0.9, the indicator also shows the effect name from ToneLib's current chain, for example **Effetto: 1 → 5 · Spring Rvb**. A background reader requests ToneLib's native Copy preset summary on the kit's private display while its main window has focus and no keys are held. It restores the private text clipboard; the desktop clipboard is separate. Names refresh after MIDI messages and periodically to reflect preset edits. When a name cannot be read, only the numeric position is shown. Long names are shortened visually and remain available in the tooltip and details.

ToneLib's assignment dialog exposes **Control 1–8**, which the kit maps to the first eight effects. Higher positions are displayed as **non assegnato** and ignored by the adapter: they never wrap back onto effects 1–8 or send looper actions. Extending the display does not add native ToneLib controls beyond those eight. The Check utility learns the full Program Change value for the first bank's A button, without reducing it modulo eight.

The Chocolate must use its saved Custom CC profile: MIDI channel 1, CC 80/81/82/83 for A/B/C/D, momentary 127/0. The performance adapter handles presses and ignores releases. Hardware programming is an explicit operation in the Check utility described below.

## Pedal Check and programming

Open **Check**, beside **Drums** in the kit header. The utility detects the **Tone Shifter Mega (TSMEGA)** and **standard USB Chocolate (SINCO)** by name, monitors their actual MIDI messages and follows USB reconnections. It does not start Ardour or change audio routing.

| Device | Verification | Configuration |
|---|---|---|
| Tone Shifter Mega | Guided test of 1/2 and A–D on both effect pages; live CC/PC messages | Learn the previous/next CCs and the page-1 A PC offset; save software mappings for the kit. Hardware USB programming is not implemented. |
| Standard Chocolate | Read its Custom CC settings, compare them with the kit profile, and test A–D | Apply the kit looper profile over USB, or restore its Custom CC fields from a utility backup. |

**Test mode** temporarily suspends pedal actions in the kit adapter, so testing D does not clear your loop and testing 1/2 does not switch presets. Audio continues. Disable test mode or close Check to resume normal control. A short-lived lease also restores pedal actions within a few seconds if the utility crashes. Test mode requires the updated kit adapter; the utility rejects an older running adapter rather than pretending its actions are paused.

On the **Tone Shifter** tab, use **Learn** for button 1, button 2 or page-1 A, then **Save Tone Shifter mappings**. The adapter reloads the saved software profile within two seconds. This changes the kit's interpretation of MIDI, not the pedal firmware. The expected hardware layout is 1/2 sending separate preset CCs, A–D sending consecutive Program Changes, and 3/4 selecting internal banks. Selecting 3/4 alone may send no MIDI: the following A–D message identifies the page. Both values from the existing latched 1/2 profile count as presses; a different momentary press/release profile should be configured on the pedal itself.

On the **Chocolate** tab, connect the standard controller over **USB in U mode** and select **Read / verify**. **Apply TSMA looper profile** writes Custom CC mode 7, channel 1, CC80–83 and momentary switches. Before writing, it backs up the first 1009-byte Custom CC settings region. Each changed field is read back and compared with the complete region; an unexpected change stops programming. Only mode, channel and the four CC/latch pairs can be written. Advanced banks, firmware, Bluetooth and Chocolate Plus programming are outside this utility. A readback confirms the current configuration; unplug/replug and run the guided test to verify persistence and physical switch behavior.

**Restore backup** restores those ten supported fields, with another backup first. It is not a full firmware or complete-device restore. **Save report** records device discovery, observed messages and completed test steps; a connected device is not automatically marked as having passed its physical test.

Software mappings live in `config/pedals.conf` inside the writable kit data folder and survive package upgrades. Backups and reports live in `state/pedals/` and are excluded from GitHub/releases. Existing ToneLib presets, registration and loop audio are not changed by the utility.

```bash
# Installed DEB/RPM or AppImage: diagnostics without starting the audio kit
tsmega-kit --check
./TSMega-kit-VERSION-x86_64.AppImage --check

# Source checkout
./check-pedals
```

The tool uses the bundled Python/GTK and ALSA libraries; it needs no Wine, Bluetooth manager or extra Python MIDI packages. The Chocolate SysEx protocol is documented by [cbix/mvave-chocolate-sysex](https://github.com/cbix/mvave-chocolate-sysex).

## Install and run

The supported installation target is an **Ubuntu/Debian/Mint x86_64 desktop** with a user systemd session and X11 or XWayland. The bundled profile has been tested locally; each new PC still needs an audio, latency and USB reconnect check before live use.

1. For a source checkout, install [ToneLib GFX](https://tonelib.net/downloads.html) separately. The proprietary application and its license are **not included** in this repository. The setup was tested with ToneLib GFX 4.9.
2. Clone the repository and run the installer as your normal desktop user:

   ```bash
   git clone https://github.com/somotechsrl/TSMega-kit.git
   cd TSMega-kit
   ./install-tsmega
   ```

   The installer installs missing system dependencies with `sudo`, builds the MIDI adapter and menu lock module, imports the saved ToneLib settings/preset slots, and creates a desktop icon. Existing ToneLib configuration is backed up under `~/.local/share/tsmega-kit/backups/` before import. Use `./install-tsmega --keep-profile` to retain an existing profile instead.
3. Connect both pedalboards, plug the guitar into input L, connect headphones or amplification to the Tone Shifter, and open the **TSMega-kit** desktop icon or run:

   ```bash
   ./start-tsmega
   ```

The folder can be moved. Stop the kit before moving it and rerun the installer to update the desktop icon. On another Linux distribution, install the dependencies yourself and use `./install-tsmega --no-deps`. ARM is not supported by the tested ToneLib application.

## Performance interface and saved data

The SooperLooper menu is hidden and disabled, and its menu accelerators are removed. A clickable guard covers ToneLib's preferences button, while common preferences shortcuts are intercepted inside the container. These controls prevent accidental configuration changes during performance; they are not an access-control boundary. For maintenance, stop the kit and open the original applications outside the container.

- `save-loop` requests a loop save. The engine also saves after recording/overdub finishes and when pausing; a saved loop is restored paused.
- `save-config` exports the current preset slots and musical settings into this source tree, excluding personal paths, recordings and registration files. Review preset/IR content before publishing further changes.
- `stop-tsmega`, or closing the container window, stops the kit gracefully. JACK and external applications remain separate.
- `state/` holds local SooperLooper session/audio data; `log/` holds diagnostics. Both are ignored by Git.

The repository includes the saved preset parameter slots and MIDI mappings. **Recorded loops, registration credentials, proprietary binaries and external impulse-response audio are excluded.** Presets that use external IRs need those IRs installed locally. The existing private portable kit retains the full personal configuration.

## Development checks

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s config/Jack/Drivers.d/tests -v
cc -Wall -Wextra -Werror -O2 config/Jack/Drivers.d/tsmega-midi.c \
  -Wl,-l:libasound.so.2 -o /tmp/tsma-midi-check
/tmp/tsma-midi-check --self-test
```

These checks run without audio hardware. The source of the SooperLooper GTK menu lock is in `src/slgui-lock.c`; the nested GUI is managed by `bin/gui.py` using GTK3, Xephyr and Openbox.
