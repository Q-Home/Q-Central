import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Server, ShieldCheck, RefreshCw, Send, CheckSquare, Square, LogOut, Activity, AlertTriangle, Home, CloudUpload, Search, ChevronRight, Eye, Bell, User, Cpu, HardDrive, Boxes, Menu} from 'lucide-react';
import './style.css';

const api = '/api';

function Badge({children,type='ok'}){return <span className={'badge '+type}>{children}</span>}
function pct(value){const n=Number(value); return Number.isFinite(n)?Math.round(n):null}
function MetricBar({label,value,type='blue'}){
  const shown=pct(value);
  return <div className="metric-line"><div className="metric-top"><span>{label}</span><strong>{shown===null?'-':`${shown}%`}</strong></div><div className="mini-bar"><i className={type} style={{width:`${shown===null?0:Math.min(100,shown)}%`}}/></div></div>
}
function Spark({type='blue'}){return <svg className={'spark '+type} viewBox="0 0 120 40" preserveAspectRatio="none"><polyline points="0,20 10,17 18,19 28,24 38,18 48,28 58,21 70,23 82,12 92,22 104,16 120,20" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/></svg>}
function StatCard({icon,label,value,sub,type='blue'}){return <article className="stat-card"><div className={'stat-icon '+type}>{icon}</div><div><span>{label}</span><strong>{value}</strong><p>{sub}</p></div></article>}
function NavButton({id,active,setActive,icon,label}){return <button className={active===id?'active':''} onClick={()=>setActive(id)}>{icon}<span>{label}</span></button>}

function App(){
  const [user,setUser]=useState(null);
  const [login,setLogin]=useState({username:'admin',password:''});
  const [devices,setDevices]=useState([]);
  const [monitoring,setMonitoring]=useState(null);
  const [activeTab,setActiveTab]=useState('dashboard');
  const [selected,setSelected]=useState({});
  const [query,setQuery]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [agentUpdate,setAgentUpdate]=useState({version:'',url:'',sha256:''});
  const [submitting,setSubmitting]=useState(false);

  async function apiFetch(path, options={}){return fetch(api+path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}})}
  async function checkSession(){const r=await apiFetch('/auth/me'); if(r.ok){setUser(await r.json()); await load(false)}}
  useEffect(()=>{checkSession()},[])
  useEffect(()=>{if(!user)return; const timer=setInterval(()=>load(false),30000); return()=>clearInterval(timer)},[user])

  async function loginAdmin(e){
    e.preventDefault(); setError(''); setNotice('');
    const r=await apiFetch('/auth/login',{method:'POST',body:JSON.stringify(login)});
    if(!r.ok){setError('Login mislukt. Controleer gebruikersnaam en wachtwoord.'); return}
    setUser(await r.json()); await load(false)
  }
  async function logout(){await apiFetch('/auth/logout',{method:'POST'}); setUser(null); setDevices([]); setMonitoring(null); setSelected({}); setNotice('Uitgelogd.')}
  async function load(clear=true){
    setError(''); if(clear)setNotice('');
    const r=await apiFetch('/devices');
    if(!r.ok){setError('Sessie verlopen of geen toegang. Log opnieuw in.'); setUser(null); return}
    setDevices(await r.json());
    const mr=await apiFetch('/monitoring/overview');
    if(mr.ok)setMonitoring(await mr.json())
  }

  const monitored=monitoring?.devices||[];
  const filtered=monitored.filter(d=>`${d.name||''} ${d.serial||''} ${d.customer||''} ${d.site||''}`.toLowerCase().includes(query.toLowerCase()));
  const primary=filtered[0]||monitored[0];
  const totals=monitoring?.totals||{};
  const online=totals.online??devices.filter(d=>d.status==='online').length;
  const pending=totals.pending??devices.filter(d=>!d.authorized).length;
  const alerts=totals.alerts??0;
  const offline=Math.max(0,(totals.devices??devices.length)-online);
  const selectedSerials=useMemo(()=>Object.entries(selected).filter(([,v])=>v).map(([k])=>k),[selected]);
  const allSelected=devices.length>0&&selectedSerials.length===devices.length;
  function toggle(serial){setSelected(s=>({...s,[serial]:!s[serial]}))}
  function toggleAll(){if(allSelected){setSelected({});return} const next={}; devices.forEach(d=>next[d.serial]=true); setSelected(next)}
  async function queueAgentUpdates(){
    setError(''); setNotice('');
    if(selectedSerials.length===0){setError('Selecteer minstens één device.'); return}
    if(!agentUpdate.url){setError('Agent update URL is verplicht.'); return}
    if(!agentUpdate.sha256){setError('SHA256 is verplicht voor productie-updates.'); return}
    setSubmitting(true);
    const results=[];
    for(const serial of selectedSerials){const r=await apiFetch('/jobs/agent-update',{method:'POST',body:JSON.stringify({serial,url:agentUpdate.url,sha256:agentUpdate.sha256,version:agentUpdate.version||null})}); results.push({serial,ok:r.ok})}
    setSubmitting(false);
    const failed=results.filter(r=>!r.ok);
    if(failed.length){setError('Sommige updates konden niet aangemaakt worden: '+failed.map(f=>f.serial).join(', ')); return}
    setNotice(`Agent update job aangemaakt voor ${results.length} device(s).`); await load(false)
  }

  if(!user){return <main className="auth-page"><section className="auth-card"><div className="brandmark">Q</div><h1>Q-Central</h1><p>Publieke admin login</p><form onSubmit={loginAdmin} className="auth-form"><label>Gebruikersnaam<input autoComplete="username" value={login.username} onChange={e=>setLogin({...login,username:e.target.value})}/></label><label>Wachtwoord<input type="password" autoComplete="current-password" value={login.password} onChange={e=>setLogin({...login,password:e.target.value})}/></label><button type="submit">Inloggen</button></form>{error&&<div className="error">{error}</div>}{notice&&<div className="notice">{notice}</div>}</section></main>}

  return <div className="app-shell">
    <aside className="sidebar"><div className="side-brand"><div className="brandmark">Q</div><strong>Q-Central</strong></div><nav><NavButton id="dashboard" active={activeTab} setActive={setActiveTab} icon={<Home size={19}/>} label="Dashboard"/><NavButton id="monitoring" active={activeTab} setActive={setActiveTab} icon={<Activity size={19}/>} label="Monitoring"/><NavButton id="ota" active={activeTab} setActive={setActiveTab} icon={<CloudUpload size={19}/>} label="OTA"/><NavButton id="devices" active={activeTab} setActive={setActiveTab} icon={<Server size={19}/>} label="Devices"/></nav><div className="side-status"><strong>Q-Central</strong><span>v1.0.2</span><p><i/> API Online</p><small>© 2026 Q-Home</small></div></aside>
    <main className="content">
      <header className="topbar"><div className="title-row"><button className="icon-button"><Menu size={22}/></button><div><h1>Q-Central</h1><p>Production control plane voor Q-Box devices</p></div></div><div className="top-actions"><button className="ghost" onClick={()=>load(false)}><RefreshCw size={17}/> Auto refresh: 30s <i className="dot"/></button><button className="ghost alert"><Bell size={17}/>{alerts>0&&<b>{alerts}</b>}</button><button className="ghost"><User size={17}/> {user.username}</button><button className="logout" onClick={logout}><LogOut size={17}/> Logout</button></div></header>
      {error&&<div className="error">{error}</div>}{notice&&<div className="notice">{notice}</div>}
      <section className="stats"><StatCard icon={<Server/>} label="Devices" value={devices.length} sub="Totaal geregistreerd" type="blue"/><StatCard icon={<ShieldCheck/>} label="Pending auth" value={pending} sub="Wachten op autorisatie" type="amber"/><StatCard icon={<Activity/>} label="Online" value={online} sub="Actief binnen 5 min" type="green"/><StatCard icon={<AlertTriangle/>} label="Alerts" value={alerts} sub="Actieve meldingen" type="red"/></section>

      {(activeTab==='dashboard'||activeTab==='monitoring')&&<>
        <section className="dashboard-grid"><article className="panel status-panel"><h2>Device status</h2><div className="donut-wrap"><div className="donut" style={{background:`conic-gradient(#43b85c 0 ${devices.length?online/devices.length*100:0}%, #e5eaf1 0 100%)`}}><span><strong>{devices.length}</strong>Totaal</span></div><div className="legend"><p><i className="green"/>Online <strong>{online} ({devices.length?Math.round(online/devices.length*100):0}%)</strong></p><p><i className="red"/>Offline <strong>{offline}</strong></p><p><i/>Unknown <strong>0</strong></p></div></div></article>
        <article className="panel monitor-table"><div className="panel-head"><h2>Monitoring overzicht</h2><label className="search"><Search size={17}/><input placeholder="Zoek device..." value={query} onChange={e=>setQuery(e.target.value)}/></label></div><table><thead><tr><th>Device</th><th>Status</th><th>CPU</th><th>RAM</th><th>Disk</th><th>Laatste seen</th><th>Alerts</th><th></th></tr></thead><tbody>{filtered.map(d=><tr key={d.serial}><td><strong>{d.name||d.serial}</strong><small>{d.serial}</small></td><td><Badge type={d.status==='online'?'ok':'off'}>{d.status}</Badge><small>{d.hostname||'-'}</small></td><td><MetricBar label="" value={d.cpu_percent}/></td><td><MetricBar label="" value={d.mem_percent} type="green"/></td><td><MetricBar label="" value={d.disk_percent} type="amber"/></td><td>{d.last_seen?new Date(d.last_seen).toLocaleString():'-'}</td><td>{d.disk_percent>=60?<Badge type="warn">1</Badge>:<Badge type="ok">0</Badge>}</td><td><ChevronRight size={18}/></td></tr>)}</tbody></table><footer>{filtered.length} van {monitored.length} devices</footer></article></section>
        {primary&&<section className="panel detail-panel"><div className="panel-head"><div><h2>{primary.name||primary.serial} <Badge type={primary.status==='online'?'ok':'off'}>{primary.status}</Badge></h2><p>Laatst gezien: {primary.last_seen?new Date(primary.last_seen).toLocaleString():'-'}</p></div><button className="ghost"><Eye size={16}/> Details vernieuwen</button></div><div className="detail-grid"><article><h3>Systeem informatie</h3><dl><dt>Hostname</dt><dd>{primary.hostname||'-'}</dd><dt>IP adres</dt><dd>{primary.ip_address||'-'}</dd><dt>Agent versie</dt><dd>{primary.agent_version||'-'}</dd><dt>Firmware</dt><dd>{primary.firmware||'-'}</dd></dl></article><article><h3>CPU</h3><strong className="big">{pct(primary.cpu_percent)??'-'}%</strong><Spark/><MetricBar label="" value={primary.cpu_percent}/><small>Q-Box runtime</small></article><article><h3>RAM</h3><strong className="big">{pct(primary.mem_percent)??'-'}%</strong><Spark type="green"/><MetricBar label="" value={primary.mem_percent} type="green"/></article><article><h3>Disk</h3><strong className="big">{pct(primary.disk_percent)??'-'}%</strong><Spark type="amber"/><MetricBar label="" value={primary.disk_percent} type="amber"/></article><article><h3>Apps ({(primary.apps||[]).length})</h3>{(primary.apps||[]).length?(primary.apps||[]).slice(0,5).map(a=><p className="app-pill" key={a}><Boxes size={14}/>{a}<Badge type="ok">running</Badge></p>):<p className="muted">Geen apps gemeld</p>}</article></div></section>}
        <section className="panel alerts-panel"><div className="panel-head"><h2>Recente alerts</h2><button className="ghost">Bekijk alle alerts</button></div><table><thead><tr><th>Tijd</th><th>Device</th><th>Level</th><th>Bericht</th><th></th></tr></thead><tbody>{filtered.filter(d=>d.disk_percent>=60||d.status!=='online').map(d=><tr key={d.serial}><td>{new Date().toLocaleString()}</td><td>{d.name||d.serial}</td><td><Badge type="warn">Warning</Badge></td><td>{d.status!=='online'?'Device offline':`Disk usage is above 60% (${pct(d.disk_percent)}%)`}</td><td><ChevronRight size={18}/></td></tr>)}</tbody></table></section>
      </>}

      {activeTab==='ota'&&<section className="panel"><h2>Agent update vanuit Q-Central</h2><p className="muted">Selecteer devices, kies een release artifact en queue een <code>agent_update</code> job.</p><div className="formgrid"><label>Nieuwe versie<input placeholder="bijv. 1.0.2" value={agentUpdate.version} onChange={e=>setAgentUpdate({...agentUpdate,version:e.target.value})}/></label><label>Artifact URL<input placeholder="https://github.com/Q-Home/Q-Central/releases/download/..." value={agentUpdate.url} onChange={e=>setAgentUpdate({...agentUpdate,url:e.target.value})}/></label><label>SHA256<input placeholder="verplicht" value={agentUpdate.sha256} onChange={e=>setAgentUpdate({...agentUpdate,sha256:e.target.value})}/></label></div><div className="actions"><button onClick={toggleAll}>{allSelected?<CheckSquare size={16}/>:<Square size={16}/>} {allSelected?'Deselecteer alles':'Selecteer alles'}</button><button disabled={submitting} onClick={queueAgentUpdates}><Send size={16}/> {submitting?'Bezig...':'Queue agent update'}</button><span className="muted">{selectedSerials.length} device(s) geselecteerd</span></div></section>}
      {(activeTab==='devices'||activeTab==='ota')&&<section className="panel"><h2>Device inventory</h2><table><thead><tr><th></th><th>Serial</th><th>Naam</th><th>Klant</th><th>Site</th><th>Firmware</th><th>Status</th></tr></thead><tbody>{devices.map(d=><tr key={d.serial}><td><input type="checkbox" checked={!!selected[d.serial]} onChange={()=>toggle(d.serial)}/></td><td><code>{d.serial}</code></td><td>{d.name||'-'}</td><td>{d.customer||'-'}</td><td>{d.site||'-'}</td><td>{d.firmware||'-'}</td><td><Badge type={d.status==='online'?'ok':d.status==='pending'?'warn':'off'}>{d.status}</Badge></td></tr>)}</tbody></table></section>}
    </main>
  </div>
}
createRoot(document.getElementById('root')).render(<App/>);
