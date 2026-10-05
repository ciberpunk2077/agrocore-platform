import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { harness, load, tick, deferred, button, text, nodes } from './test-support.mjs'
import { env, record, animal, refreshed, payload, animalId, organizationId, statusId, id, types, farms, lots } from './flow-test-support.mjs'
const movementPath = `/api/animal-movements/${record.id}`, historyPath = `/api/animal-movements/animal/${animalId}/history`, animalPath = `/api/animals/${animalId}`
const snapshot = (movement=record, fresh=refreshed) => ({revision:1,organizationId,movement,animal:fresh,history:[movement]})
function confirmation(e=env(),extra={}) {
  const h=harness(), confirms=[], cancels=[]
  const Component=load('./components/AnimalMovementDeleteConfirmation.tsx',{
    react:h.react,'react/jsx-runtime':jsx,'../../auth/session':e.session,'../../lib/api-errors':e.errors,'../animal-movements.service':e.service,
  }).default
  const props={movementId:record.id,animalId,revision:1,organizationId,types,farms,lots,disabled:false,onCancel:()=>cancels.push(true),onConfirm:async s=>confirms.push(s),...extra}
  let tree;const render=()=>tree=h.render(Component,props)
  function queue(m=record,a=refreshed,history=[m]){e.queue(`/api/animal-movements/${props.movementId}`,{data:m});e.queue(historyPath,{data:history});e.queue(animalPath,{data:a})}
  async function ready(m,a,history){queue(m,a,history);render();await tick();render()}
  return {e,h,props,confirms,cancels,render,queue,ready,tree:()=>tree}
}
async function scopeDelete(e=env()) {await e.ready(undefined,[record]);e.history().props.onDelete(record.id);e.render();return e}
const syncAbsent = e => e.sync([],animal)

for(const role of ['OWNER','ADMIN','VETERINARIAN','OPERATOR','VIEWER'])test(`${role} delete visibility, history protection and details`,()=>{
  const History=load('./components/AnimalMovementHistory.tsx',{'react/jsx-runtime':jsx}).default
  const tree=History({history:[record,{...record,id:id(61)}],types,farms,lots,onDetail:()=>{},onEdit:role==='VIEWER'?undefined:()=>{},onDelete:role==='VIEWER'?undefined:()=>{},editDisabled:false})
  assert.ok(button(tree,'Ver detalles'));const deletes=nodes(tree).filter(n=>n.type==='button'&&text(n)==='Eliminar')
  assert.equal(deletes.length,role==='VIEWER'?0:2);if(deletes.length){assert.equal(deletes[0].props.disabled,false);assert.equal(deletes[1].props.disabled,true)}
})
for(const code of ['TRANSFER','ENTRY','PURCHASE','EXIT','SALE'])test(`confirmation fresh GETs and effects for ${code}`,async()=>{
  const entry=['ENTRY','PURCHASE'].includes(code);const m={...record,movement_type_id:types.find(t=>t.code===code).id,...(entry?{origin_farm_id:null,origin_lot_id:null}:{})}
  const c=confirmation();await c.ready(m);assert.equal(c.e.count('GET'),3);assert.ok(button(c.tree(),'Confirmar eliminación'))
  assert.ok(text(c.tree()).includes(m.id));assert.ok(text(c.tree()).includes(code));assert.match(text(c.tree()),/sobrescribir/);assert.match(text(c.tree()),/hist/)
  if(entry)assert.match(text(c.tree()),/Sin ubicaci/);else assert.ok(text(c.tree()).includes(farms[0].name))
  assert.ok(text(c.tree()).includes(statusId));assert.equal(c.e.count('DELETE'),0)
})
test('null snapshot preserves current status and historical names fall back to IDs',async()=>{
  const c=confirmation(undefined,{types:[],farms:[],lots:[]});await c.ready({...record,origin_status_id:null})
  assert.match(text(c.tree()),/conservar/);assert.ok(text(c.tree()).includes(refreshed.status));assert.ok(text(c.tree()).includes(record.origin_farm_id));assert.ok(text(c.tree()).includes(record.movement_type_id))
})
for(const invalid of ['movement','animal','schema','historical','inactive','missing-animal'])test(`preparation ${invalid} blocks DELETE`,async()=>{
  const c=confirmation();let m=record,a=refreshed,history=[record]
  if(invalid==='movement')m={...record,id:id(99)}
  if(invalid==='animal')a={...refreshed,id:id(99)}
  if(invalid==='schema')m={...record,date:42}
  if(invalid==='historical')history=[{...record,id:id(61)},record]
  if(invalid==='inactive')a={...refreshed,is_active:false}
  if(invalid==='missing-animal'){c.e.queue(movementPath,{data:record});c.e.queue(historyPath,{data:history});c.e.queue(animalPath,{status:404});c.render();await tick();c.render()}
  else await c.ready(m,a,history)
  assert.equal(button(c.tree(),'Confirmar eliminación'),undefined);assert.equal(c.e.count('DELETE'),0);assert.ok(button(c.tree(),'Reintentar preparación'))
  if(['inactive','missing-animal'].includes(invalid))assert.match(text(c.tree()),/Animal/)
})
test('cancel confirmation = zero DELETE and releases local exclusion',async()=>{
  const c=confirmation();await c.ready();button(c.tree(),'Cancelar').props.onClick();assert.equal(c.cancels.length,1);assert.equal(c.e.count('DELETE'),0)
  const e=await scopeDelete();await e.form().props.onCreate(payload);assert.equal(e.count('POST'),0);e.deletion().props.onCancel();e.render();assert.equal(e.form().props.disabled,false)
})
test('confirmation two synchronous clicks and pending click call delete once',async()=>{
  const c=confirmation(),d=deferred();c.props.onConfirm=async s=>{c.confirms.push(s);await d.promise};await c.ready()
  const click=button(c.tree(),'Confirmar eliminación').props.onClick;click();click();c.render();button(c.tree(),'Confirmar eliminación').props.onClick();assert.equal(c.confirms.length,1);d.resolve();await tick()
})
test('scope double delete = one request, full immutable scoped snapshot',async()=>{
  const e=await scopeDelete(),d=deferred();e.queue('DELETE',()=>d.promise);syncAbsent(e)
  const remove=e.deletion().props.onConfirm;const first=remove(snapshot());await remove(snapshot());e.render();await e.deletion().props.onConfirm(snapshot());assert.equal(e.count('DELETE'),1)
  const attempt=e.protocol.getAttempt(e.protocol.attemptKey(1,organizationId,animalId));assert.equal(attempt.kind,'delete');assert.equal(Object.isFrozen(attempt.deleteSnapshot),true);assert.equal(Object.isFrozen(attempt.deleteSnapshot.movement),true);assert.equal(attempt.deleteSnapshot.revision,1)
  d.resolve({data:{success:true}});await first;e.render();assert.match(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,false);assert.equal(e.history().props.history.length,0)
})
for(const response of [{data:{success:false}},{data:{success:true,extra:1}},{data:null},{data:[]},{status:202,data:{success:true}},{status:503},new TypeError('network'),{status:404}])test(`DELETE uncertain ${response.status??response.message??'body'}: never repeats`,async()=>{
  const e=await scopeDelete();e.queue('DELETE',response);const remove=e.deletion().props.onConfirm;await remove(snapshot());e.render()
  assert.match(text(e.tree()),/incierta/);assert.equal(e.form().props.disabled,true);await remove(snapshot());await e.form().props.onCreate(payload);e.history().props.onEdit(record.id);e.render()
  assert.equal(e.count('DELETE'),1);assert.equal(e.count('POST'),0);assert.equal(e.editor(),undefined)
})
test('confirmed DELETE refresh failure retains success; retry is only 2 GET',async()=>{
  const e=await scopeDelete();e.queue('DELETE',{data:{success:true}});e.queue(historyPath,{status:503});e.queue(animalPath,{data:animal});await e.deletion().props.onConfirm(snapshot());e.render()
  assert.match(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,true);assert.equal(e.history().props.history.length,0)
  syncAbsent(e);const before=e.count('GET');button(e.tree(),'Recuperar lecturas').props.onClick();await tick();e.render()
  assert.equal(e.count('GET')-before,2);assert.equal(e.count('DELETE'),1);assert.equal(e.form().props.disabled,false);assert.equal(e.form().props.animal.farm_id,animal.farm_id)
})
test('DELETE recovery GET 200 remains uncertain: one GET, no second DELETE',async()=>{
  const e=await scopeDelete();e.queue('DELETE',{status:503});await e.deletion().props.onConfirm(snapshot());e.render();e.queue(movementPath,{data:record});const before=e.count('GET')
  button(e.tree(),'Reconciliar ausencia').props.onClick();await tick();e.render();assert.equal(e.count('GET')-before,1);assert.equal(e.count('DELETE'),1);assert.match(text(e.tree()),/incierta/);assert.equal(e.form().props.disabled,true)
})
test('404 + history absent + fresh valid Animal reconcile absence, without attribution or snapshot equality',async()=>{
  const e=await scopeDelete();e.queue('DELETE',new TypeError('network'));await e.deletion().props.onConfirm(snapshot());e.render();e.queue(movementPath,{status:404});e.sync([],refreshed);const before=e.count('GET')
  button(e.tree(),'Reconciliar ausencia').props.onClick();await tick();e.render();assert.equal(e.count('GET')-before,3);assert.equal(e.count('DELETE'),1);assert.match(text(e.tree()),/Estado reconciliado/);assert.match(text(e.tree()),/no se atribuye/);assert.equal(e.form().props.disabled,false);assert.equal(e.updates[0].lot_id,refreshed.lot_id)
})
for(const failure of ['history','animal-id','animal-inactive','animal-failure','record-reappears','get-invalid-id','get-invalid-animal','get-5xx'])test(`absence evidence ${failure} insufficient`,async()=>{
  const e=await scopeDelete();e.queue('DELETE',{status:503});await e.deletion().props.onConfirm(snapshot());e.render()
  e.queue(movementPath,failure==='get-invalid-id'?{data:{...record,id:id(99)}}:failure==='get-invalid-animal'?{data:{...record,animal_id:id(99)}}:failure==='get-5xx'?{status:503}:{status:404})
  if(!failure.startsWith('get-')){e.queue(historyPath,failure==='history'?{status:503}:{data:failure==='record-reappears'?[record]:[]});e.queue(animalPath,failure==='animal-failure'?{status:503}:{data:failure==='animal-id'?{...animal,id:id(99)}:failure==='animal-inactive'?{...animal,is_active:false}:animal})}
  button(e.tree(),'Reconciliar ausencia').props.onClick();await tick();e.render();assert.match(text(e.tree()),/incierta/);assert.doesNotMatch(text(e.tree()),/Estado reconciliado/);assert.equal(e.form().props.disabled,true);assert.equal(e.updates.length,0);assert.equal(e.count('DELETE'),1)
})
test('confirmed DELETE with movement reappearing does not unlock writes',async()=>{
  const e=await scopeDelete();e.queue('DELETE',{data:{success:true}});e.sync([record],animal);await e.deletion().props.onConfirm(snapshot());e.render();assert.match(text(e.tree()),/confirmada/);assert.equal(e.form().props.disabled,true)
})
for(const op of ['create','update'])test(`${op} pending/uncertain/sync block DELETE`,async()=>{
  const e=env();await e.ready(undefined,[record])
  if(op==='create'){e.queue('POST',{status:503});await e.form().props.onCreate({...payload,date:'2026-01-02'})}
  else {e.history().props.onEdit(record.id);e.render();e.queue('PUT',{status:503});await e.editor().props.onSave(record,{...payload,notes:'changed'})}
  e.render();e.history().props.onDelete(record.id);e.render();assert.equal(e.deletion(),undefined);assert.equal(e.count('DELETE'),0)
})
test('DELETE preparation blocks CREATE/UPDATE and cancel cannot release uncertain attempt',async()=>{
  const e=await scopeDelete();await e.form().props.onCreate(payload);e.history().props.onEdit(record.id);e.render();assert.equal(e.count('POST'),0);assert.equal(e.editor(),undefined)
  e.queue('DELETE',{status:503});await e.deletion().props.onConfirm(snapshot());e.render();e.deletion().props.onCancel();e.render();assert.ok(e.deletion());assert.equal(e.form().props.disabled,true)
})
for(const identity of ['revision','organization','animal','movement','inactive'])test(`scope refuses bad snapshot ${identity}`,async()=>{
  const e=await scopeDelete();const s=snapshot();if(identity==='revision')s.revision=99;if(identity==='organization')s.organizationId=id(99);if(identity==='animal')s.animal={...animal,id:id(99)};if(identity==='movement')s.movement={...record,id:id(99)};if(identity==='inactive')s.animal={...animal,is_active:false}
  await e.deletion().props.onConfirm(s);assert.equal(e.count('DELETE'),0)
})
for(const stage of ['DELETE','refresh','reconciliation'])for(const change of ['abort','session'])test(`${stage} late after ${change} cannot apply`,async()=>{
  const e=await scopeDelete(),d=deferred();let first
  if(stage==='DELETE'){e.queue('DELETE',()=>d.promise);first=e.deletion().props.onConfirm(snapshot())}
  else if(stage==='refresh'){e.queue('DELETE',{data:{success:true}});e.queue(historyPath,()=>d.promise);e.queue(animalPath,{data:animal});first=e.deletion().props.onConfirm(snapshot());await tick()}
  else {e.queue('DELETE',{status:503});await e.deletion().props.onConfirm(snapshot());e.render();e.queue(movementPath,()=>d.promise);button(e.tree(),'Reconciliar ausencia').props.onClick()}
  if(change==='abort')e.h.unmount();else e.changeSession(true)
  d.resolve(stage==='reconciliation'?{status:404}:{data:stage==='refresh'?[]:{success:true}});if(first)await first;await tick();assert.equal(e.updates.length,0);assert.equal(e.count('DELETE'),1)
})
test('A-B-A preserves uncertain delete, no stale confirmation reopens, recovery only GET',async()=>{
  const a=await scopeDelete();a.queue('DELETE',{status:503});await a.deletion().props.onConfirm(snapshot());a.h.unmount()
  const b=env(a.protocol);await b.ready({animalId:id(99),animal:{...animal,id:id(99)}});assert.equal(b.form().props.disabled,false);b.h.unmount()
  const back=env(a.protocol);await back.ready(undefined,[record]);assert.equal(back.deletion(),undefined);assert.equal(back.form().props.disabled,true);back.queue(movementPath,{status:404});syncAbsent(back);button(back.tree(),'Reconciliar ausencia').props.onClick();await tick();back.render();assert.equal(back.count('DELETE'),0);assert.equal(back.form().props.disabled,false)
})
test('confirmation stale/session/context/out-of-order results cannot replace newest preparation',async()=>{
  const c=confirmation(),d=deferred();c.e.queue(movementPath,()=>d.promise);c.e.queue(historyPath,{data:[record]});c.e.queue(animalPath,{data:refreshed});c.render()
  c.props.organizationId=id(99);c.queue({...record,notes:'NEW'});c.render();await tick();c.render();d.resolve({data:{...record,notes:'OLD'}});await tick();c.render();assert.match(text(c.tree()),/NEW/);assert.doesNotMatch(text(c.tree()),/OLD/);assert.ok(c.e.calls[0].signal.aborted)
  c.e.changeSession(true);button(c.tree(),'Confirmar eliminación').props.onClick();assert.equal(c.confirms.length,0)
})
test('VIEWER scope never exposes delete; catalogue failure does not block safe delete fallback',async()=>{
  const viewer=env();await viewer.ready({canWrite:false},[record]);assert.equal(viewer.history().props.onDelete,undefined);assert.equal(viewer.deletion(),undefined)
  const e=env();e.queue(historyPath,{data:[record]});e.queue('/api/catalogs/movement-types',{status:503});e.queue('/api/farms/',{data:farms});e.queue('/api/lots/',{data:lots});e.render();await tick();e.render();assert.equal(e.history().props.deleteDisabled,false);e.history().props.onDelete(record.id);e.render();assert.ok(e.deletion())
})
test('known 400/403/422 rejection does not claim success or uncertainty; cancellation frees exclusion',async()=>{
  for(const status of [400,403,422]){const e=await scopeDelete();e.queue('DELETE',{status,data:{detail:'Rejected'}});await assert.rejects(e.deletion().props.onConfirm(snapshot()));e.render();assert.doesNotMatch(text(e.tree()),/incierta|confirmada/);e.deletion().props.onCancel();e.render();assert.equal(e.form().props.disabled,false)}
})
test('double recovery action produces one three-GET recovery and no second DELETE',async()=>{
  const e=await scopeDelete();e.queue('DELETE',{status:503});await e.deletion().props.onConfirm(snapshot());e.render();const d=deferred();e.queue(movementPath,()=>d.promise);syncAbsent(e);const recover=button(e.tree(),'Reconciliar ausencia').props.onClick,before=e.count('GET');recover();recover();assert.equal(e.count('GET')-before,1);d.resolve({status:404});await tick();e.render();assert.equal(e.count('GET')-before,3);assert.equal(e.count('DELETE'),1)
})

test('stale confirm handler cannot use a replaced preparation snapshot',async()=>{
  const c=confirmation();await c.ready();const stale=button(c.tree(),'Confirmar eliminación').props.onClick
  c.props.movementId=id(61);c.e.queue(`/api/animal-movements/${id(61)}`,{data:{...record,id:id(61)}});c.e.queue(historyPath,{data:[{...record,id:id(61)}]});c.e.queue(animalPath,{data:animal});c.render();await tick();c.render()
  stale();assert.equal(c.confirms.length,0);button(c.tree(),'Confirmar eliminación').props.onClick();await tick();assert.equal(c.confirms.length,1);assert.equal(c.confirms[0].movement.id,id(61))
})
