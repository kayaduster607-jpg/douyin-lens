import http.server
import json
import urllib.request
import urllib.parse
import re
import os
import gzip
import http.cookiejar
import zlib

from browser_parser import BrowserParseError, get_video_item

HOST = "127.0.0.1"
PORT = 8080

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 12; Pixel 4) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MEDIA_DOMAINS = (
    "douyin.com", "iesdouyin.com", "snssdk.com", "bytecdn.com",
    "byteimg.com", "douyinpic.com", "bytedance.com", "toutiao.com",
    "amemv.com", "bytetos.com", "douyinvod.com", "zjcdn.com",
    "douyinstatic.com", "bytevcloud.com", "ibytedtos.com",
)


def is_allowed_url(url, domains=MEDIA_DOMAINS):
    """按真实主机名校验，避免把查询参数中的域名误当成目标域名。"""
    try:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme in ("http", "https")
            and not parsed.username and not parsed.password
            and parsed.port in (None, 80, 443)
            and any(host == domain or host.endswith("." + domain) for domain in domains)
        )
    except ValueError:
        return False


class MediaRedirectHandler(urllib.request.HTTPRedirectHandler):
    """代理重定向也必须保持在已知的媒体域名内。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_url(newurl):
            raise ValueError("媒体重定向地址不受支持")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_media(url, method="GET", extra_headers=None):
    """文件大小与下载使用相同的域名规则、请求头和重定向规则。"""
    if not is_allowed_url(url):
        raise ValueError("不支持的媒体地址")
    headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }
    headers.update(extra_headers or {})
    opener = urllib.request.build_opener(MediaRedirectHandler())
    return opener.open(urllib.request.Request(url, method=method, headers=headers), timeout=30)


def make_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def fetch_page(url, user_agent=MOBILE_UA):
    opener, _ = make_opener()
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=20) as resp:
        data = resp.read()
        encoding = resp.headers.get("Content-Encoding")
        if encoding == "gzip":
            data = gzip.decompress(data)
        elif encoding == "deflate":
            data = zlib.decompress(data)
        return resp.geturl(), data.decode("utf-8", errors="replace")


def resolve_short_url(url):
    final_url, _ = fetch_page(url, user_agent=DESKTOP_UA)
    return final_url


def extract_url_from_text(text):
    """从分享文字中选择真实的抖音链接，不接受仿冒域名。"""
    for candidate in re.findall(r'https?://[^\s<>"，。！？]+', text):
        url = candidate.rstrip("，。！？,.!?）)")
        if is_allowed_url(url, ("douyin.com", "iesdouyin.com")):
            return url
    return ""


def extract_video_id(url):
    parsed = urllib.parse.urlparse(url)
    match = re.search(r"/(?:video|note|modal)/(\d+)(?:/|$)", parsed.path)
    if match:
        return match.group(1)
    params = urllib.parse.parse_qs(parsed.query)
    for key in ("modal_id", "aweme_id", "item_id"):
        value = params.get(key, [""])[0]
        if re.fullmatch(r"\d{15,22}", value):
            return value
    return None


def get_content_length(url):
    """Get file size from URL without downloading the full file."""
    try:
        with open_media(url, method="HEAD") as resp:
            size = resp.headers.get("Content-Length")
            return int(size) if size else None
    except Exception:
        return None


def format_size(bytes_size):
    """Format bytes to human-readable size."""
    if not bytes_size:
        return ""
    if bytes_size < 1024:
        return f"{bytes_size}B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.0f}KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f}MB"


def playback_url(address):
    """优先使用接口给出的媒体地址，只对旧播放接口替换水印路径。"""
    for url in address.get("url_list", []):
        if isinstance(url, str) and is_allowed_url(url):
            return url.replace("/playwm/", "/play/")
    return ""


def get_available_qualities(video):
    """按接口实际返回的分辨率列出清晰度，不通过 ratio 虚构 4K。"""
    variants = [(video.get("play_addr") or {}, 0)]
    for entry in video.get("bit_rate") or []:
        if isinstance(entry, dict):
            variants.append((entry.get("play_addr") or {}, entry.get("bit_rate") or 0))
    by_resolution = {}
    for address, bit_rate in variants:
        url = playback_url(address)
        if not url:
            continue
        width, height = address.get("width", 0), address.get("height", 0)
        resolution = min(width, height) if width and height else 0
        size = address.get("data_size") or None
        quality = {
            "label": f"{resolution}p" if resolution else "默认",
            "tag": "可用画质",
            "url": url,
            "size": size,
            "size_text": format_size(size),
        }
        # 同一分辨率保留接口提供的最高码率，避免重复的下载行。
        if resolution not in by_resolution or bit_rate > by_resolution[resolution][0]:
            by_resolution[resolution] = (bit_rate, quality)
    return [by_resolution[key][1] for key in sorted(by_resolution, reverse=True)]


def get_video_info_from_share_page(video_id):
    url = f"https://www.iesdouyin.com/share/video/{video_id}/"
    _, html = fetch_page(url)

    match = re.search(
        r"window\._ROUTER_DATA\s*=\s*({.*?})\s*;?\s*</script>",
        html,
        re.DOTALL,
    )
    if not match:
        return None

    try:
        router_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    loader_data = router_data.get("loaderData", {})
    page_data = loader_data.get("video_(id)/page", {})
    if not page_data:
        for key, val in loader_data.items():
            if isinstance(val, dict) and "videoInfoRes" in val:
                page_data = val
                break

    video_info_res = page_data.get("videoInfoRes")
    # 缺失字段表示页面没有内嵌数据，不能伪造为上游返回了状态码 -1。
    if not isinstance(video_info_res, dict):
        return None
    status_code = video_info_res.get("status_code")
    if status_code != 0:
        return {"error": f"分享页接口返回错误，状态码: {status_code}", "error_code": "upstream_error"}

    filter_list = video_info_res.get("filter_list", [])
    if filter_list:
        reason = filter_list[0].get("filter_reason", "")
        if reason == "SYSTEM_ITEM_NOT_EXIST":
            return {"error": "视频不存在，可能已被删除或设置了私密", "error_code": "unavailable"}
        elif reason:
            return {"error": f"视频不可用: {reason}"}

    item_list = video_info_res.get("item_list", [])
    if not item_list:
        return {"error": "未找到视频数据，可能视频已删除或设置了私密"}

    return parse_video_item(item_list[0])


def parse_video_item(item):
    video = item.get("video", {})
    play_addr = video.get("play_addr", {})
    qualities = get_available_qualities(video)
    default_url = playback_url(play_addr)
    if not default_url and qualities:
        default_url = qualities[0]["url"]

    # Cover images
    cover_urls = []
    cover_obj = video.get("cover", {})
    if isinstance(cover_obj, dict):
        cover_urls = cover_obj.get("url_list", [])
    if not cover_urls:
        origin_cover = video.get("origin_cover", {})
        if isinstance(origin_cover, dict):
            cover_urls = origin_cover.get("url_list", [])

    # Dynamic cover
    dynamic_cover_urls = []
    dynamic_cover = video.get("dynamic_cover", {})
    if isinstance(dynamic_cover, dict):
        dynamic_cover_urls = dynamic_cover.get("url_list", [])

    # Image list (for image posts / 图集)
    images = []
    image_infos = item.get("images") or item.get("image_infos") or []
    if isinstance(image_infos, list):
        for img in image_infos:
            if isinstance(img, dict):
                img_urls = img.get("url_list", [])
                if img_urls:
                    images.append(img_urls[0])

    # Author info
    author_info = item.get("author", {})
    author = author_info.get("nickname", "")
    author_avatar = ""
    avatar_thumb = author_info.get("avatar_thumb", {})
    if isinstance(avatar_thumb, dict):
        avatar_urls = avatar_thumb.get("url_list", [])
        if avatar_urls:
            author_avatar = avatar_urls[0]

    # Music info
    music_info = item.get("music", {})
    music_title = music_info.get("title", "")
    music_author = music_info.get("author", "")

    # Statistics
    stats = item.get("statistics", {})

    # Video dimensions
    width = video.get("width", 0)
    height = video.get("height", 0)

    # Duration (ms -> seconds)
    duration = video.get("duration", 0)
    if duration:
        duration = duration // 1000

    return {
        "video_id": item.get("aweme_id", ""),
        "title": item.get("desc", "无标题"),
        "author": author,
        "author_avatar": author_avatar,
        "duration": duration,
        "width": width,
        "height": height,
        "default_video_url": default_url,
        "qualities": qualities,
        "cover_urls": cover_urls,
        "dynamic_cover_urls": dynamic_cover_urls,
        "images": images,
        "music_title": music_title,
        "music_author": music_author,
        "digg_count": stats.get("digg_count", 0),
        "comment_count": stats.get("comment_count", 0),
        "play_count": stats.get("play_count", 0),
        "share_count": stats.get("share_count", 0),
    }


def handle_parse(url):
    url = extract_url_from_text(url)
    if not url:
        return {"error": "请输入有效的抖音视频链接", "error_code": "invalid_url"}

    if urllib.parse.urlparse(url).hostname in ("v.douyin.com", "vm.douyin.com"):
        try:
            url = resolve_short_url(url)
        except Exception as e:
            return {"error": f"解析短链接失败: {str(e)}"}

    video_id = extract_video_id(url)
    if not video_id:
        return {"error": "无法从链接中提取视频ID，请检查链接是否正确"}

    try:
        info = get_video_info_from_share_page(video_id)
    except (OSError, ValueError):
        # 分享页网络异常不应阻止桌面页的独立解析路径。
        info = None
    if not info or (info.get("error") and info.get("error_code") != "unavailable"):
        try:
            info = parse_video_item(get_video_item(video_id))
            info["parse_source"] = "browser"
        except BrowserParseError as exc:
            return {"error": str(exc), "error_code": "browser_parse_failed"}
    if info.get("error"):
        return info
    if not info.get("default_video_url") and not info.get("images"):
        return {"error": "未能获取到视频下载地址"}

    return info


class RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.serve_file("templates/index.html", "text/html; charset=utf-8")
        elif path == "/api/parse":
            self.handle_api_parse(parsed)
        elif path == "/api/filesize":
            self.handle_api_filesize(parsed)
        elif path == "/api/proxy":
            self.handle_api_proxy(parsed)
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404)

    def serve_file(self, filepath, content_type):
        full = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
        if not os.path.exists(full):
            self.send_error(404)
            return
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_api_parse(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        url = params.get("url", [""])[0].strip()
        if not url:
            self.send_json({"error": "请输入视频链接"}, 400)
            return
        if "douyin.com" not in url and "iesdouyin.com" not in url:
            self.send_json({"error": "请输入有效的抖音视频链接"}, 400)
            return
        try:
            result = handle_parse(url)
            self.send_json(result, 502 if result.get("error") else 200)
        except Exception as e:
            self.send_json({"error": f"解析出错: {str(e)}"}, 500)

    def handle_api_filesize(self, parsed):
        """Get file size for a given URL (HEAD request)."""
        params = urllib.parse.parse_qs(parsed.query)
        url = params.get("url", [""])[0].strip()
        if not url:
            self.send_json({"error": "缺少 url 参数"}, 400)
            return
        if not is_allowed_url(url):
            self.send_json({"error": "不支持的媒体地址"}, 400)
            return
        try:
            size = get_content_length(url)
            self.send_json({"size": size, "size_text": format_size(size)})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def handle_api_proxy(self, parsed):
        """Proxy video/image requests with proper headers to bypass 403."""
        params = urllib.parse.parse_qs(parsed.query)
        url = params.get("url", [""])[0].strip()
        if not url:
            self.send_error(400)
            return

        if not is_allowed_url(url):
            self.send_error(403)
            return

        try:
            # 转发 Range 和 206 响应，视频预览才能按需读取和拖动进度。
            headers = {}
            if self.headers.get("Range"):
                headers["Range"] = self.headers["Range"]
            with open_media(url, extra_headers=headers) as resp:
                self.send_response(resp.status)
                for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                    value = resp.headers.get(name)
                    if value:
                        self.send_header(name, value)
                self.end_headers()
                while chunk := resp.read(65536):
                    self.wfile.write(chunk)

        except urllib.error.HTTPError as e:
            self.send_error(e.code)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # 浏览器停止预览或取消下载时，连接关闭属于正常情况。
            pass
        except Exception as e:
            self.send_error(502)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    print(f"Server running at http://{HOST}:{PORT}")
    # 预览、文件大小和解析可能并发，单线程会被视频流长期占用。
    server = http.server.ThreadingHTTPServer((HOST, PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
