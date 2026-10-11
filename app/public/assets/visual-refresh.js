/* ODDB v0.8.0: decorative hero only. No application state, requests or data. */
(() => {
 'use strict';
 function init() {
  const hero = document.querySelector('.oddb-home .hero');
  if (!hero) return; // No animation listeners or observers on scientific pages.
  const scene = hero.querySelector('.oddb-retinal-scene');
  const parallax = hero.querySelector('.oddb-retinal-parallax');
  const toggle = hero.querySelector('.oddb-motion-toggle');
  if (!scene || !parallax || !toggle) return;

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const budgetDevice = (navigator.deviceMemory && navigator.deviceMemory <= 2)
   || (navigator.connection && navigator.connection.saveData);
  const storageKey = 'oddbDecorativeMotionPaused';
  let userPaused = false;
  try {userPaused = sessionStorage.getItem(storageKey) === '1';} catch (_) {}
  // Older environments without IntersectionObserver keep the static SVG.
  let visible = false;
  let frame = null;
  let pendingX = 0, pendingY = 0;
  let pointerAttached = false;
  let disposed = false;

  function cancelPointer() {
   if (frame !== null) window.cancelAnimationFrame(frame);
   frame = null;
   pendingX = pendingY = 0;
   parallax.style.removeProperty('--retinal-x');
   parallax.style.removeProperty('--retinal-y');
  }
  function canAnimate() {
   return !disposed && !reduced.matches && !budgetDevice && !userPaused
    && visible && !document.hidden && !document.body.classList.contains('oddb-intro-lock');
  }
  function renderPointer() {
   frame = null;
   if (!canAnimate()) return;
   parallax.style.setProperty('--retinal-x', `${pendingX.toFixed(2)}px`);
   parallax.style.setProperty('--retinal-y', `${pendingY.toFixed(2)}px`);
  }
  function move(event) {
   if (!canAnimate() || event.pointerType === 'touch') return;
   // No element layout reads. Multiple pointer events share a single frame.
   pendingX = Math.max(-4, Math.min(4, (event.clientX / window.innerWidth - .5) * 8));
   pendingY = Math.max(-3, Math.min(3, (event.clientY / window.innerHeight - .5) * 6));
   if (frame === null) frame = window.requestAnimationFrame(renderPointer);
  }
  function update() {
   const running = canAnimate();
   hero.classList.toggle('oddb-motion-running', running);
   hero.classList.toggle('oddb-motion-paused', !running);
   toggle.hidden = reduced.matches || Boolean(budgetDevice) || !('IntersectionObserver' in window);
   toggle.setAttribute('aria-pressed', String(userPaused));
   toggle.textContent = userPaused ? 'Resume background animation' : 'Pause background animation';
   const wantsPointer = running && finePointer.matches;
   if (wantsPointer !== pointerAttached) {
    if (wantsPointer) {
     hero.addEventListener('pointermove', move, {passive: true});
     hero.addEventListener('pointerleave', cancelPointer, {passive: true});
    } else {
     hero.removeEventListener('pointermove', move);
     hero.removeEventListener('pointerleave', cancelPointer);
    }
    pointerAttached = wantsPointer;
   }
   if (!wantsPointer) cancelPointer();
  }
  function clickToggle() {
   userPaused = !userPaused;
   try {sessionStorage.setItem(storageKey, userPaused ? '1' : '0');} catch (_) {}
   update();
  }
  toggle.addEventListener('click', clickToggle);
  document.addEventListener('visibilitychange', update);
  const listen = media => {
   if (media.addEventListener) media.addEventListener('change', update);
   else if (media.addListener) media.addListener(update);
  };
  const unlisten = media => {
   if (media.removeEventListener) media.removeEventListener('change', update);
   else if (media.removeListener) media.removeListener(update);
  };
  listen(reduced);
  listen(finePointer);
  let observer = null;
  if ('IntersectionObserver' in window) {
   observer = new IntersectionObserver(entries => {
    visible = entries.some(entry => entry.isIntersecting);
    update();
   }, {threshold: 0});
   observer.observe(hero);
  }
  // Preserve the original intro, and wait for it to release the page.
  let introObserver = null;
  if (document.body.classList.contains('oddb-intro-lock') && 'MutationObserver' in window) {
   introObserver = new MutationObserver(() => {
    update();
    if (!document.body.classList.contains('oddb-intro-lock')) introObserver.disconnect();
   });
   introObserver.observe(document.body, {attributes: true, attributeFilter: ['class']});
  }
  // Optional one-time arrivals on static homepage headings only. They are
  // always readable, even before the observer fires or when JS is unavailable.
  let revealObserver = null;
  if ('IntersectionObserver' in window && !reduced.matches && !budgetDevice) {
   revealObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
     if (!entry.isIntersecting) return;
     if (!reduced.matches) {
      entry.target.classList.add('oddb-reveal-once');
      entry.target.addEventListener('animationend', () => entry.target.classList.remove('oddb-reveal-once'), {once: true});
     }
     revealObserver.unobserve(entry.target);
    });
   }, {threshold: .15});
   document.querySelectorAll('.oddb-home main .section-heading, .oddb-home #about .eyebrow').forEach(el => revealObserver.observe(el));
  }
  window.addEventListener('pagehide', event => {
   if (event.persisted) {visible = false; update(); return;}
   disposed = true;
   update();
   if (observer) observer.disconnect();
   if (introObserver) introObserver.disconnect();
   if (revealObserver) revealObserver.disconnect();
   document.removeEventListener('visibilitychange', update);
   toggle.removeEventListener('click', clickToggle);
   unlisten(reduced);
   unlisten(finePointer);
  });
  window.addEventListener('pageshow', event => {
   if (!event.persisted || disposed || !observer) return;
   // Reobserve to receive fresh visibility after back/forward cache restore.
   observer.unobserve(hero);
   observer.observe(hero);
  });
  update();
 }
 if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
 else init();
})();
