const state = {
  user: null,
  token: localStorage.getItem("token") || null,
  devices: [],
  types: [],
  rooms: [],
  records: [],
  users: [],
  faces: [],
  lastDetection: null,
  selectedImage: null,
  filters: {
    type: "",
    room: "",
  },
};

const API_BASE_URL = window.API_BASE_URL || `${window.location.origin.replace(/:\d+$/, '')}:5000`;

const demoDevices = [
  { device_name: "客厅主灯", device_type: "light", room: "客厅", status: "on" },
  { device_name: "卧室空调", device_type: "aircon", room: "卧室", status: "off" },
  { device_name: "入口门禁", device_type: "door", room: "玄关", status: "off" },
];

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const body = options.body;

  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (state.token && !options.noAuth) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }

  const url = path.startsWith("http") ? path : `${API_BASE_URL}${path}`;

  const response = await fetch(url, {
    ...options,
    headers,
  });

  let payload = {};
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      payload = { success: false, message: text };
    }
  }

  if (!response.ok || payload.success === false) {
    if (response.status === 401) {
      clearSession();
      renderAuth();
    }
    throw new Error(payload.message || "请求失败");
  }

  return payload;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.add("hidden"), 2800);
}

function clearSession() {
  state.user = null;
  state.token = null;
  state.devices = [];
  state.types = [];
  state.rooms = [];
  state.records = [];
  state.users = [];
  state.lastDetection = null;
  localStorage.removeItem("token");
}

function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = label || "处理中...";
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

function renderAuth() {
  $("#auth-view").classList.remove("hidden");
  $("#dashboard-view").classList.add("hidden");
}

function renderDashboardShell() {
  $("#auth-view").classList.add("hidden");
  $("#dashboard-view").classList.remove("hidden");
  const roleText = state.user.role === "admin" ? "管理员" : "普通用户";
  $("#current-user").textContent = `${state.user.name || state.user.username} (${state.user.username}) [${roleText}]`;
  $("#admin-panel").classList.toggle("hidden", state.user.role !== "admin");
}

async function boot() {
  bindEvents();
  try {
    const payload = await api("/");
    if (payload.status === "logged_in") {
      state.user = {
        id: payload.user_id,
        username: payload.username,
        name: payload.username,
        role: payload.role || 'user',
      };
      renderDashboardShell();
      await loadDashboard();
    } else {
      renderAuth();
    }
  } catch (error) {
    renderAuth();
  }
}

function bindEvents() {
  document.querySelectorAll("[data-auth-tab]").forEach((button) => {
    button.addEventListener("click", () => switchAuthTab(button.dataset.authTab));
  });

  $("#login-form").addEventListener("submit", handleLogin);
  $("#register-form").addEventListener("submit", handleRegister);
  $("#logout-btn").addEventListener("click", handleLogout);
  $("#refresh-btn").addEventListener("click", () => loadDashboard(true));

  $("#type-filter").addEventListener("change", (event) => {
    state.filters.type = event.target.value;
    loadDevices();
  });
  $("#room-filter").addEventListener("change", (event) => {
    state.filters.room = event.target.value;
    loadDevices();
  });

  $("#new-device-btn").addEventListener("click", () => openDeviceDialog());
  $("#cancel-device-btn").addEventListener("click", () => $("#device-dialog").close());
  $("#device-form").addEventListener("submit", handleDeviceSave);
  $("#seed-devices-btn").addEventListener("click", seedDemoDevices);

  $("#detect-form").addEventListener("submit", handleDetect);
    
    $("#mode-camera").addEventListener("click", () => switchDetectionMode("camera"));
    $("#mode-upload").addEventListener("click", () => switchDetectionMode("upload"));
    $("#upload-image").addEventListener("change", handleUploadImageChange);
    $("#upload-form").addEventListener("submit", handleUploadAnalyze);

    $("#new-face-btn").addEventListener("click", () => openFaceDialog());
    $("#cancel-face-btn").addEventListener("click", () => $("#face-dialog").close());
    $("#face-form").addEventListener("submit", handleFaceSave);
    $("#face-form [name='image_data']").addEventListener("change", handleFaceImageChange);
}

function switchAuthTab(tab) {
  document.querySelectorAll("[data-auth-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.authTab === tab);
  });
  $("#login-form").classList.toggle("hidden", tab !== "login");
  $("#register-form").classList.toggle("hidden", tab !== "register");
}

async function handleLogin(event) {
  event.preventDefault();
  const button = event.submitter;
  setBusy(button, true, "登录中...");
  const form = new FormData(event.currentTarget);

  try {
    const payload = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username").trim(),
        password: form.get("password"),
      }),
      noAuth: true,
    });
    state.user = payload.user;
    state.token = payload.token;
    localStorage.setItem("token", payload.token);
    showToast("登录成功");
    renderDashboardShell();
    await loadDashboard();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const button = event.submitter;
  setBusy(button, true, "注册中...");
  const form = new FormData(event.currentTarget);

  try {
    await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: form.get("username").trim(),
        name: form.get("name").trim(),
        password: form.get("password"),
        password2: form.get("password2"),
      }),
    });
    showToast("注册成功，请登录");
    event.currentTarget.reset();
    switchAuthTab("login");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function handleLogout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (error) {
    // Logging out should return the user to the auth screen even if the session has expired.
  }
  clearSession();
  renderAuth();
  showToast("已退出登录");
}

async function loadDashboard(showSuccess = false) {
  if (!state.user) return;
  renderDashboardShell();
  try {
    await Promise.all([loadDevices(), loadRecords(), loadUsersIfAdmin(), loadFaces()]);
    renderOverview();
    renderAnalytics();
    renderDeviceOptions();
    startVideoFeed();
    if (showSuccess) showToast("数据已刷新");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadDevices() {
  const params = new URLSearchParams();
  if (state.filters.type) params.set("type", state.filters.type);
  if (state.filters.room) params.set("room", state.filters.room);
  const suffix = params.toString() ? `?${params}` : "";

  const [devicesPayload, typesPayload, roomsPayload] = await Promise.all([
    api(`/api/device/devices${suffix}`),
    api("/api/device/devices/types"),
    api("/api/device/devices/rooms"),
  ]);

  state.devices = devicesPayload.devices || [];
  state.types = typesPayload.types || [];
  state.rooms = roomsPayload.rooms || [];
  renderFilters();
  renderDevices();
}

async function loadRecords() {
  const payload = await api("/api/yolo/access/records");
  state.records = payload.records || [];
  renderRecords();
}

async function loadUsersIfAdmin() {
  if (state.user.role !== "admin") {
    state.users = [];
    renderUsers();
    return;
  }
  const payload = await api("/api/auth/users");
  state.users = payload.users || [];
  renderUsers();
}

function renderFilters() {
  renderOptions("#type-filter", state.types, "全部类型", state.filters.type);
  renderOptions("#room-filter", state.rooms, "全部房间", state.filters.room);
}

function renderOptions(selector, values, placeholder, selectedValue = "") {
  const select = $(selector);
  select.innerHTML = `<option value="">${placeholder}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labelFor(value);
    option.selected = value === selectedValue;
    select.appendChild(option);
  });
}

function labelFor(value) {
  const labels = {
    light: "灯光",
    aircon: "空调/风扇",
    door: "门禁",
    access_control: "门禁",
    on: "开启",
    off: "关闭",
  };
  return labels[value] || value || "未设置";
}

function renderOverview() {
  const total = state.devices.length;
  const online = state.devices.filter((device) => device.status === "on").length;
  const doors = state.devices.filter((device) => device.device_type === "door").length;
  const latest = state.records[0]?.detected_object || state.lastDetection?.detected_object || "暂无";
  const statItems = [
    ["设备总数", total],
    ["开启设备", online],
    ["门禁设备", doors],
    ["最近识别", latest],
  ];

  $("#overview-stats").innerHTML = statItems.map(([label, value]) => `
    <article class="stat-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </article>
  `).join("");

  $("#hero-summary").textContent = total
    ? `当前系统接入 ${total} 个设备，其中 ${online} 个处于开启状态，已记录 ${state.records.length} 条门禁访问数据。`
    : "当前还没有设备数据，可以先初始化演示设备，再进行控制和统计演示。";

  $("#seed-devices-btn").classList.toggle("hidden", total > 0);
}

function renderDevices() {
  const list = $("#device-list");
  if (!state.devices.length) {
    list.innerHTML = `<div class="empty">暂无设备。可以新增设备，或点击“初始化演示设备”。</div>`;
    renderOverview();
    renderAnalytics();
    renderDeviceOptions();
    return;
  }

  list.innerHTML = state.devices.map((device) => `
    <article class="device-card ${device.status === "on" ? "on" : ""}">
      <span class="badge ${device.status === "on" ? "" : "off"}">${labelFor(device.status)}</span>
      <h3>${escapeHtml(device.device_name)}</h3>
      <div class="device-meta">
        <span>${escapeHtml(labelFor(device.device_type))}</span>
        <span>${escapeHtml(device.room || "未分配房间")}</span>
      </div>
      <div class="device-actions">
        <button class="primary-btn" type="button" data-action="toggle" data-id="${device.id}">
          ${device.status === "on" ? "关闭" : "开启"}
        </button>
        <button class="ghost-btn" type="button" data-action="edit" data-id="${device.id}">编辑</button>
        <button class="danger-btn" type="button" data-action="delete" data-id="${device.id}">删除</button>
      </div>
    </article>
  `).join("");

  list.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", handleDeviceAction);
  });
  renderOverview();
  renderAnalytics();
  renderDeviceOptions();
}

async function handleDeviceAction(event) {
  const button = event.currentTarget;
  const id = Number(button.dataset.id);
  const device = state.devices.find((item) => item.id === id);
  if (!device) return;

  if (button.dataset.action === "edit") {
    openDeviceDialog(device);
    return;
  }

  if (button.dataset.action === "delete") {
    if (!window.confirm(`确定删除设备“${device.device_name}”？`)) return;
    try {
      await api(`/api/device/devices/${id}`, { method: "DELETE" });
      showToast("设备已删除");
      await loadDashboard();
    } catch (error) {
      showToast(error.message, true);
    }
    return;
  }

  try {
    setBusy(button, true, "切换中...");
    await api(`/api/device/devices/${id}/toggle`, { method: "POST" });
    showToast(`${device.device_name} 状态已切换`);
    await loadDashboard();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function openDeviceDialog(device = null) {
  const dialog = $("#device-dialog");
  const form = $("#device-form");
  form.reset();
  $("#device-dialog-title").textContent = device ? "编辑设备" : "新增设备";
  form.elements.id.value = device?.id || "";
  form.elements.device_name.value = device?.device_name || "";
  form.elements.device_type.value = device?.device_type || "light";
  form.elements.room.value = device?.room || "";
  form.elements.status.value = device?.status || "off";
  dialog.showModal();
}

async function handleDeviceSave(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  const payload = {
    device_name: form.elements.device_name.value.trim(),
    device_type: form.elements.device_type.value,
    room: form.elements.room.value.trim(),
    status: form.elements.status.value,
  };

  try {
    if (id) {
      await api(`/api/device/devices/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("设备已更新");
    } else {
      await api("/api/device/devices", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("设备已创建");
    }
    $("#device-dialog").close();
    await loadDashboard();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadFaces() {
  try {
    const payload = await api("/api/yolo/face/list");
    state.faces = payload.faces || [];
    renderFaces();
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderFaces() {
  const list = $("#face-list");
  if (!state.faces.length) {
    list.innerHTML = `<div class="empty">暂无注册人脸。点击“注册人脸”添加。</div>`;
    return;
  }

  list.innerHTML = state.faces.map((face) => `
    <article class="face-card">
      <span class="badge">ID ${face.id}</span>
      <h4>${escapeHtml(face.name || face.feature_name || "未知")}</h4>
      <p>${escapeHtml(face.username || "")}</p>
      <p>${escapeHtml(face.created_at || "")}</p>
      <div class="row-actions" style="margin-top: 8px;">
        <button class="danger-btn" type="button" data-face-action="delete" data-user-id="${face.user_id}">删除</button>
      </div>
    </article>
  `).join("");

  list.querySelectorAll("[data-face-action]").forEach((button) => {
    button.addEventListener("click", handleFaceAction);
  });
}

function openFaceDialog() {
  const dialog = $("#face-dialog");
  const form = $("#face-form");
  form.reset();
  $("#face-preview").src = "";
  $("#face-dialog-title").textContent = "注册人脸";
  renderFaceUserOptions();
  dialog.showModal();
}

function renderFaceUserOptions() {
  const select = $("#face-user-select");
  select.innerHTML = "";
  if (!state.users.length) {
    select.innerHTML = `<option value="">暂无用户</option>`;
    return;
  }
  state.users.forEach((user) => {
    const option = document.createElement("option");
    option.value = user.id;
    option.textContent = `${user.name || user.username} (${user.username})`;
    select.appendChild(option);
  });
}

function handleFaceImageChange(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    $("#face-preview").src = e.target.result;
  };
  reader.readAsDataURL(file);
}

async function handleFaceSave(event) {
  event.preventDefault();
  const button = event.submitter;
  const form = event.currentTarget;
  const userId = Number($("#face-user-select").value);
  const fileInput = form.elements.image_data;

  if (!userId || !fileInput.files[0]) {
    showToast("请选择用户和人脸图片", true);
    return;
  }

  try {
    setBusy(button, true, "注册中...");
    const file = fileInput.files[0];
    const reader = new FileReader();

    await new Promise((resolve, reject) => {
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

    const imageData = reader.result;

    await api("/api/yolo/face/register", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        image_data: imageData,
        feature_name: "face",
      }),
    });

    showToast("人脸注册成功");
    $("#face-dialog").close();
    await loadFaces();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function handleFaceAction(event) {
  const button = event.currentTarget;
  const userId = Number(button.dataset.userId);

  if (!window.confirm("确定删除该人脸特征？")) return;

  try {
    await api(`/api/yolo/face/delete/${userId}`, { method: "DELETE" });
    showToast("人脸特征已删除");
    await loadFaces();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function seedDemoDevices() {
  const button = $("#seed-devices-btn");
  setBusy(button, true, "初始化中...");
  try {
    for (const device of demoDevices) {
      await api("/api/device/devices", {
        method: "POST",
        body: JSON.stringify(device),
      });
    }
    showToast("演示设备已创建");
    await loadDashboard();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function renderDeviceOptions() {
  const selects = [$("#detect-device"), $("#upload-device")];
  const doorDevices = state.devices.filter((device) => 
    device.device_type === "door" || device.device_type === "access_control"
  );
  const candidates = doorDevices.length ? doorDevices : state.devices;

  selects.forEach((select) => {
    if (!select) return;
    select.innerHTML = "";
    if (!candidates.length) {
      select.innerHTML = `<option value="">暂无设备</option>`;
      return;
    }
    candidates.forEach((device) => {
      const option = document.createElement("option");
      option.value = device.id;
      option.textContent = `${device.device_name} (${device.room || "未分配"})`;
      select.appendChild(option);
    });
  });
}

function startVideoFeed() {
  const videoFeed = $("#video-feed");
  if (!videoFeed) return;
  const token = state.token || localStorage.getItem("token");
  const url = token 
    ? `${API_BASE_URL}/api/yolo/video_feed?token=${encodeURIComponent(token)}`
    : `${API_BASE_URL}/api/yolo/video_feed`;
  videoFeed.src = url;
  videoFeed.onload = () => {
    $("#video-overlay").classList.add("hidden");
  };
  videoFeed.onerror = () => {
    showToast("无法连接摄像头，请检查后端服务", true);
  };
}

async function handleDetect(event) {
  event.preventDefault();
  const button = event.submitter;
  const form = new FormData(event.currentTarget);
  const deviceId = Number($("#detect-device").value);

  try {
    setBusy(button, true, "检测中...");
    const requestData = {
      user_id: state.user.id,
      device_id: deviceId,
      confidence: Number(form.get("confidence") || 0.5),
    };

    const payload = await api("/api/yolo/capture", {
      method: "POST",
      body: JSON.stringify(requestData),
    });

    state.selectedImage = payload.image_data;
    const capturedImage = $("#captured-image");
    capturedImage.innerHTML = `<img src="${payload.image_data}" alt="抓拍图片">`;
    capturedImage.classList.remove("hidden");

    state.lastDetection = {
      detected_object: payload.detected_object || payload.detection_result?.objects?.[0] || "未检测到物体",
      confidence: payload.confidence || payload.detection_result?.confidence_scores?.[0] || 0,
      message: payload.message,
      access_granted: payload.access_granted,
      safety_warning: payload.safety_warning,
    };

    renderLastDetection();
    renderOverview();
    await loadRecords();
    showToast("YOLO 检测完成");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function switchDetectionMode(mode) {
  $("#mode-camera").classList.toggle("active", mode === "camera");
  $("#mode-upload").classList.toggle("active", mode === "upload");
  $("#camera-mode").classList.toggle("hidden", mode !== "camera");
  $("#upload-mode").classList.toggle("hidden", mode !== "upload");
}

function handleUploadImageChange(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    const preview = $("#upload-preview");
    preview.src = e.target.result;
    preview.classList.remove("hidden");
    $("#upload-label").classList.add("hidden");
  };
  reader.readAsDataURL(file);
}

async function handleUploadAnalyze(event) {
  event.preventDefault();
  const button = event.submitter;
  const fileInput = $("#upload-image");
  
  if (!fileInput.files[0]) {
    showToast("请先选择图片", true);
    return;
  }

  const deviceId = Number($("#upload-device").value);
  const confidence = Number($("#upload-form [name='confidence']").value || 0.5);

  try {
    setBusy(button, true, "分析中...");
    
    const formData = new FormData();
    formData.append("image", fileInput.files[0]);
    formData.append("user_id", state.user.id);
    if (deviceId) formData.append("device_id", deviceId);
    formData.append("confidence", confidence);

    const payload = await api("/api/yolo/detect/image", {
      method: "POST",
      body: formData,
      headers: {},
    });

    state.selectedImage = payload.image_data;
    const capturedImage = $("#captured-image");
    capturedImage.innerHTML = `<img src="${payload.image_data}" alt="上传分析图片">`;
    capturedImage.classList.remove("hidden");

    state.lastDetection = {
      detected_object: payload.detected_object || payload.detection_result?.objects?.[0] || "未检测到物体",
      confidence: payload.confidence || payload.detection_result?.confidence_scores?.[0] || 0,
      message: payload.message,
      access_granted: payload.access_granted,
      safety_warning: payload.safety_warning,
      face_detected: payload.face_detected,
      identity: payload.identity,
      similarity: payload.similarity,
    };

    renderLastDetection();
    renderOverview();
    await loadRecords();
    showToast("图片分析完成");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}



function renderLastDetection() {
  const box = $("#last-detection");
  if (!state.lastDetection) {
    box.textContent = "暂无识别结果";
    return;
  }

  const accessStatus = state.lastDetection.access_granted 
    ? `<span class="status-granted">✓ 门禁已开启</span>` 
    : `<span class="status-denied">✗ 门禁关闭</span>`;
  
  const safetyWarning = state.lastDetection.safety_warning 
    ? `<p class="warning-text">⚠️ ${escapeHtml(state.lastDetection.safety_warning)}</p>` 
    : "";

  box.innerHTML = `
    <strong>${escapeHtml(state.lastDetection.message || "识别结果")}</strong>
    <p>${accessStatus}</p>
    <p>对象：${escapeHtml(state.lastDetection.detected_object || "未返回对象")}</p>
    <p>置信度：${escapeHtml(String(state.lastDetection.confidence ?? 0))}</p>
    ${safetyWarning}
  `;
}

function renderRecords() {
  const list = $("#record-list");
  if (!state.records.length) {
    list.innerHTML = `<div class="empty">暂无门禁访问记录。</div>`;
    return;
  }

  list.innerHTML = state.records.slice(0, 12).map((record) => `
    <article class="record-item">
      <span class="badge warning">#${record.id}</span>
      <div>
        <strong>${escapeHtml(record.detected_object || "未知对象")}</strong>
        <small>用户 ${escapeHtml(String(record.user_id || "-"))} / 设备 ${escapeHtml(String(record.device_id || "-"))} / ${escapeHtml(record.access_type || "-")}</small>
      </div>
      <small>${escapeHtml(record.created_at || "")}</small>
    </article>
  `).join("");
}

function renderAnalytics() {
  const analytics = $("#analytics");
  const byRoom = groupBy(state.devices, (device) => device.room || "未分配");
  const byType = groupBy(state.devices, (device) => labelFor(device.device_type));
  const byStatus = groupBy(state.devices, (device) => labelFor(device.status));
  const sensorValues = [24, 25, 27, 28, 31, 29, 26, 25];

  analytics.innerHTML = `
    ${renderBarChart("按房间统计", byRoom)}
    ${renderBarChart("按类型统计", byType)}
    ${renderBarChart("开关状态", byStatus)}
    <article class="chart-card">
      <h3>温度/亮度演示趋势</h3>
      <div class="sensor-line">
        ${sensorValues.map((value) => `<span style="height:${value * 2}px" title="${value}"></span>`).join("")}
      </div>
      <small>前端演示数据，等待硬件传感器接口接入。</small>
    </article>
  `;
}

function renderBarChart(title, data) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, value]) => value));

  if (!entries.length) {
    return `<article class="chart-card"><h3>${title}</h3><div class="empty">暂无数据</div></article>`;
  }

  return `
    <article class="chart-card">
      <h3>${title}</h3>
      ${entries.map(([label, value]) => `
        <div class="bar-row">
          <span>${escapeHtml(label)}</span>
          <div class="bar"><i style="width:${Math.max(8, (value / max) * 100)}%"></i></div>
          <b>${value}</b>
        </div>
      `).join("")}
    </article>
  `;
}

function groupBy(items, getKey) {
  return items.reduce((acc, item) => {
    const key = getKey(item);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function renderUsers() {
  const panel = $("#admin-panel");
  const list = $("#user-list");

  if (state.user?.role !== "admin") {
    panel.classList.add("hidden");
    list.innerHTML = "";
    return;
  }

  panel.classList.remove("hidden");
  if (!state.users.length) {
    list.innerHTML = `<div class="empty">暂无用户数据。</div>`;
    return;
  }

  list.innerHTML = state.users.map((user) => `
    <article class="table-row">
      <span class="badge">ID ${user.id}</span>
      <div>
        <strong>${escapeHtml(user.name)}</strong>
        <small>${escapeHtml(user.username)} / ${escapeHtml(user.created_at || "")}</small>
      </div>
      <span class="badge ${user.role === 'admin' ? 'warning' : ''}">${user.role === 'admin' ? '管理员' : '普通用户'}</span>
      <div class="row-actions">
        <button class="ghost-btn" type="button" data-user-action="rename" data-id="${user.id}">改名</button>
        <button class="primary-btn" type="button" data-user-action="role" data-id="${user.id}" data-role="${user.role}">${user.role === 'admin' ? '设为普通' : '设为管理员'}</button>
        <button class="danger-btn" type="button" data-user-action="delete" data-id="${user.id}">删除</button>
      </div>
    </article>
  `).join("");

  list.querySelectorAll("[data-user-action]").forEach((button) => {
    button.addEventListener("click", handleUserAction);
  });
}

async function handleUserAction(event) {
  const button = event.currentTarget;
  const id = Number(button.dataset.id);
  const user = state.users.find((item) => item.id === id);
  if (!user) return;

  try {
    if (button.dataset.userAction === "rename") {
      const name = window.prompt("请输入新的姓名", user.name);
      if (!name || name.trim() === user.name) return;
      await api(`/api/auth/users/${id}`, {
        method: "PUT",
        body: JSON.stringify({ name: name.trim() }),
      });
      showToast("用户信息已更新");
    } else if (button.dataset.userAction === "role") {
      const newRole = button.dataset.role === "admin" ? "user" : "admin";
      const roleText = newRole === "admin" ? "管理员" : "普通用户";
      if (!window.confirm(`确定将用户“${user.username}”设为${roleText}？`)) return;
      await api(`/api/auth/users/${id}`, {
        method: "PUT",
        body: JSON.stringify({ role: newRole }),
      });
      showToast(`用户已设为${roleText}`);
      if (id === state.user.id) {
        state.user.role = newRole;
        renderDashboardShell();
      }
    } else {
      if (!window.confirm(`确定删除用户“${user.username}”？`)) return;
      await api(`/api/auth/users/${id}`, { method: "DELETE" });
      showToast("用户已删除");
      if (id === state.user.id) {
        clearSession();
        renderAuth();
        return;
      }
    }
    await loadUsersIfAdmin();
  } catch (error) {
    showToast(error.message, true);
  }
}

function escapeHtml(value) {
  if (value == null) return "";
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

document.addEventListener("DOMContentLoaded", boot);
