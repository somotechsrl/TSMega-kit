#!/usr/bin/python3
"""One native host window containing the two applications on a private X display."""
import fcntl,json,os,re,secrets,signal,subprocess,time
from pathlib import Path
# Xephyr's parent and the embedded windows require X11 window IDs. Select
# XWayland before GTK initializes, including when launched directly or by systemd.
os.environ['GDK_BACKEND']='x11'
import gi
gi.require_version('Gtk','3.0');gi.require_version('GdkX11','3.0')
from gi.repository import Gtk,Gdk,GdkX11,GLib,Pango
from window_layout import sizes,minimum_size,load_geometry,save_geometry,fit_geometry
from effect_bank import EffectBankMonitor
from effect_names import EffectNameReader
from midimix_panel import MidimixPanel
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'jack-hooks-{os.getuid()}'
STATE=RUNTIME/'tsma-gui.json'
WINDOW_SETTINGS=Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')/'tsmega-kit/window.json'

def call(args,env=None,check=False):
 return subprocess.run(args,env=env,check=check,capture_output=True,text=True,timeout=5)

def normal_tonelib_window(window,env):
 # JUCE also gives its progress dialogs the title N/A. Only embed the main
 # window: stretching a progress dialog hides the player while files load.
 return '_NET_WM_WINDOW_TYPE_NORMAL' in call(['xprop','-id',window,'_NET_WM_WINDOW_TYPE'],env=env).stdout

def monitor_area():
 display=Gdk.Display.get_default();screen=Gdk.Screen.get_default()
 monitor=None
 # On first conversion preserve the monitor where ToneLib was placed.
 pids=call(['pgrep','-x','ToneLib-GFX']).stdout.split()
 for line in call(['wmctrl','-lpG']).stdout.splitlines():
  fields=line.split(None,8)
  if len(fields)>=8 and fields[2] in pids:
   monitor=display.get_monitor_at_point(int(fields[3])+int(fields[5])//2,int(fields[4])+int(fields[6])//2);break
 if monitor is None:
  _,x,y=display.get_default_seat().get_pointer().get_position()
  monitor=display.get_monitor_at_point(x,y)
 if monitor is None:monitor=display.get_primary_monitor() or display.get_monitor(0)
 rect=monitor.get_workarea()
 return rect.x,rect.y,rect.width,rect.height

class Container:
 def __init__(self):
  self.server=self.wm=None;self.keyboard_focus=None;self.env=None;self.ready=False;self.closed=False;self.last=None;self.peer=None
  self.looper_window=None;self.looper_min=(848,187)
  self.log=(ROOT/'log/gui.log').open('a')
  x,y,w,h=monitor_area();width=min(1506,w-80);height=min(920,h-130)
  self.geometry={'x':x+(w-width)//2,'y':y+12,'width':width,'height':height}
  saved=load_geometry(WINDOW_SETTINGS)
  if saved is not None:
   display=Gdk.Display.get_default();areas=[]
   for i in range(display.get_n_monitors()):
    rect=display.get_monitor(i).get_workarea();areas.append((rect.x,rect.y,rect.width,rect.height))
   self.geometry=fit_geometry(saved,areas,(x,y,w,h))
  width=self.geometry['width'];height=self.geometry['height']
  self.window=Gtk.Window(title='TSMega-kit')
  self.window.get_style_context().add_class('tsma-shell')
  root_info=call(['xwininfo','-root']).stdout
  visual_id=int(re.search(r'Visual: (0x[0-9a-fA-F]+)',root_info)[1],16)
  visual=GdkX11.X11Screen.lookup_visual(Gdk.Screen.get_default(),visual_id)
  self.window.set_visual(visual)
  self.window.set_wmclass('tsmega-kit','TSMega-kit')
  self.window.set_icon_from_file(str(ROOT/'icona.svg'))
  self.window.set_default_size(width,height);self.window.set_size_request(848,600)
  header=Gtk.HeaderBar(title='TSMega-kit',show_close_button=True)
  self.window.set_titlebar(header)
  self.drums=Gtk.Button(label='Drums');self.drums.set_tooltip_text('Choose and play a drum backing track');self.drums.connect('clicked',self.choose_drums);header.pack_start(self.drums)
  self.drums_process=None
  check=Gtk.Button(label='Check');check.set_tooltip_text('Verify and configure the pedal controllers');check.connect('clicked',self.check_pedals);header.pack_start(check)
  self.bank_monitor=EffectBankMonitor(ROOT/'config/pedals.conf')
  self.effect_names=EffectNameReader(self.log);self.tone_window=None
  self.bank_display=Gtk.Button(label='Banco: — · Effetto: —');self.bank_display.set_margin_start(6)
  self.bank_display.set_focus_on_click(False);self.bank_display.get_child().set_width_chars(30)
  self.bank_display.get_child().set_max_width_chars(56);self.bank_display.get_child().set_ellipsize(Pango.EllipsizeMode.END)
  self.bank_display.get_style_context().add_class('tsma-bank')
  self.bank_display.connect('clicked',self.bank_details)
  header.pack_start(self.bank_display)
  self.bank_status=None;self.update_bank()
  self.check_window=None
  style=Gtk.CssProvider()
  style.load_from_data(b'headerbar {background:#202225;color:#f7f7f7;} headerbar .title, headerbar button {color:#f7f7f7;} headerbar button.tsma-bank {background:#30383b;font-weight:bold;} headerbar button.tsma-bank.effect-on {background:#21633e;} headerbar button.tsma-bank.effect-off {background:#44484b;color:#d0d0d0;} .tsma-lock {background:#272727;color:#c8c8c8;} window.tsma-shell decoration {border:3px solid #52606d; border-radius:8px;}')
  Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),style,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
  self.window.move(self.geometry['x'],self.geometry['y'])
  self.area=Gtk.DrawingArea();self.area.set_can_focus(True)
  self.area.set_visual(visual)
  overlay=Gtk.Overlay();overlay.add(self.area)
  body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
  self.midimix_panel=MidimixPanel();body.pack_start(self.midimix_panel,False,False,0)
  body.pack_start(overlay,True,True,0);self.window.add(body)
  self.lock=Gtk.EventBox();self.lock.set_visible_window(True)
  self.lock.set_above_child(True);self.lock.set_halign(Gtk.Align.START);self.lock.set_valign(Gtk.Align.START)
  self.lock.set_size_request(64,44);self.lock.set_margin_top(0)
  self.lock.get_style_context().add_class('tsma-lock')
  self.lock.add(Gtk.Image.new_from_icon_name('changes-prevent-symbolic',Gtk.IconSize.BUTTON))
  self.lock.set_tooltip_text('Preferenze bloccate per l’uso dal vivo')
  self.lock.connect('button-press-event',lambda *_:True)
  self.lock.connect('scroll-event',lambda *_:True)
  overlay.add_overlay(self.lock)
  self.window.connect('delete-event',self.close)
  self.window.connect('configure-event',self.remember_geometry)
  self.window.connect('destroy',lambda *_:Gtk.main_quit())
  self.window.show_all();self.area.grab_focus()
  GLib.idle_add(self.start)
  GLib.timeout_add(250,self.tick)
 def reload_midimix(self):
  # UI-only refresh: ToneLib, SooperLooper and the audio server keep running.
  import importlib,midimix_panel
  body=self.midimix_panel.get_parent()
  self.midimix_panel.close();body.remove(self.midimix_panel)
  self.midimix_panel=importlib.reload(midimix_panel).MidimixPanel()
  body.pack_start(self.midimix_panel,False,False,0);body.reorder_child(self.midimix_panel,0)
  self.midimix_panel.show_all()
  return False
 def update_bank(self):
  bank=self.bank_monitor.poll();effect=self.bank_monitor.effect
  name=self.effect_names.update(effect,self.bank_monitor.generation,self.tone_window,self.env)
  active=self.effect_names.active if name and effect is not None else None
  state='● Acceso' if active is True else '○ Spento' if active is False else ''
  status=(self.bank_monitor.connected,effect,name,active)
  if status==self.bank_status:return
  self.bank_status=status
  style=self.bank_display.get_style_context()
  for css,value in (('effect-on',True),('effect-off',False)):
   if active is value:style.add_class(css)
   else:style.remove_class(css)
  self.bank_display.set_label(((state+' · ' if state else '')+f'Banco: {bank*4+1}–{bank*4+4} · Effetto: {effect%4+1} → {effect+1}'+(' · '+name if name else '')+(' · non assegnato' if effect>=8 else '')) if bank is not None else 'Banco: — · Effetto: —')
  self.current_effect_name=name
  self.bank_display.set_tooltip_text(((name+'\n' if name else '')+(state+' — stato letto da ToneLib GFX.\n' if state else 'Stato acceso/spento non disponibile.\n')+'Ultimo effetto azionato: posizione nel banco → numero assoluto. Il banco lampeggiante sulla pedaliera si aggiorna qui dopo A–D.'+(' Oltre l’effetto 8, ToneLib non ha un controllo assegnato.' if effect>=8 else '')) if effect is not None else 'Premi A–D per rilevare il banco e l’effetto.' if self.bank_monitor.connected else 'Tone Shifter non collegata.')
 def bank_details(self,*_):
  self.bank_popover=Gtk.Popover.new(self.bank_display)
  label=Gtk.Label(label=('Ultimo effetto: '+self.current_effect_name+'\n\n' if self.current_effect_name else '')+'Banco confermato dall’ultimo A–D. Effetto: posizione 1–4 nel banco → numero assoluto.\n\nIl nome viene letto dal riepilogo nativo di ToneLib, quando la sua finestra è attiva nel display privato.\n\nIl prefisso lampeggiante sulla TS Mega è in attesa di conferma. ToneLib assegna i controlli MIDI ai primi 8 effetti; i successivi sono indicati come non assegnati.')
  label.set_line_wrap(True);label.set_max_width_chars(46)
  for side in ('top','bottom','start','end'):getattr(label,'set_margin_'+side)(12)
  self.bank_popover.add(label);self.bank_popover.show_all()
 def remember_geometry(self,*_):
  native=self.window.get_window()
  if native is None or native.get_state() & Gdk.WindowState.ICONIFIED:return False
  x,y=self.window.get_position();width,height=self.window.get_size()
  self.geometry.update(x=x,y=y,width=width,height=height)
  return False
 def check_pedals(self,*_):
  if self.check_window is not None:
   self.check_window.present();return
  try:
   from pedal_check import PedalCheck
   self.check_window=PedalCheck(self.window)
   self.check_window.connect('destroy',lambda *_:setattr(self,'check_window',None))
  except Exception as exc:
   notice=Gtk.MessageDialog(parent=self.window,message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.CLOSE,text=str(exc))
   notice.run();notice.destroy()
 def choose_drums(self,*_):
  dialog=Gtk.FileChooserDialog(title='Drum backing tracks',parent=self.window,action=Gtk.FileChooserAction.OPEN)
  dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Load & Play',Gtk.ResponseType.OK)
  library=ROOT/'BackingTracks/Drums';dialog.set_current_folder(str(library if library.is_dir() else Path.home()))
  audio=Gtk.FileFilter();audio.set_name('Audio backing tracks')
  for pattern in ('*.mp3','*.wav','*.flac','*.ogg'):audio.add_pattern(pattern)
  dialog.add_filter(audio);answer=dialog.run();file=dialog.get_filename();dialog.destroy()
  if answer!=Gtk.ResponseType.OK or not file:return
  pids=call(['pgrep','-x','ToneLib-GFX']).stdout.split()
  for row in call(['wmctrl','-lpG'],env=self.env).stdout.splitlines():
   fields=row.split(None,8)
   if len(fields)<9 or fields[2] not in pids or fields[8] not in ('ToneLib GFX','N/A'):continue
   if not normal_tonelib_window(fields[0],self.env):continue
   try:
    self.drums_process=subprocess.Popen([os.environ.get('TSMA_PYTHON','/usr/bin/python3'),str(ROOT/'bin/backing_track.py'),fields[0],file],env=self.env,stdout=self.log,stderr=subprocess.STDOUT)
   except OSError as exc:self.drums_error(str(exc));return
   self.drums.set_sensitive(False);self.drums.set_label('Loading…')
   GLib.child_watch_add(self.drums_process.pid,self.drums_loaded)
   return
  self.drums_error('ToneLib non è ancora disponibile.')
 def drums_error(self,message):
  notice=Gtk.MessageDialog(parent=self.window,message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.CLOSE,text='Caricamento drum')
  notice.format_secondary_text(message);notice.run();notice.destroy()
 def drums_loaded(self,pid,status):
  if self.drums_process is not None:self.drums_process.returncode=os.waitstatus_to_exitcode(status)
  self.drums_process=None
  if self.closed:return
  self.drums.set_sensitive(True);self.drums.set_label('Drums')
  if status:self.drums_error('Avvio automatico non riuscito. Controlla il player Backing track di ToneLib; i dettagli sono in log/gui.log.')
 def start(self):
  try:
   width=self.area.get_allocated_width();height=self.area.get_allocated_height()
   auth=RUNTIME/'tsma-gui.auth'
   auth.touch(mode=0o600,exist_ok=True);auth.chmod(0o600)
   for number in range(90,100):
    if Path(f'/tmp/.X11-unix/X{number}').exists() or Path(f'/tmp/.X{number}-lock').exists():continue
    self.display=f':{number}'
    call(['xauth','-f',str(auth),'add',self.display,'.',secrets.token_hex(16)],check=True)
    xid=self.area.get_window().get_xid()
    self.server=subprocess.Popen(['Xephyr',self.display,'-parent',str(xid),'-screen',f'{width}x{height}','-resizeable','-no-host-grab','-nolisten','tcp','-auth',str(auth),'-noreset','-title','TSMega-kit'],stdout=self.log,stderr=subprocess.STDOUT)
    self.env=os.environ.copy();self.env.update(DISPLAY=self.display,XAUTHORITY=str(auth),GDK_BACKEND='x11')
    deadline=time.monotonic()+4
    while time.monotonic()<deadline and self.server.poll() is None:
     if call(['xprop','-root'],env=self.env).returncode==0:break
     time.sleep(.1)
    else:
     if self.server.poll() is None:self.server.terminate();self.server.wait(timeout=3)
     continue
    self.wm=subprocess.Popen(['openbox','--sm-disable','--config-file',str(ROOT/'config/openbox.xml')],env=self.env,stdout=self.log,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
     if call(['wmctrl','-m'],env=self.env).returncode==0:break
     if self.wm.poll() is not None:raise RuntimeError('Openbox non è partito')
     time.sleep(.1)
    else:raise RuntimeError('Gestore delle finestre non pronto')
    children=call(['xwininfo','-id',str(xid),'-children']).stdout
    peer=re.search(r'(?m)^\s+(0x[0-9a-fA-F]+) "TSMega-kit":',children)
    if peer:
     peer_id=int(peer[1],16)
     self.peer=GdkX11.X11Window.foreign_new_for_display(Gdk.Display.get_default(),peer_id)
     self.keyboard_focus=subprocess.Popen([os.environ.get('TSMA_PYTHON','/usr/bin/python3'),str(ROOT/'bin/keyboard_focus.py'),str(self.window.get_window().get_xid()),str(peer_id),str(os.getpid()),self.env['DISPLAY'],self.env['XAUTHORITY']],stdout=self.log,stderr=subprocess.STDOUT)
    self.ready=True
    STATE.write_text(json.dumps({'ready':True,'display':self.display,'xauthority':str(auth),'pid':os.getpid()}))
    return False
   raise RuntimeError('Display grafico privato non disponibile')
  except Exception as exc:
   print('Contenitore:',exc,flush=True);self.window.destroy();return False
 def tick(self):
  if self.closed:return False
  self.update_bank()
  if self.ready:
   if self.server.poll() is not None or self.wm.poll() is not None:
    self.close();self.window.destroy();return False
   width=self.area.get_allocated_width();height=self.area.get_allocated_height()
   if self.last!=(width,height):
    if self.peer:self.peer.move_resize(0,0,width,height)
    self.lock.set_margin_top(sizes(width,height)[1][1]);self.last=(width,height)
   rows=call(['wmctrl','-lpG'],env=self.env).stdout.splitlines()
   pids=call(['pgrep','-x','ToneLib-GFX']).stdout.split()
   self.tone_window=None
   for row in rows:
    fields=row.split(None,8)
    if len(fields)<9:continue
    title=fields[8];geom=None
    if title.startswith('SooperLooper v '):
     hints=call(['xprop','-id',fields[0],'WM_NORMAL_HINTS'],env=self.env).stdout
     reported_min=minimum_size(hints)
     if self.looper_window!=fields[0] or reported_min!=self.looper_min:
      new_window=self.looper_window!=fields[0]
      self.looper_min=reported_min;self.looper_window=fields[0]
      self.window.set_size_request(max(848,self.looper_min[0]),max(600,self.looper_min[1]+300))
      # Older wxGTK builds use WM_CLASS Slgui instead of SooperLooper.
      # This explicit hint also protects against a changed upstream class name.
      if new_window:call(['xprop','-id',fields[0],'-f','_MOTIF_WM_HINTS','32c','-set','_MOTIF_WM_HINTS','2, 0, 0, 0, 0'],env=self.env)
     geom=sizes(width,height,self.looper_min[1])[0]
    elif fields[2] in pids and title in ('ToneLib GFX','N/A') and normal_tonelib_window(fields[0],self.env):
     geom=sizes(width,height,self.looper_min[1])[1];self.tone_window=int(fields[0],16)
    if geom is None:continue
    actual=tuple(map(int,(fields[3],fields[4],fields[5],fields[6])))
    if actual!=geom:
     call(['wmctrl','-ir',fields[0],'-b','remove,maximized_vert,maximized_horz'],env=self.env)
     call(['wmctrl','-ir',fields[0],'-e','0,'+','.join(map(str,geom))],env=self.env)
  return True
 def close(self,*_):
  if self.closed:return False
  if self.check_window is not None and self.check_window.busy:
   self.check_window.present();self.check_window.log('Finish the pedal configuration transaction before closing the kit.');return True
  if self.check_window is not None:self.check_window.destroy()
  self.remember_geometry()
  self.midimix_panel.close()
  self.bank_monitor.close()
  self.effect_names.close()
  try:save_geometry(WINDOW_SETTINGS,self.geometry)
  except OSError as exc:print('Salvataggio finestra:',exc,file=self.log,flush=True)
  self.closed=True;STATE.unlink(missing_ok=True)
  if self.keyboard_focus is not None and self.keyboard_focus.poll() is None:
   self.keyboard_focus.terminate();self.keyboard_focus.wait(timeout=3)
  if self.drums_process is not None:self.drums_process.terminate()
  if self.ready:
   # Close gracefully while X is still alive so application settings can save.
   subprocess.run(['systemctl','--user','stop','tsma-tonelib.service','tsma-looper-gui.service','tsmega-kit.service'],timeout=20)
   subprocess.run(['systemctl','--user','stop','jack-tsmega.service','tsma-jack-drivers.service'],timeout=15,stderr=subprocess.DEVNULL)
  for child in (self.wm,self.server):
   if child is not None and child.poll() is None:
    child.terminate()
    try:child.wait(timeout=3)
    except subprocess.TimeoutExpired:child.kill();child.wait()
  self.log.close();return False

if __name__=='__main__':
 RUNTIME.mkdir(mode=0o700,parents=True,exist_ok=True)
 with open(RUNTIME/'tsma-gui.lock','w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit(0)
  container=Container()
  def stop(*_):GLib.idle_add(lambda:(container.close(),container.window.destroy(),False)[-1])
  signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
  signal.signal(signal.SIGUSR1,lambda *_:GLib.idle_add(container.reload_midimix))
  try:Gtk.main()
  finally:container.close()
