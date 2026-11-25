#!/usr/bin/env python3
"""Collect public metadata and bounded download checks. Never download media/ISOs."""
import argparse, concurrent.futures, hashlib, html, json, re, sys, tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, quote, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
UA='CoolCode-OpenSeed/1.0 (+https://coolcode.ca/openseed/)'
ALLOWED=('ubuntu.com','debian.org','archlinux.org','pkgbuild.com','archive.org','zenodo.org')
def safe_url(url):
 p=urlsplit(url)
 if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not p.hostname or not any(p.hostname==d or p.hostname.endswith('.'+d) for d in ALLOWED): raise ValueError('Unapproved source host or non-HTTPS URL')
 return url
class Redirects(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return super().redirect_request(req,fp,code,msg,headers,safe_url(newurl))
OPENER=build_opener(Redirects())
def request(url,cap=4_000_000,probe=False):
 headers={'User-Agent':UA,'Accept':'*/*'}
 if probe:headers['Range']='bytes=0-0'
 with OPENER.open(Request(safe_url(url),headers=headers),timeout=25) as r:
  safe_url(r.url)
  body=r.read(1 if probe else cap+1)
  if len(body)>cap:raise ValueError('Metadata exceeds the bounded response size')
  return body,r.status,r.headers.get('Content-Type','')
def json_get(url):return json.loads(request(url)[0])
class Links(HTMLParser):
 def __init__(self):super().__init__();self.urls=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':
   for key,value in attrs:
    if key=='href' and value:self.urls.append(value)
def links(data,base):
 p=Links();p.feed(data.decode('utf8',errors='replace'));return [urljoin(base,html.unescape(x)) for x in p.urls]
def torrent_metadata(raw):
 if len(raw)>4_000_000:raise ValueError('Torrent metadata too large')
 pos=0;nodes=0;info_span=None
 def parse(depth=0):
  nonlocal pos,nodes,info_span
  nodes+=1
  if depth>32 or nodes>100000 or pos>=len(raw):raise ValueError('Malformed torrent metadata')
  token=raw[pos:pos+1]
  if token==b'i':
   end=raw.find(b'e',pos);s=raw[pos+1:end]
   if end<0 or not re.fullmatch(rb'-?(0|[1-9][0-9]*)',s):raise ValueError('Malformed integer')
   pos=end+1;return int(s)
  if token in (b'l',b'd'):
   pos+=1;out=[] if token==b'l' else {}
   while pos<len(raw) and raw[pos:pos+1]!=b'e':
    if token==b'l':out.append(parse(depth+1))
    else:
     key=parse(depth+1)
     if not isinstance(key,bytes) or key in out:raise ValueError('Malformed dictionary')
     start=pos;out[key]=parse(depth+1)
     if depth==0 and key==b'info':info_span=(start,pos)
   if pos>=len(raw):raise ValueError('Unclosed container')
   pos+=1;return out
  if token.isdigit():
   end=raw.find(b':',pos)
   if end<0 or end-pos>9 or not raw[pos:end].isdigit():raise ValueError('Malformed string')
   size=int(raw[pos:end]);pos=end+1
   if pos+size>len(raw):raise ValueError('Truncated string')
   value=raw[pos:pos+size];pos+=size;return value
  raise ValueError('Not a bencoded torrent')
 root=parse()
 if pos!=len(raw) or not isinstance(root,dict) or not isinstance(root.get(b'info'),dict) or info_span is None:raise ValueError('Invalid torrent')
 info=root[b'info'];files=info.get(b'files')
 lengths=[f.get(b'length') for f in files if isinstance(f,dict)] if isinstance(files,list) else [info.get(b'length')]
 if not lengths or any(not isinstance(n,int) or n<0 for n in lengths):raise ValueError('Invalid payload sizes')
 names=['/'.join(p.decode('utf8',errors='replace') for p in f.get(b'path',[]) if isinstance(p,bytes)) for f in files] if isinstance(files,list) else [info.get(b'name',b'').decode('utf8',errors='replace')]
 return {'size_bytes':sum(lengths),'infohash':hashlib.sha1(raw[info_span[0]:info_span[1]]).hexdigest(),'file_count':len(lengths),'payload_names':names}
def check_download(item):
 try:
  body,status,ctype=request(item['download_url'],probe=item['download_kind']!='torrent')
  if 'text/html' in ctype.lower():raise ValueError('Download returned an HTML page')
  if item['download_kind']=='torrent':item.update(torrent_metadata(body))
  elif not body:raise ValueError('Download returned no bytes')
  item.update(availability='available',http_status=status,error=None)
 except HTTPError as e:item.update(availability='unavailable',http_status=e.code,error=f'HTTP {e.code}')
 except Exception as e:item.update(availability='unverified',http_status=None,error=type(e).__name__)
 return item

def checksum_lines(data):
 out=[]
 for line in data.decode('utf8',errors='replace').splitlines():
  m=re.match(r'^([0-9a-fA-F]{64})\s+[* ]?(.+)$',line)
  if m:out.append({'algorithm':'SHA-256','value':m[1].lower(),'file':m[2].strip()})
 return out

def linux_items(source,limit,now):
 raw=request(source['index'])[0];urls=links(raw,source['index']);is_arch=source.get('adapter')=='arch'
 torrents=list(dict.fromkeys(u for u in urls if urlsplit(u).path.endswith('.torrent') or is_arch and '/torrent/' in urlsplit(u).path))[:limit]
 if not torrents:raise ValueError('No official torrent links found')
 check_url=next((u for u in urls if u.endswith('sha256sums.txt')),None) if is_arch else urljoin(source['index'],source.get('checksums','SHA256SUMS'))
 checksums=[]
 if check_url:
  try:checksums=checksum_lines(request(check_url,cap=200000)[0])
  except Exception:pass
 out=[]
 for url in torrents:
  name=Path(urlsplit(url).path).name
  if is_arch:name='Arch Linux '+urlsplit(url).path.split('/')[-3]+' x86_64'
  else:name=name.removesuffix('.torrent')
  out.append({'id':source['id']+':'+hashlib.sha256(url.encode()).hexdigest()[:16],'title':name,'kind':'Linux','provider':source['name'],'source_id':source['id'],'source_url':source['source_url'],'description':'Official distribution torrent. Check the finished installer against the publisher’s checksum and signature.','download_url':url,'download_kind':'torrent','size_bytes':None,'license_label':source['license_label'],'license_url':source['license_url'],'checksum_url':check_url,'checksums':checksums,'checked_at':now,'metadata_checked_at':now})
 return out

def open_license(url,prefixes):
 if not isinstance(url,str):return False
 return any(url.replace('http://','https://',1).startswith(p) for p in prefixes)
def archive_item(identifier,config,now):
 obj=json_get('https://archive.org/metadata/'+quote(identifier,safe=''));meta=obj.get('metadata',{});license_url=meta.get('licenseurl','');license_url=license_url[0] if isinstance(license_url,list) and license_url else license_url
 if not open_license(license_url,config['open_license_prefixes']):return None
 files=obj.get('files',[]);torrent=next((f for f in files if f.get('format')=='Archive BitTorrent' and f.get('name','').endswith('.torrent')),None)
 if not torrent:return None
 title=meta.get('title',identifier);title=title[0] if isinstance(title,list) else title
 clean=re.sub('<[^>]+>',' ',str(meta.get('description','')));clean=' '.join(html.unescape(clean).split())[:400]
 checks=[]
 for f in files:
  if f.get('source')=='original' and f.get('sha1') and len(checks)<5:checks.append({'algorithm':'SHA-1 (source-published)','file':f['name'],'value':f['sha1']})
 return {'id':'ia:'+identifier,'title':str(title),'kind':'Archive media','provider':'Internet Archive','source_id':'archive','source_url':'https://archive.org/details/'+quote(identifier,safe=''),'description':clean,'download_url':'https://archive.org/download/'+quote(identifier,safe='')+'/'+quote(torrent['name'],safe=''),'download_kind':'torrent','size_bytes':None,'license_label':license_url.rstrip('/').split('creativecommons.org/')[-1],'license_url':license_url.replace('http://','https://',1),'checksums':checks,'checksum_url':'https://archive.org/metadata/'+quote(identifier,safe=''),'checked_at':now,'metadata_checked_at':now}

def zenodo_items(config,limit,now):
 out=[];seen=set()
 for query in config['queries']:
  obj=json_get('https://zenodo.org/api/records/?'+urlencode({'q':query,'size':config['rows'],'sort':'mostdownloaded'}))
  for record in obj.get('hits',{}).get('hits',[]):
   meta=record.get('metadata',{});lic=(meta.get('license') or {}).get('id');files=record.get('files',[])
   if str(record.get('id')) in seen or meta.get('access_right')!='open' or meta.get('resource_type',{}).get('type')!='dataset' or lic not in config['open_license_ids'] or not files:continue
   seen.add(str(record['id']));f=min(files,key=lambda f:f.get('size',1e99));url=f.get('links',{}).get('self','')
   try:safe_url(url)
   except ValueError:continue
   checksum=f.get('checksum','');algorithm,_,value=checksum.partition(':');source='https://zenodo.org/records/'+str(record['id'])
   out.append({'id':'zenodo:'+str(record['id']),'title':meta['title'],'kind':'Research data','provider':'Zenodo','source_id':'zenodo','source_url':source,'description':' '.join(html.unescape(re.sub('<[^>]+>',' ',meta.get('description',''))).split())[:400],'download_url':url,'download_kind':'file','download_name':f['key'],'size_bytes':f['size'],'record_size_bytes':sum(x.get('size',0) for x in files),'record_file_count':len(files),'license_label':lic.upper(),'license_url':{'cc-by-4.0':'https://creativecommons.org/licenses/by/4.0/','cc-by-3.0':'https://creativecommons.org/licenses/by/3.0/','cc-by-sa-4.0':'https://creativecommons.org/licenses/by-sa/4.0/','cc0-1.0':'https://creativecommons.org/publicdomain/zero/1.0/'}.get(lic,'https://spdx.org/licenses/'+lic+'.html'),'checksums':[{'algorithm':algorithm.upper(),'file':f['key'],'value':value}] if value else [],'checksum_url':source,'checked_at':now,'metadata_checked_at':now})
   if len(out)>=limit:return out
 return out

def collect(config,now):
 limit=config.get('max_items_per_source',12)
 if not 1<=limit<=50:raise ValueError('max_items_per_source must be between 1 and 50')
 tasks=[(s['id'],lambda s=s:linux_items(s,limit,now)) for s in config['linux']]
 tasks.append(('archive',lambda:[i for i in [archive_item(x,config['archive'],now) for x in config['archive']['ids']] if i]))
 tasks.append(('zenodo',lambda:zenodo_items(config['zenodo'],limit,now)))
 entries=[];sources=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  futures={pool.submit(fn):name for name,fn in tasks}
  for future in concurrent.futures.as_completed(futures):
   name=futures[future]
   try:
    items=future.result()
    if not items:raise ValueError('Source yielded no eligible entries')
    entries+=items;sources.append({'id':name,'state':'ok','items':len(items),'checked_at':now});print(name,len(items),flush=True)
   except Exception as exc:raise RuntimeError(f'Source {name} failed ({type(exc).__name__}); preserving the last published catalogue') from exc
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:entries=list(pool.map(check_download,entries))
 for item in entries:
  if item['download_kind']=='torrent' and item.get('payload_names'):item['checksums']=[c for c in item['checksums'] if c['file'] in item['payload_names'] or Path(c['file']).name in {Path(n).name for n in item['payload_names']}]
  item.pop('payload_names',None)
 entries.sort(key=lambda i:(i['kind'],i['title'].casefold()))
 if len({i['id'] for i in entries})!=len(entries):raise ValueError('Duplicate catalogue IDs')
 if not entries:raise ValueError('Empty catalogue')
 return {'schema':'openseed.v1','checked_at':now,'sources':sorted(sources,key=lambda x:x['id']),'items':entries}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,default=ROOT/'config/sources.json');args=parser.parse_args()
 now=datetime.now(timezone.utc).isoformat().replace('+00:00','Z');data=collect(json.loads(args.config.read_text()),now)
 dest=ROOT/'web/data/catalogue.json';dest.parent.mkdir(exist_ok=True,parents=True)
 with tempfile.NamedTemporaryFile('w',dir=dest.parent,delete=False,encoding='utf8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');stage=Path(f.name)
 stage.replace(dest);print(json.dumps({'items':len(data['items']),'available':sum(i['availability']=='available' for i in data['items']),'checked_at':now}))
if __name__=='__main__':main()
