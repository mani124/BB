import{c as d,j as s,F as P}from"./index-C1Mxa2PG.js";import{a as j,u as c,r as k,b as v,P as b,c as C,s as F,d as g}from"./DockApp-DZWJEE-v.js";import{u as w,a as A}from"./hooks-gx_ADmpT.js";/**
 * @license lucide-react v0.344.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=d("PinOff",[["line",{x1:"2",x2:"22",y1:"2",y2:"22",key:"a6p6uj"}],["line",{x1:"12",x2:"12",y1:"17",y2:"22",key:"1jrz49"}],["path",{d:"M9 9v1.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V17h12",key:"13x2n8"}],["path",{d:"M15 9.34V6h1a2 2 0 0 0 0-4H7.89",key:"reo3ki"}]]);/**
 * @license lucide-react v0.344.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const B=d("Pin",[["line",{x1:"12",x2:"12",y1:"17",y2:"22",key:"1jrz49"}],["path",{d:"M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z",key:"13yl11"}]]),M={pinned:!1,subject:null},V=p=>{var l;const[n,i]=w(p,M),o=j({pinned:n.pinned,pinnedTo:n.subject??void 0}),t=c(e=>e),{signal:a,position:r,candidate:u}=k(t,o),m=c(e=>e.trades),h=new Set((((l=t.scanner.paper_portfolio)==null?void 0:l.active_positions)??[]).map(e=>e.signal_id)),f=A(),y=v(),x=s.jsxs("button",{type:"button",className:"desk-btn","aria-pressed":n.pinned,onClick:()=>i({pinned:!n.pinned,subject:n.pinned?null:o}),title:n.pinned?"Follow the selection again":"Keep showing this item",children:[n.pinned?s.jsx(S,{className:"h-3.5 w-3.5","aria-hidden":!0}):s.jsx(B,{className:"h-3.5 w-3.5","aria-hidden":!0}),n.pinned?"Unpin":"Pin"]});return s.jsx(b,{title:"Focus",sources:["scanner","portfolio","watch"],actions:x,children:s.jsx(P,{signal:a??null,position:r??null,candidate:u??null,trades:m,isBought:a?h.has(a.id):!1,onPaperBuy:e=>{g.paperBuy(e)},onClosePosition:e=>{f(e)},onOpenTrade:e=>{F({kind:"trade",id:e}),y.openPanel("trades")},onClear:()=>{n.pinned&&i({pinned:!1,subject:null}),C()}})})};export{V as default};
