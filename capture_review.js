let capture=null,editing=false,opening=0;
const editable=['subject','lighting','capture_device','input_sensor','user'];
const labels={subject:'Identity',lighting:'Lighting',capture_device:'Web capture device (blank for App SDK)',input_sensor:'Input sensor / App device metadata',user:'User'};
function controls(disabled){$('save-metadata').disabled=disabled;$('remove-capture').disabled=disabled;$('review-close').disabled=editing}
async function openCapture(key){
 const ticket=++opening;capture=null;$('review-title').textContent='Loading capture…';$('review-error').textContent='';$('review-fields').replaceChildren();$('all-metadata').textContent='';$('review-image').removeAttribute('src');controls(true);$('review').showModal();
 try{
  const responses=await Promise.all([fetch('/api/capture?key='+encodeURIComponent(key)),fetch('/api/batches'),fetch('/api/captures')]);
  if(!responses[0].ok)throw Error(responses[0].status===404?'This capture was removed. Its log entry remains as history.':await responses[0].text());
  if(!responses[1].ok||!responses[2].ok)throw Error('Unable to load metadata choices. Please reopen this capture.');
  const [row,batches,rows]=await Promise.all(responses.map(res=>res.json()));if(ticket!==opening)return;
  const batch=batches.find(b=>b.batch_name===row.folder&&b.test_plan_name===row.metadata.test_plan_name);
  if(!batch)throw Error('This batch has no matching definition in the batches CSV.');
  const split=value=>(value||'').split(';').map(v=>v.trim()).filter(Boolean);
  const identities=split(batch.expected_identities);
  const choices={subject:identities.length?identities:[...new Set(rows.filter(r=>r.metadata.test_plan_name===row.metadata.test_plan_name).map(r=>r.metadata.subject).filter(Boolean))].sort(),lighting:split(batch.expected_lighting),capture_device:['',...split(batch.expected_web_devices)]};
  $('review-title').textContent=row.folder+' / '+row.metadata.filename;$('review-image').src='/api/image?key='+encodeURIComponent(row.key);$('all-metadata').textContent=JSON.stringify(row.metadata,null,2);
  for(const k of editable){
   const label=document.createElement('label');label.textContent=labels[k];const input=document.createElement(choices[k]?'select':k==='input_sensor'?'textarea':'input');input.id='edit-'+k;const current=row.metadata[k]||'';
   if(choices[k]){
    if(!choices[k].includes(current)){const option=document.createElement('option');option.value=current;option.textContent=(current||'(missing)')+' — current value outside configured choices';input.append(option)}
    for(const value of [...new Set(choices[k])]){const option=document.createElement('option');option.value=value;option.textContent=value||(k==='capture_device'?'App SDK — use input sensor':'(missing)');input.append(option)}
   }
   input.value=current;label.append(input);$('review-fields').append(label);
  }
  const hint=document.createElement('p');hint.textContent='Lighting and Web devices: batch CSV. Identities: '+(identities.length?'batch CSV.':'annotated identities in this test plan.');$('review-fields').append(hint);
  capture=row;controls(false);
 }catch(e){if(ticket===opening)$('review-error').textContent=e.message}
}
async function executeEdit(remove){if(!capture||editing)return;const row=capture;const changes=Object.fromEntries(editable.filter(k=>$('edit-'+k).value!==(row.metadata[k]||'')).map(k=>[k,$('edit-'+k).value]));if(!remove&&!Object.keys(changes).length){$('review-error').textContent='No metadata changes.';return}const question=remove?'Delete '+row.metadata.filename+' from both CSV indexes and delete its images? JSON metadata and ingestion history remain.':'Save these metadata changes in both CSV indexes?\n'+Object.entries(changes).map(([k,v])=>k+': '+v).join('\n');if(!confirm(question))return;const pin=prompt('Enter your PIN:');if(!pin)return;editing=true;controls(true);$('review-error').textContent='';try{const payload=remove?{confirm_count:1,remove:[{key:row.key,folder:row.folder,uuid:row.metadata.uuid,filename:row.metadata.filename}]}:{folder:row.folder,uuid:row.metadata.uuid,filename:row.metadata.filename,changes,expected:row.metadata};const res=await fetch(remove?'/api/apply-decisions':'/api/edit-capture',{method:'POST',headers:{'Content-Type':'application/json','X-Delete-Token':pin},body:JSON.stringify(payload)});if(!res.ok)throw Error(await res.text());if(remove){try{const d=JSON.parse(localStorage.getItem('idrecapture-review-v1')||'{}');delete d[row.key];localStorage.setItem('idrecapture-review-v1',JSON.stringify(d))}catch{}capture=null;$('review').close();await refresh()}else{await refresh();editing=false;await openCapture(row.key)} }catch(e){$('review-error').textContent='Not saved: '+e.message}finally{editing=false;controls(!capture)}}
$('review-close').onclick=()=>{opening++;$('review').close()};$('review').addEventListener('cancel',e=>{if(editing)e.preventDefault();else opening++});$('save-metadata').onclick=()=>executeEdit(false);$('remove-capture').onclick=()=>executeEdit(true);
