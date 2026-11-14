from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QueueLess</title>
<style>
body{font-family:system-ui,sans-serif;background:#f4f7fb;margin:0;padding:12px;color:#1a2433}
.card{max-width:420px;margin:16px auto;background:#fff;border-radius:16px;padding:20px;box-shadow:0 2px 12px rgba(0,0,0,.08)}
h1{font-size:20px;margin:0 0 4px}
.muted{color:#6b778c;font-size:14px}
input{width:100%;box-sizing:border-box;padding:12px;font-size:16px;border:1px solid #cdd5e0;border-radius:10px;margin:12px 0}
button{width:100%;padding:12px;font-size:16px;border:0;border-radius:10px;background:#0b6e4f;color:#fff;cursor:pointer}
button.secondary{background:#fff;color:#b42318;border:1px solid #b42318;margin-top:12px}
button.lang{width:auto;float:right;padding:6px 12px;font-size:14px;background:#e6efe9;color:#0b6e4f}
.big{font-size:56px;font-weight:700;text-align:center;margin:8px 0}
.row{display:flex;justify-content:space-between;font-size:15px;padding:8px 0;border-bottom:1px solid #eef2f7}
.hide{display:none}
</style>
</head>
<body>
<div class="card">
<button class="lang" id="langBtn"></button>
<h1 id="qname">QueueLess</h1>
<div class="muted" id="sub"></div>
<div id="joinBox">
<p class="muted" id="jt"></p>
<input id="name" maxlength="80">
<button id="joinBtn"></button>
</div>
<div id="statusBox" class="hide">
<div class="muted" id="tokLbl"></div>
<div class="big" id="num">-</div>
<div class="row"><span id="l1"></span><b id="pos">-</b></div>
<div class="row"><span id="l2"></span><b id="eta">-</b></div>
<div class="row"><span id="l3"></span><b id="serving">-</b></div>
<div class="row"><span id="l4"></span><b id="stat">-</b></div>
<button class="secondary" id="cancelBtn"></button>
</div>
<p class="muted" id="msg"></p>
</div>
<script>
const code = location.pathname.split('/').filter(Boolean).pop();
const API = '/api/public';
const $ = id => document.getElementById(id);
const S = {
 en: {title:'Join the queue', ph:'Your name (optional)', join:'Join queue', tok:'Your token', pos:'Your position', eta:'Estimated wait (min)', serving:'Now serving', st:'Status', cancel:'Cancel my token', wc:'People waiting', closed:'This queue is closed right now.', called:"It's your turn! Please go to the counter.", done:'Done. Thank you for visiting!', cancelled:'Your token was cancelled.', err:'Something went wrong. Please try again.', lost:'We could not find your token. Please join again.', lang:'हिन्दी', s_waiting:'Waiting', s_called:'Your turn', s_completed:'Completed', s_cancelled:'Cancelled', s_no_show:'Marked absent', s_held:'On hold'},
 hi: {title:'कतार में शामिल हों', ph:'आपका नाम (वैकल्पिक)', join:'कतार में जुड़ें', tok:'आपका टोकन', pos:'आपकी स्थिति', eta:'अनुमानित प्रतीक्षा (मिनट)', serving:'अभी चल रहा है', st:'स्थिति', cancel:'मेरा टोकन रद्द करें', wc:'प्रतीक्षा में लोग', closed:'यह कतार अभी बंद है।', called:'आपकी बारी आ गई है! कृपया काउंटर पर जाएँ।', done:'सेवा पूरी हुई। धन्यवाद!', cancelled:'आपका टोकन रद्द कर दिया गया।', err:'कुछ गड़बड़ हुई। फिर से कोशिश करें।', lost:'आपका टोकन नहीं मिला। फिर से जुड़ें।', lang:'English', s_waiting:'प्रतीक्षा में', s_called:'आपकी बारी', s_completed:'पूरा हुआ', s_cancelled:'रद्द', s_no_show:'अनुपस्थित', s_held:'रोका गया'}
};
let lang = localStorage.getItem('ql_lang') || 'en';
const tokenKey = 'ql_tok_' + code;
let tokenCode = localStorage.getItem(tokenKey);
const t = k => S[lang][k] || S.en[k];

function paint() {
 $('langBtn').textContent = t('lang');
 $('jt').textContent = t('title');
 $('name').placeholder = t('ph');
 $('joinBtn').textContent = t('join');
 $('tokLbl').textContent = t('tok');
 $('l1').textContent = t('pos');
 $('l2').textContent = t('eta');
 $('l3').textContent = t('serving');
 $('l4').textContent = t('st');
 $('cancelBtn').textContent = t('cancel');
}

async function api(path, opts = {}) {
 const r = await fetch(API + path, opts);
 const j = await r.json().catch(() => ({}));
 if (!r.ok) throw new Error(j.detail || t('err'));
 return j;
}

function showQueue(q) {
 $('qname').textContent = q.queue_name;
 $('sub').textContent = t('wc') + ': ' + q.waiting + ' · ' + t('serving') + ': ' + (q.now_serving.join(', ') || '-');
 $('statusBox').classList.add('hide');
 $('joinBox').classList.toggle('hide', !q.is_open);
 if (!q.is_open) $('msg').textContent = t('closed');
}

function showToken(tok) {
 $('joinBox').classList.add('hide');
 $('statusBox').classList.remove('hide');
 $('qname').textContent = tok.queue_name;
 $('num').textContent = tok.number;
 $('pos').textContent = tok.position == null ? '-' : tok.position;
 $('eta').textContent = tok.estimated_wait_seconds == null ? '-' : Math.ceil(tok.estimated_wait_seconds / 60);
 $('serving').textContent = tok.now_serving.join(', ') || '-';
 $('stat').textContent = t('s_' + tok.status);
 $('cancelBtn').classList.toggle('hide', !['waiting', 'held'].includes(tok.status));
 $('msg').textContent = tok.status === 'called' ? t('called') : '';
}

async function poll() {
 try {
  if (!tokenCode) return showQueue(await api('/queues/' + code));
  let tok = null;
  try { tok = await api('/tokens/' + tokenCode); }
  catch (e) { localStorage.removeItem(tokenKey); tokenCode = null; $('msg').textContent = t('lost'); }
  if (!tok) return;
  if (['completed', 'cancelled', 'no_show'].includes(tok.status)) {
   localStorage.removeItem(tokenKey); tokenCode = null;
   if (tok.status === 'completed') $('msg').textContent = t('done');
   showQueue(await api('/queues/' + code));
  } else showToken(tok);
 } catch (e) { $('msg').textContent = e.message; }
}

$('joinBtn').onclick = async () => {
 $('joinBtn').disabled = true;
 try {
  const tok = await api('/queues/' + code + '/join', {
   method: 'POST',
   headers: {'Content-Type': 'application/json'},
   body: JSON.stringify({customer_name: $('name').value.trim() || null})
  });
  tokenCode = tok.token_code;
  localStorage.setItem(tokenKey, tokenCode);
  $('msg').textContent = '';
  showToken(tok);
 } catch (e) { $('msg').textContent = e.message; }
 $('joinBtn').disabled = false;
};

$('cancelBtn').onclick = async () => {
 try {
  await api('/tokens/' + tokenCode + '/cancel', {method: 'POST'});
  localStorage.removeItem(tokenKey); tokenCode = null;
  $('msg').textContent = t('cancelled');
  showQueue(await api('/queues/' + code));
 } catch (e) { $('msg').textContent = e.message; }
};

$('langBtn').onclick = () => {
 lang = lang === 'en' ? 'hi' : 'en';
 localStorage.setItem('ql_lang', lang);
 paint();
 poll();
};

paint();
poll();
setInterval(poll, 5000);
</script>
</body>
</html>
"""

@router.get("/q/{code}", response_class=HTMLResponse)
def customer_page(code: str):
    return HTML
