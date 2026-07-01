// scanner.js - QR Scanner
// Student details are fetched from DB via /api/student_info (no manual form)

let stream = null, scanInterval = null, scanning = false, cooldown = false;

const canvas    = document.getElementById("scanCanvas");
const ctx       = canvas.getContext("2d");
const camStatus = document.getElementById("camStatus");

// ── Camera ────────────────────────────────────────────────────────────────────
async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    camStatus.textContent = "Error";
    camStatus.className   = "badge bg-danger";
    showError("Camera Not Available",
      "Open at http://127.0.0.1:5000 — camera requires localhost.");
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    const video = document.createElement("video");
    video.srcObject = stream;
    video.setAttribute("playsinline", true);
    await video.play();

    canvas.width  = video.videoWidth  || 640;
    canvas.height = video.videoHeight || 480;

    document.getElementById("startBtn").classList.add("d-none");
    document.getElementById("stopBtn").classList.remove("d-none");
    camStatus.textContent = "Live";
    camStatus.className   = "badge bg-success";
    showState("scanning");
    scanning = true;

    function drawFrame() {
      if (!scanning) return;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      requestAnimationFrame(drawFrame);
    }
    drawFrame();

    scanInterval = setInterval(() => {
      if (!cooldown && scanning) captureAndScan();
    }, 800);

  } catch (err) {
    camStatus.textContent = "Error";
    camStatus.className   = "badge bg-danger";
    showError("Camera Error", "Could not access webcam: " + err.message);
  }
}

function stopCamera() {
  scanning = false;
  clearInterval(scanInterval);
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  document.getElementById("startBtn").classList.remove("d-none");
  document.getElementById("stopBtn").classList.add("d-none");
  camStatus.textContent = "Stopped";
  camStatus.className   = "badge bg-secondary";
}

// ── Capture & Decode ──────────────────────────────────────────────────────────
function captureAndScan() {
  const frameData = canvas.toDataURL("image/jpeg", 0.8);
  fetch("/api/scan", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ frame: frameData })
  })
  .then(r => r.json())
  .then(data => {
    if (data.qr_text && data.qr_text.startsWith("TEACHER_SESSION|")) {
      handleTeacherQR(data.qr_text);
    } else if (data.message && data.message !== "No QR code detected") {
      handleStudentQR(data);
    }
  })
  .catch(err => console.warn("Scan error:", err));
}

// ── Teacher QR — fetch student from DB automatically ─────────────────────────
function handleTeacherQR(qrText) {
  const parts = qrText.split("|");
  if (parts.length < 6) { showError("Invalid QR", "Teacher QR format invalid."); return; }

  const token = parts[5];
  cooldown = true;
  camStatus.textContent = "Processing...";
  camStatus.className   = "badge bg-warning text-dark";

  // Fetch logged-in student info from server (no manual input needed)
  fetch("/api/student_info")
    .then(r => r.json())
    .then(info => {
      if (!info.success) {
        // Not logged in as student — still try to mark with empty info
        return markTeacherAttendance(token, "", "", "", "");
      }
      return markTeacherAttendance(
        token,
        info.student_id,
        info.name,
        info.roll_no,
        info.branch
      );
    })
    .catch(() => markTeacherAttendance(token, "", "", "", ""));
}

function markTeacherAttendance(token, studentId, name, rollNo, department) {
  return fetch("/teacher/api/mark", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token:        token,
      student_id:   studentId,
      student_name: name,
      roll_no:      rollNo,
      department:   department
    })
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      stopCamera();
      document.getElementById("resName").textContent    = name    || result.student_name || "—";
      document.getElementById("resRoll").textContent    = rollNo  || "—";
      document.getElementById("resSubject").textContent = result.subject || "—";
      document.getElementById("resTime").textContent    = new Date().toLocaleTimeString();
      addToLog(name || "Student", result.subject, new Date().toLocaleTimeString());
      showState("success");
      setTimeout(() => { cooldown = false; resetScan(); }, 8000);

    } else if (result.message && result.message.toLowerCase().includes("already")) {
      stopCamera();
      document.getElementById("dupMsg").textContent = result.message;
      showState("duplicate");
      setTimeout(() => { cooldown = false; resetScan(); startCamera(); }, 4000);

    } else {
      stopCamera();
      showError("Error", result.message || "Could not mark attendance.");
      setTimeout(() => { cooldown = false; }, 3000);
    }
  })
  .catch(err => { cooldown = false; console.warn(err); });
}

// ── Student QR (admin scan flow) ──────────────────────────────────────────────
function handleStudentQR(data) {
  if (!data.success && !data.duplicate && !data.message) return;
  if (data.success) {
    cooldown = true;
    stopCamera();
    document.getElementById("resName").textContent    = data.name       || "—";
    document.getElementById("resRoll").textContent    = data.roll_no    || "—";
    document.getElementById("resSubject").textContent = data.subject    || "—";
    document.getElementById("resTime").textContent    = data.time       || "—";
    addToLog(data.name, data.subject, data.time);
    showState("success");
    setTimeout(() => { cooldown = false; resetScan(); }, 8000);
  } else if (data.duplicate) {
    cooldown = true;
    stopCamera();
    document.getElementById("dupMsg").textContent = data.message;
    showState("duplicate");
    setTimeout(() => { cooldown = false; resetScan(); startCamera(); }, 4000);
  } else {
    stopCamera();
    showError("Error", data.message || "Something went wrong.");
  }
}

// ── Live Log ──────────────────────────────────────────────────────────────────
function addToLog(name, subject, time) {
  const log   = document.getElementById("liveLog");
  const empty = document.getElementById("logEmpty");
  if (empty) empty.remove();

  const row = document.createElement("div");
  row.className = "list-group-item px-3 py-2 list-group-item-success";
  row.innerHTML = `
    <div class="d-flex justify-content-between align-items-center">
      <div>
        <div class="fw-semibold small">${name}</div>
        <div class="text-muted" style="font-size:.75rem">${subject || ''} &bull; ${time}</div>
      </div>
      <span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Present</span>
    </div>`;
  log.prepend(row);

  const items = log.querySelectorAll(".list-group-item");
  if (items.length > 10) items[items.length - 1].remove();

  const counter = document.getElementById("logCount");
  if (counter) counter.textContent = parseInt(counter.textContent || 0) + 1;
}

// ── UI State ──────────────────────────────────────────────────────────────────
function showState(state) {
  ["idleState","scanningState","successState","errorState","duplicateState"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add("d-none");
  });
  const map = {
    idle:"idleState", scanning:"scanningState",
    success:"successState", error:"errorState", duplicate:"duplicateState"
  };
  const t = document.getElementById(map[state]);
  if (t) t.classList.remove("d-none");
}

function showError(title, msg) {
  document.getElementById("errorTitle").textContent = title;
  document.getElementById("errorMsg").textContent   = msg;
  showState("error");
}

function resetScan() {
  cooldown = false;
  showState("idle");
  document.getElementById("startBtn").classList.remove("d-none");
  document.getElementById("stopBtn").classList.add("d-none");
  camStatus.textContent = "Ready";
  camStatus.className   = "badge bg-secondary";
}
