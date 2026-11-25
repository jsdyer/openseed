import importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('refresh',ROOT/'scripts/refresh.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
def encode(v):
 if isinstance(v,bytes):return str(len(v)).encode()+b':'+v
 if isinstance(v,int):return b'i'+str(v).encode()+b'e'
 if isinstance(v,list):return b'l'+b''.join(encode(x)for x in v)+b'e'
 return b'd'+b''.join(encode(k)+encode(v[k])for k in sorted(v))+b'e'
class RefreshTests(unittest.TestCase):
 def test_torrent_sizes_and_infohash(self):
  info={b'name':b'linux.iso',b'length':1024,b'piece length':256,b'pieces':b'a'*80};raw=encode({b'info':info});data=r.torrent_metadata(raw)
  import hashlib
  self.assertEqual(data['size_bytes'],1024);self.assertEqual(data['infohash'],hashlib.sha1(encode(info)).hexdigest())
 def test_multifile_and_malformed(self):
  raw=encode({b'info':{b'name':b'film',b'files':[{b'path':[b'a.mp4'],b'length':12},{b'path':[b'b.txt'],b'length':3}]}})
  self.assertEqual(r.torrent_metadata(raw)['size_bytes'],15)
  for data in [b'<html>Forbidden</html>',b'd4:info',encode({b'info':{b'length':-1}}),b'l'*40+b'e'*40]:
   with self.assertRaises(ValueError):r.torrent_metadata(data)
 def test_download_404_is_not_reported_as_available(self):
  item={'download_url':'https://archive.org/download/a/a.torrent','download_kind':'torrent'}
  with patch.object(r,'request',side_effect=r.HTTPError(item['download_url'],404,'not found',None,None)):
   self.assertEqual(r.check_download(item)['availability'],'unavailable');self.assertEqual(item['http_status'],404)
 def test_html_download_is_rejected(self):
  with patch.object(r,'request',return_value=(b'<html>',200,'text/html')):
   self.assertEqual(r.check_download({'download_url':'https://zenodo.org/x','download_kind':'file'})['availability'],'unverified')
 def test_source_hosts_and_https_only(self):
  self.assertEqual(r.safe_url('https://releases.ubuntu.com/'),'https://releases.ubuntu.com/')
  for u in ['http://archive.org/','https://archive.org.attacker.test/','https://user:pass@archive.org/','https://127.0.0.1/','https://archive.org:444/','file:///etc/passwd']:
   with self.assertRaises(ValueError):r.safe_url(u)
 def test_open_licenses_only(self):
  prefixes=['https://creativecommons.org/licenses/by/']
  self.assertTrue(r.open_license('http://creativecommons.org/licenses/by/4.0/',prefixes))
  self.assertFalse(r.open_license('https://creativecommons.org/licenses/by-nc/4.0/',prefixes))
 def test_duplicate_listing_links_are_deduplicated_and_checksum_matches(self):
  source={'id':'test','name':'Test','index':'https://releases.ubuntu.com/test/','source_url':'https://ubuntu.com/','license_url':'https://ubuntu.com/legal','license_label':'packages'}
  with patch.object(r,'request',side_effect=[(b'<a href="x.iso.torrent">a</a><a href="x.iso.torrent">b</a>',200,'text/html'),(b'a'*64+b' *x.iso\n',200,'text/plain')]):
   rows=r.linux_items(source,12,'2026-11-25T12:00:00Z');self.assertEqual(len(rows),1);self.assertEqual(rows[0]['checksums'][0]['file'],'x.iso')
 def test_source_failure_does_not_overwrite_saved_catalogue(self):
  before=(ROOT/'web/data/catalogue.json').read_bytes();config=json.loads((ROOT/'config/sources.json').read_text())
  with patch.object(r,'linux_items',side_effect=RuntimeError('offline')),patch.object(r,'archive_item',return_value=None),patch.object(r,'zenodo_items',return_value=[]):
   with self.assertRaises(RuntimeError):r.collect(config,'2026-11-25T12:00:00Z')
  self.assertEqual((ROOT/'web/data/catalogue.json').read_bytes(),before)
if __name__=='__main__':unittest.main()
