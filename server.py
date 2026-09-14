import ast,csv,json,mimetypes,os,threading,hmac
from delete_capture import delete_capture
from ingestion import IngestionLog, with_current_metadata
from edit_capture import edit_capture, Conflict
from quality_reviews import read_reviews, save_review
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
ROOT=Path(os.environ.get('DATA_ROOT','/data')).resolve()
MATRIX_NAME='internal_colour_print_enhancement_2'
MATRIX_PATH=ROOT/(MATRIX_NAME+'.csv')
BATCHES_PATH=ROOT/(MATRIX_NAME+'_batches.csv')
DELETE_LOCK=threading.Lock()
DELETE_TOKEN=Path('/run/secrets/delete_token').read_text().strip()
assert DELETE_TOKEN, 'Deletion PIN must not be empty'
def collection_annotation(folder,uuid):
 p=folder/'mykadfront/datacollector_annotation'/(uuid+'.json')
 try:return json.loads(p.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):return {}
def records():
 out=[]
 for folder in sorted(ROOT.iterdir()):
  p=folder/'index_annotation_.csv'
  if folder.name in {'test','webcam_genuine','webcam_replay','capture_viewer'} or not p.is_file():continue
  with p.open(newline='',encoding='utf-8-sig') as f:
   for line,r in enumerate(csv.DictReader(f),2):
    cap=r.get('capture_device','').strip();raw=r.get('input_sensor','')
    if cap:sdk,device='web',cap
    else:
     sdk='app'
     try:
      d=ast.literal_eval(raw);device=d.get('model','unknown') if isinstance(d,dict) else raw
     except (ValueError,SyntaxError):device=raw.split(',')[0].removeprefix('model:')
    annotation=collection_annotation(folder,r.get('uuid',''))
    out.append(dict(key=folder.name+'/'+r.get('uuid','')+'/'+r.get('filename',''),folder=folder.name,line=line,sdk=sdk,device=device,annotation_lighting=annotation.get('lighting',''),metadata=r))
 return out
def matrix():
 with MATRIX_PATH.open(newline='',encoding='utf-8-sig') as f:
  return [r for r in csv.DictReader(f) if r.get('matrix_name')==MATRIX_NAME]
def batches():
 with BATCHES_PATH.open(newline='',encoding='utf-8-sig') as f:
  return list(csv.DictReader(f))
INGESTION=IngestionLog(ROOT, os.environ.get('INGESTION_DB','/state/ingestion.sqlite'), DELETE_LOCK, '/logs/ingestion.jsonl')
INGESTION.start()
QUALITY_PATH=INGESTION.log_path.with_name('quality_reviews.json')
class Handler(BaseHTTPRequestHandler):
 def send(self,data,kind='application/json',status=200):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  try:
   u=urlparse(self.path);q=parse_qs(u.query)
   if u.path=='/':return self.send(Path('/app/index.html').read_bytes(),'text/html; charset=utf-8')
   if u.path=='/image_zoom.js':return self.send(Path('/app/image_zoom.js').read_bytes(),'text/javascript; charset=utf-8')
   if u.path=='/frozen_panes.css':return self.send(Path('/app/frozen_panes.css').read_bytes(),'text/css; charset=utf-8')
   if u.path=='/terminal.css':return self.send(Path('/app/terminal.css').read_bytes(),'text/css; charset=utf-8')
   if u.path=='/quality.html':return self.send(Path('/app/quality.html').read_bytes(),'text/html; charset=utf-8')
   if u.path=='/api/quality':
    with DELETE_LOCK:reviews=read_reviews(QUALITY_PATH)
    return self.send(json.dumps(reviews).encode())
   if u.path=='/health':return self.send(b'{"ok":true}')
   if u.path=='/search.html':return self.send(Path('/app/search.html').read_bytes(),'text/html; charset=utf-8')
   if u.path=='/capture_review.js':return self.send(Path('/app/capture_review.js').read_bytes(),'text/javascript; charset=utf-8')
   if u.path=='/api/search':
    term=q.get('q',[''])[0].strip().lower()
    if not term or len(term)>200:return self.send(b'Enter an image ID or filename (up to 200 characters)','text/plain',400)
    matches=[r for r in records() if term in r['metadata'].get('uuid','').lower() or term in r['metadata'].get('filename','').lower()]
    return self.send(json.dumps({'total':len(matches),'results':matches[:100]}).encode())
   if u.path=='/api/captures':return self.send(json.dumps(records()).encode())
   if u.path=='/api/matrix':return self.send(json.dumps(matrix()).encode())
   if u.path=='/ingestion.html':return self.send(Path('/app/ingestion.html').read_bytes(),'text/html; charset=utf-8')
   if u.path=='/api/ingestion':
    try:
     limit=max(1,min(500,int(q.get('limit',['100'])[0])));before=int(q['before'][0]) if 'before' in q else None
    except ValueError:return self.send(b'Invalid pagination','text/plain',400)
    with DELETE_LOCK:
     result=with_current_metadata(INGESTION.snapshot(limit,before), records())
    return self.send(json.dumps(result).encode())
   if u.path=='/api/batches':return self.send(json.dumps(batches()).encode())
   if u.path=='/coverage.html':return self.send(Path('/app/coverage.html').read_bytes(),'text/html; charset=utf-8')
   if u.path not in ('/api/image','/api/annotation','/api/capture'):return self.send(b'Not found','text/plain',404)
   r=next((r for r in records() if r['key']==q.get('key',[''])[0]),None)
   if r is None:return self.send(b'Capture not found','text/plain',404)
   if u.path=='/api/capture':return self.send(json.dumps(r).encode())
   folder=(ROOT/r['folder']).resolve()
   if u.path=='/api/image':p=folder/r['metadata'].get('ori_path','')
   else:p=folder/'mykadfront/datacollector_annotation'/(r['metadata']['uuid']+'.json')
   p=p.resolve()
   if not p.is_relative_to(folder) or not p.is_file():return self.send(b'File not found','text/plain',404)
   self.send(p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
  except Exception as e:
   print(type(e).__name__,str(e),flush=True);self.send(b'Request failed','text/plain',500)
 def do_POST(self):
  try:
   if urlparse(self.path).path not in ('/api/apply-decisions','/api/edit-capture','/api/quality'):return self.send(b'Not found','text/plain',404)
   if not hmac.compare_digest(self.headers.get('X-Delete-Token',''),DELETE_TOKEN):return self.send(b'Invalid deletion PIN','text/plain',403)
   size=int(self.headers.get('Content-Length','0'))
   if size<1 or size>1048576:return self.send(b'Invalid request size','text/plain',400)
   request=json.loads(self.rfile.read(size))
   if urlparse(self.path).path=='/api/quality':
    with DELETE_LOCK:
     row=next((r for r in records() if r['key']==request.get('key')),None)
     if row is None:return self.send(b'Capture no longer exists','text/plain',409)
     result=save_review(QUALITY_PATH,row,request.get('status'),request.get('notes',''),request.get('expected'),ROOT)
    return self.send(json.dumps(result).encode())
   if urlparse(self.path).path=='/api/edit-capture':
    with DELETE_LOCK:
     result=edit_capture(ROOT,request.get('folder',''),request.get('uuid',''),request.get('filename',''),request.get('changes'),request.get('expected'))
     changes={k:{'from':request['expected'].get(k,''),'to':v} for k,v in request['changes'].items()}
     INGESTION.record_action('modified',request['folder'],request['uuid'],request['filename'],changes)
    return self.send(json.dumps(result).encode())
   items=request.get('remove',[])
   if not isinstance(items,list) or not items or len(items)>500:return self.send(b'No valid remove decisions','text/plain',400)
   if request.get('confirm_count')!=len(items):return self.send(b'Confirmation count does not match','text/plain',400)
   keys=[item.get('key','') for item in items]
   if len(keys)!=len(set(keys)):return self.send(b'Duplicate decisions are not allowed','text/plain',400)
   with DELETE_LOCK:
    current={r['key']:r for r in records()}
    for item in items:
     folder=item.get('folder','');uuid=item.get('uuid','');filename=item.get('filename','');expected=folder+'/'+uuid+'/'+filename
     if item.get('key')!=expected or expected not in current:return self.send(b'A selected capture changed or is missing; refresh and review again','text/plain',409)
    results=[]
    for item in items:
     results.append(delete_capture(ROOT,item['folder'],item['uuid'],item['filename']))
     INGESTION.record_action('deleted',item['folder'],item['uuid'],item['filename'])
   return self.send(json.dumps({'deleted':len(results),'results':results}).encode())
  except Conflict as e:return self.send(str(e).encode(),'text/plain',409)
  except (ValueError,json.JSONDecodeError) as e:return self.send(str(e).encode(),'text/plain',400)
  except Exception as e:
   print(type(e).__name__,str(e),flush=True);return self.send(b'Batch deletion failed; refresh before retrying','text/plain',500)
ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
