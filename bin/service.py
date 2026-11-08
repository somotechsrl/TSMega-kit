#!/usr/bin/python3
"""Own the dedicated SooperLooper engine and translate the four looper pedals."""
import fcntl,json,os,selectors,signal,socket,subprocess,time
import xml.etree.ElementTree as ET
from pathlib import Path
from osc import encode,decode
from controls import transition
ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'config/kit.json').read_text())
RUNTIME=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/f'jack-hooks-{os.getuid()}'
SESSION=ROOT/'state/looper.slsess'
SOCKET=RUNTIME/'tsma-looper.sock'
FLAG=RUNTIME/'tsmega-kit.active'
STATUS=RUNTIME/'tsmega-kit.status.json'

class Kit:
 def __init__(self):
  self.running=True;self.engine=None;self.ready=False;self.state=-1;self.length=0.;self.next_start=0;self.save_at=None
  self.udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.udp.bind(('127.0.0.1',0));self.udp.setblocking(False)
  self.url=f'osc.udp://127.0.0.1:{self.udp.getsockname()[1]}/'
  self.control=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
  SOCKET.unlink(missing_ok=True);self.control.bind(str(SOCKET));os.chmod(SOCKET,0o600);self.control.setblocking(False)
  self.selector=selectors.DefaultSelector();self.selector.register(self.udp,selectors.EVENT_READ,'osc');self.selector.register(self.control,selectors.EVENT_READ,'pedal')
  self.log=(ROOT/'log/engine.log').open('a')
 def send(self,path,*args):self.udp.sendto(encode(path,*args),('127.0.0.1',CONFIG['osc_port']))
 def hit(self,name):self.send('/sl/0/hit',name)
 def start_engine(self):
  if subprocess.run(['jack_control','status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3).returncode:return
  # Saved sessions contain absolute audio paths. Rebase only audio files that
  # actually travel alongside this session when the kit folder is moved.
  if SESSION.is_file():
   tree=ET.parse(SESSION);changed=False
   for loop in tree.findall('.//Looper'):
    audio=loop.get('loop_audio')
    if audio:
     local=SESSION.parent/Path(audio).name
     if local.is_file() and str(local)!=audio:loop.set('loop_audio',str(local));changed=True
   if changed:tree.write(SESSION,encoding='utf-8',xml_declaration=True)
  args=['sooperlooper','-j',CONFIG['jack_client'],'-p',str(CONFIG['osc_port']),'-l','1','-c',str(CONFIG['channels']),'-t',str(CONFIG['loop_seconds']),'-D','no']
  if SESSION.is_file():args+=['-L',str(SESSION)]
  self.engine=subprocess.Popen(args,stdout=self.log,stderr=subprocess.STDOUT)
  self.ready=False;self.state=-1;self.length=0.;self.started=time.monotonic();self.setup_at=0
 def setup(self):
  self.send('/set','dry',1.);self.send('/set','wet',1.);self.send('/set','input_gain',1.)
  self.send('/set','auto_disable_latency',1.)
  for name,value in {'dry':0.,'wet':1.,'input_gain':1.,'feedback':1.,'rec_thresh':0.,'quantize':0.,'round':0.,'sync':0.,'playback_sync':0.,'use_common_ins':1.,'use_common_outs':1.,'fade_samples':64.}.items():self.send('/sl/0/set',name,value)
  for name in ('state','loop_len'):
   self.send('/sl/0/register_auto_update',name,20,self.url,'/update')
   self.send('/sl/0/get',name,self.url,'/update')
  self.hit('pause_on') if SESSION.is_file() else None
  self.ready=True;FLAG.write_text(str(ROOT)+'\n')
  # Compatibility for an already-running central driver from the previous name.
  legacy=RUNTIME/'tsma-kit.active'
  if not legacy.exists():
   legacy.unlink(missing_ok=True);legacy.symlink_to(FLAG.name)
  print('SooperLooper pronto',flush=True)
 def action(self,action):
  if action=='save':self.save();return
  if not self.ready or self.state<0:print('Looper non ancora pronto',flush=True);return
  action={'record_play_overdub':'record_play','stop':'pause'}.get(action,action)
  commands,new_state,save=transition(action,self.state,self.length)
  for name in commands:self.hit(name)
  self.state=new_state
  if action=='clear':self.length=0.
  if save:self.save_at=time.monotonic()+.7
  print('Pedale',action,'stato previsto',self.state,flush=True)
 def save(self):
  if not self.ready:return
  if self.state in (1,2,3,5):self.save_at=time.monotonic()+1;return
  self.send('/save_session',str(SESSION),self.url,'/error',1)
  self.save_at=None;print('Salvataggio loop richiesto',flush=True)
 def receive(self):
  try:path,args=decode(self.udp.recv(65536))
  except (ValueError,IndexError,BlockingIOError):return
  if path=='/pong' and not self.ready:self.setup()
  elif path=='/update' and len(args)>=3:
   if args[1]=='state':self.state=int(args[2])
   elif args[1]=='loop_len':self.length=float(args[2])
  elif path=='/error':print('SooperLooper:',args,flush=True)
 def run(self):
  last_ping=last_status=0
  try:
   while self.running:
    now=time.monotonic()
    if self.engine is None or self.engine.poll() is not None:
     if now>=self.next_start:
      FLAG.unlink(missing_ok=True);self.ready=False
      self.start_engine();self.next_start=now+2
    if self.engine is not None and self.engine.poll() is None and now-last_ping>=1:
     self.send('/ping',self.url,'/pong');last_ping=now
    for key,_ in self.selector.select(.02):
     if key.data=='osc':self.receive()
     else:
      try:self.action(self.control.recv(256).decode().strip())
      except (ValueError,BlockingIOError):pass
    if self.save_at is not None and now>=self.save_at:self.save()
    if now-last_status>=.5:
     tmp=STATUS.with_suffix('.tmp');tmp.write_text(json.dumps({'ready':self.ready,'state':self.state,'loop_seconds':self.length,'engine_pid':self.engine.pid if self.engine else None,'kit':str(ROOT),'updated':time.time()}));tmp.replace(STATUS);last_status=now
  finally:
   self.save();time.sleep(.3)
   FLAG.unlink(missing_ok=True);SOCKET.unlink(missing_ok=True);STATUS.unlink(missing_ok=True)
   if self.engine is not None and self.engine.poll() is None:
    self.engine.terminate()
    try:self.engine.wait(timeout=3)
    except subprocess.TimeoutExpired:self.engine.kill();self.engine.wait()
   self.log.close();self.control.close();self.udp.close()

if __name__=='__main__':
 RUNTIME.mkdir(mode=0o700,exist_ok=True);(ROOT/'state').mkdir(exist_ok=True);(ROOT/'log').mkdir(exist_ok=True)
 with open(RUNTIME/'tsmega-kit.lock','w') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit(0)
  kit=Kit();signal.signal(signal.SIGTERM,lambda *_:setattr(kit,'running',False));signal.signal(signal.SIGINT,lambda *_:setattr(kit,'running',False));kit.run()
