#!/usr/bin/env python3
"""Read the live ODDB deployment and create a reviewed-source publication ZIP."""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import tokenize
import urllib.request
import zipfile

BASE = '93ff1dba3302ec6e95b6bc8880cf31105be91f33'
REPO = 'https://github.com/UmairSeemab/ODDB'
MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 500 * 1024 * 1024
BAD_PARTS = {'secrets', 'private', 'backups', 'backup', 'database', 'analytics_data',
             'geodata', 'downloads', 'node_modules', '.git', '__pycache__', '.venv',
             'source_review', 'reports', 'logs', 'sessions', 'cache'}
BAD_SUFFIXES = {'.zip', '.gz', '.tar', '.sqlite', '.db', '.sql', '.csv', '.tsv',
                '.xlsx', '.pdf', '.pem', '.key', '.p12', '.pfx', '.log', '.bak',
                '.old', '.pyc', '.ipynb'}
SOURCE_SUFFIXES = {'.php', '.js', '.css', '.html', '.json', '.md', '.py', '.sh',
                   '.yaml', '.yml', '.toml', '.ini', '.conf', '.svg', '.png',
                   '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.woff2', '.ttf',
                   '.eot', '.txt', '.cff', '.example', '.map'}

DB_READ = r'''<?php
$pdo = new PDO('mysql:host='.getenv('ODDB_DB_HOST').';port='.(getenv('ODDB_DB_PORT')?:'3306').';dbname='.getenv('ODDB_DB_NAME').';charset=utf8mb4',getenv('ODDB_DB_USER'),getenv('ODDB_DB_PASSWORD'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
$pdo->exec('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
$tables=$pdo->query("SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")->fetchAll(PDO::FETCH_ASSOC);
$out=['counts'=>[],'definitions'=>[]];
foreach($tables as $t){
 $name=$t['TABLE_NAME'];
 if(!preg_match('/^[A-Za-z0-9_]+$/',$name)||$t['ENGINE']!=='InnoDB')throw new RuntimeException('Unexpected table or engine');
 $out['counts'][$name]=(int)$pdo->query('SELECT COUNT(*) FROM `'.$name.'`')->fetchColumn();
 $r=$pdo->query('SHOW CREATE TABLE `'.$name.'`')->fetch(PDO::FETCH_NUM);
 $ddl=preg_replace('/ AUTO_INCREMENT=\d+/','',$r[1]);
 $out['definitions'][$name]=$ddl;
}
$out['views_omitted']=(int)$pdo->query("SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE()")->fetchColumn();
$pdo->rollBack();echo json_encode($out,JSON_THROW_ON_ERROR);
'''

def command(args, data=None):
    p = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError('Command failed: '+args[0]+' (details suppressed to protect credentials)')
    return p.stdout

def docker(*args, data=None):
    return command(['sudo', '-n', 'docker', *args], data)

def inspect(name):
    return json.loads(docker('inspect', name))[0]

def identity(info):
    return (info['Id'], info['Image'], info['State']['StartedAt'])

def allowed(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        return False
    lower = [v.lower() for v in p.parts]
    if any(v in BAD_PARTS or 'backup' in v or 'before_' in v or
           v.startswith(('stats_staging_build', 'statistics_backup', 'stats_build'))
           for v in lower):
        return False
    n = p.name.lower()
    if n.startswith('.') and n not in {'.gitignore', '.dockerignore', '.env.example', '.htaccess'}:
        return False
    if n.startswith('.env') and n != '.env.example':
        return False
    if any(x in n for x in ('id_rsa', 'id_ed25519', 'credential', 'password', 'visitor_aggregates')):
        return False
    if p.suffix.lower() in BAD_SUFFIXES:
        return False
    return p.suffix.lower() in SOURCE_SUFFIXES or n in {'dockerfile', 'license', 'notice', 'copying', 'makefile', '.gitignore', '.dockerignore', '.htaccess'}

PLACEHOLDER = re.compile(r'(?:your[_ -]|example|placeholder|change[_ -]?me|replace[_ -]|dummy|^\*+$|^\.+$)', re.I)
LITERAL = re.compile(r'''(?ix)
    ["']?\b(?:[a-z0-9_]*(?:password|passwd|secret|api_key|access_token|auth_token)[a-z0-9_]*)["']?
    \s*(?:=>|:|=)\s*(["'])([^"'\r\n]{8,})\1
''')

def python_string_spans(text):
    """Locate complete Python string tokens without executing source."""
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    try:
        return [(offsets[t.start[0]-1]+t.start[1],
                 offsets[t.end[0]-1]+t.end[1])
                for t in tokenize.generate_tokens(io.StringIO(text).readline)
                if t.type == tokenize.STRING]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []  # Keep the stricter text check if tokenization fails.

def clean(data, secrets, python_source=False):
    count = 0
    for value in sorted(secrets, key=len, reverse=True):
        raw = value.encode()
        if raw in data:
            count += data.count(raw)
            data = data.replace(raw, b'REPLACE_WITH_PRIVATE_SECRET')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return data, count
    if re.search(r'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----', text):
        raise ValueError('private key')
    if re.search(r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b', text):
        raise ValueError('credential signature')
    spans = python_string_spans(text) if python_source else []
    for match in LITERAL.finditer(text):
        # A regex can mistake the end of one Python string and the start of
        # another for a quoted credential. Those intervening bytes are code.
        opening = next((s for s in spans if s[0] <= match.start(1) < s[1]), None)
        closing = next((s for s in spans if s[0] <= match.end()-1 < s[1]), None)
        if opening is not None and closing is not None and opening != closing:
            continue
        value = match.group(2)
        # Templates and variable interpolation are source, not literal credentials.
        if not PLACEHOLDER.search(value) and not any(x in value for x in ('$', '${', '%', '<', '>', '\\')):
            raise ValueError('possible literal credential')
    return data, count

class Collector:
    def __init__(self, root, secrets):
        self.root, self.secrets = root, secrets
        self.total = self.redactions = self.excluded = 0
        self.blocked = []

    def add(self, name, data, trusted_generated=False):
        if not trusted_generated and not allowed(name):
            self.excluded += 1
            return
        if len(data) > MAX_FILE or self.total + len(data) > MAX_TOTAL:
            raise RuntimeError('Source package size limit exceeded')
        try:
            data, n = clean(data, self.secrets, python_source=name.endswith('.py'))
        except ValueError as error:
            self.blocked.append({'path': name, 'reason': str(error)})
            return
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.total += len(data)
        self.redactions += n

    def container_tree(self, container, source, prefix):
        # Read a streaming tar. Never extract paths or links from a container archive.
        with tempfile.TemporaryFile() as error:
            p = subprocess.Popen(['sudo','-n','docker','exec',container,'tar','-C',source,'-cf','-','.'], stdout=subprocess.PIPE, stderr=error)
            try:
                with tarfile.open(fileobj=p.stdout, mode='r|') as tar:
                    for member in tar:
                        relative = member.name.removeprefix('./')
                        name = prefix+'/'+relative
                        if not member.isfile() or not allowed(name):
                            self.excluded += 1
                            continue
                        if member.size > MAX_FILE:
                            raise RuntimeError('Oversized source file: '+name)
                        self.add(name, tar.extractfile(member).read())
                if p.wait() != 0:
                    raise RuntimeError('Source archive read failed')
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()

def known_secrets(infos):
    values = set()
    for info in infos:
        for item in info['Config'].get('Env', []):
            key, _, value = item.partition('=')
            if re.search(r'PASSWORD|PASSWD|TOKEN|SECRET|API_KEY', key, re.I):
                if key.endswith('_FILE') and value.startswith('/'):
                    value = docker('exec',info['Id'],'cat',value).decode().strip()
                if len(value) >= 4:
                    values.add(value)
        for mount in info.get('Mounts', []):
            target = mount.get('Destination','')
            if target.startswith('/run/secrets/'):
                value = docker('exec',info['Id'],'cat',target).decode().strip()
                if len(value) >= 4:
                    values.add(value)
    return values

def base_source(c):
    req = urllib.request.Request('https://codeload.github.com/UmairSeemab/ODDB/zip/'+BASE, headers={'User-Agent':'ODDB-publication-packager/28'})
    with urllib.request.urlopen(req, timeout=120) as r, tempfile.TemporaryFile() as f:
        total = 0
        while True:
            b = r.read(1024*1024)
            if not b: break
            total += len(b)
            if total > MAX_TOTAL: raise RuntimeError('Upstream source archive too large')
            f.write(b)
        f.seek(0)
        with zipfile.ZipFile(f) as z:
            for m in z.infolist():
                p = PurePosixPath(m.filename)
                name = '/'.join(p.parts[1:])
                if not name or m.is_dir(): continue
                if name.split('/')[0] in {'app','schema'} or name in {'SHA256SUMS.txt','package_manifest.json'}:
                    continue
                if m.file_size > MAX_FILE: raise RuntimeError('Upstream member too large')
                # Reject symlinks even in the public base archive.
                if ((m.external_attr >> 16) & 0o170000) == 0o120000: continue
                c.add(name, z.read(m))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path.home()/'oddb_publication')
    args = parser.parse_args()
    os.umask(0o077)
    out = args.output_dir.expanduser().resolve()
    out.mkdir(parents=True,exist_ok=True)
    web, db, visitor = [inspect(n) for n in ['oddb-production-web-1','oddb-production-db-1','oddb-visitors-23']]
    infos = [web,db,visitor]
    if not all(i['State']['Running'] for i in infos): raise RuntimeError('Expected live containers are not running')
    initial = [identity(i) for i in infos]
    secrets = known_secrets(infos)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')
    with tempfile.TemporaryDirectory(prefix='.publication-',dir=out) as work:
        root = Path(work)/'ODDB'
        root.mkdir()
        c = Collector(root,secrets)
        print('Reading the existing public source snapshot...',flush=True)
        base_source(c)
        print('Reading current web and visitor-service source...',flush=True)
        c.container_tree(web['Id'],'/srv/oddb/app','app')
        c.container_tree(visitor['Id'],'/app','services/visitors')
        c.add('tools/create_publication_28.py',Path(__file__).read_bytes())
        # The live service has no Dockerfile in /app. Include its small reproducible build recipe.
        c.add('services/visitors/Dockerfile',b'FROM python:3.12-slim\nWORKDIR /app\nCOPY analytics.py countries.json ./\nENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\nUSER 33:33\nEXPOSE 8080\nCMD ["python", "analytics.py"]\n')
        print('Reading exact table counts and base-table schema (no database rows)...',flush=True)
        data = json.loads(docker('exec','-i',web['Id'],'php',data=DB_READ.encode()))
        if not data['counts'] or not data['definitions']: raise RuntimeError('Empty schema export')
        ddl = '-- ODDB base-table schema only; no records, accounts, views, routines or events.\nSET FOREIGN_KEY_CHECKS=0;\n'
        ddl += '\n\n'.join(v+';' for v in data['definitions'].values())
        ddl += '\nSET FOREIGN_KEY_CHECKS=1;\n'
        c.add('schema/oddb_enriched_schema.sql',ddl.encode(),True)
        counts = 'table_name\trow_count\n'+''.join(f'{k}\t{v}\n' for k,v in data['counts'].items())
        c.add('schema/table_counts.tsv',counts.encode(),True)
        counts_json = json.dumps(data['counts'],indent=2)+'\n'
        c.add('schema/table_counts.json',counts_json.encode())
        readme = root/'README.md'
        if readme.exists():
            historical = readme.read_bytes()
            readme.unlink()
            c.add('docs/README_BEFORE_ENRICHMENT.md',historical)
        overview = {k:data['counts'].get(k) for k in ['disease','gene','variant','drug','clinical_trial','clinical_report','disease_gene_association','disease_drug_association']}
        doc = f'''# ODDB: Ocular Disease Database

Source: {REPO}
Website: https://www.oculardiseases.fi/

This source snapshot was exported from the running enrichment deployment at {stamp} UTC. It overlays current application source onto public repository commit `{BASE}`. No production files or database rows were modified.

## Release counts

| Entity table | Records |
| --- | ---: |
'''+''.join(f'| {k} | {v:,} |\n' for k,v in overview.items() if v is not None)+f'''
All exact base-table counts are in `schema/table_counts.tsv`. Schema definitions are in `schema/oddb_enriched_schema.sql`. Counts were read in one consistent read-only InnoDB transaction. Views omitted from this schema export: {data['views_omitted']}. Table definitions are read separately within that session; avoid concurrent DDL while packaging.

## Source layout and running

`app/` contains the current PHP/JavaScript website, including scoped Explore search, node hovers, navigation controls, current release statistics and visitor globe. `services/visitors/` contains the country-aggregate service source without visitor records or geolocation database. `retnet_pipeline/`, `ops/` and `deploy/` preserve earlier source and require the deployment updates described below.

The existing root Compose and ops files are HISTORICAL deployment examples. They do not configure the added visitor sidecar, the enriched download bind mount, or the renamed release database. Do not run them against production as an upgrade procedure. Read `docs/ENRICHMENT_PUBLICATION.md` before adapting them. The source archive alone is not a complete deployment backup.

For a local source review with PHP/PDO MySQL and a separately restored matching database:

```bash
export ODDB_DB_HOST=127.0.0.1 ODDB_DB_PORT=3306 ODDB_DB_NAME=oddb_v1
export ODDB_DB_USER=oddb_reader
read -r -s -p 'Local database password: ' ODDB_DB_PASSWORD; echo
export ODDB_DB_PASSWORD ODDB_VISITOR_MODE=preview
php -S 127.0.0.1:8081 -t app/public
```

PHP's built-in server is for local review. Bulk downloads and country lookup require separately supplied matching assets. Local visitor collection is disabled. Production requires a configured web server, trusted reverse-proxy addresses, service credentials and read-only app database access.

## Scientific interpretation

Trial investigation does not establish approval or efficacy. Shared drug targets are discovery context and are distinct from disease-specific drug evidence. RetNet imports preserve source assertions and user acceptance; this does not establish independent verification of every reference. Dataset versions and upstream redistribution rights must be documented separately.

## Publication and license

The existing MIT software license and CITATION.cff are retained. Third-party assets retain their original terms. Data are not relicensed by this source archive. Cite the final reviewed Git commit/tag and archive that exact version for the manuscript; no DOI is invented here. Review existing citation metadata and historical docs against this release before submission.

`PUBLICATION_REPORT.json` and `SHA256SUMS.txt` describe the exported source. Automated screening is a safeguard, not a guarantee that all secrets have been identified. Review before public upload.
'''
        c.add('README.md',doc.encode())
        notes = '''# Enriched deployment and publication notes

The source archive intentionally excludes full SQL data, downloadable research files, geolocation ranges, mail/database credentials, TLS keys, visitor records, raw logs, container images, runtime patch backups and private deployment state.

Keep matching data in a separately reviewed scientific archive with source attribution, version, checksums and applicable permissions. Supply all current release-catalog paths and statistics snapshots before acceptance testing. A schema-only database will not reproduce the live website data.

Deployment adaptations: web app env uses ODDB_DB_HOST, ODDB_DB_PORT, ODDB_DB_NAME, ODDB_DB_USER, ODDB_DB_PASSWORD. Configure a private mail password file if contact mail is enabled. Retain historical downloads at /srv/oddb/retnet_pipeline/releases and mount the enriched published download directory read-only at /srv/oddb/enrichment_downloads. Do not expose app/config as the document root.

Visitor service uses a private shared token (ANALYTICS_TOKEN in the sidecar and ODDB_VISITOR_TOKEN in web), /data for private aggregate/dedup SQLite and /geo for the licensed country lookup (ANALYTICS_GEO=/geo). Web uses ODDB_VISITOR_URL, ODDB_VISITOR_MODE and explicitly trusted ODDB_VISITOR_TRUSTED_PROXIES. Collection must stay off in preview. Preserve DB-IP Lite attribution and provide independently obtained country data plus import tooling before enabling country lookup. Never publish a live token or visitor SQLite file.

The earlier repository deployment files are preserved for provenance, not certified as a runnable enriched deployment. The private hosting handover contains exact runtime configuration and must stay separate from publication. Prepare and browser-test deployment adaptations on a separate host before moving DNS.

After upload, regenerate a final release/tag from the reviewed repository tree, preserve authors and license, and archive the matching permitted dataset separately. Historical checksums were replaced by the new source manifest, not presented as checksums for the current release. Browser behavior and a clean-host deployment still need review; packaging does not claim these tests passed.
'''
        c.add('docs/ENRICHMENT_PUBLICATION.md',notes.encode())
        # Tighten the inherited ignore file; a .gitignore is not a substitute for screening.
        old=(root/'.gitignore').read_text() if (root/'.gitignore').exists() else ''
        c.add('.gitignore',(old+'\n# Private runtime and data artifacts\n.env\n.env.*\n!.env.example\nsecrets/\nprivate/\nbackups/\n*.sqlite*\n*.sql.gz\n*.zip\nanalytics_data/\ngeodata/\n').encode())
        if c.blocked:
            report=out/('PUBLICATION_BLOCKED_'+stamp+'.json')
            report.write_text(json.dumps(c.blocked,indent=2)+'\n')
            raise RuntimeError('No ZIP created: likely secrets found. Review '+str(report))
        if initial != [identity(inspect(i['Id'])) for i in infos]:
            raise RuntimeError('A container changed during packaging; rerun after deployment finishes')
        report = {'repository':REPO,'base_commit':BASE,'created_utc':stamp,'production_changed':False,
                  'database_rows_included':False,'visitor_records_included':False,
                  'base_tables':len(data['counts']),'views_omitted':data['views_omitted'],
                  'overview_table_counts':overview,'excluded_files':c.excluded,
                  'credential_replacements':c.redactions,'automated_screening_passed':True,
                  'manual_review_required':True,'deployment_tested':False}
        c.add('PUBLICATION_REPORT.json',(json.dumps(report,indent=2)+'\n').encode())
        files=sorted(p for p in root.rglob('*') if p.is_file())
        manifest={p.relative_to(root).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
        c.add('package_manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
        sums=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n' for p in sorted(root.rglob('*')) if p.is_file())
        c.add('SHA256SUMS.txt',sums.encode())
        final=out/('ODDB_publication_'+stamp+'.zip')
        partial=final.with_suffix('.zip.partial')
        with zipfile.ZipFile(partial,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for p in sorted(root.rglob('*')):
                if p.is_file(): z.write(p,'ODDB/'+p.relative_to(root).as_posix())
        with zipfile.ZipFile(partial) as z:
            if z.testzip(): raise RuntimeError('ZIP validation failed')
        partial.rename(final)
        digest=hashlib.sha256(final.read_bytes()).hexdigest()
        final.with_suffix('.zip.sha256').write_text(digest+'  '+final.name+'\n')
        print(json.dumps({'publication_zip':str(final),'files':len(manifest)+2,'counts':overview,'manual_review_required':True,'production_changed':False},indent=2))

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('FAILED: '+str(error),file=sys.stderr)
        sys.exit(1)
