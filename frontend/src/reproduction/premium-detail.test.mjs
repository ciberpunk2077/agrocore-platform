import assert from 'node:assert/strict'
import test from 'node:test'
import * as jsx from 'react/jsx-runtime'
import { renderToStaticMarkup } from 'react-dom/server'
import { load, harness, tick, deferred, nodes, text, mod } from '../breeding/test-support.mjs'
import { detailImports, labelImports } from './test-support.mjs'

const ui = detailImports['../../reproduction/RecordDetail']
const id = n => `00000000-0000-0000-0000-${String(n).padStart(12,'0')}`
const base = {id:id(1),animal_id:id(2),mother_id:id(2),male_id:id(3),breeding_type_id:id(4),breeding_id:id(5),pregnancy_id:id(6),calf_id:id(7),calf_gender_id:id(8),date:'2026-01-02',diagnosis_date:'2026-02-03',expected_birth:'2026-10-05',birth_date:'2026-10-04',technician:'Técnico real',birth_weight:'0.00',status:'FINISHED',confirmed:false,alive:false,dystocia:true,notes:'Notas completas\nSegunda línea'}
const animalLabel = animal => [animal.name,animal.internal_id].filter(Boolean).join(' · ') || animal.id

for (const [kind,path,stateKey] of [['breeding','BreedingHistory','eventId'],['pregnancy','PregnancyHistory','pregnancyId'],['births','BirthHistory','birthId']]) {
  const History = load(`../${kind}/components/${path}.tsx`, {...detailImports,'react/jsx-runtime':jsx,'../breeding.service':{animalLabel},'../../auth/WriteOnly':mod(()=>null)}).default
  const props = {history:[{...base,notes:'cached notes'}],types:[{id:id(4),name:'Monta natural'}],animals:[{id:id(3),name:'Toro Roble',internal_id:'M-01'},{id:id(7),name:'Cría Ceiba',internal_id:'C-01'}],genders:[{id:id(8),name:'Hembra'}],eventLabels:new Map([[id(5),'02/01/2026 · Monta natural']]),disabled:true,onAbort(){},onOpenDetail(){},onCloseDetail(){}}
  test(`${kind}: full-width independent named panel, resolved labels and fresh data only`,()=>{
    const tree = History({...props,detail:{status:'success',[stateKey]:base.id,record:base}})
    const panel = nodes(tree).find(n=>n.props?.className==='repro-detail')
    assert.ok(tree.props.children.includes(panel),'panel is a direct child outside the cards')
    assert.equal(nodes(panel).filter(n=>n.type==='dl').length,1)
    assert.match(text(panel),/Notas completas/);assert.doesNotMatch(text(panel),/cached notes/)
    assert.equal(nodes(tree).filter(n=>n.type==='details').length,0)
    assert.equal(nodes(panel).filter(n=>n.type==='button').length,1)
    const html=renderToStaticMarkup(panel)
    assert.match(html,kind==='breeding'?/Toro Roble/:kind==='pregnancy'?/Monta natural/:/Cría Ceiba/)
    if(kind==='births'){assert.match(html,/Hembra/);assert.match(html,/0.00 kg/);assert.match(html,/No viva/)}
  })
  test(`${kind}: missing relations remain registered, UUID is secondary, notes use Sin datos`,()=>{
    const tree=History({...props,types:[],animals:[],genders:[],eventLabels:new Map(),detail:{status:'success',[stateKey]:base.id,record:{...base,notes:' ',technician:null,expected_birth:null}}})
    const panel=nodes(tree).find(n=>n.props?.className==='repro-detail')
    const html=renderToStaticMarkup(panel)
    assert.match(html,/referencia registrada/);assert.match(html,/repro-reference__id/);assert.match(html,/Sin datos/)
    assert.doesNotMatch(html,/no disponible|No existe|No registrada/)
  })
}

function refs(services={},h=harness(),session={getSession:()=>({access:'token'}),getSessionRevision:()=>1}) {
  const resolver=load('../reproduction/references.ts',{...labelImports,'../breeding/breeding.service':{animalLabel,...services}})
  return {h,...resolver,...load('../reproduction/ReferenceValue.tsx',{react:h.react,'react/jsx-runtime':jsx,'../auth/session':session,'./references':resolver})}
}
test('relation resolution uses existing services and actual gender names, never catalog UUID as label',async()=>{
  const calls=[]
  const r=refs({getBreedingAnimal:async(...args)=>{calls.push(args);return{id:id(3),name:'Toro',internal_id:'M-01'}},getBreedingGenders:async()=>[{id:id(8),name:'Hembra'}],getBreedingTypes:async()=>[{id:id(4),name:'Monta natural'}],getBreedingEvent:async(...args)=>{calls.push(args);return base}})
  const signal=new AbortController().signal
  assert.equal(await r.resolveReference('animal',id(3),undefined,'token',signal),'Toro · M-01')
  assert.equal(await r.resolveReference('gender',id(8),undefined,'token',signal),'Hembra')
  assert.equal(await r.resolveReference('event',id(5),id(2),'token',signal),'Servicio del 02/01/2026 · Monta natural')
  assert.equal(calls[1][1],id(2));assert.equal(calls[1][3],signal)
})
test('known labels do not issue GET; null relationships do not create reference components',()=>{
  let calls=0
  const r=refs({getBreedingAnimal:async()=>{calls++;return base}})
  r.h.render(r.default,{kind:'animal',id:id(3),label:'Toro conocido',children:'fallback'})
  assert.equal(calls,0);assert.equal(ui.reference('animal',null),'Sin datos')
})
test('unresolved GET preserves explanatory fallback; aborted/session-stale results cannot publish a name',async()=>{
  let revision=1
  const response=deferred()
  const r=refs({getBreedingAnimal:()=>response.promise},harness(),{getSession:()=>({access:'token'}),getSessionRevision:()=>revision})
  const props={kind:'animal',id:id(3),children:'Referencia registrada'}
  r.h.render(r.default,props);revision++
  response.resolve({id:id(3),name:'Nombre tardío'});await tick()
  assert.equal(r.h.render(r.default,props),'Referencia registrada')
  r.h.unmount()
  const failed=refs({getBreedingAnimal:async()=>{throw Error('404')}})
  failed.h.render(failed.default,props);await tick()
  assert.equal(failed.h.render(failed.default,props),'Referencia registrada')
})
test('closing and Escape return to the trigger with no write controls',()=>{
  let closed=0
  const panel=ui.recordDetail({kind:'birth',id:id(1),title:'Parto',onClose:()=>closed++,onRetry(){}})
  nodes(panel).find(n=>n.type==='button').props.onClick();assert.equal(closed,1)
  panel.props.onKeyDown({key:'Escape',stopPropagation(){}});assert.equal(closed,2)
  assert.doesNotMatch(text(panel),/Guardar|Editar|Eliminar|Registrar aborto/)
})

test('animal identification falls back to real official/electronic tags, never to the UUID',()=>{
  assert.equal(ui.animalName({id:id(3),official_tag:'OF-42'}),'OF-42')
  assert.equal(ui.animalName({id:id(3),electronic_tag:'RFID-7'}),'RFID-7')
  assert.doesNotMatch(ui.animalName({id:id(3)}),new RegExp(id(3)))
})
