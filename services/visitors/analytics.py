"""Country-only site analytics. No request/IP/URL logs and no research DB access."""
import csv,gzip,hashlib,hmac,ipaddress,json,os,re,secrets,sqlite3,time
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(os.getenv('ANALYTICS_DATA','/data'))
COUNTRIES=json.loads((Path(__file__).parent/'countries.json').read_text())
PAGES={'index.php','explore.php','statistics.php','documentation.php','data.php','contact.php'}
BOTS=re.compile(r'bot|spider|crawler|headless|curl|wget|python|monitor|uptime|preview',re.I)

def connect():
 db=sqlite3.connect(ROOT/'visitors.sqlite',timeout=3)
 db.execute('PRAGMA journal_mode=WAL');return db

def init():
 ROOT.mkdir(parents=True,exist_ok=True)
 with connect() as db:
  db.executescript('''CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT);
  CREATE TABLE IF NOT EXISTS daily(day TEXT,country TEXT,views INTEGER NOT NULL,visitors INTEGER NOT NULL,PRIMARY KEY(day,country));
  CREATE TABLE IF NOT EXISTS seen(day TEXT,token TEXT,PRIMARY KEY(day,token));
  CREATE TABLE IF NOT EXISTS recent(token TEXT,page TEXT,at REAL,PRIMARY KEY(token,page));''')

def address(value):
 try:
  ip=ipaddress.ip_address(value)
  if isinstance(ip,ipaddress.IPv6Address) and ip.ipv4_mapped:ip=ip.ipv4_mapped
  return ip
 except ValueError:return None

def country(value):
 ip=address(value)
 if ip is None or not ip.is_global:return 'ZZ'
 geo=Path(os.getenv('ANALYTICS_GEO',str(ROOT)))/'geo.sqlite'
 if not geo.exists():return 'ZZ'
 # IPv4 and IPv6 occupy separate indexed namespaces.
 key=f'{int(ip):032x}'
 with sqlite3.connect(f'file:{geo}?mode=ro',uri=True) as db:
  row=db.execute('SELECT end,country FROM ranges WHERE family=? AND start<=? ORDER BY start DESC LIMIT 1',(ip.version,key)).fetchone()
 return row[1] if row and key<=row[0] and re.fullmatch('[A-Z]{2}',row[1]) else 'ZZ'

def record(ip,ua,page,enabled,now=None):
 now=time.time() if now is None else now
 day=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m-%d')
 code=country(ip)
 if not enabled or page not in PAGES or BOTS.search(ua) or not ua:return code
 # Transient IP is used only for a daily HMAC. Delete prior-day keys/tokens.
 # IP+UA is an estimate, not a count of identifiable people.
 with connect() as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute("SELECT v FROM meta WHERE k='key_day'").fetchone()
  if not row or row[0]!=day:
   db.execute('DELETE FROM seen');db.execute('DELETE FROM recent')
   for k,v in [('key_day',day),('daily_key',secrets.token_hex(32))]:db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(k,v))
  key=db.execute("SELECT v FROM meta WHERE k='daily_key'").fetchone()[0]
  token=hmac.new(key.encode(),(str(address(ip) or '')+'|'+ua[:256]).encode(),hashlib.sha256).hexdigest()
  last=db.execute('SELECT at FROM recent WHERE token=? AND page=?',(token,page)).fetchone()
  if last and now-last[0]<10:return code
  db.execute('INSERT OR REPLACE INTO recent VALUES (?,?,?)',(token,page,now))
  fresh=db.execute('INSERT OR IGNORE INTO seen VALUES (?,?)',(day,token)).rowcount
  db.execute('INSERT INTO daily VALUES (?,?,1,?) ON CONFLICT(day,country) DO UPDATE SET views=views+1,visitors=visitors+excluded.visitors',(day,code,fresh))
  db.execute("INSERT OR IGNORE INTO meta VALUES ('started_utc',?)",(datetime.fromtimestamp(now,timezone.utc).isoformat(),))
 return code

def summary(ip,enabled):
 day=datetime.now(timezone.utc).strftime('%Y-%m-%d')
 with connect() as db:
  rows=db.execute('SELECT country,SUM(views),SUM(visitors),SUM(CASE WHEN day=? THEN visitors ELSE 0 END) FROM daily GROUP BY country ORDER BY SUM(views) DESC,country',(day,)).fetchall()
  started=db.execute("SELECT v FROM meta WHERE k='started_utc'").fetchone()
 result=[]
 for code,views,visitors,today in rows:
  result.append({'code':code,'name':COUNTRIES.get(code,{}).get('name',code if code!='ZZ' else 'Unknown country'),'page_views':views,'visitor_days':visitors,'visitors_today':today})
 code=country(ip)
 return {'ok':True,'collection_enabled':enabled,'started_utc':started[0] if started else None,'day_utc':day,'your_country':code,'your_country_name':COUNTRIES.get(code,{}).get('name',code if code!='ZZ' else 'Unknown'),'total_page_views':sum(r['page_views'] for r in result),'estimated_visitors_today':sum(r['visitors_today'] for r in result),'countries_reached':sum(r['code']!='ZZ' for r in result),'countries':result}

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+os.environ['ANALYTICS_TOKEN']):self.send_error(403);return
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=2048:raise ValueError()
   data=json.loads(self.rfile.read(n));ip=str(data.get('ip',''))[:64]
   enabled=data.get('mode')=='production'
   if self.path=='/event':record(ip,str(data.get('ua',''))[:256],data.get('page',''),enabled)
   elif self.path!='/stats':self.send_error(404);return
   body=json.dumps(summary(ip,enabled)).encode()
   self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  except (ValueError,TypeError,sqlite3.Error,OSError):self.send_error(503)

if __name__=='__main__':
 os.umask(0o077);init();ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
