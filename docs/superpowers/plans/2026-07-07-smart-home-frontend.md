# Smart Home Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask-served Web GUI for the smart home project that covers authentication, dashboard overview, device control, access recognition, statistics, and admin user management.

**Architecture:** Keep the existing Flask API and database models intact. Add a single-page GUI served from `/`, with static CSS and JavaScript calling existing `/api/...` endpoints using same-origin session cookies. Only modify backend routing enough to render the page and keep API behavior stable.

**Tech Stack:** Flask templates, vanilla HTML/CSS/JavaScript, Fetch API, existing Flask-SQLAlchemy backend, SQLite.

---

## File Structure

- Create `flaskproject/templates/index.html`: main single-page app shell and semantic UI regions.
- Create `flaskproject/static/css/app.css`: responsive control-console styling.
- Create `flaskproject/static/js/app.js`: API client, state management, rendering, form handlers.
- Modify `flaskproject/app.py`: import `render_template` and serve the frontend at `/`; expose JSON system status at `/api/status`.
- Keep existing API modules unchanged unless a runtime bug blocks frontend integration.

## Tasks

### Task 1: Prepare Backend Project

**Files:**
- Extract: `D:/电脑管家迁移文件/xwechat_files/wxid_7wci4raf781t22_dffc/temp/RWTemp/2026-07/9e20f478899dc29eb19741386f9343c8/flaskproject.zip`
- Target: `C:/Users/yu646/Desktop/智能家居软件/flaskproject`

- [ ] **Step 1: Extract the backend zip into the workspace**

Run:

```powershell
Expand-Archive -LiteralPath 'D:\电脑管家迁移文件\xwechat_files\wxid_7wci4raf781t22_dffc\temp\RWTemp\2026-07\9e20f478899dc29eb19741386f9343c8\flaskproject.zip' -DestinationPath 'C:\Users\yu646\Desktop\智能家居软件' -Force
```

Expected: `flaskproject/app.py`, `flaskproject/models.py`, and `flaskproject/routes` exist.

- [ ] **Step 2: Verify Python dependencies are available**

Run:

```powershell
flaskproject\venv\Scripts\python.exe -c "import flask, flask_sqlalchemy; print('ok')"
```

Expected: prints `ok`.

### Task 2: Serve The Frontend

**Files:**
- Modify: `flaskproject/app.py`
- Create: `flaskproject/templates/index.html`

- [ ] **Step 1: Add a minimal template**

Create `templates/index.html` with a valid HTML document containing a root element:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>智能家居控制中心</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
</head>
<body>
  <div id="app"></div>
  <script src="{{ url_for('static', filename='js/app.js') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Change `/` to render the GUI and add `/api/status`**

In `app.py`, import `render_template`:

```python
from flask import Flask, jsonify, session, render_template
```

Replace the body of `index()` with:

```python
return render_template('index.html')
```

Add a new route `@app.route('/api/status')` that returns the previous JSON login status payload.

- [ ] **Step 3: Verify Flask imports**

Run:

```powershell
flaskproject\venv\Scripts\python.exe -m py_compile flaskproject\app.py
```

Expected: command exits with code 0.

### Task 3: Build Static UI Skeleton

**Files:**
- Modify: `flaskproject/templates/index.html`
- Create: `flaskproject/static/css/app.css`
- Create: `flaskproject/static/js/app.js`

- [ ] **Step 1: Add semantic page regions**

Add markup for:

- `#auth-view` with login and register forms.
- `#dashboard-view` with header, overview cards, device panel, recognition panel, analytics panel, and admin panel.
- Modal/dialog containers for device editing.
- Toast container.

- [ ] **Step 2: Add base JavaScript state**

Create:

```javascript
const state = {
  user: null,
  devices: [],
  types: [],
  rooms: [],
  records: [],
  users: [],
  lastDetection: null,
};
```

Add an `api(path, options = {})` helper that sets `Content-Type: application/json`, uses `credentials: 'same-origin'`, parses JSON, and throws an error with `message` on failed responses.

- [ ] **Step 3: Add responsive styling**

Define a restrained console palette with light surfaces, green online accents, amber warning accents, and compact cards. Ensure layout adapts below 760px by stacking columns and keeping buttons readable.

### Task 4: Authentication Flow

**Files:**
- Modify: `flaskproject/static/js/app.js`

- [ ] **Step 1: Implement login/register/logout handlers**

Handlers:

- Login posts `{ username, password }` to `/api/auth/login`.
- Register posts `{ username, name, password, password2 }` to `/api/auth/register`.
- Logout posts to `/api/auth/logout`, clears state, renders auth view.

- [ ] **Step 2: Implement boot login-state check**

Call `/api/status` on startup. If `status === 'logged_in'`, set `state.user` from the status payload and load dashboard data; otherwise render auth view.

- [ ] **Step 3: Verify manually**

Run Flask and verify:

- Unauthenticated `/` shows login/register.
- Login switches to dashboard.
- Logout returns to auth view.

### Task 5: Device Control

**Files:**
- Modify: `flaskproject/static/js/app.js`

- [ ] **Step 1: Load devices, types, and rooms**

Fetch:

- `/api/device/devices`
- `/api/device/devices/types`
- `/api/device/devices/rooms`

If the devices list is empty, show a “初始化演示设备” button.

- [ ] **Step 2: Render device cards and filters**

Render each device with name, type label, room, status badge, toggle button, edit button, delete button. Filters should call `/api/device/devices?type=...&room=...`.

- [ ] **Step 3: Implement device create/update/delete/toggle**

Use existing endpoints:

- `POST /api/device/devices`
- `PUT /api/device/devices/<id>`
- `DELETE /api/device/devices/<id>`
- `POST /api/device/devices/<id>/toggle`

After each successful operation, reload dashboard data.

### Task 6: Recognition And Access Records

**Files:**
- Modify: `flaskproject/static/js/app.js`

- [ ] **Step 1: Implement image upload preview and Base64 conversion**

Use `FileReader.readAsDataURL(file)` and send `{ image_data, user_id, device_id }` to `/api/yolo/detect`.

- [ ] **Step 2: Implement access verification demo**

Submit `{ user_id, device_id, detected_object, confidence }` to `/api/yolo/access/verify`.

- [ ] **Step 3: Render access record timeline**

Fetch `/api/yolo/access/records`, sort by returned order, display record id, user id, device id, detected object, result, and created time.

### Task 7: Dashboard Analytics

**Files:**
- Modify: `flaskproject/static/js/app.js`
- Modify: `flaskproject/static/css/app.css`

- [ ] **Step 1: Compute overview stats**

Calculate:

- Total devices.
- Devices with `status === 'on'`.
- Number of access records.
- Most recent detected object or “暂无”.

- [ ] **Step 2: Render simple charts**

Use CSS bars, not a chart library:

- Device count by room.
- Device count by type.
- On/off ratio.

- [ ] **Step 3: Add sensor demo card**

Show “温度/亮度演示趋势” using deterministic front-end sample values and clearly label it as front-end demo data until hardware APIs are connected.

### Task 8: Admin User Management

**Files:**
- Modify: `flaskproject/static/js/app.js`

- [ ] **Step 1: Show admin panel only for username `admin`**

If `state.user.username !== 'admin'`, hide the user management section.

- [ ] **Step 2: Load and render users**

Fetch `/api/auth/users`, render id, username, name, created_at.

- [ ] **Step 3: Implement update/delete**

Use:

- `PUT /api/auth/users/<id>` with `{ name }`
- `DELETE /api/auth/users/<id>`

After changes, reload users and show a toast.

### Task 9: Verification

**Files:**
- All touched files.

- [ ] **Step 1: Compile backend**

Run:

```powershell
flaskproject\venv\Scripts\python.exe -m py_compile flaskproject\app.py flaskproject\models.py flaskproject\routes\auth.py flaskproject\routes\device.py flaskproject\routes\yolo.py flaskproject\utils.py
```

Expected: exit code 0.

- [ ] **Step 2: Start Flask**

Run:

```powershell
flaskproject\venv\Scripts\python.exe flaskproject\app.py
```

Expected: Flask serves on `http://127.0.0.1:5000`.

- [ ] **Step 3: Smoke test HTTP endpoints**

Use a browser or `Invoke-WebRequest` to verify `/` returns HTML and `/api/status` returns JSON.

- [ ] **Step 4: Manual UI flow**

Verify login/register, device create/toggle/edit/delete, access verify, records display, and admin users section.

## Self-Review

- Spec coverage: authentication, overview, device control, recognition, records, statistics, and admin management are covered.
- Scope: real YOLO, hardware sensor integration, and backend database expansion remain out of scope.
- Placeholder scan: no TODO/TBD placeholders are used.
- Commit note: the current workspace is not a git repository, so the usual commit checkpoints cannot be completed.
