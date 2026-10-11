(() => {
 'use strict';
 // Load the larger, existing About figures only when their disclosure opens.
 const figures = document.getElementById('oddbAboutFigures');
 if (figures) {
  const loadFigures = () => {
   if (!figures.open) return;
   figures.querySelectorAll('img[data-src]').forEach(image => {
    image.src = image.dataset.src;
    image.removeAttribute('data-src');
   });
  };
  figures.addEventListener('toggle', loadFigures);
  loadFigures();
 }
 const root = document.documentElement;
 const intro = document.getElementById('oddbIntro');
 if (!intro || !root.classList.contains('oddb-intro-pending')) return;
 const skip = intro.querySelector('[data-intro-skip]');
 const previousFocus = document.activeElement;
 const background = Array.from(document.body.children).filter(element =>
  element !== intro && !['SCRIPT', 'STYLE', 'LINK'].includes(element.tagName));
 const previousInert = background.map(element => element.inert);
 background.forEach(element => { element.inert = true; });
 intro.setAttribute('aria-hidden', 'false');
 const media = window.matchMedia('(prefers-reduced-motion: reduce)');
 let done = false;
 let endTimer;
 let fadeTimer;
 function finish() {
  if (done) return;
  done = true;
  window.clearTimeout(endTimer);
  window.clearTimeout(fadeTimer);
  window.clearTimeout(window.__oddbIntroFallback);
  root.classList.remove('oddb-intro-pending');
  intro.setAttribute('aria-hidden', 'true');
  background.forEach((element, index) => { element.inert = previousInert[index]; });
  document.removeEventListener('keydown', onKey);
  document.removeEventListener('visibilitychange', onVisibility);
  window.removeEventListener('pagehide', finish);
  if (media.removeEventListener) media.removeEventListener('change', onMotion);
  if (skip) skip.removeEventListener('click', finish);
  if (intro.contains(document.activeElement)) {
   const target = previousFocus && previousFocus !== document.body && previousFocus.isConnected
    ? previousFocus : document.querySelector('.oddb-nav-brand');
   if (target && !target.inert) target.focus({preventScroll: true});
  }
  delete window.__oddbFinishIntro;
 }
 function onKey(event) {
  if (event.key === 'Escape') finish();
  if (event.key === 'Tab' && skip) {event.preventDefault(); skip.focus();}
 }
 function onVisibility() {if (document.hidden) finish();}
 function onMotion(event) {if (event.matches) finish();}
 window.__oddbFinishIntro = finish;
 const remaining = Math.max(0, (window.__oddbIntroDeadline || 0) - performance.now());
 if (remaining === 0 || document.hidden || media.matches) {finish(); return;}
 document.addEventListener('keydown', onKey);
 document.addEventListener('visibilitychange', onVisibility);
 window.addEventListener('pagehide', finish, {once: true});
 if (media.addEventListener) media.addEventListener('change', onMotion);
 if (skip) {skip.addEventListener('click', finish); skip.focus({preventScroll: true});}
 fadeTimer = window.setTimeout(() => intro.classList.add('is-leaving'), Math.max(0, remaining - 180));
 endTimer = window.setTimeout(finish, remaining);
})();
