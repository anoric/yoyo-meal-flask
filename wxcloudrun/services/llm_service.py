"""
LLM 服务封装 - 火山引擎豆包API
"""
import json
import logging
from typing import Dict, List, Any, Generator, Optional
import requests

from config import VOLCANO_API_KEY

logger = logging.getLogger('log')


class LLMService:
    """火山引擎豆包LLM服务"""

    # 模型配置
    # 参考: https://www.volcengine.com/docs/82379/1263482
    MODELS = {
        'fast': 'doubao-1.5-pro-32k',       # 快速模型，用于普通任务
        'advanced': 'doubao-1.5-pro-256k'   # 高级模型，用于复杂问题
    }

    BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'

    def __init__(self):
        self.api_key = VOLCANO_API_KEY

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        model_type: str = 'fast',
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式对话

        Args:
            messages: 消息列表 [{'role': 'user/assistant/system', 'content': '...'}]
            tools: 工具定义列表 (OpenAI Function Calling 格式)
            model_type: 'fast' 或 'advanced'
            temperature: 温度参数
            max_tokens: 最大token数

        Yields:
            流式响应块:
            - {'type': 'text', 'content': '...'} - 文本内容
            - {'type': 'tool_call', 'tool': {...}} - 工具调用
            - {'type': 'finish', 'reason': '...'} - 完成标记
            - {'type': 'error', 'content': '...'} - 错误
            - {'type': 'done'} - 结束
        """
        if not self.api_key:
            yield {'type': 'error', 'content': 'VOLCANO_API_KEY not configured'}
            return

        model = self.MODELS.get(model_type, self.MODELS['fast'])

        payload = {
            'model': model,
            'messages': messages,
            'stream': True,
            'temperature': temperature,
            'max_tokens': max_tokens
        }

        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = 'auto'

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        try:
            response = requests.post(
                f'{self.BASE_URL}/chat/completions',
                headers=headers,
                json=payload,
                stream=True,
                timeout=60
            )
            response.raise_for_status()

            # 用于累积工具调用的参数
            tool_call_accumulator = {}

            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode('utf-8')
                if not line.startswith('data: '):
                    continue

                data = line[6:]  # 去掉 'data: ' 前缀
                if data == '[DONE]':
                    yield {'type': 'done'}
                    break

                try:
                    chunk = json.loads(data)
                    parsed = self._parse_chunk(chunk, tool_call_accumulator)
                    if parsed:
                        yield parsed
                except json.JSONDecodeError:
                    continue

        except requests.exceptions.Timeout:
            logger.error("LLM request timeout")
            yield {'type': 'error', 'content': '请求超时，请稍后重试'}

        except requests.exceptions.RequestException as e:
            logger.error(f"LLM request failed: {e}")
            yield {'type': 'error', 'content': f'服务暂时不可用: {str(e)}'}

        except Exception as e:
            logger.error(f"LLM unexpected error: {e}", exc_info=True)
            yield {'type': 'error', 'content': '服务异常，请稍后重试'}

    def _parse_chunk(
        self,
        chunk: Dict,
        tool_call_accumulator: Dict
    ) -> Optional[Dict[str, Any]]:
        """解析响应块"""
        if 'choices' not in chunk or not chunk['choices']:
            return None

        choice = chunk['choices'][0]
        delta = choice.get('delta', {})

        # 检查是否是工具调用
        if 'tool_calls' in delta:
            for tc in delta['tool_calls']:
                index = tc.get('index', 0)

                if index not in tool_call_accumulator:
                    tool_call_accumulator[index] = {
                        'id': '',
                        'name': '',
                        'arguments': ''
                    }

                acc = tool_call_accumulator[index]

                if tc.get('id'):
                    acc['id'] = tc['id']
                if tc.get('function', {}).get('name'):
                    acc['name'] = tc['function']['name']
                if tc.get('function', {}).get('arguments'):
                    acc['arguments'] += tc['function']['arguments']

            return None  # 工具调用在 finish 时返回

        # 普通文本内容
        if 'content' in delta and delta['content']:
            return {
                'type': 'text',
                'content': delta['content']
            }

        # 完成标记
        finish_reason = choice.get('finish_reason')
        if finish_reason:
            # 如果有工具调用，在完成时返回
            if finish_reason == 'tool_calls' and tool_call_accumulator:
                # 返回第一个工具调用（通常只有一个）
                first_tool = tool_call_accumulator.get(0)
                if first_tool:
                    return {
                        'type': 'tool_call',
                        'tool': {
                            'id': first_tool['id'],
                            'name': first_tool['name'],
                            'arguments': first_tool['arguments']
                        }
                    }

            return {
                'type': 'finish',
                'reason': finish_reason
            }

        return None

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        model_type: str = 'fast',
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        非流式对话 (同步)

        Returns:
            {
                'content': '...',       # 文本内容
                'tool_call': {...},     # 工具调用 (如果有)
                'error': '...'          # 错误信息 (如果有)
            }
        """
        result = {
            'content': '',
            'tool_call': None,
            'error': None
        }

        for chunk in self.chat_stream(messages, tools, model_type, temperature, max_tokens):
            if chunk['type'] == 'text':
                result['content'] += chunk['content']
            elif chunk['type'] == 'tool_call':
                result['tool_call'] = chunk['tool']
            elif chunk['type'] == 'error':
                result['error'] = chunk['content']
                break

        return result
