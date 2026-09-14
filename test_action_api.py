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
  edit=dict(folder='genuine',uuid='fixture',filename='fixture.jpg',changes={'lighting':'office-white'},expected=row)
  assert post('/api/edit-capture',edit,'wrong')[0]==403
  assert post('/api/edit-capture',edit)[0]==200
  with urllib.request.urlopen(base+'/api/ingestion') as r:updated=json.load(r)
  assert next(e for e in updated['events'] if e['uuid']=='fixture')['lighting']=='office-white'
  assert updated['actions'][0]['action']=='modified'
  assert post('/api/edit-capture',edit)[0]==409
  item=dict(folder='genuine',uuid='fixture',filename='fixture.jpg',key='genuine/fixture/fixture.jpg')
  assert post('/api/apply-decisions',dict(confirm_count=1,remove=[item]))[0]==200
  actions=[json.loads(line) for line in (root/'actions.jsonl').read_text().splitlines()]
  assert [a['action'] for a in actions]==['modified','deleted']
  assert actions[0]['changes']=={'lighting':{'from':'dark','to':'office-white'}}
  with urllib.request.urlopen(base+'/api/ingestion') as r:data=json.load(r)
  assert data['action_total']==2
  print('PASS real HTTP edit/delete -> physical actions log; bad PIN and stale edit produce no action entries. Disposable data only.')
 finally:proc.terminate();proc.wait()
