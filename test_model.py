import onnx
model = onnx.load("/home/HwHiAiUser/software/Smartliving/backend/YOLO/best.onnx")
# 遍历模型内置元数据
for prop in model.metadata_props:
    print(f"{prop.key}: {prop.value}")