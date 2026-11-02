import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, nodes, text, tick, deferred, mod } from '../breeding/test-support.mjs'
const id = n => `${String(n).padStart(8,'0')}-1111-1111-1111-111111111111`
const logic = load('../dashboard/drilldown.ts', {})
const bv = load('../breeding/validation.ts', {})
const pv = load('../pregnancy/validation.ts', { '../breeding/validation': bv })
const birthsValidation = load('../births/validation.ts', { '../breeding/validation': bv })
const vv = load('../vaccinations/validation.ts', { './civil-date': load('../vaccinations/civil-date.ts', {}) })
const presentation = load('../dashboard/presentation.ts', {})
const dv = load('../dashboard/validation.ts', { '../breeding/validation': bv })
const animal = { id:id(1),name:'Luna',internal_id:'A-01',gender_code:'F',is_active:false }
const pregnancy = {id:id(2),animal_id:id(1),breeding_id:id(3),diagnosis_date:'2026-09-01',expected_birth:'2026-10-20',confirmed:true,status:'ACTIVE',notes:null}
const breeding = {id:id(3),animal_id:id(1),male_id:null,breeding_type_id:id(4),date:'2026-01-01',expected_birth:null,technician:null,notes:null}
const birth = {id:id(5),mother_id:id(1),pregnancy_id:id(2),calf_id:null,calf_gender_id:null,birth_date:'2026-10-01',birth_weight:'30',alive:false,dystocia:false,notes:null}
const vaccination = {id:id(6),animal_id:id(1),vaccine_name:'Vacuna real',application_date:'2026-09-01',next_application_date:'2026-10-20',dose:'1',batch:null,veterinarian:null,notes:null,is_active:true}
function service(overrides = {}, count = 1) {
  const calls = [], fixtures = { '/dashboard/summary': {total_animals:10,active_animals:8,pregnancies:count,births_this_month:count,upcoming_births:count,vaccinations_due:count,average_weight:null},
    '/dashboard/upcoming-births': [{animal_id:id(1),animal:'A-01',expected_birth:'2026-10-20'}], '/pregnancies/':[pregnancy], '/breeding/':[breeding], '/births/':[birth], '/vaccinations/':[vaccination], '/animals/parents/candidates':[animal], ...overrides }
  const api = { apiRequest: async (path, options) => { calls.push({path,...options}); assert.equal(options.accessToken,'fixture'); assert.ok(options.signal instanceof AbortSignal); if(fixtures[path] instanceof Error)throw fixtures[path]; assert.ok(path in fixtures,path); return fixtures[path] } }
  const summary = load('../dashboard/dashboard.service.ts', { '../lib/api':api, './validation':dv })
  const apiService = load('../dashboard/drilldown.service.ts', { '../lib/api':api, './dashboard.service':summary, '../breeding/validation':bv, '../pregnancy/validation':pv, '../births/validation':birthsValidation, '../vaccinations/validation':vv, './presentation':presentation, './drilldown':logic })
  return {calls, fixtures, get:(kind,today='2026-10-20')=>apiService.getDrilldown(kind,today,'fixture',new AbortController().signal)}
}
for(const kind of Object.keys(logic.indicators))test(`${kind}: real endpoints, exact one-record KPI and no writes`,async()=>{
  const e=service(), result=await e.get(kind);assert.equal(result.expected,1);assert.equal(result.rows.length,1);assert.equal(result.limitation,null)
  assert.equal(new Set(e.calls.map(c=>c.path)).size,e.calls.length);assert.ok(e.calls.every(c=>!c.method||c.method==='GET'))
})
test('gestations exclude unconfirmed, finished and aborted without deduplicating animals',async()=>{
  const rows=[pregnancy,{...pregnancy,id:id(20)},...['FINISHED','ABORTED'].map((status,i)=>({...pregnancy,id:id(30+i),status})),{...pregnancy,id:id(40),confirmed:false}]
  const r=await service({'/pregnancies/':rows},2).get('pregnancies');assert.equal(r.rows.length,2);assert.equal(new Set(r.rows.map(r=>r.animalId)).size,1)
})
test('month filter is civil year/month, including all dates of that month and non-live births',async()=>{
  const records=['2026-10-01','2026-10-31','2025-10-20','2026-09-30','2026-11-01'].map((birth_date,i)=>({...birth,id:id(50+i),birth_date}))
  const r=await service({'/births/':records},2).get('births_this_month');assert.equal(r.rows.length,2);assert.equal(r.rows[0].status,'No vivo')
})
test('vaccinations include overdue and today, exclude future and null next applications',async()=>{
  const records=['2026-10-19','2026-10-20','2026-10-21',null].map((next_application_date,i)=>({...vaccination,id:id(60+i),next_application_date}))
  const r=await service({'/vaccinations/':records},2).get('vaccinations_due');assert.equal(r.rows.length,2);assert.equal(r.rows[0].status,'Vencida');assert.equal(r.rows[1].status,'Vence hoy')
})
test('upcoming births include today/+30 and preserve repeated animal rows',async()=>{
  const r=await service({'/dashboard/upcoming-births':[{animal_id:id(1),animal:'A',expected_birth:'2026-10-20'},{animal_id:id(1),animal:'A',expected_birth:'2026-11-19'}]},2).get('upcoming_births')
  assert.equal(r.rows.length,2);assert.equal(r.rows[1].cells[1].value,'En 30 días')
})
test('business day change updates due definition; no browser clock fallback',async()=>{
  const e=service();assert.equal((await e.get('vaccinations_due','2026-10-19')).rows.length,0)
  assert.ok((await e.get('vaccinations_due','2026-10-19')).limitation)
  await assert.rejects(e.get('vaccinations_due','invalid'))
})
for(const kind of Object.keys(logic.indicators))test(`${kind}: mismatched counts never publish a partial/false equivalent`,async()=>{
  const r=await service({},2).get(kind);assert.equal(r.expected,2);assert.equal(r.rows.length,0);assert.ok(r.limitation)
})
test('archived or foreign/unavailable related IDs block publication, even if aggregate could match',async()=>{
  for(const[kind,overrides]of[['pregnancies',{'/breeding/':[]}],['births_this_month',{'/pregnancies/':[]}],['vaccinations_due',{'/animals/parents/candidates':[]}]]){
    const r=await service(overrides).get(kind);assert.equal(r.rows.length,0);assert.match(r.limitation,/relaciones/)
  }
})
test('missing/foreign calf cannot leak a technical ID or be treated as absent',async()=>{
  const r=await service({'/births/':[{...birth,calf_id:id(999)}]}).get('births_this_month');assert.equal(r.rows.length,0);assert.ok(r.limitation)
})
test('authorized inactive animals resolve names, UUID-only names use an explanatory label',async()=>{
  assert.equal((await service().get('pregnancies')).rows[0].animal,'Luna · A-01')
  const r=await service({'/dashboard/upcoming-births':[{animal_id:id(1),animal:id(1),expected_birth:'2026-10-20'}]}).get('upcoming_births');assert.equal(r.rows[0].animal,'Identificación no disponible')
})
test('zero KPI and empty complete response remain a genuine empty result',async()=>{
  const r=await service({'/dashboard/upcoming-births':[]},0).get('upcoming_births');assert.equal(r.expected,0);assert.equal(r.limitation,null);assert.equal(r.rows.length,0)
})
test('wrong day window, malformed envelopes, duplicate IDs and network errors are not hidden',async()=>{
  assert.ok((await service({'/dashboard/upcoming-births':[{animal_id:id(1),animal:'A',expected_birth:'2026-11-20'}]}).get('upcoming_births')).limitation)
  for(const data of[{results:[pregnancy]},[pregnancy,pregnancy],[{...pregnancy,confirmed:null}],new Error('network')])await assert.rejects(service({'/pregnancies/':data}).get('pregnancies'))
})
test('indicator allowlist rejects URL-controlled tenant names and prototype properties',()=>{
  for(const value of['__proto__','organization','org-other','unknown',undefined])assert.equal(logic.isIndicator(value),false)
})
const ui=load('../ui/components.tsx',{'react/jsx-runtime':jsx}), Link=props=>jsx.jsx('a',{...props,href:props.to})
const Results=load('../dashboard/components/DrilldownResults.tsx',{'react/jsx-runtime':jsx,react:{useState:()=>{}},'react-router-dom':{Link},'../../ui/components':ui})
const row={key:id(1),animalId:id(1),animal:'Luna',date:'2026-10-20',status:'Vence hoy',cells:[{label:'Vacuna',value:'Vacuna real'}]}
const action=(tree,label)=>nodes(tree).find(n=>n.type===ui.Button&&text(n)===label)
const control=(tree,id)=>nodes(tree).find(n=>n.type===ui.Field&&n.props.id===id).props.children({id})
function resultEnv(rows=Array.from({length:50},(_,i)=>({...row,key:id(100+i),animal:`Luna ${i}`}))){
  const h=harness();const Component=load('../dashboard/components/DrilldownResults.tsx',{'react/jsx-runtime':jsx,react:h.react,'react-router-dom':{Link},'../../ui/components':ui}).default
  return{render:()=>h.render(Component,{rows,expected:rows.length})}
}
test('results share global search/date filters and page while switching table/cards',()=>{
  const e=resultEnv();let tree=e.render();action(tree,'Siguiente').props.onClick();tree=e.render();const tableLinks=nodes(tree).filter(n=>n.type===Link).length;assert.equal(tableLinks,24)
  action(tree,'Tarjetas').props.onClick();tree=e.render();assert.equal(nodes(tree).filter(n=>n.type===Link).length,24);assert.match(text(tree),/Página 2 de 3/)
  control(tree,'drill-search').props.onChange({target:{value:'Luna 49'}});tree=e.render();assert.equal(nodes(tree).filter(n=>n.type===Link).length,1)
  action(tree,'Tabla').props.onClick();tree=e.render();assert.equal(control(tree,'drill-search').props.value,'Luna 49');assert.match(text(tree),/Página 1 de 1/)
  action(tree,'Limpiar filtros').props.onClick();tree=e.render();assert.equal(control(tree,'drill-search').props.value,'')
  control(tree,'drill-date').props.onChange({target:{value:'2026-10-19'}});tree=e.render();assert.match(text(tree),/No hay resultados/)
})
test('result links use actual animal ID, unique animals are separate from record count, no write actions',()=>{
  const e=resultEnv([row,{...row,key:id(2)}]);const html=renderToStaticMarkup(e.render());assert.match(html,/2 registros · 1 animal distinto/);assert.ok(html.includes(`/animals/${id(1)}`));assert.doesNotMatch(html,/\/new|\/edit|Eliminar|Modificar/)
})
function scopeEnv(){
  const h=harness(), pending=[],calls=[],context={revision:1,org:id(10),fresh:true,canRead:true,indicator:'pregnancies'},lease={}
  const Component=load('../pages/DashboardDrilldownPage.tsx',{'react/jsx-runtime':jsx,react:h.react,'react-router-dom':{Link,useParams:()=>({indicator:context.indicator,organization:'ignored'})},
    '../auth/current-context':{useCurrentContext:()=>({status:'loaded',canRead:context.canRead,currentOrganization:{id:context.org},businessTimeReady:true,businessTimeLease:lease,data:{business_time:{business_today:'2026-10-20'}},isCurrentOrganization:org=>org===context.org})},
    '../auth/useSession':{useSession:()=>({session:{},revision:context.revision})},'../auth/session':{getSession:()=>({access:'fixture'}),getSessionRevision:()=>context.revision},'../auth/business-time':{businessTimeIsFresh:()=>context.fresh},
    '../ui/components':ui,'../dashboard/drilldown':logic,'../dashboard/components/DrilldownResults':mod(Results.default),
    '../dashboard/drilldown.service':{getDrilldown:(...args)=>{calls.push(args);const d=deferred();pending.push(d);return d.promise}},
  })
  const props={indicator:'pregnancies',today:'2026-10-20',revision:1,organizationId:id(10),lease,isCurrentOrganization:org=>org===context.org}
  return{Component,context,calls,pending,props,render:()=>h.render(Component.DrilldownScope,props),unmount:h.unmount}
}
for(const reason of['tenant','session','unmount'])test(`late drill response ignored after ${reason}`,async()=>{
  const e=scopeEnv();e.render();if(reason==='tenant')e.context.org=id(999);if(reason==='session')e.context.revision++;if(reason==='unmount')e.unmount()
  e.pending[0].resolve({expected:1,rows:[row],limitation:null});await tick();assert.doesNotMatch(text(e.render()),/Coincide/);assert.ok(e.calls[0][3] instanceof AbortSignal)
})
test('lease expiry rejects a late snapshot and retry only performs reads',async()=>{
  const e=scopeEnv();e.render();e.context.fresh=false;e.pending[0].resolve({expected:1,rows:[row],limitation:null});await tick();let tree=e.render();assert.match(text(tree),/caducó/)
  e.context.fresh=true;action(tree,'Reintentar').props.onClick();e.render();assert.equal(e.calls.length,2)
  e.pending[1].resolve({expected:1,rows:[row],limitation:null});await tick();tree=e.render();assert.ok(nodes(tree).some(n=>n.type===Results.default))
})
test('wrapper identity includes actual context tenant, indicator and business day; URL tenant ignored',()=>{
  const e=scopeEnv();const first=e.Component.default();assert.equal(first.props.organizationId,id(10));assert.match(first.key,/pregnancies:2026-10-20/)
  e.context.org=id(999);assert.notEqual(e.Component.default().key,first.key);e.context.org=id(10);e.context.revision++;assert.notEqual(e.Component.default().key,first.key)
})

test('no read permission or unsupported route cannot initiate dataset requests',()=>{
  const e=scopeEnv();e.context.canRead=false;assert.equal(e.Component.default().type,ui.ErrorState);assert.equal(e.calls.length,0)
  e.context.canRead=true;e.context.indicator='__proto__';assert.equal(e.Component.default().type,ui.ErrorState);assert.equal(e.calls.length,0)
})
for(const field of['indicator','today'])test(`changed ${field} cancels old response before publication`,async()=>{
  const e=scopeEnv();e.render();e.props[field]=field==='indicator'?'upcoming_births':'2026-10-21';e.render()
  assert.equal(e.calls[0][3].aborted,true);e.pending[0].resolve({expected:1,rows:[row],limitation:null});await tick()
  assert.equal(nodes(e.render()).some(n=>n.type===Results.default),false)
})
