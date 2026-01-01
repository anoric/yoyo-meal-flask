import os

# 是否开启debug模式
DEBUG = True

# 读取数据库环境变量
username = os.environ.get("MYSQL_USERNAME", 'root')
password = os.environ.get("MYSQL_PASSWORD", 'root')
db_address = os.environ.get("MYSQL_ADDRESS", '127.0.0.1:3306')

# 微信小程序配置
WX_APPID = os.environ.get("WX_APPID", '')
WX_APP_SECRET = os.environ.get("WX_APP_SECRET", '')

# JWT配置
JWT_SECRET = os.environ.get("JWT_SECRET", 'yoyo-meal-secret-key-change-in-production')

# 火山引擎AI配置
VOLCANO_API_KEY = os.environ.get("VOLCANO_API_KEY", '')
