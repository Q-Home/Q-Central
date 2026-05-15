import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Server, ShieldCheck, UploadCloud, Boxes, RefreshCw, Send, CheckSquare, Square, LogOut} from 'lucide-react';
import './style.css';

const api = '/api';
function Badge({children,type='ok'}){return <span className={'badge '+type}>{children}</span>}
function App(){
  const [user,setUser]=useState(null);
  const [login,setLogin]=useState({username:'admin',password:''});
  const [devices,setDevices]=useState([]);
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
    setUser(null); setDevices([]); setSelected({}); setNotice('Uitgelogd.');
  }

  async function load(){
    setError(''); setNotice('');
    const r=await apiFetch('/devices');
    if(!r.ok){setError('Sessie verlopen of geen toegang. Log opnieuw in.'); setUser(null); return}
    const data=await r.json();
    setDevices(data);
  }

  const online=devices.filter(d=>d.status==='online').length;
  const pending=devices.filter(d=>!d.authorized).length;
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
    await load();
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
    <section className="login"><button onClick={load}><RefreshCw size={16}/> Herladen</button><span className="muted">Aangemeld als {user.username}</span></section>
    {error && <div className="error">{error}</div>}
    {notice && <div className="notice">{notice}</div>}
    <section className="stats"><Card icon={<Server/>} label="Devices" value={devices.length}/><Card icon={<ShieldCheck/>} label="Pending auth" value={pending}/><Card icon={<UploadCloud/>} label="Online" value={online}/><Card icon={<Boxes/>} label="Apps" value="managed"/></section>

    <section className="panel"><h2>Agent update vanuit Q-Central</h2><p className="muted">Selecteer devices, kies een release artifact en queue een <code>agent_update</code> job. SHA256 is verplicht zodat agents alleen gecontroleerde artifacts installeren.</p>
      <div className="formgrid">
        <label>Nieuwe versie<input placeholder="bijv. 1.0.2" value={agentUpdate.version} onChange={e=>setAgentUpdate({...agentUpdate,version:e.target.value})}/></label>
        <label>Artifact URL<input placeholder="https://github.com/Q-Home/Q-Central/releases/download/.../qbox-agent.tar.gz" value={agentUpdate.url} onChange={e=>setAgentUpdate({...agentUpdate,url:e.target.value})}/></label>
        <label>SHA256<input placeholder="verplicht" value={agentUpdate.sha256} onChange={e=>setAgentUpdate({...agentUpdate,sha256:e.target.value})}/></label>
      </div>
      <div className="actions"><button onClick={toggleAll}>{allSelected?<CheckSquare size={16}/>:<Square size={16}/>} {allSelected?'Deselecteer alles':'Selecteer alles'}</button><button disabled={submitting} onClick={queueAgentUpdates}><Send size={16}/> {submitting?'Bezig...':'Queue agent update'}</button><span className="muted">{selectedSerials.length} device(s) geselecteerd</span></div>
    </section>

    <section className="panel"><h2>Device inventory</h2><table><thead><tr><th></th><th>Serial</th><th>Naam</th><th>Klant</th><th>Site</th><th>Firmware</th><th>Status</th></tr></thead><tbody>{devices.map(d=><tr key={d.serial}><td><input type="checkbox" checked={!!selected[d.serial]} onChange={()=>toggle(d.serial)}/></td><td><code>{d.serial}</code></td><td>{d.name||'-'}</td><td>{d.customer||'-'}</td><td>{d.site||'-'}</td><td>{d.firmware||'-'}</td><td><Badge type={d.status==='online'?'ok':d.status==='pending'?'warn':'off'}>{d.status}</Badge></td></tr>)}</tbody></table></section>
  </main>
}
function Card({icon,label,value}){return <div className="card"><div>{icon}</div><strong>{value}</strong><span>{label}</span></div>}
createRoot(document.getElementById('root')).render(<App/>);
