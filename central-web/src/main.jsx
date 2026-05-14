import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Server, ShieldCheck, UploadCloud, Boxes, RefreshCw } from 'lucide-react';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8080';

function App() {
  const [devices, setDevices] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [status, setStatus] = useState('loading');
  const [serial, setSerial] = useState('QBX-2026-0001');

  async function load() {
    const [d, j] = await Promise.all([
      fetch(`${API}/api/devices`).then(r => r.json()),
      fetch(`${API}/api/ota/jobs`).then(r => r.json()),
    ]);
    setDevices(d); setJobs(j); setStatus('ok');
  }
  useEffect(() => { load().catch(() => setStatus('offline')); }, []);

  async function authorize(s) { await fetch(`${API}/api/provision/authorize/${s}`, {method:'POST'}); await load(); }
  async function ota(s) { await fetch(`${API}/api/ota/deploy?serial=${encodeURIComponent(s)}&target_firmware=2026.05.1`, {method:'POST'}); await load(); }
  async function createSerial() { await fetch(`${API}/api/serials`, {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({serial, name:'New Q-Box', claim_token:'dev-claim-token'})}); await load(); }

  const online = devices.filter(d => ['online','authorized'].includes(d.status)).length;
  const pending = devices.filter(d => !d.authorized).length;
  const appCount = new Set(devices.flatMap(d => d.apps || [])).size;

  return <main>
    <header>
      <div className="logo">Q</div><div><h1>Q-Box Central</h1><p>Provisioning, ZeroTier authorization, OTA, apps en inventory</p></div>
      <button onClick={load}><RefreshCw size={16}/> Sync</button>
    </header>
    <section className="stats">
      <Card icon={<Server/>} value={devices.length} label="Devices" sub={`${online} online`} />
      <Card icon={<ShieldCheck/>} value={pending} label="Pending authorization" sub="auto/manual" />
      <Card icon={<UploadCloud/>} value={jobs.length} label="OTA jobs" sub="queued/history" />
      <Card icon={<Boxes/>} value={appCount} label="Apps" sub="reported by agents" />
    </section>
    <section className="panel">
      <h2>Serial registry</h2>
      <div className="row"><input value={serial} onChange={e=>setSerial(e.target.value)} /><button onClick={createSerial}>Registreer serial</button></div>
    </section>
    <section className="panel">
      <h2>Device inventory <span className={status}>{status}</span></h2>
      <div className="table">
        <div className="tr th"><b>Serial</b><b>Name</b><b>Customer</b><b>Status</b><b>Firmware</b><b>Acties</b></div>
        {devices.map(d => <div className="tr" key={d.serial}>
          <span className="mono">{d.serial}</span><span>{d.name}</span><span>{d.customer || '-'}</span><span className={`badge ${d.status}`}>{d.status}</span><span>{d.firmware || '-'}</span>
          <span>{!d.authorized && <button onClick={()=>authorize(d.serial)}>Authorize</button>}<button onClick={()=>ota(d.serial)}>OTA</button></span>
        </div>)}
      </div>
    </section>
    <section className="panel">
      <h2>OTA jobs</h2>
      {jobs.map(j => <div className="job" key={j.id}><b>{j.serial}</b> → {j.target_firmware || j.command} <span>{j.status}</span></div>)}
    </section>
  </main>
}
function Card({icon,value,label,sub}){return <div className="card"><div className="icon">{icon}</div><div><strong>{value}</strong><p>{label}</p><small>{sub}</small></div></div>}

createRoot(document.getElementById('root')).render(<App/>);
