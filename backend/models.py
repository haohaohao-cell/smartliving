"""
数据库模型定义
=====================================
定义智能家居系统所需的数据表结构

包含模型：
- User - 用户信息模型
- Device - 设备信息模型
- AccessRecord - 门禁访问记录模型

性能优化：
- 高频查询字段添加索引
- to_dict方法优化，避免重复格式化
"""

from flask_sqlalchemy import SQLAlchemy

# 创建SQLAlchemy实例，用于数据库操作
db = SQLAlchemy()


class User(db.Model):
    """
    用户信息模型
    存储授权人员的账号信息
    
    表名: users
    """
    __tablename__ = 'users'
    
    # 用户ID，主键，自增
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 用户名，唯一，不可为空，最大长度50字符，添加索引提升登录查询速度
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    # 密码（哈希存储），不可为空，最大长度255字符
    password = db.Column(db.String(255), nullable=False)
    # 用户姓名，不可为空，最大长度100字符
    name = db.Column(db.String(100), nullable=False)
    # 创建时间，默认为当前时间
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    # 当前会话token（用于互斥登录），最大长度500字符，添加索引提升token验证速度
    session_token = db.Column(db.String(500), index=True)
    # 最后登录时间
    last_login_time = db.Column(db.DateTime)
    # 用户角色：admin/user
    role = db.Column(db.String(20), default='user')
    
    def to_dict(self):
        """将用户对象转换为字典格式，用于API响应
        注意：不返回密码字段和session_token，保护用户隐私
        """
        created_at_str = self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        return {
            'id': self.id,
            'username': self.username,
            'name': self.name,
            'role': self.role,
            'created_at': created_at_str
        }


class Device(db.Model):
    """
    设备信息模型
    存储智能家居设备的信息，如灯、空调等
    
    表名: devices
    """
    __tablename__ = 'devices'
    
    # 设备ID，主键，自增
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 设备名称，不可为空，最大长度100字符
    device_name = db.Column(db.String(100), nullable=False)
    # 设备类型，不可为空，最大长度50字符，添加索引提升类型筛选速度
    device_type = db.Column(db.String(50), nullable=False, index=True)
    # 设备状态，默认值'off'，最大长度20字符，添加索引提升状态查询速度
    status = db.Column(db.String(20), default='off', index=True)
    # 设备所在房间，最大长度50字符
    room = db.Column(db.String(50))
    # 创建时间，默认为当前时间
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def to_dict(self):
        """将设备对象转换为字典格式，用于API响应"""
        created_at_str = self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        return {
            'id': self.id,
            'device_name': self.device_name,
            'device_type': self.device_type,
            'status': self.status,
            'room': self.room,
            'created_at': created_at_str
        }


class FaceFeature(db.Model):
    """
    人脸特征模型
    存储用户的人脸特征向量，用于人脸识别比对
    
    表名: face_features
    """
    __tablename__ = 'face_features'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True, nullable=False)
    feature_data = db.Column(db.LargeBinary, nullable=False)
    feature_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    user = db.relationship('User', backref=db.backref('face_features', lazy=True))
    
    def to_dict(self):
        created_at_str = self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        return {
            'id': self.id,
            'user_id': self.user_id,
            'feature_name': self.feature_name,
            'created_at': created_at_str
        }


class AccessRecord(db.Model):
    """
    门禁访问记录模型
    存储人脸识别门禁系统的访问记录
    
    表名: access_records
    """
    __tablename__ = 'access_records'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), index=True)
    access_type = db.Column(db.String(50))
    result = db.Column(db.String(20), index=True)
    detected_object = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp(), index=True)
    
    user = db.relationship('User', backref=db.backref('access_records', lazy=True))
    device = db.relationship('Device', backref=db.backref('access_records', lazy=True))
    
    def to_dict(self):
        created_at_str = self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        return {
            'id': self.id,
            'user_id': self.user_id,
            'device_id': self.device_id,
            'access_type': self.access_type,
            'result': self.result,
            'detected_object': self.detected_object,
            'created_at': created_at_str
        }
