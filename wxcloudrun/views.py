"""
YoYo辅食管理 - API路由
所有API接口定义
"""
from datetime import datetime, date, timedelta
from flask import render_template, request

from run import app
from wxcloudrun import dao
from wxcloudrun.model import Food
from wxcloudrun.response import make_succ_response, make_err_response
from wxcloudrun.utils.auth import (
    generate_token, login_required, get_current_user, get_current_user_id,
    check_baby_permission, generate_invite_code
)
from wxcloudrun.utils.wechat import code2session
from wxcloudrun.services.meal_plan_generator import MealPlanGenerator
import logging

logger = logging.getLogger('log')


# ==========================================
# 首页
# ==========================================

@app.route('/')
def index():
    """返回index页面"""
    return render_template('index.html')


# ==========================================
# 认证模块 API
# ==========================================

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """微信登录

    请求参数:
        code: 微信登录凭证
        nickname: 用户昵称（可选）
        avatar_url: 头像URL（可选）

    返回:
        token: JWT Token
        expires_in: 过期时间（秒）
        user: 用户信息
        is_new_user: 是否新用户
    """
    params = request.get_json() or {}
    code = params.get('code')

    if not code:
        return make_err_response('缺少code参数', error_code='INVALID_PARAMS')

    # 调用微信接口获取openid
    wx_result = code2session(code)
    if not wx_result or 'openid' not in wx_result:
        return make_err_response('微信登录失败', error_code='WX_LOGIN_FAILED')

    openid = wx_result['openid']
    session_key = wx_result.get('session_key')

    # 查找或创建用户
    user = dao.get_user_by_openid(openid)
    is_new_user = False

    if not user:
        # 创建新用户
        nickname = params.get('nickname')
        avatar_url = params.get('avatar_url')
        user = dao.create_user(openid, nickname, avatar_url)
        is_new_user = True
        if not user:
            return make_err_response('创建用户失败', error_code='CREATE_USER_FAILED')
    else:
        # 更新用户信息
        if params.get('nickname'):
            user.nickname = params.get('nickname')
        if params.get('avatar_url'):
            user.avatar_url = params.get('avatar_url')

    # 更新session_key
    user.session_key = session_key

    # 生成token
    token = generate_token(user.id)
    user.token = token
    user.token_expires_at = datetime.now() + timedelta(days=7)
    dao.update_user(user)

    # 获取用户的宝宝列表
    babies = dao.get_babies_by_user(user.id)
    babies_data = []
    for baby in babies:
        manager = dao.get_baby_manager(baby.id, user.id)
        babies_data.append({
            'id': baby.id,
            'name': baby.name,
            'gender': baby.gender,
            'birthday': baby.birthday.isoformat() if baby.birthday else None,
            'age_months': baby.get_age_months(),
            'role': manager.role if manager else 'unknown'
        })

    # 为每个宝宝补全未来7天的辅食计划
    logger.info(f"[Login] 用户 {user.id} 有 {len(babies)} 个宝宝")
    for baby in babies:
        try:
            logger.info(f"[Login] 为宝宝 {baby.id} ({baby.name}) 生成计划, 月龄: {baby.get_age_months()}")
            generator = MealPlanGenerator(baby, user.id)
            missing_dates = generator.get_missing_dates()
            if missing_dates:
                count = generator.generate_and_save(missing_dates)
                logger.info(f"[Login] 为宝宝 {baby.id} 补全了 {count} 个辅食计划")
            else:
                logger.info(f"[Login] 宝宝 {baby.id} 不需要补全计划")
        except Exception as e:
            logger.error(f"[Login] 生成辅食计划失败: {e}", exc_info=True)

    return make_succ_response({
        'token': token,
        'expires_in': 7 * 24 * 3600,  # 7天
        'user': {
            'id': user.id,
            'nickname': user.nickname,
            'avatar_url': user.avatar_url,
            'current_baby_id': user.current_baby_id
        },
        'babies': babies_data,
        'is_new_user': is_new_user
    })


@app.route('/api/auth/me', methods=['GET'])
@login_required
def auth_me():
    """获取当前用户信息"""
    user = get_current_user()

    # 获取用户的宝宝列表
    babies = dao.get_babies_by_user(user.id)
    babies_data = []
    for baby in babies:
        manager = dao.get_baby_manager(baby.id, user.id)
        babies_data.append({
            'id': baby.id,
            'name': baby.name,
            'gender': baby.gender,
            'birthday': baby.birthday.isoformat() if baby.birthday else None,
            'age_months': baby.get_age_months(),
            'role': manager.role if manager else 'unknown'
        })

    # 为每个宝宝补全未来7天的辅食计划
    for baby in babies:
        try:
            generator = MealPlanGenerator(baby, user.id)
            missing_dates = generator.get_missing_dates()
            if missing_dates:
                count = generator.generate_and_save(missing_dates)
                logger.info(f"[auth_me] 为宝宝 {baby.id} 补全了 {count} 个辅食计划")
        except Exception as e:
            logger.error(f"[auth_me] 生成辅食计划失败: {e}", exc_info=True)

    return make_succ_response({
        'user': user.to_dict(),
        'babies': babies_data,
        'current_baby_id': user.current_baby_id
    })


# ==========================================
# 宝宝管理模块 API
# ==========================================

@app.route('/api/babies', methods=['GET'])
@login_required
def get_babies():
    """获取宝宝列表"""
    user_id = get_current_user_id()
    babies = dao.get_babies_by_user(user_id)

    result = []
    for baby in babies:
        manager = dao.get_baby_manager(baby.id, user_id)
        special_status = dao.get_active_special_status(baby.id)

        result.append({
            **baby.to_dict(),
            'role': manager.role if manager else 'unknown',
            'is_current': baby.id == get_current_user().current_baby_id,
            'has_special_status': special_status is not None
        })

    return make_succ_response({
        'babies': result,
        'current_baby_id': get_current_user().current_baby_id
    })


@app.route('/api/babies', methods=['POST'])
@login_required
def create_baby():
    """创建宝宝

    请求参数:
        name: 宝宝名称（必填）
        birthday: 出生日期，格式YYYY-MM-DD（必填）
        gender: 性别，0=未知，1=男，2=女（可选，默认0）
        avatar: 头像URL（可选）
        allergy_notes: 过敏备注（可选）
        food_preferences: 食物偏好（可选）
    """
    params = request.get_json() or {}
    user_id = get_current_user_id()

    # 参数校验
    name = params.get('name')
    birthday_str = params.get('birthday')

    if not name:
        return make_err_response('请输入宝宝名称', error_code='INVALID_PARAMS')
    if not birthday_str:
        return make_err_response('请输入出生日期', error_code='INVALID_PARAMS')

    try:
        birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
    except ValueError:
        return make_err_response('出生日期格式错误', error_code='INVALID_PARAMS')

    # 校验月龄（必须在6-36月龄之间）
    today = date.today()
    age_months = (today.year - birthday.year) * 12 + (today.month - birthday.month)
    if age_months < 4:
        return make_err_response('宝宝月龄太小，建议满4个月后再添加辅食', error_code='INVALID_PARAMS')
    if age_months > 36:
        return make_err_response('宝宝月龄超过36个月，不适合使用辅食管理', error_code='INVALID_PARAMS')

    # 转换性别参数
    gender_param = params.get('gender', 0)
    if gender_param == 'male':
        gender = 1
    elif gender_param == 'female':
        gender = 2
    elif isinstance(gender_param, int):
        gender = gender_param
    else:
        gender = 0

    # 创建宝宝
    baby = dao.create_baby(
        name=name,
        birthday=birthday,
        gender=gender,
        created_by=user_id,
        avatar=params.get('avatar'),
        allergy_notes=params.get('allergy_notes'),
        food_preferences=params.get('food_preferences')
    )

    if not baby:
        return make_err_response('创建宝宝失败', error_code='CREATE_BABY_FAILED')

    # 设置为当前宝宝
    user = get_current_user()
    user.current_baby_id = baby.id
    dao.update_user(user)

    return make_succ_response({
        'baby': baby.to_dict(),
        'message': '创建成功'
    })


@app.route('/api/babies/<int:baby_id>', methods=['GET'])
@login_required
def get_baby(baby_id):
    """获取宝宝详情"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限访问该宝宝', error_code='PERMISSION_DENIED')

    baby = dao.get_baby_by_id(baby_id)
    if not baby:
        return make_err_response('宝宝不存在', error_code='NOT_FOUND')

    # 获取特殊状态
    special_status = dao.get_active_special_status(baby_id)

    # 获取正在排敏的食材
    testing_food = dao.get_baby_testing_food(baby_id)
    testing_food_info = None
    if testing_food:
        food = dao.get_food_by_id(testing_food.food_id)
        if food:
            testing_food_info = {
                'food_id': food.id,
                'food_name': food.name,
                'start_date': testing_food.testing_start_date.isoformat() if testing_food.testing_start_date else None,
                'end_date': testing_food.testing_end_date.isoformat() if testing_food.testing_end_date else None,
                'days_remaining': testing_food.get_testing_days_remaining()
            }

    # 获取管理员信息
    manager = dao.get_baby_manager(baby_id, user_id)

    return make_succ_response({
        **baby.to_dict(),
        'role': manager.role if manager else 'unknown',
        'special_status': special_status.to_dict() if special_status else None,
        'testing_food': testing_food_info
    })


@app.route('/api/babies/<int:baby_id>', methods=['PUT'])
@login_required
def update_baby(baby_id):
    """更新宝宝信息"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限修改该宝宝', error_code='PERMISSION_DENIED')

    baby = dao.get_baby_by_id(baby_id)
    if not baby:
        return make_err_response('宝宝不存在', error_code='NOT_FOUND')

    params = request.get_json() or {}

    # 更新字段
    if 'name' in params:
        baby.name = params['name']
    if 'avatar' in params:
        baby.avatar = params['avatar']
    if 'gender' in params:
        gender_param = params['gender']
        if gender_param == 'male':
            baby.gender = 1
        elif gender_param == 'female':
            baby.gender = 2
        elif isinstance(gender_param, int):
            baby.gender = gender_param
        else:
            baby.gender = 0
    if 'birthday' in params:
        try:
            baby.birthday = datetime.strptime(params['birthday'], '%Y-%m-%d').date()
        except ValueError:
            return make_err_response('出生日期格式错误', error_code='INVALID_PARAMS')
    if 'allergy_notes' in params:
        baby.allergy_notes = params['allergy_notes']
    if 'food_preferences' in params:
        baby.food_preferences = params['food_preferences']

    if not dao.update_baby(baby):
        return make_err_response('更新失败', error_code='UPDATE_FAILED')

    return make_succ_response({
        'baby': baby.to_dict(),
        'message': '更新成功'
    })


@app.route('/api/babies/<int:baby_id>', methods=['DELETE'])
@login_required
def delete_baby(baby_id):
    """删除宝宝（仅创建者可删除）"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id, require_owner=True):
        return make_err_response('仅创建者可删除宝宝', error_code='PERMISSION_DENIED')

    if not dao.delete_baby(baby_id):
        return make_err_response('删除失败', error_code='DELETE_FAILED')

    # 如果删除的是当前宝宝，清除current_baby_id
    user = get_current_user()
    if user.current_baby_id == baby_id:
        user.current_baby_id = None
        # 尝试设置其他宝宝为当前
        babies = dao.get_babies_by_user(user_id)
        if babies:
            user.current_baby_id = babies[0].id
        dao.update_user(user)

    return make_succ_response({'message': '删除成功'})


@app.route('/api/babies/<int:baby_id>/switch', methods=['POST'])
@login_required
def switch_baby(baby_id):
    """切换当前宝宝"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限访问该宝宝', error_code='PERMISSION_DENIED')

    user = get_current_user()
    user.current_baby_id = baby_id
    dao.update_user(user)

    return make_succ_response({'message': '切换成功', 'current_baby_id': baby_id})


# ==========================================
# 邀请分享模块 API
# ==========================================

@app.route('/api/babies/<int:baby_id>/invite', methods=['POST'])
@login_required
def create_invite(baby_id):
    """创建邀请链接

    请求参数:
        expires_hours: 过期时间（小时），默认24
        max_uses: 最大使用次数，默认1
    """
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id, require_owner=True):
        return make_err_response('仅创建者可邀请他人', error_code='PERMISSION_DENIED')

    params = request.get_json() or {}
    expires_hours = params.get('expires_hours', 24)
    max_uses = params.get('max_uses', 1)

    code = generate_invite_code()
    invitation = dao.create_invitation(
        baby_id=baby_id,
        inviter_id=user_id,
        code=code,
        expires_hours=expires_hours,
        max_uses=max_uses
    )

    if not invitation:
        return make_err_response('创建邀请失败', error_code='CREATE_INVITE_FAILED')

    return make_succ_response({
        'invite_code': code,
        'invite_url': f'/pages/invite/accept?code={code}',
        'expires_at': invitation.expires_at.isoformat()
    })


@app.route('/api/invite/accept', methods=['POST'])
@login_required
def accept_invite():
    """接受邀请

    请求参数:
        code: 邀请码
    """
    params = request.get_json() or {}
    code = params.get('code')

    if not code:
        return make_err_response('缺少邀请码', error_code='INVALID_PARAMS')

    invitation = dao.get_invitation_by_code(code)
    if not invitation:
        return make_err_response('邀请码不存在', error_code='NOT_FOUND')

    if not invitation.is_valid():
        return make_err_response('邀请码已过期或已使用', error_code='INVITE_EXPIRED')

    user_id = get_current_user_id()

    # 检查是否已经是管理员
    existing = dao.get_baby_manager(invitation.baby_id, user_id)
    if existing:
        return make_err_response('您已经是该宝宝的管理员', error_code='ALREADY_MANAGER')

    # 添加为管理员
    manager = dao.add_baby_manager(
        baby_id=invitation.baby_id,
        user_id=user_id,
        invited_by=invitation.inviter_id
    )

    if not manager:
        return make_err_response('接受邀请失败', error_code='ACCEPT_INVITE_FAILED')

    # 使用邀请
    dao.use_invitation(invitation)

    # 获取宝宝信息
    baby = dao.get_baby_by_id(invitation.baby_id)

    return make_succ_response({
        'message': '已成为管理员',
        'baby': baby.to_dict() if baby else None
    })


@app.route('/api/babies/<int:baby_id>/managers', methods=['GET'])
@login_required
def get_managers(baby_id):
    """获取宝宝的管理员列表"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限访问', error_code='PERMISSION_DENIED')

    managers = dao.get_baby_managers(baby_id)
    result = []
    for m in managers:
        user = dao.get_user_by_id(m.user_id)
        result.append({
            'user_id': m.user_id,
            'nickname': user.nickname if user else None,
            'avatar_url': user.avatar_url if user else None,
            'role': m.role,
            'created_at': m.created_at.isoformat() if m.created_at else None
        })

    return make_succ_response({'managers': result})


@app.route('/api/babies/<int:baby_id>/managers/<int:target_user_id>', methods=['DELETE'])
@login_required
def remove_manager(baby_id, target_user_id):
    """移除管理员"""
    user_id = get_current_user_id()

    # 如果是自己退出
    if target_user_id == user_id:
        manager = dao.get_baby_manager(baby_id, user_id)
        if manager and manager.role == 'owner':
            return make_err_response('创建者不能退出', error_code='PERMISSION_DENIED')
        dao.remove_baby_manager(baby_id, user_id)
        return make_succ_response({'message': '已退出管理'})

    # 否则需要owner权限
    if not check_baby_permission(baby_id, user_id, require_owner=True):
        return make_err_response('仅创建者可移除他人', error_code='PERMISSION_DENIED')

    dao.remove_baby_manager(baby_id, target_user_id)
    return make_succ_response({'message': '已移除管理员'})


# ==========================================
# 食材库模块 API
# ==========================================

@app.route('/api/foods', methods=['GET'])
@login_required
def get_foods():
    """获取食材列表

    查询参数:
        category: 分类筛选（可选）
        month: 按月龄筛选（可选）
        baby_id: 包含该宝宝的食材状态（可选）
    """
    category = request.args.get('category')
    month = request.args.get('month', type=int)
    baby_id = request.args.get('baby_id', type=int)

    foods = dao.get_all_foods(category=category, max_month=month)

    # 按分类分组
    categories_map = {}
    for food in foods:
        cat = food.category
        if cat not in categories_map:
            categories_map[cat] = {
                'category': cat,
                'category_name': Food.CATEGORY_NAMES.get(cat, cat),
                'foods': []
            }

        food_data = food.to_dict()

        # 如果指定了baby_id，获取该宝宝的食材状态
        if baby_id:
            status = dao.get_baby_food_status(baby_id, food.id)
            food_data['baby_status'] = status.status if status else 'unknown'

        categories_map[cat]['foods'].append(food_data)

    # 按分类排序
    category_order = ['staple', 'vegetable', 'fruit', 'meat', 'dairy', 'seafood']
    result = []
    for cat in category_order:
        if cat in categories_map:
            result.append(categories_map[cat])

    return make_succ_response({'categories': result})


@app.route('/api/foods/<int:food_id>', methods=['GET'])
@login_required
def get_food(food_id):
    """获取食材详情"""
    food = dao.get_food_by_id(food_id)
    if not food:
        return make_err_response('食材不存在', error_code='NOT_FOUND')

    return make_succ_response(food.to_dict())


@app.route('/api/babies/<int:baby_id>/foods', methods=['GET'])
@login_required
def get_baby_foods(baby_id):
    """获取宝宝的食材状态列表

    查询参数:
        status: 状态筛选（safe/allergic/testing）
    """
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限访问', error_code='PERMISSION_DENIED')

    status = request.args.get('status')
    food_statuses = dao.get_baby_food_statuses(baby_id, status)

    # 统计各状态数量
    all_statuses = dao.get_baby_food_statuses(baby_id)
    safe_count = sum(1 for s in all_statuses if s.status == 'safe')
    allergic_count = sum(1 for s in all_statuses if s.status == 'allergic')
    testing_count = sum(1 for s in all_statuses if s.status == 'testing')

    result = []
    for fs in food_statuses:
        food = dao.get_food_by_id(fs.food_id)
        if food:
            result.append({
                **fs.to_dict(),
                'food_name': food.name,
                'category': food.category,
                'category_name': Food.CATEGORY_NAMES.get(food.category, food.category)
            })

    return make_succ_response({
        'safe_count': safe_count,
        'allergic_count': allergic_count,
        'testing_count': testing_count,
        'foods': result
    })


@app.route('/api/babies/<int:baby_id>/foods/batch', methods=['POST'])
@login_required
def batch_update_baby_food_status(baby_id):
    """批量更新宝宝的食材状态

    请求参数:
        items: [{ food_id, status, notes? }]
    """
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    params = request.get_json() or {}
    items = params.get('items', [])

    if not items:
        return make_succ_response({'message': '无需更新', 'updated_count': 0})

    updated_count = 0
    for item in items:
        food_id = item.get('food_id')
        status = item.get('status')

        if not food_id or status not in ['safe', 'allergic', 'testing']:
            continue

        food_status = dao.create_or_update_baby_food_status(
            baby_id=baby_id,
            food_id=food_id,
            status=status,
            updated_by=user_id,
            notes=item.get('notes')
        )
        if food_status:
            updated_count += 1

    return make_succ_response({
        'message': f'已更新 {updated_count} 个食材状态',
        'updated_count': updated_count
    })


@app.route('/api/babies/<int:baby_id>/foods/<int:food_id>', methods=['PUT'])
@login_required
def update_baby_food_status(baby_id, food_id):
    """更新宝宝的食材状态

    请求参数:
        status: 状态（safe/allergic/testing）
        allergy_symptoms: 过敏症状（当status=allergic时）
        notes: 备注
    """
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    params = request.get_json() or {}
    status = params.get('status')

    if status not in ['safe', 'allergic', 'testing']:
        return make_err_response('状态参数错误', error_code='INVALID_PARAMS')

    food_status = dao.create_or_update_baby_food_status(
        baby_id=baby_id,
        food_id=food_id,
        status=status,
        updated_by=user_id,
        allergy_symptoms=params.get('allergy_symptoms'),
        notes=params.get('notes')
    )

    if not food_status:
        return make_err_response('更新失败', error_code='UPDATE_FAILED')

    return make_succ_response({
        'food_status': food_status.to_dict(),
        'message': '更新成功'
    })


@app.route('/api/babies/<int:baby_id>/foods/<int:food_id>/test', methods=['POST'])
@login_required
def start_food_test(baby_id, food_id):
    """开始食材排敏"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    # 检查是否有特殊状态
    special_status = dao.get_active_special_status(baby_id)
    if special_status:
        return make_err_response(
            f'宝宝处于特殊状态（{special_status.status_type_name}），暂不建议添加新食材',
            error_code='SPECIAL_STATUS_ACTIVE'
        )

    # 检查是否已有正在排敏的食材
    testing = dao.get_baby_testing_food(baby_id)
    if testing:
        food = dao.get_food_by_id(testing.food_id)
        return make_err_response(
            f'正在排敏"{food.name if food else "未知食材"}"，请等待排敏结束后再添加新食材',
            error_code='TESTING_IN_PROGRESS'
        )

    # 开始排敏
    food_status = dao.start_food_testing(baby_id, food_id, user_id, days=3)
    if not food_status:
        return make_err_response('开始排敏失败', error_code='START_TESTING_FAILED')

    food = dao.get_food_by_id(food_id)

    return make_succ_response({
        'food_status': food_status.to_dict(),
        'food_name': food.name if food else None,
        'message': f'开始排敏"{food.name if food else ""}"，观察期3天'
    })


# ==========================================
# 辅食计划模块 API
# ==========================================

@app.route('/api/babies/<int:baby_id>/meal-plans', methods=['GET'])
@login_required
def get_meal_plans(baby_id):
    """获取辅食计划

    查询参数:
        date: 日期，格式YYYY-MM-DD（默认今天）
    """
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限访问', error_code='PERMISSION_DENIED')

    date_str = request.args.get('date')
    if date_str:
        try:
            plan_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return make_err_response('日期格式错误', error_code='INVALID_PARAMS')
    else:
        plan_date = date.today()

    baby = dao.get_baby_by_id(baby_id)
    if not baby:
        return make_err_response('宝宝不存在', error_code='NOT_FOUND')

    # 获取特殊状态
    special_status = dao.get_active_special_status(baby_id)

    # 获取正在排敏的食材
    testing_food = dao.get_baby_testing_food(baby_id)

    # 判断是否可以添加新食材
    can_add_new_food = not special_status and not testing_food

    # 获取当天的计划
    plans = dao.get_meal_plans_by_date(baby_id, plan_date)

    plans_data = []
    for plan in plans:
        food_ids = plan.get_food_id_list()
        foods = dao.get_foods_by_ids(food_ids)
        foods_data = []
        for f in foods:
            is_new = plan.new_food_id == f.id
            foods_data.append({
                'id': f.id,
                'name': f.name,
                'is_new': is_new
            })

        new_food_data = None
        if plan.new_food_id:
            new_food = dao.get_food_by_id(plan.new_food_id)
            if new_food:
                status = dao.get_baby_food_status(baby_id, new_food.id)
                new_food_data = {
                    'id': new_food.id,
                    'name': new_food.name,
                    'testing_day': (date.today() - status.testing_start_date).days + 1 if status and status.testing_start_date else 1
                }

        plans_data.append({
            **plan.to_dict(),
            'foods': foods_data,
            'new_food': new_food_data
        })

    # 根据月龄计算应显示的餐次
    age_months = baby.get_age_months()
    if age_months <= 6:
        meals_for_age = ['lunch']
    elif age_months <= 8:
        meals_for_age = ['lunch', 'dinner']
    else:
        meals_for_age = ['breakfast', 'lunch', 'dinner']

    return make_succ_response({
        'date': plan_date.isoformat(),
        'baby_age_months': age_months,
        'meals_for_age': meals_for_age,  # 根据月龄应显示的餐次
        'special_status': special_status.to_dict() if special_status else None,
        'can_add_new_food': can_add_new_food,
        'testing_food': {
            'food_id': testing_food.food_id,
            'days_remaining': testing_food.get_testing_days_remaining()
        } if testing_food else None,
        'plans': plans_data
    })


@app.route('/api/babies/<int:baby_id>/meal-plans', methods=['POST'])
@login_required
def create_meal_plan(baby_id):
    """创建或更新辅食计划

    请求参数:
        date: 日期，格式YYYY-MM-DD
        meal_type: 餐次类型（breakfast/lunch/dinner/snack）
        food_ids: 食材ID列表
        new_food_id: 新添加的食材ID（可选）
        notes: 备注（可选）
    """
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    params = request.get_json() or {}

    date_str = params.get('date')
    meal_type = params.get('meal_type')
    food_ids = params.get('food_ids', [])

    if not date_str:
        return make_err_response('缺少日期参数', error_code='INVALID_PARAMS')
    if not meal_type:
        return make_err_response('缺少餐次参数', error_code='INVALID_PARAMS')
    if not food_ids:
        return make_err_response('请选择食材', error_code='INVALID_PARAMS')

    try:
        plan_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return make_err_response('日期格式错误', error_code='INVALID_PARAMS')

    # 如果有新食材，检查是否可以添加
    new_food_id = params.get('new_food_id')
    if new_food_id:
        special_status = dao.get_active_special_status(baby_id)
        if special_status:
            return make_err_response('宝宝处于特殊状态，暂不建议添加新食材', error_code='SPECIAL_STATUS_ACTIVE')

        testing = dao.get_baby_testing_food(baby_id)
        if testing and testing.food_id != new_food_id:
            return make_err_response('已有正在排敏的食材', error_code='TESTING_IN_PROGRESS')

        # 如果是新食材，开始排敏
        if not testing:
            dao.start_food_testing(baby_id, new_food_id, user_id, days=3)

    plan = dao.create_or_update_meal_plan(
        baby_id=baby_id,
        plan_date=plan_date,
        meal_type=meal_type,
        food_ids=food_ids,
        created_by=user_id,
        new_food_id=new_food_id,
        notes=params.get('notes')
    )

    if not plan:
        return make_err_response('保存失败', error_code='SAVE_FAILED')

    return make_succ_response({
        'plan': plan.to_dict(),
        'message': '保存成功'
    })


@app.route('/api/babies/<int:baby_id>/meal-plans/<int:plan_id>/complete', methods=['POST'])
@login_required
def complete_meal_plan(baby_id, plan_id):
    """标记辅食计划完成"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    if not dao.complete_meal_plan(plan_id):
        return make_err_response('操作失败', error_code='COMPLETE_FAILED')

    return make_succ_response({'message': '已完成'})


@app.route('/api/babies/<int:baby_id>/meal-plans/<int:plan_id>', methods=['DELETE'])
@login_required
def delete_meal_plan(baby_id, plan_id):
    """删除辅食计划"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    if not dao.delete_meal_plan(plan_id):
        return make_err_response('删除失败', error_code='DELETE_FAILED')

    return make_succ_response({'message': '删除成功'})


# ==========================================
# 特殊状态模块 API
# ==========================================

@app.route('/api/babies/<int:baby_id>/special-status', methods=['GET'])
@login_required
def get_special_status(baby_id):
    """获取宝宝当前特殊状态"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限访问', error_code='PERMISSION_DENIED')

    status = dao.get_active_special_status(baby_id)

    return make_succ_response({
        'special_status': status.to_dict() if status else None
    })


@app.route('/api/babies/<int:baby_id>/special-status', methods=['POST'])
@login_required
def create_special_status(baby_id):
    """创建特殊状态

    请求参数:
        status_type: 状态类型（sick/vaccine/other）
        description: 描述（可选）
        duration_days: 持续天数，默认14
    """
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    params = request.get_json() or {}
    status_type = params.get('status_type')

    if status_type not in ['sick', 'vaccine', 'other']:
        return make_err_response('状态类型错误', error_code='INVALID_PARAMS')

    status = dao.create_special_status(
        baby_id=baby_id,
        status_type=status_type,
        created_by=user_id,
        description=params.get('description'),
        duration_days=params.get('duration_days', 14)
    )

    if not status:
        return make_err_response('创建失败', error_code='CREATE_FAILED')

    return make_succ_response({
        'special_status': status.to_dict(),
        'message': '已记录特殊状态，2周内暂不添加新食材'
    })


@app.route('/api/babies/<int:baby_id>/special-status/<int:status_id>/end', methods=['POST'])
@login_required
def end_special_status(baby_id, status_id):
    """结束特殊状态"""
    user_id = get_current_user_id()

    if not check_baby_permission(baby_id, user_id):
        return make_err_response('无权限操作', error_code='PERMISSION_DENIED')

    if not dao.end_special_status(status_id):
        return make_err_response('操作失败', error_code='END_FAILED')

    return make_succ_response({'message': '特殊状态已结束'})
