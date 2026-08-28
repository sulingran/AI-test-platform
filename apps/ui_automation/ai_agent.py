import logging
import asyncio
import sys
from .ai_base import BaseBrowserAgent

logger = logging.getLogger('django')


def _run_agent_coro(coro):
    """运行 agent 协程，Windows 下强制使用 ProactorEventLoop。

    Daphne 在 import 时会把全局事件循环策略改成 WindowsSelectorEventLoopPolicy
    （Twisted 的 asyncioreactor 只支持 selector 循环），此后任何线程里
    asyncio.run() 创建的都是 SelectorEventLoop。而 Windows 上 selector 循环
    不支持子进程，browser-use 启动浏览器时会在 create_subprocess_exec 处
    抛 NotImplementedError。这里显式创建 ProactorEventLoop 绕开被篡改的全局策略。
    """
    if sys.platform != 'win32':
        return asyncio.run(coro)

    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

class BrowserAgent(BaseBrowserAgent):
    """
    Standard Browser Agent for Text Mode.
    Inherits all base functionality without applying dangerous visual patches.
    """
    def __init__(self, execution_mode='text', enable_gif=True, case_name=None):
        self.enable_gif = enable_gif
        self.case_name = case_name or "Adhoc Task"
        super().__init__(execution_mode='text')

# ============================================================================
# EXPORTED FUNCTIONS (FACTORY)
# ============================================================================

def get_agent_class(execution_mode='text'):
    # 始终返回文本模式实现
    return BrowserAgent

def run_ai_task_sync(task_description: str, planned_tasks=None, callback=None, should_stop=None, execution_mode='text'):
    agent = BrowserAgent(execution_mode='text')
    return _run_agent_coro(agent.run_task(task_description, planned_tasks, callback, should_stop))

def analyze_task_sync(task_description: str, execution_mode='text'):
    agent = BrowserAgent(execution_mode='text')
    return _run_agent_coro(agent.analyze_task(task_description))

def run_full_process_sync(task_description: str, analysis_callback=None, step_callback=None, should_stop=None, execution_mode='text', enable_gif=True, case_name=None):
    logger.info(f"DEBUG: Entering run_full_process_sync with execution_mode=text, enable_gif={enable_gif}")

    agent = BrowserAgent(execution_mode='text', enable_gif=enable_gif, case_name=case_name)

    logger.info(f"DEBUG: Agent created successfully ({type(agent).__name__}), starting event loop")
    return _run_agent_coro(agent.run_full_process(task_description, analysis_callback, step_callback, should_stop))
