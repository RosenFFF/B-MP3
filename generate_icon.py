"""生成「光影工坊」的高分辨率应用图标 (icon.ico 和 icon.png)。
采用 4x 超采样抗锯齿渲染，包含多种分辨率规格。
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def create_lumina_icon(size: int = 1024) -> Image.Image:
    scale = 4
    canvas_size = size * scale
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = int(canvas_size * 0.08)
    radius = int(canvas_size * 0.22)
    box = [margin, margin, canvas_size - margin, canvas_size - margin]

    # 1. 绘制带有柔和外发光的底层
    # 基础圆角矩形遮罩
    mask = Image.new("L", (canvas_size, canvas_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(box, radius=radius, fill=255)

    # 背景渐变：从深墨绿灰 (#191D17) 到深曜石黑 (#111310)
    bg = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    for y in range(margin, canvas_size - margin):
        t = (y - margin) / (canvas_size - 2 * margin)
        # 渐变过渡: (26, 31, 24) -> (15, 17, 14)
        r = int(28 * (1 - t) + 14 * t)
        g = int(34 * (1 - t) + 17 * t)
        b = int(28 * (1 - t) + 14 * t)
        bg_draw.line([(margin, y), (canvas_size - margin, y)], fill=(r, g, b, 255))
    
    # 复合遮罩
    base_plate = Image.composite(bg, Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0)), mask)

    # 2. 边框质感与内发光 (高雅的金铜/流光边缘)
    border_img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_img)
    border_draw.rounded_rectangle(box, radius=radius, outline=(224, 160, 74, 120), width=int(8 * scale))
    # 顶部微弱高光
    inner_box = [margin + int(4 * scale), margin + int(4 * scale), canvas_size - margin - int(4 * scale), canvas_size - margin - int(4 * scale)]
    border_draw.rounded_rectangle(inner_box, radius=radius - int(4 * scale), outline=(245, 230, 200, 40), width=int(3 * scale))

    base_plate = Image.alpha_composite(base_plate, border_img)

    # 3. 绘制中心主题徽标：「光影流转」—— 胶片/光环与转码三角形组合
    # 中心坐标
    cx, cy = canvas_size // 2, canvas_size // 2
    
    # 背景微光（光晕）
    glow = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_radius = int(canvas_size * 0.32)
    glow_draw.ellipse(
        [cx - glow_radius, cy - glow_radius, cx + glow_radius, cy + glow_radius],
        fill=(224, 160, 74, 45)
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=int(60 * scale)))
    base_plate = Image.alpha_composite(base_plate, glow)

    # 动态圆环与转换流光 (双色弧光：琥珀金 -> 鼠尾草绿)
    ring_img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    ring_draw = ImageDraw.Draw(ring_img)
    
    r_outer = int(canvas_size * 0.28)
    r_inner = int(canvas_size * 0.23)
    ring_width = r_outer - r_inner

    # 绘制外层旋光胶片弧线（代表视频流与转码）
    # 琥珀金主弧 (角度 -30 到 150)
    ring_box = [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer]
    ring_draw.arc(ring_box, start=-40, end=140, fill=(240, 175, 78, 240), width=ring_width)
    # 鼠尾草绿副弧 (角度 140 到 320)
    ring_draw.arc(ring_box, start=140, end=320, fill=(138, 185, 134, 240), width=ring_width)

    # 胶片刻度小孔 (四颗流光刻度点，象征帧和镜头)
    for angle in [-20, 20, 60, 100, 160, 200, 240, 280]:
        rad = math.radians(angle)
        mid_r = (r_outer + r_inner) / 2
        px = cx + mid_r * math.cos(rad)
        py = cy + mid_r * math.sin(rad)
        dot_r = int(2.5 * scale)
        ring_draw.ellipse([px - dot_r, py - dot_r, px + dot_r, py + dot_r], fill=(20, 24, 19, 230))

    base_plate = Image.alpha_composite(base_plate, ring_img)

    # 4. 核心符号：流光渐变立体播放/转换箭头（三角形）
    arrow_img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    arrow_draw = ImageDraw.Draw(arrow_img)

    # 三角形顶点坐标（稍微居中调整）
    tri_len = int(canvas_size * 0.17)
    x_offset = int(canvas_size * 0.02)  # 播放键视觉中心稍往右
    p1 = (cx + int(tri_len * 1.05) + x_offset, cy)
    p2 = (cx - int(tri_len * 0.65) + x_offset, cy - int(tri_len * 0.95))
    p3 = (cx - int(tri_len * 0.65) + x_offset, cy + int(tri_len * 0.95))

    # 渐变多边形填充：通过遮罩
    tri_mask = Image.new("L", (canvas_size, canvas_size), 0)
    tri_mask_draw = ImageDraw.Draw(tri_mask)
    tri_mask_draw.polygon([p1, p2, p3], fill=255)

    tri_grad = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    tri_grad_draw = ImageDraw.Draw(tri_grad)
    for x in range(int(p2[0]), int(p1[0]) + 1):
        progress = (x - p2[0]) / (p1[0] - p2[0] + 1e-5)
        # 从纯净象牙白金到温润流光金
        gr = int(255 * (1 - progress) + 245 * progress)
        gg = int(250 * (1 - progress) + 195 * progress)
        gb = int(235 * (1 - progress) + 105 * progress)
        tri_grad_draw.line([(x, 0), (x, canvas_size)], fill=(gr, gg, gb, 255))
    
    tri_final = Image.composite(tri_grad, Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0)), tri_mask)
    
    # 微弱阴影让三角形浮起
    tri_shadow = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    tri_shadow_draw = ImageDraw.Draw(tri_shadow)
    sp1 = (p1[0] + int(4 * scale), p1[1] + int(8 * scale))
    sp2 = (p2[0] + int(4 * scale), p2[1] + int(8 * scale))
    sp3 = (p3[0] + int(4 * scale), p3[1] + int(8 * scale))
    tri_shadow_draw.polygon([sp1, sp2, sp3], fill=(10, 12, 10, 140))
    tri_shadow = tri_shadow.filter(ImageFilter.GaussianBlur(radius=int(12 * scale)))

    base_plate = Image.alpha_composite(base_plate, tri_shadow)
    base_plate = Image.alpha_composite(base_plate, tri_final)

    # 5. 转换环绕弧箭头（象征 Format Conversion）
    arrow_arc = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    arrow_arc_draw = ImageDraw.Draw(arrow_arc)
    
    # 顶部右侧转换箭头头标
    tip_angle = math.radians(140)
    tip_cx = cx + r_outer * math.cos(tip_angle)
    tip_cy = cy + r_outer * math.sin(tip_angle)
    # 画一个小三角箭头
    arrow_tip = [
        (tip_cx + int(12 * scale), tip_cy - int(16 * scale)),
        (tip_cx - int(10 * scale), tip_cy - int(6 * scale)),
        (tip_cx + int(6 * scale), tip_cy + int(14 * scale)),
    ]
    arrow_arc_draw.polygon(arrow_tip, fill=(143, 196, 138, 255))

    # 底部左侧对应箭头
    tip2_angle = math.radians(320)
    tip2_cx = cx + r_outer * math.cos(tip2_angle)
    tip2_cy = cy + r_outer * math.sin(tip2_angle)
    arrow_tip2 = [
        (tip2_cx - int(12 * scale), tip2_cy + int(16 * scale)),
        (tip2_cx + int(10 * scale), tip2_cy + int(6 * scale)),
        (tip2_cx - int(6 * scale), tip2_cy - int(14 * scale)),
    ]
    arrow_arc_draw.polygon(arrow_tip2, fill=(240, 175, 78, 255))

    base_plate = Image.alpha_composite(base_plate, arrow_arc)

    # 6. 超采样降采样到目标尺寸
    final_img = base_plate.resize((size, size), Image.Resampling.LANCZOS)
    return final_img


def build_icons(target_dir: Path) -> tuple[Path, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    icon_png = target_dir / "icon.png"
    icon_ico = target_dir / "icon.ico"

    img_1024 = create_lumina_icon(1024)
    img_512 = img_1024.resize((512, 512), Image.Resampling.LANCZOS)
    img_512.save(icon_png, format="PNG")

    # 生成包含多分辨率的 Windows .ico
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    ico_images = [img_1024.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    ico_images[0].save(icon_ico, format="ICO", sizes=sizes, append_images=ico_images[1:])

    return icon_png, icon_ico


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent / "resources"
    p_png, p_ico = build_icons(out_dir)
    print(f"Generated: {p_png} and {p_ico}")
