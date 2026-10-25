"""
YOLO模型加载模块
=====================================
负责加载和管理YOLO模型，提供检测接口

模型文件: YOLO/best.onnx

性能优化：
- 模型单例加载，文件存在性仅检查一次
- 检测循环优化，提前取出name_map避免重复属性访问
- 线程池优雅关闭，通过atexit注册回调
- YOLO在320x320小图上推理，坐标映射回640x480
"""

import os
import atexit
import concurrent.futures
import logging
import cv2
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

_model = None
_model_loaded = False
_model_path = os.path.join(os.path.dirname(__file__), 'YOLO', 'best.onnx')
_model_path_check = False

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='yolo-worker')

INPUT_WIDTH = 320
INPUT_HEIGHT = 320
ORIG_WIDTH = 640
ORIG_HEIGHT = 480
CONF_THRESHOLD = 0.01


def load_model():
    global _model, _model_loaded, _model_path_check

    if _model_loaded and _model is not None:
        return _model

    if not _model_path_check:
        if not os.path.exists(_model_path):
            logger.warning(f"模型文件不存在: {_model_path}")
            _model_path_check = True
            return None
        _model_path_check = True

    try:
        logger.info(f"正在加载YOLO模型: {_model_path}")
        _model = YOLO(_model_path)
        _model_loaded = True
        logger.info("YOLO模型加载成功")
        return _model
    except Exception as e:
        logger.error(f"YOLO模型加载失败: {e}")
        return None


def is_model_loaded():
    return _model_loaded


def preprocess_image(image_array):
    """预处理图像：缩放至320x240，再填充黑边至320x320"""
    h, w = image_array.shape[:2]
    
    scale = INPUT_WIDTH / w
    scaled_h = int(h * scale)
    
    resized = cv2.resize(image_array, (INPUT_WIDTH, scaled_h), interpolation=cv2.INTER_LINEAR)
    
    pad_top = (INPUT_HEIGHT - scaled_h) // 2
    pad_bottom = INPUT_HEIGHT - scaled_h - pad_top
    
    padded = cv2.copyMakeBorder(resized, pad_top, pad_bottom, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])
    
    return padded, scale, pad_top


def postprocess_boxes(boxes, scale, pad_top):
    """后处理边界框：映射回640x480坐标系"""
    processed_boxes = []
    for box in boxes:
        x1, y1, x2, y2 = box[:4]
        
        y1 = (y1 - pad_top) / scale
        y2 = (y2 - pad_top) / scale
        x1 = x1 / scale
        x2 = x2 / scale
        
        x1 = max(0, min(x1, ORIG_WIDTH))
        y1 = max(0, min(y1, ORIG_HEIGHT))
        x2 = max(0, min(x2, ORIG_WIDTH))
        y2 = max(0, min(y2, ORIG_HEIGHT))
        
        processed_boxes.append([x1, y1, x2, y2])
    
    return processed_boxes


def detect_objects(image_path=None, image_bytes=None, image_array=None, conf=CONF_THRESHOLD):
    model = load_model()
    if model is None:
        logger.error("YOLO模型加载失败")
        return {
            'success': False,
            'message': 'YOLO模型加载失败'
        }

    try:
        if image_path:
            image_array = cv2.imread(image_path)
            if image_array is None:
                logger.error(f"无法读取图片: {image_path}")
                return {'success': False, 'message': '无法读取图片'}
        elif image_bytes:
            image_array = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
            if image_array is None:
                logger.error("无法解码图片字节数据")
                return {'success': False, 'message': '无法解码图片'}
        elif image_array is None:
            logger.error("未提供图片数据")
            return {'success': False, 'message': '请提供图片数据'}

        original_shape = image_array.shape
        logger.debug(f"输入图像形状: {original_shape}")

        if len(image_array.shape) == 2:
            image_array = cv2.cvtColor(image_array, cv2.COLOR_GRAY2BGR)
            logger.debug("已将灰度图像转换为彩色")

        logger.info(f"开始YOLO推理，置信度阈值: {conf}")
        results = model(image_array, conf=conf)
        logger.info(f"YOLO推理完成")

        detected_objects = []
        confidence_scores = []
        bounding_boxes = []

        name_map = results[0].names if results else {}
        logger.info(f"模型类别映射: {name_map}")

        total_boxes = 0
        for result in results:
            for box in result.boxes:
                total_boxes += 1
                class_id = int(box.cls[0])
                class_name = name_map.get(class_id, str(class_id))
                confidence = float(box.conf[0])
                
                logger.info(f"检测到物体: class_id={class_id}, class_name={class_name}, confidence={confidence:.4f}, bbox={box.xyxy[0].tolist()}")
                
                if confidence >= conf:
                    bbox = box.xyxy[0].tolist()
                    detected_objects.append(class_name)
                    confidence_scores.append(confidence)
                    bounding_boxes.append(bbox)
                    logger.info(f"✅ 物体 {class_name} 通过过滤，置信度 {confidence:.4f} >= 阈值 {conf}")
                else:
                    logger.info(f"❌ 物体 {class_name} 置信度 {confidence:.4f} 低于阈值 {conf}，已过滤")

        logger.info(f"检测结果: 总计{total_boxes}个框，过滤后{len(detected_objects)}个有效物体")
        logger.info(f"检测到的物体: {detected_objects}")
        logger.info(f"置信度分数: {confidence_scores}")

        formatted_boxes = []
        for bbox in bounding_boxes:
            formatted_boxes.append({
                'x1': bbox[0],
                'y1': bbox[1],
                'x2': bbox[2],
                'y2': bbox[3]
            })

        return {
            'success': True,
            'objects': detected_objects,
            'confidence_scores': confidence_scores,
            'bounding_boxes': formatted_boxes
        }

    except Exception as e:
        logger.error(f"检测失败: {e}", exc_info=True)
        return {
            'success': False,
            'message': f'检测失败: {e}'
        }


def detect_objects_async(image_path=None, image_bytes=None, image_array=None, conf=CONF_THRESHOLD):
    return _executor.submit(
        detect_objects,
        image_path=image_path,
        image_bytes=image_bytes,
        image_array=image_array,
        conf=conf
    )


def shutdown_executor(wait=True):
    _executor.shutdown(wait=wait)
    logger.info("YOLO线程池已关闭")


atexit.register(shutdown_executor, wait=False)