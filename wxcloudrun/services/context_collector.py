"""
上下文收集器 - 为Agent收集宝宝相关上下文信息
"""
from datetime import date, timedelta, datetime
from typing import Dict, List, Any

from wxcloudrun import dao
from wxcloudrun.model import Baby, MealPlan, SpecialStatus


class ContextCollector:
    """上下文收集器 - 收集宝宝相关信息作为Agent的上下文"""

    def __init__(self, baby: Baby, user_id: int):
        self.baby = baby
        self.user_id = user_id

    def collect(self) -> Dict[str, Any]:
        """收集完整上下文"""
        return {
            'baby_info': self._get_baby_info(),
            'recent_meals': self._get_recent_meals(),
            'future_meals': self._get_future_meals(),
            'recent_events': self._get_recent_events(),
            'food_status_summary': self._get_food_status_summary(),
            'current_date': date.today().isoformat(),
            'current_time': datetime.now().strftime('%H:%M')
        }

    def _get_baby_info(self) -> Dict[str, Any]:
        """获取宝宝基础信息"""
        gender_map = {0: '宝宝', 1: '男宝', 2: '女宝'}
        return {
            'name': self.baby.name,
            'age_months': self.baby.get_age_months(),
            'gender': gender_map.get(self.baby.gender, '宝宝'),
            'birthday': self.baby.birthday.isoformat() if self.baby.birthday else None,
            'allergy_notes': self.baby.allergy_notes,
            'food_preferences': self.baby.food_preferences
        }

    def _get_recent_meals(self) -> List[Dict[str, Any]]:
        """获取过去7天的辅食记录"""
        today = date.today()
        start_date = today - timedelta(days=7)
        plans = dao.get_meal_plans_by_date_range(
            self.baby.id, start_date, today - timedelta(days=1)
        )

        result = []
        for plan in plans:
            food_ids = plan.get_food_id_list()
            foods = dao.get_foods_by_ids(food_ids)
            food_names = [f.name for f in foods]

            result.append({
                'date': plan.plan_date.isoformat() if plan.plan_date else None,
                'meal_type': plan.meal_type,
                'meal_type_name': MealPlan.MEAL_TYPE_NAMES.get(plan.meal_type, plan.meal_type),
                'foods': food_names,
                'is_completed': plan.is_completed
            })

        return result

    def _get_future_meals(self) -> List[Dict[str, Any]]:
        """获取未来7天的辅食计划"""
        today = date.today()
        end_date = today + timedelta(days=7)
        plans = dao.get_meal_plans_by_date_range(self.baby.id, today, end_date)

        result = []
        for plan in plans:
            food_ids = plan.get_food_id_list()
            foods = dao.get_foods_by_ids(food_ids)
            food_names = [f.name for f in foods]

            new_food_name = None
            if plan.new_food_id:
                new_food = dao.get_food_by_id(plan.new_food_id)
                new_food_name = new_food.name if new_food else None

            result.append({
                'date': plan.plan_date.isoformat() if plan.plan_date else None,
                'meal_type': plan.meal_type,
                'meal_type_name': MealPlan.MEAL_TYPE_NAMES.get(plan.meal_type, plan.meal_type),
                'foods': food_names,
                'new_food': new_food_name
            })

        return result

    def _get_recent_events(self) -> List[Dict[str, Any]]:
        """获取近期事件(特殊状态、过敏记录、排敏中的食材)"""
        events = []

        # 当前特殊状态
        special_status = dao.get_active_special_status(self.baby.id)
        if special_status:
            events.append({
                'type': 'special_status',
                'status_type': special_status.status_type,
                'status_name': SpecialStatus.STATUS_TYPE_NAMES.get(
                    special_status.status_type, special_status.status_type
                ),
                'start_date': special_status.start_date.isoformat() if special_status.start_date else None,
                'end_date': special_status.end_date.isoformat() if special_status.end_date else None,
                'days_remaining': special_status.get_days_remaining(),
                'description': special_status.description
            })

        # 正在排敏的食材
        testing_food = dao.get_baby_testing_food(self.baby.id)
        if testing_food:
            food = dao.get_food_by_id(testing_food.food_id)
            events.append({
                'type': 'food_testing',
                'food_name': food.name if food else '未知',
                'start_date': testing_food.testing_start_date.isoformat() if testing_food.testing_start_date else None,
                'end_date': testing_food.testing_end_date.isoformat() if testing_food.testing_end_date else None,
                'days_remaining': testing_food.get_testing_days_remaining()
            })

        # 最近的过敏记录(最近3条)
        allergic_statuses = dao.get_baby_food_statuses(self.baby.id, status='allergic')
        for status in allergic_statuses[-3:]:
            food = dao.get_food_by_id(status.food_id)
            events.append({
                'type': 'allergy',
                'food_name': food.name if food else '未知',
                'symptoms': status.allergy_symptoms,
                'date': status.updated_at.date().isoformat() if status.updated_at else None
            })

        return events

    def _get_food_status_summary(self) -> Dict[str, Any]:
        """获取食材状态摘要"""
        all_statuses = dao.get_baby_food_statuses(self.baby.id)

        safe_foods = []
        allergic_foods = []

        for status in all_statuses:
            food = dao.get_food_by_id(status.food_id)
            if not food:
                continue
            if status.status == 'safe':
                safe_foods.append(food.name)
            elif status.status == 'allergic':
                allergic_foods.append(food.name)

        return {
            'safe_count': len(safe_foods),
            'safe_foods': safe_foods,
            'allergic_count': len(allergic_foods),
            'allergic_foods': allergic_foods
        }

    def to_prompt(self) -> str:
        """将上下文转换为Prompt格式"""
        ctx = self.collect()

        # 构建宝宝基本信息部分
        prompt = f"""## 宝宝信息
- 姓名: {ctx['baby_info']['name']}
- 月龄: {ctx['baby_info']['age_months']}个月
- 性别: {ctx['baby_info']['gender']}
- 出生日期: {ctx['baby_info']['birthday']}

## 当前时间
{ctx['current_date']} {ctx['current_time']}

## 食材状态
- 已安全添加: {ctx['food_status_summary']['safe_count']}种"""

        if ctx['food_status_summary']['safe_foods']:
            safe_display = ', '.join(ctx['food_status_summary']['safe_foods'][:10])
            if len(ctx['food_status_summary']['safe_foods']) > 10:
                safe_display += '...'
            prompt += f" ({safe_display})"
        else:
            prompt += " (暂无)"

        prompt += f"\n- 过敏食材: {ctx['food_status_summary']['allergic_count']}种"
        if ctx['food_status_summary']['allergic_foods']:
            prompt += f" ({', '.join(ctx['food_status_summary']['allergic_foods'])})"
        else:
            prompt += " (暂无)"

        # 近期事件
        prompt += "\n\n## 近期事件\n"
        if ctx['recent_events']:
            for event in ctx['recent_events']:
                if event['type'] == 'special_status':
                    prompt += f"- 【特殊状态】{event['status_name']}: {event['start_date']} ~ {event['end_date']}, 剩余{event['days_remaining']}天\n"
                elif event['type'] == 'food_testing':
                    prompt += f"- 【排敏中】{event['food_name']}: 剩余{event['days_remaining']}天\n"
                elif event['type'] == 'allergy':
                    symptoms = event['symptoms'] or '无症状记录'
                    prompt += f"- 【过敏记录】{event['food_name']}: {symptoms} ({event['date']})\n"
        else:
            prompt += "暂无特殊事件\n"

        # 过去7天食谱
        prompt += "\n## 过去7天食谱\n"
        if ctx['recent_meals']:
            for meal in ctx['recent_meals']:
                status = "已完成" if meal['is_completed'] else "未完成"
                foods_str = ', '.join(meal['foods']) if meal['foods'] else '无'
                prompt += f"- {meal['date']} {meal['meal_type_name']}: {foods_str} [{status}]\n"
        else:
            prompt += "暂无记录\n"

        # 未来7天计划
        prompt += "\n## 未来7天计划\n"
        if ctx['future_meals']:
            for meal in ctx['future_meals']:
                foods_str = ', '.join(meal['foods']) if meal['foods'] else '无'
                new_mark = f" 【新食材: {meal['new_food']}】" if meal.get('new_food') else ""
                prompt += f"- {meal['date']} {meal['meal_type_name']}: {foods_str}{new_mark}\n"
        else:
            prompt += "暂无计划\n"

        return prompt
