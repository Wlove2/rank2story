"""Opt-in loopback-only image reading for public Xiaohongshu gallery notes.

Signed CDN URLs are held in memory and never serialized to the source packet.
Each photo must actually be fetched and passed to a local vision model.
"""
from __future__ import annotations

import base64
import hashlib
import json
import urllib.parse
import urllib.request
from typing import Any

GALLERY_DOM_JS = """(async()=>{
 const swiper=document.querySelector('#noteContainer .swiper.note-slider')?.swiper;
 if(!swiper)return JSON.stringify({gallery_items:[]});
 const all=[...swiper.slides].filter(x=>!x.classList.contains('swiper-slide-duplicate'));
 const gallery_items=[];
 for(let i=0;i<all.length;i++){
   swiper.slideToLoop(i,0);
   await new Promise(resolve=>setTimeout(resolve,450));
   const slide=swiper.slides[swiper.activeIndex],img=slide?.querySelector('img');
   if(img){try{await Promise.race([img.decode(),new Promise((_,reject)=>setTimeout(()=>reject('timeout'),2500))])}catch(e){}}
   gallery_items.push({index:i,src:img?.currentSrc||img?.src||'',
     width:img?.naturalWidth||0,height:img?.naturalHeight||0});
 }
 return JSON.stringify({gallery_items});
})()"""


def sanitize_public_cdn(url: str) -> str:
    target = urllib.parse.urlsplit(url)
    host = (target.hostname or "").lower()
    if target.scheme != "https" or not (
        host == "xhscdn.com" or host.endswith(".xhscdn.com")
    ):
        raise ValueError("NOT_PUBLIC_XHS_IMAGE_CDN")
    return url


def safe_image_bytes(url: str) -> bytes:
    sanitize_public_cdn(url)
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.xiaohongshu.com/",
    })
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=18
    ) as response:
        if not str(response.headers.get("Content-Type", "")).startswith("image/"):
            raise ValueError("XHS_IMAGE_NOT_IMAGE")
        content = response.read(6_000_001)
    if not 5_000 <= len(content) <= 6_000_000:
        raise ValueError("XHS_IMAGE_BYTES_UNSUPPORTED")
    return content


def local_ollama_read(image: bytes, model: str, *, timeout: int = 155) -> str:
    if not model or not model.isprintable() or len(model) > 80:
        raise ValueError("VISION_MODEL_ID_INVALID")
    prompt = (
        "严格观察这张真实网文/小说相关图片，转写全部清晰可辨的汉字与书名，"
        "然后补一句视觉内容描述。如果没有文字，明确说明画面内容。"
        "不可把看不清的部分猜成作品名，使用[无法识别]标记。"
    )
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps({
            "model": model, "prompt": prompt,
            "images": [base64.b64encode(image).decode("ascii")],
            "stream": False,
            "options": {"num_predict": 850},
        }, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    result = str(payload.get("response") or "").strip()
    if len(result) < 55:
        raise ValueError("VISION_RESPONSE_TOO_SHORT")
    return result


def read_public_gallery(
    prefix: list[str],
    session: str,
    run_cli: Any,
    expected_images: int,
    *,
    model: str,
    max_images: int | None = None,
) -> list[dict[str, Any]]:
    status, response = run_cli(
        prefix, ["browser", session, "eval", GALLERY_DOM_JS], 45
    )
    if status:
        return []
    try:
        gallery = json.loads(response).get("gallery_items", [])
    except (ValueError, TypeError):
        return []
    if not isinstance(gallery, list) or len(gallery) != expected_images:
        return []
    records: list[dict[str, Any]] = []
    for media in gallery[:max_images]:
        index = media.get("index")
        if not isinstance(index, int) or index < 0:
            continue
        try:
            if media.get("width", 0) < 100 or media.get("height", 0) < 100:
                raise ValueError("XHS_IMAGE_DID_NOT_LOAD")
            content = safe_image_bytes(str(media.get("src") or ""))
            text = local_ollama_read(content, model)
            records.append({
                "index": index,
                "image_sha256": hashlib.sha256(content).hexdigest(),
                "model": model,
                "text": text,
                "reading_status": "machine_read_unreviewed",
            })
        except (OSError, ValueError, urllib.error.URLError, TimeoutError):
            # The missing image cannot count toward 'images_read'.
            continue
    return records
