#!/usr/bin/python3
"""Create only a desktop shortcut; do not start audio or import user settings."""
import os,pwd,shutil,subprocess
from pathlib import Path
if os.geteuid()==0:
 name=os.environ.get('SUDO_USER')
 if not name and os.environ.get('PKEXEC_UID'):name=pwd.getpwuid(int(os.environ['PKEXEC_UID'])).pw_name
 if not name or name=='root':raise SystemExit(0)
 user=pwd.getpwnam(name)
 env=os.environ.copy();env.update(HOME=user.pw_dir,USER=name,LOGNAME=name,XDG_RUNTIME_DIR=f'/run/user/{user.pw_uid}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{user.pw_uid}/bus')
 subprocess.run(['runuser','-u',name,'--','env',*[f'{k}={env[k]}' for k in ('HOME','USER','LOGNAME','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS')],'/usr/bin/python3',__file__],check=True)
 raise SystemExit(0)
try:desktop=Path(subprocess.check_output(['xdg-user-dir','DESKTOP'],text=True).strip())
except (OSError,subprocess.CalledProcessError):desktop=Path.home()/'Desktop'
desktop.mkdir(parents=True,exist_ok=True);target=desktop/'TSMega-kit.desktop'
shutil.copy2('/usr/share/applications/tsmega-kit.desktop',target);target.chmod(0o755)
if shutil.which('gio'):
 env=os.environ.copy();env.pop('GIO_MODULE_DIR',None)
 subprocess.run(['gio','set',str(target),'metadata::trusted','true'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
