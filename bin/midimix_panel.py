"""Compact live fader legend embedded in TSMega-kit."""
import json
import os
from pathlib import Path
import subprocess
import sys
from gi.repository import Gtk, GLib, Pango, Gdk


def meter_fraction(db):
    return 0.0 if db is None else max(0.0, min(1.0, (db + 60) / 66))


def db_text(db):
    return '—' if db is None else '−∞ dB' if db < -120 else f'{db:.1f} dB'


def place_unity_mark(overlay, child, allocation, mark):
    if child is not mark:
        return False
    width = overlay.get_allocated_width()
    height = overlay.get_allocated_height()
    allocation.x = max(0, round((width-2)*meter_fraction(0)))
    allocation.y = max(0, height-14)
    allocation.width = min(2, max(1, width))
    allocation.height = min(14, max(1, height))
    return True


class MidimixPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.set_margin_start(6); self.set_margin_end(6)
        self.set_margin_top(3); self.set_margin_bottom(3)
        self.status = Gtk.Label(label='Ardour Midimix · collegamento ad Ardour…', xalign=0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.set_tooltip_text('Collegamento automatico ad Ardour. Bank Left/Right sul MIDImix aggiornano le otto corrispondenze.\nLe altre assegnazioni MIDI passano inalterate ad Ardour. Il collegamento originale viene ripristinato quando chiudi TSMega-kit.\nSe Ardour era già aperto alla prima installazione, la configurazione si applica automaticamente dopo la sua chiusura, senza riavviarlo durante il lavoro.')
        heading = Gtk.Box(spacing=4)
        heading.pack_start(self.status, True, True, 0)
        for title, delta in (('‹', -1), ('›', 1)):
            button = Gtk.Button(label=title); button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_tooltip_text('Banco precedente' if delta < 0 else 'Banco successivo')
            button.connect('clicked', lambda _, step=delta: self.change_bank(step))
            heading.pack_start(button, False, False, 0)
        self.pack_start(heading, False, False, 0)
        row = Gtk.Box(spacing=4, homogeneous=True)
        self.labels = []; self.boxes = []; self.volumes = []; self.vus = []; self.mutes = []
        style = Gtk.CssProvider()
        style.load_from_data(b"""
        .tsma-mute {font-size:9px; padding:2px 3px; border-radius:3px; background:#343a40; color:#828990;}
        .tsma-mute.active {background:#b33939; color:#fff; font-weight:bold;}
        .tsma-meter {font-size:10px; color:#fff; text-shadow:0 1px #111;}
        .tsma-meter trough {min-height:14px; background:#20272b; border:0; border-radius:2px;}
        .tsma-meter progress {min-height:14px; border:0; border-radius:2px;}
        .tsma-volume progress {background:#326b98;}
        .tsma-volume.unity progress {background:#428fa1;}
        .tsma-unity-mark {background:#f4ead2; min-width:2px;}
        .tsma-vu progress {background:linear-gradient(to right,#207943,#43b964);}
        .tsma-vu.warn progress {background:#c29528;}
        .tsma-vu.clip progress {background:#d64a43;}
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for number in range(1, 9):
            box = Gtk.Frame(); label = Gtk.Label(label=f'{number} · —')
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(18); label.set_margin_top(5); label.set_margin_bottom(5)
            label.set_margin_start(4); label.set_margin_end(4)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            content.set_margin_start(3); content.set_margin_end(3); content.set_margin_bottom(4)
            title = Gtk.Box(spacing=2)
            title.pack_start(label, True, True, 0)
            mute = Gtk.Label(label='MUTE'); mute.get_style_context().add_class('tsma-mute')
            title.pack_start(mute, False, False, 0); self.mutes.append(mute)
            content.pack_start(title, False, False, 0)
            for kind, collection in (('volume', self.volumes), ('vu', self.vus)):
                bar = Gtk.ProgressBar(show_text=True)
                bar.set_text(('Vol ' if kind == 'volume' else 'VU ')+'—')
                bar.get_style_context().add_class('tsma-meter')
                bar.get_style_context().add_class('tsma-'+kind)
                if kind == 'volume':
                    overlay = Gtk.Overlay(); overlay.add(bar)
                    mark = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                    mark.get_style_context().add_class('tsma-unity-mark')
                    mark.set_halign(Gtk.Align.START); mark.set_valign(Gtk.Align.END)
                    mark.set_size_request(2, 14)
                    overlay.add_overlay(mark); overlay.set_overlay_pass_through(mark, True)
                    overlay.connect('get-child-position', place_unity_mark, mark)
                    overlay.set_tooltip_text('Tacca 0 dB · aggancio magnetico del fader MIDImix')
                    content.pack_start(overlay, False, False, 0)
                else:
                    content.pack_start(bar, False, False, 0)
                collection.append(bar)
            box.add(content); row.pack_start(box, True, True, 0)
            self.labels.append(label); self.boxes.append(box)
        self.pack_start(row, False, False, 0)
        self.buffer = b''; self.closed = False
        self.worker = subprocess.Popen([sys.executable, str(Path(__file__).with_name('midimix.py'))],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        os.set_blocking(self.worker.stdout.fileno(), False)
        self.timer = GLib.timeout_add(40, self.poll)

    def change_bank(self, delta):
        if self.closed:
            return
        try:
            self.worker.stdin.write((json.dumps({'bank_delta': delta})+'\n').encode())
            self.worker.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def update(self, state):
        self.status.set_text(state['status'])
        names = state.get('names', [])
        for i, label in enumerate(self.labels):
            name = names[i] if i < len(names) else '—'
            text = f'{i+1} · {name}'
            if i == state.get('fader'):
                label.set_markup('<b>'+GLib.markup_escape_text(text)+'</b>')
            else:
                label.set_text(text)
            label.set_tooltip_text(f'Fader MIDImix {i+1} → {name}')
            values = state.get('mutes', [])
            muted = values[i] if i < len(values) and name != '—' else None
            context = self.mutes[i].get_style_context()
            if muted is True: context.add_class('active')
            else: context.remove_class('active')
            self.mutes[i].set_tooltip_text('Mute attivo' if muted is True else 'Mute disattivato' if muted is False else 'Mute non disponibile')
            for key, bar, prefix in (('gains', self.volumes[i], 'Vol'), ('meters', self.vus[i], 'VU')):
                values = state.get(key, [])
                db = values[i] if i < len(values) else None
                if name == '—': db = None
                bar.set_fraction(meter_fraction(db))
                bar.set_text(prefix+' '+db_text(db))
                bar.set_tooltip_text(('Volume del fader' if key == 'gains' else 'Picco audio letto da Ardour')+' · '+name+' · '+db_text(db))
                if key == 'gains':
                    context = bar.get_style_context()
                    if db is not None and abs(db) < .05: context.add_class('unity')
                    else: context.remove_class('unity')
                if key == 'meters':
                    context = bar.get_style_context()
                    for css, active in (('warn', db is not None and -6 <= db < 0), ('clip', db is not None and db >= 0)):
                        if active: context.add_class(css)
                        else: context.remove_class(css)

    def poll(self):
        if self.closed:
            return False
        try:
            while True:
                data = os.read(self.worker.stdout.fileno(), 65536)
                if not data:
                    self.update({'status':'Ardour Midimix · ponte fermo; riapri TSMega-kit per riconnettere','names':['—']*8})
                    return False
                self.buffer += data
                while b'\n' in self.buffer:
                    line, self.buffer = self.buffer.split(b'\n', 1)
                    self.update(json.loads(line))
        except BlockingIOError:
            pass
        return True

    def close(self):
        if self.closed:
            return
        self.closed = True
        GLib.source_remove(self.timer)
        # EOF releases the routing lease. Also works if the host process dies.
        self.worker.stdin.close()
        try:
            self.worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.worker.terminate()
        self.worker.stdout.close()
