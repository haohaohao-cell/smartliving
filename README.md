# 智能家居软件

一个前后端分离的智能家居系统。后端基于 Flask 提供设备管理与 AI 识别 API，前端为纯静态页面；内置 YOLO 目标检测与人脸识别模型，可本地运行。

项目已拆分为前后端两个目录：

- `backend/`: Flask 后端 API、数据库模型、路由和依赖
- `frontend/`: 静态 HTML/CSS/JavaScript 前端

## 启动后端

```powershell
cd backend
venv\Scripts\python.exe app.py
```

后端默认运行在 `http://localhost:5000`。

## 启动前端

```powershell
cd frontend
python -m http.server 8080
```

前端访问地址为 `http://localhost:8080`。

前端默认通过 `http://localhost:5000` 调用后端 API。如需修改地址，可以在加载 `js/app.js` 前设置 `window.API_BASE_URL`。
