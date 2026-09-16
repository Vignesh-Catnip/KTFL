import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {BrowserRouter,useLocation,useNavigate,useParams,Routes,Route,Link,Navigate} from 'react-router-dom';
import {Upload,FileText,History,AlertCircle,LogOut,ArrowLeft,CheckCircle2,Loader2,Search,RefreshCw} from 'lucide-react';
import './index.css'; import {api} from './lib/api';

type Invoice={
  id:number;filename:string;vendor:string;invoice_number:string;invoice_date:string;
  po_number:string;gstin:string;hsn_sac:string;vendor_code:string;tax_code:string;
  business_place:string;currency:string;subtotal:number;cgst:number;sgst:number;
  igst:number;tax:number;total:number;confidence:number;status:string;
  error_message?:string|null;
  lines:{id:number;item:string;quantity:number;rate:number;tax_code:string;amount:number}[]
};

const nav=[['/upload','Upload invoice',Upload],['/review','Review queue',FileText],['/history','Processed history',History],['/exceptions','Exceptions',AlertCircle]] as const;

function Shell({children}:{children:React.ReactNode}){
  const loc=useLocation();const navg=useNavigate();
  return <div className="min-h-screen flex">
    <aside className="w-60 shrink-0 p-5 flex flex-col justify-between" style={{background:'var(--navy)'}}>
      <div>
        <div className="flex items-center gap-2.5 mb-9">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold" style={{background:'var(--teal)'}}>IP</div>
          <span className="text-white text-sm font-semibold">Invoice Processing</span>
        </div>
        <nav className="space-y-1">
          {nav.map(([p,l,I])=><Link key={p} to={p} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm" style={loc.pathname.startsWith(p)?{background:'var(--navy2)',color:'#fff'}:{color:'#B6C2D9'}}><I size={16}/>{l}</Link>)}
        </nav>
      </div>
      <div className="border-t border-white/10 pt-4">
        <div className="text-white text-sm">A. Sharma</div>
        <div className="text-xs mb-2" style={{color:'#8393AD'}}>AP Processing Team</div>
        <button className="text-xs" style={{color:'#8393AD'}} onClick={()=>navg('/login')}>Log out</button>
      </div>
    </aside>
    <main className="flex-1 p-6 min-w-0">{children}</main>
  </div>
}

function Login(){
  const n=useNavigate();
  return <div className="min-h-screen flex items-center justify-center" style={{background:'var(--navy)'}}>
    <div className="card w-[400px] p-10 fade">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white font-bold" style={{background:'var(--teal)'}}>IP</div>
        <div><div className="font-semibold">Invoice Processing</div><div className="text-xs text-neutral-400">AI extraction · RPA posting to SAP</div></div>
      </div>
      <label className="text-xs text-neutral-500">Username</label>
      <input defaultValue="a.sharma@company.com" className="w-full border rounded-lg p-2.5 mt-1 mb-4"/>
      <label className="text-xs text-neutral-500">Password</label>
      <input defaultValue="password123" type="password" className="w-full border rounded-lg p-2.5 mt-1 mb-6"/>
      <button className="btn w-full" onClick={()=>n('/upload')}>Log in</button>
      <div className="text-center text-[11px] text-neutral-400 mt-5">SSO available for company domains</div>
    </div>
  </div>
}

function UploadPage(){
  const n=useNavigate();
  const[f,setF]=useState<File|null>(null);
  const[busy,setBusy]=useState(false);
  const[err,setErr]=useState('');
  async function submit(){
    if(!f)return;setBusy(true);setErr('');
    try{const r=await api.upload(f);sessionStorage.setItem('lastInvoiceId',String(r.id));n(r.status==='EXCEPTION'?'/exceptions':`/review/${r.id}`)}
    catch(e:any){setErr(e.message)}finally{setBusy(false)}
  }
  return <Shell><div className="card p-9 min-h-[calc(100vh-48px)] fade">
    <div className="text-lg font-semibold">Upload vendor invoice</div>
    <div className="text-sm text-neutral-500 mt-1 mb-7">Attach the invoice PDF and supporting documents for AI extraction.</div>
    {err&&<div className="p-3 mb-4 rounded-lg text-sm" style={{background:'var(--redBg)',color:'var(--red)'}}>{err}</div>}
    <label className="h-72 rounded-xl border-2 border-dashed flex flex-col items-center justify-center cursor-pointer bg-[#FAFBFC]">
      <input hidden type="file" accept="application/pdf,image/png,image/jpeg" onChange={e=>setF(e.target.files?.[0]||null)}/>
      {f?<><FileText size={38} style={{color:'var(--teal)'}}/><b className="mt-3 text-sm">{f.name}</b><span className="text-xs text-neutral-400 mt-1">{(f.size/1024/1024).toFixed(2)} MB · ready to submit</span></>
        :<><Upload size={36} className="text-neutral-300"/><b className="mt-3 text-sm text-neutral-600">Click to browse invoice</b><span className="text-xs text-neutral-400 mt-1">PDF, JPG, PNG · up to 20MB</span></>}
    </label>
    <div className="flex justify-end mt-8">
      <button className="btn" disabled={!f||busy} onClick={submit}>{busy?<><Loader2 size={15} className="inline animate-spin mr-2"/>Extracting…</>:'Submit for extraction →'}</button>
    </div>
  </div></Shell>
}

function Field({label,value,highlight}:{label:string;value:string|number|null|undefined;highlight?:boolean}){
  const display = value===null||value===undefined||value===''||value===0?'—':String(value);
  return <div>
    <div className="text-[11px] text-neutral-400 mb-1">{label}</div>
    <div className="border rounded-lg p-2.5 text-sm flex justify-between items-center">
      <span>{display}</span>
      {highlight&&display!=='—'&&<span className="text-[10px]" style={{color:'var(--amber)'}}>verify</span>}
    </div>
  </div>
}

function Review(){
  const{id}=useParams();const n=useNavigate();
  const[inv,setInv]=useState<Invoice|null>(null);
  const[busy,setBusy]=useState(false);
  const[err,setErr]=useState('');
  useEffect(()=>{api.get(Number(id)).then(setInv).catch(e=>setErr(e.message))},[id]);
  if(!inv)return <Shell><div className="card p-8">{err||'Loading invoice…'}</div></Shell>;
  async function approve(){setBusy(true);try{await api.approve(inv.id);n(`/processing/${inv.id}`)}catch(e:any){setErr(e.message)}finally{setBusy(false)}}
  async function sendBack(){try{await api.sendBack(inv.id);n('/exceptions')}catch(e:any){setErr(e.message)}}
  const fmt=(n:number)=>n>0?`₹${n.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})}`:'—';
  return <Shell>
    <div className="card px-6 py-4 flex items-center gap-5 mb-4">
      <Step n={1} label="Upload" done/><Step n={2} label="AI extraction" done/>
      <Step n={3} label="Human verification" active/><Step n={4} label="RPA → SAP MIRO"/>
    </div>
    <div className="card p-8 fade">
      <div className="flex justify-between mb-6">
        <div>
          <div className="text-[17px] font-semibold">{inv.filename}</div>
          <div className="text-sm text-neutral-500 mt-1">Extracted by Ollama AI · verify before posting to SAP</div>
        </div>
        <span className="px-2.5 py-1 rounded-full text-xs h-fit" style={{background:'var(--amberBg)',color:'var(--amber)'}}>Awaiting review</span>
      </div>
      {err&&<div className="p-3 rounded mb-4 text-sm bg-red-50 text-red-700">{err}</div>}

      {/* Section 1: Vendor & Invoice Info */}
      <div className="mb-2 text-xs font-semibold text-neutral-500 uppercase tracking-wide">Invoice Details</div>
      <div className="grid grid-cols-3 gap-4 mb-5">
        <Field label="Vendor / Supplier" value={inv.vendor}/>
        <Field label="Invoice Number" value={inv.invoice_number}/>
        <Field label="Invoice Date" value={inv.invoice_date}/>
        <Field label="PO / Reference Number" value={inv.po_number}/>
        <Field label="Vendor GSTIN" value={inv.gstin}/>
        <Field label="Vendor Code" value={inv.vendor_code}/>
        <Field label="HSN / SAC Code" value={inv.hsn_sac}/>
        <Field label="Tax Code" value={inv.tax_code} highlight/>
        <Field label="Business Place" value={inv.business_place}/>
      </div>

      {/* Section 2: Amounts */}
      <div className="mb-2 text-xs font-semibold text-neutral-500 uppercase tracking-wide">Tax & Amount</div>
      <div className="grid grid-cols-4 gap-4 mb-5">
        <Field label="Currency" value={inv.currency}/>
        <Field label="Subtotal (Taxable Value)" value={fmt(inv.subtotal)}/>
        <Field label="CGST" value={fmt(inv.cgst)}/>
        <Field label="SGST" value={fmt(inv.sgst)}/>
        <Field label="IGST" value={fmt(inv.igst)}/>
        <Field label="Total Tax" value={fmt(inv.tax)}/>
        <div className="col-span-2">
          <div className="text-[11px] text-neutral-400 mb-1">Invoice Total</div>
          <div className="border-2 rounded-lg p-2.5 text-sm font-bold" style={{borderColor:'var(--teal)',color:'var(--teal)'}}>{fmt(inv.total)}</div>
        </div>
      </div>

      {/* Section 3: Line Items */}
      <div className="mb-2 text-xs font-semibold text-neutral-500 uppercase tracking-wide">Line Items</div>
      <div className="rounded-lg overflow-hidden border mb-5">
        <table className="w-full text-sm">
          <thead className="bg-[#FAFBFC]">
            <tr>
              <th className="p-2 text-left">Item / Description</th>
              <th className="p-2 text-center">Qty</th>
              <th className="p-2 text-right">Rate</th>
              <th className="p-2 text-center">HSN/Tax</th>
              <th className="p-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {inv.lines.length===0
              ?<tr><td colSpan={5} className="p-4 text-center text-neutral-400">No line items extracted</td></tr>
              :inv.lines.map(l=><tr className="border-t" key={l.id}>
                <td className="p-2">{l.item||'—'}</td>
                <td className="p-2 text-center">{l.quantity||'—'}</td>
                <td className="p-2 text-right font-mono">{l.rate>0?fmt(l.rate):'—'}</td>
                <td className="p-2 text-center font-mono text-xs">{l.tax_code||'—'}</td>
                <td className="p-2 text-right font-mono">{fmt(l.amount)}</td>
              </tr>)
            }
          </tbody>
        </table>
      </div>

      {/* Confidence */}
      <div className="flex items-center gap-3 mb-6 text-sm">
        <span className="text-neutral-500">AI Extraction Confidence:</span>
        <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
          <div className="h-full rounded-full" style={{width:`${Math.round(inv.confidence*100)}%`,background:inv.confidence>=0.8?'var(--teal)':inv.confidence>=0.6?'var(--amber)':'var(--red)'}}/>
        </div>
        <b>{Math.round(inv.confidence*100)}%</b>
      </div>

      <div className="flex justify-between items-center mt-4">
        <button className="flex items-center gap-2 text-sm text-neutral-600" onClick={()=>n('/upload')}><ArrowLeft size={15}/>Back</button>
        <div className="flex gap-3">
          <button className="border rounded-lg px-4 py-2.5 text-sm" onClick={sendBack}>Send back for correction</button>
          <button className="btn" disabled={busy} onClick={approve}>{busy?'Launching bot…':'Confirm & trigger RPA bot →'}</button>
        </div>
      </div>
    </div>
  </Shell>
}

function Step({n,label,done,active}:{n:number;label:string;done?:boolean;active?:boolean}){
  return <div className="flex items-center gap-2 shrink-0">
    <div className="w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium"
      style={done?{background:'var(--teal)',color:'#fff'}:active?{border:'2px solid var(--teal)',color:'var(--teal)'}:{border:'2px solid #E3E6EC',color:'#C9CFDA'}}>
      {done?'✓':n}
    </div>
    <span className="text-xs font-medium text-neutral-700">{label}</span>
  </div>
}

function Processing(){
  const{id}=useParams();const n=useNavigate();
  const[data,setData]=useState<any>();const[err,setErr]=useState('');
  useEffect(()=>{
    let stop=false;
    const load=async()=>{try{const x=await api.processing(Number(id));if(!stop)setData(x)}catch(e:any){if(!stop)setErr(e.message)}};
    load();const t=setInterval(load,1200);return()=>{stop=true;clearInterval(t)}
  },[id]);
  return <Shell><div className="card p-8 fade">
    <div className="flex justify-between items-start mb-6">
      <div><div className="text-[17px] font-semibold">Posting invoice to SAP MIRO</div>
      <div className="text-sm text-neutral-500 mt-1 font-mono">{data?.session_id||'Starting session…'}</div></div>
      <button className="border rounded-lg px-4 py-2 text-sm" onClick={()=>n(`/review/${id}`)}><ArrowLeft size={14} className="inline mr-1"/>Back</button>
    </div>
    {err&&<div className="text-sm text-red-600 mb-4">{err}</div>}
    <div className="border rounded-lg overflow-hidden">
      {(data?.detail?.steps||['Bot session started on VM','Logged in to SAP, opened MIRO','Vendor identified, header data entered','GRN line items fetched & matched','TDS codes applied','Simulate posting — balance check','Document posted (MM + FI)']).map((s:string,i:number)=>
        <div key={s} className="flex items-center gap-3 px-4 py-3.5 border-b last:border-b-0">
          <div className="w-5 h-5 rounded-full flex items-center justify-center"
            style={data?.status==='COMPLETED'||i<4?{background:'var(--teal)',color:'#fff'}:{border:'2px solid #E3E6EC'}}>
            {data?.status==='COMPLETED'||i<4?<CheckCircle2 size={13}/>:''}
          </div>
          <span className="text-sm">{s}</span>
        </div>
      )}
    </div>
    {data?.status==='COMPLETED'&&<div className="mt-5 p-4 rounded-lg text-sm" style={{background:'var(--greenBg)',color:'var(--tealDark)'}}>RPA completed. SAP document: <b>{data.sap_document}</b></div>}
    <div className="text-xs text-neutral-400 mt-5">Real SAP posting requires a configured RPA adapter. Mock mode is used for local testing.</div>
  </div></Shell>
}

function ListPage({mode}:{mode:'history'|'exceptions'}){
  const[data,setData]=useState<Invoice[]>([]);const[q,setQ]=useState('');const[err,setErr]=useState('');
  const n=useNavigate();
  const load=()=>api.list(mode==='history'?'PROCESSED':'EXCEPTION',q).then(setData).catch(e=>setErr(e.message));
  useEffect(()=>{load()},[mode]);
  return <Shell><div className="card p-7 fade">
    <div className="flex justify-between items-center mb-5">
      <div><h1 className="text-lg font-semibold">{mode==='history'?'Processed history':'Exceptions'}</h1>
      <p className="text-sm text-neutral-500 mt-1">{mode==='history'?'Previously posted invoices':'Invoices requiring human action'}</p></div>
      <button className="border rounded-lg p-2" onClick={load}><RefreshCw size={16}/></button>
    </div>
    <div className="flex gap-2 mb-5">
      <div className="flex-1 relative"><Search size={16} className="absolute left-3 top-3 text-neutral-400"/>
        <input value={q} onChange={e=>setQ(e.target.value)} onKeyDown={e=>e.key==='Enter'&&load()} placeholder="Search vendor, invoice or PO" className="w-full border rounded-lg pl-9 p-2.5 text-sm"/>
      </div>
      <button className="btn" onClick={load}>Search</button>
    </div>
    {err&&<div className="text-sm text-red-600 mb-4">{err}</div>}
    {data.length===0?<div className="text-center py-14 text-sm text-neutral-400">No records found.</div>
      :data.map(x=><button key={x.id} onClick={()=>n(`/review/${x.id}`)} className="w-full text-left border-b last:border-b-0 py-4 flex justify-between hover:bg-neutral-50">
          <div>
            <b className="text-sm">{x.invoice_number}</b>
            <div className="text-xs text-neutral-500 mt-1">{x.vendor} · {x.filename}</div>
            <div className="text-xs text-neutral-400 mt-0.5">{x.gstin&&`GSTIN: ${x.gstin}`}{x.total>0&&` · ₹${x.total.toLocaleString('en-IN')}`}</div>
            {x.error_message&&<div className="text-xs text-red-600 mt-1">{x.error_message}</div>}
          </div>
          <span className="text-xs font-medium shrink-0 ml-4">{x.status}</span>
        </button>
      )
    }
  </div></Shell>
}

function ReviewRedirect(){const id=sessionStorage.getItem('lastInvoiceId');return <Navigate to={id?`/review/${id}`:'/upload'} replace/>}

function App(){return <Routes>
  <Route path="/login" element={<Login/>}/>
  <Route path="/upload" element={<UploadPage/>}/>
  <Route path="/review/:id" element={<Review/>}/>
  <Route path="/review" element={<ReviewRedirect/>}/>
  <Route path="/processing/:id" element={<Processing/>}/>
  <Route path="/history" element={<ListPage mode="history"/>}/>
  <Route path="/exceptions" element={<ListPage mode="exceptions"/>}/>
  <Route path="*" element={<Navigate to="/login" replace/>}/>
</Routes>}

createRoot(document.getElementById('root')!).render(<BrowserRouter><App/></BrowserRouter>);
