#!/usr/bin/env python
"""
OmniParser Invocation Script

This script is designed to be run in the OmniParser environment.
It takes a screenshot path as input and outputs JSON with the parsed results.
"""

import sys
import os
import json
import argparse
from pathlib import Path

# Add OmniParser to path
omniparser_home = Path(os.getenv("OMNIPARSER_HOME", Path.home() / "omniparser"))
sys.path.insert(0, str(omniparser_home / "util"))
sys.path.insert(0, str(omniparser_home))

from util.utils import (
    get_yolo_model,
    get_caption_model_processor,
    get_som_labeled_img,
    check_ocr_box,
)
from PIL import Image
import torch


def _json_default(value):
    """Convert NumPy/PyTorch scalar containers emitted by OmniParser to JSON types."""
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main():
    parser = argparse.ArgumentParser(description="OmniParser CLI for AgentQE")
    parser.add_argument("image_path", help="Path to screenshot image")
    parser.add_argument("--box-threshold", type=float, default=0.05)
    parser.add_argument("--iou-threshold", type=float, default=0.1)
    parser.add_argument("--use-paddleocr", action="store_true", default=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--model-dir", type=str, 
                       default=str(Path(os.getenv("OMNIPARSER_MODEL_DIR", Path.home() / "omniparser" / "weights"))))
    
    args = parser.parse_args()
    
    try:
        # Load models
        yolo_model = get_yolo_model(
            model_path=str(Path(args.model_dir) / "icon_detect_v3" / "model.pt"),
            device="cuda" if torch.cuda.is_available() else "cpu"
        )
        
        # Fix Florence-2 config compatibility issue with newer transformers
        import transformers
        from transformers import AutoConfig
        florence_config_path = str(Path(args.model_dir) / "icon_caption_florence")
        try:
            config = AutoConfig.from_pretrained(florence_config_path, trust_remote_code=True)
            # Patch the config to add missing attribute
            if not hasattr(config, 'forced_bos_token_id'):
                config.forced_bos_token_id = None
        except Exception:
            pass
        
        caption_model_processor = get_caption_model_processor(
            model_name="florence2",
            model_name_or_path=florence_config_path,
            device="cuda" if torch.cuda.is_available() else "cpu"
        )
        
        # Load image
        image = Image.open(args.image_path).convert("RGB")
        
        # Run OCR - force EasyOCR to avoid PaddleOCR version compatibility issues
        ocr_result, _ = check_ocr_box(
            image,
            display_img=False,
            output_bb_format='xyxy',
            goal_filtering=None,
            easyocr_args={'paragraph': False, 'text_threshold': 0.9},
            use_paddleocr=False
        )
        if ocr_result is None:
            ocr_text, ocr_bbox = [], []
        else:
            ocr_text, ocr_bbox = ocr_result
        
        # Run full parsing with SOM labeling
        draw_bbox_config = {
            'text_scale': 0.8,
            'text_thickness': 2,
            'text_padding': 3,
            'thickness': 3,
        }
        
        encoded_image, label_coordinates, parsed_content_list = get_som_labeled_img(
            image_source=image,
            model=yolo_model,
            BOX_TRESHOLD=args.box_threshold,
            output_coord_in_ratio=True,
            ocr_bbox=ocr_bbox,
            draw_bbox_config=draw_bbox_config,
            caption_model_processor=caption_model_processor,
            ocr_text=ocr_text,
            iou_threshold=args.iou_threshold,
            imgsz=args.imgsz,
        )
        
        # Output JSON result
        result = {
            "encoded_image": encoded_image,
            "label_coordinates": label_coordinates,
            "parsed_content_list": parsed_content_list,
            "ocr_text": ocr_text,
            "ocr_bbox": ocr_bbox,
            "image_width": image.width,
            "image_height": image.height,
        }
        
        print(json.dumps(result, default=_json_default))
        sys.exit(0)
        
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()