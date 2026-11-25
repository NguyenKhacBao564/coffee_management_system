import cv2

from .geometry import clip_box


def vehicle_crop(image, box):
    x1, y1, x2, y2 = clip_box(box, image.shape)
    crop = image[y1:y2, x1:x2]
    return crop, (x1, y1)


def frame_quality(image, box):
    crop, _ = vehicle_crop(image, box)
    if not crop.size:
        return 0.0
    sharpness = cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
    return float(sharpness * (crop.shape[0] * crop.shape[1]) ** 0.5)


def plate_crop(image, detection):
    # Preserve real pixels and dimensions; no generative enhancement or invented text.
    return vehicle_crop(image, detection.box)[0]
