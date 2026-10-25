"""
YOLO人脸识别接口模块
=====================================
提供YOLO物体检测和门禁验证的API接口

URL前缀: /api/yolo

功能：
- YOLO物体检测（识别无人机、灭火器等）
- 人脸识别开启门禁
- 访问记录查询
- 摄像头视频流（640x480, 12fps）
- 跨帧跟踪（每隔1帧检测一次）

所有接口需要登录后才能访问

性能优化：
- 使用线程池异步推理
- 数据库异步写入
- 访问记录限制为最近20条
- joinedload预加载关联表，避免N+1查询
- YOLO在320x320小图上推理，坐标映射回640x480
- 跨帧跟踪减少检测频率
"""

from flask import Blueprint, request, jsonify, Response, current_app, g
from models import db, AccessRecord
from utils import login_required
from yolo_model import detect_objects, detect_objects_async, load_model, is_model_loaded
from face_recognition import process_roi, add_identity, load_features_from_db, get_registered_faces, delete_identity
from detection_types import is_person_class
from sqlalchemy.orm import joinedload

import base64
import io
import threading
from scipy.optimize import linear_sum_assignment
import logging
import time
from PIL import Image
import cv2
import numpy as np

logger = logging.getLogger(__name__)

MAX_ACCESS_RECORDS = 20

yolo_bp = Blueprint('yolo', __name__)

CAM_WIDTH = 640
CAM_HEIGHT = 480
FRAME_RATE = 12
FRAME_INTERVAL = 1.0 / FRAME_RATE

_camera = None
_camera_lock = threading.Lock()
_latest_frame = None
_frame_lock = threading.Lock()
_camera_running = False
_camera_ref_count = 0
_camera_ref_lock = threading.Lock()
_last_client_access_time = 0
_client_access_lock = threading.Lock()
CAMERA_IDLE_TIMEOUT = 30

_frame_counter = 0
_frame_counter_lock = threading.Lock()

_tracked_objects = {}
_track_lock = threading.Lock()
TRACK_LIFETIME = 25


class TrackedObject:
    def __init__(self, obj_id, bbox, obj_type, confidence):
        self.id = obj_id
        self.bbox = bbox
        self.type = obj_type
        self.confidence = confidence
        self.last_seen = 0
        self.identity = None


def iou(box1, box2):
    x1 = max(box1['x1'], box2['x1'])
    y1 = max(box1['y1'], box2['y1'])
    x2 = min(box1['x2'], box2['x2'])
    y2 = min(box1['y2'], box2['y2'])
    
    w = max(0, x2 - x1)
    h = max(0, y2 - y1)
    inter = w * h
    
    area1 = (box1['x2'] - box1['x1']) * (box1['y2'] - box1['y1'])
    area2 = (box2['x2'] - box2['x1']) * (box2['y2'] - box2['y1'])
    
    if area1 + area2 - inter == 0:
        return 0
    return inter / (area1 + area2 - inter)


def update_tracks(new_detections):
    global _tracked_objects
    
    with _track_lock:
        for track_id in list(_tracked_objects.keys()):
            _tracked_objects[track_id].last_seen += 1
            if _tracked_objects[track_id].last_seen > TRACK_LIFETIME:
                del _tracked_objects[track_id]
        
        tracks = list(_tracked_objects.items())
        if not tracks or not new_detections:
            for detection in new_detections:
                new_id = max(_tracked_objects.keys(), default=0) + 1
                obj = TrackedObject(
                    new_id,
                    detection['bbox'],
                    detection['type'],
                    detection['confidence']
                )
                if 'identity' in detection:
                    obj.identity = detection['identity']
                _tracked_objects[new_id] = obj
            return
        
        cost_matrix = []
        for detection in new_detections:
            row = []
            for track_id, track in tracks:
                if track.type == detection['type']:
                    iou_score = iou(track.bbox, detection['bbox'])
                    row.append(1.0 - iou_score)
                else:
                    row.append(1.0)
            cost_matrix.append(row)
        
        cost_matrix = [[1.0 if col > 1.0 else col for col in row] for row in cost_matrix]
        
        row_indices, col_indices = linear_sum_assignment(cost_matrix)
        
        matched_tracks = set()
        matched_detections = set()
        
        for row_idx, col_idx in zip(row_indices, col_indices):
            cost = cost_matrix[row_idx][col_idx]
            if cost < 0.50:
                track_id, track = tracks[col_idx]
                detection = new_detections[row_idx]
                
                _tracked_objects[track_id].bbox = detection['bbox']
                _tracked_objects[track_id].confidence = detection['confidence']
                _tracked_objects[track_id].last_seen = 0
                if 'identity' in detection and detection['identity'] != 'Unknown':
                    _tracked_objects[track_id].identity = detection['identity']
                
                matched_tracks.add(track_id)
                matched_detections.add(row_idx)
        
        for row_idx, detection in enumerate(new_detections):
            if row_idx not in matched_detections:
                new_id = max(_tracked_objects.keys(), default=0) + 1
                obj = TrackedObject(
                    new_id,
                    detection['bbox'],
                    detection['type'],
                    detection['confidence']
                )
                if 'identity' in detection:
                    obj.identity = detection['identity']
                _tracked_objects[new_id] = obj


def crop_head_region(frame, bbox):
    """从640x480原始帧中裁剪头部区域，并直接缩放到160x160"""
    x1, y1, x2, y2 = bbox['x1'], bbox['y1'], bbox['x2'], bbox['y2']
    
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    width = x2 - x1
    height = y2 - y1
    
    head_top = y1
    head_bottom = y1 + height * 0.25
    head_left = center_x - width * 0.35
    head_right = center_x + width * 0.35
    
    expand_w = (head_right - head_left) * 0.1
    expand_h = (head_bottom - head_top) * 0.1
    
    head_left -= expand_w
    head_right += expand_w
    head_top -= expand_h
    head_bottom += expand_h
    
    head_left = max(0, int(head_left))
    head_top = max(0, int(head_top))
    
    h, w = frame.shape[:2]
    head_right = min(w, int(head_right))
    head_bottom = min(h, int(head_bottom))
    
    head_w = head_right - head_left
    head_h = head_bottom - head_top
    
    if head_w < 60 or head_h < 60:
        return None
    
    head_region = frame[head_top:head_bottom, head_left:head_right]
    head_resized = cv2.resize(head_region, (160, 160))
    return head_resized


def cleanup_old_records():
    try:
        record_count = db.session.query(AccessRecord).count()
        if record_count > MAX_ACCESS_RECORDS:
            delete_count = record_count - MAX_ACCESS_RECORDS
            subquery = db.session.query(AccessRecord.id)\
                .order_by(AccessRecord.created_at.asc())\
                .limit(delete_count)\
                .subquery()
            db.session.query(AccessRecord)\
                .filter(AccessRecord.id.in_(subquery))\
                .delete(synchronize_session=False)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"清理旧记录失败: {e}")


def process_detection_result(response, result, frame, confidence, user_id, device_id, 
                             tracked_identity=None, tracked_face_detected=False):
    objects = result.get('objects', [])
    logger.info(f"process_detection_result - 检测到的物体列表: {objects}")
    logger.info(f"process_detection_result - 置信度分数: {result.get('confidence_scores', [])}")
    
    if not objects:
        logger.info("process_detection_result - 未检测到任何物体")
        return response
    
    detected_object = objects[0]
    detection_confidence = result['confidence_scores'][0]
    
    logger.info(f"process_detection_result - 处理第一个物体: {detected_object}, 置信度: {detection_confidence:.4f}, 阈值: {confidence}")
    
    if is_person_class(detected_object) and detection_confidence >= confidence:
        logger.info(f"process_detection_result - ✅ 检测到人类，开始处理人脸识别")
        response['access_granted'] = True
        response['detected_object'] = detected_object
        response['confidence'] = detection_confidence
        
        identity = tracked_identity if tracked_identity is not None else 'Unknown'
        similarity = 0.0
        face_detected = tracked_face_detected
        head_detected = False
        
        if tracked_identity is None:
            bbox = result['bounding_boxes'][0]
            logger.info(f"process_detection_result - 人类边界框: {bbox}")
            head_resized = crop_head_region(frame, bbox)
            
            if head_resized is not None:
                head_detected = True
                logger.info(f"process_detection_result - ✅ 成功裁剪头部区域，大小: {head_resized.shape}")
                
                head_enc, head_buf = cv2.imencode('.jpg', head_resized)
                if head_enc:
                    head_base64 = base64.b64encode(head_buf.tobytes()).decode('utf-8')
                    response['head_image'] = f'data:image/jpeg;base64,{head_base64}'
                
                face_info, identity, similarity, user_id = process_roi(head_resized)
                logger.info(f"process_detection_result - 人脸识别结果: identity={identity}, similarity={similarity:.4f}, user_id={user_id}")
                
                if identity != 'Unknown':
                    face_detected = True
                    logger.info(f"process_detection_result - ✅ 人脸识别成功: {identity}")
                else:
                    face_detected = bool(face_info)
                    logger.info(f"process_detection_result - 人脸识别未知, face_info={face_info}")
            else:
                logger.warning(f"process_detection_result - ❌ 头部区域裁剪失败")
        else:
            logger.info(f"process_detection_result - 使用跟踪身份: {tracked_identity}")
        
        response['head_detected'] = head_detected
        response['face_detected'] = face_detected
        response['identity'] = identity
        response['similarity'] = similarity
        
        if identity != 'Unknown':
            response['message'] = f'识别成功：{identity}'
        else:
            response['message'] = '未识别到身份'
        
        if identity != 'Unknown' and user_id and device_id:
            save_access_record_async(
                user_id=user_id,
                device_id=device_id,
                access_type='face_recognition',
                result='granted',
                detected_object='person'
            )
    elif detected_object == 'drone' and detection_confidence >= confidence:
        logger.info(f"process_detection_result - ✅ 检测到无人机")
        response['safety_warning'] = '检测到无人机入侵'
        response['safety_object'] = 'drone'
        response['detected_object'] = detected_object
        response['confidence'] = detection_confidence
    elif detected_object == 'fire_extinguisher' and detection_confidence >= confidence:
        logger.info(f"process_detection_result - ✅ 检测到灭火器")
        response['access_granted'] = True
        response['detected_object'] = detected_object
        response['confidence'] = detection_confidence
        
        if user_id and device_id:
            save_access_record_async(
                user_id=user_id,
                device_id=device_id,
                access_type='face_recognition',
                result='granted',
                detected_object='fire_extinguisher'
            )
    else:
        logger.info(f"process_detection_result - 其他物体: {detected_object}, 置信度不足或未处理")
        response['access_granted'] = False
        response['detected_object'] = detected_object
        response['confidence'] = detection_confidence
    
    return response


def save_access_record_async(user_id, device_id, access_type, result, detected_object):
    app_ref = current_app._get_current_object()
    
    def _save():
        with app_ref.app_context():
            try:
                access_record = AccessRecord(
                    user_id=user_id,
                    device_id=device_id,
                    access_type=access_type,
                    result=result,
                    detected_object=detected_object
                )
                db.session.add(access_record)
                db.session.commit()
                cleanup_old_records()
            except Exception as e:
                db.session.rollback()
                logger.error(f"异步保存访问记录失败: {e}")
    
    thread = threading.Thread(target=_save, daemon=True)
    thread.start()


def base64_to_image(image_data):
    try:
        if image_data.startswith('data:image'):
            image_data = image_data.split(',')[1]
        
        image_bytes = base64.b64decode(image_data)
        image = Image.open(io.BytesIO(image_bytes))
        return image
    except Exception as e:
        logger.error(f"Base64图片转换失败: {e}")
        return None


def image_to_bgr_array(image):
    if image is None:
        return None
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


@yolo_bp.route('/detect', methods=['POST'])
@login_required
def detect_object():
    data = request.get_json()
    
    if not data or 'image_data' not in data:
        return jsonify({
            'success': False,
            'message': '缺少必要参数'
        }), 400
    
    image_data = data['image_data']
    confidence = data.get('confidence', 0.25)
    
    image = base64_to_image(image_data)
    if image is None:
        return jsonify({
            'success': False,
            'message': '图片格式错误'
        }), 400
    
    image_array = image_to_bgr_array(image)
    result = detect_objects(image_array=image_array, conf=confidence)
    
    if not result['success']:
        return jsonify({
            'success': False,
            'message': result['message']
        }), 500
    
    return jsonify({
        'success': True,
        'message': '检测成功',
        'detection_result': {
            'objects': result['objects'],
            'confidence_scores': result['confidence_scores'],
            'bounding_boxes': result['bounding_boxes'],
            'class_names': result.get('class_names', [])
        }
    }), 200


@yolo_bp.route('/access/verify', methods=['POST'])
@login_required
def verify_access():
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': '缺少必要参数'
        }), 400
    
    user_id = data.get('user_id')
    device_id = data.get('device_id')
    image_data = data.get('image_data')
    confidence = data.get('confidence', 0.5)
    
    detected_object = None
    detection_confidence = 0
    access_granted = False
    detection_result = {}
    safety_warning = None
    safety_object = None
    
    if not image_data:
        return jsonify({
            'success': False,
            'message': '缺少必要参数：image_data'
        }), 400
    
    image = base64_to_image(image_data)
    if image is None:
        return jsonify({
            'success': False,
            'message': '图片格式错误'
        }), 400
    
    image_array = image_to_bgr_array(image)
    future = detect_objects_async(image_array=image_array, conf=confidence)
    try:
        result = future.result(timeout=30)
    except TimeoutError:
        return jsonify({
            'success': False,
            'message': '检测超时，请重试'
        }), 504
    except Exception as e:
        logger.error(f"门禁检测失败: {e}")
        return jsonify({
            'success': False,
            'message': '检测失败，请稍后重试'
        }), 500
    
    if not result['success']:
        return jsonify({
            'success': False,
            'message': f'检测失败: {result["message"]}'
        }), 500
    
    detection_result = result
    
    response = {
        'success': True,
        'message': '未检测到任何物体',
        'access_granted': access_granted,
        'detected_object': detected_object,
        'confidence': detection_confidence,
        'detection_result': detection_result,
        'safety_warning': safety_warning,
        'safety_object': safety_object
    }
    
    process_detection_result(response, detection_result, image_array, confidence, user_id, device_id)
    
    record_already_saved = (
        response.get('identity', 'Unknown') != 'Unknown'
        or (response.get('detected_object') == 'fire_extinguisher' and response.get('access_granted'))
    )
    if user_id and device_id and not record_already_saved:
        save_access_record_async(
            user_id=user_id,
            device_id=device_id,
            access_type='face_recognition',
            result='granted' if response.get('access_granted') else 'denied',
            detected_object=response.get('detected_object')
        )
    
    return jsonify(response), 200


@yolo_bp.route('/access/records', methods=['GET'])
@login_required
def get_access_records():
    user_id = request.args.get('user_id')
    device_id = request.args.get('device_id')
    
    query = db.session.query(AccessRecord).options(
        joinedload(AccessRecord.user),
        joinedload(AccessRecord.device)
    )
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    if device_id:
        query = query.filter_by(device_id=device_id)
    
    records = query.order_by(AccessRecord.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'records': [record.to_dict() for record in records]
    }), 200


@yolo_bp.route('/access/records/<int:record_id>', methods=['GET'])
@login_required
def get_access_record(record_id):
    record = db.session.query(AccessRecord).options(
        joinedload(AccessRecord.user),
        joinedload(AccessRecord.device)
    ).filter_by(id=record_id).first()
    
    if not record:
        return jsonify({'success': False, 'message': '记录不存在'}), 404
    return jsonify({'success': True, 'record': record.to_dict()}), 200


@yolo_bp.route('/model/status', methods=['GET'])
@login_required
def get_model_status():
    model_loaded = is_model_loaded()
    return jsonify({
        'success': True,
        'model_loaded': model_loaded,
        'message': 'YOLO模型已加载' if model_loaded else 'YOLO模型未加载'
    }), 200


@yolo_bp.route('/face/register', methods=['POST'])
@login_required
def register_face():
    data = request.get_json()
    
    if not data or 'image_data' not in data or 'user_id' not in data:
        return jsonify({
            'success': False,
            'message': '缺少必要参数：image_data 和 user_id'
        }), 400
    
    image_data = data['image_data']
    user_id_raw = data.get('user_id')
    feature_name = data.get('feature_name', 'face')
    
    try:
        user_id = int(user_id_raw)
    except (ValueError, TypeError):
        logger.error(f"user_id类型转换失败: user_id_raw={user_id_raw}, type={type(user_id_raw)}")
        return jsonify({
            'success': False,
            'message': 'user_id格式错误'
        }), 400
    
    logger.info(f"开始人脸注册: user_id={user_id}, feature_name={feature_name}")
    
    image = base64_to_image(image_data)
    if image is None:
        logger.error("图片转换失败")
        return jsonify({
            'success': False,
            'message': '图片格式错误'
        }), 400
    
    image_array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    logger.info(f"图片数组形状: {image_array.shape}")
    
    from face_recognition import detect_faces, align_face, extract_features
    
    faces = detect_faces(image_array)
    logger.info(f"检测到人脸数量: {len(faces)}")
    
    if not faces:
        return jsonify({
            'success': False,
            'message': '图片中未检测到人脸'
        }), 400
    
    aligned = align_face(image_array, faces[0]['landmarks'])
    logger.info(f"对齐后形状: {aligned.shape}")
    
    features = extract_features(aligned)
    logger.info(f"特征形状: {features.shape}, 特征范数: {np.linalg.norm(features)}")
    
    success = add_identity(feature_name, features, user_id)
    
    if success:
        return jsonify({
            'success': True,
            'message': '人脸注册成功',
            'face_count': len(get_registered_faces())
        }), 201
    else:
        return jsonify({
            'success': False,
            'message': '人脸注册失败'
        }), 500


@yolo_bp.route('/face/list', methods=['GET'])
@login_required
def list_faces():
    faces = get_registered_faces()
    return jsonify({
        'success': True,
        'faces': faces,
        'count': len(faces)
    }), 200


@yolo_bp.route('/face/delete/<int:user_id>', methods=['DELETE'])
@login_required
def delete_face(user_id):
    success = delete_identity(user_id)
    if success:
        return jsonify({
            'success': True,
            'message': '人脸特征删除成功'
        }), 200
    else:
        return jsonify({
            'success': False,
            'message': '人脸特征删除失败'
        }), 500


def find_available_camera(max_devices=10):
    """自动扫描可用的视频设备，返回第一个能读取帧的设备索引"""
    backends = [
        (cv2.CAP_ANY, 'CAP_ANY'),
        (cv2.CAP_V4L2, 'CAP_V4L2'),
    ]
    
    logger.info(f"开始扫描视频设备，最大尝试设备数: {max_devices}")
    
    for i in range(max_devices):
        for backend, backend_name in backends:
            try:
                logger.debug(f"尝试打开 /dev/video{i}, 后端: {backend_name}")
                cap = cv2.VideoCapture(i, backend)
                if cap.isOpened():
                    logger.debug(f"/dev/video{i} 打开成功, 开始读取帧")
                    ret, frame = cap.read()
                    if ret and frame is not None and len(frame.shape) == 3 and frame.shape[2] == 3:
                        cap.release()
                        time.sleep(0.1)
                        logger.info(f"找到可用摄像头: /dev/video{i}, 后端: {backend_name}, 帧大小: {frame.shape}")
                        return i, backend
                    else:
                        logger.debug(f"/dev/video{i} 打开成功但读取帧失败: ret={ret}, frame={frame is not None}")
                        cap.release()
                else:
                    logger.debug(f"/dev/video{i} 打开失败, isOpened=False")
            except Exception as e:
                logger.debug(f"/dev/video{i} 后端 {backend_name} 异常: {e}")
                continue
    
    logger.warning("扫描完成，未找到可用的视频设备")
    return None, None


def init_camera():
    global _camera, _camera_running, _camera_ref_count
    
    logger.info(f"init_camera 被调用，当前引用计数: {_camera_ref_count}")
    
    with _camera_ref_lock:
        _camera_ref_count += 1
        logger.info(f"引用计数增加: {_camera_ref_count}")
    
    with _camera_lock:
        if _camera is not None:
            logger.info(f"摄像头已初始化，直接返回")
            with _client_access_lock:
                _last_client_access_time = time.time()
            return True
        
        try:
            logger.info(f"开始查找可用摄像头")
            camera_index, backend = find_available_camera()
            
            if camera_index is None:
                logger.error(f"未找到可用摄像头")
                _camera = None
                with _camera_ref_lock:
                    _camera_ref_count -= 1
                return False
            
            logger.info(f"找到摄像头: /dev/video{camera_index}, 准备打开")
            _camera = cv2.VideoCapture(camera_index, backend)
            
            if not _camera.isOpened():
                logger.error(f"摄像头打开失败: /dev/video{camera_index}")
                _camera = None
                with _camera_ref_lock:
                    _camera_ref_count -= 1
                return False
            
            logger.info(f"摄像头打开成功，设置参数: {CAM_WIDTH}x{CAM_HEIGHT}, {FRAME_RATE}fps")
            _camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
            _camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
            _camera.set(cv2.CAP_PROP_FPS, FRAME_RATE)
            
            _camera_running = True
            with _client_access_lock:
                _last_client_access_time = time.time()
            
            logger.info(f"启动帧捕获线程")
            capture_thread = threading.Thread(target=capture_loop, daemon=True)
            capture_thread.start()
            
            logger.info(f"摄像头初始化成功，设备: /dev/video{camera_index}, 分辨率: {CAM_WIDTH}x{CAM_HEIGHT}, 帧率: {FRAME_RATE}")
            return True
        except Exception as e:
            logger.error(f"摄像头初始化失败: {e}", exc_info=True)
            _camera = None
            with _camera_ref_lock:
                _camera_ref_count -= 1
            return False


def release_camera():
    global _camera, _camera_running, _camera_ref_count
    
    with _camera_ref_lock:
        _camera_ref_count -= 1
        if _camera_ref_count > 0:
            return
    
    with _camera_lock:
        if _camera is not None:
            _camera_running = False
            time.sleep(0.1)
            _camera.release()
            _camera = None
            logger.info("摄像头资源已释放")


def capture_loop():
    global _camera_running, _latest_frame, _frame_counter
    
    logger.info("帧捕获线程已启动")
    
    frame_interval = 1.0 / FRAME_RATE
    last_frame_time = time.time()
    
    with _client_access_lock:
        _last_client_access_time = time.time()
    
    frame_count = 0
    while _camera_running:
        try:
            with _client_access_lock:
                idle_time = time.time() - _last_client_access_time
            if idle_time > CAMERA_IDLE_TIMEOUT:
                logger.info(f"摄像头空闲超时({CAMERA_IDLE_TIMEOUT}秒)，自动关闭")
                release_camera()
                break
            
            now = time.time()
            if now - last_frame_time >= frame_interval:
                ret, frame = _camera.read()
                if ret:
                    frame = cv2.resize(frame, (CAM_WIDTH, CAM_HEIGHT))
                    
                    with _frame_lock:
                        _latest_frame = frame.copy()
                    
                    with _frame_counter_lock:
                        _frame_counter += 1
                    
                    frame_count += 1
                    if frame_count % 30 == 0:
                        logger.info(f"帧捕获线程运行中，已捕获 {frame_count} 帧")
                else:
                    logger.warning(f"摄像头读取失败: ret={ret}")
                
                last_frame_time = now
            
            time.sleep(0.01)
        except Exception as e:
            logger.error(f"摄像头读取失败: {e}", exc_info=True)
            break
    
    logger.info(f"帧捕获线程退出，共捕获 {frame_count} 帧")


@yolo_bp.route('/video_feed', methods=['GET'])
def video_feed():
    token = request.args.get('token')
    if token:
        from app import decode_token, token_user_cache, cache_lock
        
        with cache_lock:
            cached = token_user_cache.get(token)
            if cached and cached['expires'] > time.time():
                g.user_id = cached['user_id']
                g.username = cached['username']
                g.role = cached['role']
                g.token_valid = True
            else:
                payload = decode_token(token)
                if payload:
                    from models import User, db
                    user_id = payload.get('user_id')
                    user = db.session.get(User, user_id)
                    if user and user.session_token == token:
                        g.user_id = user_id
                        g.username = payload.get('username')
                        g.role = user.role
                        g.token_valid = True
    
    if not hasattr(g, 'token_valid') or not g.token_valid:
        return jsonify({'success': False, 'message': '未授权访问'}), 401
    
    if not init_camera():
        return jsonify({'success': False, 'message': '无法打开摄像头'}), 500
    
    def generate():
        global _latest_frame
        
        logger.info("视频流生成器已启动")
        
        frame_interval = 1.0 / FRAME_RATE
        last_frame_time = time.time()
        
        frame_count = 0
        try:
            while True:
                now = time.time()
                if now - last_frame_time >= frame_interval:
                    with _client_access_lock:
                        _last_client_access_time = time.time()
                    
                    with _frame_lock:
                        frame = _latest_frame
                    if frame is None:
                        logger.debug("视频流：_latest_frame 为 None")
                        time.sleep(0.05)
                        continue
                    
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    if not ret:
                        logger.debug("视频流：JPEG编码失败")
                        time.sleep(0.01)
                        continue
                    
                    frame_count += 1
                    if frame_count % 30 == 0:
                        logger.info(f"视频流已发送 {frame_count} 帧")
                    
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                    last_frame_time = now
                else:
                    time.sleep(0.01)
        except GeneratorExit:
            logger.info(f"视频流客户端已断开连接，共发送 {frame_count} 帧")
            release_camera()
        except Exception as e:
            logger.error(f"视频流生成器异常: {e}", exc_info=True)
    
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@yolo_bp.route('/detect/image', methods=['POST'])
@login_required
def detect_image_upload():
    if 'image' not in request.files:
        return jsonify({
            'success': False,
            'message': '缺少图片文件'
        }), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({
            'success': False,
            'message': '未选择图片'
        }), 400
    
    try:
        image_bytes = file.read()
        image_array = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        
        if image_array is None:
            return jsonify({
                'success': False,
                'message': '无法解码图片'
            }), 400
        
        confidence = float(request.form.get('confidence', 0.01))
        user_id = request.form.get('user_id')
        device_id = request.form.get('device_id')
        
        result = detect_objects(image_array=image_array, conf=confidence)
        
        if not result['success']:
            return jsonify({
                'success': False,
                'message': result['message']
            }), 500
        
        detection_result = result
        h, w = image_array.shape[:2]
        response = {
            'success': True,
            'message': '检测成功',
            'detection_result': detection_result,
            'image_size': {
                'original': {'width': w, 'height': h}
            }
        }
        
        process_detection_result(response, result, image_array, confidence, user_id, device_id)
        
        ret, buffer = cv2.imencode('.jpg', image_array)
        if ret:
            image_bytes = buffer.tobytes()
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            response['image_data'] = f'data:image/jpeg;base64,{image_base64}'
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"图片上传检测失败: {e}")
        return jsonify({
            'success': False,
            'message': '检测失败，请稍后重试'
        }), 500


@yolo_bp.route('/capture', methods=['POST'])
@login_required
def capture_and_detect():
    data = request.get_json() or {}
    
    confidence = data.get('confidence', 0.01)
    user_id = data.get('user_id')
    device_id = data.get('device_id')
    
    if not init_camera():
        return jsonify({'success': False, 'message': '无法打开摄像头'}), 500
    
    with _frame_lock:
        frame = _latest_frame
    if frame is None:
        release_camera()
        return jsonify({'success': False, 'message': '无法获取摄像头帧'}), 500
    
    with _frame_counter_lock:
        current_frame = _frame_counter
    
    new_detections = []
    detection_result = None
    
    result = detect_objects(image_array=frame, conf=confidence)
    
    if not result['success']:
        release_camera()
        return jsonify({
            'success': False,
            'message': result['message']
        }), 500
    
    for i, obj in enumerate(result['objects']):
        det = {
            'type': obj,
            'bbox': result['bounding_boxes'][i],
            'confidence': result['confidence_scores'][i]
        }
        
        if is_person_class(obj):
            head_resized = crop_head_region(frame, det['bbox'])
            if head_resized is not None:
                face_info, identity, similarity, user_id = process_roi(head_resized)
                det['identity'] = identity
    
        new_detections.append(det)
    
    update_tracks(new_detections)
    detection_result = result
    
    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ret:
        release_camera()
        return jsonify({'success': False, 'message': '图像编码失败'}), 500
    
    image_bytes = buffer.tobytes()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    response = {
        'success': True,
        'message': '检测成功',
        'image_data': f'data:image/jpeg;base64,{image_base64}',
        'detection_result': detection_result,
        'frame_number': current_frame,
        'is_detection_frame': True
    }
    
    process_detection_result(response, detection_result, frame, confidence, user_id, device_id)
    
    return jsonify(response), 200




