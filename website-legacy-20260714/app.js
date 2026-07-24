document.documentElement.classList.add('js');

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const header = document.querySelector('[data-header]');
const menuButton = document.querySelector('.menu-button');
const navigation = document.querySelector('.site-nav');
let lastFocusedBeforeMenu = null;

requestAnimationFrame(() => document.documentElement.classList.add('is-ready'));

function configuredDemoUrl() {
  const raw = typeof OLIN_DEMO_URL === 'string' ? OLIN_DEMO_URL.trim() : '';
  if (!raw) return '';

  try {
    const url = new URL(raw, window.location.href);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch (_error) {
    return '';
  }
}

const demoUrl = configuredDemoUrl();
document.querySelectorAll('[data-demo-link]').forEach((link) => {
  if (!(link instanceof HTMLAnchorElement)) return;
  if (!demoUrl) {
    const label = link.querySelector('span');
    if (label && link.dataset.demoFallback) label.textContent = link.dataset.demoFallback;
    return;
  }
  link.href = demoUrl;
  if (new URL(demoUrl).origin !== window.location.origin) {
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  }
});

function setMenu(open) {
  if (!menuButton || !navigation) return;
  menuButton.setAttribute('aria-expanded', String(open));
  const menuLabel = menuButton.querySelector('.sr-only');
  if (menuLabel) menuLabel.textContent = open ? 'Cerrar menú' : 'Abrir menú';
  navigation.classList.toggle('open', open);
  document.body.classList.toggle('menu-open', open);

  if (open) {
    lastFocusedBeforeMenu = document.activeElement;
    navigation.querySelector('a')?.focus();
  } else if (lastFocusedBeforeMenu instanceof HTMLElement) {
    lastFocusedBeforeMenu.focus();
    lastFocusedBeforeMenu = null;
  }
}

menuButton?.addEventListener('click', () => {
  setMenu(menuButton.getAttribute('aria-expanded') !== 'true');
});

navigation?.addEventListener('click', (event) => {
  if (event.target instanceof HTMLAnchorElement || event.target.closest('a')) {
    setMenu(false);
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && menuButton?.getAttribute('aria-expanded') === 'true') {
    setMenu(false);
  }
});

const revealBlocks = [...document.querySelectorAll('.reveal-block')];
if ('IntersectionObserver' in window && !reduceMotion) {
  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.13, rootMargin: '0px 0px -5% 0px' });

  revealBlocks.forEach((element) => revealObserver.observe(element));
} else {
  revealBlocks.forEach((element) => element.classList.add('is-visible'));
}

const profiles = {
  strong: {
    application: 'OL-0142',
    merchant: 'Abarrotes San Luis',
    amount: '$25,000',
    tenure: '9 años',
    coverage: '85%',
    bureau: 'C1',
    bureauDetail: '≥ 670',
    bureauBar: 92,
    dscrBand: 'D1',
    dscr: '2.7',
    dscrBar: 88,
    scoreBand: 'S1',
    score: '81',
    scoreBar: 81,
    tier: '1',
    decision: 'AUTO · REVISIÓN HUMANA',
    reason: 'La combinación más sólida. El piloto todavía exige aprobación y justificación del analista.',
    state: 'approve'
  },
  thin: {
    application: 'OL-0143',
    merchant: 'Abarrotes El Parque',
    amount: '$20,000',
    tenure: '6 años',
    coverage: '68%',
    bureau: 'C3',
    bureauDetail: 'sin expediente',
    bureauBar: 42,
    dscrBand: 'D2',
    dscr: '2.1',
    dscrBar: 68,
    scoreBand: 'S1',
    score: '78',
    scoreBar: 78,
    tier: '11',
    decision: 'COMITÉ',
    reason: 'Poco historial formal: la capacidad y la evidencia operativa requieren revisión humana.',
    state: 'committee'
  },
  stress: {
    application: 'OL-0144',
    merchant: 'Abarrotes La Esquina',
    amount: '$30,000',
    tenure: '3 años',
    coverage: '72%',
    bureau: 'C2',
    bureauDetail: '600–669',
    bureauBar: 65,
    dscrBand: 'D3',
    dscr: '1.3',
    dscrBar: 37,
    scoreBand: 'S2',
    score: '64',
    scoreBar: 64,
    tier: '13',
    decision: 'DECLINE',
    reason: 'La capacidad de pago está por debajo del piso. El rechazo del motor no se puede anular en el piloto.',
    state: 'decline'
  }
};

const consoleElement = document.querySelector('.decision-console');
const profileTabs = [...document.querySelectorAll('[data-profile]')];

function setProfile(profileName, tab) {
  const profile = profiles[profileName];
  if (!profile || !consoleElement) return;

  profileTabs.forEach((button) => {
    const active = button === tab;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
    button.setAttribute('tabindex', active ? '0' : '-1');
  });
  consoleElement.setAttribute('aria-labelledby', tab.id);
  consoleElement.classList.add('is-changing');

  window.setTimeout(() => {
    consoleElement.querySelectorAll('[data-field]').forEach((element) => {
      const key = element.dataset.field;
      if (key && Object.prototype.hasOwnProperty.call(profile, key)) {
        element.textContent = profile[key];
      }
    });

    consoleElement.querySelectorAll('[data-bar]').forEach((bar) => {
      const key = `${bar.dataset.bar}Bar`;
      const value = profile[key];
      if (typeof value === 'number') bar.style.transform = `scaleX(${Math.max(0, Math.min(100, value)) / 100})`;
    });

    consoleElement.querySelector('.console-result')?.setAttribute('data-state', profile.state);
    consoleElement.classList.remove('is-changing');
  }, reduceMotion ? 0 : 150);
}

profileTabs.forEach((tab, index) => {
  tab.addEventListener('click', () => setProfile(tab.dataset.profile, tab));
  tab.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    let nextIndex = index;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = profileTabs.length - 1;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextIndex = (index + 1) % profileTabs.length;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextIndex = (index - 1 + profileTabs.length) % profileTabs.length;
    const nextTab = profileTabs[nextIndex];
    nextTab.focus();
    setProfile(nextTab.dataset.profile, nextTab);
  });
});

const proofSection = document.querySelector('.proof');
if (proofSection && 'IntersectionObserver' in window && !reduceMotion) {
  const countObserver = new IntersectionObserver((entries, observer) => {
    const entry = entries[0];
    if (!entry?.isIntersecting) return;

    proofSection.querySelectorAll('[data-count]').forEach((element) => {
      const target = Number(element.dataset.count);
      const started = performance.now();
      const duration = 650;
      const tick = (now) => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        element.textContent = String(Math.round(target * eased));
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    observer.disconnect();
  }, { threshold: 0.45 });
  countObserver.observe(proofSection);
}

const processSection = document.querySelector('.process');
let ticking = false;

function updateScrollState() {
  const y = window.scrollY;
  header?.classList.toggle('is-scrolled', y > 24);

  if (processSection) {
    const rect = processSection.getBoundingClientRect();
    const start = window.innerHeight * 0.72;
    const distance = rect.height + window.innerHeight * 0.25;
    const progress = Math.max(0, Math.min(1, (start - rect.top) / distance));
    processSection.style.setProperty('--process-progress', String(progress));
  }
  ticking = false;
}

function requestScrollUpdate() {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(updateScrollState);
}

window.addEventListener('scroll', requestScrollUpdate, { passive: true });
window.addEventListener('resize', requestScrollUpdate, { passive: true });
updateScrollState();
