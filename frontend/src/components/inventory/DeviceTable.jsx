import React from 'react';
import {Eye} from 'lucide-react';
import {platformInfo,pct,safe,osDietPiLabel,loxberryVersion,ramTotalLabel} from '../shared/utils';

function Badge({children,type='ok'}){return <span className={'badge '+type}>{children}</span>}
function MetricBar({label,value,type='blue'}){const n=pct(value);return <div className="metric-line"><div className="metric-top"><span>{label}</span><strong>{n===null?'-':`${n}%`}</strong></div><div className="mini-bar"><i className={type} style={{width:`${n===null?0:Math.min(100,n)}%`}}/></div></div>}

export default function DeviceTable({devices,selected,toggle,activeSerial,setActiveSerial}){
 return <table className="device-inventory-table"><thead><tr><th></th><th>Device</th><th>Platform</th><th>OS/DietPi</th><th>LoxBerry</th><th>Agent</th><th>Firmware</th><th>CPU</th><th>RAM totaal</th><th>RAM gebruik</th><th>Disk</th><th>Status</th><th></th></tr></thead><tbody>{devices.map(d=>{const m=d.metrics||{},p=platformInfo(d),isActive=activeSerial===d.serial;return <tr key={d.serial} className={isActive?'selected-row':''}><td><input type="checkbox" checked={!!selected[d.serial]} onChange={()=>toggle(d.serial)}/></td><td><strong>{d.name||d.serial}</strong><small>{d.serial}</small></td><td>{p.model}<small>{p.type}</small></td><td>{safe(osDietPiLabel(d))}</td><td>{safe(loxberryVersion(d))}</td><td>{safe(d.agent_version||m.agent_version)}</td><td>{safe(d.firmware)}</td><td>{pct(d.cpu_percent)??'-'}%</td><td>{ramTotalLabel(d)}</td><td><MetricBar label="" value={d.mem_percent} type="green"/></td><td><MetricBar label="" value={d.disk_percent} type="amber"/></td><td><Badge type={d.status==='online'?'ok':d.status==='stale'?'warn':'off'}>{d.status}</Badge></td><td><button className="ghost" onClick={()=>setActiveSerial(isActive?null:d.serial)}><Eye size={15}/> {isActive?'Sluit':'Details'}</button></td></tr>})}</tbody></table>
}
