(() => {
'use strict';

/*
 * ODDB v1 image-led 8-second intro v0.5.5
 *
 * Timeline
 * 0.0–2.25 s  ODDB / eye splash
 * 2.25–4.65 s Human-eye anatomy
 * 4.65–7.40 s Ocular diseases by anatomy
 * 7.40–8.00 s Fade into the real Home page
 */

const STORAGE_KEY='oddbIntroSeenThisSession';
const STAGE_2_AT=2250;
const STAGE_3_AT=4650;
const EXIT_AT=7400;
const END_AT=8000;

function queryParam(name){
 return new URLSearchParams(window.location.search).get(name);
}

function shouldRun(){
 if(window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
 if(queryParam('intro')==='1') return true;
 try{
  return sessionStorage.getItem(STORAGE_KEY)!=='1';
 }catch(_){
  return true;
 }
}

function markSeen(){
 try{sessionStorage.setItem(STORAGE_KEY,'1')}catch(_){}
}

function init(){
 const intro=document.getElementById('oddbIntro');
 if(!intro) return;

 if(!shouldRun()){
  intro.remove();
  document.body.classList.remove('oddb-intro-lock');
  return;
 }

 const stage1=intro.querySelector('.intro-stage-1 img');
 const stage2=intro.querySelector('.intro-stage-2 img');
 const stage3=intro.querySelector('.intro-stage-3 img');

 /* Keep the existing index.php markup compatible with the new exact artwork. */
 if(stage1) stage1.src='assets/oddb-eye-front.svg';
 if(stage2) stage2.src='assets/oddb-eye-anatomy.svg';
 if(stage3) stage3.src='assets/oddb-eye-diseases.svg';

 document.body.classList.add('oddb-intro-lock');
 intro.classList.remove('stage-2','stage-3','stage-exit','is-hidden');
 intro.classList.add('stage-1');

 const timers=[];
 const later=(fn,ms)=>timers.push(window.setTimeout(fn,ms));

 function clearTimers(){
  while(timers.length) window.clearTimeout(timers.pop());
 }

 function setStage(name){
  intro.classList.remove('stage-1','stage-2','stage-3','stage-exit');
  intro.classList.add(name);
 }

 function finish(){
  clearTimers();
  markSeen();
  intro.classList.add('is-hidden');
  document.body.classList.remove('oddb-intro-lock');
  window.setTimeout(()=>intro.remove(),650);
 }

 later(()=>setStage('stage-2'),STAGE_2_AT);
 later(()=>setStage('stage-3'),STAGE_3_AT);
 later(()=>setStage('stage-exit'),EXIT_AT);
 later(finish,END_AT);

 const skip=intro.querySelector('[data-intro-skip]');
 if(skip) skip.addEventListener('click',finish,{once:true});

 const esc=e=>{
  if(e.key==='Escape'){
   document.removeEventListener('keydown',esc);
   finish();
  }
 };
 document.addEventListener('keydown',esc);
}

if(document.readyState==='loading'){
 document.addEventListener('DOMContentLoaded',init,{once:true});
}else{
 init();
}
})();
