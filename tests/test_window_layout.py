import sys
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from window_layout import minimum_size,sizes,load_geometry,save_geometry,fit_geometry


class WindowSettings(unittest.TestCase):
 def setUp(self):
  self.geometry=dict(x=-1600,y=40,width=1200,height=800)

 def test_old_maximized_flag_is_ignored(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'window.json'
   save_geometry(path,dict(self.geometry,maximized=True))
   self.assertEqual(load_geometry(path),self.geometry)

 def test_persistence_survives_restart_and_replaces_previous_settings(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'tsmega-kit/window.json'
   self.assertIsNone(load_geometry(path))
   save_geometry(path,self.geometry)
   self.assertEqual(load_geometry(path),self.geometry)
   moved=dict(self.geometry,x=200,width=1400)
   save_geometry(path,moved)
   self.assertEqual(load_geometry(path),moved)
   self.assertFalse(path.with_suffix('.tmp').exists())

 def test_invalid_settings_fall_back_to_defaults(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'window.json'
   for content in ('{', 'null', '[]', '{}',
                   '{"x":0,"y":0,"width":"1200","height":800}',
                   '{"x":0,"y":0,"width":0,"height":800}'):
    path.write_text(content)
    self.assertIsNone(load_geometry(path))

 def test_negative_coordinates_on_connected_monitor_are_preserved(self):
  areas=[(-1920,0,1920,1080),(0,0,1920,1080)]
  self.assertEqual(fit_geometry(self.geometry,areas,areas[1]),self.geometry)

 def test_removed_monitor_and_smaller_screen_remain_visible(self):
  area=(0,24,1024,744)
  self.assertEqual(fit_geometry(self.geometry,[area],area),
                   dict(self.geometry,x=0,y=24,width=1024,height=744))

 def test_partially_offscreen_window_is_brought_inside_workarea(self):
  area=(0,24,1920,1056)
  geometry=dict(self.geometry,x=1600,y=900)
  self.assertEqual(fit_geometry(geometry,[area],area),
                   dict(geometry,x=720,y=280))


class Layout(unittest.TestCase):
 def test_bundled_wxgtk_minimum_is_not_clipped(self):
  hints='WM_NORMAL_HINTS(WM_SIZE_HINTS):\n\t\tprogram specified minimum size: 848 by 187'
  width,height=minimum_size(hints)
  looper,tone=sizes(1506,920,height)
  self.assertGreaterEqual(looper[3],height)
  self.assertEqual(looper[1]+looper[3],920)
  self.assertEqual(tone[1]+tone[3],looper[1])
  self.assertEqual(width,848)

 def test_other_theme_minimum_still_fits(self):
  for screen in (600,768,920):
   for requested in (160,187,224):
    looper,tone=sizes(1000,screen,requested)
    self.assertGreaterEqual(looper[3],requested)
    self.assertEqual(looper[1]+looper[3],screen)
    self.assertEqual(tone[3],looper[1])

 def test_missing_hints_have_a_safe_default(self):
  self.assertEqual(minimum_size('WM_NORMAL_HINTS: not found.'),(848,187))

 def test_compact_panel_does_not_reintroduce_hidden_menu_space(self):
  looper,tone=sizes(1506,920,178)
  self.assertEqual(looper,(0,742,1506,178))
  self.assertEqual(tone,(0,0,1506,742))
