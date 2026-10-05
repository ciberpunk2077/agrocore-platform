import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { tick, deferred, load, harness, nodes, text, find, button, mod } from './test-support.mjs'
import { id, animalId, organizationId, statusId, types, farms, lots, animal, payload, record, refreshed, validation, env } from './flow-test-support.mjs'

const histPath = `/api/animal-movements/animal/${animalId}/history`
const animalPath = `/api/animals/${animalId}`

test('runtime contracts: movement, nullable fields, dates, history identity, catalogs and Animal', () => {
  assert.equal(validation.isMovement(record, animalId), true)
  for (const key of ['id','animal_id','movement_type_id','origin_status_id','origin_farm_id','origin_lot_id','destination_farm_id','destination_lot_id','date','reason','notes']) {
    assert.equal(validation.isMovement({ ...record, [key]: 42 }, animalId), false, key)
  }
  assert.equal(validation.isMovement({ ...record, date: '2026-02-30' }, animalId), false)
  assert.equal(validation.isHistory([record], id(99)), false)
  assert.equal(validation.isHistory([record, record], animalId), false)
  assert.equal(validation.isMovement({ ...record, reason: null, notes: null, destination_lot_id: null }, animalId), true)
  assert.equal(validation.isMovementTypes(types), true)
  assert.equal(validation.isMovementTypes([{ ...types[0], id: 'bad' }]), false)
  assert.equal(validation.isFarms(farms), true)
  assert.equal(validation.isFarms([{ ...farms[0], name: null }]), false)
  assert.equal(validation.isLots(lots, organizationId), true)
  assert.equal(validation.isLots(lots, id(99)), false)
  assert.equal(validation.isAnimal(refreshed, animalId), true)
  assert.equal(validation.isAnimal(refreshed, id(99)), false)
  assert.equal(validation.isAnimal({ ...refreshed, status_id: null }, animalId), false)
})

test('history remains available despite catalog failure', async () => {
  const f=env(); f.queue(histPath,{data:[record]}); f.queue('/api/catalogs/movement-types',{status:503}); f.queue('/api/farms/',{data:farms}); f.queue('/api/lots/',{data:lots})
  f.render(); await tick(); f.render()
  assert.equal(f.history().props.history.length,1); assert.equal(f.form(),undefined)
  assert.match(text(f.tree()),/catálogos/)
})

test('wrong-animal history is rejected with retry and CREATE blocked', async () => {
  const e=env(); e.defaults([{...record,animal_id:id(99)}]); e.render(); await tick(); e.render()
  assert.equal(e.history().props.history.length,0); assert.equal(e.form().props.disabled,true)
  e.queue(histPath,{data:[record]}); button(e.tree(),'Reintentar historial').props.onClick(); e.render(); await tick(); e.render()
  assert.equal(e.history().props.history.length,1)
})

test('VIEWER renders only READ without CREATE handler', async () => {
  const e=env(); await e.ready({canWrite:false}); assert.equal(e.form(),undefined)
  assert.equal(e.count('POST'),0); assert.ok(e.history())
  e.context({status:'loaded',currentOrganization:{id:organizationId},canWrite:false})
  const outer=e.h.render(e.component.default,{animalId,animal,onAnimalUpdated:()=>{}})
  assert.equal(outer.props.canWrite,false)
})

for (const response of [{status:202,data:record},{status:200,data:{}},{status:503},{status:200,data:{...record,notes:'different'}},new TypeError('network')]) {
  test(`uncertain ${response.status ?? response.message}: exactly 1 POST, recovery GET only, no attributed success`, async () => {
    const e=env(); await e.ready(); e.queue('POST',response)
    const create=e.form().props.onCreate; await create(payload); e.render()
    assert.match(text(e.tree()),/Resultado incierto/); assert.equal(e.form().props.disabled,true)
    await create(payload); await create(payload); assert.equal(e.count('POST'),1)
    e.sync(); const before=e.count('GET'); button(e.tree(),'Recuperar lecturas').props.onClick(); await tick(); e.render()
    assert.equal(e.count('GET')-before,2); assert.equal(e.count('POST'),1)
    assert.match(text(e.tree()),/sigue incierto/); assert.doesNotMatch(text(e.tree()),/Movimiento registrado correctamente/)
    await e.form().props.onCreate(payload); assert.equal(e.count('POST'),1)
  })
}

test('confirmed POST + refresh failure keeps success; retry is two GET; next CREATE uses fresh Animal', async () => {
  const e=env(); await e.ready(); e.queue('POST',{data:record}); e.queue(histPath,{status:503}); e.queue(animalPath,{data:refreshed})
  await e.form().props.onCreate(payload); e.render()
  assert.match(text(e.tree()),/Movimiento registrado correctamente/); assert.equal(e.form().props.disabled,true)
  assert.equal(e.count('POST'),1); e.sync(); const before=e.count('GET')
  button(e.tree(),'Recuperar lecturas').props.onClick(); await tick(); e.render()
  assert.equal(e.count('GET')-before,2); assert.equal(e.count('POST'),1); assert.equal(e.form().props.disabled,false)
  assert.equal(e.form().props.animal.farm_id,farms[1].id); assert.equal(e.form().props.animal.lot_id,lots[1].id)
  const next={...payload,origin_farm_id:farms[1].id,origin_lot_id:lots[1].id,destination_farm_id:farms[0].id,destination_lot_id:lots[0].id,date:'2026-01-02'}
  e.queue('POST',{data:{...next,id:id(61),origin_status_id:statusId}}); e.sync([{...next,id:id(61),origin_status_id:statusId},record],animal)
  await e.form().props.onCreate(next); assert.equal(e.count('POST'),2)
  assert.equal(JSON.parse(e.calls.filter(c=>c.method==='POST')[1].body).origin_lot_id,lots[1].id)
})

test('two synchronous CREATE actions and pending clicks issue exactly one POST', async () => {
  const e=env(); await e.ready(); const d=deferred(); e.queue('POST',()=>d.promise); e.sync()
  const create=e.form().props.onCreate; const first=create(payload); await create(payload); e.render(); await e.form().props.onCreate(payload)
  assert.equal(e.count('POST'),1); d.resolve({data:record}); await first; e.render()
  assert.match(text(e.tree()),/Movimiento registrado correctamente/)
})

test('incorrect refresh Animal ID never unlocks another CREATE', async () => {
  const e=env(); await e.ready(); e.queue('POST',{data:record}); e.sync([record],{...refreshed,id:id(99)})
  await e.form().props.onCreate(payload); e.render()
  assert.equal(e.updates.length,0); assert.equal(e.form().props.disabled,true)
  assert.match(text(e.tree()),/Movimiento registrado correctamente/)
})

test('known rejection allows retry and does not enter uncertainty', async () => {
  const e=env(); await e.ready(); e.queue('POST',{status:400,data:{detail:'Ubicación incorrecta'}})
  await assert.rejects(e.form().props.onCreate(payload)); e.render()
  assert.equal(e.form().props.disabled,false); assert.doesNotMatch(text(e.tree()),/Resultado incierto/)
})

for(const stage of ['initial','POST','refresh']) {
  test(`A→B during ${stage}: aborted/late results never apply; A→B→A retains unresolved attempt`,async()=>{
    const e=env(), d=deferred(); let pending
    if(stage==='initial') { e.queue(histPath,()=>d.promise); e.queue('/api/catalogs/movement-types',{data:types});e.queue('/api/farms/',{data:farms});e.queue('/api/lots/',{data:lots});e.render() }
    else { await e.ready(); e.queue('POST',stage==='POST'?()=>d.promise:{data:record}); if(stage==='refresh'){e.queue(histPath,()=>d.promise);e.queue(animalPath,{data:refreshed})} pending=e.form().props.onCreate(payload);await tick() }
    e.h.unmount(); assert.ok(e.calls.some(c=>c.signal.aborted))
    d.resolve({data:stage==='POST'?record:[record]}); if(pending) await pending; await tick(); assert.equal(e.updates.length,0)
    const b=env(); await b.ready({animalId:id(99),animal:{...animal,id:id(99)}}); assert.equal(b.history().props.history.length,0)
    if(stage==='POST') assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1,organizationId,animalId)).phase,'uncertain')
    if(stage==='refresh') assert.equal(e.protocol.getAttempt(e.protocol.attemptKey(1,organizationId,animalId)).phase,'confirmed')
  })
}
for(const logout of [false,true]) test(`session revision / logout ${logout} ignores late POST`,async()=>{
  const e=env();await e.ready();const d=deferred();e.queue('POST',()=>d.promise);const pending=e.form().props.onCreate(payload)
  e.changeSession(logout);d.resolve({data:record});await pending;e.render();assert.equal(e.updates.length,0);assert.equal(e.count('GET'),4)
})

test('out of order initial history cannot overwrite newer synchronization',async()=>{
  const e=env(),d=deferred()
  const key=e.protocol.attemptKey(1,organizationId,animalId)
  e.protocol.beginAttempt(key,payload);e.protocol.setAttemptPhase(key,'uncertain')
  e.queue(histPath,()=>d.promise);e.queue('/api/catalogs/movement-types',{data:types});e.queue('/api/farms/',{data:farms});e.queue('/api/lots/',{data:lots})
  e.render();await tick();e.render();e.sync([record])
  button(e.tree(),'Recuperar lecturas').props.onClick();await tick();e.render()
  assert.equal(e.history().props.history[0].id,record.id)
  d.resolve({data:[{...record,id:id(90),date:'2025-01-01'}]});await tick();e.render()
  assert.equal(e.history().props.history[0].id,record.id);assert.equal(e.count('POST'),0)
})

test('A?B?A remount retains uncertainty and forbids new POST after read recovery',async()=>{
  const a=env();await a.ready();a.queue('POST',{status:503});await a.form().props.onCreate(payload);a.h.unmount()
  const b=env(a.protocol);await b.ready({animalId:id(99),animal:{...animal,id:id(99)}});assert.equal(b.form().props.disabled,false);b.h.unmount()
  const returned=env(a.protocol);await returned.ready();assert.equal(returned.form().props.disabled,true)
  await returned.form().props.onCreate(payload);assert.equal(returned.count('POST'),0)
  returned.sync([],animal);button(returned.tree(),'Recuperar lecturas').props.onClick();await tick();returned.render()
  assert.equal(returned.form().props.disabled,true);assert.doesNotMatch(text(returned.tree()),/Movimiento registrado correctamente/)
})

for(const stage of ['history','catalogs','refresh']) test(`session change rejects late ${stage}`,async()=>{
  const e=env(),d=deferred();let pending
  if(stage==='refresh'){await e.ready();e.queue('POST',{data:record});e.queue(histPath,()=>d.promise);e.queue(animalPath,{data:refreshed});pending=e.form().props.onCreate(payload);await tick()}
  else {e.queue(histPath,stage==='history'?()=>d.promise:{data:[]});e.queue('/api/catalogs/movement-types',stage==='catalogs'?()=>d.promise:{data:types});e.queue('/api/farms/',{data:farms});e.queue('/api/lots/',{data:lots});e.render()}
  e.changeSession();d.resolve({data:stage==='catalogs'?types:[record]});if(pending)await pending;await tick()
  assert.equal(e.updates.length,0);e.render();assert.equal(e.history().props.history.length,stage==='refresh'?1:0)
  if(stage==='catalogs')assert.equal(e.form(),undefined)
})

test('POST confirmation requires every sent field and origin status to match',async()=>{
  for(const key of ['animal_id','movement_type_id','origin_status_id','origin_farm_id','origin_lot_id','destination_farm_id','destination_lot_id','date','reason','notes']){
    const e=env();const value=key==='date'?'2026-01-02':key==='reason'||key==='notes'?'other':id(99)
    e.queue('POST',{data:{...record,[key]:value}})
    await assert.rejects(e.service.createAnimalMovement(payload,statusId,'token',new AbortController().signal))
  }
})

test('POST success with changed status is used by next CREATE',async()=>{
  const e=env();await e.ready();e.queue('POST',{data:record});const changed={...refreshed,status_id:id(80),status:'OTHER'};e.sync([record],changed)
  await e.form().props.onCreate(payload);e.render();assert.equal(e.form().props.animal.status_id,id(80))
  const next={...payload,date:'2026-01-02',origin_farm_id:farms[1].id,origin_lot_id:lots[1].id,destination_farm_id:farms[0].id,destination_lot_id:lots[0].id}
  e.queue('POST',{data:{...next,id:id(61),origin_status_id:id(80)}});e.sync([{...next,id:id(61),origin_status_id:id(80)},record],{...animal,status_id:id(80),status:'OTHER'})
  await e.form().props.onCreate(next);e.render();assert.equal(e.count('POST'),2);assert.doesNotMatch(text(e.tree()),/Resultado incierto/)
})

test('stale CREATE handler cannot submit the pre-refresh origin',async()=>{
  const e=env();await e.ready();const oldCreate=e.form().props.onCreate
  e.queue('POST',{data:record});e.sync();await oldCreate(payload)
  await assert.rejects(oldCreate({...payload,date:'2026-01-02'}))
  assert.equal(e.count('POST'),1)
})

function formEnv(code='TRANSFER', location=true,lastDate='') {
  const h=harness(),calls=[]
  const module=load('./components/AnimalMovementForm.tsx',{react:h.react,'react/jsx-runtime':jsx,'../../components/FieldError':mod(()=>null),'../../lib/api-errors':{fieldErrorAttributes:()=>({}),normalizeApiError:()=>({message:'error',fieldErrors:{}})},'../validation':validation})
  const props={animalId,animal:location?animal:{...animal,farm_id:null,lot_id:null},types,farms,lots,lastDate,disabled:false,onCreate:async p=>{calls.push(p)}}
  let tree;const render=()=>tree=h.render(module.default,props)
  const change=(control,value)=>{nodes(tree).find(n=>n.props?.id===control).props.onChange({target:{value}});render()}
  render();change('movement-type',types.find(t=>t.code===code).id);change('movement-date','2026-01-01')
  if(!['EXIT','SALE'].includes(code)){change('movement-destination-farm',farms[1].id);change('movement-destination-lot',lots[1].id)}
  return {h,calls,props,render,change,tree:()=>tree,submit:()=>find(tree,'form').props.onSubmit({preventDefault(){}})}
}
for(const code of ['TRANSFER','ENTRY','PURCHASE','EXIT','SALE']) test(`form preserves ${code} payload rules`,async()=>{
  const e=formEnv(code,!['ENTRY','PURCHASE'].includes(code));await e.submit();assert.equal(e.calls.length,1)
  assert.equal(e.calls[0].origin_farm_id,['ENTRY','PURCHASE'].includes(code)?null:farms[0].id)
  assert.equal(e.calls[0].destination_farm_id,['EXIT','SALE'].includes(code)?null:farms[1].id)
})
for(const kind of ['future','same-date','earlier-date','same-location','missing-lot','entry-located','purchase-located','invalid-date','unknown-id']) test(`form rejects ${kind}`,async()=>{
  const e=formEnv(kind==='entry-located'?'ENTRY':kind==='purchase-located'?'PURCHASE':'TRANSFER',true,['same-date','earlier-date'].includes(kind)?'2026-01-01':'')
  if(kind==='future')e.change('movement-date','9999-01-01')
  if(kind==='earlier-date')e.change('movement-date','2025-12-31')
  if(kind==='invalid-date')e.change('movement-date','2026-02-30')
  if(kind==='unknown-id')e.change('movement-type',id(999))
  if(kind==='same-location'){e.change('movement-destination-farm',farms[0].id);e.change('movement-destination-lot',lots[0].id)}
  if(kind==='missing-lot')e.change('movement-destination-lot','')
  await e.submit();assert.equal(e.calls.length,0)
})
test('real form two synchronous submit events and pending click call create once',async()=>{
  const e=formEnv(),d=deferred();e.props.onCreate=async p=>{e.calls.push(p);await d.promise};e.render()
  const handler=find(e.tree(),'form').props.onSubmit, event={preventDefault(){}}
  const first=handler(event);await handler(event);e.render();await e.submit();assert.equal(e.calls.length,1);d.resolve();await first
})

test('form retains UTC date boundary, text normalization and same-farm transfer',async()=>{
  const e=formEnv();assert.equal(nodes(e.tree()).find(n=>n.props?.id==='movement-date').props.max,new Date().toISOString().slice(0,10))
  e.change('movement-reason','  Motivo  ');e.change('movement-notes','  Notas  ')
  const localLot={...lots[1],farm_id:farms[0].id};e.props.lots=[lots[0],localLot];e.render()
  e.change('movement-destination-farm',farms[0].id);e.change('movement-destination-lot',localLot.id)
  await e.submit();assert.equal(e.calls.length,1);assert.equal(e.calls[0].reason,'Motivo');assert.equal(e.calls[0].notes,'Notas')
})

test('unknown active catalogue code retains existing generic behavior',async()=>{
  const e=formEnv();e.props.types=[...types,{id:id(95),code:'OTHER',name:'Other'}];e.render()
  e.change('movement-type',id(95));await e.submit()
  assert.equal(e.calls.length,1);assert.equal(e.calls[0].origin_farm_id,null);assert.equal(e.calls[0].destination_farm_id,null)
})
