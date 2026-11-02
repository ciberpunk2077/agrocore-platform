import assert from 'node:assert/strict'
import { detailImports } from '../reproduction/test-support.mjs'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { load, harness, tick, deferred, find, nodes, button, text } from './test-support.mjs'
import { env, id, animalId, organizationId, statusId, types, farms, lots, animal, record, payload, refreshed, validation, updateValidation } from './flow-test-support.mjs'
const detailPath = `/api/animal-movements/${record.id}`
const historyPath = `/api/animal-movements/animal/${animalId}/history`
const animalPath = `/api/animals/${animalId}`
const changed = { ...record, reason: ' changed ', notes: ' historical text ' }
const updatedPayload = updateValidation.updatePayload(changed)
const importBase = (e,h) => ({...detailImports,react:h.react,'react/jsx-runtime':jsx,'../../auth/session':e.session,'../../lib/api':e.api,'../../lib/api-errors':e.errors,'../animal-movements.service':e.service,'../update-validation':updateValidation})
function detailEnv(e=env(), extra={}) {
  const h=harness(), close=[]
  const component=load('./components/AnimalMovementDetail.tsx',importBase(e,h)).default
  const props={movementId:record.id,animalId,organizationId,revision:1,types,farms,lots,animal,onClose:()=>close.push(true),...extra}
  let tree;const render=()=>tree=h.render(component,props)
  return {e,h,close,props,render,tree:()=>tree}
}
function editEnv(e=env(),extra={}) {
  const h=harness(),saves=[],cancels=[]
  const component=load('./components/AnimalMovementEditForm.tsx',importBase(e,h)).default
  const props={movementId:record.id,animalId,organizationId,revision:1,types,farms,lots,disabled:false,animalActive:true,onSave:async (r,p)=>saves.push({r,p}),onCancel:()=>cancels.push(true),...extra}
  let tree;const render=()=>tree=h.render(component,props)
  const change=(control,value)=>{nodes(tree).find(n=>n.props?.id===control).props.onChange({target:{value}});render()}
  async function ready(fresh=record,history=[fresh]){e.queue(detailPath,{data:fresh});e.queue(historyPath,{data:history});render();await tick();render()}
  return {e,h,props,saves,cancels,render,change,ready,tree:()=>tree,submit:()=>find(tree,'form').props.onSubmit({preventDefault(){}})}
}
async function scopeEditor(e=env()) {
  await e.ready(undefined,[record]);e.history().props.onEdit(record.id);e.render();return e
}

test('DETAIL fresh GET, all fields and historical ID fallback; open/close never writes',async()=>{
  const d=detailEnv(undefined,{types:[],farms:[],lots:[]});d.e.queue(detailPath,{data:{...record,reason:' spaces ',notes:' notes ',origin_status_id:null}})
  d.render();assert.match(text(d.tree()),/Cargando/);await tick();d.render()
  for(const value of [record.id,'01/01/2026',record.movement_type_id,record.origin_farm_id,record.origin_lot_id,record.destination_farm_id,record.destination_lot_id,' spaces ',' notes ','Sin snapshot'])assert.ok(text(d.tree()).includes(value),value)
  button(d.tree(),'Volver').props.onClick();assert.equal(d.close.length,1);assert.equal(d.e.count('GET'),1);assert.equal(d.e.count('PUT'),0);assert.equal(d.e.count('POST'),0)
})
for(const role of ['OWNER','ADMIN','VETERINARIAN','OPERATOR','VIEWER'])test(`history ${role}: details always available, edit only write`,()=>{
  const c=load('./components/AnimalMovementHistory.tsx',{'react/jsx-runtime':jsx}).default,calls=[]
  const tree=c({history:[record,{...record,id:id(61)}],types,farms,lots,onDetail:v=>calls.push(v),onEdit:role==='VIEWER'?undefined:()=>{},editDisabled:false})
  const details=nodes(tree).filter(n=>n.type==='button'&&text(n)==='Ver detalles');assert.equal(details.length,2);details[0].props.onClick();assert.equal(calls[0],record.id)
  const edits=nodes(tree).filter(n=>n.type==='button'&&text(n)==='Editar');assert.equal(edits.length,role==='VIEWER'?0:2)
  if(edits.length){assert.equal(edits[0].props.disabled,false);assert.equal(edits[1].props.disabled,true)}
})
for(const result of [{data:{...record,id:id(99)}},{data:{...record,animal_id:id(99)}},{data:{...record,date:'invalid'}},{status:404,data:{detail:'not found'}},{status:503}])test(`DETAIL rejects ${result.status??JSON.stringify(result.data)} and permits GET retry`,async()=>{
  const d=detailEnv();d.e.queue(detailPath,result,{data:record});d.render();await tick();d.render();assert.ok(find(d.tree(),'dl')===undefined);assert.ok(button(d.tree(),'Reintentar detalle'))
  if(result.status===404)assert.match(text(d.tree()),/no est/)
  button(d.tree(),'Reintentar detalle').props.onClick();d.render();await tick();d.render();assert.ok(find(d.tree(),'dl'));assert.equal(d.e.count('GET'),2)
})
for(const reason of ['abort','session','organization','movement','animal'])test(`DETAIL ignores stale result on ${reason}`,async()=>{
  const d=detailEnv(),pending=deferred();d.e.queue(detailPath,()=>pending.promise);d.render()
  if(reason==='session')d.e.changeSession(true)
  else if(reason==='organization'){d.props.organizationId=id(99);d.e.queue(detailPath,{data:record});d.render()}
  else if(reason==='movement'){d.props.movementId=id(99);d.e.queue(`/api/animal-movements/${id(99)}`,{data:{...record,id:id(99)}});d.render()}
  else if(reason==='animal'){d.props.animalId=id(99);d.e.queue(detailPath,{data:{...record,animal_id:id(99)}});d.render()}
  else d.h.unmount()
  pending.resolve({data:{...record,notes:'OLD'}});await tick();if(reason!=='abort')d.render()
  assert.doesNotMatch(text(d.tree()),/OLD/);if(reason!=='session')assert.ok(d.e.calls[0].signal.aborted)
})

test('UPDATE prefill uses individual GET not history; fixed animal/origin/status; complete strings preserved',async()=>{
  const original={...record,reason:'  historical reason  ',notes:'  historical notes  ',origin_status_id:null}
  const e=editEnv();await e.ready(original,[{...record,reason:'STALE'}]);assert.equal(nodes(e.tree()).find(n=>n.props?.id==='movement-edit-reason').props.value,original.reason)
  assert.equal(nodes(e.tree()).find(n=>n.props?.id==='movement-edit-notes').props.value,original.notes)
  assert.ok(text(e.tree()).includes(record.origin_farm_id));assert.match(text(e.tree()),/Sin snapshot/)
  await e.submit();assert.equal(e.saves.length,1);assert.equal(Object.keys(e.saves[0].p).length,9)
  assert.equal(e.saves[0].p.reason,original.reason);assert.equal(e.saves[0].p.notes,original.notes);assert.equal(e.saves[0].p.animal_id,record.animal_id);assert.equal(e.saves[0].p.origin_lot_id,record.origin_lot_id)
  assert.equal(e.saves[0].r.origin_status_id,null)
})
test('UPDATE cancellation sends zero PUT and explicit clearing retains empty strings',async()=>{
  const e=editEnv();await e.ready();button(e.tree(),'Cancelar').props.onClick();assert.equal(e.cancels.length,1);assert.equal(e.e.count('PUT'),0)
  e.change('movement-edit-reason','');e.change('movement-edit-notes','');await e.submit();assert.equal(e.saves[0].p.reason,'');assert.equal(e.saves[0].p.notes,'')
})
test('UPDATE historical movement is not editable',async()=>{
  const e=editEnv();await e.ready(record,[{...record,id:id(61),date:'2026-01-02'},record]);assert.equal(find(e.tree(),'form'),undefined);assert.match(text(e.tree()),/ltimo movimiento activo/)
})
test('UPDATE inactive immutable origin is blocked without replacement',async()=>{
  const e=editEnv(undefined,{farms:[]});await e.ready();assert.equal(find(e.tree(),'form'),undefined);assert.match(text(e.tree()),/origen hist/);assert.equal(e.e.count('PUT'),0)
})
test('UPDATE prefill failure retries both GET reads',async()=>{
  const e=editEnv();e.e.queue(detailPath,{status:503},{data:record});e.e.queue(historyPath,{data:[record]},{data:[record]});e.render();await tick();e.render();assert.ok(button(e.tree(),'Reintentar preparación'))
  button(e.tree(),'Reintentar preparación').props.onClick();e.render();await tick();e.render();assert.ok(find(e.tree(),'form'));assert.equal(e.e.count('GET'),4)
})
for(const date of ['2025-12-30','2025-12-31','9999-01-01','2026-02-30'])test(`UPDATE invalid date ${date} = zero PUT`,async()=>{
  const e=editEnv();await e.ready(record,[record,{...record,id:id(61),date:'2025-12-31'}]);e.change('movement-edit-date',date);await e.submit();assert.equal(e.saves.length,0)
})
test('UPDATE valid date can preserve original or follow previous date',async()=>{
  const e=editEnv();await e.ready(record,[record,{...record,id:id(61),date:'2025-12-30'}]);await e.submit();e.change('movement-edit-date','2025-12-31');await e.submit();assert.equal(e.saves.length,2)
})
for(const [from,to] of [['TRANSFER','TRANSFER'],['TRANSFER','EXIT'],['EXIT','TRANSFER'],['SALE','TRANSFER'],['SALE','EXIT'],['TRANSFER','SALE'],['TRANSFER','ENTRY'],['EXIT','PURCHASE'],['ENTRY','PURCHASE']])test(`UPDATE transition ${from} → ${to} follows real rules`,()=>{
  const noOrigin=from==='ENTRY'||from==='PURCHASE';const noDestination=to==='EXIT'||to==='SALE'
  const original={...record,movement_type_id:types.find(t=>t.code===from).id,...(noOrigin?{origin_farm_id:null,origin_lot_id:null}:{})}
  const p={...updateValidation.updatePayload(original),movement_type_id:types.find(t=>t.code===to).id,destination_farm_id:noDestination?null:farms[1].id,destination_lot_id:noDestination?null:lots[1].id}
  assert.equal(updateValidation.updateError(p,original,'',types,farms,lots),null)
})
for(const from of ['ENTRY','PURCHASE'])for(const to of ['TRANSFER','EXIT','SALE'])test(`UPDATE ${from} null origin → ${to} rejected`,()=>{
  const original={...record,movement_type_id:types.find(t=>t.code===from).id,origin_farm_id:null,origin_lot_id:null}
  const p={...updateValidation.updatePayload(original),movement_type_id:types.find(t=>t.code===to).id,destination_farm_id:to==='TRANSFER'?farms[1].id:null,destination_lot_id:to==='TRANSFER'?lots[1].id:null}
  assert.match(updateValidation.updateError(p,original,'',types,farms,lots),/origen/)
})
for(const field of ['animal_id','origin_farm_id','origin_lot_id'])test(`UPDATE immutable ${field}`,()=>{
  assert.match(updateValidation.updateError({...updatedPayload,[field]:id(99)},record,'',types,farms,lots),/inmutables/)
})
test('semantic comparison null text equals persisted empty; strings never trimmed; null status accepted',()=>{
  assert.equal(validation.matchesAttempt({...record,reason:'',notes:'',origin_status_id:null},{...payload,reason:null,notes:null},null),true)
  assert.equal(validation.matchesAttempt({...record,reason:' text '},{...payload,reason:'text'},statusId),false)
})

for(const result of [{status:202,data:changed},{data:{}},{data:{...changed,id:id(99)}},{data:{...changed,animal_id:id(99)}},{data:{...changed,origin_status_id:id(99)}},{status:503},new TypeError('network')])test(`PUT uncertain ${result.status??result.message??'invalid body'}; duplicate action cannot resend`,async()=>{
  const e=await scopeEditor();e.queue('PUT',result);const save=e.editor().props.onSave
  await save(record,updatedPayload);e.render();assert.match(text(e.tree()),/incierta/);assert.equal(e.form().props.disabled,true)
  await save(record,updatedPayload);await e.form().props.onCreate(payload);assert.equal(e.count('PUT'),1);assert.equal(e.count('POST'),0)
})
test('PUT two synchronous actions and clicks while pending = one PUT',async()=>{
  const e=await scopeEditor(),d=deferred();e.queue('PUT',()=>d.promise);e.sync([changed]);const save=e.editor().props.onSave
  const first=save(record,updatedPayload);await save(record,updatedPayload);e.render();await e.editor().props.onSave(record,updatedPayload);assert.equal(e.count('PUT'),1)
  d.resolve({data:changed});await first;e.render();assert.match(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,false)
})
test('real editor two synchronous submit events and pending click = one save',async()=>{
  const e=editEnv(),d=deferred();e.props.onSave=async(r,p)=>{e.saves.push({r,p});await d.promise};await e.ready()
  const submit=find(e.tree(),'form').props.onSubmit,event={preventDefault(){}};const first=submit(event);await submit(event);e.render();await e.submit();assert.equal(e.saves.length,1);d.resolve();await first
})
test('PUT confirmed with refresh failed retains success; retry only two GET',async()=>{
  const e=await scopeEditor();e.queue('PUT',{data:changed});e.queue(historyPath,{status:503});e.queue(animalPath,{data:refreshed});await e.editor().props.onSave(record,updatedPayload);e.render()
  assert.match(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,true);assert.equal(e.count('PUT'),1)
  e.sync([changed]);const before=e.count('GET');button(e.tree(),'Recuperar lecturas').props.onClick();await tick();e.render()
  assert.equal(e.count('GET')-before,2);assert.equal(e.count('PUT'),1);assert.equal(e.form().props.disabled,false);assert.equal(e.editor(),undefined);assert.equal(e.form().props.animal.lot_id,refreshed.lot_id)
})
test('PUT uncertain matching GET reconciles STATE then syncs history + Animal: one PUT, three GET',async()=>{
  const e=await scopeEditor();e.queue('PUT',{status:503});await e.editor().props.onSave(record,updatedPayload);e.render();e.queue(detailPath,{data:changed});e.sync([changed]);const before=e.count('GET')
  button(e.tree(),'Reconciliar').props.onClick();await tick();e.render();assert.equal(e.count('GET')-before,3);assert.equal(e.count('PUT'),1);assert.match(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,false)
})
for(const result of [{data:record},{status:404},{status:503},{data:{...changed,id:id(99)}},{data:{...changed,animal_id:id(99)}},{data:{...changed,origin_status_id:id(99)}}])test(`reconciliation ${result.status??'different/identity'} remains uncertain with one GET`,async()=>{
  const e=await scopeEditor();e.queue('PUT',new TypeError('network'));await e.editor().props.onSave(record,updatedPayload);e.render();e.queue(detailPath,result);const before=e.count('GET')
  button(e.tree(),'Reconciliar').props.onClick();await tick();e.render();assert.equal(e.count('GET')-before,1);assert.equal(e.count('PUT'),1);assert.match(text(e.tree()),/incierta/);assert.doesNotMatch(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,true)
})
test('equivalent reconciliation but bad Animal refresh keeps confirmed state and lock',async()=>{
  const e=await scopeEditor();e.queue('PUT',{status:503});await e.editor().props.onSave(record,updatedPayload);e.render();e.queue(detailPath,{data:changed});e.sync([changed],{...refreshed,id:id(99)})
  button(e.tree(),'Reconciliar').props.onClick();await tick();e.render();assert.match(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,true);assert.equal(e.updates.length,0)
})
test('CREATE↔UPDATE exclusion includes preparation/cancellation/pending/uncertainty',async()=>{
  const e=await scopeEditor();await e.form().props.onCreate(payload);assert.equal(e.count('POST'),0)
  e.editor().props.onCancel();e.render();assert.equal(e.form().props.disabled,false);e.queue('POST',{status:503});await e.form().props.onCreate({...payload,date:'2026-01-02'});e.render()
  e.history().props.onEdit(record.id);e.render();assert.equal(e.editor(),undefined);assert.equal(e.count('PUT'),0)
})
for(const stage of ['PUT','refresh','reconciliation'])for(const stop of ['abort','session'])test(`late ${stage} after ${stop} cannot contaminate scope`,async()=>{
  const e=await scopeEditor(),d=deferred();let pending
  if(stage==='PUT'){e.queue('PUT',()=>d.promise);pending=e.editor().props.onSave(record,updatedPayload)}
  else if(stage==='refresh'){e.queue('PUT',{data:changed});e.queue(historyPath,()=>d.promise);e.queue(animalPath,{data:refreshed});pending=e.editor().props.onSave(record,updatedPayload);await tick()}
  else {e.queue('PUT',{status:503});await e.editor().props.onSave(record,updatedPayload);e.render();e.queue(detailPath,()=>d.promise);button(e.tree(),'Reconciliar').props.onClick()}
  if(stop==='abort')e.h.unmount();else e.changeSession(true)
  d.resolve({data:stage==='refresh'?[changed]:changed});if(pending)await pending;await tick();assert.equal(e.updates.length,0);assert.equal(e.count('PUT'),1)
})
test('A→B→A retains uncertain UPDATE with snapshot but never reopens obsolete form',async()=>{
  const a=await scopeEditor();a.queue('PUT',{status:503});await a.editor().props.onSave(record,updatedPayload);a.h.unmount()
  const b=env(a.protocol);await b.ready({animalId:id(99),animal:{...animal,id:id(99)}});assert.equal(b.form().props.disabled,false);b.h.unmount()
  const back=env(a.protocol);await back.ready(undefined,[record]);assert.equal(back.editor(),undefined);assert.equal(back.form().props.disabled,true)
  back.queue(detailPath,{data:changed});back.sync([changed]);button(back.tree(),'Reconciliar').props.onClick();await tick();back.render();assert.equal(back.count('PUT'),0);assert.equal(back.form().props.disabled,false)
})
test('pending snapshot is frozen; cancellation cannot release uncertain UPDATE',async()=>{
  const e=await scopeEditor();e.queue('PUT',{status:503});await e.editor().props.onSave(record,updatedPayload);e.render();e.editor().props.onCancel();e.render();assert.ok(e.editor());assert.equal(e.form().props.disabled,true)
  const attempt=e.protocol.getAttempt(e.protocol.attemptKey(1,organizationId,animalId));assert.equal(Object.isFrozen(attempt.payload),true);assert.equal(attempt.originStatusId,statusId)
})
test('known PUT 400 preserves editor and permits safe subsequent user action',async()=>{
  const e=await scopeEditor();e.queue('PUT',{status:400,data:{detail:'Historical'}});await assert.rejects(e.editor().props.onSave(record,updatedPayload));e.render();assert.equal(e.editor().props.disabled,false)
})

test('DETAIL A-B-A and out-of-order reads keep only newest record',async()=>{
  const d=detailEnv(),a=deferred(),b=deferred()
  d.e.queue(detailPath,()=>a.promise,{data:{...record,notes:'LATEST-A'}})
  d.e.queue(`/api/animal-movements/${id(61)}`,()=>b.promise)
  d.render();d.props.movementId=id(61);d.render();d.props.movementId=record.id;d.render();await tick();d.render()
  b.resolve({data:{...record,id:id(61),notes:'OLD-B'}});a.resolve({data:{...record,notes:'OLD-A'}});await tick();d.render()
  assert.match(text(d.tree()),/LATEST-A/);assert.doesNotMatch(text(d.tree()),/OLD-/);assert.equal(d.e.count('GET'),3)
})
for(const [from,to] of [['TRANSFER','EXIT'],['EXIT','TRANSFER'],['SALE','TRANSFER'],['SALE','EXIT'],['TRANSFER','SALE'],['TRANSFER','ENTRY'],['EXIT','PURCHASE']])test(`real editor transition ${from}-${to} preserves origin and snapshot`,async()=>{
  const original={...record,movement_type_id:types.find(t=>t.code===from).id,...(['EXIT','SALE'].includes(from)?{destination_farm_id:null,destination_lot_id:null}:{})}
  const e=editEnv();await e.ready(original);e.change('movement-edit-type',types.find(t=>t.code===to).id)
  if(!['EXIT','SALE'].includes(to)){e.change('movement-edit-farm',farms[1].id);e.change('movement-edit-lot',lots[1].id)}
  await e.submit();assert.equal(e.saves.length,1);assert.equal(e.saves[0].p.origin_farm_id,original.origin_farm_id);assert.equal(e.saves[0].r.origin_status_id,original.origin_status_id)
  if(['EXIT','SALE'].includes(to)){assert.equal(e.saves[0].p.destination_farm_id,null);assert.equal(e.saves[0].p.destination_lot_id,null)}
})
test('UPDATE valid date is checked against fresh preparation history, not obsolete parent history',async()=>{
  const e=env();const old={...record,date:'2026-01-10'};await e.ready(undefined,[old,{...record,id:id(61),date:'2026-01-05'}]);e.history().props.onEdit(old.id);e.render()
  const desired={...old,date:'2026-01-01'};e.queue('PUT',{data:desired});e.sync([desired])
  await e.editor().props.onSave(old,updateValidation.updatePayload(desired),[old]);e.render();assert.equal(e.count('PUT'),1);assert.match(text(e.tree()),/confirmada/)
})
test('VIEWER scope has details handler but no editor or PUT path',async()=>{
  const e=env();await e.ready({canWrite:false},[record]);assert.equal(e.history().props.onEdit,undefined);e.history().props.onDetail(record.id);e.render();assert.equal(e.detail().props.movementId,record.id);assert.equal(e.editor(),undefined);assert.equal(e.count('PUT'),0)
})
test('double reconciliation action issues one GET and never a second PUT',async()=>{
  const e=await scopeEditor();e.queue('PUT',{status:503});await e.editor().props.onSave(record,updatedPayload);e.render();const d=deferred();e.queue(detailPath,()=>d.promise);e.sync([changed]);const recover=button(e.tree(),'Reconciliar').props.onClick;const before=e.count('GET')
  recover();recover();assert.equal(e.count('GET')-before,1);d.resolve({data:changed});await tick();e.render();assert.equal(e.count('GET')-before,3);assert.equal(e.count('PUT'),1)
})
test('PUT confirmation/reconciliation accepts null origin status and normalized null text',async()=>{
  const e=await scopeEditor();const original={...record,origin_status_id:null},p={...updatedPayload,reason:null,notes:null};e.queue('PUT',{data:{...original,reason:'',notes:''}});e.sync([{...original,reason:'',notes:''}]);await e.editor().props.onSave(original,p);e.render();assert.match(text(e.tree()),/confirmada/);assert.equal(e.count('PUT'),1)
})
