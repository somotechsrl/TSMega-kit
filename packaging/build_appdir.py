#!/usr/bin/env python3
"""Build the AppDir inside an Ubuntu 22.04 runtime container."""
import hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
SOURCE=Path('/src');OUTPUT=SOURCE/'dist';APP=OUTPUT/'TSMega-kit.AppDir';VERSION=(SOURCE/'VERSION').read_text().strip()
if APP.exists():shutil.rmtree(APP)
APP.mkdir(parents=True);BASE=APP/'usr/share/tsmega-kit';KIT=BASE/'kit';KIT.mkdir(parents=True)
for name in ('bin','src','config','tests','LICENSES'):
 shutil.copytree(SOURCE/name,KIT/name,ignore=shutil.ignore_patterns('__pycache__','tsmega-midi','*.so','*.reginfo','*.wav','*.flac','*.mp3'))
for name in ('start-tsmega','stop-tsmega','install-tsmega','save-loop','save-config','import-drums','check-pedals','README.md','NOTICE','icona.svg'):shutil.copy2(SOURCE/name,KIT/name)
for name in ('state','log','vendor'):(KIT/name).mkdir(exist_ok=True)
subprocess.run(['cc','-O2',str(KIT/'config/Jack/Drivers.d/tsmega-midi.c'),'-Wl,-l:libasound.so.2','-o',str(KIT/'config/Jack/Drivers.d/tsmega-midi')],check=True)
subprocess.run(['cc','-O2','-shared','-fPIC',str(KIT/'src/slgui-lock.c'),'-Wl,-l:libgtk-3.so.0','-Wl,-l:libgobject-2.0.so.0','-Wl,-l:libglib-2.0.so.0','-o',str(KIT/'vendor/slgui-lock.so')],check=True)
shutil.copy2(SOURCE/'packaging/runtime.py',BASE/'runtime.py');shutil.copy2(SOURCE/'.cache-build/custom-dsp/custom-dsp-builds.json',BASE/'custom-dsp-builds.json');(BASE/'VERSION').write_text(VERSION+'\n');shutil.copy2('/etc/ssl/certs/ca-certificates.crt',BASE/'ca-bundle.crt')
shutil.copy2(SOURCE/'packaging/AppRun',APP/'AppRun');(APP/'AppRun').chmod(0o755)
shutil.copy2(SOURCE/'icona.svg',APP/'tsmega-kit.svg')
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf
GdkPixbuf.Pixbuf.new_from_file_at_scale(str(APP/'tsmega-kit.svg'),256,256,True).savev(str(APP/'tsmega-kit.png'),'png',[],[])
(APP/'.DirIcon').symlink_to('tsmega-kit.png')
(APP/'tsmega-kit.desktop').write_text('[Desktop Entry]\nType=Application\nName=TSMega-kit\nExec=AppRun\nIcon=tsmega-kit\nCategories=AudioVideo;Audio;\nStartupWMClass=TSMega-kit\n')
seeds=[];owned=set()
def copy(src,dest=None):
 src=Path(src);dest=Path(dest) if dest else APP/str(src).lstrip('/')
 if not src.exists():return
 if src.is_dir():
  shutil.copytree(src,dest,dirs_exist_ok=True,symlinks=False,ignore=shutil.ignore_patterns('__pycache__'));owned.update(p for p in src.rglob('*') if p.is_file())
  for p in dest.rglob('*'):
   if p.is_file():
    with p.open('rb') as f:
     if f.read(4)==b'\x7fELF':seeds.append(p)
 else:
  dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest,follow_symlinks=True);owned.add(src)
  with dest.open('rb') as f:
   if f.read(4)==b'\x7fELF':seeds.append(dest)
programs=['python3','sooperlooper','slgui','jackdbus','jack_control','jack_lsp','jack_samplerate','jack_connect','jack_disconnect','zita-a2j','zita-j2a','Xephyr','openbox','xauth','xprop','xwininfo','xrandr','wmctrl','notify-send','xdg-user-dir','gio','ffmpeg','ffprobe','zstd']
for name in programs:
 path=shutil.which(name)
 if not path:raise RuntimeError('Missing build tool '+name)
 copy(path,APP/'usr/bin'/name)
for path in ['/usr/lib/python3.10','/usr/lib/python3/dist-packages','/usr/lib/x86_64-linux-gnu/girepository-1.0','/usr/lib/x86_64-linux-gnu/gdk-pixbuf-2.0','/usr/lib/x86_64-linux-gnu/gtk-3.0','/usr/lib/x86_64-linux-gnu/jack','/usr/share/glib-2.0/schemas','/usr/share/themes/Clearlooks','/usr/share/xml/openbox','/usr/share/X11/xkb','/usr/share/icons/hicolor','/usr/share/icons/Adwaita','/usr/share/mime']:
 copy(path)
# The backing-track helper loads XTest dynamically to press the recognized Play
# control. It is not visible to ldd on the bundled executables.
xtst=Path('/usr/lib/x86_64-linux-gnu/libXtst.so.6')
if not xtst.exists():raise RuntimeError('Missing build library libXtst.so.6')
copy(xtst)
# Do not inject build tools, host GPU drivers or glibc into unrelated host commands.
blacklist=re.compile(r'^(ld-linux|libc\.so|libpthread\.so|libdl\.so|librt\.so|libm\.so|libresolv\.so|libutil\.so|libnss_|libstdc\+\+\.so|libgcc_s\.so|libGL\.so|libGLX|libGLdispatch|libEGL\.so|libGLES)')
seen=set()
while seeds:
 elf=seeds.pop()
 if elf in seen:continue
 seen.add(elf)
 text=subprocess.run(['ldd',str(elf)],capture_output=True,text=True).stdout
 for lib in re.findall(r'=> (/\S+)',text):
  path=Path(lib)
  if blacklist.match(path.name):continue
  dest=APP/'usr/lib/x86_64-linux-gnu'/path.name
  if not dest.exists():copy(path,dest)
# JACK uses a Python script; its interpreter must come from this runtime.
p=APP/'usr/bin/jack_control';text=p.read_text();p.write_text(re.sub(r'^#![^\n]+','#!/usr/bin/env python3',text,count=1));p.chmod(0o755)
(APP/'bin').mkdir()
for name in ('systemctl','systemd-run'):
 p=APP/'bin'/name;p.write_text('#!/bin/sh\nexec env -u LD_LIBRARY_PATH -u LD_PRELOAD -u PYTHONHOME -u PYTHONPATH -u GI_TYPELIB_PATH /usr/bin/'+name+' "$@"\n');p.chmod(0o755)
# Keep copyright/license files and exact source package versions for bundled files.
packages=set()
paths=[str(p) for p in owned if '__pycache__' not in p.parts]
for offset in range(0,len(paths),250):
 result=subprocess.run(['dpkg-query','-S',*paths[offset:offset+250]],capture_output=True,text=True)
 for row in result.stdout.splitlines():
  if ': /' in row:packages.update(row.split(': /',1)[0].split(', '))
manifest=[]
for package in sorted(packages):
 result=subprocess.run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n',package],capture_output=True,text=True)
 if result.returncode==0:manifest.append(result.stdout.strip().split('\t'))
 copyright=Path('/usr/share/doc')/package.split(':')[0]/'copyright'
 if copyright.exists():copy(copyright,BASE/'licenses'/package.replace(':','-')/'copyright')
(BASE/'runtime-packages.json').write_text(json.dumps(manifest,indent=2)+'\n')
subprocess.run(['glib-compile-schemas',str(APP/'usr/share/glib-2.0/schemas')],check=True)
print('AppDir ready:',APP,flush=True)
