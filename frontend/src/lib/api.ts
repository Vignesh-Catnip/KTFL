const BASE=import.meta.env.VITE_API_URL||'http://localhost:8000';
async function request(path:string,init:RequestInit={}){const r=await fetch(BASE+path,init);let body:any={};try{body=await r.json()}catch{}if(!r.ok){const msg=Array.isArray(body.detail)?body.detail.join(', '):body.detail?.message||body.detail||`Request failed (${r.status})`;throw new Error(msg)}return body}
export const api={
 health:()=>request('/health'),
 upload:(file:File)=>{const f=new FormData();f.append('file',file);return request('/api/invoices/upload',{method:'POST',body:f})},
 list:(status?:string,search?:string)=>request('/api/invoices?'+new URLSearchParams({...(status?{status}:{}),...(search?{search}:{})})),
 get:(id:number)=>request(`/api/invoices/${id}`),
 update:(id:number,data:any)=>request(`/api/invoices/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}),
 sendBack:(id:number)=>request(`/api/invoices/${id}/send-back`,{method:'POST'}),
 approve:(id:number)=>request(`/api/invoices/${id}/approve`,{method:'POST'}),
 processing:(id:number)=>request(`/api/invoices/${id}/processing`)
};
