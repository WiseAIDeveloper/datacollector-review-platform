import csv
import io
from pathlib import Path
from delete_capture import atomic_write, INDEXES, SAFE_FOLDER

FIELDS={'subject','lighting','capture_device','input_sensor','user'}
class Conflict(ValueError):
    pass

def edit_capture(root,folder_name,uuid,filename,changes,expected,*,allowed_fields=FIELDS):
    root=Path(root).resolve()
    if not isinstance(folder_name,str) or not SAFE_FOLDER.fullmatch(folder_name):raise ValueError('Invalid folder')
    folder=(root/folder_name).resolve()
    if folder.parent!=root or folder_name in {'test','webcam_genuine','webcam_replay','capture_viewer'}:raise ValueError('Invalid folder')
    if not isinstance(changes,dict) or not changes or not set(changes)<=allowed_fields:raise ValueError('Invalid metadata fields')
    if any(not isinstance(v,str) or len(v)>4096 for v in changes.values()):raise ValueError('Invalid field value')
    if 'lighting' in changes and changes['lighting'] not in {'dark','office-white','office-yellow'}:raise ValueError('Choose dark, office-white or office-yellow')
    if 'subject' in changes and not changes['subject'].strip():raise ValueError('Identity cannot be empty')
    prepared=[]
    for name in INDEXES:
        path=folder/name
        if path.resolve().parent!=folder:raise ValueError('Invalid index path')
        old=path.read_bytes();reader=csv.DictReader(io.StringIO(old.decode('utf-8-sig'),newline=''));rows=list(reader);fields=list(reader.fieldnames or [])
        matches=[r for r in rows if r.get('uuid')==uuid]
        if len(matches)!=1:raise Conflict('Capture changed or is missing; reopen it')
        if (name==INDEXES[0] or 'filename' in fields) and matches[0].get('filename')!=filename:raise Conflict('Capture filename changed; reopen it')
        if name!=INDEXES[0] and 'filename' not in fields and matches[0].get('ori_path') and Path(matches[0]['ori_path']).name!=filename:raise Conflict('Capture image path changed; reopen it')
        if name==INDEXES[0] and matches[0]!=expected:raise Conflict('Metadata changed since you opened it; reopen it')
        matches[0].update(changes)
        fields.extend(k for k in changes if k not in fields)
        out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        new=(b'\xef\xbb\xbf' if old.startswith(b'\xef\xbb\xbf') else b'')+out.getvalue().encode()
        prepared.append((path,old,new,path.stat().st_mode&0o777))
    for path,old,_,_ in prepared:
        if path.read_bytes()!=old:raise Conflict('Index changed; reopen capture')
    written=[]
    try:
        for path,old,new,mode in prepared:
            atomic_write(path,new,mode);written.append((path,old,mode))
    except Exception:
        for path,old,mode in written:atomic_write(path,old,mode)
        raise
    return {'updated':True,'changes':changes,'json_preserved':True}
