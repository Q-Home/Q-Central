import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Server, ShieldCheck, UploadCloud, Boxes, RefreshCw, Send, CheckSquare, Square, LogOut, Activity, AlertTriangle, Cpu, HardDrive} from 'lucide-react';
import './style.css';

const api = '/api';
function Badge({children,type='ok'}){return <span className={'badge '+type}>{children}</span>}
function MetricBar({label,value}){
  const n = Number(value);
  const shown = Number.isFinite(n) ? Math.round(n) : null;
  const level = shown === null ? 'off' : shown >= 90 ? 'danger' : shown >= 75 ? 'warn' : 'ok';
  return <div className="metric"><div><span>{label}</span><strong>{shown === null ? '-' : `${shown}%`}</strong></div><div className="bar"><i className={level} style={{width: `${shown === null ? 0 : Math.min(100, shown)}%`}} /></div></div>
}
function App(){
  const [user,setUser]=useState(null);
  const [login,setLogin]=useState({username:'admin',password:''});
  const [devices,setDevices]=useState([]);
  const [monitoring,setMonitoring]=useState(null);
  const [activeTab,setActiveTab]=useState('dashboard');
  const [selected,setSelected]=useState({});
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [agentUpdate,setAgentUpdate]=useState({version:'',url:'',sha256:''});
  const [submitting,setSubmitting]=useState(false);

  async function apiFetch(path, options={}){
    return fetch(api+path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
  }

  async function checkSession(){
    const r=await apiFetch('/auth/me');
    if(r.ok){ setUser(await r.json()); await load(); }
  }
  useEffect(()=>{ checkSession(); },[]);
  useEffect(()=>{
    if(!user) return;
    const timer = setInterval(()=>load(false), 30000);
    return ()=>clearInterval(timer);
  },[user]);

  async function loginAdmin(e){
    e.preventDefault();
    setError(''); setNotice('');
    const r=await apiFetch('/auth/login',{method:'POST',body:JSON.stringify(login)});
    if(!r.ok){ setError('Login mislukt. Controleer gebruikersnaam en wachtwoord.'); return; }
    setUser(await r.json());
    await load();
  }

  async function logout(){
    await apiFetch('/auth/logout',{method:'POST'});
    setUser(null); setDevices([]); setMonitoring(null); setSelected({}); setNotice('Uitgelogd.');
  }

  async function load(showNotice=true){
    setError(''); if(showNotice) setNotice('');
    const r=await apiFetch('/devices');
    if(!r.ok){setError('Sessie verlopen of geen toegang. Log opnieuw in.'); setUser(null); return}
    const data=await r.json();
    setDevices(data);
    const mr=await apiFetch('/monitoring/overview');
    if(mr.ok){ setMonitoring(await mr.json()); }
  }

  const online=monitoring?.totals?.online ?? devices.filter(d=>d.status==='online').length;
  const pending=monitoring?.totals?.pending ?? devices.filter(d=>!d.authorized).length;
  const alerts=monitoring?.totals?.alerts ?? 0;
  const selectedSerials=useMemo(()=>Object.entries(selected).filter(([,v])=>v).map(([k])=>k),[selected]);
  const allSelected=devices.length>0 && selectedSerials.length===devices.length;

  function toggle(serial){ setSelected(s=>({...s,[serial]:!s[serial]})); }
  function toggleAll(){
    if(allSelected){ setSelected({}); return; }
    const next={}; devices.forEach(d=>{next[d.serial]=true}); setSelected(next);
  }

  async function queueAgentUpdates(){
    setError(''); setNotice('');
    if(selectedSerials.length===0){ setError('Selecteer minstens één device.'); return; }
    if(!agentUpdate.url){ setError('Agent update URL is verplicht.'); return; }
    if(!agentUpdate.sha256){ setError('SHA256 is verplicht voor productie-updates.'); return; }
    setSubmitting(true);
    const results=[];
    for(const serial of selectedSerials){
      const r=await apiFetch('/jobs/agent-update',{
        method:'POST',
        body:JSON.stringify({serial,url:agentUpdate.url,sha256:agentUpdate.sha256,version:agentUpdate.version||null})
      });
      results.push({serial,ok:r.ok,text:r.ok?'queued':await r.text()});
    }
    setSubmitting(false);
    const failed=results.filter(r=>!r.ok);
    if(failed.length){ setError('Sommige updates konden niet aangemaakt worden: '+failed.map(f=>f.serial).join(', ')); return; }
    setNotice(`Agent update job aangemaakt voor ${results.length} device(s).`);
    await load(false);
  }

  if(!user){
    return <main className="auth-page">
      <section className="auth-card">
        <div className="logo">Q</div>
        <h1>Q-Central</h1>
        <p>Publieke admin login</p>
        <form onSubmit={loginAdmin} className="auth-form">
          <label>Gebruikersnaam<input autoComplete="username" value={login.username} onChange={e=>setLogin({...login,username:e.target.value})}/></label>
          <label>Wachtwoord<input type="password" autoComplete="current-password" value={login.password} onChange={e=>setLogin({...login,password:e.target.value})}/></label>
          <button type="submit">Inloggen</button>
        </form>
        {error && <div className="error">{error}</div>}
        {notice && <div className="notice">{notice}</div>}
      </section>
    </main>
  }

  return <main>
    <header><div className="logo">Q</div><div><h1>Q-Central</h1><p>Production control plane voor Q-Box devices</p></div><button className="logout" onClick={logout}><LogOut size={16}/> Logout</button></header>
    <section className="login"><button onClick={()=>load()}><RefreshCw size={16}/> Herladen</button><span className="muted">Aangemeld als {user.username}</span></section>
    <nav className="tabs"><button className={activeTab==='dashboard'?'active':''} onClick={()=>setActiveTab('dashboard')}>Dashboard</button><button className={activeTab==='monitoring'?'active':''} onClick={()=>setActiveTab('monitoring')}>Monitoring</button><button className={activeTab==='ota'?'active':''} onClick={()=>setActiveTab('ota')}>OTA</button><button className={activeTab==='devices'?'active':''} onClick={()=>setActiveTab('devices')}>Devices</button></nav>
    {error && <div className="error">{error}</div>}
    {notice && <div className="notice">{notice}</div>}
    <section className="stats"><Card icon={<Server/>} label="Devices" value={devices.length}/><Card icon={<ShieldCheck/>} label="Pending auth" value={pending}/><Card icon={<Activity/>} label="Online" value={online}/><Card icon={<AlertTriangle/>} label="Alerts" value={alerts}/></section>

    {activeTab === 'dashboard' && <section className="panel"><h2>Q-Central overzicht</h2><p className="muted">Gebruik de Monitoring-tab voor CPU, RAM, disk, agentversies en apps per Q-Box.</p></section>}

    {activeTab === 'monitoring' && <section className="panel"><h2>Monitoring</h2><p className="muted">Geïntegreerde monitoring op basis van Q-Box heartbeats. Vernieuwt automatisch elke 30 seconden.</p>
      <div className="monitor-grid">{(monitoring?.devices || []).map(d=><article className="device-card" key={d.serial}>
        <div className="device-head"><div><strong>{d.name || d.serial}</strong><span>{d.customer || '-'} · {d.site || '-'}</span></div><Badge type={d.status==='online'?'ok':d.status==='pending'?'warn':'off'}>{d.status}</Badge></div>
        <div className="device-meta"><span>{d.hostname || d.ip_address || '-'}</span><span>Agent {d.agent_version || '-'}</span><span>{d.firmware || '-'}</span></div>
        <MetricBar label="CPU" value={d.cpu_percent}/><MetricBar label="RAM" value={d.mem_percent}/><MetricBar label="Disk" value={d.disk_percent}/>
        <div className="apps"><Boxes size={15}/>{(d.apps || []).length ? d.apps.slice(0,6).join(', ') : 'Geen apps gemeld'}</div>
        <small>Laatst gezien: {d.last_seen ? new Date(d.last_seen).toLocaleString() : '-'}</small>
      </article>)}</div>
      {(!monitoring?.devices || monitoring.devices.length===0) && <p className="muted">Nog geen monitoringdata. Zodra een Q-Box heartbeat stuurt, verschijnt hij hier.</p>}
    </section>}

    {activeTab === 'ota' && <section className="panel"><h2>Agent update vanuit Q-Central</h2><p className="muted">Selecteer devices, kies een release artifact en queue een <code>agent_update</code> job. SHA256 is verplicht zodat agents alleen gecontroleerde artifacts installeren.</p>
      <div className="formgrid">
        <label>Nieuwe versie<input placeholder="bijv. 1.0.2" value={agentUpdate.version} onChange={e=>setAgentUpdate({...agentUpdate,version:e.target.value})}/></label>
        <label>Artifact URL<input placeholder="https://github.com/Q-Home/Q-Central/releases/download/.../qbox-agent.tar.gz" value={agentUpdate.url} onChange={e=>setAgentUpdate({...agentUpdate,url:e.target.value})}/></label>
        <label>SHA256<input placeholder="verplicht" value={agentUpdate.sha256} onChange={e=>setAgentUpdate({...agentUpdate,sha256:e.target.value})}/></label>
      </div>
      <div className="actions"><button onClick={toggleAll}>{allSelected?<CheckSquare size={16}/>:<Square size={16}/>} {allSelected?'Deselecteer alles':'Selecteer alles'}</button><button disabled={submitting} onClick={queueAgentUpdates}><Send size={16}/> {submitting?'Bezig...':'Queue agent update'}</button><span className="muted">{selectedSerials.length} device(s) geselecteerd</span></div>
    </section>}

    {(activeTab === 'devices' || activeTab === 'ota') && <section className="panel"><h2>Device inventory</h2><table><thead><tr><th></th><th>Serial</th><th>Naam</th><th>Klant</th><th>Site</th><th>Firmware</th><th>Status</th></tr></thead><tbody>{devices.map(d=><tr key={d.serial}><td><input type="checkbox" checked={!!selected[d.serial]} onChange={()=>toggle(d.serial)}/></td><td><code>{d.serial}</code></td><td>{d.name||'-'}</td><td>{d.customer||'-'}</td><td>{d.site||'-'}</td><td>{d.firmware||'-'}</td><td><Badge type={d.status==='online'?'ok':d.status==='pending'?'warn':'off'}>{d.status}</Badge></td></tr>)}</tbody></table></section>}
  </main>
}
function Card({icon,label,value}){return <div className="card"><div>{icon}</div><strong>{value}</strong><span>{label}</span></div>}
createRoot(document.getElementById('root')).render(<App/>);
