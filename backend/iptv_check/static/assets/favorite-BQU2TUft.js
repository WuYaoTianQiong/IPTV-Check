import{c,o as h,k as g,l as m,m as w,t as D,h as M,u as k,_ as F,q as u,ae as j,p as f,af as B,ag as H,ac as x,ah as _,ai as q,aj as z,ak as A}from"./index-8JNaYjgU.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=c("CheckIcon",[["path",{d:"M20 6 9 17l-5-5",key:"1gmf2c"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const U=c("ChevronLeftIcon",[["path",{d:"m15 18-6-6 6-6",key:"1wnfg3"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const Z=c("DownloadIcon",[["path",{d:"M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4",key:"ih7n3h"}],["polyline",{points:"7 10 12 15 17 10",key:"2ggqvy"}],["line",{x1:"12",x2:"12",y1:"15",y2:"3",key:"1vk2je"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const $=c("FolderIcon",[["path",{d:"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z",key:"1kt360"}]]);/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const E=c("InboxIcon",[["polyline",{points:"22 12 16 12 14 15 10 15 8 12 2 12",key:"o97t9d"}],["path",{d:"M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z",key:"oot6mr"}]]),G={__name:"LatencyBadge",props:{latency:{type:[Number,String],default:null}},setup(n){const r=n,l=u(()=>{const o=r.latency;if(o==null||o===""||o==="-")return NaN;const i=Number(o);return isNaN(i)?NaN:i}),s=u(()=>!isNaN(l.value)&&l.value>0),d=u(()=>Math.round(l.value)),y=u(()=>{const o=l.value;return isNaN(o)||o<=0?"":o<200?"bg-green-600 text-white dark:bg-green-700":o<800?"bg-yellow-500 text-black dark:bg-yellow-600 dark:text-white":"bg-red-600 text-white dark:bg-red-700"});return(o,i)=>s.value?(h(),g(k(F),{key:0,class:M([y.value,"text-[10px] shrink-0 font-medium whitespace-nowrap inline-flex justify-center w-10"])},{default:m(()=>[w(D(d.value)+"ms ",1)]),_:1},8,["class"])):(h(),g(k(F),{key:1,class:"text-[10px] shrink-0 font-medium whitespace-nowrap inline-flex justify-center w-10 bg-muted text-muted-foreground"},{default:m(()=>[...i[0]||(i[0]=[w(" - ",-1)])]),_:1}))}},J=j("favorite",()=>{const n=f([]),r=f([]),l=f(!1),s=f(null),d=u(()=>new Set(n.value.map(e=>e.url)));async function y(e=null){l.value=!0;try{const a={};e!==null&&(a.folder_id=e);const{data:t}=await B(a);n.value=t.favorites||[]}catch(a){throw n.value=[],a}finally{l.value=!1}}async function o(){try{const{data:e}=await H();r.value=e.folders||[]}catch{r.value=[]}}function i(e){return d.value.has(e)}async function b(e){s.value=e}async function N(e){const a=n.value.find(t=>t.url===e.url);if(a)await x(a.id),n.value=n.value.filter(t=>t.id!==a.id);else{const{data:t}=await _({channel_id:e.channel_id||0,name:e.name,url:e.url,folder_id:s.value,channel_group:e.group||""});n.value.push(t)}}async function I(e,a){const t=n.value.find(p=>p.url===e.url);if(t)return await x(t.id),n.value=n.value.filter(p=>p.id!==t.id),{action:"removed"};const{data:v}=await _({channel_id:e.channel_id||0,name:e.name,url:e.url,folder_id:a,channel_group:e.group||""});return n.value.push(v),{action:"added",data:v}}async function L(e){const{data:a}=await q({name:e});return r.value.push(a),a}async function C(e,a){try{await z(e,a);const t=r.value.findIndex(v=>v.id===e);t!==-1&&(r.value[t]={...r.value[t],...a})}catch{}}async function S(e){try{await A(e),r.value=r.value.filter(a=>a.id!==e),s.value===e&&(s.value=null)}catch{}}return{favorites:n,folders:r,isLoading:l,activeFolderId:s,favoriteUrlSet:d,fetchFavorites:y,fetchFolders:o,isFavorite:i,toggleFavorite:N,addFavoriteTo:I,setDefaultFolder:b,addFolder:L,updateFolder:C,removeFolder:S}});export{U as C,Z as D,$ as F,E as I,G as _,V as a,J as u};
