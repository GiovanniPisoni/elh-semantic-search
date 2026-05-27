// DOM diagnostic — paste into DevTools Console while the Streamlit
// chat view is open. Reports the position/size of the key layout
// elements and flags the symptoms of Streamlit 1.57's known quirks
// (the -80px stMain offset, broken column grid, leaking footer).
(function(){
  const out = [];
  const VH = window.innerHeight;
  out.push(`VIEWPORT: ${window.innerWidth} x ${VH}`);
  out.push(`PAGE SCROLLS: ${document.documentElement.scrollHeight > VH ? 'YES (BAD)' : 'NO (good)'}`);
  out.push('');
  out.push('=== HEADERS ===');
  document.querySelectorAll('.col-header').forEach((h, i) => {
    const r = h.getBoundingClientRect();
    out.push(`  [${i}] top=${r.top.toFixed(0)} h=${r.height.toFixed(0)} display=${getComputedStyle(h).display}`);
  });
  out.push('=== SCROLL BODIES ===');
  document.querySelectorAll('.col-scroll').forEach((s, i) => {
    out.push(`  [${i}] h=${s.getBoundingClientRect().height.toFixed(0)} scrollable=${s.scrollHeight > s.clientHeight}`);
  });
  const f = document.querySelector('[data-testid="stForm"]');
  if (f) {
    const r = f.getBoundingClientRect();
    out.push(`=== FORM ===`);
    out.push(`  top=${r.top.toFixed(0)} bottom=${(r.top+r.height).toFixed(0)} white-below=${(VH - r.top - r.height).toFixed(0)}px`);
  }
  console.log(out.join('\n'));
})();
