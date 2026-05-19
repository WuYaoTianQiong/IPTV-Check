import{c as i,as as d,o as c,a as m,a6 as p,u as f,i as h,q as g}from"./index-8JNaYjgU.js";/**
 * @license lucide-vue-next v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const x=i("ChevronRightIcon",[["path",{d:"m9 18 6-6-6-6",key:"mthhwq"}]]),_=["value"],V={__name:"Input",props:{modelValue:{type:String,default:""}},emits:["update:modelValue"],setup(t,{emit:o}){const s=o,a=d(),n=g(()=>{const{class:e,modelValue:l,"onUpdate:modelValue":b,...u}=a;return u});function r(e){s("update:modelValue",e.target.value)}return(e,l)=>(c(),m("input",p({class:f(h)("flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",e.$attrs.class??"")},n.value,{value:t.modelValue,onInput:r}),null,16,_))}};export{x as C,V as _};
