const API = '/api';
const ZEROTIER_NETWORK = '9445e68adada0b99';

function ensureStyles(){
  if(document.getElementById('qcentral-enroll-style')) return;
  const style=document.createElement('style');
  style.id='qcentral-enroll-style';
  style.textContent=`
  .enroll-fab{position:fixed;right:24px;bottom:24px;z-index:50;border:0;border-radius:999px;padding:13px 18px;background:#172b4d;color:#fff;font-weight:800;box-shadow:0 14px 34px rgba(15,23,42,.25);cursor:pointer}
  .enroll-backdrop{position:fixed;inset:0;z-index:80;background:rgba(15,23,42,.45);display:flex;align-items:center;justify-content:center;padding:24px}
  .enroll-modal{width:min(760px,100%);background:#fff;border-radius:22px;box-shadow:0 24px 70px rgba(15,23,42,.35);padding:24px;color:#162033}
  body.dark .enroll-modal{background:#111827;color:#e5eefb}
  .enroll-modal h2{margin:0 0 6px}.enroll-modal p{margin:0 0 18px;color:#64748b}.enroll-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.enroll-modal label{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:700}.enroll-modal input{border:1px solid #d8e0ea;border-radius:12px;padding:11px 12px;font:inherit}.enroll-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:18px}.enroll-actions button{border:0;border-radius:12px;padding:11px 14px;font-weight:800;cursor:pointer}.enroll-primary{background:#2563eb;color:#fff}.enroll-secondary{background:#eef2f7}.enroll-command{margin-top:16px;background:#0f172a;color:#dbeafe;border-radius:14px;padding:14px;white-space:pre-wrap;word-break:break-all;font-family:ui-monospace,Menlo,monospace;font-size:12px}.enroll-error{margin-top:12px;color:#b91c1c;font-weight:700}.enroll-note{margin-top:12px;font-size:12px;color:#64748b}`;
  document.head.appendChild(style);
}

async function api(path,options={}){
  const r=await fetch(API+path,{credentials:'include',headers:{'Content-Type':'application/json'},...options});
  if(!r.ok){throw new Error(await r.text());}
  return r.json();
}

function commandFor({central,serial,claim,release}){
  const url=release.url;
  const sha=release.sha256;
  const version=release.version||'unknown';
  return `sudo bash -c 'set -euo pipefail\nexport DEBIAN_FRONTEND=noninteractive\napt-get update -y\napt-get install -y python3 python3-venv python3-pip curl tar rsync ca-certificates\nif ! command -v zerotier-cli >/dev/null 2>&1; then curl -fsSL https://install.zerotier.com | bash || true; fi\nzerotier-cli join ${ZEROTIER_NETWORK} || true\ninstall -d -m 0755 /etc/qbox-agent /opt/qbox-agent\ncat > /etc/qbox-agent/config.json <<JSON\n{"serial":"${serial}","claim_token":"${claim}","central_url":"${central}","firmware":"${version}"}\nJSON\nchmod 0600 /etc/qbox-agent/config.json\nworkdir=$(mktemp -d /tmp/qbox-agent-install.XXXXXX)\ntrap "rm -rf $workdir" EXIT\ncurl -fsSL "${url}" -o "$workdir/agent.tar.gz"\necho "${sha}  $workdir/agent.tar.gz" | sha256sum -c -\ntar -xzf "$workdir/agent.tar.gz" -C "$workdir"\nif [ -d "$workdir/agent/qbox_agent" ]; then src="$workdir/agent"; else src=$(find "$workdir" -maxdepth 3 -type d -name qbox_agent -print -quit | xargs -r dirname); fi\n[ -n "$src" ] && [ -d "$src/qbox_agent" ]\nrsync -a --delete "$src/" /opt/qbox-agent/\npython3 -m venv /opt/qbox-agent/venv\n/opt/qbox-agent/venv/bin/pip install --upgrade pip\n/opt/qbox-agent/venv/bin/pip install -r /opt/qbox-agent/requirements.txt\nprintf "%s\\n" "${version}" > /etc/qbox-agent/version\ncat > /etc/systemd/system/qbox-agent.service <<UNIT\n[Unit]\nDescription=Q-Box Agent\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory=/opt/qbox-agent\nExecStart=/opt/qbox-agent/venv/bin/python -m qbox_agent\nRestart=always\nRestartSec=10\nUser=root\n\n[Install]\nWantedBy=multi-user.target\nUNIT\nsystemctl daemon-reload\nrm -f /etc/qbox-agent/agent-token\ncd /opt/qbox-agent\n/opt/qbox-agent/venv/bin/python -m qbox_agent --once --provision\nsystemctl enable --now qbox-agent.service\nsystemctl restart qbox-agent.service\nsleep 2\nsystemctl --no-pager --full status qbox-agent.service | head -n 25 || true\necho Q-Box agent installed and provisioned for ${serial}\n'`;
}

function openWizard(){
  ensureStyles();
  const backdrop=document.createElement('div');
  backdrop.className='enroll-backdrop';
  backdrop.innerHTML=`<div class="enroll-modal"><h2>Add Device</h2><p>Maak een Q-Box enrollment aan en genereer een install command met ZeroTier network ${ZEROTIER_NETWORK}.</p><div class="enroll-grid"><label>Serial<input id="enroll-serial" placeholder="QBX-..." /></label><label>Naam<input id="enroll-name" placeholder="Q-Box naam" /></label><label>Klant<input id="enroll-customer" /></label><label>Site<input id="enroll-site" /></label><label>Model<input id="enroll-model" placeholder="NanoPi R5C / Raspberry Pi 5" /></label><label>Q-Central URL<input id="enroll-central" /></label></div><div class="enroll-actions"><button class="enroll-secondary" id="enroll-close">Sluit</button><button class="enroll-primary" id="enroll-create">Maak enrollment</button></div><div id="enroll-output"></div></div>`;
  document.body.appendChild(backdrop);
  backdrop.querySelector('#enroll-central').value=window.location.origin;
  backdrop.querySelector('#enroll-close').onclick=()=>backdrop.remove();
  backdrop.querySelector('#enroll-create').onclick=async()=>{
    const out=backdrop.querySelector('#enroll-output');
    out.innerHTML='Bezig...';
    try{
      const body={serial:backdrop.querySelector('#enroll-serial').value.trim(),name:backdrop.querySelector('#enroll-name').value.trim(),customer:backdrop.querySelector('#enroll-customer').value.trim(),site:backdrop.querySelector('#enroll-site').value.trim(),model:backdrop.querySelector('#enroll-model').value.trim()};
      const created=await api('/serials',{method:'POST',body:JSON.stringify(body)});
      const releases=await api('/software/agent/releases');
      const release=releases.latest;
      if(!release||!release.ready) throw new Error('Geen geldige agent release gevonden');
      const cmd=commandFor({central:backdrop.querySelector('#enroll-central').value.replace(/\/$/,''),serial:created.serial,claim:created.claim_token,release});
      out.innerHTML='<div class="enroll-command"></div><div class="enroll-note">Kopieer dit commando naar een root shell op de Q-Box. Root wachtwoord wordt niet opgeslagen in Q-Central.</div>';
      out.querySelector('.enroll-command').textContent=cmd;
    }catch(e){out.innerHTML='<div class="enroll-error">'+String(e.message||e)+'</div>';}
  };
}

function addButton(){
  if(document.querySelector('.enroll-fab')) return;
  const btn=document.createElement('button');
  btn.className='enroll-fab';
  btn.textContent='+ Add Device';
  btn.onclick=openWizard;
  document.body.appendChild(btn);
}

window.addEventListener('load',()=>setTimeout(addButton,800));
