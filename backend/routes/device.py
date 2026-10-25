"""
设备控制接口模块
=====================================
提供智能家居设备管理和控制的API接口

URL前缀: /api/device

支持的设备类型：
- light（灯）
- aircon（空调）
- door（门）
- access_control（门禁）
- 其他自定义设备类型

功能：
- 设备CRUD管理
- 设备开关控制
- 设备状态切换
- 设备类型和房间查询

所有接口需要登录后才能访问

性能优化：
- 高频只读接口内存缓存
- 更新操作时主动清除缓存
- print替换为logging
"""

from flask import Blueprint, request, jsonify
from models import db, Device
from utils import login_required
import time
import logging

logger = logging.getLogger(__name__)

# 创建设备控制模块的Blueprint
device_bp = Blueprint('device', __name__)

# 设备列表内存缓存：{'devices': {'data': list, 'expires': float}}
_device_cache = {}
_DEVICE_CACHE_TTL = 300  # 缓存有效期（秒）

# 缓存键常量
_CACHE_KEY_DEVICES = 'devices'


def invalidate_device_cache():
    """清除设备列表缓存"""
    _device_cache.pop(_CACHE_KEY_DEVICES, None)


@device_bp.route('/devices', methods=['GET'])
@login_required
def get_devices():
    """
    获取设备列表接口（带内存缓存）
    
    请求方法: GET
    请求URL: /api/device/devices
    
    查询参数（可选）:
    - type: string, 根据设备类型筛选（如：light, aircon）
    - room: string, 根据房间筛选（如：客厅, 卧室）
    
    成功响应（200 OK）:
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
    
    失败响应:
    - 401: 未登录，请先登录
    """
    # 获取查询参数
    device_type = request.args.get('type')
    room = request.args.get('room')
    
    # 无筛选条件时使用缓存
    if not device_type and not room:
        cached = _device_cache.get(_CACHE_KEY_DEVICES)
        if cached and cached['expires'] > time.time():
            return jsonify({
                'success': True,
                'devices': cached['data']
            }), 200
    
    # 构建查询
    query = db.session.query(Device)
    
    # 根据设备类型筛选（如果提供）
    if device_type:
        query = query.filter_by(device_type=device_type)
    # 根据房间筛选（如果提供）
    if room:
        query = query.filter_by(room=room)
    
    # 查询所有设备
    devices = query.all()
    devices_data = [device.to_dict() for device in devices]
    
    # 无筛选条件时写入缓存
    if not device_type and not room:
        _device_cache[_CACHE_KEY_DEVICES] = {
            'data': devices_data,
            'expires': time.time() + _DEVICE_CACHE_TTL
        }
    
    # 返回设备列表
    return jsonify({
        'success': True,
        'devices': devices_data
    }), 200


@device_bp.route('/devices/<int:device_id>', methods=['GET'])
@login_required
def get_device(device_id):
    """
    获取单个设备信息接口
    
    请求方法: GET
    请求URL: /api/device/devices/<device_id>
    
    路径参数:
    - device_id: int, 设备ID
    
    成功响应（200 OK）:
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
    
    失败响应:
    - 401: 未登录，请先登录
    - 404: 设备不存在
    """
    # 根据设备ID查询设备
    device = db.session.get(Device, device_id)
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    return jsonify({'success': True, 'device': device.to_dict()}), 200


@device_bp.route('/devices', methods=['POST'])
@login_required
def create_device():
    """
    创建新设备接口
    
    请求方法: POST
    请求URL: /api/device/devices
    
    请求参数（JSON格式）:
    {
        "device_name": "string, 必填, 设备名称",
        "device_type": "string, 必填, 设备类型（如：light, aircon）",
        "room": "string, 可选, 设备所在房间",
        "status": "string, 可选, 设备状态，默认'off'"
    }
    
    成功响应（201 Created）:
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
    
    失败响应:
    - 400: 缺少必要参数
    - 401: 未登录，请先登录
    - 500: 创建失败（数据库错误）
    """
    data = request.get_json()
    
    # 参数校验：检查是否包含必要字段
    if not data or 'device_name' not in data or 'device_type' not in data:
        return jsonify({'success': False, 'message': '缺少必要参数'}), 400
    
    # 提取请求参数
    device_name = data['device_name'].strip()
    device_type = data['device_type'].strip()
    room = data.get('room', '').strip()
    status = data.get('status', 'off')
    
    # 长度校验
    if len(device_name) > 100:
        return jsonify({'success': False, 'message': '设备名称长度不能超过100字符'}), 400
    if len(device_type) > 50:
        return jsonify({'success': False, 'message': '设备类型长度不能超过50字符'}), 400
    if len(room) > 50:
        return jsonify({'success': False, 'message': '房间名称长度不能超过50字符'}), 400
    
    # 创建新设备对象
    new_device = Device(
        device_name=device_name,
        device_type=device_type,
        room=room,
        status=status
    )
    
    try:
        # 将新设备添加到数据库会话
        db.session.add(new_device)
        # 提交数据库事务
        db.session.commit()
        # 清除设备列表缓存
        invalidate_device_cache()
        # 返回成功响应，包含设备信息
        return jsonify({
            'success': True,
            'message': '设备创建成功',
            'device': new_device.to_dict()
        }), 201
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        logger.error(f"创建设备失败: {e}")
        return jsonify({'success': False, 'message': f'创建失败: {e}'}), 500


@device_bp.route('/devices/<int:device_id>', methods=['PUT'])
@login_required
def update_device(device_id):
    """
    更新设备信息接口
    
    请求方法: PUT
    请求URL: /api/device/devices/<device_id>
    
    路径参数:
    - device_id: int, 设备ID
    
    请求参数（JSON格式，可选）:
    {
        "device_name": "string, 可选, 设备名称",
        "device_type": "string, 可选, 设备类型",
        "room": "string, 可选, 设备所在房间",
        "status": "string, 可选, 设备状态"
    }
    
    成功响应（200 OK）:
    {
        "success": true,
        "message": "设备更新成功",
        "device": {
            "id": 1,
            "device_name": "客厅灯",
            "device_type": "light",
            "status": "on",
            "room": "客厅",
            "created_at": "2026-07-06 14:58:28"
        }
    }
    
    失败响应:
    - 401: 未登录，请先登录
    - 404: 设备不存在
    - 500: 更新失败（数据库错误）
    """
    data = request.get_json()
    # 根据设备ID查询设备
    device = db.session.get(Device, device_id)
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    # 更新设备名称（如果提供）
    if 'device_name' in data:
        device.device_name = data['device_name']
    # 更新设备类型（如果提供）
    if 'device_type' in data:
        device.device_type = data['device_type']
    # 更新设备所在房间（如果提供）
    if 'room' in data:
        device.room = data['room']
    # 更新设备状态（如果提供）
    if 'status' in data:
        device.status = data['status']
    
    try:
        # 提交数据库事务
        db.session.commit()
        # 清除设备列表缓存
        invalidate_device_cache()
        return jsonify({
            'success': True,
            'message': '设备更新成功',
            'device': device.to_dict()
        }), 200
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        logger.error(f"更新设备失败: {e}")
        return jsonify({'success': False, 'message': f'更新失败: {e}'}), 500


@device_bp.route('/devices/<int:device_id>', methods=['DELETE'])
@login_required
def delete_device(device_id):
    """
    删除设备接口
    
    请求方法: DELETE
    请求URL: /api/device/devices/<device_id>
    
    路径参数:
    - device_id: int, 设备ID
    
    成功响应（200 OK）:
    {
        "success": true,
        "message": "设备删除成功"
    }
    
    失败响应:
    - 401: 未登录，请先登录
    - 404: 设备不存在
    - 500: 删除失败（数据库错误）
    """
    # 根据设备ID查询设备
    device = db.session.get(Device, device_id)
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    try:
        # 删除设备
        db.session.delete(device)
        # 提交数据库事务
        db.session.commit()
        # 清除设备列表缓存
        invalidate_device_cache()
        return jsonify({'success': True, 'message': '设备删除成功'}), 200
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        logger.error(f"删除设备失败: {e}")
        return jsonify({'success': False, 'message': f'删除失败: {e}'}), 500


@device_bp.route('/devices/<int:device_id>/control', methods=['POST'])
@login_required
def control_device(device_id):
    """
    控制设备开关接口
    
    请求方法: POST
    请求URL: /api/device/devices/<device_id>/control
    
    路径参数:
    - device_id: int, 设备ID
    
    请求参数（JSON格式）:
    {
        "action": "string, 必填, 操作指令（on/off）"
    }
    
    成功响应（200 OK）:
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
    
    失败响应:
    - 400: 缺少必要参数 / 无效的操作指令
    - 401: 未登录，请先登录
    - 404: 设备不存在
    - 500: 控制失败（数据库错误）
    """
    data = request.get_json()
    # 根据设备ID查询设备
    device = db.session.get(Device, device_id)
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    # 参数校验：检查是否包含操作指令
    if not data or 'action' not in data:
        return jsonify({'success': False, 'message': '缺少必要参数 action'}), 400
    
    # 将操作指令转换为小写
    action = data['action'].lower()
    
    # 验证操作指令是否有效
    if action in ('on', 'off'):
        # 更新设备状态
        device.status = action
        try:
            # 提交数据库事务
            db.session.commit()
            # 清除设备列表缓存
            invalidate_device_cache()
            return jsonify({
                'success': True,
                'message': f'{device.device_name}已{action}',
                'device': device.to_dict()
            }), 200
        except Exception as e:
            # 发生异常时回滚事务
            db.session.rollback()
            logger.error(f"控制设备失败: {e}")
            return jsonify({'success': False, 'message': f'控制失败: {e}'}), 500
    else:
        # 返回无效指令错误
        return jsonify({'success': False, 'message': '无效的操作指令，仅支持 on/off'}), 400


@device_bp.route('/devices/<int:device_id>/toggle', methods=['POST'])
@login_required
def toggle_device(device_id):
    """
    切换设备状态接口
    
    请求方法: POST
    请求URL: /api/device/devices/<device_id>/toggle
    
    路径参数:
    - device_id: int, 设备ID
    
    成功响应（200 OK）:
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
    
    失败响应:
    - 401: 未登录，请先登录
    - 404: 设备不存在
    - 500: 切换失败（数据库错误）
    """
    # 根据设备ID查询设备
    device = db.session.get(Device, device_id)
    
    if not device:
        return jsonify({'success': False, 'message': '设备不存在'}), 404
    
    # 切换设备状态：如果是off则变为on，如果是on则变为off
    device.status = 'on' if device.status == 'off' else 'off'
    
    try:
        # 提交数据库事务
        db.session.commit()
        # 清除设备列表缓存
        invalidate_device_cache()
        return jsonify({
            'success': True,
            'message': f'{device.device_name}状态已切换为{device.status}',
            'device': device.to_dict()
        }), 200
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        logger.error(f"切换设备状态失败: {e}")
        return jsonify({'success': False, 'message': f'切换失败: {e}'}), 500


@device_bp.route('/devices/types', methods=['GET'])
@login_required
def get_device_types():
    """
    获取所有设备类型列表接口
    
    请求方法: GET
    请求URL: /api/device/devices/types
    
    成功响应（200 OK）:
    {
        "success": true,
        "types": ["light", "aircon", "door"]
    }
    
    失败响应:
    - 401: 未登录，请先登录
    """
    # 查询所有不同的设备类型
    types = db.session.query(Device.device_type).distinct().all()
    # 提取设备类型列表
    device_types = [t[0] for t in types]
    
    return jsonify({
        'success': True,
        'types': device_types
    }), 200


@device_bp.route('/devices/rooms', methods=['GET'])
@login_required
def get_device_rooms():
    """
    获取所有设备所在房间列表接口
    
    请求方法: GET
    请求URL: /api/device/devices/rooms
    
    成功响应（200 OK）:
    {
        "success": true,
        "rooms": ["客厅", "卧室", "厨房"]
    }
    
    失败响应:
    - 401: 未登录，请先登录
    """
    # 查询所有不同的房间
    rooms = db.session.query(Device.room).distinct().all()
    # 提取房间列表（过滤空值）
    room_list = [r[0] for r in rooms if r[0]]
    
    return jsonify({
        'success': True,
        'rooms': room_list
    }), 200
