#!/usr/bin/env python3
"""Download exact Ubuntu source packages corresponding to the bundled runtime."""
import json,subprocess,tarfile
from pathlib import Path
ROOT=Path('/src');DIST=ROOT/'dist';VERSION=(ROOT/'VERSION').read_text().strip()
manifest=json.loads((DIST/'TSMega-kit.AppDir/usr/share/tsmega-kit/runtime-packages.json').read_text())
folder=ROOT/'.cache-build/runtime-sources';folder.mkdir(parents=True,exist_ok=True)
packages=[package+'='+version for package,version in sorted({(row[2],row[3]) for row in manifest})]
subprocess.run(['apt-get','source','-y','--download-only',*packages],cwd=folder,check=True)
with tarfile.open(DIST/f'TSMega-kit-{VERSION}-runtime-sources.tar.gz','w:gz',compresslevel=1) as archive:
 for file in sorted(folder.iterdir()):
  if file.is_file():archive.add(file,arcname=file.name)
 archive.add(DIST/'TSMega-kit.AppDir/usr/share/tsmega-kit/runtime-packages.json',arcname='runtime-packages.json')
 for file in sorted((ROOT/'.cache-build/custom-dsp').glob('*.tar.bz2')):archive.add(file,arcname='custom-dsp/'+file.name)
 archive.add(ROOT/'.cache-build/custom-dsp/custom-dsp-builds.json',arcname='custom-dsp/custom-dsp-builds.json')
 archive.add(ROOT/'packaging/build_dsp.py',arcname='custom-dsp/build_dsp.py')
print('Runtime source archive ready.')
