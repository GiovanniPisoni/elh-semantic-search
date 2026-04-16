"""
src/app.py  —  ErASKmus  |  ELH AI Room Finder
Uso: streamlit run src/app.py --server.fileWatcherType none
"""
import streamlit as st
import streamlit.components.v1 as components
import time, sys, os, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.pipeline import query as rag_query

st.set_page_config(page_title="ErASKmus — ELH AI", page_icon="🏠",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  #MainMenu, footer, header { visibility: hidden; }
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
  [data-testid="stAppViewBlockContainer"] { background:#ffffff !important; }

  /* Zero padding globale — vale per entrambe le pagine */
  [data-testid="stAppViewBlockContainer"],
  [data-testid="stMain"],
  .block-container,
  [data-testid="stVerticalBlock"],
  [data-testid="stVerticalBlockBorderWrapper"],
  div.stMarkdown,
  div.element-container { padding-top: 0 !important; margin-top: 0 !important; }
  [data-testid="stAppViewBlockContainer"] { padding: 0 !important; max-width: 100% !important; }

  /* sidebar */
  [data-testid="stSidebar"] {
    background:#fff !important; border-right:1px solid #E2E8F0 !important;
  }
  [data-testid="stSidebar"] .stSlider>label,
  [data-testid="stSidebar"] .stSelectbox>label,
  [data-testid="stSidebar"] .stSelectSlider>label {
    font-size:.75rem !important; font-weight:600 !important;
    color:#64748B !important; text-transform:uppercase; letter-spacing:.07em;
  }
  [data-testid="stSidebar"] button {
    background:#F8FAFC !important; border:1px solid #E2E8F0 !important;
    color:#334155 !important; border-radius:8px !important; font-size:.83rem !important;
  }
  [data-testid="stSidebar"] button:hover {
    background:#EFF6FF !important; border-color:#93C5FD !important; color:#1D4ED8 !important;
  }
  [data-testid="stSidebar"] hr { border-color:#E2E8F0 !important; }

  /* Welcome — input box */
  .welcome-input-wrap {
    border: 2px solid #1D4ED8;
    border-radius: 14px;
    background: #fff;
    display: flex;
    align-items: center;
    padding: 0 10px 0 18px;
    gap: 8px;
    max-width: 800px;
    margin: 0 auto;
  }

  /* Quick suggestion chips */
  .sug-btn {
    border: 2px solid #1D4ED8 !important;
    border-radius: 12px !important;
    background: #fff !important;
    color: #0F172A !important;
    font-weight: 600 !important;
    font-size: .92rem !important;
    padding: .7rem 1rem !important;
    text-align: left !important;
    height: auto !important;
    min-height: 56px !important;
    line-height: 1.3 !important;
    margin-bottom: .5rem !important;
  }
  .sug-btn:hover {
    background: #EFF6FF !important;
    border-color: #2563EB !important;
  }

  /* Form override for welcome */
  [data-testid="stForm"] {
    border: 2px solid #1D4ED8 !important;
    border-radius: 14px !important;
    background: #fff !important;
    padding: .3rem .5rem .3rem 1rem !important;
    max-width: 100% !important;
  }
  [data-testid="stFormSubmitButton"] button {
    background: #1D4ED8 !important; color: #fff !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 600 !important; height: 44px !important;
    font-size: 1.1rem !important;
    white-space: nowrap !important;
    min-width: 48px !important;
  }
  [data-testid="stFormSubmitButton"] button:hover { background: #2563EB !important; }
  [data-testid="stTextInput"] input {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
    font-size: 1rem !important;
    background: transparent !important;
    color: #0F172A !important;
    padding: .5rem 0 !important;
  }
  [data-testid="stTextInput"] input:focus {
    border: none !important;
    box-shadow: none !important;
    outline: none !important;
  }
  [data-testid="stTextInput"] > div {
    border: none !important;
    box-shadow: none !important;
  }
  [data-testid="stTextInput"] > div:focus-within {
    border: none !important;
    box-shadow: none !important;
  }
  [data-testid="stTextInput"] input::placeholder { color: #94A3B8 !important; }

  /* Chat left panel */
  .chat-left-header {
    background: #EFF6FF;
    padding: .8rem 1.2rem;
    border-radius: 10px;
    margin-bottom: 1rem;
  }

  /* Chat form (bottom) override */
  .bottom-form [data-testid="stForm"] {
    border: 1.5px solid #E2E8F0 !important;
    border-radius: 14px !important;
    max-width: 100% !important;
    padding: .3rem .5rem .3rem 1rem !important;
  }

  /* Chat bubbles */
  .bubble-user {
    background: #1D4ED8; color: #fff;
    border-radius: 18px 18px 4px 18px;
    padding: .65rem 1rem;
    display: inline-block;
    max-width: 80%;
    font-size: .93rem;
    line-height: 1.5;
    margin-bottom: .5rem;
  }
  .bubble-ai {
    background: #F1F5F9; color: #0F172A;
    border-radius: 18px 18px 18px 4px;
    padding: .65rem 1rem;
    display: inline-block;
    max-width: 95%;
    font-size: .93rem;
    line-height: 1.6;
    margin-bottom: .5rem;
  }

  /* Right panel — property cards */
  .right-panel-header {
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: .6rem;
    margin-bottom: 1rem;
  }
  .prop-card {
    border: 1px solid #E2E8F0;
    border-radius: 14px;
    background: #fff;
    overflow: hidden;
    margin-bottom: 1rem;
  }
  .prop-img {
    width: 100%; height: 160px;
    object-fit: cover;
    display: block;
  }
  .prop-img-placeholder {
    width: 100%; height: 160px;
    background: linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%);
    display: flex; align-items: center; justify-content: center;
    font-size: 2rem; color: #93C5FD;
    position: relative;
  }
  .price-badge {
    position: absolute; top: 10px; right: 10px;
    background: #F97316; color: #fff;
    border-radius: 20px; padding: 4px 12px;
    font-size: .8rem; font-weight: 700;
  }
  .prop-body { padding: .8rem 1rem; }
  .prop-title { font-weight: 700; font-size: .97rem; color: #0F172A; margin-bottom: .2rem; }
  .prop-loc { color: #1D4ED8; font-size: .8rem; font-weight: 500; margin-bottom: .5rem; }
  .prop-desc { font-size: .8rem; color: #64748B; line-height: 1.5; margin-bottom: .6rem; }
  .prop-meta { display:flex; gap:1rem; font-size:.78rem; color:#475569; }
  .prop-meta span { display:flex; align-items:center; gap:4px; }

  /* Left col scrollable, right fixed */


  [data-testid="stMetric"] {
    background:#F8FAFC !important; border:1.5px solid #E2E8F0 !important;
    border-radius:10px !important; padding:.7rem .9rem !important;
  }
</style>
""", unsafe_allow_html=True)

# ── PLACEHOLDER DATA ──────────────────────────────────────
PLACEHOLDER_IMGS = [
    "https://images.unsplash.com/photo-1555854877-bab0e564b8d5?w=600&q=80",
    "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=600&q=80",
    "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=600&q=80",
    "https://images.unsplash.com/photo-1484154218962-a197022b5858?w=600&q=80",
    "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=600&q=80",
]
PLACEHOLDER_PRICES = [350, 380, 420, 450, 490, 520, 390, 410]

# ── LOADING ANIMATIONS ────────────────────────────────────
LOADING_HTML = """<!DOCTYPE html><html><body style="margin:0;padding:1px 0 0;background:#fff;font-family:system-ui;">
<canvas id="cv" height="24" style="width:100%;height:24px;display:block;"></canvas>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  var N=14,rx=-12,t=0;
  function resize(){cv.width=cv.offsetWidth||400;}resize();
  function house(cx,filled){
    var H=cv.height,gnd=H-2,w=12,h=14,bx=cx-w/2,by=gnd-h;
    ctx.strokeStyle=filled?'#1D4ED8':'#CBD5E1';ctx.lineWidth=1;ctx.lineJoin='round';
    ctx.fillStyle=filled?'rgba(29,78,216,0.09)':'rgba(0,0,0,0)';
    ctx.beginPath();ctx.moveTo(bx-1,by+h*0.42);ctx.lineTo(cx,by);
    ctx.lineTo(bx+w+1,by+h*0.42);ctx.lineTo(bx+w+1,by+h);ctx.lineTo(bx-1,by+h);
    ctx.closePath();ctx.fill();ctx.stroke();
    var dw=3,dh=5,dx=cx-dw/2,dy=by+h-dh;
    ctx.fillStyle=filled?'#1D4ED8':'#CBD5E1';
    ctx.beginPath();ctx.moveTo(dx,by+h);ctx.lineTo(dx,dy+dh*0.35);
    ctx.quadraticCurveTo(dx,dy,dx+dw/2,dy);ctx.quadraticCurveTo(dx+dw,dy,dx+dw,dy+dh*.35);
    ctx.lineTo(dx+dw,by+h);ctx.closePath();ctx.fill();
  }
  function runner(x){
    var H=cv.height,gnd=H-2,ph=t*0.3,C='#1D4ED8',CD='#1E40AF',gy=gnd;
    ctx.strokeStyle=C;ctx.lineWidth=1.2;ctx.lineCap='round';
    var l1=Math.sin(ph)*3,l2=Math.sin(ph+Math.PI)*3;
    var lly=Math.abs(Math.cos(ph))*3,lry=Math.abs(Math.cos(ph+Math.PI))*3;
    ctx.beginPath();ctx.moveTo(x,gy-5);ctx.lineTo(x+l1*.5,gy-2.5);ctx.lineTo(x+l1,gy-lly);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x,gy-5);ctx.lineTo(x+l2*.5,gy-2.5);ctx.lineTo(x+l2,gy-lry);ctx.stroke();
    ctx.fillStyle=C;ctx.beginPath();ctx.roundRect(x-1.5,gy-11,3,6,1);ctx.fill();
    ctx.strokeStyle=CD;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(x-1,gy-10);ctx.lineTo(x-1+Math.sin(ph+Math.PI)*3,gy-7);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+1,gy-10);ctx.lineTo(x+1+Math.sin(ph)*3,gy-7);ctx.stroke();
    ctx.fillStyle=C;ctx.beginPath();ctx.arc(x,gy-13.5,2.5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=CD;ctx.beginPath();ctx.arc(x,gy-15,1.8,Math.PI,0);ctx.fill();
  }
  function loop(){
    var W=cv.offsetWidth||400;if(cv.width!==W)cv.width=W;
    ctx.clearRect(0,0,W,cv.height);
    var sw=W/N,np=Math.max(-1,Math.floor((rx-sw*.1)/sw));
    for(var i=0;i<N;i++)house(sw*i+sw/2,i<=np);
    if(rx>-15&&rx<W+15)runner(rx);
    rx+=3;t++;if(rx>W+20)rx=-15;
    requestAnimationFrame(loop);
  }
  loop();
})();
</script></body></html>"""

DONE_HTML = """<!DOCTYPE html><html><body style="margin:0;padding:1px 0 0;background:#fff;font-family:system-ui;">
<canvas id="cv" height="24" style="width:100%;height:24px;display:block;"></canvas>
<script>
(function(){
  var cv=document.getElementById('cv'),ctx=cv.getContext('2d');
  cv.width=cv.offsetWidth||400;
  var N=14,H=cv.height,W=cv.width,sw=W/N,t=0;
  function house(cx){
    var gnd=H-2,w=12,h=14,bx=cx-w/2,by=gnd-h;
    ctx.strokeStyle='#16A34A';ctx.lineWidth=1;ctx.lineJoin='round';
    ctx.fillStyle='rgba(22,163,74,0.09)';
    ctx.beginPath();ctx.moveTo(bx-1,by+h*.42);ctx.lineTo(cx,by);
    ctx.lineTo(bx+w+1,by+h*.42);ctx.lineTo(bx+w+1,by+h);ctx.lineTo(bx-1,by+h);
    ctx.closePath();ctx.fill();ctx.stroke();
    var dw=3,dh=5,dx=cx-dw/2,dy=by+h-dh;
    ctx.fillStyle='#16A34A';
    ctx.beginPath();ctx.moveTo(dx,by+h);ctx.lineTo(dx,dy+dh*.35);
    ctx.quadraticCurveTo(dx,dy,dx+dw/2,dy);ctx.quadraticCurveTo(dx+dw,dy,dx+dw,dy+dh*.35);
    ctx.lineTo(dx+dw,by+h);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#16A34A';ctx.lineWidth=.8;ctx.lineCap='round';
    ctx.beginPath();ctx.moveTo(cx-2.5,by+h*.52);ctx.lineTo(cx-.5,by+h*.7);ctx.lineTo(cx+3,by+h*.35);ctx.stroke();
  }
  function celebrant(){
    var gnd=H-2,x=sw*(N-0.5),bounce=Math.abs(Math.sin(t*.15))*5,y=gnd-bounce;
    var C='#16A34A',CD='#166534';
    ctx.fillStyle=C;ctx.beginPath();ctx.arc(x,y-13.5,2.5,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=CD;ctx.beginPath();ctx.arc(x,y-15,1.8,Math.PI,0);ctx.fill();
    ctx.fillStyle=C;ctx.beginPath();ctx.roundRect(x-1.5,y-11,3,6,1);ctx.fill();
    ctx.strokeStyle=C;ctx.lineWidth=1.2;ctx.lineCap='round';
    ctx.beginPath();ctx.moveTo(x-1.5,y-9);ctx.lineTo(x-5,y-14);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+1.5,y-9);ctx.lineTo(x+5,y-14);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x-1,y-5);ctx.lineTo(x-1.5,y);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+1,y-5);ctx.lineTo(x+1.5,y);ctx.stroke();
    var op=(Math.sin(t*.2)+1)/2*.8+.2;
    ctx.fillStyle='rgba(22,163,74,'+op.toFixed(2)+')';
    [[-6,-4],[6,-5],[0,-10],[-4,-8],[5,-3]].forEach(function(s){
      ctx.beginPath();ctx.arc(x+s[0],y+s[1],1.2,0,Math.PI*2);ctx.fill();
    });
  }
  function draw(){
    var W2=cv.offsetWidth||400;if(cv.width!==W2){cv.width=W2;W=W2;}
    ctx.clearRect(0,0,W,H);
    for(var i=0;i<N;i++)house(sw*i+sw/2);
    celebrant(); t++;
    requestAnimationFrame(draw);
  }
  draw();
})();
</script></body></html>"""

# ── SUGGESTIONS ────────────────────────────────────────────
SUGGESTIONS = [
    "Rooms with a comfortable bed",
    "Fast WiFi for studying",
    "Near metro or public transport",
    "Responsive and helpful landlords",
]

# ── SESSION STATE ──────────────────────────────────────────
for k,v in [("last_result",None),("prefill",""),("auto",False),
            ("current_q",""),("history",[]),("chat_history",[])]:
    if k not in st.session_state: st.session_state[k]=v

# ── SIDEBAR ────────────────────────────────────────────────
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

def run_query(q):
    return rag_query(q, top_k=top_k, city_filter=city_filter, min_rating=min_rating)

def save_result(q, result):
    st.session_state["last_result"]=result
    st.session_state["current_q"]=q
    h=st.session_state["history"]
    if q not in [x["q"] for x in h]:
        h.insert(0,{"q":q,"n":len(result["sources"])})
    st.session_state["history"]=h[:10]
    # chat history
    ch=st.session_state["chat_history"]
    ch.append({"role":"user","content":q})
    ch.append({"role":"ai","content":result["answer"]})
    st.session_state["chat_history"]=ch

has_result = st.session_state["last_result"] is not None

# ══════════════════════════════════════════════════════════
# WELCOME
# ══════════════════════════════════════════════════════════
if not has_result:
    st.markdown("<div style='height:10vh'></div>", unsafe_allow_html=True)

    _, mid, _ = st.columns([1,2.2,1])
    with mid:
        # Logo + titolo
        st.markdown("""
        <div style="text-align:center;margin-bottom:1.8rem;">
          <div style="width:80px;height:80px;background:#DBEAFE;border-radius:50%;
                      display:inline-flex;align-items:center;justify-content:center;
                      margin-bottom:1rem;">
            <svg width="38" height="38" viewBox="0 0 24 24" fill="none">
              <path d="M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V15H9V21H4C3.45 21 3 20.55 3 20V10.5Z"
                stroke="#1D4ED8" stroke-width="2" stroke-linejoin="round" fill="none"/>
            </svg>
          </div>
          <h1 style="font-size:2rem;font-weight:800;color:#1D4ED8;
                     letter-spacing:-.02em;margin:0 0 .4rem;">Welcome in ErASKmus</h1>
          <p style="font-size:.97rem;color:#475569;margin:0;">
            Your ELH AI — find the perfect room in Lisbon &amp; Porto
          </p>
        </div>
        """, unsafe_allow_html=True)

        # Form input
        loading_slot = st.empty()
        with st.form(key="welcome_form", clear_on_submit=False):
            q_col, btn_col = st.columns([9,1])
            with q_col:
                question = st.text_input("q",
                    value=st.session_state.get("prefill",""),
                    placeholder="Describe your ideal room...",
                    label_visibility="collapsed")
            with btn_col:
                submitted = st.form_submit_button("➤", type="primary", use_container_width=True)

        if st.session_state.get("prefill"): st.session_state["prefill"]=""
        if st.session_state.get("auto"): st.session_state["auto"]=False; submitted=True

        # Chips
        st.markdown('<p style="text-align:center;font-size:.83rem;color:#94A3B8;margin:1.4rem 1.4rem;">Or try one of these questions:</p>', unsafe_allow_html=True)
        col1, col2 = st.columns(2, gap="medium")
        for idx, sug in enumerate(SUGGESTIONS):
            col = col1 if idx % 2 == 0 else col2
            with col:
                if st.button(sug, key=f"sug_{idx}", use_container_width=True):
                    st.session_state["prefill"]=sug
                    st.session_state["auto"]=True
                    st.rerun()

    if submitted and question.strip():
        with loading_slot:
            components.html(LOADING_HTML, height=32, scrolling=False)
        result = run_query(question.strip())
        with loading_slot:
            components.html(DONE_HTML, height=32, scrolling=False)
        time.sleep(0.3)
        save_result(question.strip(), result)
        st.rerun()

# ══════════════════════════════════════════════════════════
# CHAT RESULT
# ══════════════════════════════════════════════════════════
else:
    result       = st.session_state["last_result"]
    sources      = result["sources"]
    chat_history = st.session_state["chat_history"]

    # CSS: stile chat page come mockup
    st.markdown("""
    <style>
      /* Reset padding globale */
      [data-testid="stAppViewBlockContainer"] { 
        padding: 0 !important; 
        max-width: 100% !important;
      }
      [data-testid="stMain"] { padding: 0 !important; }
      .block-container { padding: 0 !important; }
      
      /* Layout colonne */
      [data-testid="stHorizontalBlock"] {
        gap: 0 !important; 
        margin: 0 !important;
        height: 100vh !important;
      }
      [data-testid="stHorizontalBlock"] > div { 
        padding: 0 !important; 
        height: 100vh !important;
      }
      [data-testid="stColumn"] > div,
      [data-testid="stVerticalBlock"] {
        padding: 0 !important; 
        gap: 0 !important;
      }
      .element-container { 
        margin: 0 !important; 
      }
      
      /* Colonna sinistra con bordo destro */
      [data-testid="stHorizontalBlock"] > div:first-child {
        border-right: 1px solid #E2E8F0 !important;
        position: relative !important;
      }
      
      /* Form input - compatto, fisso in basso */
      [data-testid="stForm"] {
        position: fixed !important;
        bottom: 16px !important;
        left: 16px !important;
        width: calc(50% - 32px) !important;
        height: auto !important;
        max-height: 56px !important;
        border: 2px solid #1D4ED8 !important;
        border-radius: 14px !important;
        padding: 6px 8px 6px 16px !important;
        margin: 0 !important;
        background: #fff !important;
        z-index: 9999 !important;
        box-shadow: 0 -4px 20px rgba(0,0,0,0.08) !important;
        display: flex !important;
        align-items: center !important;
      }
      /* Rimuovi tutto lo spazio extra dentro il form */
      [data-testid="stForm"] > div {
        width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
      }
      [data-testid="stForm"] [data-testid="stVerticalBlock"] {
        gap: 0 !important;
        padding: 0 !important;
      }
      /* Input e bottone sulla stessa riga, compatti */
      [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
        height: 40px !important;
        gap: 8px !important;
        align-items: center !important;
        margin: 0 !important;
        padding: 0 !important;
      }
      [data-testid="stForm"] [data-testid="stHorizontalBlock"] > div {
        height: 40px !important;
        padding: 0 !important;
        margin: 0 !important;
      }
      /* Input text compatto */
      [data-testid="stForm"] [data-testid="stTextInput"] {
        height: 40px !important;
      }
      [data-testid="stForm"] [data-testid="stTextInput"] > div {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
        height: 40px !important;
        min-height: 40px !important;
        padding: 0 !important;
      }
      [data-testid="stForm"] [data-testid="stTextInput"] input {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
        padding: 0 !important;
        height: 40px !important;
        background: transparent !important;
        font-size: 0.95rem !important;
      }
      [data-testid="stForm"] [data-testid="stTextInput"] input:focus {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
      }
      /* Bottone submit compatto */
      [data-testid="stForm"] [data-testid="stFormSubmitButton"] {
        height: 40px !important;
        padding: 0 !important;
        margin: 0 !important;
      }
      [data-testid="stForm"] [data-testid="stFormSubmitButton"] > div {
        height: 40px !important;
      }
      [data-testid="stFormSubmitButton"] button {
        background: #1D4ED8 !important;
        color: #fff !important;
        border: none !important;
        border-radius: 10px !important; 
        height: 40px !important;
        width: 40px !important;
        min-width: 40px !important;
        padding: 0 !important;
        margin: 0 !important;
      }
      [data-testid="stFormSubmitButton"] button:hover {
        background: #2563EB !important;
      }
    </style>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1], gap="small")
    FORM_H = 80

    # ── SINISTRA ───────────────────────────────────────────
    with col_left:
        import html as _html
        bubbles_html = ""
        for msg in chat_history:
            if msg["role"] == "user":
                c = _html.escape(msg["content"])
                bubbles_html += (
                    "<div style=\"display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:.7rem;\">"
                    f"<div class=\"bubble-user\">{c}</div>"
                    "<div style=\"width:30px;height:30px;border-radius:50%;background:#F97316;"
                    "display:flex;align-items:center;justify-content:center;"
                    "color:#fff;font-size:.8rem;flex-shrink:0;\">&#128100;</div>"
                    "</div>"
                )
            else:
                ah = _html.escape(msg["content"]).replace("\n", "<br>")
                bubbles_html += (
                    "<div style=\"display:flex;align-items:flex-start;gap:8px;margin-bottom:.7rem;\">"
                    "<div style=\"width:30px;height:30px;border-radius:50%;background:#DBEAFE;"
                    "display:flex;align-items:center;justify-content:center;flex-shrink:0;\">"
                    "<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\">"
                    "<path d=\"M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V15H9V21H4C3.45 21 3 20.55 3 20V10.5Z\"stroke=\"#1D4ED8\" stroke-width=\"1.8\" stroke-linejoin=\"round\"/>"
                    "</svg></div>"
                    f"<div class=\"bubble-ai\">{ah}</div>"
                    "</div>"
                )

        left_html = (
            "<div style=\"display:flex;flex-direction:column;height:calc(100vh - 80px);overflow:hidden;\">"
            "<div style=\"flex-shrink:0;background:#EFF6FF;padding:.75rem 1rem;border-bottom:1px solid #DBEAFE;\">"
            "<div style=\"font-weight:800;font-size:1rem;color:#1D4ED8;\">ErASKmus AI</div>"
            "<div style=\"font-size:.75rem;color:#64748B;\">Your personal housing assistant</div>"
            "</div>"
            "<div style=\"flex:1;overflow-y:auto;padding:.9rem 1rem 1rem;\">"
            + bubbles_html +
            "</div></div>"
        )
        st.markdown(left_html, unsafe_allow_html=True)

        loading_slot2 = st.empty()

        with st.form(key="chat_form", clear_on_submit=True):
            fi1, fi2 = st.columns([10, 1])
            with fi1:
                new_q = st.text_input("nq",
                    value=st.session_state.get("prefill", ""),
                    placeholder="Ask another question...",
                    label_visibility="collapsed")
            with fi2:
                sub2 = st.form_submit_button("➤", type="primary", use_container_width=True)

        if st.session_state.get("prefill"): st.session_state["prefill"] = ""
        if st.session_state.get("auto"):    st.session_state["auto"] = False; sub2 = True

        if sub2 and new_q.strip():
            with loading_slot2:
                components.html(LOADING_HTML, height=32, scrolling=False)
            result2 = run_query(new_q.strip())
            with loading_slot2:
                components.html(DONE_HTML, height=32, scrolling=False)
            time.sleep(0.3)
            save_result(new_q.strip(), result2)
            st.rerun()

    # ── DESTRA — header + cards in un unico div flex ───────
    with col_right:
        import html as _html
        cards_inner = ""
        for i, src in enumerate(sources):
            m        = src["metadata"]
            flat     = _html.escape(m.get("flatname", "ELH Property"))
            zone     = _html.escape(m.get("zone", ""))
            city_m   = _html.escape(m.get("city", "Lisbon"))
            roomname = _html.escape(m.get("roomname", ""))
            orig     = _html.escape((m.get("review_text_original", "") or "")[:120]) + "…"
            price    = PLACEHOLDER_PRICES[i % len(PLACEHOLDER_PRICES)]
            img_url  = PLACEHOLDER_IMGS[i % len(PLACEHOLDER_IMGS)]
            rooms    = [1, 1, 1, 2, 2, 3][i % 6]
            baths    = [1, 1, 2][i % 3]
            loc      = f"📍 {zone}{', ' if zone and city_m else ''}{city_m}"
            title    = f"{flat}{' — ' + roomname if roomname else ''}"
            cards_inner += (
                "<div class=\"prop-card\">"
                "<div style=\"position:relative;\">"
                f"<img src=\"{img_url}\" class=\"prop-img\" onerror=\"this.style.display='none'\"/>"
                f"<div class=\"price-badge\">€ {price}/month</div>"
                "</div>"
                "<div class=\"prop-body\">"
                f"<div class=\"prop-title\">{title}</div>"
                f"<div class=\"prop-loc\">{loc}</div>"
                f"<div class=\"prop-desc\">{orig}</div>"
                "<div class=\"prop-meta\">"
                f"<span>🛏 {rooms} bed</span>"
                f"<span>🚿 {baths} bath</span>"
                "</div></div></div>"
            )

        right_html = (
            f"<div style=\"display:flex;flex-direction:column;height:100vh;overflow:hidden;border-left:1px solid #E2E8F0;\">"
            "<div style=\"flex-shrink:0;padding:.85rem 1.2rem .6rem;border-bottom:1px solid #E2E8F0;\">"
            "<div style=\"font-size:1.05rem;font-weight:800;color:#1D4ED8;\">Results found</div>"
            f"<div style=\"font-size:.78rem;color:#64748B;\">{len(sources)} properties</div>"
            "</div>"
            "<div style=\"flex:1;min-height:0;overflow-y:auto;padding:.8rem 1.2rem 1rem;\">"
            + cards_inner +
            "</div></div>"
        )
        st.markdown(right_html, unsafe_allow_html=True)