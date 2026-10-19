"""用独立浏览器加载公开作品页，兼容不再内嵌视频数据的分享页。"""

import json
import threading
import time
import urllib.parse


class BrowserParseError(RuntimeError):
    """可直接展示给用户的浏览器解析错误。"""


_BROWSER_LOCK = threading.Lock()
_CACHE = {}
CACHE_SECONDS = 180
BROWSER_TIMEOUT_MS = 45000


def is_detail_response(url, video_id):
    """只接收目标作品的数据，排除推荐列表和其他视频。"""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    return (
        parsed.hostname == "www.douyin.com"
        and parsed.path == "/aweme/v1/web/aweme/detail/"
        and params.get("aweme_id") == [video_id]
    )


def launch_browser(playwright):
    """优先复用系统浏览器，不读取用户的浏览器资料或登录信息。"""
    for channel in ("msedge", "chrome", None):
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except Exception:
            # Edge 未安装时尝试 Chrome，最后尝试 Playwright 自带浏览器。
            continue
    raise BrowserParseError(
        "未能启动浏览器。请安装 Edge 或 Chrome，或运行：python -m playwright install chromium"
    )


def read_detail_response(response, video_id):
    """浏览器负责页面脚本和会话；这里只读取正常返回的作品 JSON。"""
    if not is_detail_response(response.url, video_id) or response.status != 200:
        return None
    try:
        item = response.json().get("aweme_detail")
    except (ValueError, AttributeError, json.JSONDecodeError):
        return None
    if isinstance(item, dict) and str(item.get("aweme_id")) == video_id:
        return item
    return None


def load_video_item(playwright, video_id):
    """在限定时间内等待作品数据，退出时总是关闭独立浏览器。"""
    from playwright.sync_api import Error, TimeoutError

    browser = launch_browser(playwright)
    try:
        page = browser.new_page(locale="zh-CN")
        items = []

        def collect_response(response):
            # 单个响应读取失败时继续等，避免把瞬时网络异常当作作品不存在。
            try:
                item = read_detail_response(response, video_id)
                if item:
                    items.append(item)
            except Error:
                pass

        page.on("response", collect_response)
        deadline = time.monotonic() + BROWSER_TIMEOUT_MS / 1000
        try:
            page.goto(
                f"https://www.douyin.com/video/{video_id}",
                wait_until="domcontentloaded",
                timeout=BROWSER_TIMEOUT_MS,
            )
        except TimeoutError:
            # 页面加载超时后，已收到的作品响应仍然有效。
            pass
        while not items and time.monotonic() < deadline:
            page.wait_for_timeout(200)
        if items:
            return items[0]
        raise BrowserParseError(
            "抖音桌面页未返回可下载的视频数据，可能需要登录、验证或稍后重试。"
            "请确认作品在网页版中可正常播放。"
        )
    except Error as exc:
        raise BrowserParseError("浏览器访问抖音失败，请检查网络后重试。") from exc
    finally:
        browser.close()


def get_video_item(video_id):
    """串行运行浏览器并短暂缓存，避免重复解析启动大量进程。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserParseError(
            "分享页未提供视频数据，需要浏览器解析。请先运行：python -m pip install -r requirements.txt"
        ) from exc

    with _BROWSER_LOCK:
        now = time.monotonic()
        cached = _CACHE.get(video_id)
        if cached and now - cached[0] < CACHE_SECONDS:
            return cached[1]
        with sync_playwright() as playwright:
            item = load_video_item(playwright, video_id)
        # 仅缓存成功结果；保留少量短期有效的媒体地址。
        expired = [key for key, (stamp, _) in _CACHE.items() if now - stamp >= CACHE_SECONDS]
        for key in expired:
            del _CACHE[key]
        if len(_CACHE) >= 32:
            del _CACHE[next(iter(_CACHE))]
        _CACHE[video_id] = (time.monotonic(), item)
        return item
