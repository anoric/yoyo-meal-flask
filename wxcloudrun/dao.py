import logging
from datetime import datetime, date, timedelta
from typing import Optional, List

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy import and_, or_

from wxcloudrun import db
from wxcloudrun.model import (
    User, Baby, BabyManager, Food, BabyFoodStatus,
    MealPlan, SpecialStatus, Invitation
)

# 初始化日志
logger = logging.getLogger('log')


# ==========================================
# 用户相关 DAO
# ==========================================

def get_user_by_id(user_id: int) -> Optional[User]:
    """根据ID获取用户"""
    try:
        return User.query.get(user_id)
    except OperationalError as e:
        logger.error(f"get_user_by_id error: {e}")
        return None


def get_user_by_openid(openid: str) -> Optional[User]:
    """根据openid获取用户"""
    try:
        return User.query.filter(User.openid == openid).first()
    except OperationalError as e:
        logger.error(f"get_user_by_openid error: {e}")
        return None


def get_user_by_token(token: str) -> Optional[User]:
    """根据token获取用户"""
    try:
        return User.query.filter(
            User.token == token,
            User.token_expires_at > datetime.now()
        ).first()
    except OperationalError as e:
        logger.error(f"get_user_by_token error: {e}")
        return None


def create_user(openid: str, nickname: str = None, avatar_url: str = None) -> Optional[User]:
    """创建用户"""
    try:
        user = User(
            openid=openid,
            nickname=nickname,
            avatar_url=avatar_url
        )
        db.session.add(user)
        db.session.commit()
        return user
    except SQLAlchemyError as e:
        logger.error(f"create_user error: {e}")
        db.session.rollback()
        return None


def update_user(user: User) -> bool:
    """更新用户"""
    try:
        db.session.commit()
        return True
    except OperationalError as e:
        logger.error(f"update_user error: {e}")
        db.session.rollback()
        return False


# ==========================================
# 宝宝相关 DAO
# ==========================================

def get_baby_by_id(baby_id: int) -> Optional[Baby]:
    """根据ID获取宝宝"""
    try:
        return Baby.query.get(baby_id)
    except OperationalError as e:
        logger.error(f"get_baby_by_id error: {e}")
        return None


def get_babies_by_user(user_id: int) -> List[Baby]:
    """获取用户管理的所有宝宝"""
    try:
        # 通过baby_managers表关联查询
        baby_ids = db.session.query(BabyManager.baby_id).filter(
            BabyManager.user_id == user_id
        ).all()
        baby_ids = [bid[0] for bid in baby_ids]

        if not baby_ids:
            return []

        return Baby.query.filter(Baby.id.in_(baby_ids)).all()
    except OperationalError as e:
        logger.error(f"get_babies_by_user error: {e}")
        return []


def create_baby(name: str, birthday: date, gender: int, created_by: int,
                avatar: str = None, allergy_notes: str = None,
                food_preferences: str = None) -> Optional[Baby]:
    """创建宝宝"""
    try:
        baby = Baby(
            name=name,
            birthday=birthday,
            gender=gender,
            created_by=created_by,
            avatar=avatar,
            allergy_notes=allergy_notes,
            food_preferences=food_preferences
        )
        db.session.add(baby)
        db.session.flush()  # 获取baby.id

        # 同时创建管理员关系
        manager = BabyManager(
            baby_id=baby.id,
            user_id=created_by,
            role='owner'
        )
        db.session.add(manager)
        db.session.commit()
        return baby
    except OperationalError as e:
        logger.error(f"create_baby error: {e}")
        db.session.rollback()
        return None


def update_baby(baby: Baby) -> bool:
    """更新宝宝信息"""
    try:
        db.session.commit()
        return True
    except OperationalError as e:
        logger.error(f"update_baby error: {e}")
        db.session.rollback()
        return False


def delete_baby(baby_id: int) -> bool:
    """删除宝宝及相关数据"""
    try:
        # 删除相关的管理员关系
        BabyManager.query.filter(BabyManager.baby_id == baby_id).delete()
        # 删除相关的食材状态
        BabyFoodStatus.query.filter(BabyFoodStatus.baby_id == baby_id).delete()
        # 删除相关的辅食计划
        MealPlan.query.filter(MealPlan.baby_id == baby_id).delete()
        # 删除相关的特殊状态
        SpecialStatus.query.filter(SpecialStatus.baby_id == baby_id).delete()
        # 删除相关的邀请
        Invitation.query.filter(Invitation.baby_id == baby_id).delete()
        # 删除宝宝
        Baby.query.filter(Baby.id == baby_id).delete()

        db.session.commit()
        return True
    except OperationalError as e:
        logger.error(f"delete_baby error: {e}")
        db.session.rollback()
        return False


# ==========================================
# 宝宝管理员相关 DAO
# ==========================================

def get_baby_manager(baby_id: int, user_id: int) -> Optional[BabyManager]:
    """获取宝宝管理员关系"""
    try:
        return BabyManager.query.filter(
            BabyManager.baby_id == baby_id,
            BabyManager.user_id == user_id
        ).first()
    except OperationalError as e:
        logger.error(f"get_baby_manager error: {e}")
        return None


def get_baby_managers(baby_id: int) -> List[BabyManager]:
    """获取宝宝的所有管理员"""
    try:
        return BabyManager.query.filter(BabyManager.baby_id == baby_id).all()
    except OperationalError as e:
        logger.error(f"get_baby_managers error: {e}")
        return []


def add_baby_manager(baby_id: int, user_id: int, invited_by: int) -> Optional[BabyManager]:
    """添加宝宝管理员"""
    try:
        manager = BabyManager(
            baby_id=baby_id,
            user_id=user_id,
            role='manager',
            invited_by=invited_by
        )
        db.session.add(manager)
        db.session.commit()
        return manager
    except OperationalError as e:
        logger.error(f"add_baby_manager error: {e}")
        db.session.rollback()
        return None


def remove_baby_manager(baby_id: int, user_id: int) -> bool:
    """移除宝宝管理员"""
    try:
        BabyManager.query.filter(
            BabyManager.baby_id == baby_id,
            BabyManager.user_id == user_id
        ).delete()
        db.session.commit()
        return True
    except OperationalError as e:
        logger.error(f"remove_baby_manager error: {e}")
        db.session.rollback()
        return False


# ==========================================
# 食材相关 DAO
# ==========================================

def get_all_foods(category: str = None, max_month: int = None) -> List[Food]:
    """获取食材列表"""
    try:
        query = Food.query.filter(Food.is_active == True)

        if category:
            query = query.filter(Food.category == category)

        if max_month is not None:
            query = query.filter(Food.min_month <= max_month)

        return query.order_by(Food.sort_order).all()
    except OperationalError as e:
        logger.error(f"get_all_foods error: {e}")
        return []


def get_food_by_id(food_id: int) -> Optional[Food]:
    """根据ID获取食材"""
    try:
        return Food.query.get(food_id)
    except OperationalError as e:
        logger.error(f"get_food_by_id error: {e}")
        return None


def get_foods_by_ids(food_ids: List[int]) -> List[Food]:
    """根据ID列表获取食材"""
    try:
        if not food_ids:
            return []
        return Food.query.filter(Food.id.in_(food_ids)).all()
    except OperationalError as e:
        logger.error(f"get_foods_by_ids error: {e}")
        return []


# ==========================================
# 宝宝食材状态相关 DAO
# ==========================================

def get_baby_food_status(baby_id: int, food_id: int) -> Optional[BabyFoodStatus]:
    """获取宝宝的某个食材状态"""
    try:
        return BabyFoodStatus.query.filter(
            BabyFoodStatus.baby_id == baby_id,
            BabyFoodStatus.food_id == food_id
        ).first()
    except OperationalError as e:
        logger.error(f"get_baby_food_status error: {e}")
        return None


def get_baby_food_statuses(baby_id: int, status: str = None) -> List[BabyFoodStatus]:
    """获取宝宝的食材状态列表"""
    try:
        query = BabyFoodStatus.query.filter(BabyFoodStatus.baby_id == baby_id)

        if status:
            query = query.filter(BabyFoodStatus.status == status)

        return query.all()
    except OperationalError as e:
        logger.error(f"get_baby_food_statuses error: {e}")
        return []


def get_baby_testing_food(baby_id: int) -> Optional[BabyFoodStatus]:
    """获取宝宝正在排敏的食材"""
    try:
        today = date.today()
        return BabyFoodStatus.query.filter(
            BabyFoodStatus.baby_id == baby_id,
            BabyFoodStatus.status == 'testing',
            BabyFoodStatus.testing_end_date >= today
        ).first()
    except OperationalError as e:
        logger.error(f"get_baby_testing_food error: {e}")
        return None


def create_or_update_baby_food_status(
    baby_id: int,
    food_id: int,
    status: str,
    updated_by: int,
    testing_start_date: date = None,
    testing_end_date: date = None,
    allergy_symptoms: str = None,
    notes: str = None
) -> Optional[BabyFoodStatus]:
    """创建或更新宝宝食材状态"""
    try:
        food_status = get_baby_food_status(baby_id, food_id)

        if food_status:
            food_status.status = status
            food_status.updated_by = updated_by
            if testing_start_date:
                food_status.testing_start_date = testing_start_date
            if testing_end_date:
                food_status.testing_end_date = testing_end_date
            if allergy_symptoms:
                food_status.allergy_symptoms = allergy_symptoms
            if notes:
                food_status.notes = notes
            if status == 'allergic':
                food_status.allergy_count += 1
        else:
            food_status = BabyFoodStatus(
                baby_id=baby_id,
                food_id=food_id,
                status=status,
                updated_by=updated_by,
                testing_start_date=testing_start_date,
                testing_end_date=testing_end_date,
                allergy_symptoms=allergy_symptoms,
                notes=notes
            )
            db.session.add(food_status)

        db.session.commit()
        return food_status
    except OperationalError as e:
        logger.error(f"create_or_update_baby_food_status error: {e}")
        db.session.rollback()
        return None


def start_food_testing(baby_id: int, food_id: int, updated_by: int, days: int = 3) -> Optional[BabyFoodStatus]:
    """开始食材排敏"""
    today = date.today()
    end_date = today + timedelta(days=days)

    return create_or_update_baby_food_status(
        baby_id=baby_id,
        food_id=food_id,
        status='testing',
        updated_by=updated_by,
        testing_start_date=today,
        testing_end_date=end_date
    )


# ==========================================
# 辅食计划相关 DAO
# ==========================================

def get_meal_plans_by_date(baby_id: int, plan_date: date) -> List[MealPlan]:
    """获取某天的辅食计划"""
    try:
        return MealPlan.query.filter(
            MealPlan.baby_id == baby_id,
            MealPlan.plan_date == plan_date
        ).order_by(MealPlan.meal_type).all()
    except OperationalError as e:
        logger.error(f"get_meal_plans_by_date error: {e}")
        return []


def get_meal_plans_by_date_range(baby_id: int, start_date: date, end_date: date) -> List[MealPlan]:
    """获取日期范围内的辅食计划"""
    try:
        return MealPlan.query.filter(
            MealPlan.baby_id == baby_id,
            MealPlan.plan_date >= start_date,
            MealPlan.plan_date <= end_date
        ).order_by(MealPlan.plan_date, MealPlan.meal_type).all()
    except OperationalError as e:
        logger.error(f"get_meal_plans_by_date_range error: {e}")
        return []


def get_meal_plan(baby_id: int, plan_date: date, meal_type: str) -> Optional[MealPlan]:
    """获取某天某餐的辅食计划"""
    try:
        return MealPlan.query.filter(
            MealPlan.baby_id == baby_id,
            MealPlan.plan_date == plan_date,
            MealPlan.meal_type == meal_type
        ).first()
    except OperationalError as e:
        logger.error(f"get_meal_plan error: {e}")
        return None


def create_or_update_meal_plan(
    baby_id: int,
    plan_date: date,
    meal_type: str,
    food_ids: List[int],
    created_by: int,
    new_food_id: int = None,
    is_ai_generated: bool = False,
    notes: str = None
) -> Optional[MealPlan]:
    """创建或更新辅食计划"""
    try:
        plan = get_meal_plan(baby_id, plan_date, meal_type)

        if plan:
            plan.set_food_id_list(food_ids)
            plan.new_food_id = new_food_id
            plan.is_ai_generated = is_ai_generated
            plan.notes = notes
        else:
            plan = MealPlan(
                baby_id=baby_id,
                plan_date=plan_date,
                meal_type=meal_type,
                food_ids=','.join(str(fid) for fid in food_ids),
                new_food_id=new_food_id,
                is_ai_generated=is_ai_generated,
                notes=notes,
                created_by=created_by
            )
            db.session.add(plan)

        db.session.commit()
        return plan
    except OperationalError as e:
        logger.error(f"create_or_update_meal_plan error: {e}")
        db.session.rollback()
        return None


def complete_meal_plan(plan_id: int) -> bool:
    """标记辅食计划完成"""
    try:
        plan = MealPlan.query.get(plan_id)
        if plan:
            plan.is_completed = True
            plan.completed_at = datetime.now()
            db.session.commit()
            return True
        return False
    except OperationalError as e:
        logger.error(f"complete_meal_plan error: {e}")
        db.session.rollback()
        return False


def delete_meal_plan(plan_id: int) -> bool:
    """删除辅食计划"""
    try:
        MealPlan.query.filter(MealPlan.id == plan_id).delete()
        db.session.commit()
        return True
    except OperationalError as e:
        logger.error(f"delete_meal_plan error: {e}")
        db.session.rollback()
        return False


# ==========================================
# 特殊状态相关 DAO
# ==========================================

def get_active_special_status(baby_id: int) -> Optional[SpecialStatus]:
    """获取宝宝当前有效的特殊状态"""
    try:
        today = date.today()
        return SpecialStatus.query.filter(
            SpecialStatus.baby_id == baby_id,
            SpecialStatus.is_active == True,
            SpecialStatus.end_date >= today
        ).first()
    except OperationalError as e:
        logger.error(f"get_active_special_status error: {e}")
        return None


def create_special_status(
    baby_id: int,
    status_type: str,
    created_by: int,
    description: str = None,
    duration_days: int = 14
) -> Optional[SpecialStatus]:
    """创建特殊状态"""
    try:
        # 先结束之前的特殊状态
        SpecialStatus.query.filter(
            SpecialStatus.baby_id == baby_id,
            SpecialStatus.is_active == True
        ).update({'is_active': False})

        today = date.today()
        end_date = today + timedelta(days=duration_days)

        status = SpecialStatus(
            baby_id=baby_id,
            status_type=status_type,
            start_date=today,
            end_date=end_date,
            description=description,
            created_by=created_by
        )
        db.session.add(status)
        db.session.commit()
        return status
    except OperationalError as e:
        logger.error(f"create_special_status error: {e}")
        db.session.rollback()
        return None


def end_special_status(status_id: int) -> bool:
    """结束特殊状态"""
    try:
        status = SpecialStatus.query.get(status_id)
        if status:
            status.is_active = False
            status.end_date = date.today()
            db.session.commit()
            return True
        return False
    except OperationalError as e:
        logger.error(f"end_special_status error: {e}")
        db.session.rollback()
        return False


# ==========================================
# 邀请相关 DAO
# ==========================================

def get_invitation_by_code(code: str) -> Optional[Invitation]:
    """根据邀请码获取邀请"""
    try:
        return Invitation.query.filter(Invitation.code == code).first()
    except OperationalError as e:
        logger.error(f"get_invitation_by_code error: {e}")
        return None


def create_invitation(
    baby_id: int,
    inviter_id: int,
    code: str,
    expires_hours: int = 24,
    max_uses: int = 1
) -> Optional[Invitation]:
    """创建邀请"""
    try:
        expires_at = datetime.now() + timedelta(hours=expires_hours)

        invitation = Invitation(
            code=code,
            baby_id=baby_id,
            inviter_id=inviter_id,
            expires_at=expires_at,
            max_uses=max_uses
        )
        db.session.add(invitation)
        db.session.commit()
        return invitation
    except OperationalError as e:
        logger.error(f"create_invitation error: {e}")
        db.session.rollback()
        return None


def use_invitation(invitation: Invitation) -> bool:
    """使用邀请（增加使用次数）"""
    try:
        invitation.used_count += 1
        if invitation.used_count >= invitation.max_uses:
            invitation.is_active = False
        db.session.commit()
        return True
    except OperationalError as e:
        logger.error(f"use_invitation error: {e}")
        db.session.rollback()
        return False
