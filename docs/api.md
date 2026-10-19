# 本地 API 与字段说明

默认地址为 `http://127.0.0.1:8080`。API 供本机学习页面使用，没有鉴权、配额或公网服务承诺。

## 1. GET /api/parse

参数 `url` 是经过 URL 编码的作品链接或整段分享文字。

```powershell
$shareText = Read-Host "粘贴你有权使用的抖音作品链接或分享文字"
$encodedShareText = [uri]::EscapeDataString($shareText)
Invoke-RestMethod "http://127.0.0.1:8080/api/parse?url=$encodedShareText"
```

### 成功字段

| 字段 | 说明 |
| --- | --- |
| `video_id`、`title`、`author` | 作品 ID、描述、作者昵称 |
| `author_avatar` | 头像地址，可能为空 |
| `duration` | 毫秒转换并取整后的秒数 |
| `width`、`height` | 视频字段中的宽高 |
| `default_video_url` | 默认播放地址，可能不是最高画质地址 |
| `qualities` | 含 `label`、`tag`、`url`、`size`、`size_text` 的列表 |
| `cover_urls`、`dynamic_cover_urls` | 封面及动态封面地址 |
| `images` | 图集图片地址 |
| `music_title`、`music_author` | 音乐字段，可能为空 |
| `digg_count`、`comment_count`、`play_count`、`share_count` | 缺失时默认为 0，不代表真实统计一定为 0 |
| `parse_source` | 浏览器路径额外设置为 `browser`；分享页路径没有此标记 |

没有文件大小时，`size` 为 `null`，`size_text` 为空。

### 状态码

| 状态 | 当前含义 |
| --- | --- |
| 200 | 返回可用作品结果 |
| 400 | 缺少输入或前置链接文本检查失败 |
| 502 | `handle_parse()` 返回 `error`，包括部分输入识别错误和浏览器失败 |
| 500 | 请求处理器捕获到未预期异常 |

错误含 `error`，部分分支还含 `error_code`。错误分类没有完全统一，不能假定所有 502 都来自上游故障。前端按 JSON 的 `error` 显示原因。

请求可能启动浏览器，45 秒浏览器等待预算不是完整 HTTP 请求总超时。

## 2. GET /api/filesize

参数 `url` 是编码后的允许媒体地址。后端通过 HEAD 读取 `Content-Length`，不为测量大小下载整个文件。

返回 `size`（字节数或 `null`）和 `size_text`（如 `9.3MB` 或空字符串）。缺参数或不允许地址返回 400。HEAD 失败通常返回 200 加 `size: null`，不能据此判断视频无法播放。

## 3. GET /api/proxy

参数 `url` 是编码后的媒体地址。预览、封面和下载都使用该路径。

- 使用统一的允许域名、请求头和媒体重定向规则。
- 转发浏览器提供的 `Range`。
- 转发上游状态及存在的 `Content-Type`、`Content-Length`、`Content-Range`、`Accept-Ranges`。
- 按 65536 字节块读取并流式转发。
- 缺参数返回 400，不允许地址返回 403；上游 HTTP 错误返回相应状态，其他代理异常通常返回 502。

媒体 URL 可能包含短期签名。默认访问日志可能包含查询串，分享前需脱敏，不要公开 Cookie 或完整签名链接。

## 4. 其他路由

| 路由 | 行为 |
| --- | --- |
| `/`、`/index.html` | 返回 `templates/index.html` |
| `/favicon.ico` | 返回 204 |
| 其他路径 | 返回 404 |

仓库中的文档和图片用于 GitHub 展示，并不由这个 Web 服务提供。地址和端口在 `app.py` 中定义，没有命令行配置入口。
