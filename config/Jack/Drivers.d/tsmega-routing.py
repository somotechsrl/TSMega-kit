#!/usr/bin/python3
"""Reconnect the guitar chain; use TS MEGA monitoring when the DAW is absent."""
import json,os,re,signal,socket,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATE=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'jack-hooks-{os.getuid()}'
running=True
ARDOUR_NAME=r'ardour(-?[0-9][a-zA-Z0-9.~+-]*)?'

def stop(*args):
 global running
 running=False

def graph():
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(2);s.connect(str(STATE/'monitor-graph.sock'));s.sendall(b'graph\n');data=b''
  while not data.endswith(b'\n'):
   part=s.recv(65536)
   if not part:raise OSError('Graph service closed')
   data+=part
  return json.loads(data)['ports']

def plan(g, kit=None, tonelib=True, track='TSMA-Kit', ardour=False):
 if kit is None:kit=(STATE/'tsmega-kit.active').exists()
 wanted=[];owned=[]
 def edge(source,dest):
  if dest in g:
   owned.append(dest)
   if source in g:wanted.append((source,dest))
 if tonelib:
  for i in (1,2):edge('TSMEGA_in:capture_1',f'JUCEJack:in_{i}')
 if kit:
  daw=all(f'ardour:{track}/audio_in {i}' in g for i in (1,2))
  for i in (1,2):
   if tonelib:edge(f'JUCEJack:out_{i}',f'TSMA_Looper:common_in_{i}')
   elif f'TSMA_Looper:common_in_{i}' in g:owned.append(f'TSMA_Looper:common_in_{i}')
   edge(f'TSMA_Looper:common_out_{i}',f'ardour:{track}/audio_in {i}')
   if not daw:edge(f'TSMA_Looper:common_out_{i}',f'TSMEGA_out:playback_{i}')
 else:
  if tonelib:
   for i in (1,2):edge(f'JUCEJack:out_{i}',f'ardour:{track}/audio_in {i}')
 # Feed PipeWire's JACK Source (usable by OBS) only without Ardour. Check
 # every Ardour client, including sessions without the dedicated kit track.
 daw_active=ardour or any(re.fullmatch(ARDOUR_NAME,port.partition(':')[0],re.I) for port in g)
 disconnect=[]
 for i,channel in ((1,'FL'),(2,'FR')):
  source=f'TSMA_Looper:common_out_{i}';dest=f'PipeWire:capture_{channel}'
  if source not in g or dest not in g:continue
  if kit and not daw_active:
   wanted.append((source,dest))
  elif dest in g[source]['connections']:
   disconnect.append((source,dest))
 # The PipeWire inputs can also carry other audio. Remove only our own
 # mirror links when Ardour appears, preserving all other connections.
 for dest in set(owned):
  expected={source for source,target in wanted if target==dest}
  disconnect.extend((source,dest) for source in g[dest]['connections'] if source not in expected)
 sources=([f'JUCEJack:out_{i}' for i in (1,2)] if tonelib else [])
 if kit:sources.extend(f'TSMA_Looper:common_out_{i}' for i in (1,2))
 for source in sources:
  if source in g:
   disconnect.extend((source,dest) for dest in g[source]['connections'] if dest.startswith(('system:','TSMEGA_out:')) and (source,dest) not in wanted)
 return [(source,dest) for source,dest in wanted if dest not in g[source]['connections']],disconnect

def tonelib_running():
 return subprocess.run(['pgrep','-x','ToneLib-GFX'],stdout=subprocess.DEVNULL).returncode==0

def ardour_running():
 return subprocess.run(['pgrep','-ix',ARDOUR_NAME],stdout=subprocess.DEVNULL,timeout=2).returncode==0

if __name__=='__main__':
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 owner=os.environ.get('JACK_DRIVERS_OWNER_PID')
 owner_file=Path(f'/proc/{owner}/stat') if owner else None
 owner_start=owner_file.read_text().split()[21] if owner_file else None
 midi=subprocess.Popen([str(ROOT/'tsmega-midi')])
 try:
  while running:
   if owner_file:
    try:
     if owner_file.read_text().split()[21]!=owner_start:break
    except OSError:break
   if midi.poll() is not None:raise RuntimeError('TSMEGA MIDI adapter stopped')
   try:
    g=graph();connect,disconnect=plan(g,tonelib=tonelib_running(),ardour=ardour_running())
    for source,dest in disconnect:
     subprocess.run(['jack_disconnect',source,dest],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
    for source,dest in connect:
     subprocess.run(['jack_connect',source,dest],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
   except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as e:
    pass
   time.sleep(.5)
 finally:
  midi.terminate()
  try:midi.wait(timeout=3)
  except subprocess.TimeoutExpired:midi.kill();midi.wait()
