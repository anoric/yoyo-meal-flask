from datetime import datetime, date

from wxcloudrun import db


# ==========================================
# 用户表
# ==========================================
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    openid = db.Column(db.String(64), unique=True, nullable=False)
    unionid = db.Column(db.String(64), nullable=True)
    nickname = db.Column(db.String(64), nullable=True)
    avatar_url = db.Column(db.String(512), nullable=True)
    session_key = db.Column(db.String(64), nullable=True)
    token = db.Column(db.String(128), unique=True, nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    current_baby_id = db.Column(db.BigInteger, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'openid': self.openid,
            'nickname': self.nickname,
            'avatar_url': self.avatar_url,
            'current_baby_id': self.current_baby_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# 宝宝表
# ==========================================
class Baby(db.Model):
    __tablename__ = 'babies'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(32), nullable=False)
    avatar = db.Column(db.String(512), nullable=True)
    birthday = db.Column(db.Date, nullable=False)
    gender = db.Column(db.SmallInteger, default=0)  # 0=未知，1=男，2=女
    allergy_notes = db.Column(db.Text, nullable=True)
    food_preferences = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def get_age_months(self) -> int:
        """计算月龄"""
        today = date.today()
        months = (today.year - self.birthday.year) * 12 + (today.month - self.birthday.month)
        if today.day < self.birthday.day:
            months -= 1
        return max(0, months)

    def get_age_days(self) -> int:
        """计算天数"""
        today = date.today()
        return (today - self.birthday).days

    def to_dict(self, include_age=True):
        result = {
            'id': self.id,
            'name': self.name,
            'avatar': self.avatar,
            'birthday': self.birthday.isoformat() if self.birthday else None,
            'gender': self.gender,
            'allergy_notes': self.allergy_notes,
            'food_preferences': self.food_preferences,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_age:
            result['age_months'] = self.get_age_months()
            result['age_days'] = self.get_age_days()
        return result


# ==========================================
# 宝宝管理员关系表
# ==========================================
class BabyManager(db.Model):
    __tablename__ = 'baby_managers'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    baby_id = db.Column(db.BigInteger, nullable=False)
    user_id = db.Column(db.BigInteger, nullable=False)
    role = db.Column(db.Enum('owner', 'manager'), nullable=False, default='manager')
    invited_by = db.Column(db.BigInteger, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'baby_id': self.baby_id,
            'user_id': self.user_id,
            'role': self.role,
            'invited_by': self.invited_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# 食材库表
# ==========================================
class Food(db.Model):
    __tablename__ = 'foods'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(32), nullable=False)
    category = db.Column(db.Enum('staple', 'vegetable', 'fruit', 'meat', 'dairy', 'seafood'), nullable=False)
    min_month = db.Column(db.SmallInteger, nullable=False, default=6)
    max_month = db.Column(db.SmallInteger, nullable=True)
    allergy_risk = db.Column(db.SmallInteger, nullable=False, default=0)  # 0=低，1=中，2=高
    nutrition_info = db.Column(db.String(255), nullable=True)
    cooking_tips = db.Column(db.String(255), nullable=True)
    icon = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 分类中文名称映射
    CATEGORY_NAMES = {
        'staple': '主食',
        'vegetable': '蔬菜',
        'fruit': '水果',
        'meat': '肉类',
        'dairy': '蛋奶',
        'seafood': '海鲜'
    }

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category': self.category,
            'category_name': self.CATEGORY_NAMES.get(self.category, self.category),
            'min_month': self.min_month,
            'max_month': self.max_month,
            'allergy_risk': self.allergy_risk,
            'nutrition_info': self.nutrition_info,
            'cooking_tips': self.cooking_tips,
            'icon': self.icon,
            'is_active': self.is_active,
            'sort_order': self.sort_order
        }


# ==========================================
# 宝宝食材状态表
# ==========================================
class BabyFoodStatus(db.Model):
    __tablename__ = 'baby_food_status'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    baby_id = db.Column(db.BigInteger, nullable=False)
    food_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum('safe', 'allergic', 'testing'), nullable=False, default='testing')
    testing_start_date = db.Column(db.Date, nullable=True)
    testing_end_date = db.Column(db.Date, nullable=True)
    allergy_count = db.Column(db.Integer, nullable=False, default=0)
    allergy_symptoms = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.String(255), nullable=True)
    updated_by = db.Column(db.BigInteger, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def get_testing_days_remaining(self) -> int:
        """获取排敏剩余天数"""
        if self.status != 'testing' or not self.testing_end_date:
            return 0
        today = date.today()
        remaining = (self.testing_end_date - today).days
        return max(0, remaining)

    def to_dict(self):
        return {
            'id': self.id,
            'baby_id': self.baby_id,
            'food_id': self.food_id,
            'status': self.status,
            'testing_start_date': self.testing_start_date.isoformat() if self.testing_start_date else None,
            'testing_end_date': self.testing_end_date.isoformat() if self.testing_end_date else None,
            'testing_days_remaining': self.get_testing_days_remaining(),
            'allergy_count': self.allergy_count,
            'allergy_symptoms': self.allergy_symptoms,
            'notes': self.notes,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ==========================================
# 辅食计划表
# ==========================================
class MealPlan(db.Model):
    __tablename__ = 'meal_plans'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    baby_id = db.Column(db.BigInteger, nullable=False)
    plan_date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.Enum('breakfast', 'lunch', 'dinner', 'snack'), nullable=False, default='lunch')
    food_ids = db.Column(db.String(255), nullable=False)  # 逗号分隔的食材ID
    new_food_id = db.Column(db.Integer, nullable=True)  # 新添加的食材ID
    is_ai_generated = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.String(255), nullable=True)
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 餐次中文名称映射
    MEAL_TYPE_NAMES = {
        'breakfast': '早餐',
        'lunch': '午餐',
        'dinner': '晚餐',
        'snack': '加餐'
    }

    def get_food_id_list(self) -> list:
        """获取食材ID列表"""
        if not self.food_ids:
            return []
        return [int(fid) for fid in self.food_ids.split(',') if fid.strip()]

    def set_food_id_list(self, food_ids: list):
        """设置食材ID列表"""
        self.food_ids = ','.join(str(fid) for fid in food_ids)

    def to_dict(self):
        return {
            'id': self.id,
            'baby_id': self.baby_id,
            'plan_date': self.plan_date.isoformat() if self.plan_date else None,
            'meal_type': self.meal_type,
            'meal_type_name': self.MEAL_TYPE_NAMES.get(self.meal_type, self.meal_type),
            'food_ids': self.get_food_id_list(),
            'new_food_id': self.new_food_id,
            'is_ai_generated': self.is_ai_generated,
            'notes': self.notes,
            'is_completed': self.is_completed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# 特殊状态表
# ==========================================
class SpecialStatus(db.Model):
    __tablename__ = 'special_status'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    baby_id = db.Column(db.BigInteger, nullable=False)
    status_type = db.Column(db.Enum('sick', 'vaccine', 'other'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 状态类型中文名称映射
    STATUS_TYPE_NAMES = {
        'sick': '生病',
        'vaccine': '打疫苗',
        'other': '其他'
    }

    def get_days_remaining(self) -> int:
        """获取剩余天数"""
        if not self.is_active or not self.end_date:
            return 0
        today = date.today()
        remaining = (self.end_date - today).days
        return max(0, remaining)

    def to_dict(self):
        return {
            'id': self.id,
            'baby_id': self.baby_id,
            'status_type': self.status_type,
            'status_type_name': self.STATUS_TYPE_NAMES.get(self.status_type, self.status_type),
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'days_remaining': self.get_days_remaining(),
            'description': self.description,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# ==========================================
# 邀请链接表
# ==========================================
class Invitation(db.Model):
    __tablename__ = 'invitations'

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    baby_id = db.Column(db.BigInteger, nullable=False)
    inviter_id = db.Column(db.BigInteger, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    max_uses = db.Column(db.Integer, nullable=False, default=1)
    used_count = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def is_valid(self) -> bool:
        """检查邀请是否有效"""
        if not self.is_active:
            return False
        if self.used_count >= self.max_uses:
            return False
        if datetime.now() > self.expires_at:
            return False
        return True

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'baby_id': self.baby_id,
            'inviter_id': self.inviter_id,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'max_uses': self.max_uses,
            'used_count': self.used_count,
            'is_active': self.is_active,
            'is_valid': self.is_valid(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
