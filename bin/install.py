#!/usr/bin/python3
"""One-time installation on a new Linux desktop; never run the launcher as root."""
import argparse,os,platform,shutil,subprocess,sys
from pathlib import Path
from profile import install_profile,fresh_qjackctl
ROOT=Path(__file__).resolve().parents[1]

def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def desktop_entry(root):
 def quote(s):return '"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
 return f'''[Desktop Entry]
Type=Application
Name=TSMega-kit
Comment=Chitarra · ToneLib GFX · SooperLooper
Exec={quote(root/'start-tsmega')}
Icon={root/'icona.svg'}
Terminal=false
Categories=AudioVideo;Audio;
StartupWMClass=TSMega-kit
Actions=SalvaLoop;

[Desktop Action SalvaLoop]
Name=Salva il loop
Exec={quote(root/'save-loop')}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--dry-run',action='store_true',help='Mostra le operazioni, senza modifiche')
 parser.add_argument('--no-deps',action='store_true',help='Dipendenze già installate manualmente')
 parser.add_argument('--keep-profile',action='store_true',help='Conserva un profilo ToneLib già esistente')
 args=parser.parse_args()
 if os.geteuid()==0:raise RuntimeError('Esegui come utente normale: lo script richiede sudo solo per i pacchetti.')
 if platform.machine() not in ('x86_64','amd64'):raise RuntimeError('ToneLib incluso richiede Linux x86_64; questo kit non supporta ARM.')
 print('Cartella:',ROOT)
 print('Profilo: preset ToneLib, comandi TS Mega/Chocolate, looper stereo 48 kHz.')
 print('Ardour resta separato. I profili ToneLib esistenti saranno prima copiati in ~/.local/share/tsmega-kit/backups/.')
 if args.dry_run:
  print('Simulazione: installazione dipendenze, importazione profilo, compilazione MIDI e icona sul desktop.');return
 if not (ROOT/'vendor/ToneLib-GFX').is_file() and not shutil.which('ToneLib-GFX'):
  raise RuntimeError('Install ToneLib GFX separately from https://tonelib.net/downloads.html before installing this source checkout.')
 if not args.no_deps:
  if not shutil.which('apt-get'):raise RuntimeError('Installazione automatica per Ubuntu/Debian/Mint. Su altre distribuzioni installa le dipendenze del LEGGIMI e usa --no-deps.')
  packages=['python3','python3-dbus','python3-gi','gir1.2-gtk-3.0','xserver-xephyr','openbox','xauth','x11-utils','build-essential','linux-libc-dev','libasound2-dev','jackd2','jack-tools','qjackctl','sooperlooper','zita-ajbridge','alsa-utils','wmctrl','libnotify-bin','xdg-user-dirs','libfontconfig1','libfreetype6','libgl1','libx11-6','libxext6','libxinerama1','libxcursor1','libxrandr2','libxrender1']
  missing=[]
  for package in packages:
   result=subprocess.run(['dpkg-query','-W','-f=${Status}',package],capture_output=True,text=True)
   if result.returncode or result.stdout!='install ok installed':missing.append(package)
  if missing:
   print('Pacchetti da installare:',', '.join(missing),flush=True)
   run('sudo','apt-get','update')
   run('sudo','apt-get','install','-y',*missing)
 for command in ('cc','jack_control','jack_lsp','jack_samplerate','qjackctl','sooperlooper','slgui','zita-a2j','zita-j2a','aconnect','wmctrl'):
  if not shutil.which(command):raise RuntimeError('Comando mancante: '+command)
 if subprocess.run(['pgrep','-x','ToneLib-GFX'],stdout=subprocess.DEVNULL).returncode==0:
  raise RuntimeError('Chiudi ToneLib prima di importare il profilo. Nessun preset è stato modificato.')
 install_profile(ROOT,Path.home(),force=not args.keep_profile)
 fresh_qjackctl(Path.home())
 folder=ROOT/'config/Jack/Drivers.d'
 run('cc','-Wall','-Wextra','-Werror','-O2',str(folder/'tsmega-midi.c'),'-Wl,-l:libasound.so.2','-o',str(folder/'tsmega-midi'))
 run(str(folder/'tsmega-midi'),'--self-test')
 run('cc','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC',str(ROOT/'src/slgui-lock.c'),'-Wl,-l:libgtk-3.so.0','-Wl,-l:libgobject-2.0.so.0','-Wl,-l:libglib-2.0.so.0','-o',str(ROOT/'vendor/slgui-lock.so'))
 try:desktop=Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
 except (OSError,subprocess.CalledProcessError):desktop=Path.home()/'Desktop'
 desktop.mkdir(parents=True,exist_ok=True)
 entry=desktop/'TSMega-kit.desktop';entry.write_text(desktop_entry(ROOT));entry.chmod(0o755)
 applications=Path.home()/'.local/share/applications';applications.mkdir(parents=True,exist_ok=True)
 shutil.copy2(entry,applications/entry.name)
 env=os.environ.copy();env.pop('GIO_MODULE_DIR',None)
 if shutil.which('gio'):subprocess.run(['gio','set',str(entry),'metadata::trusted','true'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 print('Pronto. Collega TS Mega e Chocolate, poi apri TSMega-kit dal desktop o esegui ./start-tsmega.')

if __name__=='__main__':
 try:main()
 except (RuntimeError,subprocess.CalledProcessError) as exc:print(str(exc),file=sys.stderr);sys.exit(1)
