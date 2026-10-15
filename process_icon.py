from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

source_path = Path(r"C:\Users\LENOVO\.gemini\antigravity\brain\933278fd-aa82-42b8-b884-07ffcaee7d0e\luminastudio_app_icon_1792029591686.jpg")
target_dir = Path(__file__).resolve().parent / "resources"
target_dir.mkdir(parents=True, exist_ok=True)

img = Image.open(source_path).convert("RGBA")

# 裁剪并放大略微边距
# 原始 Squircle 范围大约是 [150, 150, 874, 874]，留出柔和边缘与高光阴影
crop_box = (130, 130, 894, 894)
cropped = img.crop(crop_box)
w, h = cropped.size

# 构造平滑的圆角矩形遮罩，过滤掉外部纯黑背景
scale = 4
mask = Image.new("L", (w * scale, h * scale), 0)
mask_draw = ImageDraw.Draw(mask)
# 边距留约 20 * scale，圆角约 165 * scale
m = 20 * scale
r = 165 * scale
mask_draw.rounded_rectangle([m, m, w * scale - m, h * scale - m], radius=r, fill=255)
mask = mask.resize((w, h), Image.Resampling.LANCZOS)

# 创建透明画布，应用遮罩
final_icon = Image.new("RGBA", (w, h), (0, 0, 0, 0))
final_icon.paste(cropped, (0, 0), mask)

# 调整到标准 512x512
icon_512 = final_icon.resize((512, 512), Image.Resampling.LANCZOS)
icon_png_path = target_dir / "icon.png"
icon_ico_path = target_dir / "icon.ico"

icon_512.save(icon_png_path, format="PNG")

# 生成多尺寸 Windows .ico
sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
ico_imgs = [icon_512.resize(s, Image.Resampling.LANCZOS) for s in sizes]
ico_imgs[0].save(icon_ico_path, format="ICO", sizes=sizes, append_images=ico_imgs[1:])

print(f"Generated {icon_png_path} and {icon_ico_path}")
