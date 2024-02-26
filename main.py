import subprocess
import requests
import json
import time
import logging
import logging.handlers
import configparser
import os
from datetime import datetime, timedelta
import platform

# 配置文件路径
CONFIG_FILE = 'config.ini'

# 读取配置文件
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

# 获取ips部分的所有配置
ips_section = config['ips']

# 创建一个空字典来存储转换后的数据
ip_dict = {}

# 遍历ips部分的所有键和值
for key, value in ips_section.items():
    try:
        # 使用split()方法将值按空格分割成两部分
        ip, description = value.split(' ', 1)
    except:
        # 没有描述默认使用IP
        ip, description = value, value
        # 将键和对应的值（IP和描述）添加到字典中
    ip_dict[ip] = description

print(ip_dict)
# 获取配置文件中ip和描述
ip_addresses = ip_dict.keys()
ip_description = ip_dict.values()

print(ip_addresses, ip_description)


# 从配置文件中获取IP地址列表
# print(config.items("ips"))
# ip_addresses = [value for key, value in config.items("ips")]

# 记录每个IP的上一个状态
# 默认为True
last_status = {ip: True for ip in ip_addresses}
print(last_status)

# 获取配置信息
WEBHOOK_URL = config.get('general', 'webhook_url')
LOG_RETENTION_DAYS = int(config.get('general', 'log_retention_days'))
LOG_DIRECTORY = config.get('general', 'log_directory')
PING_TIME = int(config.get('general', 'ping_time'))

# 确保日志目录存在
if not os.path.exists(LOG_DIRECTORY):
    os.makedirs(LOG_DIRECTORY)

# 创建日志文件路径模板
LOG_FILE_FORMAT = os.path.join(LOG_DIRECTORY, f"ping_monitor_{datetime.today().strftime('%Y-%m-%d')}.log")

# 创建日志处理器，每天滚动一次日志文件
log_handler = logging.handlers.TimedRotatingFileHandler(LOG_FILE_FORMAT, when='midnight',
                                                        backupCount=LOG_RETENTION_DAYS, encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
log_handler.setLevel(logging.INFO)

# 创建日志记录器并添加处理器
logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)


# 删除旧日志文件的函数
def delete_old_logs():
    try:
        today = datetime.now()
        for root, dirs, files in os.walk(LOG_DIRECTORY):
            for file in files:
                if file.startswith('ping_monitor_') and file.endswith('.log'):
                    file_path = os.path.join(root, file)
                    file_date = datetime.strptime(file[len('ping_monitor_'):-4], '%Y-%m-%d')
                    if (today - file_date).days >= LOG_RETENTION_DAYS:
                        os.remove(file_path)
                        logger.info(f"Deleted old log file: {file_path}")
    except Exception as e:
        logger.error(f"An error occurred while deleting old log files: {e}")


def send_webhook(message):
    try:
        headers = {'Content-Type': 'application/json'}
        payload = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }
        response = requests.post(WEBHOOK_URL, headers=headers, json=payload)
        if response.status_code == 200:
            logger.info(f"Webhook sent successfully with message: {message}")
        else:
            logger.error(f"Failed to send webhook. Status code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"An error occurred while sending webhook: {e}")


def check_ping(ip, timeout=100, packets=3):
    command = []
    if platform.system() == "Windows":
        # Windows ping命令不支持直接设置超时，但可以通过timeout参数间接设置
        # 使用-n参数设置发送的包数
        command = ["ping", "-n", str(packets), ip]
        try:
            # 在Windows上，通过启动一个新的进程并等待它来完成来模拟超时
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = process.communicate(timeout=timeout)
            print(output.decode('gbk'), error.decode('gbk'))
            if "ms" in str(output):
                return True, "故障问题恢复"
            else:
                return False, "故障问题"
        except subprocess.TimeoutExpired:
            return False, "超时"
    else:
        # Linux和macOS使用-c和-W参数
        command = ["ping", "-c", str(packets), "-W", str(timeout), ip]
        try:
            output = subprocess.check_output(command, stderr=subprocess.STDOUT)
            if "ms" in str(output):
                return True, "故障问题恢复"
            else:
                return False, "故障问题"
        except subprocess.CalledProcessError:
            return False, "Ping失败"
        except subprocess.TimeoutExpired:
            return False, "超时"


def monitor_ips():
    while True:
        for ip in ip_addresses:
            current_status, message = check_ping(ip)
            if current_status != last_status[ip]:
                if not current_status:
                    # Send alert for failure
                    send_webhook(f"ip：{ip} - 描述：{ip_dict[ip]} - 消息：{message}")
                    logger.info(f"ip：{ip} - 描述：{ip_dict[ip]} - 消息：{message}")
                else:
                    # Send alert for recovery
                    send_webhook(f"ip：{ip} - 描述：{ip_dict[ip]} - 消息：业务恢复")
                    logger.info(f"ip：{ip} - 描述：{ip_dict[ip]} - 消息：业务恢复")
                # 更新IP地址的状态
                last_status[ip] = current_status

        # 等待一段时间再次检查
        time.sleep(PING_TIME)

        # 每天清理旧日志文件
        delete_old_logs()


# 运行监控函数
monitor_ips()
