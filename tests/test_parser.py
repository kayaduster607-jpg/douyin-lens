"""覆盖字段缺失、分享链接、真实清晰度和媒体代理边界的回归测试。"""

import contextlib
import http.server
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import app
import browser_parser


VIDEO_ID = "7697690805168058033"
MEDIA_URL = "https://v5-dy-ov-experiment.zjcdn.com/video.mp4"


def video_item():
    """最小作品样本：只提供真实存在的一档画质。"""
    return {
        "aweme_id": VIDEO_ID,
        "desc": "测试作品",
        "video": {
            "play_addr": {"url_list": [MEDIA_URL], "width": 720, "height": 1280},
            "duration": 28000,
        },
    }


class ParserTests(unittest.TestCase):
    def test_share_text_and_modal_id(self):
        text = "文案 https://v.douyin.com/ngA9m4mpWDM/ 复制链接"
        self.assertEqual(app.extract_url_from_text(text), "https://v.douyin.com/ngA9m4mpWDM/")
        self.assertEqual(app.extract_video_id(f"https://www.douyin.com/user/self?modal_id={VIDEO_ID}"), VIDEO_ID)
        # 账号编号和无关查询参数都不能冒充作品编号。
        self.assertIsNone(app.extract_video_id(f"https://www.douyin.com/user/{VIDEO_ID}"))
        self.assertIsNone(app.extract_video_id(f"https://www.douyin.com/user/self?other={VIDEO_ID}"))

    def test_url_domain_validation(self):
        self.assertTrue(app.is_allowed_url(MEDIA_URL))
        for url in (
            "https://douyin.com.example.org/video.mp4",
            "https://example.org/?douyin.com",
            "http://127.0.0.1/?douyin",
            "https://douyin.com:invalid/video",
            "https://user@www.douyin.com/video",
        ):
            self.assertFalse(app.is_allowed_url(url), url)

    def test_missing_ssr_data_is_not_minus_one(self):
        html = 'window._ROUTER_DATA = {"loaderData":{"video_(id)/page":{"itemId":"1"}}}</script>'
        with patch.object(app, "fetch_page", return_value=("", html)):
            self.assertIsNone(app.get_video_info_from_share_page(VIDEO_ID))

    def test_browser_fallback_recovers_missing_ssr(self):
        with patch.object(app, "get_video_info_from_share_page", return_value=None), patch.object(
            app, "get_video_item", return_value=video_item()
        ) as browser:
            result = app.handle_parse(f"https://www.douyin.com/video/{VIDEO_ID}")
        browser.assert_called_once_with(VIDEO_ID)
        self.assertEqual(result["default_video_url"], MEDIA_URL)
        self.assertEqual(result["parse_source"], "browser")

    def test_definite_unavailable_does_not_launch_browser(self):
        error = {"error": "作品不存在", "error_code": "unavailable"}
        with patch.object(app, "get_video_info_from_share_page", return_value=error), patch.object(
            app, "get_video_item"
        ) as browser:
            self.assertEqual(app.handle_parse(f"https://www.douyin.com/video/{VIDEO_ID}"), error)
        browser.assert_not_called()

    def test_browser_error_is_actionable(self):
        with patch.object(app, "get_video_info_from_share_page", return_value=None), patch.object(
            app, "get_video_item", side_effect=browser_parser.BrowserParseError("请安装依赖")
        ):
            result = app.handle_parse(f"https://www.douyin.com/video/{VIDEO_ID}")
        self.assertEqual(result["error"], "请安装依赖")

    def test_only_report_available_qualities(self):
        result = app.parse_video_item(video_item())
        self.assertEqual([q["label"] for q in result["qualities"]], ["720p"])
        video = video_item()["video"]
        video["bit_rate"] = [{"bit_rate": 100, "play_addr": {
            "url_list": [MEDIA_URL + "?1080"], "width": 1080, "height": 1920, "data_size": 2000000,
        }}]
        qualities = app.get_available_qualities(video)
        self.assertEqual([q["label"] for q in qualities], ["1080p", "720p"])
        self.assertEqual(qualities[0]["size_text"], "1.9MB")
        self.assertEqual(app.parse_video_item({"images": [{"url_list": [MEDIA_URL]}]})["qualities"], [])

    def test_only_capture_target_detail(self):
        base = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
        self.assertTrue(browser_parser.is_detail_response(base + "?aweme_id=" + VIDEO_ID, VIDEO_ID))
        self.assertFalse(browser_parser.is_detail_response(base + "?aweme_id=123", VIDEO_ID))
        self.assertFalse(browser_parser.is_detail_response(base.replace("www.douyin.com", "example.org") + "?aweme_id=" + VIDEO_ID, VIDEO_ID))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 使用临时端口，避免影响用户正在运行的 8080 服务。
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), app.RequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_parse_failure_uses_http_502(self):
        with patch.object(app, "handle_parse", return_value={"error": "未返回数据"}):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(self.base + "/api/parse?url=https://www.douyin.com/video/" + VIDEO_ID)
            self.assertEqual(caught.exception.code, 502)
            self.assertEqual(json.loads(caught.exception.read())["error"], "未返回数据")

    def test_range_proxy_forwards_partial_response(self):
        response = unittest.mock.MagicMock()
        response.status = 206
        response.headers = {"Content-Type": "video/mp4", "Content-Length": "4", "Content-Range": "bytes 0-3/100"}
        response.read.side_effect = [b"test", b""]
        with patch.object(app, "open_media", return_value=contextlib.nullcontext(response)) as media:
            request = urllib.request.Request(self.base + "/api/proxy?url=" + MEDIA_URL, headers={"Range": "bytes=0-3"})
            with urllib.request.urlopen(request) as result:
                self.assertEqual(result.status, 206)
                self.assertEqual(result.headers["Content-Range"], "bytes 0-3/100")
                self.assertEqual(result.read(), b"test")
        media.assert_called_once_with(MEDIA_URL, extra_headers={"Range": "bytes=0-3"})


if __name__ == "__main__":
    unittest.main()
