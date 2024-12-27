#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import uuid
import random
import string
import hashlib
import platform
import subprocess
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging
from datetime import datetime

# ANSI 颜色代码
class Colors:
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'

# 版本信息
VERSION = "dev"

# 错误类型常量
ERR_PERMISSION = "permission_error"
ERR_CONFIG = "config_error"
ERR_PROCESS = "process_error"
ERR_SYSTEM = "system_error"

# 配置类
@dataclass
class TextResource:
    success_message: str = "[√] 配置文件已成功更新！"
    restart_message: str = "[!] 请手动重启 Cursor 以使更新生效"
    reading_config: str = "正在读取配置文件..."
    generating_ids: str = "正在生成新的标识符..."
    press_enter_to_exit: str = "按回车键退出程序..."
    error_prefix: str = "程序发生严重错误: %v"
    privilege_error: str = "\n[!] 错误：需要管理员权限"
    run_with_sudo: str = "请使用 sudo 命令运行此程序"
    sudo_example: str = "示例: sudo %s"
    config_location: str = "配置文件位置:"
    checking_processes: str = "正在检查运行中的 Cursor 实例..."
    closing_processes: str = "正在关闭 Cursor 实例..."
    processes_closed: str = "所有 Cursor 实例已关闭"
    please_wait: str = "请稍候..."
    set_readonly_message: str = "设置 storage.json 为只读模式, 这将导致 workspace 记录信息丢失等问题"

@dataclass
class StorageConfig:
    telemetry_mac_machine_id: str
    telemetry_machine_id: str
    telemetry_dev_device_id: str
    telemetry_sqm_id: str

    def to_dict(self) -> dict:
        return {
            "telemetry.macMachineId": self.telemetry_mac_machine_id,
            "telemetry.machineId": self.telemetry_machine_id,
            "telemetry.devDeviceId": self.telemetry_dev_device_id,
            "telemetry.sqmId": self.telemetry_sqm_id
        }

class AppError(Exception):
    def __init__(self, error_type: str, op: str, path: str, err: Exception, context: dict = None):
        self.type = error_type
        self.op = op
        self.path = path
        self.err = err
        self.context = context

    def __str__(self):
        if self.context:
            return f"[{self.type}] {self.op}: {self.err} (context: {self.context})"
        return f"[{self.type}] {self.op}: {self.err}"

@dataclass
class SpinnerConfig:
    frames: List[str]
    delay: float

@dataclass
class SystemConfig:
    retry_attempts: int
    retry_delay: float
    timeout: float

class ProgressSpinner:
    def __init__(self, message: str):
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.current = 0
        self.message = message

def get_config_path(username: str) -> str:
    """获取配置文件路径"""
    if platform.system() == "Darwin":  # macOS
        return os.path.join("/Users", username, "Library", "Application Support", "Cursor", "User", "globalStorage", "storage.json")
    else:  # Linux
        return os.path.join("/home", username, ".config", "Cursor", "User", "globalStorage", "storage.json")

def generate_machine_id() -> str:
    """生成新的机器ID"""
    prefix = "auth0|user_"
    sequence = f"{random.randint(0, 99):02d}"
    unique_id = ''.join(random.choices(string.ascii_uppercase + string.digits.replace('0', '').replace('1', ''), k=23))
    full_id = prefix + sequence + unique_id
    return full_id.encode().hex()

def generate_mac_machine_id() -> str:
    """生成新的MAC机器ID"""
    data = os.urandom(32)
    return hashlib.sha256(data).hexdigest()

def generate_dev_device_id() -> str:
    """生成新的设备ID"""
    return str(uuid.uuid4())

def new_storage_config(old_config: Optional[StorageConfig] = None) -> StorageConfig:
    """创建新的存储配置"""
    config = StorageConfig(
        telemetry_mac_machine_id=generate_mac_machine_id(),
        telemetry_machine_id=generate_machine_id(),
        telemetry_dev_device_id=generate_dev_device_id(),
        telemetry_sqm_id=""
    )
    
    if old_config and old_config.telemetry_sqm_id:
        config.telemetry_sqm_id = old_config.telemetry_sqm_id
    else:
        config.telemetry_sqm_id = generate_mac_machine_id()
        
    return config

def read_existing_config(username: str) -> Optional[StorageConfig]:
    """读取现有配置"""
    config_path = get_config_path(username)
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return StorageConfig(
                    telemetry_mac_machine_id=data.get("telemetry.macMachineId", ""),
                    telemetry_machine_id=data.get("telemetry.machineId", ""),
                    telemetry_dev_device_id=data.get("telemetry.devDeviceId", ""),
                    telemetry_sqm_id=data.get("telemetry.sqmId", "")
                )
    except Exception as e:
        raise AppError(ERR_CONFIG, "read_config", config_path, e)
    return None

def save_config(config: StorageConfig, username: str) -> None:
    """保存配置"""
    config_path = get_config_path(username)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    # 确保文件可写
    if os.path.exists(config_path):
        os.chmod(config_path, 0o666)

        # 创建备份
        backup_path = f"{config_path}.{int(time.time())}.bak"
        try:
            with open(config_path, 'r', encoding='utf-8') as src, \
                 open(backup_path, 'w', encoding='utf-8') as dst:
                dst.write(src.read())
            log_print(f"\n已创建配置文件备份: {backup_path}", Colors.GREEN)
        except Exception as e:
            log_print(f"\n创建备份失败: {str(e)}", Colors.YELLOW)

    try:
        # 读取原始文件保留其他字段
        original_data = {}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
        
        # 更新配置
        new_data = {**original_data, **config.to_dict()}
        
        # 写入新配置
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2)
            
    except Exception as e:
        raise AppError(ERR_CONFIG, "save_config", config_path, e)

def get_running_cursor_processes() -> List[int]:
    """获取运行中的Cursor进程ID列表"""
    try:
        output = subprocess.check_output(["pgrep", "-i", "cursor"], text=True)
        return [int(pid) for pid in output.splitlines()]
    except subprocess.CalledProcessError:
        return []

def log_print(text: str, color: str = None, end: str = '\n'):
    """统一的打印和日志记录函数"""
    # 移除文本开头的换行符
    text = text.lstrip('\n')
    
    # 记录到日志（不含颜色代码）
    logging.info(text)
    
    # 直接打印到控制台（带颜色）
    if color:
        sys.stdout.write(f"{color}{text}{Colors.RESET}{end}")
    else:
        sys.stdout.write(f"{text}{end}")
    sys.stdout.flush()

def print_colored(text: str, color: str):
    """打印彩色文本并记录日志"""
    log_print(text, color)

def show_id_comparison(old_config: Optional[StorageConfig], new_config: StorageConfig):
    """显示ID对比"""
    print("\n=== ID 修改对比 ===")

    if old_config:
        print_colored("\n[原始 ID]", Colors.CYAN)
        print_colored(f"Machine ID: {old_config.telemetry_machine_id}", Colors.YELLOW)
        print_colored(f"Mac Machine ID: {old_config.telemetry_mac_machine_id}", Colors.YELLOW)
        print_colored(f"Dev Device ID: {old_config.telemetry_dev_device_id}", Colors.YELLOW)

    print_colored("\n[新生成 ID]", Colors.CYAN)
    print_colored(f"Machine ID: {new_config.telemetry_machine_id}", Colors.YELLOW)
    print_colored(f"Mac Machine ID: {new_config.telemetry_mac_machine_id}", Colors.YELLOW)
    print_colored(f"Dev Device ID: {new_config.telemetry_dev_device_id}", Colors.YELLOW)
    print_colored(f"SQM ID: {new_config.telemetry_sqm_id}\n", Colors.YELLOW)

def check_cursor_running() -> bool:
    """检查Cursor是否在运行"""
    pids = get_running_cursor_processes()
    if pids:
        log_print("发现正在运行的Cursor进程：", Colors.YELLOW)
        # 使用集合去重PID
        unique_pids = sorted(set(pids))
        for pid in unique_pids:
            log_print(f"PID: {pid}")
        log_print("请手动关闭这些进程后再运行本程序。", Colors.YELLOW)
        # 询问用户是否要自动关闭进程
        log_print("\n是否要自动关闭这些进程? [y/N] ", Colors.YELLOW, end='')
        choice = input().lower()
        if choice == 'y':
            # 自动关闭所有进程
            for pid in unique_pids:
                try:
                    subprocess.run(['kill', '-9', str(pid)], check=False)
                    log_print(f"已终止进程 {pid}", Colors.GREEN)
                except subprocess.SubprocessError:
                    log_print(f"终止进程 {pid} 失败", Colors.RED)
            return False
        else:       
            # 显示手动关闭的提示
            log_print("\n使用命令手动关闭: kill -9 <PID>")
            log_print("请手动关闭进程后重试...", Colors.YELLOW)
            # 提供命令预览方便复制执行
            log_print(f"kill -9 {' '.join(map(str, unique_pids))}", Colors.YELLOW)
            return True

def ensure_cursor_closed() -> Optional[str]:
    """确保Cursor已关闭"""
    max_attempts = 3
    log_print(f"⚡ 正在检查运行中的 Cursor 实例...", Colors.CYAN)

    for attempt in range(1, max_attempts + 1):
        if not get_running_cursor_processes():
            log_print(f"⚡ 所有 Cursor 实例已关闭", Colors.CYAN)
            log_print("")
            return None

        message = f"请在继续之前关闭 Cursor。尝试 {attempt}/{max_attempts}\n请稍候..."
        log_print(f"⚡ {message}", Colors.CYAN)
        time.sleep(5)

    return "cursor is still running"

def wait_exit():
    """等待退出"""
    if os.getenv("AUTOMATED_MODE") == "1":
        return

    input("\n按回车键退出程序...")

def print_cyberpunk_banner():
    """打印赛博朋克风格的横幅"""
    banner = """
    ██████╗██╗   ██╗██████╗ ███████╗ ██████╗ ██████╗
   ██╔════╝██║   ██║██╔══██╗██╔════╝██╔═══██╗██╔══██╗
   ██║     ██║   ██║██████╔╝███████╗██║   ██║█████╔╝
   ██║     ██║   ██║██╔══██╗╚════██║██║   ██║██╔══██╗
   ╚██████╗╚██████╔╝██║  ██║███████║╚██████╔╝██║  ██║
    ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝
    """
    print(f"{Colors.CYAN}{banner}{Colors.RESET}")
    print(f"{Colors.YELLOW}\t\t>> Cursor ID 修改工具 {VERSION} <<{Colors.RESET}")
    print(f"{Colors.MAGENTA}\t\t   [ By Pancake Fruit Rolled Shark Chili ]{Colors.RESET}")
    print(f"\n\t\t   {Colors.GREEN}当前语言：简体中文{Colors.RESET}\n")

def show_config(config: StorageConfig, title: str):
    """显示配置信息"""
    print_colored(f"\n[{title}]", Colors.CYAN)
    print_colored(f"Machine ID: {config.telemetry_machine_id}", Colors.YELLOW)
    print_colored(f"Mac Machine ID: {config.telemetry_mac_machine_id}", Colors.YELLOW)
    print_colored(f"Dev Device ID: {config.telemetry_dev_device_id}", Colors.YELLOW)
    print_colored(f"SQM ID: {config.telemetry_sqm_id}", Colors.YELLOW)

def confirm_action(prompt: str) -> bool:
    """获取用户确认"""
    while True:
        response = input(f"\n{prompt} (y/n): ").lower().strip()
        if response in ['y', 'yes', '是']:
            return True
        if response in ['n', 'no', '否']:
            return False
        print("请输入 y (是) 或 n (否)")

def setup_logging():
    """配置日志"""
    # 使用固定的日志文件名
    log_file = 'cursor_machine_id.log'
    
    # 创建文件处理器（详细日志，使用追加模式）
    file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    # 配置根日志记录器（只使用文件处理器）
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler]
    )
    
    # 添加分隔线，标记新的会话开始
    logging.info("="*50)
    logging.info("新会话开始")
    
    return log_file

def main():
    """主函数"""
    # 设置日志
    log_file = setup_logging()
    logging.info("程序启动")

    # 创建文本资源实例
    texts = TextResource()

    username = os.getenv("USER")
    if not username:
        log_print("错误：无法确定当前用户", Colors.RED)
        return

    # 记录基本信息
    logging.info(f"当前用户: {username}")
    logging.info(f"操作系统: {platform.system()}")
    logging.info(f"Python版本: {sys.version}")

    # 检查Cursor是否在运行
    if check_cursor_running():
        wait_exit()
        return

    # 清屏并显示横幅
    os.system('clear')
    print_cyberpunk_banner()

    try:
        # 读取当前配置
        log_print("\n正在读取当前配置...", Colors.CYAN)
        try:
            current_config = read_existing_config(username)
            if current_config:
                show_config(current_config, "当前配置")
            else:
                log_print("\n未找到现有配置", Colors.YELLOW)
        except AppError as e:
            log_print(f"\n读取配置失败: {str(e)}", Colors.RED)
            if not confirm_action("是否继续生成新配置？"):
                return

        # 生成新配置
        log_print("\n正在生成新配置...", Colors.CYAN)
        new_config = new_storage_config(current_config)
        show_config(new_config, "新生成配置")

        # 确认是否保存
        if not confirm_action("是否要使用新配置覆盖现有配置？"):
            log_print("\n操作已取消", Colors.YELLOW)
            wait_exit()
            return

        # 保存配置
        log_print("\n正在保存配置...", Colors.CYAN)
        save_config(new_config, username)

        log_print(f"\n{texts.success_message}", Colors.GREEN)
        log_print("\n操作完成！", Colors.GREEN)

    except Exception as e:
        log_print(f"错误: {str(e)}", Colors.RED)

    if os.getenv("AUTOMATED_MODE") != "1":
        wait_exit()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.warning("用户取消操作")
        log_print("\n操作已取消", Colors.YELLOW)
        sys.exit(1)
    except Exception as e:
        logging.error(f"发生致命错误: {str(e)}", exc_info=True)
        log_print(f"\n致命错误: {str(e)}", Colors.RED)
        sys.exit(1)
