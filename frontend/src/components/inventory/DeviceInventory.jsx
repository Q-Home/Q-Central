import React,{useEffect,useState} from 'react';
import {Search} from 'lucide-react';
import DeviceTable from './DeviceTable';
import DeviceDetail from './DeviceDetail';

function Badge({children,type='ok'}){return <span className={'badge '+type}>{children}</span>}

export default function DeviceInventory({devices,selected,toggle,query,setQuery}){
 const [activeSerial,setActiveSerial]=useState(null);
 const active=devices.find(d=>d.serial===activeSerial)||null;

 useEffect(()=>{
   if(activeSerial&&!devices.some(d=>d.serial===activeSerial)){
     setActiveSerial(null);
   }
 },[activeSerial,devices]);

 return <section className="panel inventory-pro"><div className="panel-head"><div><h2>Device inventory</h2><p className="muted">Live data via agent heartbeat. Details worden live opnieuw opgebouwd vanuit de actuele device state.</p></div><div className="actions"><label className="search"><Search size={17}/><input placeholder="Zoek device, platform, klant, site..." value={query} onChange={e=>setQuery(e.target.value)}/></label><Badge type="ok">{devices.length} devices</Badge></div></div><DeviceTable devices={devices} selected={selected} toggle={toggle} activeSerial={activeSerial} setActiveSerial={setActiveSerial}/>{active&&<DeviceDetail device={active} full/>}</section>
}
