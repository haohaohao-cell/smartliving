"""
人脸识别模块
=====================================
提供人脸检测、特征提取和相似度检索功能

功能：
- YuNet人脸检测（输入160x160）
- MobileFaceNet特征提取（112x112标准正脸图）
- Faiss相似度检索（阈值0.70）
- 人脸特征数据库持久化

模型：
- face_detection_yunet_2023mar.onnx - YuNet人脸检测
- mobilefacenet.onnx - MobileFaceNet特征提取

性能优化：
- 模型单例加载
- 特征向量预加载到内存
- Faiss索引加速检索
"""

import os
import cv2
import numpy as np
import faiss
import onnxruntime
import logging
import pickle
import threading

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'YOLO')

_yunet_detector = None
_mobilefacenet_session = None
_faiss_index = None
_identity_names = []
_features = []
_user_ids = []
_faiss_lock = threading.Lock()

YUNET_CONF_THRESHOLD = 0.70
YUNET_NMS_THRESHOLD = 0.3
YUNET_TOP_K = 5000

EYE_DISTANCE_THRESHOLD = 20
YAW_THRESHOLD = 40
PITCH_THRESHOLD = 30

FAISS_THRESHOLD = 0.70

TARGET_WIDTH = 160
TARGET_HEIGHT = 160
FACE_STANDARD_SIZE = 112


def load_yunet_detector():
    global _yunet_detector
    if _yunet_detector is not None:
        return _yunet_detector
    
    model_path = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")
    
    if not os.path.exists(model_path):
        logger.error(f"YuNet模型文件不存在: {model_path}")
        return None

    try:
        _yunet_detector = cv2.FaceDetectorYN.create(
            model_path,
            "",
            (TARGET_WIDTH, TARGET_HEIGHT),
            YUNET_CONF_THRESHOLD,
            YUNET_NMS_THRESHOLD,
            YUNET_TOP_K
        )
        logger.info("YuNet人脸检测器加载成功")
        return _yunet_detector
    except Exception as e:
        logger.error(f"YuNet人脸检测器加载失败: {e}")
        return None


def load_mobilefacenet():
    global _mobilefacenet_session
    if _mobilefacenet_session is not None:
        return _mobilefacenet_session
    
    model_path = os.path.join(MODEL_DIR, "mobilefacenet.onnx")
    
    if not os.path.exists(model_path):
        logger.error(f"MobileFaceNet模型文件不存在: {model_path}")
        return None
    
    try:
        _mobilefacenet_session = onnxruntime.InferenceSession(
            model_path,
            providers=['CPUExecutionProvider']
        )
        logger.info(f"MobileFaceNet 加载成功: {model_path}")
        return _mobilefacenet_session
    except Exception as e:
        logger.error(f"MobileFaceNet 加载失败: {e}")
        return None


def init_faiss_index():
    global _faiss_index
    if _faiss_index is not None:
        return _faiss_index
    
    try:
        _faiss_index = faiss.IndexFlatL2(128)
        logger.info("Faiss索引初始化成功 (128维)")
        return _faiss_index
    except Exception as e:
        logger.error(f"Faiss索引初始化失败: {e}")
        return None


def load_features_from_db():
    """从数据库加载已注册的人脸特征到内存"""
    global _features, _identity_names, _user_ids
    
    try:
        from models import FaceFeature, db
        
        features = FaceFeature.query.all()
        
        _features = []
        _identity_names = []
        _user_ids = []
        
        for feat in features:
            feature = np.frombuffer(feat.feature_data, dtype=np.float32)
            _features.append(feature)
            _identity_names.append(feat.feature_name or 'Unknown')
            _user_ids.append(feat.user_id)
        
        if _features:
            index = init_faiss_index()
            if index is not None:
                features_np = np.array(_features, dtype=np.float32)
                index.add(features_np)
                logger.info(f"已从数据库加载 {len(_features)} 个人脸特征")
            else:
                logger.error("Faiss索引初始化失败，无法加载特征")
        else:
            logger.info("数据库中暂无已注册的人脸特征")
            
    except Exception as e:
        logger.error(f"从数据库加载特征失败: {e}")


def detect_faces(image):
    detector = load_yunet_detector()
    if detector is None:
        return []
    
    h, w = image.shape[:2]
    if w != TARGET_WIDTH or h != TARGET_HEIGHT:
        image = cv2.resize(image, (TARGET_WIDTH, TARGET_HEIGHT))
    
    detector.setInputSize((TARGET_WIDTH, TARGET_HEIGHT))
    
    try:
        _, faces = detector.detect(image)
        if faces is None:
            return []
        
        results = []
        for face in faces:
            confidence = float(face[14])
            if confidence < YUNET_CONF_THRESHOLD:
                continue
            
            bbox = face[:4].astype(int)
            landmarks = face[4:14].reshape(5, 2).astype(int)
            
            left_eye = landmarks[0]
            right_eye = landmarks[1]
            
            eye_distance = np.linalg.norm(left_eye - right_eye)
            
            yaw = float(face[15]) if len(face) > 15 else 0
            pitch = float(face[16]) if len(face) > 16 else 0
            
            if eye_distance < EYE_DISTANCE_THRESHOLD:
                continue
            
            if abs(yaw) > YAW_THRESHOLD or abs(pitch) > PITCH_THRESHOLD:
                continue
            
            results.append({
                'bbox': bbox,
                'landmarks': landmarks,
                'confidence': confidence,
                'yaw': yaw,
                'pitch': pitch
            })
        
        return results
    except Exception as e:
        logger.error(f"人脸检测失败: {e}")
        return []


def align_face(image, landmarks):
    left_eye = landmarks[0].astype(np.float32)
    right_eye = landmarks[1].astype(np.float32)
    nose = landmarks[2].astype(np.float32)
    
    std_left_eye = np.float32([30.0, 35.0])
    std_right_eye = np.float32([82.0, 35.0])
    std_nose = np.float32([56.0, 55.0])
    
    src_pts = np.float32([left_eye, right_eye, nose])
    dst_pts = np.float32([std_left_eye, std_right_eye, std_nose])
    
    M = cv2.getAffineTransform(src_pts, dst_pts)
    aligned = cv2.warpAffine(image, M, (FACE_STANDARD_SIZE, FACE_STANDARD_SIZE))
    return aligned


def extract_features(image):
    session = load_mobilefacenet()
    if session is None:
        return np.zeros(128)
    
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    normalized = (rgb.astype(np.float32) / 127.5) - 1.0
    input_tensor = np.transpose(normalized, (2, 0, 1))
    input_tensor = np.expand_dims(input_tensor, axis=0)
    
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    result = session.run([output_name], {input_name: input_tensor})
    
    embedding = result[0].flatten()
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    return embedding


def add_identity(name, feature, user_id=None):
    global _features, _identity_names, _user_ids
    
    db = None
    try:
        logger.info(f"添加身份: name={name}, user_id={user_id}, feature_shape={feature.shape if hasattr(feature, 'shape') else 'unknown'}, feature_dtype={feature.dtype if hasattr(feature, 'dtype') else 'unknown'}")
        
        if user_id is not None:
            logger.info(f"开始保存到数据库: user_id={user_id}")
            from models import FaceFeature, db as db_instance
            db = db_instance
            feature_bytes = feature.tobytes()
            logger.info(f"特征字节长度: {len(feature_bytes)}")
            face_feature = FaceFeature(
                user_id=user_id,
                feature_data=feature_bytes,
                feature_name=name
            )
            db.session.add(face_feature)
            db.session.commit()
        
        with _faiss_lock:
            _features.append(feature)
            _identity_names.append(name)
            _user_ids.append(user_id)
            
            if _faiss_index is None:
                _faiss_index = faiss.IndexFlatL2(128)
            
            feature_np = np.array([feature], dtype=np.float32)
            _faiss_index.add(feature_np)
        
        logger.info(f"已添加身份: {name}" + (f" (user_id: {user_id})" if user_id else ""))
        return True
    except Exception as e:
        logger.error(f"添加身份失败: type={type(e).__name__}, str={str(e)}")
        import traceback
        logger.error(f"堆栈跟踪: {traceback.format_exc()}")
        if db is not None:
            try:
                db.session.rollback()
            except Exception as rollback_e:
                logger.error(f"回滚失败: {rollback_e}")
        return False


def search_identity(feature):
    with _faiss_lock:
        index = _faiss_index
        if index is None or index.ntotal == 0:
            return 'Unknown', 0.0, None
        
        try:
            feature_np = np.array([feature], dtype=np.float32)
            distances, indices = index.search(feature_np, 1)
            
            if len(indices) > 0 and len(indices[0]) > 0:
                idx = indices[0][0]
                l2_distance = distances[0][0]
                
                similarity = 1.0 / (1.0 + l2_distance)
                
                if similarity >= FAISS_THRESHOLD and idx < len(_identity_names):
                    user_id = _user_ids[idx] if idx < len(_user_ids) else None
                    return _identity_names[idx], similarity, user_id
            
            return 'Unknown', 0.0, None
        except Exception as e:
            logger.error(f"身份检索失败: {e}")
            return 'Unknown', 0.0, None


def recognize_face(image):
    faces = detect_faces(image)
    if not faces:
        return None, 'Unknown', 0.0, None
    best_face = faces[0]
    aligned = align_face(image, best_face['landmarks'])
    features = extract_features(aligned)
    identity, similarity, user_id = search_identity(features)
    return best_face, identity, similarity, user_id


def process_roi(roi_image):
    faces = detect_faces(roi_image)
    if not faces:
        return None, 'Unknown', 0.0, None
    best_face = faces[0]
    aligned = align_face(roi_image, best_face['landmarks'])
    features = extract_features(aligned)
    identity, similarity, user_id = search_identity(features)
    return best_face, identity, similarity, user_id


def delete_identity(user_id):
    """删除指定用户的人脸特征"""
    global _features, _identity_names, _user_ids, _faiss_index
    
    try:
        from models import FaceFeature, db
        
        FaceFeature.query.filter_by(user_id=user_id).delete()
        db.session.commit()
        
        mask = np.array(_user_ids) != user_id
        new_features = [_features[i] for i in range(len(_features)) if mask[i]]
        new_identity_names = [_identity_names[i] for i in range(len(_identity_names)) if mask[i]]
        new_user_ids = [_user_ids[i] for i in range(len(_user_ids)) if mask[i]]
        
        with _faiss_lock:
            _features = new_features
            _identity_names = new_identity_names
            _user_ids = new_user_ids
            
            new_index = faiss.IndexFlatL2(128)
            if _features:
                features_np = np.array(_features, dtype=np.float32)
                new_index.add(features_np)
            _faiss_index = new_index
        
        logger.info(f"已删除用户 {user_id} 的人脸特征")
        return True
    except Exception as e:
        logger.error(f"删除身份失败: {e}")
        db.session.rollback()
        return False


def get_registered_faces():
    """获取已注册的人脸列表"""
    try:
        from models import FaceFeature, User, db
        
        features = FaceFeature.query.join(User).all()
        result = []
        for feat in features:
            result.append({
                'id': feat.id,
                'user_id': feat.user_id,
                'username': feat.user.username if feat.user else None,
                'name': feat.user.name if feat.user else None,
                'feature_name': feat.feature_name,
                'created_at': feat.created_at.strftime('%Y-%m-%d %H:%M:%S') if feat.created_at else None
            })
        return result
    except Exception as e:
        logger.error(f"获取已注册人脸列表失败: {e}")
        return []


def preload_identity(name, image_path):
    if not os.path.exists(image_path):
        logger.error(f"图片不存在: {image_path}")
        return False
    image = cv2.imread(image_path)
    if image is None:
        logger.error(f"无法读取图片: {image_path}")
        return False
    h, w = image.shape[:2]
    if w != TARGET_WIDTH or h != TARGET_HEIGHT:
        image = cv2.resize(image, (TARGET_WIDTH, TARGET_HEIGHT))
    faces = detect_faces(image)
    if not faces:
        logger.error(f"图片中未检测到人脸: {image_path}")
        return False
    aligned = align_face(image, faces[0]['landmarks'])
    features = extract_features(aligned)
    return add_identity(name, features)