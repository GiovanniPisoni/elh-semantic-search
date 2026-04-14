import streamlit as st
import streamlit.components.v1 as components
import time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.pipeline import query as rag_query

st.set_page_config(page_title="Scout — ELH AI", page_icon="🏠",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  #MainMenu, footer, header { visibility: hidden; }
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
  [data-testid="stAppViewBlockContainer"] {
    background: #ffffff !important;
  }
  [data-testid="stSidebar"] {
    background: #fff !important; border-right: 1px solid #E2E8F0 !important;
  }
  /* Form */
  [data-testid="stForm"] {
    border: 1.5px solid #E2E8F0 !important; border-radius: 14px !important;
    background: #fff !important; padding: .5rem .9rem !important;
  }
  [data-testid="stFormSubmitButton"] button {
    background: #1D4ED8 !important; color: #fff !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; height: 42px !important;
    white-space: nowrap !important; min-width: 100px !important;
  }
  [data-testid="stFormSubmitButton"] button:hover { background: #2563EB !important; }
  /* sidebar toggle always visible */
  [data-testid="stSidebarCollapsedControl"] {
    display: flex !important; visibility: visible !important;
  }
  [data-testid="stTextInput"] input {
    border: none !important; box-shadow: none !important;
    font-size: .97rem !important; background: transparent !important;
    color: #0F172A !important;
  }
  [data-testid="stTextInput"] input::placeholder { color: #94A3B8 !important; }
  /* Quick chips */
  [data-testid="stSidebar"] button,
  button[kind="secondary"] {
    background: #F8FAFC !important; border: 1.5px solid #E2E8F0 !important;
    color: #475569 !important; border-radius: 20px !important;
    font-size: .83rem !important;
  }
  button[kind="secondary"]:hover {
    border-color: #93C5FD !important; color: #1D4ED8 !important;
    background: #EFF6FF !important;
  }
  /* Answer */
  .elh-answer {
    font-size: .97rem; line-height: 1.8; color: #0F172A; margin-bottom: 1rem;
  }
  .elh-answer strong, .elh-answer b { color: #1D4ED8; }
  /* Property cards */
  .prop-card {
    background: #fff; border: 1.5px solid #E2E8F0; border-radius: 12px;
    padding: .9rem 1rem; margin-bottom: .6rem;
  }
  .prop-card:hover { border-color: #93C5FD; }
  .prop-name { font-weight: 700; font-size: .9rem; color: #0F172A; }
  .prop-loc  { font-size: .78rem; color: #64748B; }
  .prop-score {
    background: #EFF6FF; color: #1D4ED8; font-size: .72rem;
    font-weight: 700; border-radius: 20px; padding: 2px 9px;
  }
  .prop-stars { color: #F59E0B; font-size: .82rem; }
  .prop-text  {
    font-size: .8rem; color: #475569; line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 3;
    -webkit-box-orient: vertical; overflow: hidden;
  }
  [data-testid="stMetric"] {
    background: #F8FAFC !important; border: 1.5px solid #E2E8F0 !important;
    border-radius: 10px !important; padding: .7rem .9rem !important;
  }
  /* Left col scrolls, right col sticky like Claude artifacts */
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
    overflow-y: auto;
    max-height: calc(100vh - 120px);
    padding-right: 1rem;
  }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
    position: sticky;
    top: 0;
    overflow-y: auto;
    max-height: calc(100vh - 120px);
    border-left: 1px solid #E2E8F0;
    padding-left: 1.2rem;
  }
</style>
""", unsafe_allow_html=True)

# ── LOADING ANIMATIONS ────────────────────────────────────
LOADING_HTML = """<!DOCTYPE html><html><body style="margin:0;padding:0;background:#fff;font-family:system-ui;">
<div style="border:1.5px solid #E2E8F0;border-radius:10px;padding:8px 12px 7px;">
  <canvas id="cv" height="38" style="width:100%;height:38px;display:block;"></canvas>
  <div style="height:1px;background:#E2E8F0;margin:5px 0 4px;"></div>
  <div style="font-size:11px;color:#94A3B8;">Scout is searching<span id="d"></span></div>
</div>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  var N=14,rx=-20,t=0;
  function resize(){cv.width=cv.offsetWidth||680;}resize();
  function house(cx,filled){
    var H=cv.height,gnd=H-2,w=18,h=20,bx=cx-w/2,by=gnd-h;
    ctx.strokeStyle=filled?'#1D4ED8':'#CBD5E1';ctx.lineWidth=1.6;ctx.lineJoin='round';
    ctx.fillStyle=filled?'rgba(29,78,216,0.08)':'rgba(0,0,0,0)';
    ctx.beginPath();ctx.moveTo(bx-2,by+h*0.42);ctx.lineTo(cx,by);
    ctx.lineTo(bx+w+2,by+h*0.42);ctx.lineTo(bx+w+2,by+h);ctx.lineTo(bx-2,by+h);
    ctx.closePath();ctx.fill();ctx.stroke();
    var dw=5,dh=8,dx=cx-dw/2,dy=by+h-dh;
    ctx.fillStyle=filled?'#1D4ED8':'#CBD5E1';
    ctx.beginPath();ctx.moveTo(dx,by+h);ctx.lineTo(dx,dy+dh*0.35);
    ctx.quadraticCurveTo(dx,dy,dx+dw/2,dy);ctx.quadraticCurveTo(dx+dw,dy,dx+dw,dy+dh*.35);
    ctx.lineTo(dx+dw,by+h);ctx.closePath();ctx.fill();
  }
  function runner(x){
    var H=cv.height,gnd=H-2,ph=t*0.26,C='#1D4ED8',CD='#1E40AF',gy=gnd;
    ctx.strokeStyle=C;ctx.lineWidth=2.2;ctx.lineCap='round';
    var l1=Math.sin(ph)*6,l2=Math.sin(ph+Math.PI)*6;
    var lly=Math.abs(Math.cos(ph))*5,lry=Math.abs(Math.cos(ph+Math.PI))*5;
    ctx.beginPath();ctx.moveTo(x,gy-9);ctx.lineTo(x+l1*.5,gy-4);ctx.lineTo(x+l1,gy-lly);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x,gy-9);ctx.lineTo(x+l2*.5,gy-4);ctx.lineTo(x+l2,gy-lry);ctx.stroke();
    ctx.fillStyle=C;ctx.beginPath();ctx.roundRect(x-3,gy-19,6,10,1.5);ctx.fill();
    ctx.strokeStyle=CD;ctx.lineWidth=1.8;
    ctx.beginPath();ctx.moveTo(x-2,gy-17);ctx.lineTo(x-2+Math.sin(ph+Math.PI)*5,gy-12);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+2,gy-17);ctx.lineTo(x+2+Math.sin(ph)*5,gy-12);ctx.stroke();
    ctx.fillStyle=C;ctx.beginPath();ctx.arc(x,gy-23,4.5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=CD;ctx.beginPath();ctx.arc(x,gy-26,3,Math.PI,0);ctx.fill();
  }
  function loop(){
    var W=cv.offsetWidth||680;if(cv.width!==W)cv.width=W;
    ctx.clearRect(0,0,W,cv.height);
    var sw=W/N,np=Math.max(-1,Math.floor((rx-sw*.1)/sw));
    for(var i=0;i<N;i++)house(sw*i+sw/2,i<=np);
    if(rx>-25&&rx<W+25)runner(rx);
    rx+=2.4;t++;if(rx>W+28)rx=-28;
    requestAnimationFrame(loop);
  }
  loop();
  var di=0,del=document.getElementById('d');
  setInterval(function(){di=(di+1)%4;del.textContent='.'.repeat(di);},380);
})();
</script></body></html>"""

DONE_HTML="""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#fff;font-family:system-ui;">
<div style="border:1.5px solid #E2E8F0;border-radius:10px;padding:8px 12px 7px;">
  <canvas id="cv" height="38" style="width:100%;height:38px;display:block;"></canvas>
  <div style="height:1px;background:#E2E8F0;margin:5px 0 4px;"></div>
  <div style="font-size:11px;color:#16A34A;display:flex;align-items:center;gap:5px;">
    <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
      <polyline points="2,6 5,9 10,3" stroke="#16A34A" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>Found it!
  </div>
</div>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  cv.width=cv.offsetWidth||680;
  var N=14,H=cv.height,W=cv.width,sw=W/N;
  function house(cx){
    var gnd=H-2,w=18,h=20,bx=cx-w/2,by=gnd-h;
    ctx.strokeStyle='#16A34A';ctx.lineWidth=1.6;ctx.lineJoin='round';
    ctx.fillStyle='rgba(22,163,74,0.08)';
    ctx.beginPath();ctx.moveTo(bx-2,by+h*.42);ctx.lineTo(cx,by);
    ctx.lineTo(bx+w+2,by+h*.42);ctx.lineTo(bx+w+2,by+h);ctx.lineTo(bx-2,by+h);
    ctx.closePath();ctx.fill();ctx.stroke();
    var dw=5,dh=8,dx=cx-dw/2,dy=by+h-dh;
    ctx.fillStyle='#16A34A';
    ctx.beginPath();ctx.moveTo(dx,by+h);ctx.lineTo(dx,dy+dh*.35);
    ctx.quadraticCurveTo(dx,dy,dx+dw/2,dy);ctx.quadraticCurveTo(dx+dw,dy,dx+dw,dy+dh*.35);
    ctx.lineTo(dx+dw,by+h);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#16A34A';ctx.lineWidth=1.2;ctx.lineCap='round';
    ctx.beginPath();ctx.moveTo(cx-4,by+h*.55);ctx.lineTo(cx-1,by+h*.72);ctx.lineTo(cx+5,by+h*.38);ctx.stroke();
  }
  ctx.clearRect(0,0,W,H);
  for(var i=0;i<N;i++)house(sw*i+sw/2);
})();
</script></body></html>"""

SUGGESTIONS=[
    "🛏️ Comfortable bed","📶 Fast WiFi","🧹 Cleanliness reviews",
    "🚇 Near metro","🚿 Private bathroom","🌇 City views",
    "💬 Responsive landlords","💰 Best value",
]

for k,v in [("last_result",None),("prefill",""),("auto",False),("current_q",""),("history",[])]:
    if k not in st.session_state: st.session_state[k]=v

# ── SIDEBAR ───────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p style="font-size:.75rem;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.07em;margin-bottom:.5rem;">Search settings</p>', unsafe_allow_html=True)
    top_k=st.slider("Reviews",3,10,5)
    city_filter=st.selectbox("City",["All cities","Lisbon","Porto"])
    city_filter=None if city_filter=="All cities" else city_filter
    min_rating=st.select_slider("Min rating",[1,2,3,4,5],1,
                                format_func=lambda x:"★"*x+"☆"*(5-x))
    min_rating=None if min_rating==1 else min_rating
    st.divider()
    if st.session_state["history"]:
        st.markdown("**Recent**")
        for item in st.session_state["history"]:
            if st.button(f"↩ {item['q'][:32]}",key=f"sh_{item['q'][:28]}",use_container_width=True):
                st.session_state["prefill"]=item["q"]
                st.session_state["auto"]=True
                st.rerun()

has_result = st.session_state["last_result"] is not None

def run_query(q):
    return rag_query(q, top_k=top_k, city_filter=city_filter, min_rating=min_rating)

def save_result(q, result):
    st.session_state["last_result"] = result
    st.session_state["current_q"] = q
    h = st.session_state["history"]
    if q not in [x["q"] for x in h]:
        h.insert(0, {"q": q, "n": len(result["sources"])})
    st.session_state["history"] = h[:10]

# ══════════════════════════════════════════════════════════
# WELCOME
# ══════════════════════════════════════════════════════════
if not has_result:
    # Spazio verticale per centrare
    st.markdown("<div style='height:12vh'></div>", unsafe_allow_html=True)

    # Titolo centrato
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.markdown("""
        <div style="text-align:center; margin-bottom:1.8rem;">
          <div style="width:52px;height:52px;background:#1D4ED8;border-radius:14px;
                      display:inline-flex;align-items:center;justify-content:center;
                      font-size:1.5rem;margin-bottom:.9rem;">🏠</div>
          <h1 style="font-size:2rem;font-weight:800;color:#0F172A;
                     letter-spacing:-.03em;margin:0 0 .3rem;">Welcome to ErASKmus</h1>
          <p style="font-size:.95rem;color:#94A3B8;margin:0;">
            Your ELH AI — find the perfect room in Lisbon &amp; Porto
          </p>
        </div>
        """, unsafe_allow_html=True)

        loading_slot = st.empty()

        with st.form(key="welcome_form", clear_on_submit=False):
            q_col, btn_col = st.columns([5,1])
            with q_col:
                question = st.text_input("q",
                    value=st.session_state.get("prefill",""),
                    placeholder="Find me a room with a comfortable bed near the metro...",
                    label_visibility="collapsed")
            with btn_col:
                submitted = st.form_submit_button("Search →", type="primary", use_container_width=True)

        if st.session_state.get("prefill"): st.session_state["prefill"]=""
        if st.session_state.get("auto"): st.session_state["auto"]=False; submitted=True

    # Chips suggerimenti
    st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)
    _, mid2, _ = st.columns([1, 2, 1])
    with mid2:
        chip_cols = st.columns(4)
        for idx, sug in enumerate(SUGGESTIONS):
            with chip_cols[idx % 4]:
                if st.button(sug, key=f"sug_{idx}", use_container_width=True):
                    st.session_state["prefill"] = sug.split(" ", 1)[1]
                    st.session_state["auto"] = True
                    st.rerun()

    if submitted and question.strip():
        _, mid3, _ = st.columns([1,2,1])
        with mid3:
            with loading_slot:
                components.html(LOADING_HTML, height=76, scrolling=False)
        result = run_query(question.strip())
        with loading_slot:
            components.html(DONE_HTML, height=76, scrolling=False)
        time.sleep(1.2)
        save_result(question.strip(), result)
        st.rerun()


# ══════════════════════════════════════════════════════════
# CHAT RESULT
# ══════════════════════════════════════════════════════════
else:
    result = st.session_state["last_result"]
    current_q = st.session_state.get("current_q","")

    # ── header ────────────────────────────────────────────
    h1, h2, h3 = st.columns([1, 10, 1])
    with h1:
        if st.button("← New", key="back"):
            st.session_state["last_result"] = None
            st.session_state["current_q"] = ""
            st.rerun()
    with h2:
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:8px;padding:.4rem 0;">
          <div style="width:22px;height:22px;background:#1D4ED8;border-radius:5px;
                      display:inline-flex;align-items:center;justify-content:center;
                      color:#fff;font-size:.75rem;">🏠</div>
          <span style="font-weight:800;color:#1D4ED8;font-size:.9rem;">Scout</span>
          <span style="color:#E2E8F0;margin:0 3px;">|</span>
          <span style="color:#64748B;font-size:.85rem;font-style:italic;">"{current_q}"</span>
        </div>""", unsafe_allow_html=True)
    st.markdown('<hr style="margin:.3rem 0 1.2rem;border-color:#E2E8F0;">', unsafe_allow_html=True)

    # ── contenuto split ───────────────────────────────────
    # LEFT: input domanda in alto, risposta sotto
    # RIGHT: pannello fisso con property cards
    col_ans, col_cards = st.columns([1,1], gap="medium")

    with col_ans:
        # ── nuova domanda (in cima alla colonna sx) ───────
        loading_slot2 = st.empty()
        with st.form(key="chat_form", clear_on_submit=True):
            fi1, fi2 = st.columns([5,1])
            with fi1:
                new_q = st.text_input("nq",
                    value=st.session_state.get("prefill",""),
                    placeholder="Ask another question...",
                    label_visibility="collapsed")
            with fi2:
                sub2 = st.form_submit_button("Search →", type="primary", use_container_width=True)

        if st.session_state.get("prefill"): st.session_state["prefill"]=""
        if st.session_state.get("auto"): st.session_state["auto"]=False; sub2=True

        if sub2 and new_q.strip():
            with loading_slot2:
                components.html(LOADING_HTML, height=76, scrolling=False)
            result2 = run_query(new_q.strip())
            with loading_slot2:
                components.html(DONE_HTML, height=76, scrolling=False)
            time.sleep(1.2)
            save_result(new_q.strip(), result2)
            st.rerun()

        # ── risposta testuale ─────────────────────────────
        st.markdown('<p style="font-size:.72rem;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:.08em;margin:.8rem 0 .4rem;">Answer</p>', unsafe_allow_html=True)
        ans = result["answer"].replace("\n","<br>")
        st.markdown(f'<div class="elh-answer">{ans}</div>', unsafe_allow_html=True)

        sources = result["sources"]
        if sources:
            st.divider()
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Reviews", len(sources))
            m2.metric("Avg match", f"{int(sum(s['score'] for s in sources)/len(sources)*100)}%")
            m3.metric("Avg rating", f"{sum(s['metadata'].get('overall_rating',0) for s in sources)/len(sources):.1f}/5")
            m4.metric("Cities", ", ".join(filter(None,set(s["metadata"].get("city","") for s in sources))))

    # ── colonna destra fissa ──────────────────────────────
    with col_cards:
        st.markdown("""
        <style>
          /* Pannello dx fisso come artefatto Claude */
          [data-testid="stHorizontalBlock"] > div:last-child {
            position: sticky !important;
            top: 1rem !important;
            max-height: calc(100vh - 100px) !important;
            overflow-y: auto !important;
            border-left: 1px solid #E2E8F0;
            padding-left: 1.5rem !important;
          }
        </style>""", unsafe_allow_html=True)

        sources = result["sources"]
        st.markdown(f'<p style="font-size:.72rem;font-weight:700;color:#94A3B8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.5rem;">{len(sources)} properties found</p>', unsafe_allow_html=True)
        for i, src in enumerate(sources, 1):
            m=src["metadata"]; score=src.get("score",0)
            flat=m.get("flatname","—"); zone=m.get("zone","")
            city_m=m.get("city",""); rating=m.get("overall_rating",0)
            stars="★"*int(rating)+"☆"*(5-int(rating)) if rating else "—"
            roomname=m.get("roomname",""); title=m.get("review_title","")
            orig=(m.get("review_text_original","") or "")[:180]+"…"
            card=f"""<div class="prop-card">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.3rem;">
    <div><div class="prop-name">{flat}</div>
    <div class="prop-loc">📍 {zone}{', ' if zone and city_m else ''}{city_m}</div></div>
    <span class="prop-score">{int(score*100)}% match</span>
  </div>
  <div class="prop-stars">{stars} <span style="color:#64748B;font-size:.75rem;">{rating}/5</span>
    {f'<span style="margin-left:6px;font-size:.75rem;color:#475569;">· {roomname}</span>' if roomname else ''}
  </div>
  {f'<div style="font-size:.8rem;color:#1D4ED8;font-style:italic;margin:.25rem 0 .15rem;">"{title}"</div>' if title else ''}
  <div class="prop-text">{orig}</div>
</div>"""
            st.markdown(card, unsafe_allow_html=True)