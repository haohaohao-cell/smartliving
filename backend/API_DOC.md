# 智能家居系统后端 API 文档

## 项目简介

本项目是一个智能家居系统的后端服务，基于 Flask 框架开发，提供用户管理、人脸识别门禁和设备控制等功能的 RESTful API 接口。

**安全特性**：系统采用 Session 会话管理，人脸识别和设备控制接口需要登录后才能访问，登录一次即可访问所有功能。

## 技术栈

| 技术               | 版本    | 说明          |
| ---------------- | ----- | ----------- |
| Python           | 3.13+ | 编程语言        |
| Flask            | 3.1.x | Web 框架      |
| Flask-SQLAlchemy | 3.1.x | ORM 数据库操作   |
| SQLite           | -     | 默认数据库（轻量级）  |
| MySQL            | 8.0+  | 可选数据库（生产环境） |
| Werkzeug         | 3.1.x | 密码哈希处理      |

## 项目结构

```
flaskproject/
├── app.py                    # 主应用入口
├── models.py                 # 数据库模型定义
├── utils.py                  # 工具函数和登录验证装饰器
├── routes/
│   ├── auth.py               # 用户认证接口
│   ├── yolo.py               # YOLO人脸识别接口（需登录）
│   └── device.py             # 设备控制接口（需登录）
├── smart_home.db             # SQLite数据库文件
└── API_DOC.md                # API接口文档
```

## 数据库模型

### 用户模型 (User)

| 字段         | 类型          | 约束                         | 说明       |
| ---------- | ----------- | -------------------------- | -------- |
| id         | Integer     | PRIMARY KEY, AUTOINCREMENT | 用户ID     |
| username   | String(50)  | UNIQUE, NOT NULL           | 用户名      |
| password   | String(255) | NOT NULL                   | 密码（哈希存储） |
| name       | String(100) | NOT NULL                   | 用户姓名     |
| created_at | DateTime    | DEFAULT CURRENT_TIMESTAMP  | 创建时间     |

### 设备模型 (Device)

| 字段          | 类型          | 约束                         | 说明                      |
| ----------- | ----------- | -------------------------- | ----------------------- |
| id          | Integer     | PRIMARY KEY, AUTOINCREMENT | 设备ID                    |
| device_name | String(100) | NOT NULL                   | 设备名称                    |
| device_type | String(50)  | NOT NULL                   | 设备类型（light/aircon/door） |
| status      | String(20)  | DEFAULT 'off'              | 设备状态（on/off）            |
| room        | String(50)  | -                          | 设备所在房间                  |
| created_at  | DateTime    | DEFAULT CURRENT_TIMESTAMP  | 创建时间                    |

### 门禁访问记录模型 (AccessRecord)

| 字段              | 类型          | 约束                         | 说明                           |
| --------------- | ----------- | -------------------------- | ---------------------------- |
| id              | Integer     | PRIMARY KEY, AUTOINCREMENT | 记录ID                         |
| user_id         | Integer     | FOREIGN KEY                | 用户ID                         |
| device_id       | Integer     | FOREIGN KEY                | 设备ID                         |
| access_type     | String(50)  | -                          | 访问类型（face_recognition）       |
| result          | String(20)  | -                          | 访问结果（success/failed/pending） |
| detected_object | String(100) | -                          | 检测到的物体                       |
| created_at      | DateTime    | DEFAULT CURRENT_TIMESTAMP  | 创建时间                         |

## API 接口说明

### 基础地址

```
http://localhost:5000
```

### 认证说明

| 接口类型     | 认证要求 | 说明          |
| -------- | ---- | ----------- |
| 用户认证     | 无需登录 | 登录、注册等接口    |
| YOLO人脸识别 | 需登录  | 所有接口需要登录后访问 |
| 设备控制     | 需登录  | 所有接口需要登录后访问 |

**登录流程**：

1. 访问首页 `/` → 返回登录/注册接口
2. 调用登录接口 `/api/auth/login` → 设置 Session
3. 登录后即可访问所有功能接口
4. 调用登出接口 `/api/auth/logout` → 清除 Session

**未登录访问受保护接口响应**：

```json
{
    "success": false,
    "message": "未登录，请先登录",
    "redirect": "/api/auth/login"
}
```

---

## 1. 用户认证接口 (`/api/auth`)

### 1.1 用户登录

- **请求方法**: POST
- **请求URL**: `/api/auth/login`

**请求参数**:

| 参数       | 类型     | 必填  | 说明  |
| -------- | ------ | --- | --- |
| username | String | 是   | 用户名 |
| password | String | 是   | 密码  |

**请求示例**:

```json
{
    "username": "admin",
    "password": "123456"
}
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "登录成功",
    "user": {
        "id": 1,
        "username": "admin",
        "name": "管理员",
        "created_at": "2026-07-06 14:58:16"
    },
    "note": "已登录，可访问人脸识别和设备控制功能"
}
```

**失败响应**:

| 状态码 | 说明     |
| --- | ------ |
| 400 | 缺少必要参数 |
| 404 | 账号不存在  |
| 401 | 密码错误   |

---

### 1.2 用户登出

- **请求方法**: POST
- **请求URL**: `/api/auth/logout`

**说明**: 清除 Session，退出登录状态。

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "登出成功"
}
```

---

### 1.3 用户注册

- **请求方法**: POST
- **请求URL**: `/api/auth/register`

**请求参数**:

| 参数        | 类型     | 必填  | 说明       |
| --------- | ------ | --- | -------- |
| username  | String | 是   | 用户名      |
| password  | String | 是   | 密码（至少6位） |
| password2 | String | 是   | 确认密码     |
| name      | String | 是   | 用户姓名     |

**请求示例**:

```json
{
    "username": "admin",
    "password": "123456",
    "password2": "123456",
    "name": "管理员"
}
```

**成功响应** (201 Created):

```json
{
    "success": true,
    "message": "注册成功",
    "user": {
        "id": 1,
        "username": "admin",
        "name": "管理员",
        "created_at": "2026-07-06 14:58:16"
    },
    "note": "注册成功，请登录后使用系统功能"
}
```

**失败响应**:

| 状态码 | 说明                          |
| --- | --------------------------- |
| 400 | 缺少必要参数 / 两次密码不一致 / 密码长度不足6位 |
| 409 | 账号已存在                       |
| 500 | 注册失败（数据库错误）                 |

---

### 1.4 获取所有用户列表

- **请求方法**: GET
- **请求URL**: `/api/auth/users`

**成功响应** (200 OK):

```json
{
    "success": true,
    "users": [
        {
            "id": 1,
            "username": "admin",
            "name": "管理员",
            "created_at": "2026-07-06 14:58:16"
        }
    ]
}
```

---

### 1.5 获取单个用户信息

- **请求方法**: GET
- **请求URL**: `/api/auth/users/<user_id>`

**路径参数**:

| 参数      | 类型      | 说明   |
| ------- | ------- | ---- |
| user_id | Integer | 用户ID |

**成功响应** (200 OK):

```json
{
    "success": true,
    "user": {
        "id": 1,
        "username": "admin",
        "name": "管理员",
        "created_at": "2026-07-06 14:58:16"
    }
}
```

**失败响应**:

| 状态码 | 说明    |
| --- | ----- |
| 404 | 用户不存在 |

---

### 1.6 更新用户信息

- **请求方法**: PUT
- **请求URL**: `/api/auth/users/<user_id>`

**路径参数**:

| 参数      | 类型      | 说明   |
| ------- | ------- | ---- |
| user_id | Integer | 用户ID |

**请求参数**:

| 参数        | 类型     | 必填  | 说明    |
| --------- | ------ | --- | ----- |
| name      | String | 否   | 用户姓名  |
| password  | String | 否   | 新密码   |
| password2 | String | 否   | 确认新密码 |

**请求示例**:

```json
{
    "name": "新管理员",
    "password": "654321",
    "password2": "654321"
}
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "更新成功",
    "user": {
        "id": 1,
        "username": "admin",
        "name": "新管理员",
        "created_at": "2026-07-06 14:58:16"
    }
}
```

**失败响应**:

| 状态码 | 说明          |
| --- | ----------- |
| 400 | 两次密码不一致     |
| 404 | 用户不存在       |
| 500 | 更新失败（数据库错误） |

---

### 1.7 删除用户

- **请求方法**: DELETE
- **请求URL**: `/api/auth/users/<user_id>`

**路径参数**:

| 参数      | 类型      | 说明   |
| ------- | ------- | ---- |
| user_id | Integer | 用户ID |

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "删除成功"
}
```

**失败响应**:

| 状态码 | 说明          |
| --- | ----------- |
| 404 | 用户不存在       |
| 500 | 删除失败（数据库错误） |

---

## 2. YOLO人脸识别接口 (`/api/yolo`)

**注意**：此模块所有接口需要登录后才能访问。

### 2.1 YOLO物体检测

- **请求方法**: POST
- **请求URL**: `/api/yolo/detect`

**说明**: 此接口预留用于YOLO人脸识别功能，未来将实现无人机和灭火器识别。

**请求参数**:

| 参数         | 类型      | 必填  | 说明             |
| ---------- | ------- | --- | -------------- |
| image_data | String  | 是   | 图片数据（Base64编码） |
| device_id  | Integer | 否   | 设备ID           |
| user_id    | Integer | 否   | 用户ID           |

**请求示例**:

```json
{
    "image_data": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
    "device_id": 1,
    "user_id": 1
}
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "YOLO检测接口已就绪",
    "detection_result": {
        "objects": [],
        "confidence_scores": [],
        "bounding_boxes": []
    },
    "note": "此接口预留用于YOLO人脸识别功能，未来将实现无人机和灭火器识别"
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 400 | 缺少必要参数   |
| 401 | 未登录，请先登录 |

---

### 2.2 门禁验证

- **请求方法**: POST
- **请求URL**: `/api/yolo/access/verify`

**说明**: 此接口预留用于人脸识别开启门禁功能，未来将实现身份验证逻辑。

**请求参数**:

| 参数              | 类型      | 必填  | 说明        |
| --------------- | ------- | --- | --------- |
| user_id         | Integer | 否   | 用户ID      |
| device_id       | Integer | 否   | 设备ID      |
| detected_object | String  | 否   | 检测到的物体    |
| confidence      | Float   | 否   | 检测置信度，默认0 |

**请求示例**:

```json
{
    "user_id": 1,
    "device_id": 1,
    "detected_object": "drone",
    "confidence": 0.95
}
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "门禁验证接口已就绪",
    "access_granted": false,
    "detected_object": "drone",
    "confidence": 0.95,
    "note": "此接口预留用于人脸识别开启门禁功能，未来将实现身份验证逻辑"
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 400 | 缺少必要参数   |
| 401 | 未登录，请先登录 |

---

### 2.3 获取门禁访问记录列表

- **请求方法**: GET
- **请求URL**: `/api/yolo/access/records`

**查询参数**:

| 参数        | 类型      | 必填  | 说明         |
| --------- | ------- | --- | ---------- |
| user_id   | Integer | 否   | 根据用户ID筛选记录 |
| device_id | Integer | 否   | 根据设备ID筛选记录 |

**请求示例**:

```
GET /api/yolo/access/records?user_id=1&device_id=1
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "records": [
        {
            "id": 1,
            "user_id": 1,
            "device_id": 1,
            "access_type": "face_recognition",
            "result": "pending",
            "detected_object": "drone",
            "created_at": "2026-07-06 14:58:16"
        }
    ]
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 401 | 未登录，请先登录 |

---

### 2.4 获取单个门禁访问记录

- **请求方法**: GET
- **请求URL**: `/api/yolo/access/records/<record_id>`

**路径参数**:

| 参数        | 类型      | 说明   |
| --------- | ------- | ---- |
| record_id | Integer | 记录ID |

**成功响应** (200 OK):

```json
{
    "success": true,
    "record": {
        "id": 1,
        "user_id": 1,
        "device_id": 1,
        "access_type": "face_recognition",
        "result": "pending",
        "detected_object": "drone",
        "created_at": "2026-07-06 14:58:16"
    }
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 401 | 未登录，请先登录 |
| 404 | 记录不存在    |

---

## 3. 设备控制接口 (`/api/device`)

**注意**：此模块所有接口需要登录后才能访问。

### 3.1 获取设备列表

- **请求方法**: GET
- **请求URL**: `/api/device/devices`

**查询参数**:

| 参数   | 类型     | 必填  | 说明                          |
| ---- | ------ | --- | --------------------------- |
| type | String | 否   | 根据设备类型筛选（light/aircon/door） |
| room | String | 否   | 根据房间筛选（客厅/卧室）               |

**请求示例**:

```
GET /api/device/devices?type=light&room=客厅
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "devices": [
        {
            "id": 1,
            "device_name": "客厅灯",
            "device_type": "light",
            "status": "on",
            "room": "客厅",
            "created_at": "2026-07-06 14:58:28"
        }
    ]
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 401 | 未登录，请先登录 |

---

### 3.2 获取单个设备信息

- **请求方法**: GET
- **请求URL**: `/api/device/devices/<device_id>`

**路径参数**:

| 参数        | 类型      | 说明   |
| --------- | ------- | ---- |
| device_id | Integer | 设备ID |

**成功响应** (200 OK):

```json
{
    "success": true,
    "device": {
        "id": 1,
        "device_name": "客厅灯",
        "device_type": "light",
        "status": "on",
        "room": "客厅",
        "created_at": "2026-07-06 14:58:28"
    }
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 401 | 未登录，请先登录 |
| 404 | 设备不存在    |

---

### 3.3 创建新设备

- **请求方法**: POST
- **请求URL**: `/api/device/devices`

**请求参数**:

| 参数          | 类型     | 必填  | 说明                      |
| ----------- | ------ | --- | ----------------------- |
| device_name | String | 是   | 设备名称                    |
| device_type | String | 是   | 设备类型（light/aircon/door） |
| room        | String | 否   | 设备所在房间                  |
| status      | String | 否   | 设备状态，默认'off'            |

**请求示例**:

```json
{
    "device_name": "客厅灯",
    "device_type": "light",
    "room": "客厅",
    "status": "off"
}
```

**成功响应** (201 Created):

```json
{
    "success": true,
    "message": "设备创建成功",
    "device": {
        "id": 1,
        "device_name": "客厅灯",
        "device_type": "light",
        "status": "off",
        "room": "客厅",
        "created_at": "2026-07-06 14:58:28"
    }
}
```

**失败响应**:

| 状态码 | 说明          |
| --- | ----------- |
| 400 | 缺少必要参数      |
| 401 | 未登录，请先登录    |
| 500 | 创建失败（数据库错误） |

---

### 3.4 更新设备信息

- **请求方法**: PUT
- **请求URL**: `/api/device/devices/<device_id>`

**路径参数**:

| 参数        | 类型      | 说明   |
| --------- | ------- | ---- |
| device_id | Integer | 设备ID |

**请求参数**:

| 参数          | 类型     | 必填  | 说明     |
| ----------- | ------ | --- | ------ |
| device_name | String | 否   | 设备名称   |
| device_type | String | 否   | 设备类型   |
| room        | String | 否   | 设备所在房间 |
| status      | String | 否   | 设备状态   |

**请求示例**:

```json
{
    "device_name": "客厅主灯",
    "room": "客厅"
}
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "设备更新成功",
    "device": {
        "id": 1,
        "device_name": "客厅主灯",
        "device_type": "light",
        "status": "off",
        "room": "客厅",
        "created_at": "2026-07-06 14:58:28"
    }
}
```

**失败响应**:

| 状态码 | 说明          |
| --- | ----------- |
| 401 | 未登录，请先登录    |
| 404 | 设备不存在       |
| 500 | 更新失败（数据库错误） |

---

### 3.5 删除设备

- **请求方法**: DELETE
- **请求URL**: `/api/device/devices/<device_id>`

**路径参数**:

| 参数        | 类型      | 说明   |
| --------- | ------- | ---- |
| device_id | Integer | 设备ID |

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "设备删除成功"
}
```

**失败响应**:

| 状态码 | 说明          |
| --- | ----------- |
| 401 | 未登录，请先登录    |
| 404 | 设备不存在       |
| 500 | 删除失败（数据库错误） |

---

### 3.6 控制设备开关

- **请求方法**: POST
- **请求URL**: `/api/device/devices/<device_id>/control`

**路径参数**:

| 参数        | 类型      | 说明   |
| --------- | ------- | ---- |
| device_id | Integer | 设备ID |

**请求参数**:

| 参数     | 类型     | 必填  | 说明           |
| ------ | ------ | --- | ------------ |
| action | String | 是   | 操作指令（on/off） |

**请求示例**:

```json
{
    "action": "on"
}
```

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "客厅灯已on",
    "device": {
        "id": 1,
        "device_name": "客厅灯",
        "device_type": "light",
        "status": "on",
        "room": "客厅",
        "created_at": "2026-07-06 14:58:28"
    }
}
```

**失败响应**:

| 状态码 | 说明               |
| --- | ---------------- |
| 400 | 缺少必要参数 / 无效的操作指令 |
| 401 | 未登录，请先登录         |
| 404 | 设备不存在            |
| 500 | 控制失败（数据库错误）      |

---

### 3.7 切换设备状态

- **请求方法**: POST
- **请求URL**: `/api/device/devices/<device_id>/toggle`

**路径参数**:

| 参数        | 类型      | 说明   |
| --------- | ------- | ---- |
| device_id | Integer | 设备ID |

**说明**: 将设备状态从on切换为off，或从off切换为on。

**成功响应** (200 OK):

```json
{
    "success": true,
    "message": "客厅灯状态已切换为on",
    "device": {
        "id": 1,
        "device_name": "客厅灯",
        "device_type": "light",
        "status": "on",
        "room": "客厅",
        "created_at": "2026-07-06 14:58:28"
    }
}
```

**失败响应**:

| 状态码 | 说明          |
| --- | ----------- |
| 401 | 未登录，请先登录    |
| 404 | 设备不存在       |
| 500 | 切换失败（数据库错误） |

---

### 3.8 获取所有设备类型

- **请求方法**: GET
- **请求URL**: `/api/device/devices/types`

**成功响应** (200 OK):

```json
{
    "success": true,
    "types": ["light", "aircon", "door"]
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 401 | 未登录，请先登录 |

---

### 3.9 获取所有设备所在房间

- **请求方法**: GET
- **请求URL**: `/api/device/devices/rooms`

**成功响应** (200 OK):

```json
{
    "success": true,
    "rooms": ["客厅", "卧室", "厨房"]
}
```

**失败响应**:

| 状态码 | 说明       |
| --- | -------- |
| 401 | 未登录，请先登录 |

---

## 4. 系统接口

### 4.1 首页

- **请求方法**: GET
- **请求URL**: `/`

**说明**: 根据登录状态返回不同内容。

**未登录响应** (200 OK):

```json
{
    "success": true,
    "message": "智能家居系统 - 请先登录",
    "status": "not_logged_in",
    "endpoints": {
        "auth": {
            "login": "POST /api/auth/login",
            "register": "POST /api/auth/register"
        }
    },
    "note": "人脸识别和设备控制功能需要登录后才能访问"
}
```

**已登录响应** (200 OK):

```json
{
    "success": true,
    "message": "欢迎回来，用户ID: 1",
    "status": "logged_in",
    "user_id": 1,
    "username": "admin",
    "endpoints": {
        "auth": {
            "logout": "POST /api/auth/logout"
        },
        "yolo": {
            "detect": "POST /api/yolo/detect",
            "verify_access": "POST /api/yolo/access/verify",
            "access_records": "GET /api/yolo/access/records"
        },
        "device": {
            "devices": "GET/POST /api/device/devices",
            "device": "GET/PUT/DELETE /api/device/devices/<id>",
            "control": "POST /api/device/devices/<id>/control",
            "toggle": "POST /api/device/devices/<id>/toggle"
        }
    }
}
```

---

## 启动方式

### 开发环境

```bash
# 进入项目目录
cd flaskproject

# 安装依赖（首次运行）
pip install flask flask-sqlalchemy mysql-connector-python werkzeug

# 启动应用
python app.py
```

### 配置数据库说明

默认使用 SQLite 数据库，数据库文件位于 `smart_home.db`。

如需切换到 MySQL，修改 `app.py` 中的配置：

```python
# 注释掉 SQLite 配置
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smart_home.db'

# 启用 MySQL 配置（替换为实际的用户名、密码和数据库名）
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://username:password@localhost:3306/smart_home'
```

---

## 使用示例

### 使用 curl 测试

```bash
# 查看首页（未登录）
curl http://localhost:5000/

# 注册用户
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456","password2":"123456","name":"管理员"}'

# 登录（使用 -c 保存Cookie）
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}' \
  -c cookie.txt

# 查看首页（已登录）
curl -b cookie.txt http://localhost:5000/

# 创建设备（需要登录）
curl -X POST http://localhost:5000/api/device/devices \
  -H "Content-Type: application/json" \
  -d '{"device_name":"客厅灯","device_type":"light","room":"客厅"}' \
  -b cookie.txt

# 控制设备（需要登录）
curl -X POST http://localhost:5000/api/device/devices/1/control \
  -H "Content-Type: application/json" \
  -d '{"action":"on"}' \
  -b cookie.txt
```

### 使用 Python requests 测试

```python
import requests

# 创建会话对象（自动管理Cookie）
session = requests.Session()

# 查看首页（未登录）
response = session.get('http://localhost:5000/')
print('首页（未登录）:', response.json())

# 注册用户
response = session.post(
    'http://localhost:5000/api/auth/register',
    json={'username': 'admin', 'password': '123456', 'password2': '123456', 'name': '管理员'}
)
print('注册:', response.json())

# 登录
response = session.post(
    'http://localhost:5000/api/auth/login',
    json={'username': 'admin', 'password': '123456'}
)
print('登录:', response.json())

# 查看首页（已登录）
response = session.get('http://localhost:5000/')
print('首页（已登录）:', response.json())

# 创建设备（需要登录）
response = session.post(
    'http://localhost:5000/api/device/devices',
    json={'device_name': '客厅灯', 'device_type': 'light', 'room': '客厅'}
)
print('创建设备:', response.json())

# 控制设备（需要登录）
response = session.post(
    'http://localhost:5000/api/device/devices/1/control',
    json={'action': 'on'}
)
print('控制设备:', response.json())
```

---

## 安全特性

1. **密码安全**: 使用 Werkzeug 的 `generate_password_hash` 进行密码哈希存储，不存储明文密码
2. **SQL 注入防护**: 使用 SQLAlchemy ORM 进行数据库操作，自动防止 SQL 注入攻击
3. **敏感信息保护**: 返回用户信息时不包含密码字段
4. **标准错误处理**: 使用标准 HTTP 状态码进行错误响应
5. **Session 会话管理**: 使用 Flask Session 管理登录状态，登录一次即可访问所有功能
6. **接口访问控制**: YOLO人脸识别和设备控制接口需要登录后才能访问，未登录返回 401 错误

---

## 版本历史

| 版本   | 日期         | 说明                              |
| ---- | ---------- | ------------------------------- |
| v1.0 | 2026-07-06 | 初始版本，实现用户认证、设备控制和YOLO接口预留       |
| v1.1 | 2026-07-07 | 添加Session会话管理，人脸识别和设备控制接口需登录后访问 |
