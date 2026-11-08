#!/usr/bin/env python3
"""Writable user data and first-run setup for the bundled application."""
import argparse,fcntl,json,os,shutil,subprocess,sys,tarfile,tempfile,threading,time,urllib.request
from pathlib import Path
BUNDLE=Path(os.environ['TSMA_BUNDLE_ROOT']);BASE=BUNDLE/'usr/share/tsmega-kit'
PAYLOAD=BASE/'kit';VERSION=(BASE/'VERSION').read_text().strip();HOME=Path.home()
DATA=Path(os.environ.get('XDG_DATA_HOME',HOME/'.local/share'))/'tsmega-kit'
KIT=Path(os.environ.get('TSMA_KIT_HOME',DATA/'kit')).expanduser()
RUNTIME=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'jack-hooks-{os.getuid()}'
def run(*args,**kw):return subprocess.run(args,check=True,**kw)
def active_gui():
 try:
  data=json.loads((RUNTIME/'tsma-gui.json').read_text());return data.get('ready') and Path(f'/proc/{data["pid"]}').exists()
 except (OSError,ValueError,KeyError):return False
def desktop_icon():
 try:desktop=Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
 except (OSError,subprocess.CalledProcessError):desktop=HOME/'Desktop'
 DATA.mkdir(parents=True,exist_ok=True);desktop.mkdir(parents=True,exist_ok=True)
 executable=Path('/usr/bin/tsmega-kit')
 if not executable.exists():executable=Path(os.environ['APPIMAGE']).resolve()
 quote=lambda p:'"'+str(p).replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('`','\\`').replace('%','%%')+'"'
 icon=DATA/'tsmega-kit.svg';shutil.copy2(PAYLOAD/'icona.svg',icon)
 text=f'[Desktop Entry]\nType=Application\nName=TSMega-kit\nComment=Guitar effects and live looping\nExec={quote(executable)}\nIcon={icon}\nTerminal=false\nCategories=AudioVideo;Audio;\nStartupWMClass=TSMega-kit\n'
 target=desktop/'TSMega-kit.desktop';target.write_text(text);target.chmod(0o755)
 applications=Path(os.environ.get('XDG_DATA_HOME',HOME/'.local/share'))/'applications';applications.mkdir(parents=True,exist_ok=True);(applications/'tsmega-kit.desktop').write_text(text)
 if shutil.which('gio'):subprocess.run(['gio','set',str(target),'metadata::trusted','true'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 return target
def sync_payload():
 KIT.mkdir(parents=True,exist_ok=True)
 for src in PAYLOAD.rglob('*'):
  rel=src.relative_to(PAYLOAD)
  if not src.is_file() or '__pycache__' in rel.parts or rel.parts[0] in ('state','log'):continue
  dest=KIT/rel
  preserve=rel.parts[:2]==('config','Gadwin') or str(rel) in ('config/kit.json','config/portable-drivers.conf','config/pedals.conf')
  if preserve and dest.exists():continue
  dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists() or src.read_bytes()!=dest.read_bytes():shutil.copy2(src,dest)
 for name in ('state','log','vendor'):(KIT/name).mkdir(exist_ok=True)
 (KIT/'.package-version').write_text(VERSION+'\n')
def extract_official(package,dest):
 if package.read(8)!=b'!<arch>\n':raise RuntimeError('Invalid official Debian archive.')
 while True:
  header=package.read(60)
  if len(header)!=60:raise RuntimeError('ToneLib executable not found in download.')
  name=header[:16].decode().strip().rstrip('/');size=int(header[48:58])
  if not name.startswith('data.tar'):package.seek(size+size%2,1);continue
  with tempfile.TemporaryFile() as data:
   remaining=size
   while remaining:
    block=package.read(min(1024*1024,remaining))
    if not block:raise RuntimeError('Incomplete download.')
    data.write(block);remaining-=len(block)
   data.seek(0);process=None
   if name.endswith('.zst'):
    process=subprocess.Popen(['zstd','-dc'],stdin=data,stdout=subprocess.PIPE);archive=tarfile.open(fileobj=process.stdout,mode='r|')
   else:archive=tarfile.open(fileobj=data,mode='r:*')
   try:
    with archive:
     for member in archive:
      if member.name.lstrip('./')=='usr/bin/ToneLib-GFX' and member.isfile():
       temporary=dest.with_suffix('.download')
       with archive.extractfile(member) as stream,temporary.open('wb') as output:shutil.copyfileobj(stream,output)
       temporary.chmod(0o755);temporary.replace(dest);return
     raise RuntimeError('ToneLib executable missing from official archive.')
   finally:
    if process:process.stdout.close();process.terminate();process.wait()
def ensure_tonelib():
 dest=KIT/'vendor/ToneLib-GFX'
 if dest.exists():return
 installed=shutil.which('ToneLib-GFX')
 if installed:shutil.copy2(installed,dest);return
 import gi
 gi.require_version('Gtk','3.0')
 from gi.repository import Gtk
 dialog=Gtk.MessageDialog(message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,text='Download ToneLib GFX?')
 dialog.format_secondary_text('Download the official Linux trial from tonelib.net. No author license or registration is included. Each user can later activate ToneLib with their own license.')
 dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Download official trial',Gtk.ResponseType.OK)
 answer=dialog.run();dialog.destroy()
 if answer!=Gtk.ResponseType.OK:raise RuntimeError('ToneLib download cancelled.')
 progress=Gtk.Window(title='TSMega-kit');label=Gtk.Label(label='Downloading ToneLib GFX from tonelib.net…');label.set_margin_top(24);label.set_margin_bottom(24);label.set_margin_start(24);label.set_margin_end(24);progress.add(label);progress.show_all();result=[]
 def worker():
  try:
   with urllib.request.urlopen('https://tonelib.net/download.php?id=gfx&os=lnx',timeout=60) as response,tempfile.TemporaryFile() as package:
    from urllib.parse import urlparse
    if urlparse(response.url).hostname not in ('tonelib.net','www.tonelib.net'):raise RuntimeError('Unexpected official download host.')
    shutil.copyfileobj(response,package);package.seek(0);extract_official(package,dest)
   result.append(None)
  except Exception as exc:result.append(exc)
 thread=threading.Thread(target=worker,daemon=True);thread.start()
 while thread.is_alive():
  while Gtk.events_pending():Gtk.main_iteration_do(False)
  time.sleep(.03)
 progress.destroy()
 if result[0]:raise result[0]
def ensure_jack_bus():
 import dbus
 bus=dbus.SessionBus()
 if bus.name_has_owner('org.jackaudio.service'):return
 process=subprocess.Popen(['jackdbus','auto'],stdout=(KIT/'log/jackdbus.log').open('a'),stderr=subprocess.STDOUT,start_new_session=True)
 until=time.monotonic()+8
 while time.monotonic()<until:
  if bus.name_has_owner('org.jackaudio.service'):return
  if process.poll() is not None:break
  time.sleep(.1)
 raise RuntimeError('JACK D-Bus server did not start; see log/jackdbus.log.')
def self_test():
 import ctypes,gi,dbus
 gi.require_version('Gtk','3.0');gi.require_version('GdkX11','3.0')
 from gi.repository import Gtk,GdkX11
 for name in ('libjack.so.0','libasound.so.2','libgtk-3.so.0','libXtst.so.6'):ctypes.CDLL(name)
 for name in ('sooperlooper','slgui','jackdbus','jack_control','jack_lsp','jack_samplerate','zita-a2j','zita-j2a','Xephyr','openbox','xauth','xprop','xwininfo','xrandr','wmctrl','ffmpeg'):
  if not shutil.which(name):raise RuntimeError('Missing bundled tool: '+name)
 run(str(PAYLOAD/'config/Jack/Drivers.d/tsmega-midi'),'--self-test');ctypes.CDLL(str(PAYLOAD/'vendor/slgui-lock.so'))
 sys.path.insert(0,str(PAYLOAD/'bin'))
 from pedals import load_profile,DEFAULT,write_message
 from alsa_midi import Sequencer
 if load_profile(PAYLOAD/'config/pedals.conf')!=DEFAULT:raise RuntimeError('Invalid bundled pedal profile.')
 write_message(0,7)
 print('TSMega-kit',VERSION,'bundle checks passed; no audio device was opened.')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--install-desktop',action='store_true');parser.add_argument('--stop',action='store_true');parser.add_argument('--save-loop',action='store_true');parser.add_argument('--import-drums',metavar='SOURCE');parser.add_argument('--check',action='store_true',help='Open pedal verification and programming without starting the audio kit');args=parser.parse_args()
 if args.self_test:self_test();return
 if os.geteuid()==0:raise RuntimeError('Start TSMega-kit as your desktop user, not root.')
 DATA.mkdir(parents=True,exist_ok=True)
 if args.install_desktop:print(desktop_icon());return
 if args.stop:run(str(KIT/'stop-tsmega'));return
 if args.save_loop:run(str(KIT/'save-loop'));return
 if args.check:
  sync_payload();run(os.environ['TSMA_PYTHON'],str(KIT/'bin/pedal_check.py'));return
 if args.import_drums:
  sync_payload();run(os.environ['TSMA_PYTHON'],str(KIT/'bin/import_drums.py'),args.import_drums,str(KIT/'BackingTracks/Drums'));return
 if active_gui():return
 with (DATA/'prepare.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if active_gui():return
  sync_payload();ensure_tonelib();desktop_icon();ensure_jack_bus();run(str(KIT/'start-tsmega'))
 # Systemd GUI children must retain access to an AppImage's mounted libraries.
 while active_gui():time.sleep(.5)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  print(str(exc),file=sys.stderr)
  if os.environ.get('DISPLAY') and shutil.which('notify-send'):subprocess.run(['notify-send','-u','critical','TSMega-kit',str(exc)])
  raise SystemExit(1)
