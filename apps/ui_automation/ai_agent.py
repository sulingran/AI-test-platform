import logging
import asyncio
import os
from .ai_base import BaseBrowserAgent

logger = logging.getLogger('django')

class BrowserAgent(BaseBrowserAgent):
    """
    Standard Browser Agent for Text Mode.
    Inherits all base functionality without applying dangerous visual patches.
    """
    def __init__(
        self,
        execution_mode='text',
        enable_gif=True,
        case_name=None,
        sensitive_values=None,
        sensitive_data=None,
        allowed_domains=None,
    ):
        super().__init__(
            execution_mode='text',
            enable_gif=enable_gif,
            case_name=case_name,
            sensitive_values=sensitive_values,
            sensitive_data=sensitive_data,
            allowed_domains=allowed_domains,
        )

# ============================================================================
# EXPORTED FUNCTIONS (FACTORY)
# ============================================================================

def get_agent_class(execution_mode='text'):
    # 始终返回文本模式实现
    return BrowserAgent


def _run_in_browser_event_loop(coroutine):
    """Run browser-use on an event loop that can launch Chrome on Windows."""
    if os.name != 'nt' or not hasattr(asyncio, 'ProactorEventLoop'):
        return asyncio.run(coroutine)

    loop = asyncio.ProactorEventLoop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coroutine)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        asyncio.set_event_loop(None)
        loop.close()

def run_ai_task_sync(task_description: str, planned_tasks=None, callback=None, should_stop=None, execution_mode='text'):
    agent = BrowserAgent(execution_mode='text')
    return _run_in_browser_event_loop(agent.run_task(task_description, planned_tasks, callback, should_stop))
    
def analyze_task_sync(task_description: str, execution_mode='text'):
    agent = BrowserAgent(execution_mode='text')
    return _run_in_browser_event_loop(agent.analyze_task(task_description))

def run_full_process_sync(
    task_description: str,
    analysis_callback=None,
    step_callback=None,
    should_stop=None,
    execution_mode='text',
    enable_gif=True,
    case_name=None,
    sensitive_values=None,
    sensitive_data=None,
    allowed_domains=None,
):
    logger.info(f"DEBUG: Entering run_full_process_sync with execution_mode=text, enable_gif={enable_gif}")

    agent = BrowserAgent(
        execution_mode='text',
        enable_gif=enable_gif,
        case_name=case_name,
        sensitive_values=sensitive_values,
        sensitive_data=sensitive_data,
        allowed_domains=allowed_domains,
    )

    logger.info(f"DEBUG: Agent created successfully ({type(agent).__name__}), starting browser event loop")
    return _run_in_browser_event_loop(
        agent.run_full_process(task_description, analysis_callback, step_callback, should_stop)
    )
