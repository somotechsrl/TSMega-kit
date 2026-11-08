TSMega-kit 1.0.10

- Show the last pedal effect's actual on/off state read directly from ToneLib GFX: green `● Acceso` or gray `○ Spento`, alongside its name, bank and position. Unavailable states remain neutral.
- Fix missing effect descriptions after reboot when the private Xephyr display reports Num Lock, Caps Lock or Scroll Lock as held. Real typing and held modifiers still suspend clipboard queries.
- Send the final stereo mix to the existing PipeWire JACK Source when Ardour is closed, for capture in OBS. Opening Ardour removes this extra feed while preserving unrelated PipeWire connections.

Validation: 49 offline regression tests, GTK checks for on/off/unknown button states, and live name/state reading from ToneLib GFX.

Downloads: self-contained x86_64 AppImage, DEB and RPM, corresponding runtime sources and SHA-256 checksums. Requires glibc 2.35+, systemd user services, and X11 or a Wayland desktop with XWayland enabled. ToneLib is downloaded separately from its official vendor. No personal license, registration or backing-track audio is included.

TSMega-kit 1.0.9

- Fix startup crashes on Wayland desktops: the kit window selects XWayland before GTK initializes, so the embedded Xephyr display receives X11 window IDs. X11 desktop sessions remain supported.
- Show the current effect name beside its bank and position, for example `Banco: 5–8 · Effetto: 1 → 5 · Spring Rvb`, when ToneLib's native preset summary is available.
- Refresh effect names after pedal actions and preset changes; discard stale replies from earlier presets. The reader runs on the private application display and preserves its text clipboard.
- Retain all 128 displayed positions, the eight native ToneLib assignments, automatic drum playback, saved window geometry, Check pedal configuration and the USB audio fix.

Validation: offline regression tests, GTK smoke checks with X11 and inherited Wayland backend settings, and successful startup with ToneLib and SooperLooper in a Wayland desktop session.

Downloads: self-contained x86_64 AppImage, DEB and RPM, corresponding runtime sources and SHA-256 checksums. Requires glibc 2.35+, systemd user services, and X11 or a Wayland desktop with XWayland enabled. ToneLib is downloaded separately from its official vendor. No personal license, registration or backing-track audio is included.
