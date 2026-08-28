"""本机浏览器/驱动解析。

部署环境为公司内网，无法访问 Google 下载源（webdriver-manager / Playwright CDN），
因此 UI 自动化统一使用用户本机安装的 Chrome 和项目内置的 ChromeDriver：
- Playwright：chromium 启动时加 channel='chrome'，直接驱动本机 Chrome
- Selenium：优先使用 <项目根>/webdrivers/chromedriver.exe
"""
import os
import logging

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_CHROMEDRIVER = os.path.join(_PROJECT_ROOT, 'webdrivers', 'chromedriver.exe')

_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    # Linux / macOS 常见路径
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_chrome():
    """返回本机 Chrome 可执行文件路径，未安装返回 None。"""
    for p in _CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def chrome_launch_kwargs(kwargs):
    """Playwright chromium 启动参数：有本机 Chrome 时用 channel='chrome' 驱动它。"""
    if find_chrome():
        kwargs.setdefault('channel', 'chrome')
    return kwargs


def get_chromedriver_path():
    """返回可用的 chromedriver 路径。

    优先级：项目 webdrivers 目录 > webdriver-manager 缓存 > 在线下载（内网会失败）。
    """
    if os.path.exists(LOCAL_CHROMEDRIVER):
        return LOCAL_CHROMEDRIVER
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        manager = ChromeDriverManager()
        cached = manager._cache_manager.find_driver(manager.driver)
        if cached and os.path.exists(cached):
            return cached
        return manager.install()
    except Exception as e:
        logger.error(f"无法获取 ChromeDriver: {e}")
        return None
