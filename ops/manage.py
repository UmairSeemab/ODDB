#!/usr/bin/env python3
"""Operate only the ODDB Compose project in this package. Python 3.9+."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DATABASE = 'oddb_v1'
REPORT_REVISION = '0.8.8'
VIEW_DEFINER = re.compile(rb'^/\*!50013 DEFINER=`root`@`localhost` SQL SECURITY (?:DEFINER|INVOKER) \*/;?\r?\n?$')
VIEW_OTHER = re.compile(rb'\bDEFINER\s*=|\bSQL\s+SECURITY\s+DEFINER\b', re.I)

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def write(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(mode)

def environment():
    excluded = {'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'COMPOSE_PROFILES', 'ODDB_ROOT_PASSWORD', 'ODDB_WEB_PASSWORD', 'ODDB_DOMAIN', 'ODDB_WWW_DOMAIN', 'ODDB_LOCAL_PORT'}
    return {key: value for key, value in os.environ.items() if key not in excluded}

def run(command, capture=False):
    result = subprocess.run(command, cwd=ROOT, env=environment(), text=True, capture_output=capture)
    if result.returncode:
        # No command arguments, process stderr or authentication values in errors.
        raise ValueError('Docker operation failed. Inspect this project\'s container logs locally.')
    return result.stdout if capture else ''

def config():
    return json.loads((ROOT / 'schema/deployment.json').read_text())

def env_values():
    values = {}
    for line in (ROOT / '.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key] = value
    if not all(re.fullmatch(r'[a-f0-9]{64}', values.get(key, '')) for key in ['ODDB_ROOT_PASSWORD', 'ODDB_WEB_PASSWORD']):
        raise ValueError('Expected generated 64-character hex passwords. Run init in a fresh package.')
    return values

def base_command():
    env_values()
    return ['docker', 'compose', '--env-file', str(ROOT / '.env'), '-p', 'oddb-production', '-f', str(ROOT / 'compose.yaml')]

def db_command(base, user='root'):
    if user == 'root':
        shell = 'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb --no-defaults --user=root --default-character-set=utf8mb4 --batch --raw --skip-column-names --database=oddb_v1 "$@"'
        return [*base, 'exec', '-T', 'db', 'sh', '-c', shell, 'oddb-client']
    shell = 'exec php -r \'$p=new PDO("mysql:host=db;dbname=oddb_v1;charset=utf8mb4","oddb_web",getenv("ODDB_DB_PASSWORD"),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);$p->query($argv[1]);echo "OK";\' "$@"'
    return [*base, 'exec', '-T', 'web', 'sh', '-c', shell, 'oddb-client']

def query(base, sql):
    return run([*db_command(base), '--execute=' + sql], capture=True).strip()

def quoted(value):
    return '`' + value.replace('`', '``') + '`'

def init():
    if (ROOT / '.env').exists() or (ROOT / 'secrets').exists():
        raise ValueError('Credentials already exist. They were not overwritten.')
    root_pw, web_pw = secrets.token_hex(32), secrets.token_hex(32)
    ROOT.chmod(0o700)
    write(ROOT / '.env', 'ODDB_ROOT_PASSWORD=' + root_pw + '\nODDB_WEB_PASSWORD=' + web_pw + '\nODDB_DOMAIN=oculardiseases.fi\nODDB_WWW_DOMAIN=www.oculardiseases.fi\nODDB_LOCAL_PORT=8082\n')
    (ROOT / 'secrets').mkdir(mode=0o700)
    # Entrypoint drops privileges to mysql before sourcing SQL. File is readable
    # in-container; the containing host directory and package remain private.
    write(ROOT / 'secrets/01-web-user.sql', "CREATE USER 'oddb_web'@'%' IDENTIFIED BY '" + web_pw + "';\nGRANT SELECT ON `oddb_v1`.* TO 'oddb_web'@'%';\n", 0o644)
    (ROOT / 'runtime').mkdir(mode=0o700, exist_ok=True)
    print('Generated private credentials. No containers were started.')

def check_releases():
    inventory = json.loads((ROOT / 'retnet_pipeline/releases/release_inventory.json').read_text())
    catalog = json.loads((ROOT / 'app/config/release_catalog.json').read_text())
    entries = inventory['files']
    if not entries or len(entries) != len(catalog['files']):
        raise ValueError('Release inventory and catalog disagree.')
    indexed = {item['id']: item for item in entries}
    for item in catalog['files']:
        expected = indexed.get(item['id'])
        if expected is None or expected['relative_path'] != item['relative_path'] or expected['size_bytes'] != item['size_bytes']:
            raise ValueError('Release catalog changed since packaging.')
        relative = Path(item['relative_path'])
        path = ROOT / relative
        if relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(ROOT / 'retnet_pipeline/releases') or path.is_symlink() or not path.is_file():
            raise ValueError('Missing or invalid release data: ' + relative.as_posix())
        if path.stat().st_size != item['size_bytes'] or sha(path) != expected['sha256']:
            raise ValueError('Release data checksum mismatch: ' + relative.as_posix())
    print('All release file sizes and checksums passed:', len(entries))

def import_dump(base, settings):
    dump = ROOT / 'database/oddb_v1_full.sql.gz'
    if sha(dump) != settings['backup_sha256']:
        raise ValueError('Full backup checksum mismatch.')
    schema_gz = ROOT / 'database/oddb_v1_schema.sql.gz'
    if sha(schema_gz) != settings['schema_sha256']:
        raise ValueError('Original schema checksum mismatch.')
    objects = int(query(base, 'SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE();'))
    if objects:
        raise ValueError('Database is nonempty. Import refused. A partial import is retained for investigation.')
    # Preflight before writing anything to MariaDB.
    changed = 0
    with gzip.open(dump, 'rb') as stream:
        for line in stream:
            if VIEW_DEFINER.fullmatch(line):
                changed += 1
            elif VIEW_OTHER.search(line) and not re.match(rb'^\s*(?:INSERT|REPLACE)\b', line, re.I):
                raise ValueError('Unsupported database definer clause. No SQL was imported.')
            if re.match(rb'^\s*(?:CREATE DATABASE|USE\s)', line, re.I):
                raise ValueError('Expected a single-database dump without CREATE DATABASE/USE statements.')
    if changed != len(settings['expected_schema']['views']):
        raise ValueError('Unexpected view definition count. No SQL was imported.')
    log = ROOT / 'runtime/restore.log'
    log.touch(mode=0o600, exist_ok=False)
    process = None
    with log.open('wb') as output:
        try:
            process = subprocess.Popen(db_command(base), cwd=ROOT, env=environment(), stdin=subprocess.PIPE, stdout=output, stderr=output)
            with gzip.open(dump, 'rb') as stream:
                for line in stream:
                    process.stdin.write(b'/*!50013 SQL SECURITY INVOKER */\n' if VIEW_DEFINER.fullmatch(line) else line)
            process.stdin.close()
            status = process.wait()
            if status:
                raise ValueError('Import failed. Inspect runtime/restore.log locally. Existing imported data was retained.')
        except BrokenPipeError:
            raise ValueError('Import stopped. Inspect runtime/restore.log locally. Existing imported data was retained.')
        finally:
            if process is not None:
                if process.stdin and not process.stdin.closed:
                    try:
                        process.stdin.close()
                    except BrokenPipeError:
                        pass
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
    write(ROOT / 'runtime/import_complete.json', json.dumps({'backup_sha256': settings['backup_sha256'], 'views_adjusted': changed, 'imported_at_utc': datetime.now(timezone.utc).isoformat()}, indent=2))

def require_marker(settings):
    marker = ROOT / 'runtime/import_complete.json'
    if not marker.is_file() or json.loads(marker.read_text()).get('backup_sha256') != settings['backup_sha256']:
        raise ValueError('A matching completed import marker is required. Run restore first.')

def verify(base, settings):
    require_marker(settings)
    check_releases()
    from validation import verify_database
    verify_database(ROOT, base, settings, query, run, db_command, write)
    report_file = ROOT / 'runtime/verification_report.json'
    report = json.loads(report_file.read_text())
    port = int(env_values().get('ODDB_LOCAL_PORT', '8082'))
    checks = {}
    try:
        for route in ['', 'api/stats.php', 'api/release.php']:
            for attempt in range(15 if not route else 1):
                try:
                    with urlopen('http://127.0.0.1:' + str(port) + '/' + route, timeout=180 if route else 10) as response:
                        body, status = response.read(), response.status
                    if route and json.loads(body).get('ok') is not True:
                        raise ValueError('API returned ok=false.')
                    checks[route or 'Home'] = {'status': status, 'bytes': len(body)}
                    break
                except Exception:
                    if attempt == (14 if not route else 0):
                        raise ValueError('HTTP check failed for ' + (route or 'Home'))
                    time.sleep(2)
    except ValueError as error:
        report['issues'].append(str(error)); report['passed'] = False
        raise
    finally:
        report['http_checks'] = checks
        write(report_file, json.dumps(report, indent=2))
    print('Database, PHP, release and HTTP checks passed. Browser acceptance is still separate.')

def restore(base, settings):
    check_releases()
    run([*base, 'up', '-d', '--wait', '--wait-timeout', '300', 'db'])
    marker = ROOT / 'runtime/import_complete.json'
    if marker.is_file():
        require_marker(settings)
        print('Using the completed import. No database data is overwritten.')
    else:
        import_dump(base, settings)
    run([*base, 'up', '-d', '--build', 'web'])
    verify(base, settings)
    print('Local test URL: http://127.0.0.1:' + env_values().get('ODDB_LOCAL_PORT', '8082') + '/')

def backup(base):
    backup_dir = ROOT / 'backups'
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    backup_dir.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = backup_dir / ('oddb_v1_' + stamp + '.sql.gz')
    shell = 'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb-dump --no-defaults --user=root --single-transaction --quick --routines --triggers --skip-events --hex-blob --default-character-set=utf8mb4 oddb_v1'
    # A restored schema with no routines/events may later change; never omit
    # events from a backup silently. Verify the empty event inventory first.
    if int(query(base, 'SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA=DATABASE();')):
        raise ValueError('Events exist. Review backup options before exporting.')
    before = {table: int(query(base, 'SELECT COUNT(*) FROM ' + quoted(table) + ';')) for table in config()['expected_schema']['tables']}
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    log = backup_dir / (stamp + '.log')
    log.touch(mode=0o600, exist_ok=False)
    try:
        with os.fdopen(fd, 'wb') as raw, log.open('wb') as error:
            process = subprocess.Popen([*base, 'exec', '-T', 'db', 'sh', '-c', shell], cwd=ROOT, env=environment(), stdout=subprocess.PIPE, stderr=error)
            try:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw) as compressed:
                    for block in iter(lambda: process.stdout.read(1024 * 1024), b''):
                        compressed.write(block)
                status = process.wait()
                if status:
                    raise ValueError('Backup failed. Inspect its local log.')
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=10)
        write(target.with_suffix('.counts.json'), json.dumps({'counts_before_dump': before, 'count_snapshot_note': 'Counts are measured before the dump; pause writes for exact equivalence.'}, indent=2))
        write(target.with_name(target.name + '.sha256'), sha(target) + '  ' + target.name + '\n')
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    print('Backup created:', target)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'restore', 'verify', 'publish', 'backup', 'stop'])
    args = parser.parse_args()
    if args.action == 'init':
        init(); return
    base = base_command()
    run(['docker', 'info'], capture=True)
    run([*base, 'config', '--quiet'], capture=True)
    settings = config()
    if args.action == 'restore':
        restore(base, settings)
    elif args.action == 'verify':
        verify(base, settings)
    elif args.action == 'publish':
        verify(base, settings)
        run([*base, '--profile', 'public', 'up', '-d', 'proxy'])
        print('Public proxy started. Verify DNS and HTTPS for both domain names.')
    elif args.action == 'backup':
        require_marker(settings); backup(base)
    else:
        run([*base, '--profile', 'public', 'stop'])
        print('This project stopped. All database and certificate volumes are retained.')

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print('Operation stopped:', error, file=sys.stderr)
        sys.exit(1)
