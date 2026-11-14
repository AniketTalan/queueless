from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

CUSTOMER_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QueueLess</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; margin: 0; background: #f4f6fb; color: #1d2939; }
  main { max-width: 440px; margin: 0 auto; padding: 20px 16px; }
  .card { background: #fff; border-radius: 14px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); }
  h1 { font-size: 22px; margin: 0 0 6px; }
  .muted { color: #667085; font-size: 14px; line-height: 1.5; margin: 4px 0; }
  .label { font-size: 14px; color: #344054; margin-bottom: 8px; }
  .big { font-size: 56px; font-weight: 700; text-align: center; margin: 10px 0; }
  .status { font-size: 18px; font-weight: 600; margin: 8px 0; }
  .called { color: #067647; }
  input { width: 100%; box-sizing: border-box; padding: 12px; font-size: 16px; border: 1px solid #d0d5dd; border-radius: 10px; }
  button { width: 100%; padding: 14px; font-size: 16px; border: 0; border-radius: 10px; background: #1d4ed8; color: #fff; margin-top: 12px; cursor: pointer; }
  button:disabled { background: #98a2b3; cursor: default; }
  button.secondary { background: #fff; color: #b42318; border: 1px solid #fecdca; }
  .error { color: #b42318; font-size: 14px; margin-top: 8px; min-height: 18px; }
  .hidden { display: none; }
</style>
</head>
<body>
<main>
  <div class="card">
    <h1 id="queueName">Loading queue...</h1>
    <div class="muted" id="queueState"></div>
  </div>

  <div class="card" id="joinCard">
    <div class="label">Your name (optional)</div>
    <input id="customerName" maxlength="80" placeholder="Enter your name">
    <button id="joinBtn">Get my token</button>
    <div class="error" id="joinError"></div>
  </div>

  <div class="card hidden" id="tokenCard">
    <div class="label">Your token number</div>
    <div class="big" id="tokenNumber">-</div>
    <div class="status" id="tokenStatus"></div>
    <div class="muted" id="positionLine"></div>
    <div class="muted" id="etaLine"></div>
    <div class="muted" id="nowServing"></div>
    <div class="muted">This page updates automatically every 5 seconds. Keep it open.</div>
    <button class="secondary hidden" id="cancelBtn">Cancel my token</button>
    <div class="error" id="tokenError"></div>
  </div>
</main>
<script>
const code = window.location.pathname.split("/").filter(Boolean).pop();
const storageKey = "queueless-token-" + code;
const POLL_MS = 5000;
const STATUS_TEXT = {
  waiting: "Waiting in line",
  held: "On hold. Tell staff when you are back.",
  called: "Please go to the counter now",
  completed: "Visit completed. Thank you!",
  no_show: "Marked as no-show",
  cancelled: "Token cancelled"
};
const FINAL_STATUSES = ["completed", "no_show", "cancelled"];
let pollTimer = null;

const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  if (!res.ok) {
    const error = new Error(body && typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.");
    error.status = res.status;
    throw error;
  }
  return body;
}

function formatWait(seconds) {
  if (seconds <= 0) return "Your turn is next.";
  return "Estimated wait: about " + Math.max(1, Math.round(seconds / 60)) + " min";
}

function showToken(t) {
  $("joinCard").classList.add("hidden");
  $("tokenCard").classList.remove("hidden");
  $("tokenNumber").textContent = "#" + t.number;
  $("tokenStatus").textContent = STATUS_TEXT[t.status] || t.status;
  $("tokenStatus").className = "status" + (t.status === "called" ? " called" : "");
  $("positionLine").textContent = t.position ? "Position in line: " + t.position : "";
  $("etaLine").textContent = t.status === "waiting" ? formatWait(t.estimated_wait_seconds) : "";
  $("nowServing").textContent = t.now_serving && t.now_serving.length ? "Now serving: " + t.now_serving.join(", ") : "";
  $("cancelBtn").classList.toggle("hidden", !(t.status === "waiting" || t.status === "held"));
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => { loadQueue(); refreshToken(); }, POLL_MS);
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

async function loadQueue() {
  try {
    const q = await api("/api/public/queues/" + code);
    $("queueName").textContent = q.queue_name;
    const serving = q.now_serving.length ? "Now serving: " + q.now_serving.join(", ") : "No one is being served yet.";
    $("queueState").textContent = (q.is_open ? "Open" : "Closed") + " | " + q.waiting + " waiting | " + serving;
    $("joinBtn").disabled = !q.is_open;
    if (!q.is_open) $("joinError").textContent = "This queue is closed right now.";
    else if ($("joinError").textContent === "This queue is closed right now.") $("joinError").textContent = "";
  } catch (e) {
    $("queueName").textContent = "Queue not found";
    $("queueState").textContent = "Check the QR code and try again.";
    $("joinCard").classList.add("hidden");
    stopPolling();
  }
}

async function refreshToken() {
  const saved = localStorage.getItem(storageKey);
  if (!saved) return;
  try {
    const t = await api("/api/public/tokens/" + saved);
    showToken(t);
    $("tokenError").textContent = "";
    if (FINAL_STATUSES.includes(t.status)) {
      localStorage.removeItem(storageKey);
      stopPolling();
      $("cancelBtn").classList.add("hidden");
    }
  } catch (e) {
    if (e.status === 404) {
      localStorage.removeItem(storageKey);
      stopPolling();
      $("tokenCard").classList.add("hidden");
      $("joinCard").classList.remove("hidden");
    } else {
      $("tokenError").textContent = "Connection problem. Retrying...";
    }
  }
}

$("joinBtn").addEventListener("click", async () => {
  $("joinError").textContent = "";
  $("joinBtn").disabled = true;
  try {
    const name = $("customerName").value.trim();
    const t = await api("/api/public/queues/" + code + "/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ customer_name: name || null })
    });
    localStorage.setItem(storageKey, t.token_code);
    showToken(t);
    startPolling();
  } catch (e) {
    $("joinError").textContent = e.message;
  } finally {
    $("joinBtn").disabled = false;
  }
});

$("cancelBtn").addEventListener("click", async () => {
  const saved = localStorage.getItem(storageKey);
  if (!saved || !confirm("Cancel your token? You will lose your place in line.")) return;
  try {
    const t = await api("/api/public/tokens/" + saved + "/cancel", { method: "POST" });
    showToken(t);
    localStorage.removeItem(storageKey);
    stopPolling();
  } catch (e) {
    $("tokenError").textContent = e.message;
  }
});

loadQueue();
if (localStorage.getItem(storageKey)) {
  refreshToken();
  startPolling();
}
</script>
</body>
</html>
"""


@router.get("/q/{code}", response_class=HTMLResponse)
def customer_page(code: str) -> HTMLResponse:
    return HTMLResponse(CUSTOMER_PAGE)
