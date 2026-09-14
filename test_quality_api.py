"""Exercise the real HTTP handlers with disposable files and a temporary server."""
import csv,json,os,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
src=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);folder=root/'genuine';folder.mkdir();pin=root/'pin';pin.write_text('fixture')
 row=dict(uuid='fixture',filename='fixture.jpg',subject='fixture',lighting='dark',capture_device='iphone-13',input_sensor='',ori_path='mykadfront/orig/fixture.jpg',ocr_path='mykadfront/crop/fixture.png')
 for name in ['index_annotation_.csv','index_annotation_mykadfront.csv']:
  with (folder/name).open('w',newline='') as f:
   secondary={k:row[k] for k in ['uuid','ori_path','ocr_path']} if name=='index_annotation_mykadfront.csv' else row
   w=csv.DictWriter(f,fieldnames=secondary);w.writeheader();w.writerow(secondary)
 for field in ['ori_path','ocr_path']:
  path=folder/row[field];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
 server=root/'server.py';server.write_text((src/'server.py').read_text().replace("'/run/secrets/delete_token'",repr(str(pin))).replace("'/logs/ingestion.jsonl'",repr(str(root/'ingestion.jsonl'))).replace("('0.0.0.0',8080)","('127.0.0.1',18770)"))
 proc=subprocess.Popen(['python3',str(server)],env={**os.environ,'DATA_ROOT':str(root),'INGESTION_DB':str(root/'history.sqlite'),'PYTHONPATH':str(src)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 base='http://127.0.0.1:18770'
 try:
  for _ in range(50):
   try:urllib.request.urlopen(base+'/health');break
   except OSError:time.sleep(.1)
  def post(path,payload,token='fixture'):
   request=urllib.request.Request(base+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Delete-Token':token})
   try:
    with urllib.request.urlopen(request) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,e.read().decode()
  key='genuine/fixture/fixture.jpg'
  payload=dict(key=key,status='error',notes='Glare across text',expected=None)
  assert post('/api/quality',payload,'wrong')[0]==403
  assert not (root/'quality_reviews.json').exists()
  assert post('/api/quality',{**payload,'status':'invalid'})[0]==400
  assert post('/api/quality',{**payload,'key':'genuine/missing/missing.jpg'})[0]==409
  status,result=post('/api/quality',payload);assert status==200,(status,result)
  assert result['status']=='error' and result['notes']=='Glare across text'
  for name in ['index_annotation_.csv','index_annotation_mykadfront.csv']:
   with (folder/name).open() as stream:assert next(csv.DictReader(stream))['quality_review_status']=='fail'
  assert post('/api/quality',payload)[0]==409
  with urllib.request.urlopen(base+'/api/quality') as response:assert json.load(response)[key]==result
  stored=json.loads((root/'quality_reviews.json').read_text());assert stored[key]==result
  status,result=post('/api/quality',dict(key=key,status='pass',notes='Checked again',expected=result));assert status==200
  for name in ['index_annotation_.csv','index_annotation_mykadfront.csv']:
   with (folder/name).open() as stream:assert next(csv.DictReader(stream))['quality_review_status']=='pass'
  assert (folder/row['ori_path']).read_bytes()==b'fixture'
  proc.terminate();proc.wait()
  proc=subprocess.Popen(['python3',str(server)],env={**os.environ,'DATA_ROOT':str(root),'INGESTION_DB':str(root/'history.sqlite'),'PYTHONPATH':str(src)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(50):
   try:
    with urllib.request.urlopen(base+'/api/quality') as response:assert json.load(response)[key]['status']=='pass'
    break
   except OSError:time.sleep(.1)
  else:raise AssertionError('Restart failed')
  print('PASS quality API: PIN, missing capture, invalid status, conflicts, physical persistence, server restart, and pass/error transitions.')

 finally:proc.terminate();proc.wait()
