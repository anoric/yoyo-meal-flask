"""
Agent 服务 - 核心对话处理逻辑
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Generator, Optional
import threading

from wxcloudrun.model import Baby
from wxcloudrun.services.context_collector import ContextCollector
from wxcloudrun.services.llm_service import LLMService
from wxcloudrun.services.tool_executor import ToolExecutor, TOOLS

logger = logging.getLogger('log')


class ConversationStore:
    """
    对话存储 (内存版本)

    生产环境建议使用 Redis 替代
    """

    def __init__(self, max_conversations: int = 1000, ttl_seconds: int = 3600):
        self._store: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self.max_conversations = max_conversations
        self.ttl_seconds = ttl_seconds

    def get(self, conversation_id: str) -> Optional[Dict]:
        """获取对话"""
        with self._lock:
            conv = self._store.get(conversation_id)
            if conv and self._is_expired(conv):
                del self._store[conversation_id]
                return None
            return conv

    def set(self, conversation_id: str, data: Dict):
        """设置对话"""
        with self._lock:
            self._cleanup_if_needed()
            data['last_active'] = datetime.now()
            self._store[conversation_id] = data

    def update_messages(self, conversation_id: str, messages: List[Dict]):
        """更新对话消息"""
        with self._lock:
            if conversation_id in self._store:
                self._store[conversation_id]['messages'] = messages
                self._store[conversation_id]['last_active'] = datetime.now()

    def _is_expired(self, conv: Dict) -> bool:
        """检查是否过期"""
        last_active = conv.get('last_active', datetime.min)
        return (datetime.now() - last_active).total_seconds() > self.ttl_seconds

    def _cleanup_if_needed(self):
        """清理过期对话"""
        if len(self._store) >= self.max_conversations:
            expired = [k for k, v in self._store.items() if self._is_expired(v)]
            for k in expired:
                del self._store[k]


# 全局对话存储
conversation_store = ConversationStore()


class AgentService:
    """Agent服务 - 处理用户输入并执行相应操作"""

    SYSTEM_PROMPT = """你是呦呦辅食的AI助手，专门帮助家长记录和管理宝宝的辅食情况。

你的主要职责：
1. 记录宝宝的特殊状态（生病、打疫苗等）- 使用 create_special_status 工具
2. 记录宝宝的进食情况 - 使用 create_meal_record 工具
3. 记录宝宝的过敏反应 - 使用 report_allergy 工具
4. 回答关于宝宝喂养、健康、早教等问题 - 使用 answer_question 工具

重要规则：
1. 当用户描述的信息不完整时（如缺少日期、餐次等），使用 ask_clarification 工具友好地询问
2. 如果用户说"今天"、"昨天"等相对日期，根据当前日期转换为具体日期
3. 对于需要日期但用户未提供的情况，要询问确认（例如："是今天生病的吗？"）
4. 始终保持友好、亲切、专业的语气
5. 注意宝宝的月龄，给出适合月龄的建议
6. 记录成功后，给予正面的反馈和必要的提醒

以下是当前宝宝的相关信息：

{context}
"""

    def __init__(self, baby: Baby, user_id: int):
        self.baby = baby
        self.user_id = user_id
        self.context_collector = ContextCollector(baby, user_id)
        self.llm_service = LLMService()
        self.tool_executor = ToolExecutor(baby, user_id)

    def chat_stream(
        self,
        message: str,
        conversation_id: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式对话处理

        Args:
            message: 用户消息
            conversation_id: 对话ID

        Yields:
            流式响应块:
            - {'type': 'text', 'content': '...'} - 文本内容
            - {'type': 'tool_calling', 'tool': '...'} - 正在调用工具
            - {'type': 'tool_result', 'tool': '...', 'success': bool, 'result': {...}} - 工具结果
            - {'type': 'error', 'content': '...'} - 错误
            - {'type': 'done'} - 结束
        """
        # 获取或创建对话
        conversation = conversation_store.get(conversation_id)
        if not conversation:
            conversation = {
                'id': conversation_id,
                'baby_id': self.baby.id,
                'messages': [],
                'created_at': datetime.now()
            }
            conversation_store.set(conversation_id, conversation)

        # 构建消息列表
        context_prompt = self.context_collector.to_prompt()
        system_message = {
            'role': 'system',
            'content': self.SYSTEM_PROMPT.format(context=context_prompt)
        }

        # 历史消息 + 当前消息
        messages = [system_message] + conversation['messages'] + [
            {'role': 'user', 'content': message}
        ]

        # 添加用户消息到历史
        conversation['messages'].append({'role': 'user', 'content': message})

        # 调用LLM
        full_content = ''

        for chunk in self.llm_service.chat_stream(messages, tools=TOOLS, model_type='fast'):
            if chunk['type'] == 'text':
                full_content += chunk['content']
                yield {'type': 'text', 'content': chunk['content']}

            elif chunk['type'] == 'tool_call':
                tool = chunk['tool']
                tool_name = tool.get('name', '')
                yield {'type': 'tool_calling', 'tool': tool_name}

                # 解析参数
                try:
                    arguments = json.loads(tool.get('arguments', '{}'))
                except json.JSONDecodeError:
                    arguments = {}

                # 执行工具
                success, result = self.tool_executor.execute(tool_name, arguments)

                yield {
                    'type': 'tool_result',
                    'tool': tool_name,
                    'success': success,
                    'result': result
                }

                # 根据工具结果决定下一步
                if result.get('type') == 'clarification':
                    # 需要追问
                    question = result.get('question', '')
                    yield {'type': 'text', 'content': question}
                    full_content = question

                elif result.get('type') == 'answer':
                    # 需要使用高级模型回答
                    yield from self._answer_with_advanced_model(
                        message, conversation, context_prompt
                    )
                    return

                elif success:
                    # 工具执行成功，生成确认消息
                    confirm_msg = result.get('message', '操作完成')
                    note = result.get('note', '')
                    if note:
                        confirm_msg += f"\n\n💡 {note}"
                    yield {'type': 'text', 'content': confirm_msg}
                    full_content = confirm_msg

                else:
                    # 工具执行失败
                    error_msg = result.get('error', '操作失败，请稍后重试')
                    yield {'type': 'text', 'content': f"抱歉，{error_msg}"}
                    full_content = f"抱歉，{error_msg}"

            elif chunk['type'] == 'error':
                yield {'type': 'error', 'content': chunk.get('content', '服务暂时不可用')}
                return

            elif chunk['type'] == 'done':
                break

        # 更新对话历史
        if full_content:
            conversation['messages'].append({
                'role': 'assistant',
                'content': full_content
            })
            conversation_store.update_messages(conversation_id, conversation['messages'])

        yield {'type': 'done'}

    def _answer_with_advanced_model(
        self,
        question: str,
        conversation: Dict,
        context_prompt: str
    ) -> Generator[Dict[str, Any], None, None]:
        """使用高级模型回答复杂问题"""
        system_message = {
            'role': 'system',
            'content': f"""你是一位专业、友好的育儿顾问。请基于以下宝宝信息，回答家长的问题。

回答要求：
1. 专业、准确、易懂
2. 考虑宝宝的月龄给出适合的建议
3. 如果涉及医学问题，建议咨询专业医生
4. 语气亲切友好

{context_prompt}
"""
        }

        messages = [system_message, {'role': 'user', 'content': question}]

        full_content = ''
        for chunk in self.llm_service.chat_stream(messages, model_type='advanced'):
            if chunk['type'] == 'text':
                full_content += chunk['content']
                yield {'type': 'text', 'content': chunk['content']}
            elif chunk['type'] in ('finish', 'done'):
                break
            elif chunk['type'] == 'error':
                yield {'type': 'error', 'content': chunk.get('content', '服务暂时不可用')}
                return

        # 更新对话历史
        if full_content:
            conversation['messages'].append({
                'role': 'assistant',
                'content': full_content
            })
            conversation_store.update_messages(conversation['id'], conversation['messages'])

        yield {'type': 'done'}

    def get_conversation_messages(self, conversation_id: str) -> List[Dict[str, str]]:
        """获取对话历史消息"""
        conversation = conversation_store.get(conversation_id)
        if not conversation:
            return []
        return conversation.get('messages', [])
