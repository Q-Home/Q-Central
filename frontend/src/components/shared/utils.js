export const platforms={
  'nanopi-r5c':{name:'Mini',subtitle:'Basis',model:'NanoPi R5C',type:'ARM64 edge gateway'},
  'raspberry-pi-5':{name:'Compact',subtitle:'Meer power',model:'Raspberry Pi 5',type:'ARM64 compute gateway'},
  'andino-x1':{name:'Maxi',subtitle:'DIN RAIL',model:'Andino / DIN rail',type:'industrial gateway'},
  'generic-arm64':{name:'Generic ARM64',subtitle:'Custom',model:'Linux ARM64',type:'custom gateway'},
};

export function pct(v){const n=Number(v);return Number.isFinite(n)?Math.round(n):null}
export function safe(v){if(v===null||v===undefined||v==='')return '-'; if(typeof v==='object')return v.output||v.detail||v.message||JSON.stringify(v).slice(0,180); return String(v)}
export function uptime(sec){const n=Number(sec); if(!Number.isFinite(n))return '-'; const d=Math.floor(n/86400),h=Math.floor((n%86400)/3600),m=Math.floor((n%3600)/60); return d?`${d}d ${h}u`:`${h}u ${m}m`}
export function versionOf(d){return d.agent_version||d.metrics?.agent_version||d.firmware||'-'}
export function loxberryVersion(d){const m=d.metrics||{};return m.loxberry_version||m.loxberry?.version||m.loxberryVersion||'-'}
export function osDietPiLabel(d){const m=d.metrics||{};return m.dietpi_version||m.os_pretty_name||m.platform||'-'}
export function ramTotalMb(d){const m=d.metrics||{};return Number(m.mem_total_mb||m.memory_total_mb||m.ram_total_mb||m.mem_total)}
export function ramTotalLabel(d){const mb=ramTotalMb(d);return Number.isFinite(mb)&&mb>0?`${(mb/1024).toFixed(mb>=10240?0:1)} GB`:'-'}
export function platformKey(d){const h=`${d.hardware_platform||''} ${d.model||''} ${d.metrics?.board_model||''} ${d.metrics?.platform||''}`.toLowerCase(); if(h.includes('nanopi')||h.includes('r5c'))return 'nanopi-r5c'; if(h.includes('raspberry')||h.includes('pi 5'))return 'raspberry-pi-5'; if(h.includes('andino')||h.includes('din'))return 'andino-x1'; return 'generic-arm64'}
export function platformInfo(d){return platforms[platformKey(d)]||platforms['generic-arm64']}
