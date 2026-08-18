// This talks to our FastAPI backend running on the same server.
const isDevServer =
  window.location.port !== "8000" && window.location.protocol !== "file:";

const API_BASE =
  window.location.protocol === "file:"
    ? "http://localhost:8000"
    : isDevServer
    ? `${window.location.protocol}//${window.location.hostname || "localhost"}:8000`
    : "";

// ---- Tab switching ----
const tabButtons = document.querySelectorAll(".tab-btn");
const panels = document.querySelectorAll(".tab-panel");

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabButtons.forEach((b) => b.classList.remove("active"));
    panels.forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const targetPanel = document.getElementById(btn.dataset.tab);
    if (targetPanel) {
      targetPanel.classList.add("active");
    }
    if (btn.dataset.tab === "calendar") {
      loadBookings();
    }
  });
});

// ---- Calendar tab ----
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatAppointmentTime(timeStr) {
  if (!timeStr) return "";
  const isoStr = String(timeStr).replace(" ", "T");
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return String(timeStr);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function parseAppointmentDate(timeStr) {
  if (!timeStr) return null;
  const d = new Date(String(timeStr).replace(" ", "T"));
  return isNaN(d.getTime()) ? null : d;
}

function formatTimeOnly(timeStr) {
  const d = parseAppointmentDate(timeStr);
  if (!d) return String(timeStr || "");
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function getInitials(name) {
  if (!name) return "?";
  const parts = String(name).trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

const AVATAR_COLORS = [
  { bg: "rgba(108, 110, 245, 0.22)", text: "#A5A6F6" },
  { bg: "rgba(46, 196, 120, 0.22)", text: "#4ADE80" },
  { bg: "rgba(245, 166, 35, 0.22)", text: "#F0A93A" },
  { bg: "rgba(236, 120, 180, 0.22)", text: "#F0A0C8" },
  { bg: "rgba(80, 180, 220, 0.22)", text: "#7DD3FC" },
];

function hashName(name) {
  let hash = 0;
  const str = String(name || "");
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function getAvatarColor(name) {
  return AVATAR_COLORS[hashName(name) % AVATAR_COLORS.length];
}

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning, here's today";
  if (hour < 17) return "Good afternoon, here's today";
  return "Good evening, here's today";
}

function getStatusPillClass(status) {
  const s = (status || "confirmed").toLowerCase();
  if (s === "cancelled") return "cancelled";
  if (s === "pending") return "pending";
  if (s === "confirmed") return "confirmed";
  return "info";
}

function toggleRowMenu(btn) {
  const menu = btn.nextElementSibling;
  if (!menu) return;
  const isOpen = menu.classList.contains("open");
  document.querySelectorAll(".row-menu-dropdown.open").forEach((el) => el.classList.remove("open"));
  if (!isOpen) menu.classList.add("open");
}
window.toggleRowMenu = toggleRowMenu;

document.addEventListener("click", (e) => {
  if (!e.target.closest(".row-menu")) {
    document.querySelectorAll(".row-menu-dropdown.open").forEach((el) => el.classList.remove("open"));
  }
});

async function loadBookings() {
  const container = document.getElementById("bookings-container");
  if (!container) return;

  const statToday = document.getElementById("stat-today");
  const statSource = document.getElementById("stat-source");
  const statWeek = document.getElementById("stat-week");
  const greetingText = document.querySelector(".greeting-text");
  const greetingCount = document.getElementById("greeting-count");

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000);

    const res = await fetch(`${API_BASE}/api/bookings`, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!res.ok) {
      throw new Error(`Server returned status ${res.status}`);
    }
    const bookings = await res.json();

    if (!Array.isArray(bookings)) {
      throw new Error("Invalid bookings data received from server");
    }

    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const weekEnd = new Date(todayStart);
    weekEnd.setDate(weekEnd.getDate() + 7);

    const activeBookings = bookings.filter(
      (b) => (b && b.status || "").toLowerCase() !== "cancelled"
    );

    const todayBookings = activeBookings.filter((b) => {
      const d = parseAppointmentDate(b.appointment_time);
      return d && isSameDay(d, now);
    });

    const weekBookings = activeBookings.filter((b) => {
      const d = parseAppointmentDate(b.appointment_time);
      return d && d >= todayStart && d < weekEnd;
    });

    const aiBooked = activeBookings.filter(
      (b) => b.source && b.source !== "dashboard"
    ).length;
    const manualBooked = activeBookings.filter(
      (b) => b.source === "dashboard"
    ).length;

    if (statToday) statToday.textContent = String(todayBookings.length);
    if (statSource) {
      statSource.innerHTML = `${aiBooked}<span class="stat-sub"> AI</span> / ${manualBooked}<span class="stat-sub"> manual</span>`;
    }
    if (statWeek) statWeek.textContent = String(weekBookings.length);

    if (greetingText) greetingText.textContent = getGreeting();
    if (greetingCount) {
      const count = todayBookings.length;
      greetingCount.textContent =
        count === 1
          ? "1 appointment scheduled"
          : `${count} appointments scheduled`;
    }

    const sortByTime = (a, b) => {
      const timeA = parseAppointmentDate(a.appointment_time)?.getTime() || 0;
      const timeB = parseAppointmentDate(b.appointment_time)?.getTime() || 0;
      return timeA - timeB;
    };
    todayBookings.sort(sortByTime);

    function renderScheduleRow(b) {
      const name = b.customer_name || "Unknown Customer";
      const isCancelled = (b.status || "").toLowerCase() === "cancelled";
      const statusText = b.status || "confirmed";
      const avatar = getAvatarColor(name);
      const initials = getInitials(name);
      const pillClass = getStatusPillClass(statusText);

      return `
        <div class="schedule-row">
          <span class="schedule-time">${escapeHtml(formatTimeOnly(b.appointment_time))}</span>
          <div class="schedule-customer">
            <span class="avatar" style="background:${avatar.bg};color:${avatar.text}">${escapeHtml(initials)}</span>
            <span class="customer-name">${escapeHtml(name)}</span>
          </div>
          <span class="schedule-service">${escapeHtml(b.service || "Service")}</span>
          <span class="status-pill ${pillClass}">${escapeHtml(statusText)}</span>
          <div class="row-menu">
            <button class="row-menu-btn" type="button" aria-label="Actions" onclick="toggleRowMenu(this)">···</button>
            <div class="row-menu-dropdown">
              <button class="row-menu-item danger" type="button" ${isCancelled ? "disabled" : ""} onclick="cancelBooking(${b.id})">Cancel booking</button>
            </div>
          </div>
        </div>
      `;
    }

    if (todayBookings.length > 0) {
      container.innerHTML = todayBookings.map(renderScheduleRow).join("");
    } else {
      container.innerHTML = `<p class="schedule-empty">No appointments scheduled for today</p>`;
    }
  } catch (err) {
    console.error("Failed to load bookings:", err);
    const errMsg = err && err.message ? err.message : String(err);
    if (statToday) statToday.textContent = "—";
    if (statSource) statSource.textContent = "—";
    if (statWeek) statWeek.textContent = "—";
    if (greetingCount) greetingCount.textContent = "Unable to load";
    container.innerHTML = `<p class="schedule-empty">Unable to load bookings (${escapeHtml(errMsg)}). Click Refresh to try again.</p>`;
  }
}

async function cancelBooking(id) {
  try {
    await fetch(`${API_BASE}/api/bookings/${id}`, { method: "DELETE" });
  } catch (err) {
    console.error("Failed to cancel booking:", err);
  }
  loadBookings();
}
window.cancelBooking = cancelBooking;

const refreshBtn = document.getElementById("refresh-bookings");
if (refreshBtn) {
  refreshBtn.addEventListener("click", loadBookings);
}

// ---- Your AI tab ----
async function loadPersona() {
  try {
    const res = await fetch(`${API_BASE}/api/persona`);
    if (!res.ok) return;
    const persona = await res.json();
    const busEl = document.getElementById("persona-business");
    const toneEl = document.getElementById("persona-tone");
    const promptEl = document.getElementById("persona-prompt");
    if (busEl) busEl.value = persona.business_name || "";
    if (toneEl) toneEl.value = persona.tone || "";
    if (promptEl) promptEl.value = persona.system_prompt || "";
  } catch (err) {
    console.error("Failed to load persona:", err);
  }
}

const savePersonaBtn = document.getElementById("save-persona");
if (savePersonaBtn) {
  savePersonaBtn.addEventListener("click", async () => {
    const body = {
      business_name: document.getElementById("persona-business")?.value || "",
      tone: document.getElementById("persona-tone")?.value || "",
      system_prompt: document.getElementById("persona-prompt")?.value || "",
    };
    try {
      await fetch(`${API_BASE}/api/persona`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const status = document.getElementById("persona-status");
      if (status) {
        status.textContent = "Saved ✓";
        setTimeout(() => (status.textContent = ""), 2000);
      }
    } catch (err) {
      console.error("Failed to save persona:", err);
    }
  });
}

// ---- Test Chat tab ----
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");

function addChatMessage(text, sender) {
  if (!chatMessages) return;
  const messageEl = document.createElement("div");
  messageEl.className = `message ${sender}`;
  messageEl.textContent = text;
  chatMessages.appendChild(messageEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

if (chatForm && chatInput && chatMessages) {
  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = chatInput.value.trim();
    if (!message) return;

    addChatMessage(message, "customer");
    chatInput.value = "";

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!res.ok) throw new Error(`Chat request failed: ${res.status}`);

      const data = await res.json();
      addChatMessage(data.reply || "AI backend not connected yet", "ai");
      // Reload bookings in case chat created or modified a booking
      loadBookings();
    } catch (error) {
      addChatMessage("AI backend not connected yet", "ai");
    }
  });
}

// ---- Settings tab ----
async function loadBusinessHours() {
  try {
    const res = await fetch(`${API_BASE}/api/persona`);
    if (!res.ok) return;
    const persona = await res.json();
    const input = document.getElementById("business-hours");
    if (input) {
      input.value = persona.business_hours || "";
    }
  } catch (err) {
    console.error("Failed to load business hours:", err);
  }
}

const saveHoursBtn = document.getElementById("save-hours");
if (saveHoursBtn) {
  saveHoursBtn.addEventListener("click", async () => {
    const body = {
      business_name: document.getElementById("persona-business")?.value || "",
      tone: document.getElementById("persona-tone")?.value || "",
      system_prompt: document.getElementById("persona-prompt")?.value || "",
      business_hours: document.getElementById("business-hours")?.value || "",
    };

    try {
      await fetch(`${API_BASE}/api/persona`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const status = document.getElementById("hours-status");
      if (status) {
        status.textContent = "Saved ✓";
        setTimeout(() => (status.textContent = ""), 2000);
      }
    } catch (err) {
      console.error("Failed to save hours:", err);
    }
  });
}

async function loadServices() {
  try {
    const res = await fetch(`${API_BASE}/api/services`);
    if (!res.ok) return;
    const services = await res.json();
    const tbody = document.querySelector("#services-table tbody");
    if (!tbody || !Array.isArray(services)) return;

    tbody.innerHTML = "";
    services.forEach((service) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${escapeHtml(service.name)}</td>
        <td>$${Number(service.price).toFixed(2)}</td>
        <td>${Number(service.duration_minutes)} min</td>
        <td><button onclick="deleteService(${service.id})">Delete</button></td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    console.error("Failed to load services:", err);
  }
}

async function addService() {
  const nameEl = document.getElementById("service-name");
  const priceEl = document.getElementById("service-price");
  const durationEl = document.getElementById("service-duration");
  if (!nameEl || !priceEl || !durationEl) return;

  const name = nameEl.value.trim();
  const price = priceEl.value;
  const duration = durationEl.value;

  if (!name || !price || !duration) return;

  try {
    await fetch(`${API_BASE}/api/services`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        price: parseFloat(price),
        duration_minutes: parseInt(duration, 10),
      }),
    });

    nameEl.value = "";
    priceEl.value = "";
    durationEl.value = "";
    loadServices();
  } catch (err) {
    console.error("Failed to add service:", err);
  }
}

async function deleteService(id) {
  try {
    await fetch(`${API_BASE}/api/services/${id}`, { method: "DELETE" });
  } catch (err) {
    console.error("Failed to delete service:", err);
  }
  loadServices();
}
window.deleteService = deleteService;

const addServiceBtn = document.getElementById("add-service");
if (addServiceBtn) {
  addServiceBtn.addEventListener("click", addService);
}

// ---- Clients tab ----
async function loadClients() {
  try {
    const res = await fetch(`${API_BASE}/api/clients`);
    if (!res.ok) return;
    const clients = await res.json();
    const tbody = document.querySelector("#clients-table tbody");
    if (!tbody || !Array.isArray(clients)) return;

    tbody.innerHTML = "";
    clients.forEach((client) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${escapeHtml(client.name)}</td>
        <td>${escapeHtml(client.phone || "")}</td>
        <td>${escapeHtml(client.email || "")}</td>
        <td>${escapeHtml(client.notes || "")}</td>
        <td>
          <button onclick="editClient(${client.id})">Edit</button>
          <button onclick="deleteClient(${client.id})">Delete</button>
        </td>
      `;
      tbody.appendChild(row);
    });
  } catch (err) {
    console.error("Failed to load clients:", err);
  }
}

async function addClient() {
  const nameEl = document.getElementById("client-name");
  const phoneEl = document.getElementById("client-phone");
  const emailEl = document.getElementById("client-email");
  const notesEl = document.getElementById("client-notes");
  if (!nameEl || !phoneEl) return;

  const name = nameEl.value.trim();
  const phone = phoneEl.value.trim();
  const email = emailEl ? emailEl.value.trim() : "";
  const notes = notesEl ? notesEl.value.trim() : "";

  if (!name || !phone) return;

  try {
    await fetch(`${API_BASE}/api/clients`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, phone, email: email || null, notes: notes || null }),
    });

    nameEl.value = "";
    phoneEl.value = "";
    if (emailEl) emailEl.value = "";
    if (notesEl) notesEl.value = "";
    loadClients();
  } catch (err) {
    console.error("Failed to add client:", err);
  }
}

async function deleteClient(id) {
  try {
    await fetch(`${API_BASE}/api/clients/${id}`, { method: "DELETE" });
  } catch (err) {
    console.error("Failed to delete client:", err);
  }
  loadClients();
}
window.deleteClient = deleteClient;

function editClient(id) {
  const currentPhone = prompt("Update phone number:");
  if (currentPhone === null) return;

  const currentEmail = prompt("Update email (leave blank to clear):");
  if (currentEmail === null) return;

  const currentNotes = prompt("Update notes:");
  if (currentNotes === null) return;

  fetch(`${API_BASE}/api/clients/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      phone: currentPhone.trim() || null,
      email: currentEmail.trim() || null,
      notes: currentNotes.trim() || null,
    }),
  })
    .then(() => loadClients())
    .catch((err) => console.error("Failed to edit client:", err));
}
window.editClient = editClient;

// ---- Initial load ----
loadBookings();
loadPersona();
loadBusinessHours();
loadServices();
loadClients();
