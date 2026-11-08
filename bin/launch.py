#!/usr/bin/python3
"""Start the independent guitar kit; connect to the DAW only if present."""
import fcntl,json,os,shutil,subprocess,sys,time
from pathlib import Path
from profile import install_profile,bind_midi,fresh_qjackctl,configure_backing_library
PYTHON=os.environ.get('TSMA_PYTHON','/usr/bin/python3')
ROOT=Path(__file__).resolve().parents[1];HOME=Path.home();CONFIG=json.loads((ROOT/'config/kit.json').read_text())
RUNTIME=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'jack-hooks-{os.getuid()}'

def run(*args,check=True,timeout=8):
 return subprocess.run(args,check=check,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
def process(name):return run('pgrep','-x',name,check=False).returncode==0
def unit(name,args):
 if run('systemctl','--user','is-active','--quiet',name+'.service',check=False).returncode==0:return
 keys=['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS']
 if os.environ.get('TSMA_BUNDLE_ROOT'):
  keys+=['PATH','LD_LIBRARY_PATH','PYTHONHOME','PYTHONPATH','GI_TYPELIB_PATH','GIO_MODULE_DIR','GTK_PATH','GTK_EXE_PREFIX','XDG_DATA_DIRS','GSETTINGS_SCHEMA_DIR','JACK_DRIVER_DIR','SSL_CERT_FILE','TSMA_BUNDLE_ROOT','TSMA_PYTHON','GDK_PIXBUF_MODULEDIR','GDK_PIXBUF_MODULE_FILE']
 display=[f'--setenv={key}={os.environ[key]}' for key in keys if key in os.environ]
 run('systemd-run','--user','--collect','--unit='+name,'--working-directory='+str(ROOT),*display,*args)
def wait_for(predicate,seconds,message):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  if predicate():return
  time.sleep(.2)
 raise RuntimeError(message)
def jack_ready():return run('jack_control','status',check=False).returncode==0

def on_display(name,display):
 for pid in run('pgrep','-x',name,check=False).stdout.split():
  try:
   if ('DISPLAY='+display).encode() in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):return True
  except OSError:pass
 return False

def main():
 required=['jack_control','sooperlooper','slgui','systemd-run','jack_lsp','jack_samplerate','zita-a2j','zita-j2a','Xephyr','openbox','xauth','xprop','wmctrl']
 missing=[x for x in required if not shutil.which(x)]
 if missing:raise RuntimeError('Esegui prima install-tsmega. Programmi mancanti: '+', '.join(missing))
 if 'SonicMaster_Looper:common_out_1' in run('jack_lsp',check=False).stdout:
  raise RuntimeError('Chiudi SonicMaster-kit prima di avviare TSMega-kit: condividono Chocolate e la traccia TSMA-Kit.')
 # Prepare optional Ardour integration only while the DAW is closed.
 from midimix_setup import prepare
 prepare(Path(os.environ.get('XDG_CONFIG_HOME') or HOME/'.config')/'ardour8')
 # Initial configurations are a recovery copy, never overwrite live presets.
 install_profile(ROOT,HOME)
 fresh_qjackctl(HOME)
 # Reuse a central driver manager if it is alive, otherwise use only this kit.
 jackdir=ROOT/'config/Jack';portable=True
 owner_file=RUNTIME/'drivers.pid'
 def driver_live():
  try:
   pid=int(owner_file.read_text());parts=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
   return any(Path(os.fsdecode(part)).name=='Drivers' for part in parts if part)
  except (OSError,ValueError):return False
 if driver_live():
  parts=Path(f'/proc/{int(owner_file.read_text())}/cmdline').read_bytes().split(b'\0')
  jackdir=next(Path(os.fsdecode(part)).parent for part in parts if part and Path(os.fsdecode(part)).name=='Drivers')
  portable=jackdir.resolve()==(ROOT/'config/Jack').resolve()
 # Build only when needed; the included binary also works without a build step.
 source=jackdir/'Drivers.d/tsmega-midi.c';binary=source.with_suffix('')
 if not binary.exists() or source.stat().st_mtime>binary.stat().st_mtime:
  run('cc','-Wall','-Wextra','-O2',str(source),'-Wl,-l:libasound.so.2','-o',str(binary),timeout=30)
 if not jack_ready():
  # Never invoke QjackCtl startup hooks: they can launch unrelated applications.
  # Restart only our own stale bridge manager after an external JACK shutdown.
  if portable:
   run('systemctl','--user','stop','tsma-jack-drivers.service',check=False)
  # An already-open QjackCtl observes DBus startup and fires its own hooks.
  # Its local hook consumes this one-shot request instead of opening Ardour.
  (RUNTIME/'tsma-jack-only').write_text(str(int(time.time())+120)+'\n')
  run('jack_control','ds','dummy','dps','rate',str(CONFIG['sample_rate']),'dps','period',str(CONFIG['buffer_size']),'dps','wait',str(round(1e6*CONFIG['buffer_size']/CONFIG['sample_rate'])),'start',timeout=20)
  wait_for(jack_ready,20,'JACK non è partito: consulta log/avvio.log.')
 rate=run('jack_samplerate').stdout.strip().splitlines()[-1]
 if int(rate)!=CONFIG['sample_rate']:raise RuntimeError(f'Il kit richiede {CONFIG["sample_rate"]} Hz; JACK è a {rate} Hz. Regola QjackCtl.')
 driver_env=['--setenv=JACK_DRIVERS_CONFIG='+str(ROOT/'config/portable-drivers.conf')] if portable else []
 if not driver_live():unit('tsma-jack-drivers',driver_env+[str(jackdir/'Drivers')]);wait_for(driver_live,8,'Gestore driver JACK non disponibile.')
 # A former bridge may have exited while the other audio devices stayed alive.
 pidfile=RUNTIME/'tsmega.pid'
 def ts_live():
  try:return (Path('/proc')/pidfile.read_text().strip()/'cmdline').is_file()
  except OSError:return False
 if not ts_live():
  owner=owner_file.read_text().strip()
  unit('jack-tsmega',driver_env+['--setenv=JACK_DRIVERS_OWNER_PID='+owner,str(jackdir/'Drivers.d/TSMEGA')])
 unit('tsmega-kit',['--property=Restart=on-failure','--property=RestartSec=2',PYTHON,str(ROOT/'bin/service.py')])
 def looper_ready():
  try:return json.loads((RUNTIME/'tsmega-kit.status.json').read_text()).get('ready',False)
  except (OSError,ValueError):return False
 wait_for(looper_ready,15,'SooperLooper non è pronto: controlla log/engine.log.')
 unit('tsma-gui',[PYTHON,str(ROOT/'bin/gui.py')])
 gui={}
 def gui_ready():
  try:
   gui.update(json.loads((RUNTIME/'tsma-gui.json').read_text()))
   return gui.get('ready',False) and Path(f'/proc/{gui["pid"]}').exists()
  except (OSError,ValueError,KeyError):return False
 wait_for(gui_ready,15,'Contenitore grafico non pronto: consulta log/gui.log.')
 gui_env=['--setenv=DISPLAY='+gui['display'],'--setenv=XAUTHORITY='+gui['xauthority'],'--setenv=GDK_BACKEND=x11']
 if process('ToneLib-GFX') and not on_display('ToneLib-GFX',gui['display']):
  run('systemctl','--user','stop','tsma-tonelib.service')
  wait_for(lambda:not process('ToneLib-GFX'),8,'Chiudi la vecchia finestra ToneLib per aprirla nel contenitore.')
 if not process('ToneLib-GFX'):
  configure_backing_library(HOME,ROOT/'BackingTracks/Drums')
  wait_for(lambda:bind_midi(HOME),8,'Adattatore MIDI non pronto.')
  tonelib=ROOT/'vendor/ToneLib-GFX'
  if not tonelib.exists():tonelib=Path(shutil.which('ToneLib-GFX') or '/nonexistent')
  if not tonelib.exists():raise RuntimeError('ToneLib GFX assente: esegui install-tsmega.')
  unit('tsma-tonelib',gui_env+[str(tonelib)])
 wait_for(lambda:process('ToneLib-GFX'),8,'ToneLib non è partito.')
 # Connect the UI to the dedicated engine; never let it spawn another one.
 if process('slgui') and not on_display('slgui',gui['display']):run('systemctl','--user','stop','tsma-looper-gui.service',check=False)
 if not on_display('slgui',gui['display']):unit('tsma-looper-gui',gui_env+['--setenv=GTK_MODULES='+str(ROOT/'vendor/slgui-lock.so'),shutil.which('slgui'),'-N','-n','-H','127.0.0.1','-P',str(CONFIG['osc_port']),'-X','0:0'])
 print('Kit avviato: ToneLib → SooperLooper → Tone Shifter; traccia TSMA-Kit se presente.')
 run('notify-send','--app-name=TSMega-kit','--icon='+str(ROOT/'icona.svg'),'TSMega-kit','ToneLib e SooperLooper pronti. La traccia TSMA-Kit si ricollega automaticamente.',check=False)

if __name__=='__main__':
 (ROOT/'log').mkdir(exist_ok=True);RUNTIME.mkdir(mode=0o700,parents=True,exist_ok=True)
 with open(RUNTIME/'tsma-launch.lock','w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit(0)
  try:main()
  except Exception as exc:
   print(str(exc),file=sys.stderr)
   subprocess.run(['notify-send','-u','critical','TSMega-kit',str(exc)])
   raise SystemExit(1)
