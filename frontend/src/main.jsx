import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Server, ShieldCheck, UploadCloud, Boxes, RefreshCw, Send, CheckSquare, Square} from 'lucide-react';
import './style.css';

const api = '/api';
function Badge({children,type='ok'}){return <span className={'badge '+type}>{children}</span>}
function App(){
  const [token,setToken]=useState(localStorage.getItem('adminToken')||'');
  const [devices,setDevices]=useState([]);
  const [selected,setSelected]=useState({});
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [agentUpdate,setAgentUpdate]=useState({version:'',url:'',sha256:''});
  const [submitting,setSubmitting]=useState(false);

  async function load(){
    setError(''); setNotice('');
    const r=await fetch(api+'/devices',{headers:{'X-Admin-Token':token}});
    if(!r.ok){setError('Admin token ontbreekt of is fout');return}
    const data=await r.json();
    setDevices(data); localStorage.setItem('adminToken',token);
  }
  useEffect(()=>{ if(token) load(); },[]);

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
      const r=await fetch(api+'/jobs/agent-update',{
        method:'POST',
        headers:{'X-Admin-Token':token,'Content-Type':'application/json'},
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

  return <main>
    <header><div className="logo">Q</div><div><h1>Q-Central</h1><p>Production control plane voor Q-Box devices</p></div></header>
    <section className="login"><input type="password" placeholder="Admin token" value={token} onChange={e=>setToken(e.target.value)}/><button onClick={load}><RefreshCw size={16}/> Laden</button></section>
    {error && <div className="error">{error}</div>}
    {notice && <div className="notice">{notice}</div>}
    <section className="stats"><Card icon={<Server/>} label="Devices" value={devices.length}/><Card icon={<ShieldCheck/>} label="Pending auth" value={pending}/><Card icon={<UploadCloud/>} label="Online" value={online}/><Card icon={<Boxes/>} label="Apps" value="managed"/></section>

    <section className="panel"><h2>Agent update vanuit Q-Central</h2><p className="muted">Selecteer devices, kies een release artifact en queue een <code>agent_update</code> job. SHA256 is verplicht zodat agents alleen gesigneerde/gecontroleerde artifacts installeren.</p>
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
