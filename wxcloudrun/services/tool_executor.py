"""
工具执行器 - 执行Agent调用的工具
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Tuple

from wxcloudrun import dao
from wxcloudrun.model import Baby, MealPlan, SpecialStatus

logger = logging.getLogger('log')


# 工具定义 (OpenAI Function Calling格式)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_special_status",
            "description": "记录宝宝的特殊状态，如生病、打疫苗等。创建后2周内不会添加新食材。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_type": {
                        "type": "string",
                        "enum": ["sick", "vaccine", "other"],
                        "description": "状态类型: sick=生病, vaccine=打疫苗, other=其他"
                    },
                    "description": {
                        "type": "string",
                        "description": "状态描述，如具体症状、疫苗名称等"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "开始日期，格式YYYY-MM-DD。如果用户没有明确说明，应该询问用户确认。"
                    },
                    "duration_days": {
                        "type": "integer",
                        "description": "持续天数，默认14天",
                        "default": 14
                    }
                },
                "required": ["status_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_meal_record",
            "description": "记录宝宝吃了什么。用于记录已经发生的进食情况。",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_date": {
                        "type": "string",
                        "description": "进食日期，格式YYYY-MM-DD。如果用户没有明确说明，应该询问用户确认。"
                    },
                    "meal_type": {
                        "type": "string",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                        "description": "餐次: breakfast=早餐, lunch=午餐, dinner=晚餐, snack=加餐"
                    },
                    "food_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "食材名称列表"
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注，如宝宝的反应、进食量等"
                    }
                },
                "required": ["meal_type", "food_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "report_allergy",
            "description": "记录宝宝对某种食材的过敏反应。记录后该食材将不会出现在未来的辅食计划中。",
            "parameters": {
                "type": "object",
                "properties": {
                    "food_name": {
                        "type": "string",
                        "description": "引起过敏的食材名称"
                    },
                    "symptoms": {
                        "type": "string",
                        "description": "过敏症状，如皮疹、腹泻、呕吐等"
                    },
                    "occurrence_date": {
                        "type": "string",
                        "description": "过敏发生日期，格式YYYY-MM-DD"
                    }
                },
                "required": ["food_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "当用户输入信息不完整时，向用户询问补充信息。例如：缺少日期、餐次、具体食材等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要询问用户的问题，使用友好亲切的语气"
                    },
                    "missing_info": {
                        "type": "string",
                        "enum": ["date", "meal_type", "food_name", "symptoms", "other"],
                        "description": "缺少的信息类型"
                    }
                },
                "required": ["question", "missing_info"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": "回答用户关于宝宝喂养、健康、早教等综合问题。当用户的问题不属于记录类操作时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question_type": {
                        "type": "string",
                        "enum": ["feeding", "health", "development", "sleep", "other"],
                        "description": "问题类型: feeding=喂养, health=健康, development=发育/早教, sleep=睡眠, other=其他"
                    },
                    "use_advanced_model": {
                        "type": "boolean",
                        "description": "是否使用高级模型回答。对于复杂的健康、早教问题建议使用。",
                        "default": True
                    }
                },
                "required": ["question_type"]
            }
        }
    }
]


class ToolExecutor:
    """工具执行器"""

    def __init__(self, baby: Baby, user_id: int):
        self.baby = baby
        self.user_id = user_id

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        执行工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            (success, result): 是否成功和结果数据
        """
        method = getattr(self, f'_execute_{tool_name}', None)
        if not method:
            return False, {'error': f'未知工具: {tool_name}'}

        try:
            return method(arguments)
        except Exception as e:
            logger.error(f"Tool execution error: {tool_name} - {e}", exc_info=True)
            return False, {'error': str(e)}

    def _execute_create_special_status(self, args: Dict[str, Any]) -> Tuple[bool, Dict]:
        """创建特殊状态"""
        status_type = args.get('status_type')
        description = args.get('description')
        start_date_str = args.get('start_date')
        duration_days = args.get('duration_days', 14)

        if not status_type:
            return False, {'error': '缺少状态类型'}

        # 解析日期
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                return False, {'error': '日期格式错误，请使用YYYY-MM-DD格式'}
        else:
            start_date = date.today()

        # 检查是否已有活跃的特殊状态
        existing = dao.get_active_special_status(self.baby.id)
        if existing:
            status_name = SpecialStatus.STATUS_TYPE_NAMES.get(
                existing.status_type, existing.status_type
            )
            return False, {
                'error': f'已存在特殊状态: {status_name}，将在{existing.get_days_remaining()}天后结束。如需记录新状态，请先结束当前状态。'
            }

        status = dao.create_special_status(
            baby_id=self.baby.id,
            status_type=status_type,
            created_by=self.user_id,
            description=description,
            duration_days=duration_days
        )

        if not status:
            return False, {'error': '创建失败，请稍后重试'}

        status_names = {'sick': '生病', 'vaccine': '打疫苗', 'other': '其他'}
        return True, {
            'action': 'create_special_status',
            'message': f"已记录{self.baby.name}的{status_names.get(status_type, status_type)}状态",
            'data': status.to_dict(),
            'note': '2周内将暂停添加新食材，确保宝宝安全'
        }

    def _execute_create_meal_record(self, args: Dict[str, Any]) -> Tuple[bool, Dict]:
        """创建进食记录"""
        meal_date_str = args.get('meal_date')
        meal_type = args.get('meal_type')
        food_names = args.get('food_names', [])
        notes = args.get('notes')

        if not meal_type:
            return False, {'error': '缺少餐次信息'}

        if not food_names:
            return False, {'error': '缺少食材信息'}

        # 解析日期
        if meal_date_str:
            try:
                meal_date = datetime.strptime(meal_date_str, '%Y-%m-%d').date()
            except ValueError:
                return False, {'error': '日期格式错误，请使用YYYY-MM-DD格式'}
        else:
            meal_date = date.today()

        # 查找食材ID
        food_ids = []
        found_foods = []
        not_found = []

        for name in food_names:
            food = dao.get_food_by_name(name)
            if food:
                food_ids.append(food.id)
                found_foods.append(food.name)
            else:
                not_found.append(name)

        if not food_ids:
            return False, {
                'error': f'未在食材库中找到: {", ".join(food_names)}。请确认食材名称是否正确。'
            }

        # 创建或更新计划
        plan = dao.create_or_update_meal_plan(
            baby_id=self.baby.id,
            plan_date=meal_date,
            meal_type=meal_type,
            food_ids=food_ids,
            created_by=self.user_id,
            notes=notes,
            is_ai_generated=False
        )

        if not plan:
            return False, {'error': '保存失败，请稍后重试'}

        # 标记为已完成
        dao.complete_meal_plan(plan.id)

        meal_type_name = MealPlan.MEAL_TYPE_NAMES.get(meal_type, meal_type)
        result = {
            'action': 'create_meal_record',
            'message': f"已记录{meal_date.isoformat()} {meal_type_name}: {', '.join(found_foods)}",
            'data': {
                'date': meal_date.isoformat(),
                'meal_type': meal_type,
                'foods': found_foods
            }
        }

        if not_found:
            result['warning'] = f"以下食材未在食材库中找到: {', '.join(not_found)}"

        return True, result

    def _execute_report_allergy(self, args: Dict[str, Any]) -> Tuple[bool, Dict]:
        """报告过敏"""
        food_name = args.get('food_name')
        symptoms = args.get('symptoms')

        if not food_name:
            return False, {'error': '缺少食材名称'}

        # 查找食材
        food = dao.get_food_by_name(food_name)
        if not food:
            return False, {
                'error': f'未在食材库中找到: {food_name}。请确认食材名称是否正确。'
            }

        # 更新食材状态为过敏
        food_status = dao.create_or_update_baby_food_status(
            baby_id=self.baby.id,
            food_id=food.id,
            status='allergic',
            updated_by=self.user_id,
            allergy_symptoms=symptoms
        )

        if not food_status:
            return False, {'error': '记录失败，请稍后重试'}

        return True, {
            'action': 'report_allergy',
            'message': f"已记录{self.baby.name}对{food.name}过敏",
            'data': {
                'food': food.name,
                'symptoms': symptoms
            },
            'note': f'{food.name}已被标记为过敏食材，将不会出现在未来的辅食计划中'
        }

    def _execute_ask_clarification(self, args: Dict[str, Any]) -> Tuple[bool, Dict]:
        """询问补充信息"""
        return True, {
            'action': 'ask_clarification',
            'type': 'clarification',
            'question': args.get('question', '请提供更多信息'),
            'missing_info': args.get('missing_info', 'other')
        }

    def _execute_answer_question(self, args: Dict[str, Any]) -> Tuple[bool, Dict]:
        """回答综合问题 - 标记需要使用高级模型"""
        return True, {
            'action': 'answer_question',
            'type': 'answer',
            'question_type': args.get('question_type', 'other'),
            'use_advanced_model': args.get('use_advanced_model', True)
        }
