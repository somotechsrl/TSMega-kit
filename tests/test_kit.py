"""Offline regressions for pedal semantics, OSC messages and partial routing."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bin'))
from controls import transition
from osc import encode,decode
from profile import install_profile,bind_midi,fresh_qjackctl
spec=importlib.util.spec_from_file_location('routing',ROOT/'config/Jack/Drivers.d/tsmega-routing.py')
routing=importlib.util.module_from_spec(spec);spec.loader.exec_module(routing)

class Pedals(unittest.TestCase):
 def test_record_play_and_separate_overdub(self):
  self.assertEqual(transition('record_play',0,0),(['record'],2,False))
  self.assertEqual(transition('record_play',2,1),(['record'],4,True))
  self.assertEqual(transition('overdub',4,1),(['pause_off','mute_off','overdub'],5,False))
  self.assertEqual(transition('overdub',5,1),(['overdub'],4,True))
  self.assertNotIn('overdub',transition('record_play',4,1)[0])
 def test_pause_preserves_loop_and_resumes(self):
  self.assertEqual(transition('pause',4,1),(['pause_on'],14,True))
  self.assertEqual(transition('pause',14,1),(['pause_off'],4,False))
  self.assertEqual(transition('pause',5,1),(['overdub','pause_on'],14,True))
 def test_clear_finishes_active_operation(self):
  self.assertEqual(transition('clear',5,1),(['overdub','pause_off','undo_all'],0,True))
  self.assertEqual(transition('clear',2,1),(['record','pause_off','undo_all'],0,True))
 def test_empty_overdub_and_pause_do_nothing(self):
  for action in ('overdub','pause'):
   self.assertEqual(transition(action,0,0),([],0,False))
 def test_osc_roundtrip_and_alignment(self):
  for args in [('/ping','osc.udp://127.0.0.1:11111/','/pong'),('/update',0,'state',14.),('/save_session','a b.slsess','url','/error',1)]:
   data=encode(*args);self.assertEqual(len(data)%4,0);self.assertEqual(decode(data),(args[0],list(args[1:])))

class Routing(unittest.TestCase):
 def graph(self,*names):return {n:{'connections':[]} for n in names}
 def test_tonelib_input_without_ardour_or_looper(self):
  g=self.graph('TSMEGA_in:capture_1','JUCEJack:in_1','JUCEJack:in_2')
  add,remove=routing.plan(g,kit=True)
  self.assertEqual(set(add),{('TSMEGA_in:capture_1','JUCEJack:in_1'),('TSMEGA_in:capture_1','JUCEJack:in_2')});self.assertFalse(remove)
 def test_looper_to_ardour_without_tonelib(self):
  g=self.graph('TSMA_Looper:common_out_1','ardour:TSMA-Kit/audio_in 1')
  self.assertEqual(routing.plan(g,kit=True,tonelib=False),([('TSMA_Looper:common_out_1','ardour:TSMA-Kit/audio_in 1')],[]))
 def test_restores_missing_edges_and_leaves_other_devices(self):
  g=self.graph('JUCEJack:out_1','TSMA_Looper:common_in_1','unrelated:in')
  g['unrelated:in']['connections']=['PocketMaster:out'];g['TSMA_Looper:common_in_1']['connections']=['wrong:out']
  self.assertEqual(routing.plan(g,kit=True),([('JUCEJack:out_1','TSMA_Looper:common_in_1')],[('wrong:out','TSMA_Looper:common_in_1')]))
 def test_connected_edges_are_idempotent(self):
  g=self.graph('JUCEJack:out_1','TSMA_Looper:common_in_1')
  g['JUCEJack:out_1']['connections']=['TSMA_Looper:common_in_1'];g['TSMA_Looper:common_in_1']['connections']=['JUCEJack:out_1']
  self.assertEqual(routing.plan(g,kit=True),([],[]))
 def test_standalone_monitoring_and_ardour_takeover(self):
  g=self.graph('TSMA_Looper:common_out_1','TSMA_Looper:common_out_2','TSMEGA_out:playback_1','TSMEGA_out:playback_2')
  add,remove=routing.plan(g,kit=True,tonelib=False)
  self.assertEqual(len(add),2);self.assertFalse(remove)
  for source,dest in add:g[source]['connections'].append(dest);g[dest]['connections'].append(source)
  self.assertEqual(routing.plan(g,kit=True,tonelib=False),([],[]))
  for i in (1,2):g[f'ardour:TSMA-Kit/audio_in {i}']={'connections':[]}
  add,remove=routing.plan(g,kit=True,tonelib=False)
  self.assertEqual(len(add),2);self.assertEqual(len(remove),2)
  self.assertTrue(all(dest.startswith('ardour:') for _,dest in add))
 def test_obs_feed_keeps_hardware_monitoring_and_other_pipewire_sources(self):
  g=self.graph('TSMA_Looper:common_out_1','TSMA_Looper:common_out_2',
   'TSMEGA_out:playback_1','TSMEGA_out:playback_2',
   'PipeWire:capture_FL','PipeWire:capture_FR')
  g['PipeWire:capture_FL']['connections']=['system:capture_1']
  g['PipeWire:capture_FR']['connections']=['system:capture_2']
  add,remove=routing.plan(g,kit=True,tonelib=False)
  self.assertEqual(len(add),4);self.assertEqual(remove,[])
  for source,dest in add:g[source]['connections'].append(dest);g[dest]['connections'].append(source)
  self.assertEqual(routing.plan(g,kit=True,tonelib=False),([],[]))
  # A running Ardour without the kit track must still disable the OBS feed.
  add,remove=routing.plan(g,kit=True,tonelib=False,ardour=True)
  self.assertEqual(add,[])
  mirror=[('TSMA_Looper:common_out_1','PipeWire:capture_FL'),('TSMA_Looper:common_out_2','PipeWire:capture_FR')]
  self.assertEqual(remove,mirror)
  for source,dest in remove:g[source]['connections'].remove(dest);g[dest]['connections'].remove(source)
  self.assertEqual(routing.plan(g,kit=True,tonelib=False)[0],mirror)
  self.assertEqual(g['PipeWire:capture_FL']['connections'],['system:capture_1'])
 def test_any_ardour_graph_client_suppresses_obs_feed(self):
  for client in ('ardour','Ardour','ardour8','ardour-9','ardour-8.4.0~ds1'):
   g=self.graph('TSMA_Looper:common_out_1','PipeWire:capture_FL',client+':Master/audio_out 1')
   g['TSMA_Looper:common_out_1']['connections']=['PipeWire:capture_FL']
   self.assertEqual(routing.plan(g,kit=True,tonelib=False),([],[('TSMA_Looper:common_out_1','PipeWire:capture_FL')]))
 def test_inactive_kit_removes_only_its_obs_feed(self):
  g=self.graph('TSMA_Looper:common_out_1','PipeWire:capture_FL')
  g['TSMA_Looper:common_out_1']['connections']=['PipeWire:capture_FL']
  self.assertEqual(routing.plan(g,kit=False,tonelib=False),([],[('TSMA_Looper:common_out_1','PipeWire:capture_FL')]))

class PortableProfile(unittest.TestCase):
 def test_new_home_and_renumbered_midi(self):
  import xml.etree.ElementTree as ET
  with tempfile.TemporaryDirectory(prefix='tsma home with spaces ') as folder:
   home=Path(folder)
   self.assertTrue(install_profile(ROOT,home))
   path=home/'.config/Gadwin/ToneLib GFX/_app.cfg'
   self.assertIn('100 100 1200 800',path.read_text())
   clients='Client 203 : "TSMEGA ToneLib" [User Legacy]\n  Port 1 : "ToneLib Controls" (R-e-) [In]\n'
   self.assertTrue(bind_midi(home,clients))
   setup=ET.parse(path).find("VALUE[@name='audio.device.state']/DEVICESETUP")
   self.assertEqual([(p.get('name'),p.get('identifier')) for p in setup.findall('MIDIINPUT')],[('ToneLib Controls','203-1')])
   self.assertFalse(install_profile(ROOT,home))
   fresh_qjackctl(home)
   qconf=home/'.config/rncbc.org/QjackCtl.conf'
   self.assertIn('Driver=dummy',qconf.read_text());self.assertNotIn('/home/localuser',qconf.read_text())
   qconf.write_text('existing');fresh_qjackctl(home);self.assertEqual(qconf.read_text(),'existing')
 def test_import_backs_up_existing_profile_and_keeps_activation(self):
  with tempfile.TemporaryDirectory() as folder:
   home=Path(folder);target=home/'.config/Gadwin';(target/'Shared').mkdir(parents=True)
   (target/'Shared/com.tonelib.gfx4.reginfo').write_text('existing activation')
   (target/'old-marker').write_text('saved')
   install_profile(ROOT,home,force=True)
   self.assertEqual((target/'Shared/com.tonelib.gfx4.reginfo').read_text(),'existing activation')
   self.assertEqual(len(list((home/'.local/share/tsmega-kit/backups').glob('*/old-marker'))),1)

if __name__=='__main__':unittest.main()
