#!/usr/bin/env python3
"""Wrap the same tested AppImage in Debian and Fedora native packages."""
import os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];VERSION=(ROOT/'VERSION').read_text().strip();DIST=ROOT/'dist';STAGE=DIST/'native-root'
if STAGE.exists():shutil.rmtree(STAGE)
STAGE.mkdir(parents=True)
def install(source,target,mode=0o644):
 dest=STAGE/target.lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);dest.chmod(mode)
install(DIST/f'TSMega-kit-{VERSION}-x86_64.AppImage','/usr/lib/tsmega-kit/TSMega-kit.AppImage',0o755)
for source,target,mode in [('packaging/native-launcher','/usr/bin/tsmega-kit',0o755),('packaging/install-desktop.py','/usr/share/tsmega-kit/install-desktop.py',0o755),('packaging/tsmega-kit.desktop','/usr/share/applications/tsmega-kit.desktop',0o644),('packaging/desktop-autostart.desktop','/etc/xdg/autostart/tsmega-kit-desktop.desktop',0o644),('icona.svg','/usr/share/icons/hicolor/scalable/apps/tsmega-kit.svg',0o644),('VERSION','/usr/share/tsmega-kit/VERSION',0o644),('README.md','/usr/share/doc/tsmega-kit/README.md',0o644),('NOTICE','/usr/share/doc/tsmega-kit/NOTICE',0o644)]:install(ROOT/source,target,mode)
control=STAGE/'DEBIAN';control.mkdir()
size=sum(p.stat().st_size for p in STAGE.rglob('*') if p.is_file())//1024
(control/'control').write_text(f'''Package: tsmega-kit
Version: {VERSION}
Architecture: amd64
Maintainer: TSMega-kit <noreply@github.com>
Section: sound
Priority: optional
Installed-Size: {size}
Depends: libc6 (>= 2.35), libstdc++6, libgcc-s1, libgl1, libegl1, python3, systemd, dbus-user-session, xdg-user-dirs, util-linux, coreutils
Homepage: https://github.com/somotechsrl/TSMega-kit
Description: Standalone Tone Shifter guitar effects and live looping kit
 Bundled SooperLooper, JACK and performance interface with writable user data.
 ToneLib GFX is downloaded separately from its official vendor on first use.
 No personal license, registration or backing-track audio is included.
''')
(control/'postinst').write_text('#!/bin/sh\nset -e\nif [ "$1" = configure ]; then\n /usr/bin/python3 /usr/share/tsmega-kit/install-desktop.py || true\nfi\nexit 0\n');(control/'postinst').chmod(0o755)
subprocess.run(['dpkg-deb','--root-owner-group','-Zxz','--build',str(STAGE),str(DIST/f'tsmega-kit_{VERSION}_amd64.deb')],check=True)
shutil.rmtree(control)
rpmroot=ROOT/'.cache-build/rpm'
for name in ('BUILD','RPMS','SOURCES','SPECS','SRPMS','BUILDROOT'):(rpmroot/name).mkdir(parents=True,exist_ok=True)
spec=rpmroot/'SPECS/tsmega-kit.spec'
spec.write_text(f'''Name: tsmega-kit
Version: {VERSION}
Release: 1
Summary: Standalone guitar effects and live looping kit
License: LicenseRef-TSMega-kit AND GPL-2.0-or-later AND LGPL-2.1-or-later AND Python-2.0
URL: https://github.com/somotechsrl/TSMega-kit
BuildArch: x86_64
AutoReqProv: no
Requires: glibc >= 2.35, libstdc++, libgcc, libglvnd-glx, libglvnd-egl, python3, systemd, dbus, xdg-user-dirs, util-linux, coreutils

%description
Bundled SooperLooper, JACK and a single guitar performance window.
ToneLib GFX is downloaded from its official vendor on first use.
No author license, registration or private backing tracks are included.

%prep
%build
%install
mkdir -p %{{buildroot}}
cp -a {STAGE}/. %{{buildroot}}/

%post
/usr/bin/python3 /usr/share/tsmega-kit/install-desktop.py || :

%files
/usr/bin/tsmega-kit
/usr/lib/tsmega-kit
/usr/share/tsmega-kit
/usr/share/applications/tsmega-kit.desktop
/usr/share/icons/hicolor/scalable/apps/tsmega-kit.svg
/etc/xdg/autostart/tsmega-kit-desktop.desktop
/usr/share/doc/tsmega-kit
''')
subprocess.run(['rpmbuild','-bb','--define',f'_topdir {rpmroot}','--define','_build_id_links none','--define','__os_install_post %{nil}',str(spec)],check=True)
for p in (rpmroot/'RPMS').rglob('*.rpm'):shutil.copy2(p,DIST/p.name)
print('Native packages ready.')
