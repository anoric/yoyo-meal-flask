"""
辅食计划自动生成服务

根据宝宝月龄、已排敏食材、特殊状态等条件，自动生成一周的辅食计划。

业务规则:
1. 月龄→餐次: 6月=1顿(午餐), 7-8月=2顿(午+晚), 9月+=3顿(早+午+晚)
2. 排敏期: 新食材连续3天，若有同类备选食材则每天1餐即可，否则每餐都包含
3. 特殊状态: 生病/打疫苗期间不添加新食材
4. 添加顺序: 高铁米粉 → 肉泥 → 蔬菜 → 水果
5. 搭配原则: 尽量包含主食 + 蛋白质 + 蔬菜/水果
"""
import logging
import random
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple, Set

from wxcloudrun import dao
from wxcloudrun.model import Baby, Food, BabyFoodStatus, SpecialStatus

logger = logging.getLogger('log')


class MealPlanGenerator:
    """辅食计划生成器"""

    # 食材添加优先级顺序（数字越小优先级越高）
    FOOD_INTRODUCTION_ORDER = {
        'staple': 1,     # 高铁米粉等主食最先
        'meat': 2,       # 肉泥第二（补铁）
        'vegetable': 3,  # 蔬菜第三
        'fruit': 4,      # 水果第四
        'dairy': 5,      # 蛋奶
        'seafood': 6     # 海鲜最后
    }

    # 月龄对应的每日餐次
    # 6个月: 1顿午餐
    # 7-8个月: 2顿（午餐+晚餐）
    # 9个月+: 3顿（早餐+午餐+晚餐）
    MEALS_BY_AGE = {
        6: ['lunch'],
        7: ['lunch', 'dinner'],
        8: ['lunch', 'dinner'],
    }
    # 9个月及以上默认3顿
    DEFAULT_MEALS = ['breakfast', 'lunch', 'dinner']

    # 排敏天数
    TESTING_DAYS = 3

    # 蛋白质类别（用于搭配）
    PROTEIN_CATEGORIES = ['meat', 'dairy', 'seafood']

    def __init__(self, baby: Baby, user_id: int):
        """
        初始化生成器

        Args:
            baby: 宝宝对象
            user_id: 操作用户ID
        """
        self.baby = baby
        self.user_id = user_id
        self.age_months = baby.get_age_months()

        # 缓存
        self._safe_foods: Optional[List[Food]] = None
        self._safe_foods_by_category: Optional[Dict[str, List[Food]]] = None
        self._testing_food: Optional[BabyFoodStatus] = None
        self._special_status: Optional[SpecialStatus] = None
        self._all_food_statuses: Optional[List[BabyFoodStatus]] = None

    def get_missing_dates(self) -> List[date]:
        """
        获取未来7天中缺少计划的日期列表

        Returns:
            缺少计划的日期列表
        """
        today = date.today()
        meals = self._get_meals_for_age()

        # 获取未来7天已有的计划
        end_date = today + timedelta(days=6)
        existing_plans = dao.get_meal_plans_by_date_range(self.baby.id, today, end_date)

        # 按日期统计已有计划
        plans_by_date: Dict[date, Set[str]] = {}
        for plan in existing_plans:
            if plan.plan_date not in plans_by_date:
                plans_by_date[plan.plan_date] = set()
            plans_by_date[plan.plan_date].add(plan.meal_type)

        # 找出缺少计划的日期（该日期缺少任意一餐）
        missing_dates = []
        for i in range(7):
            check_date = today + timedelta(days=i)
            existing_meals = plans_by_date.get(check_date, set())
            # 如果该日期缺少任何一餐，则视为需要补全
            if not existing_meals or not all(meal in existing_meals for meal in meals):
                missing_dates.append(check_date)

        return missing_dates

    def generate_and_save(self, target_dates: List[date] = None) -> int:
        """
        生成并保存辅食计划

        Args:
            target_dates: 要生成计划的日期列表，默认为未来7天缺失的日期

        Returns:
            成功创建的计划数量
        """
        if target_dates is None:
            target_dates = self.get_missing_dates()

        logger.info(f"[MealPlanGenerator] 宝宝 {self.baby.id} 月龄: {self.age_months}, 缺失日期: {target_dates}")

        if not target_dates:
            logger.info(f"[MealPlanGenerator] 宝宝 {self.baby.id} 没有缺失的计划日期")
            return 0

        # 生成计划
        plans = self._generate_plans(target_dates)

        logger.info(f"[MealPlanGenerator] 宝宝 {self.baby.id} 生成了 {len(plans)} 个计划")

        if not plans:
            return 0

        # 批量保存
        count = dao.batch_create_meal_plans(plans, self.baby.id, self.user_id)
        logger.info(f"为宝宝 {self.baby.id} 生成了 {count} 个辅食计划")

        return count

    def _generate_plans(self, target_dates: List[date]) -> List[Dict]:
        """
        生成指定日期的辅食计划

        Args:
            target_dates: 目标日期列表

        Returns:
            计划数据列表
        """
        plans = []
        meals = self._get_meals_for_age()
        safe_foods = self._get_safe_foods()
        special_status = self._get_special_status()
        testing_status = self._get_testing_food()

        logger.info(f"[MealPlanGenerator] 开始生成计划: 宝宝={self.baby.id}, 餐次={meals}, 安全食材数={len(safe_foods)}")

        # 跟踪排敏状态
        current_testing_food: Optional[Food] = None
        testing_end_date: Optional[date] = None
        testing_food_added_today = False

        if testing_status:
            current_testing_food = dao.get_food_by_id(testing_status.food_id)
            testing_end_date = testing_status.testing_end_date
            logger.info(f"[MealPlanGenerator] 已有排敏中食材: {current_testing_food.name if current_testing_food else 'None'}, 结束日期: {testing_end_date}")

        for plan_date in sorted(target_dates):
            testing_food_added_today = False

            # 判断当天是否在排敏期内
            in_testing_period = (
                current_testing_food and
                testing_end_date and
                plan_date <= testing_end_date
            )

            # 判断是否可以添加新食材
            can_add_new = not special_status and not in_testing_period

            # 如果排敏期结束且可以添加新食材，选择下一个新食材
            if can_add_new and not in_testing_period:
                next_food = self._select_next_new_food()
                if next_food:
                    logger.info(f"[MealPlanGenerator] 宝宝 {self.baby.id} 在 {plan_date} 开始排敏: {next_food.name} (id={next_food.id})")
                    current_testing_food = next_food
                    testing_end_date = plan_date + timedelta(days=self.TESTING_DAYS - 1)
                    in_testing_period = True
                    # 开始排敏
                    dao.start_food_testing(self.baby.id, next_food.id, self.user_id, self.TESTING_DAYS)
                    # 刷新所有缓存
                    self._safe_foods = None
                    self._safe_foods_by_category = None
                    self._all_food_statuses = None  # 重要：刷新食材状态缓存
                    safe_foods = self._get_safe_foods()

            # 检查是否有同类备选食材
            has_same_category_backup = False
            if current_testing_food:
                category_foods = self._get_safe_foods_by_category().get(current_testing_food.category, [])
                has_same_category_backup = len(category_foods) > 0

            # 为每餐生成计划
            for meal_type in meals:
                # 判断这餐是否需要包含新食材
                include_new_food = False
                if in_testing_period and current_testing_food:
                    if has_same_category_backup:
                        # 有备选，每天只在第一餐包含新食材
                        if not testing_food_added_today:
                            include_new_food = True
                            testing_food_added_today = True
                    else:
                        # 无备选，每餐都包含
                        include_new_food = True

                # 组合食材
                food_ids, new_food_id = self._compose_meal(
                    safe_foods,
                    current_testing_food if include_new_food else None
                )

                if food_ids:
                    plans.append({
                        'plan_date': plan_date,
                        'meal_type': meal_type,
                        'food_ids': food_ids,
                        'new_food_id': new_food_id
                    })

        return plans

    def _get_meals_for_age(self) -> List[str]:
        """根据月龄获取每日餐次"""
        if self.age_months in self.MEALS_BY_AGE:
            return self.MEALS_BY_AGE[self.age_months]
        elif self.age_months >= 9:
            return self.DEFAULT_MEALS
        else:
            # 小于6个月不应该添加辅食，但为安全起见返回午餐
            return ['lunch']

    def _get_safe_foods(self) -> List[Food]:
        """获取已安全排敏的食材"""
        if self._safe_foods is not None:
            return self._safe_foods

        safe_statuses = dao.get_baby_food_statuses(self.baby.id, status='safe')
        safe_food_ids = [s.food_id for s in safe_statuses]

        if safe_food_ids:
            self._safe_foods = dao.get_foods_by_ids(safe_food_ids)
        else:
            self._safe_foods = []

        return self._safe_foods

    def _get_safe_foods_by_category(self) -> Dict[str, List[Food]]:
        """获取按类别分组的安全食材"""
        if self._safe_foods_by_category is not None:
            return self._safe_foods_by_category

        safe_foods = self._get_safe_foods()
        self._safe_foods_by_category = {}

        for food in safe_foods:
            if food.category not in self._safe_foods_by_category:
                self._safe_foods_by_category[food.category] = []
            self._safe_foods_by_category[food.category].append(food)

        return self._safe_foods_by_category

    def _get_testing_food(self) -> Optional[BabyFoodStatus]:
        """获取正在排敏的食材状态"""
        if self._testing_food is None:
            self._testing_food = dao.get_baby_testing_food(self.baby.id)
        return self._testing_food

    def _get_special_status(self) -> Optional[SpecialStatus]:
        """获取活跃的特殊状态"""
        if self._special_status is None:
            self._special_status = dao.get_active_special_status(self.baby.id)
        return self._special_status

    def _get_all_food_statuses(self) -> List[BabyFoodStatus]:
        """获取所有食材状态"""
        if self._all_food_statuses is None:
            self._all_food_statuses = dao.get_baby_food_statuses(self.baby.id)
        return self._all_food_statuses

    def _select_next_new_food(self) -> Optional[Food]:
        """
        选择下一个要排敏的新食材

        规则:
        1. 如果有特殊状态，返回None
        2. 按照优先级顺序选择：主食(高铁米粉优先) → 肉泥 → 蔬菜 → 水果 → 蛋奶 → 海鲜
        3. 食材必须适合当前月龄
        4. 优先选择低过敏风险的食材
        """
        # 检查特殊状态
        if self._get_special_status():
            logger.info(f"[MealPlanGenerator] 宝宝 {self.baby.id} 有特殊状态，不添加新食材")
            return None

        # 获取已有状态的食材ID
        all_statuses = self._get_all_food_statuses()
        known_food_ids = {s.food_id for s in all_statuses}

        # 获取当前月龄可用的所有食材
        available_foods = dao.get_all_foods(max_month=self.age_months)
        logger.info(f"[MealPlanGenerator] 宝宝 {self.baby.id} 月龄 {self.age_months}, 可用食材数: {len(available_foods)}, 已知食材数: {len(known_food_ids)}")

        # 过滤掉已知的食材
        candidate_foods = [f for f in available_foods if f.id not in known_food_ids]

        if not candidate_foods:
            logger.info(f"[MealPlanGenerator] 宝宝 {self.baby.id} 没有可选的新食材")
            return None

        # 特殊处理：如果没有任何安全食材，优先选择高铁米粉
        safe_foods = self._get_safe_foods()
        if not safe_foods:
            iron_rice = next((f for f in candidate_foods if f.name == '高铁米粉'), None)
            if iron_rice:
                return iron_rice

        # 按照引入顺序和过敏风险排序
        def food_priority(food: Food) -> tuple:
            category_priority = self.FOOD_INTRODUCTION_ORDER.get(food.category, 99)
            return (category_priority, food.allergy_risk, food.sort_order)

        candidate_foods.sort(key=food_priority)

        return candidate_foods[0] if candidate_foods else None

    def _compose_meal(
        self,
        safe_foods: List[Food],
        new_food: Optional[Food] = None
    ) -> Tuple[List[int], Optional[int]]:
        """
        组合一餐的食材

        规则:
        1. 如果有新食材，必须包含新食材
        2. 尽量包含：主食 + 蛋白质(肉/蛋/奶/海鲜) + 蔬菜/水果
        3. 根据已排敏食材的丰富程度调整

        Args:
            safe_foods: 安全食材列表
            new_food: 新食材（正在排敏的）

        Returns:
            (food_ids, new_food_id): 食材ID列表和新食材ID
        """
        food_ids: List[int] = []
        new_food_id: Optional[int] = None
        used_categories: Set[str] = set()

        # 按类别分组安全食材
        foods_by_category = self._get_safe_foods_by_category()

        # 1. 如果有新食材，加入
        if new_food:
            food_ids.append(new_food.id)
            new_food_id = new_food.id
            used_categories.add(new_food.category)

        # 2. 添加主食（必须）
        if 'staple' not in used_categories and 'staple' in foods_by_category:
            staple = self._random_choice(foods_by_category['staple'])
            food_ids.append(staple.id)
            used_categories.add('staple')

        # 3. 添加蛋白质（如果有）
        for cat in self.PROTEIN_CATEGORIES:
            if cat not in used_categories and cat in foods_by_category:
                protein = self._random_choice(foods_by_category[cat])
                food_ids.append(protein.id)
                used_categories.add(cat)
                break  # 只添加一种蛋白质

        # 4. 添加蔬菜或水果（如果有）
        for cat in ['vegetable', 'fruit']:
            if cat not in used_categories and cat in foods_by_category:
                veg_fruit = self._random_choice(foods_by_category[cat])
                food_ids.append(veg_fruit.id)
                used_categories.add(cat)
                break  # 只添加一种

        # 如果没有任何食材但有新食材，至少返回新食材
        if not food_ids and new_food:
            food_ids = [new_food.id]
            new_food_id = new_food.id

        return food_ids, new_food_id

    @staticmethod
    def _random_choice(foods: List[Food]) -> Food:
        """从食材列表中随机选择一个"""
        return random.choice(foods) if foods else None
