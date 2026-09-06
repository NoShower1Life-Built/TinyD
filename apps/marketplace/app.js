const products=[
 {name:'Deterministic Research Agent',type:'Agents',icon:'R',desc:'Evidence-first research agent with replay-safe tool execution.',version:'2.4.1',rating:'4.9',installs:'18.4k',price:'Free'},
 {name:'Incident Response DAG',type:'Workflows',icon:'IR',desc:'Verified triage, containment, and post-incident workflow.',version:'1.8.0',rating:'4.8',installs:'9.7k',price:'$19/mo'},
 {name:'Postgres Snapshot Tool',type:'Tools',icon:'PG',desc:'Consistent snapshots with deterministic manifests and restore checks.',version:'3.1.2',rating:'5.0',installs:'7.2k',price:'Free'},
 {name:'Kafka Event Connector',type:'Connectors',icon:'K',desc:'Typed Kafka ingress and egress for TinyD event streams.',version:'2.0.4',rating:'4.9',installs:'14.1k',price:'Free'},
 {name:'OpenAI Gateway',type:'Connectors',icon:'AI',desc:'OpenAI-compatible gateway with tenant policy and usage metering.',version:'1.6.3',rating:'4.7',installs:'21.8k',price:'$29/mo'},
 {name:'VCIR Policy Pack',type:'Policies',icon:'V',desc:'Proof obligations and admission policies for verified execution.',version:'0.9.5',rating:'4.9',installs:'5.3k',price:'$49/mo'}
];
const state={filter:'All',query:'',sort:'featured'};
const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
function render(){let items=products.filter(p=>(state.filter==='All'||p.type===state.filter)&&(`${p.name} ${p.type} ${p.desc}`).toLowerCase().includes(state.query.toLowerCase()));if(state.sort==='rating')items.sort((a,b)=>b.rating-a.rating);if(state.sort==='newest')items.sort((a,b)=>b.version.localeCompare(a.version));$('#products').innerHTML=items.map(p=>`<article class="card"><div class="card-top"><div class="logo">${p.icon}</div><span class="verified">✓ VERIFIED</span></div><h3>${p.name}</h3><p>${p.desc}</p><div class="meta"><span>${p.type}</span><span>v${p.version}</span><span>★ ${p.rating}</span><span>${p.installs}</span><span class="price">${p.price}</span></div></article>`).join('')||'<div class="card"><h3>No packages found</h3><p>Try another search or category.</p></div>';}
function setFilter(f){state.filter=f;$$('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter===f));render();$('#featured').scrollIntoView({behavior:'smooth',block:'start'});}
$$('[data-filter]').forEach(b=>b.addEventListener('click',()=>setFilter(b.dataset.filter)));
$('#search').addEventListener('input',e=>{state.query=e.target.value;render()});
$('#sort').addEventListener('change',e=>{state.sort=e.target.value;render()});
$$('.view').forEach(b=>b.addEventListener('click',()=>{$$('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');$('#products').classList.toggle('list',b.dataset.view==='list')}));
$('#allCategories').addEventListener('click',()=>setFilter('All'));
$('#themeBtn').addEventListener('click',()=>document.body.classList.toggle('light'));
$('#dashboardBtn').addEventListener('click',()=>alert('Developer dashboard integration is ready for the TinyD control-plane route.'));
['publishTop','publishCta'].forEach(id=>$( '#'+id).addEventListener('click',()=>$('#publish').scrollIntoView({behavior:'smooth'})));
$('#docsBtn').addEventListener('click',()=>alert('Publishing guide: manifest → contract → verification → package → publish.'));
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement.tagName!=='INPUT'){e.preventDefault();$('#search').focus()}});
render();