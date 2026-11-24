"""
OCR Module for Screenrecord Manager
High-performance on-device OCR using native Apple Vision framework (Vision.framework) via PyObjC.
Ultra-fast on Apple Silicon Neural Engine with zero external binary dependencies.
"""

import io
import logging
from typing import List, Dict, Any, Tuple
from PIL import Image

logger = logging.getLogger(__name__)

VISION_AVAILABLE = False
try:
    import objc
    import Vision
    from Foundation import NSData, NSDictionary
    import Quartz
    VISION_AVAILABLE = True
except ImportError:
    logger.warning("Apple Vision framework via PyObjC not yet imported or not available.")


class AppleVisionOCR:
    def __init__(self, recognition_level: str = "accurate"):
        """
        :param recognition_level: 'accurate' (default) or 'fast'
        """
        self.recognition_level = recognition_level
        self.is_ready = False
        self._check_and_init()

    def _check_and_init(self):
        global VISION_AVAILABLE
        if not VISION_AVAILABLE:
            try:
                import objc
                import Vision
                from Foundation import NSData, NSDictionary
                import Quartz
                VISION_AVAILABLE = True
            except ImportError:
                VISION_AVAILABLE = False
        self.is_ready = VISION_AVAILABLE

    def recognize_image(self, pil_image: Image.Image) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Extract text and bounding boxes from a PIL image using Apple Vision.
        Returns:
            full_text (str): Joined multi-line text detected.
            boxes (list of dict): Each dict has:
                - text: recognized line/word
                - confidence: float (0.0 to 1.0)
                - box: [x, y, w, h] normalized (0.0 to 1.0) with TOP-LEFT origin
        """
        if not self.is_ready:
            self._check_and_init()
            if not self.is_ready:
                return self._fallback_recognize(pil_image)

        try:
            # Convert PIL image to PNG bytes (compress_level=1 is lossless & ~5-8x faster than default)
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG", compress_level=1)
            png_bytes = buf.getvalue()

            # Create CGImage via Quartz CGDataProvider
            provider = Quartz.CGDataProviderCreateWithData(None, png_bytes, len(png_bytes), None)
            cg_image = Quartz.CGImageCreateWithPNGDataProvider(
                provider, None, False, Quartz.kCGRenderingIntentDefault
            )

            if not cg_image:
                logger.warning("Failed to create CGImage from image bytes.")
                return self._fallback_recognize(pil_image)

            # Initialize Vision Request Handler with CGImage
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
                cg_image, NSDictionary.dictionary()
            )

            # Configure text recognition request
            request = Vision.VNRecognizeTextRequest.alloc().init()
            if self.recognition_level == "fast":
                request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelFast)
            else:
                request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)

            request.setUsesLanguageCorrection_(True)

            # Perform OCR request
            success, error = handler.performRequests_error_([request], None)
            if not success or error:
                logger.debug(f"Apple Vision performRequests note: {error}")
                return self._fallback_recognize(pil_image)

            results = request.results()
            if not results:
                return "", []

            lines = []
            boxes = []

            for observation in results:
                candidates = observation.topCandidates_(1)
                if not candidates:
                    continue
                cand = candidates[0]
                text = cand.string()
                conf = float(cand.confidence())
                lines.append(text)

                # Apple Vision uses normalized bottom-left origin coordinates.
                # Convert to standard top-left origin for UI rendering:
                # x = bbox.origin.x
                # y = 1.0 - (bbox.origin.y + bbox.size.height)
                # w = bbox.size.width
                # h = bbox.size.height
                bbox = observation.boundingBox()
                norm_x = float(bbox.origin.x)
                norm_y = float(1.0 - (bbox.origin.y + bbox.size.height))
                norm_w = float(bbox.size.width)
                norm_h = float(bbox.size.height)

                boxes.append({
                    "text": text,
                    "confidence": round(conf, 3),
                    "box": [round(norm_x, 4), round(norm_y, 4), round(norm_w, 4), round(norm_h, 4)]
                })

            full_text = "\n".join(lines)
            return full_text, boxes

        except Exception as e:
            logger.debug(f"Exception during Apple Vision OCR: {e}")
            return self._fallback_recognize(pil_image)

    def _fallback_recognize(self, pil_image: Image.Image) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Graceful fallback if running in a restricted sandbox or on unsupported systems.
        Can hook into pytesseract if present.
        """
        try:
            import pytesseract
            data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT)
            lines = []
            boxes = []
            img_w, img_h = pil_image.size

            for i in range(len(data["text"])):
                w_text = data["text"][i].strip()
                if w_text:
                    lines.append(w_text)
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    boxes.append({
                        "text": w_text,
                        "confidence": float(data.get("conf", [100])[i]) / 100.0,
                        "box": [round(x / img_w, 4), round(y / img_h, 4), round(w / img_w, 4), round(h / img_h, 4)]
                    })
            return " ".join(lines), boxes
        except Exception:
            return "", []


_ocr_engine = None

def get_ocr_engine() -> AppleVisionOCR:
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = AppleVisionOCR()
    return _ocr_engine
