#!/usr/bin/env python3
"""GTK pedal verification, software mapping and verified Chocolate programming."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from alsa_midi import Sequencer, devices
from pedals import (Chocolate, DEFAULT, LOOP_ACTIONS, atomic_write, describe,
                    is_channel_message, load_profile, restore_values, save_profile, summary)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / f'jack-hooks-{os.getuid()}'
STORE = ROOT / 'state' / 'pedals'


def guard_available():
    """An old adapter must never be mistaken for one supporting silent tests."""
    result = subprocess.run(['pgrep', '-x', 'tsmega-midi'], capture_output=True, text=True)
    for pid in result.stdout.split():
        try:
            if b'tsma-pedal-check.lease' not in Path(f'/proc/{pid}/exe').read_bytes(): return False
        except OSError: return False
    return True


class PedalCheck(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title='TSMega-kit — Pedal Check', transient_for=parent)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT if parent is not None else Gtk.WindowPosition.CENTER)
        self.set_default_size(900, 700)
        self.set_border_width(12)
        if (ROOT / 'icona.svg').exists(): self.set_icon_from_file(str(ROOT / 'icona.svg'))
        RUNTIME.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.instance_lock = (RUNTIME / 'tsma-pedal-utility.lock').open('w')
        try: fcntl.flock(self.instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.instance_lock.close(); self.destroy(); raise RuntimeError('Pedal Check is already open.')
        self.lease = RUNTIME / 'tsma-pedal-check.lease'
        self.closed = self.busy = False
        self.seq = None
        self.profile_path = ROOT / 'config' / 'pedals.conf'
        self.profile = load_profile(self.profile_path)
        self.seen = {}; self.passed = []; self.steps = []; self.learning = None
        self.hardware = None; self.observed = []; self.last_scan = 0
        self.last_lease = 0.
        self.worker = None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); self.add(box)
        self.status = Gtk.Label(label='Connecting to pedal MIDI…', xalign=0)
        box.pack_start(self.status, False, False, 0)
        self.test_mode = Gtk.CheckButton(label='Test mode — pause pedal actions in the kit')
        self.test_mode.connect('toggled', self.toggle_test); box.pack_start(self.test_mode, False, False, 0)
        notebook = Gtk.Notebook(); box.pack_start(notebook, False, False, 0)
        overview = self.tab(notebook, 'Devices & test')
        self.device_status = Gtk.Label(xalign=0); overview.pack_start(self.device_status, False, False, 0)
        self.instruction = Gtk.Label(label='Start a guided test to verify each physical switch.', xalign=0)
        self.instruction.set_line_wrap(True); overview.pack_start(self.instruction, False, False, 0)
        row = Gtk.Box(spacing=8); overview.pack_start(row, False, False, 0)
        for title, target in [('Test Tone Shifter', 'TSMEGA'), ('Test Chocolate', 'SINCO')]:
            button = Gtk.Button(label=title); button.connect('clicked', lambda _, t=target: self.start_test(t)); row.pack_start(button, False, False, 0)
        button = Gtk.Button(label='Save report'); button.connect('clicked', self.save_report); row.pack_start(button, False, False, 0)

        tone = self.tab(notebook, 'Tone Shifter')
        info = Gtk.Label(label='Software mappings, reloaded by the kit within two seconds. No hardware settings are written.\n'
                               'For the current hardware profile: 1/2 send CC22/25 (both values count as presses).\n'
                               '3/4 change the hardware bank; the following A–D reports its page using PC messages.\n'
                               'USB hardware programming is not implemented: configure the pedal panel if needed.', xalign=0)
        info.set_line_wrap(True); tone.pack_start(info, False, False, 0)
        grid = Gtk.Grid(column_spacing=8, row_spacing=6); tone.pack_start(grid, False, False, 0)
        self.spins = {}
        for i, (key, title, maximum) in enumerate([('previous_cc', '1 · Previous preset CC', 127),
                                                 ('next_cc', '2 · Next preset CC', 127),
                                                 ('effect_offset', 'First bank · A Program Change', 127)]):
            grid.attach(Gtk.Label(label=title, xalign=0), 0, i, 1, 1)
            spin = Gtk.SpinButton.new_with_range(0, maximum, 1); spin.set_value(self.profile[key]); self.spins[key] = spin
            grid.attach(spin, 1, i, 1, 1)
            button = Gtk.Button(label='Learn'); button.connect('clicked', lambda _, k=key: self.learn(k)); grid.attach(button, 2, i, 1, 1)
        button = Gtk.Button(label='Save Tone Shifter mappings'); button.connect('clicked', self.save_tone); tone.pack_start(button, False, False, 0)

        chocolate = self.tab(notebook, 'Chocolate')
        self.choc_status = Gtk.Label(label='Standard USB Chocolate (SINCO) only; Chocolate Plus and Bluetooth are not supported.', xalign=0)
        self.choc_status.set_line_wrap(True); chocolate.pack_start(self.choc_status, False, False, 0)
        text = Gtk.Label(label='TSMA profile: Custom CC, channel 1, momentary 127/0.\n'
                               'A = CC80 Rec/Play · B = CC81 Overdub · C = CC82 Pause/Resume · D = CC83 Clear\n'
                               'Programming backs up the current Custom CC region and reads back every changed field.\n'
                               'Only mode, channel and the four CC/latch pairs are written; other settings are preserved.', xalign=0)
        text.set_line_wrap(True); chocolate.pack_start(text, False, False, 0)
        row = Gtk.Box(spacing=8); chocolate.pack_start(row, False, False, 0)
        self.operation_buttons = []
        for title, fn in [('Read / verify', lambda _: self.chocolate_operation('read')),
                          ('Apply TSMA looper profile', lambda _: self.chocolate_operation('program')),
                          ('Restore backup…', self.restore)]:
            button = Gtk.Button(label=title); button.connect('clicked', fn); row.pack_start(button, False, False, 0); self.operation_buttons.append(button)
        scroll = Gtk.ScrolledWindow(); scroll.set_min_content_height(140)
        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.add(self.log_view); box.pack_start(scroll, True, True, 0)
        self.buffer = self.log_view.get_buffer()
        self.connect('delete-event', self.request_close); self.connect('destroy', self.cleanup)
        self.show_all()
        GLib.timeout_add(40, self.tick)

    @staticmethod
    def tab(notebook, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8); box.set_border_width(12)
        notebook.append_page(box, Gtk.Label(label=title)); return box

    def log(self, text):
        if self.closed: return False
        self.buffer.insert(self.buffer.get_end_iter(), time.strftime('%H:%M:%S ') + text + '\n')
        if self.buffer.get_line_count() > 250:
            start = self.buffer.get_start_iter(); end = self.buffer.get_iter_at_line(50); self.buffer.delete(start, end)
        self.log_view.scroll_to_iter(self.buffer.get_end_iter(), 0, False, 0, 0)
        return False

    def toggle_test(self, *_):
        if self.test_mode.get_active():
            if not guard_available():
                self.test_mode.set_active(False); self.log('Update/restart the kit: the running MIDI adapter does not support safe test mode.'); return
            self.refresh_lease(); self.status.set_text('Test mode: MIDI is visible here; kit pedal actions are paused. Audio continues.')
        else:
            if self.busy:
                self.test_mode.set_active(True); return
            self.lease.unlink(missing_ok=True); self.steps = []; self.learning = None
            self.last_lease = 0.
            self.status.set_text('Live monitor: pedal actions are active in the kit.')

    def refresh_lease(self):
        now=time.monotonic()
        if now-self.last_lease<1:return
        atomic_write(self.lease, f'{int(time.time()) + 3} {os.getpid()}\n'.encode())
        self.last_lease=now

    def start_test(self, name):
        if self.busy: return
        self.test_mode.set_active(True)
        if not self.test_mode.get_active(): return
        self.passed = []; self.learning = None
        if name == 'SINCO':
            self.steps = [(('chocolate', i), f'Chocolate: press {letter}, then release.') for i, letter in enumerate('ABCD')]
        else:
            self.steps = [(('tsmega', 'previous'), 'Tone Shifter: press 1 once.'),
                          (('tsmega', 'next'), 'Tone Shifter: press 2 once.')]
            self.steps += [(('tsmega', i), f'Tone Shifter: select page {i // 4 + 1} with 3/4, then press {"ABCD"[i % 4]}.') for i in range(8)]
        self.instruction.set_text(self.steps[0][1]); self.log('Guided test started. No musical actions are sent by the kit adapter.')

    def learn(self, key):
        if self.busy: return
        self.test_mode.set_active(True)
        if not self.test_mode.get_active(): return
        self.steps = []; self.learning = key
        self.instruction.set_text('Press page 1 A on the Tone Shifter.' if key == 'effect_offset' else 'Press Tone Shifter ' + ('1.' if key == 'previous_cc' else '2.'))

    def save_tone(self, *_):
        if self.busy: return
        try:
            values = {key: spin.get_value_as_int() for key, spin in self.spins.items()}
            if self.profile_path.exists():
                atomic_write(STORE / f'tone-mapping-{time.time_ns()}.conf', self.profile_path.read_bytes())
            save_profile(self.profile_path, values); self.profile = values
            self.log('Tone Shifter software mappings saved; the running kit reloads within two seconds.')
        except (OSError, ValueError) as exc: self.log(str(exc))

    def restore(self, *_):
        if self.busy: return
        dialog = Gtk.FileChooserDialog(title='Restore Chocolate Custom CC backup', parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Restore', Gtk.ResponseType.OK)
        if STORE.exists(): dialog.set_current_folder(str(STORE))
        response = dialog.run(); path = dialog.get_filename(); dialog.destroy()
        if response == Gtk.ResponseType.OK and path:
            try: self.chocolate_operation('restore', restore_values(path))
            except (OSError, ValueError, KeyError) as exc: self.log('Backup rejected: ' + str(exc))

    def chocolate_operation(self, operation, values=None):
        if self.busy: return
        if operation != 'read':
            self.test_mode.set_active(True)
            if not self.test_mode.get_active(): return
        self.busy = True
        for button in self.operation_buttons: button.set_sensitive(False)
        self.log('Chocolate: ' + operation + '…')
        def worker():
            result = None; error = None
            try:
                matches = [d for d in devices() if d['name'] == 'SINCO']
                if len(matches) != 1: raise RuntimeError('Connect one standard USB Chocolate in U mode.')
                with Sequencer('TSMA Chocolate configuration') as transport:
                    device = Chocolate(transport, matches[0])
                    if operation == 'read':
                        blob, _ = device.read(); result = summary(blob)
                    else:
                        result, backup = device.program(STORE, values, lambda m: GLib.idle_add(self.log, m))
            except Exception as exc: error = str(exc)
            GLib.idle_add(self.operation_done, result, error)
        self.worker = threading.Thread(target=worker, daemon=True); self.worker.start()

    def operation_done(self, result, error):
        self.busy = False
        if self.closed: return False
        for button in self.operation_buttons: button.set_sensitive(True)
        if error: self.log('Operation stopped: ' + error)
        else:
            self.hardware = result
            fields = ', '.join(f'{letter}: CC{s["cc"]} {"latch" if s["latch"] else "momentary"}' for letter, s in result['switches'].items())
            good = result['mode'] == 7 and result['channel'] == 1 and all(s['cc'] == 80 + i and s['latch'] == 0 for i, s in enumerate(result['switches'].values()))
            self.choc_status.set_text(f'{"TSMA profile verified" if good else "Profile differs from TSMA"} · mode {result["mode"]}, channel {result["channel"]}\n{fields}')
            self.log('Hardware readback verified. Reconnect and test the switches to verify persistence and physical behavior.')
        return False

    def save_report(self, *_):
        try:
            path = STORE / f'report-{time.time_ns()}.json'
            atomic_write(path, (json.dumps({'time': time.time(), 'devices': devices(), 'tone_software_profile': self.profile,
                                           'chocolate_readback': self.hardware, 'passed_steps': self.passed,
                                           'observed_events': self.observed[-100:]}, indent=2) + '\n').encode())
            self.log('Report saved: ' + str(path))
        except OSError as exc: self.log(str(exc))

    def tick(self):
        if self.closed: return False
        try:
            now = time.monotonic()
            if self.test_mode.get_active(): self.refresh_lease()
            if self.seq is None: self.seq = Sequencer()
            if now - self.last_scan >= 2:
                self.last_scan = now; present = devices()
                self.seen = {(d['client'], d['port']): d['name'] for d in present}
                for device in present: self.seq.connect(device)
                names = {d['name'] for d in present}
                self.device_status.set_text('Tone Shifter: ' + ('connected' if 'TSMEGA' in names else 'not connected') +
                                            '    ·    Chocolate: ' + ('connected' if 'SINCO' in names else 'not connected'))
                if not self.test_mode.get_active(): self.status.set_text('Live monitor: pedal actions remain active in the kit.')
            for source, raw in self.seq.pending():
                name = self.seen.get(source)
                if name is None or not is_channel_message(raw): continue
                text, action = describe(name, raw, self.profile)
                self.log(name + ' · ' + text)
                self.observed.append({'device': name, 'raw': raw.hex(), 'description': text, 'time': time.time()})
                if len(self.observed) > 200: self.observed = self.observed[-100:]
                if self.learning and name == 'TSMEGA':
                    if self.learning == 'effect_offset' and raw[0] & 240 == 192:
                        self.spins[self.learning].set_value(raw[1]); self.learning = None
                    elif self.learning != 'effect_offset' and raw[0] & 240 == 176:
                        self.spins[self.learning].set_value(raw[1]); self.learning = None
                    if self.learning is None: self.instruction.set_text('Learned. Save Tone Shifter mappings to apply.')
                if self.steps and action == self.steps[0][0]:
                    self.passed.append(self.steps.pop(0)[1])
                    self.instruction.set_text(self.steps[0][1] if self.steps else 'All requested switches verified. Exit test mode to resume pedal actions.')
        except Exception as exc:
            self.status.set_text('MIDI diagnostics: ' + str(exc))
            if self.seq: self.seq.close(); self.seq = None
        return True

    def request_close(self, *_):
        if self.busy:
            self.log('Finish the current read/write transaction before closing.'); return True
        return False

    def cleanup(self, *_):
        self.closed = True
        self.lease.unlink(missing_ok=True)
        if self.seq: self.seq.close()
        self.instance_lock.close()


if __name__ == '__main__':
    window = PedalCheck(); window.connect('destroy', lambda *_: Gtk.main_quit()); Gtk.main()
