// InfraOps NOC Dashboard JavaScript Utilities

// 1. Theme Management
function initTheme() {
  const savedTheme = localStorage.getItem("infraops_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);
  const btn = document.getElementById("theme-toggle-btn");
  if (btn) {
    btn.textContent = savedTheme === "dark" ? "Light Mode" : "Dark Mode";
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const target = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", target);
  localStorage.setItem("infraops_theme", target);
  const btn = document.getElementById("theme-toggle-btn");
  if (btn) {
    btn.textContent = target === "dark" ? "Light Mode" : "Dark Mode";
  }
}

// 2. Zero-dependency Canvas Line Chart Renderer
function drawLineChart(canvasId, points, label, unit, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();

  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  const padding = { top: 20, right: 20, bottom: 30, left: 45 };
  const chartW = w - padding.left - padding.right;
  const chartH = h - padding.top - padding.bottom;

  ctx.clearRect(0, 0, w, h);

  if (!points || points.length === 0) {
    ctx.fillStyle = "#64748b";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No telemetry datapoints recorded yet", w / 2, h / 2);
    return;
  }

  // Calculate min and max
  let minY = 0;
  let maxY = Math.max(...points.map((p) => p.y || 0), 10);
  if (unit === "%") maxY = 100;

  // Draw grid lines
  ctx.strokeStyle = "rgba(100, 116, 139, 0.2)";
  ctx.lineWidth = 1;
  const gridSteps = 4;
  ctx.font = "10px monospace";
  ctx.fillStyle = "#64748b";
  ctx.textAlign = "right";

  for (let i = 0; i <= gridSteps; i++) {
    const val = minY + ((maxY - minY) * i) / gridSteps;
    const y = padding.top + chartH - (chartH * i) / gridSteps;

    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + chartW, y);
    ctx.stroke();

    ctx.fillText(`${Math.round(val)}${unit || ""}`, padding.left - 8, y + 3);
  }

  // Compute point coordinates
  const coords = points.map((p, idx) => {
    const x = padding.left + (chartW * idx) / Math.max(points.length - 1, 1);
    const clampedY = Math.max(minY, Math.min(maxY, p.y || 0));
    const y = padding.top + chartH - ((clampedY - minY) / (maxY - minY)) * chartH;
    return { x, y };
  });

  // Draw area fill
  ctx.beginPath();
  ctx.moveTo(coords[0].x, padding.top + chartH);
  coords.forEach((c) => ctx.lineTo(c.x, c.y));
  ctx.lineTo(coords[coords.length - 1].x, padding.top + chartH);
  ctx.closePath();

  const strokeColor = color || "#3b82f6";
  ctx.fillStyle = strokeColor.replace("rgb", "rgba").replace(")", ", 0.15)");
  ctx.fill();

  // Draw stroke line
  ctx.beginPath();
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 2;
  coords.forEach((c, idx) => {
    if (idx === 0) ctx.moveTo(c.x, c.y);
    else ctx.lineTo(c.x, c.y);
  });
  ctx.stroke();

  // Draw end point highlight
  const last = coords[coords.length - 1];
  ctx.beginPath();
  ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
  ctx.fillStyle = strokeColor;
  ctx.fill();
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

// 3. Auto-refresh polling (every 5 seconds)
function setupAutoRefresh(intervalMs = 5000) {
  setInterval(() => {
    const shouldRefresh = document.body.getAttribute("data-auto-refresh") !== "false";
    if (shouldRefresh && !document.hidden) {
      window.location.reload();
    }
  }, intervalMs);
}

// 4. Incident Approvals and State Updates
async function approveIncidentStep(incidentId) {
  if (!confirm("Are you sure you want to approve and execute this remediation step?")) {
    return;
  }
  try {
    const res = await fetch(`/api/v1/incidents/${incidentId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (res.ok) {
      window.location.reload();
    } else {
      const err = await res.json();
      alert(`Approval failed: ${err.detail || "Unknown error"}`);
    }
  } catch (e) {
    alert(`Error sending approval: ${e.message}`);
  }
}

async function closeIncident(incidentId) {
  const note = prompt("Enter resolution closure note:", "Resolved per standard operations verification.");
  if (note === null) return;

  try {
    const res = await fetch(`/api/v1/incidents/${incidentId}/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ summary: note }),
    });
    if (res.ok) {
      window.location.reload();
    } else {
      const err = await res.json();
      alert(`Close failed: ${err.detail || "Unknown error"}`);
    }
  } catch (e) {
    alert(`Error closing incident: ${e.message}`);
  }
}

// 5. Simulator Triggers
async function triggerSimulator(simName, mode = "auto") {
  const btn = document.getElementById(`sim-btn-${simName}`);
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`/simulate/run?name=${simName}&mode=${mode}`, {
      method: "POST",
    });
    const data = await res.json();
    if (res.ok) {
      alert(`Simulation started: ${data.message || simName}. Watch incidents tab for detection.`);
      setTimeout(() => {
        window.location.href = "/incidents";
      }, 1000);
    } else {
      alert(`Failed to trigger simulation: ${data.detail || "Error"}`);
      if (btn) btn.disabled = false;
    }
  } catch (e) {
    alert(`Error triggering simulator: ${e.message}`);
    if (btn) btn.disabled = false;
  }
}

async function stopSimulation(simName) {
  try {
    const res = await fetch(`/simulate/stop?name=${simName}`, {
      method: "POST",
    });
    const data = await res.json();
    alert(data.message || "Simulation stopped.");
    window.location.reload();
  } catch (e) {
    alert(`Error stopping simulator: ${e.message}`);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
});
