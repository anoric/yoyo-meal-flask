from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import pymysql
import config
import logging
import sys

# 配置日志输出到 stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
# 确保 'log' logger 也输出
logger = logging.getLogger('log')
logger.setLevel(logging.INFO)

# 因MySQLDB不支持Python3，使用pymysql扩展库代替MySQLDB库
pymysql.install_as_MySQLdb()

# 初始化web应用
app = Flask(__name__, instance_relative_config=True)
app.config['DEBUG'] = config.DEBUG

# 设定数据库链接
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{}:{}@{}/{}'.format(
    config.username, config.password, config.db_address, config.db_name
)

# 初始化DB操作对象
db = SQLAlchemy(app)

# 加载控制器
from wxcloudrun import views

# 加载配置
app.config.from_object('config')

# 创建数据库表（如果不存在）
with app.app_context():
    db.create_all()
