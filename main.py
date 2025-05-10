# -*- coding: utf-8 -*-
import difflib
import json
import os
import random
import sys
import textwrap
import time
import webbrowser
from hashlib import md5

import requests
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QTextBlockFormat, QTextCharFormat, QColor, QTextCursor
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QTextEdit, QComboBox, QPushButton, QLabel, QProgressBar, QMessageBox,
                             QDialog, QVBoxLayout, QLineEdit, QFrame,
                             QTabWidget)


def levenshtein_distance(s1, s2):
    """计算两个字符串的编辑距离"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


class APIConfigDialog(QDialog):
    """API配置弹窗"""

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.initUI()

    def initUI(self):
        self.setWindowTitle('API配置')
        self.setGeometry(200, 200, 500, 300)

        layout = QVBoxLayout()

        # API配置说明
        info_label = QLabel('请配置百度翻译API信息：')
        layout.addWidget(info_label)

        # APPID输入
        appid_layout = QHBoxLayout()
        appid_label = QLabel('APPID:')
        self.appid_input = QLineEdit()
        self.appid_input.setText(self.settings.value('api/appid', ''))
        appid_layout.addWidget(appid_label)
        appid_layout.addWidget(self.appid_input)
        layout.addLayout(appid_layout)

        # APPKEY输入
        appkey_layout = QHBoxLayout()
        appkey_label = QLabel('APPKEY:')
        self.appkey_input = QLineEdit()
        self.appkey_input.setText(self.settings.value('api/appkey', ''))
        appkey_layout.addWidget(appkey_label)
        appkey_layout.addWidget(self.appkey_input)
        layout.addLayout(appkey_layout)

        # 按钮布局
        button_layout = QHBoxLayout()

        # 注册链接按钮
        register_button = QPushButton('注册账号')
        register_button.clicked.connect(lambda: webbrowser.open('https://fanyi-api.baidu.com/'))

        # 测试连接按钮
        test_button = QPushButton('测试连接')
        test_button.clicked.connect(self.test_connection)

        # 保存按钮
        save_button = QPushButton('保存配置')
        save_button.clicked.connect(self.save_config)

        button_layout.addWidget(register_button)
        button_layout.addWidget(test_button)
        button_layout.addWidget(save_button)
        layout.addLayout(button_layout)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # 版本说明
        version_info = QLabel("""版本说明：
        标准版：每月免费5万字符
        高级版：(实名认证后)每月100万字符
        """)
        version_info.setStyleSheet("color: gray;")
        layout.addWidget(version_info)

        # 当前使用量
        self.usage_label = QLabel('本月已使用：0 字符')
        layout.addWidget(self.usage_label)

        self.setLayout(layout)

    def test_connection(self):
        """测试API连接"""
        appid = self.appid_input.text().strip()
        appkey = self.appkey_input.text().strip()

        if not appid or not appkey:
            QMessageBox.warning(self, "警告", "请输入APPID和APPKEY")
            return

        # 创建临时翻译器测试连接
        translator = TranslationAPI(appid, appkey)
        result = translator.translate("测试", "zh", "en")

        if '错误' not in result and '失败' not in result:
            QMessageBox.information(self, "成功", "API连接测试成功！")
        else:
            QMessageBox.warning(self, "失败", f"API连接测试失败：{result}")

    def save_config(self):
        """保存API配置"""
        appid = self.appid_input.text().strip()
        appkey = self.appkey_input.text().strip()

        if not appid or not appkey:
            QMessageBox.warning(self, "警告", "请输入APPID和APPKEY")
            return

        self.settings.setValue('api/appid', appid)
        self.settings.setValue('api/appkey', appkey)
        QMessageBox.information(self, "成功", "配置保存成功！")
        self.accept()


class LogDialog(QDialog):
    """日志窗口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('翻译日志')
        self.setGeometry(200, 200, 500, 300)

        layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        self.setLayout(layout)

    def append_log(self, log):
        """添加日志"""
        self.log_text.append(log)
        self.log_text.update()
        self.log_text.repaint()
        QApplication.processEvents()


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self.config_file = 'config.json'
        self.config = self.load_config()

    def load_config(self):
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {'appid': '', 'appkey': ''}
        return {'appid': '', 'appkey': ''}

    def save_config(self, appid, appkey):
        """保存配置"""
        self.config = {
            'appid': appid,
            'appkey': appkey
        }
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            return True
        except:
            return False

    def get_config(self):
        """获取配置"""
        return self.config


class TranslationAPI:
    def __init__(self, appid=None, appkey=None):
        self.appid = appid
        self.appkey = appkey
        self.endpoint = 'http://api.fanyi.baidu.com'
        self.translate_path = '/api/trans/vip/translate'
        self.translate_url = self.endpoint + self.translate_path
        self.headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        self.max_text_length = 6000  # 最大文本长度限制
        self.segment_size = 2000  # 分段大小
        self.config_manager = ConfigManager()
        self.is_authenticated = False

    def validate_credentials(self):
        """验证API凭证的有效性"""
        if not self.appid or not self.appkey:
            return False, "API凭证未配置"
            
        if not self.appid.isdigit():
            return False, "APPID格式不正确"
            
        if len(self.appkey) < 20:
            return False, "APPKEY格式不正确"
            
        return True, "验证通过"

    def make_md5(self, s, encoding='utf-8'):
        return md5(s.encode(encoding)).hexdigest()

    def check_text_length(self, text):
        """检查文本长度是否超过限制"""
        if len(text) > self.max_text_length:
            return False, f"文本长度超过限制（{len(text)}/{self.max_text_length}），请删除 {len(text) - self.max_text_length} 个字符"
        return True, ""

    def split_text(self, text):
        """将文本分割为适当大小的段落"""
        # 按句号分割文本
        sentences = text.split('。')
        segments = []
        current_segment = ''

        for sentence in sentences:
            # 如果句子不是空的，加上句号
            if sentence:
                sentence = sentence + '。'

            # 如果当前段落加上新句子超过限制
            if len(current_segment) + len(sentence) > self.segment_size:
                if current_segment:
                    segments.append(current_segment)
                current_segment = sentence
            else:
                current_segment += sentence

        # 添加最后一个段落
        if current_segment:
            segments.append(current_segment)

        return segments

    def translate(self, text, from_lang, to_lang, retries=3, log_callback=None):
        if not text:
            return "错误: 输入文本为空"

        # 在每次翻译前验证API凭证
        is_valid, msg = self.validate_credentials()
        if not is_valid:
            return f"错误: {msg}"

        # 检查总文本长度
        is_valid, error_msg = self.check_text_length(text)
        if not is_valid:
            return error_msg

        # 分段处理
        segments = self.split_text(text)
        translated_segments = []

        for segment in segments:
            for attempt in range(retries):
                salt = random.randint(32768, 65536)
                sign = self.make_md5(self.appid + segment + str(salt) + self.appkey)

                payload = {
                    'appid': self.appid,
                    'q': segment,
                    'from': from_lang,
                    'to': to_lang,
                    'salt': salt,
                    'sign': sign,
                    'random': str(random.random())
                }

                try:
                    response = requests.post(self.translate_url, params=payload, headers=self.headers, timeout=20)
                    response.raise_for_status()
                    result = response.json()
                    
                    # 检查API返回的错误码
                    if 'error_code' in result:
                        error_msg = f"API错误: {result.get('error_code')} - {result.get('error_msg', '未知错误')}"
                        if result.get('error_code') in ['52001', '52002']:  # 超时错误，可以重试
                            if attempt == retries - 1:
                                return error_msg
                            time.sleep(1)
                            continue
                        return error_msg  # 其他错误直接返回
                        
                    if 'trans_result' in result:
                        translated_segments.append(result['trans_result'][0]['dst'])
                        break
                    else:
                        error = f"翻译错误: {result.get('error_code', '未知错误')} - {result.get('error_msg', '无错误信息')}"
                        if attempt == retries - 1:
                            return error
                except requests.exceptions.RequestException as e:
                    error = f"请求失败: {str(e)}"
                    if attempt == retries - 1:
                        return error
                time.sleep(1)  # 重试前延迟
            time.sleep(1)  # 每段翻译后延迟

        return ''.join(translated_segments)

    def set_api_info(self, appid, appkey):
        """设置API信息并保存"""
        # 验证新的API凭证
        self.appid = appid
        self.appkey = appkey
        is_valid, msg = self.validate_credentials()
        if not is_valid:
            return False
            
        # 保存到配置文件
        return self.config_manager.save_config(appid, appkey)


class InstructionDialog(QDialog):
    """使用说明弹窗"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('使用说明')
        self.setGeometry(200, 200, 600, 400)

        layout = QVBoxLayout()

        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_content = textwrap.dedent("""
            使用说明：
            1. 在"原文输入"框中输入需要降重的文章内容。
            2. 在"降重模式"下拉框中选择模式（初级、中级、高级）。
            3. 点击"开始降重"按钮，等待处理完成。
            4. 查看"降重结果"框中的输出和"降重率"显示。
            5. 不支持分段降重，如有2段及以上请删除段落符号再进行操作。

            软件原理：
            利用百度翻译通用API在不同语言间转换，由于不同语言语序不同，转换后可有效降重。
            - 初级：中 -> 英 -> 德 -> 中
            - 中级：中 -> 英 -> 德 -> 日 -> 葡萄牙 -> 中
            - 高级：中 -> 英 -> 德 -> 日 -> 葡萄牙 -> 意大利 -> 波兰 -> 保加利亚 -> 爱沙尼亚 -> 中

            示例：
            原文：随着信息技术的不断发展与进步，人们在21世纪已经进入互联网的时代...
            降重后：随着信息技术的持续发展和进步，21世纪的人们已进入互联网时代...
        """).strip()
        info_text.setText(info_content)

        layout.addWidget(info_text)
        self.setLayout(layout)


class ComparisonWidget(QWidget):
    """文本对比组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)

        # 创建对比文本显示区
        self.diff_text = QTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setStyleSheet("""
            QTextEdit {
                font-family: SimSun;
                font-size: 12pt;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.diff_text)

    def show_diff(self, text1, text2):
        """显示文本差异"""
        differ = difflib.Differ()
        diff = list(differ.compare(text1.splitlines(), text2.splitlines()))

        self.diff_text.clear()
        cursor = self.diff_text.textCursor()

        # 设置格式
        normal_format = QTextCharFormat()
        normal_format.setBackground(Qt.white)

        removed_format = QTextCharFormat()
        removed_format.setBackground(QColor(255, 200, 200))  # 浅红色

        added_format = QTextCharFormat()
        added_format.setBackground(QColor(200, 255, 200))  # 浅绿色

        # 设置两端对齐和首行缩进
        block_format = QTextBlockFormat()
        block_format.setAlignment(Qt.AlignJustify)
        block_format.setTextIndent(24)  # 设置首行缩进为24像素（约2个汉字）

        for line in diff:
            cursor.movePosition(QTextCursor.End)
            cursor.insertBlock(block_format)

            if line.startswith('- '):
                cursor.insertText(line[2:], removed_format)
            elif line.startswith('+ '):
                cursor.insertText(line[2:], added_format)
            elif line.startswith('  '):
                cursor.insertText(line[2:], normal_format)


class WordCountTextEdit(QTextEdit):
    """带字数统计的文本编辑框"""

    def __init__(self, parent=None, counter_label=None):
        super().__init__(parent)
        self.counter_label = counter_label
        self.textChanged.connect(self.update_word_count)

        # 设置两端对齐和首行缩进
        block_format = QTextBlockFormat()
        block_format.setAlignment(Qt.AlignJustify)
        block_format.setTextIndent(24)  # 设置首行缩进为24像素（约2个汉字）
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.setBlockFormat(block_format)

        # 设置样式
        self.setStyleSheet("""
            QTextEdit {
                font-family: SimSun;
                font-size: 12pt;
                line-height: 1.5;
            }
        """)

    def update_word_count(self):
        """更新字数统计"""
        text = self.toPlainText()
        char_count = len(text)
        word_count = len(text.split())
        if self.counter_label:
            self.counter_label.setText(f'字符数：{char_count} | 词数：{word_count}')

    def insertFromMimeData(self, source):
        """重写粘贴处理，保持格式"""
        cursor = self.textCursor()
        block_format = QTextBlockFormat()
        block_format.setAlignment(Qt.AlignJustify)
        block_format.setTextIndent(24)  # 设置首行缩进为24像素
        cursor.setBlockFormat(block_format)

        if source.hasText():
            text = source.text()
            # 分段处理文本
            paragraphs = text.split('\n')
            for i, para in enumerate(paragraphs):
                if i > 0:  # 不是第一段时，先插入换行
                    cursor.insertBlock(block_format)
                cursor.insertText(para.strip())
        else:
            super().insertFromMimeData(source)


class ReduceSimilarityApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('YourCompany', 'ArticleReducer')
        self.translation_api = TranslationAPI()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('文章降重助手')
        self.setGeometry(100, 100, 1385, 950)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # API配置区域
        api_frame = QFrame()
        api_frame.setFrameShape(QFrame.StyledPanel)
        api_layout = QVBoxLayout(api_frame)

        api_title = QLabel('API配置')
        api_title.setStyleSheet('font-size: 14px; font-weight: bold;')
        api_layout.addWidget(api_title)

        # 使用保存的API配置
        config = self.translation_api.config_manager.get_config()
        self.appid_input = QLineEdit()
        self.appid_input.setPlaceholderText('请输入APPID')
        self.appid_input.setText(config.get('appid', ''))
        api_layout.addWidget(QLabel('APPID:'))
        api_layout.addWidget(self.appid_input)

        self.appkey_input = QLineEdit()
        self.appkey_input.setPlaceholderText('请输入APPKEY')
        self.appkey_input.setText(config.get('appkey', ''))
        self.appkey_input.setEchoMode(QLineEdit.Password)
        api_layout.addWidget(QLabel('APPKEY:'))
        api_layout.addWidget(self.appkey_input)

        test_button = QPushButton('测试连接')
        test_button.clicked.connect(self.test_api_connection)
        api_layout.addWidget(test_button)

        # 添加按钮布局
        button_layout = QHBoxLayout()
        register_button = QPushButton('注册账号')
        register_button.clicked.connect(lambda: webbrowser.open('https://fanyi-api.baidu.com/'))
        button_layout.addWidget(register_button)
        api_layout.addLayout(button_layout)

        # 添加API配置说明
        api_help = QLabel('''
        API配置说明：
        1. 访问百度翻译开放平台注册账号
        2. 创建应用获取APPID和APPKEY
        3. 标准版每月免费5万字符
        4. 高级版每月免费100万字符(需实名认证)
        ''')
        api_help.setStyleSheet('color: #666;')
        api_layout.addWidget(api_help)

        left_layout.addWidget(api_frame)

        # 使用说明区域
        instruction_group = QFrame()
        instruction_group.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        instruction_layout = QVBoxLayout(instruction_group)

        instruction_title = QLabel('使用说明')
        instruction_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        instruction_layout.addWidget(instruction_title)

        instruction_text = QTextEdit()
        instruction_text.setReadOnly(True)
        instruction_content = textwrap.dedent("""
            使用步骤：
            1. 配置API：
               - 点击"注册账号"前往百度翻译开放平台注册
               - 将获取的APPID和APPKEY填入上方对应输入框
               - 点击"测试连接"确保API可用
               - 点击"保存配置"保存API信息

            2. 降重操作：
               - 在右侧"原文输入"框中输入或粘贴文章
               - 选择降重模式（字符限制：标准版5万字符/月）
               - 点击"开始降重"，等待处理完成
               - 降重完成后可查看降重率
               - 使用"一键复制"获取降重结果

            降重模式说明：
            - 初级：中 -> 英 -> 德 -> 中
            - 中级：中 -> 英 -> 德 -> 日 -> 葡萄牙 -> 中
            - 高级：中 -> 英 -> 德 -> 日 -> 葡萄牙 -> 意大利 -> 波兰 -> 保加利亚 -> 爱沙尼亚 -> 中

            注意事项：
            1. 首次使用需要配置API信息
            2. 请注意API使用量限制
            3. 建议先使用初级模式测试效果
            4. 高级模式翻译路径更长，耗时更多
            5. 降重率越高表示文章改动越大
        """).strip()
        instruction_text.setText(instruction_content)
        instruction_text.setStyleSheet("background-color: #f5f5f5;")
        instruction_layout.addWidget(instruction_text)

        left_layout.addWidget(instruction_group)

        main_layout.addWidget(left_panel, 1)  # 左侧面板占比1

        # 右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 降重率显示
        similarity_layout = QHBoxLayout()
        self.similarity_label = QLabel('降重率: 未计算')
        formula_label = QLabel('(编辑距离/原文长度 × 100%)')
        formula_label.setStyleSheet("color: gray;")
        similarity_layout.addWidget(self.similarity_label)
        similarity_layout.addWidget(formula_label)
        similarity_layout.addStretch()
        right_layout.addLayout(similarity_layout)

        # 创建选项卡
        tab_widget = QTabWidget()

        # 编辑页面
        edit_widget = QWidget()
        edit_layout = QVBoxLayout(edit_widget)

        # 输入区域
        input_group = QFrame()
        input_group.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        input_layout = QVBoxLayout(input_group)

        input_header = QHBoxLayout()
        input_label = QLabel('原文输入:')
        paste_button = QPushButton('一键粘贴')
        paste_button.clicked.connect(self.paste_text)
        self.input_counter = QLabel('字符数：0 | 词数：0')
        input_header.addWidget(input_label)
        input_header.addWidget(paste_button)
        input_header.addWidget(self.input_counter)
        input_header.addStretch()
        input_layout.addLayout(input_header)

        self.input_text = WordCountTextEdit(counter_label=self.input_counter)
        self.input_text.setPlaceholderText('请输入需要降重的文章内容...')
        self.input_text.setMinimumHeight(200)
        input_layout.addWidget(self.input_text)

        edit_layout.addWidget(input_group)

        # 模式选择和降重按钮
        control_layout = QHBoxLayout()
        mode_label = QLabel('降重模式:')
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(['初级', '中级', '高级'])
        self.translate_button = QPushButton('开始降重')
        self.translate_button.clicked.connect(self.reduce_similarity)
        control_layout.addWidget(mode_label)
        control_layout.addWidget(self.mode_combo)
        control_layout.addWidget(self.translate_button)
        control_layout.addStretch()
        edit_layout.addLayout(control_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignCenter)
        edit_layout.addWidget(self.progress_bar)

        # 输出区域
        output_group = QFrame()
        output_group.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        output_layout = QVBoxLayout(output_group)

        output_header = QHBoxLayout()
        output_label = QLabel('降重结果:')
        copy_button = QPushButton('一键复制')
        copy_button.clicked.connect(self.copy_text)
        self.output_counter = QLabel('字符数：0 | 词数：0')
        output_header.addWidget(output_label)
        output_header.addWidget(copy_button)
        output_header.addWidget(self.output_counter)
        output_header.addStretch()
        output_layout.addLayout(output_header)

        self.output_text = WordCountTextEdit(counter_label=self.output_counter)
        self.output_text.setReadOnly(True)
        self.output_text.setPlaceholderText('降重后的文章将显示在这里...')
        self.output_text.setMinimumHeight(200)
        output_layout.addWidget(self.output_text)

        edit_layout.addWidget(output_group)

        # 添加编辑页面到选项卡
        tab_widget.addTab(edit_widget, "编辑")

        # 对比页面
        self.comparison_widget = ComparisonWidget()
        tab_widget.addTab(self.comparison_widget, "对比")

        right_layout.addWidget(tab_widget)
        main_layout.addWidget(right_panel, 2)  # 右侧面板占比2

    def test_api_connection(self):
        """测试API连接"""
        appid = self.appid_input.text().strip()
        appkey = self.appkey_input.text().strip()

        # 验证输入格式
        if not appid or not appkey:
            QMessageBox.warning(self, '警告', '请输入APPID和APPKEY')
            return
        
        # 验证APPID格式（通常为数字字符串）
        if not appid.isdigit():
            QMessageBox.warning(self, '警告', 'APPID格式不正确，应为纯数字')
            return

        # 验证APPKEY格式（通常为固定长度的字符串）
        if len(appkey) < 20:  # 百度API的APPKEY通常较长
            QMessageBox.warning(self, '警告', 'APPKEY格式不正确，长度不够')
            return

        # 保存API配置
        if not self.translation_api.set_api_info(appid, appkey):
            QMessageBox.warning(self, '警告', '保存API配置失败')
            return

        # 进行严格的API验证测试
        try:
            # 使用特定的测试文本进行验证
            test_text = "API验证测试"
            result = self.translation_api.translate(test_text, 'zh', 'en')
            
            # 检查返回结果是否包含错误信息
            if isinstance(result, str) and ('错误' in result or '失败' in result):
                error_msg = result.split(': ')[-1] if ': ' in result else result
                QMessageBox.warning(self, '验证失败', f'API验证失败：{error_msg}\n请检查APPID和APPKEY是否正确')
                return
                
            # 验证翻译结果不为空且确实进行了翻译
            if not result or result == test_text:
                QMessageBox.warning(self, '验证失败', 'API响应异常，请检查配置是否正确')
                return
                
            QMessageBox.information(self, '成功', 'API验证成功！配置已保存。')
            
        except Exception as e:
            QMessageBox.warning(self, '错误', f'API验证失败：{str(e)}\n请检查网络连接和API配置')
            return

    def paste_text(self):
        """粘贴剪贴板内容到输入框"""
        clipboard = QApplication.clipboard()
        self.input_text.setText(clipboard.text())

    def copy_text(self):
        """复制输出框内容到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.output_text.toPlainText())
        QMessageBox.information(self, "提示", "复制成功！", QMessageBox.Ok)

    def calculate_similarity(self, original, translated):
        """计算降重率（编辑距离/原文长度）"""
        if not original or not translated:
            return 0.0
        edit_distance = levenshtein_distance(original, translated)
        similarity = (edit_distance / len(original)) * 100
        return min(similarity, 100.0)

    def reduce_similarity(self):
        text = self.input_text.toPlainText().strip()
        if not text:
            self.output_text.setText('请输入需要降重的文章！')
            self.output_text.update()
            self.output_text.repaint()
            self.similarity_label.setText('降重率: 未计算')
            return

        # 检查文本长度
        is_valid, error_msg = self.translation_api.check_text_length(text)
        if not is_valid:
            QMessageBox.warning(self, "警告", error_msg)
            return

        mode = self.mode_combo.currentText()
        if mode == '初级':
            languages = ['zh', 'en', 'de', 'zh']
        elif mode == '中级':
            languages = ['zh', 'en', 'de', 'jp', 'pt', 'zh']
        else:  # 高级
            languages = ['zh', 'en', 'de', 'jp', 'pt', 'it', 'pl', 'bul', 'est', 'zh']

        self.translate_button.setEnabled(False)  # 禁用按钮
        self.output_text.clear()  # 清空输出框
        self.similarity_label.setText('降重率: 计算中...')
        total_steps = len(languages) - 1
        current_text = text

        for i in range(total_steps):
            from_lang = languages[i]
            to_lang = languages[i + 1]
            result = self.translation_api.translate(current_text, from_lang, to_lang)
            if '错误' in result or '失败' in result:
                self.output_text.setText(f"翻译失败（{from_lang} -> {to_lang}）: {result}")
                self.translate_button.setEnabled(True)
                self.progress_bar.setValue(0)
                self.similarity_label.setText('降重率: 未计算')
                self.output_text.update()
                self.output_text.repaint()
                return
            current_text = result
            # 更新进度条
            self.progress_bar.setValue(int((i + 1) / total_steps * 100))
            QApplication.processEvents()

        self.output_text.setText(current_text)
        self.output_text.update()
        self.output_text.repaint()
        # 计算并显示降重率
        similarity = self.calculate_similarity(text, current_text)
        self.similarity_label.setText(f'降重率: {similarity:.1f}%')
        self.translate_button.setEnabled(True)

        # 更新对比视图
        self.comparison_widget.show_diff(text, current_text)

    def append_log(self, log):
        """处理日志信息（现在只更新使用量）"""
        if '段落长度' in log:
            chars = int(log.split(': ')[1])
            self.usage_label.setText(f'本月已使用：{self.translation_api.char_count} 字符')
            self.usage_label.update()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ReduceSimilarityApp()
    window.show()
    sys.exit(app.exec_())