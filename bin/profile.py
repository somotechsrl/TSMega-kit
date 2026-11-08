"""Install the saved musical profile without importing workstation hardware IDs."""
import re,shutil,time
import xml.etree.ElementTree as ET
from pathlib import Path

def install_profile(root,home,force=False):
 source=root/'config/Gadwin';target=home/'.config/Gadwin'
 if (target/'ToneLib GFX').exists() and not force:return False
 if target.exists() and force:
  backup=home/'.local/share/tsmega-kit/backups'/time.strftime('%Y%m%d-%H%M%S')
  backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(target,backup)
 target.mkdir(parents=True,exist_ok=True)
 for name in ('ToneLib GFX','Shared'):
  for path in (source/name).rglob('*'):
   if not path.is_file() or path.name.endswith('.reginfo') or '_app_temp' in path.name:continue
   dest=target/path.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
 config=target/'ToneLib GFX/_app.cfg';tree=ET.parse(config)
 for value in tree.findall('VALUE'):
  name=value.get('name','')
  if name=='wnd.pos':value.set('val','100 100 1200 800 frame 37 0 0 0')
  elif name.startswith('recent_'):value.set('val','')
  elif name=='gfx.impulses.dir':value.set('val',str(target/'Shared/impulses'))
 setup=tree.find("VALUE[@name='audio.device.state']/DEVICESETUP")
 if setup is not None:
  for midi in list(setup):setup.remove(midi)
 tree.write(config,encoding='utf-8',xml_declaration=True)
 return True

def bind_midi(home,clients=None):
 if clients is None:clients=Path('/proc/asound/seq/clients').read_text()
 client=None;identifier=None
 for line in clients.splitlines():
  match=re.match(r'Client\s+(\d+)\s+:\s+"([^"]+)"',line)
  if match:client=match[1] if match[2]=='TSMEGA ToneLib' else None
  port=re.match(r'\s+Port\s+(\d+)\s+:\s+"ToneLib Controls"',line)
  if client is not None and port:identifier=client+'-'+port[1];break
 if identifier is None:return False
 config=home/'.config/Gadwin/ToneLib GFX/_app.cfg';tree=ET.parse(config)
 setup=tree.find("VALUE[@name='audio.device.state']/DEVICESETUP")
 if setup is None:raise RuntimeError('Configurazione audio ToneLib assente.')
 # Only the normalized adapter feeds ToneLib; raw pedals must not trigger twice.
 for midi in list(setup):
  if midi.tag=='MIDIINPUT':setup.remove(midi)
 ET.SubElement(setup,'MIDIINPUT',name='ToneLib Controls',identifier=identifier)
 tree.write(config,encoding='utf-8',xml_declaration=True)
 return True

def fresh_qjackctl(home):
 path=home/'.config/rncbc.org/QjackCtl.conf'
 if path.exists():return
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text('''[Options]\nDBusEnabled=true\nJackDBusEnabled=true\nStartJack=false\nStopJack=false\nStartupScript=false\nPostStartupScript=false\nShutdownScript=false\nPostShutdownScript=false\n[Settings]\nDriver=dummy\nSampleRate=48000\nFrames=256\nPeriods=1\nRealtime=true\nMidiDriver=none\nServer=jackd\n''')


def configure_backing_library(home,library):
 library=Path(library)
 if not library.is_dir() or not any(p.suffix.lower() in ('.mp3','.wav','.flac') for p in library.rglob('*')):return
 config=home/'.config/Gadwin/ToneLib GFX/_app.cfg';tree=ET.parse(config);root=tree.getroot()
 value=root.find("VALUE[@name='recent_gfx.audio_dirs']")
 if value is None:value=ET.SubElement(root,'VALUE',name='recent_gfx.audio_dirs',val='')
 previous=value.get('val','').splitlines();folder=str(library.resolve())
 value.set('val','\n'.join([folder]+[p for p in previous if p and p!=folder]))
 tree.write(config,encoding='utf-8',xml_declaration=True)
