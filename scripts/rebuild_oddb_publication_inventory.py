#!/usr/bin/env python3
"""Regenerate ODDB publication manifest and SHA256SUMS after git-add, preserving provenance metadata."""
import hashlib
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

root=Path.cwd()
assert (root/'.git').exists() and (root/'package_manifest.json').exists()
tracked=sorted(p.decode() for p in subprocess.check_output(['git','ls-files','-z']).split(b'\0') if p)
assert 'package_manifest.json' in tracked and 'SHA256SUMS.txt' in tracked
assert all((root/p).is_file() for p in tracked), 'Unexpected non-file/symlink in tracked set'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path=root/'package_manifest.json'
manifest=json.loads(manifest_path.read_text())
manifest['created_at_utc']=datetime.now(timezone.utc).isoformat()
manifest['files']=[{'path':p,'size_bytes':(root/p).stat().st_size,'sha256':sha(root/p)} for p in tracked if p not in {'package_manifest.json','SHA256SUMS.txt'}]
manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
checks=[f'{sha(root/p)}  {p}' for p in tracked if p!='SHA256SUMS.txt']
(root/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n')
print('Manifest entries:',len(manifest['files']))
print('SHA-256 entries:',len(checks))
