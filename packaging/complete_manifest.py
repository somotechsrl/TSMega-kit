#!/usr/bin/env python3
"""Resolve merged-/usr library owners and complete runtime source/license metadata."""
import json,shutil,subprocess
from pathlib import Path
BASE=Path('/src/dist/TSMega-kit.AppDir/usr/share/tsmega-kit');APP=BASE.parents[2]
file=BASE/'runtime-packages.json';old=json.loads(file.read_text());packages={row[0] for row in old};paths=[]
for lib in (APP/'usr/lib/x86_64-linux-gnu').glob('*.so*'):
 paths.extend(['/usr/lib/x86_64-linux-gnu/'+lib.name,'/lib/x86_64-linux-gnu/'+lib.name])
for offset in range(0,len(paths),200):
 result=subprocess.run(['dpkg-query','-S',*paths[offset:offset+200]],capture_output=True,text=True)
 for row in result.stdout.splitlines():
  if ': /' in row:packages.update(row.split(': /',1)[0].split(', '))
manifest=[]
for package in sorted(packages):
 result=subprocess.run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n',package],capture_output=True,text=True)
 if result.returncode==0:manifest.append(result.stdout.strip().split('\t'))
 copyright=Path('/usr/share/doc')/package.split(':')[0]/'copyright'
 if copyright.exists():
  dest=BASE/'licenses'/package.replace(':','-')/'copyright';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(copyright,dest)
file.write_text(json.dumps(manifest,indent=2)+'\n');print('Runtime package manifest:',len(manifest))
