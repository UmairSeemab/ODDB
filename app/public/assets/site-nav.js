(() => {
'use strict';

const nav=document.querySelector('.oddb-site-nav');
if(!nav) return;

const button=nav.querySelector('.oddb-nav-toggle');
const menu=nav.querySelector('.oddb-nav-menu');
if(!button||!menu) return;

function closeMenu(){
 button.setAttribute('aria-expanded','false');
 button.setAttribute('aria-label','Open navigation');
 menu.classList.remove('open');
}

button.addEventListener('click',()=>{
 const open=button.getAttribute('aria-expanded')==='true';
 button.setAttribute('aria-expanded',open?'false':'true');
 button.setAttribute('aria-label',open?'Open navigation':'Close navigation');
 menu.classList.toggle('open',!open);
});

menu.querySelectorAll('a').forEach(a=>a.addEventListener('click',closeMenu));

document.addEventListener('keydown',e=>{
 if(e.key==='Escape') closeMenu();
});

window.addEventListener('resize',()=>{
 if(window.innerWidth>940) closeMenu();
});
})();
