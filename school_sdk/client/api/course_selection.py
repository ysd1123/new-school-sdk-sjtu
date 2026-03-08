# -*- coding: utf-8 -*-

import re
import typing as t
from collections import OrderedDict

from pyquery import PyQuery as pq

from school_sdk.client.api import BaseCrawler


class CourseSelection(BaseCrawler):
    """自主选课课程信息查询

    提供两个主要公开方法：
    - get_tabs(): 获取当前登录用户可选择的所有页签（Tab）信息
    - search_courses(): 在指定页签下搜索可选课程及教学班详情
    """

    GNMKDM = 'N253512'
    DEFAULT_PAGE_STEP = 10

    # 筛选条件键名映射：SDK 用户友好名称 → 教务系统表单参数名
    FILTER_KEY_MAP = {
        'college':         'kkbm_id_list',     # 开课学院
        'campus':          'xq_list',          # 校区
        'course_nature':   'kcxzdm_list',      # 课程性质
        'course_category': 'kcgs_list',        # 课程归属
        'teaching_mode':   'jxms_list',        # 教学模式
        'weekday':         'sksj_list',        # 上课星期
        'period':          'skjc_list',        # 上课节次
        'class_name':      'jxbmc_list',       # 教学班名称（文本）
        'retake':          'cxbj_list',        # 是否重修
        'has_capacity':    'yl_list',          # 有无余量
    }

    def __init__(self, user_client) -> None:
        super().__init__(user_client)
        self.endpoints: dict = self.school.config['url_endpoints']
        self._index_params: t.Optional[dict] = None
        self._tabs: t.Optional[list] = None
        self._tab_configs: dict = {}  # xkkz_id → per-tab config dict

    def get_tabs(self, **kwargs) -> list:
        """获取自主选课界面中当前登录用户可选择的所有页签信息

        无需传入参数，模拟用户打开自主选课页面后自动呈现的页签列表。

        Returns:
            list[dict]: 页签列表，按页面中从左到右的顺序排列。
                每个元素包含以下字段：
                - **name** (str): 页签显示名称，如 ``"主修课程"``、``"通识课"``
                - **kklxdm** (str): 开课类型代码
                - **xkkz_id** (str): 选课控制 ID（系统唯一标识）
                - **njdm_id** (str): 年级代码
                - **zyh_id** (str): 专业号
                - **is_default** (bool): 是否为默认选中页签

        Example::

            tabs = user.get_course_selection_tabs()
            for tab in tabs:
                print(tab['name'], tab['kklxdm'])
        """
        if self._tabs is None:
            self._load_index_page(**kwargs)
        return self._tabs

    def search_courses(self, tab: dict, keyword: str = '',
                       filters: t.Optional[dict] = None,
                       fetch_details: bool = True, **kwargs) -> list:
        """自主选课可选课程信息查询

        模拟用户在自主选课 Web 前端的搜索操作。自动处理内部的
        接口零→接口一→接口二三段式查询流程，无需关心底层参数。

        Args:
            tab (dict): 页签信息（**必填**），来自 :meth:`get_tabs` 返回的某个元素。
                相当于用户在网页上选中某个页签。

            keyword (str, optional): 搜索关键词，支持课程号、课程名称、
                教学班名称、教师姓名、教师工号等。留空则返回该页签下所有课程。

            filters (dict, optional): 筛选条件字典，所有项均为可选。
                可用的键名及含义：

                - **college** (str | list[str]): 开课学院 ID
                - **campus** (str | list[str]): 校区 ID
                - **course_nature** (str | list[str]): 课程性质代码
                - **course_category** (str | list[str]): 课程归属代码
                - **teaching_mode** (str | list[str]): 教学模式代码
                - **weekday** (str | list[str]): 上课星期（``"1"`` ~ ``"7"``）
                - **period** (str | list[str]): 上课节次（``"1"`` ~ ``"14"``）
                - **class_name** (str): 教学班名称关键词
                - **retake** (bool): 是否重修（True=仅重修, False=仅非重修）
                - **has_capacity** (bool): 有无余量（True=仅有余量, False=仅无余量）

                以上 str | list 类型的筛选项支持传入单个值或列表进行多选。
                列表/代码值可通过教务系统前端页面查看，或预先调用对应查询接口获取。

            fetch_details (bool, optional): 是否获取每门课程的教学班详情信息
                （教师、上课时间地点、选课容量等）。默认 ``True``。
                设为 ``False`` 可显著加速查询，但 ``teaching_classes`` 将为空列表。

        Returns:
            list[dict]: 课程列表，每个元素包含：

                - **course_code** (str): 课程号（如 ``"JC1004"``）
                - **course_name** (str): 课程名称
                - **credit** (str): 学分
                - **course_group** (str): 所属课程组
                - **kch_id** (str): 课程系统 ID（用于接口二查询）
                - **is_retake** (bool): 是否重修课程
                - **has_prerequisite** (bool): 是否有预修课要求
                - **is_recommended** (bool): 是否推荐课程（HOT）
                - **class_count** (int): 接口一返回的教学班计数
                - **teaching_classes** (list[dict]): 教学班详情列表，
                  每项含以下字段：

                    - **jxb_id** (str): 教学班系统 ID
                    - **do_jxb_id** (str): 操作用教学班 ID（防重放签名）
                    - **class_name** (str): 教学班名称
                    - **teachers** (list[dict]): 教师列表，每项含
                      ``id`` / ``name`` / ``title``
                    - **schedule** (str): 上课时间
                    - **location** (str): 上课地点
                    - **capacity** (int): 容量
                    - **enrolled** (int): 已选人数
                    - **credit** (str): 学分
                    - **course_nature** (str): 课程性质名称
                    - **course_type** (str): 课程类别名称
                    - **college** (str): 开课学院名称
                    - **campus** (str): 校区名称
                    - **teaching_mode** (str): 教学模式
                    - **language** (str): 授课语言
                    - **course_category** (str): 课程归属名称
                    - **remark** (str): 选课备注

        Example::

            tabs = user.get_course_selection_tabs()
            # 选择"通识课"页签
            ts_tab = next(t for t in tabs if t['name'] == '通识课')
            # 搜索包含 "AI" 的课程
            courses = user.search_elective_courses(ts_tab, keyword='AI')
            for c in courses:
                print(c['course_name'], c['credit'])
                for tc in c['teaching_classes']:
                    print(f"  {tc['class_name']} {tc['schedule']} "
                          f"{tc['enrolled']}/{tc['capacity']}")
        """
        # 确保已加载首页全局参数
        if self._index_params is None:
            self._load_index_page(**kwargs)

        # 步骤一：加载 per-Tab 配置参数（接口零）
        tab_config = self._load_tab_config(tab, **kwargs)

        # 步骤二：查询可选课程列表（接口一），自动翻页
        raw_items = self._fetch_all_courses(tab, tab_config, keyword, filters, **kwargs)

        # 步骤三：按课程分组
        grouped = self._group_courses(raw_items)

        # 构建 jxb_id → 接口一原始数据 的映射，用于补充接口二缺失字段（如 yxzrs）
        jxb_fallback: dict = {}
        for item in raw_items:
            jxb_id = item.get('jxb_id', '')
            if jxb_id:
                jxb_fallback[jxb_id] = item

        # 步骤四：格式化结果；如需要，逐课程查询教学班详情（接口二）
        result = []
        for course_info in grouped:
            course = self._format_course(course_info)
            if fetch_details:
                raw_classes = self._fetch_class_details(
                    tab, tab_config, course_info, keyword, filters, **kwargs
                )
                course['teaching_classes'] = [
                    self._format_class(c, jxb_fallback) for c in raw_classes
                ]
            result.append(course)

        return result


    #  内部方法 - 页面加载与解析

    def _load_index_page(self, **kwargs):
        """加载自主选课首页 (Index)，解析全局隐藏字段和页签列表"""
        url = self.endpoints.get('COURSE_SELECTION', {}).get(
            'INDEX', '/xsxk/zzxkyzb_cxZzxkYzbIndex.html'
        )
        params = {
            'gnmkdm': self.GNMKDM,
            'layout': 'default',
        }
        resp = self.get(url, params=params, **kwargs)
        html = resp.text
        doc = pq(html)

        # 解析全局隐藏字段（学生身份信息 + 选课配置）
        self._index_params = {}
        global_fields = [
            'xkxnm', 'xkxqm', 'xqh_id', 'jg_id_1', 'zyh_id', 'zyfx_id',
            'njdm_id', 'bh_id', 'xbm', 'xslbdm', 'mzm', 'xz', 'ccdm',
            'xsbj', 'njdm_id_1', 'zyh_id_1', 'xszxzt', 'xkmcjzxskcs',
            'xxdm', 'sfxsjxdd', 'sfxskssj', 'txbsfrl', 'dsfrlxskg',
            'xkbzsyljkg', 'xksjjfsjxskg', 'zzxkxsrwxfkg', 'xkxfqzfs',
            'xksdxjckg', 'jxbzbkg', 'jxbzhkg', 'bdzcbj',
            'xkczbj', 'xkxnmc', 'xkxqmc',
        ]
        for field in global_fields:
            el = doc(f'input#{field}')
            if el:
                self._index_params[field] = el.attr('value') or ''

        # 解析页签列表
        self._tabs = []
        tab_items = doc('#nav_tab li')
        for li in tab_items.items():
            a_tag = li.find('a')
            if not a_tag:
                continue
            onclick = a_tag.attr('onclick') or ''
            # 格式: queryCourse(this,'kklxdm','xkkz_id','njdm_id','zyh_id')
            match = re.search(
                r"queryCourse\(this,'([^']+)','([^']+)','([^']+)','([^']+)'\)",
                onclick
            )
            if match:
                self._tabs.append({
                    'name': a_tag.text().strip(),
                    'kklxdm': match.group(1),
                    'xkkz_id': match.group(2),
                    'njdm_id': match.group(3),
                    'zyh_id': match.group(4),
                    'is_default': 'active' in (li.attr('class') or ''),
                })

    def _load_tab_config(self, tab: dict, **kwargs) -> dict:
        """调用接口零 (Display)，加载指定页签的 per-Tab 配置参数

        配置参数包含选课行为控制（rwlx、sfkknj、sfkkzy 等）和选课
        时间窗口信息，由服务端根据当前选课批次动态下发。
        结果会缓存，同一页签不会重复请求。
        """
        cache_key = tab['xkkz_id']
        if cache_key in self._tab_configs:
            return self._tab_configs[cache_key]

        url = self.endpoints.get('COURSE_SELECTION', {}).get(
            'DISPLAY', '/xsxk/zzxkyzb_cxZzxkYzbDisplay.html'
        )
        data = {
            'xkkz_id': tab['xkkz_id'],
            'xszxzt': self._index_params.get('xszxzt', '1'),
            'kklxdm': tab['kklxdm'],
            'njdm_id': tab['njdm_id'],
            'zyh_id': tab['zyh_id'],
            'kspage': 0,
            'jspage': 0,
        }
        resp = self.post(url, params={'gnmkdm': self.GNMKDM}, data=data, **kwargs)
        doc = pq(resp.text)

        # 解析 per-Tab 配置隐藏字段
        config_fields = [
            # 选课行为控制
            'rwlx', 'xklc', 'xklcmc', 'xkly',
            'sfkknj', 'sfkkzy', 'sfznkx', 'zdkxms',
            'sfkxq', 'txbsfrl', 'rlzlkz', 'cdrlkz', 'rlkz',
            'sfkkjyxdxnxq', 'xkxskcgskg', 'jxbzcxskg',
            'tykczgxdcs', 'sfrxtgkcxd', 'sfkgbcx',
            'bklx_id', 'kzkcgs', 'kzybkxy', 'bhbcyxkjxb',
            'sfkcfx', 'kkbk', 'kkbkdj', 'bklbkcj',
            'bbhzxjxb', 'xkzgbj', 'gnjkxdnj',
            # 选课时间窗口
            'sfkxk', 'sfktk', 'xkkssj', 'xkjssj',
            'sfyxsksjct', 'isinxksj', 'isInylsj',
        ]
        tab_config = {}
        for field in config_fields:
            el = doc(f'input#{field}')
            if el:
                tab_config[field] = el.attr('value') or ''

        self._tab_configs[cache_key] = tab_config
        return tab_config

    #  内部方法 - 请求参数构建

    def _build_filter_params(self, keyword: str,
                             filters: t.Optional[dict]) -> dict:
        """构建搜索关键词和筛选条件的表单参数"""
        params: dict = {}

        # 搜索关键词
        if keyword:
            params['filter_list[0]'] = keyword

        if not filters:
            return params

        for user_key, value in filters.items():
            form_key = self.FILTER_KEY_MAP.get(user_key)
            if form_key is None:
                continue

            # 布尔型筛选项（是否重修、有无余量）转换为 '1'/'0'
            if user_key in ('retake', 'has_capacity'):
                if isinstance(value, bool):
                    value = '1' if value else '0'
                params[form_key] = str(value)
            elif isinstance(value, (list, tuple)):
                # 多选：使用索引格式 key[0], key[1], ...
                for i, v in enumerate(value):
                    params[f'{form_key}[{i}]'] = str(v)
            else:
                params[form_key] = str(value)

        return params

    def _build_course_list_params(self, tab: dict, tab_config: dict,
                                  keyword: str, filters: t.Optional[dict],
                                  kspage: int, jspage: int) -> dict:
        """构建接口一（查询课程列表）的完整请求参数"""
        p = self._index_params
        data = {}

        # 搜索与筛选
        data.update(self._build_filter_params(keyword, filters))

        # per-Tab 配置参数
        data.update({
            'rwlx':          tab_config.get('rwlx', ''),
            'xklc':          tab_config.get('xklc', ''),
            'xkly':          tab_config.get('xkly', '0'),
            'bklx_id':       tab_config.get('bklx_id', '0'),
            'sfkkjyxdxnxq':  tab_config.get('sfkkjyxdxnxq', '0'),
            'kzkcgs':        tab_config.get('kzkcgs', '0'),
            'sfkknj':        tab_config.get('sfkknj', '0'),
            'sfkkzy':        tab_config.get('sfkkzy', '0'),
            'kzybkxy':       tab_config.get('kzybkxy', '0'),
            'sfznkx':        tab_config.get('sfznkx', '0'),
            'zdkxms':        tab_config.get('zdkxms', '0'),
            'sfkxq':         tab_config.get('sfkxq', '1'),
            'bhbcyxkjxb':    tab_config.get('bhbcyxkjxb', '0'),
            'sfkcfx':        tab_config.get('sfkcfx', '0'),
            'kkbk':          tab_config.get('kkbk', '0'),
            'kkbkdj':        tab_config.get('kkbkdj', '0'),
            'bklbkcj':       tab_config.get('bklbkcj', '0'),
            'sfkgbcx':       tab_config.get('sfkgbcx', '1'),
            'sfrxtgkcxd':    tab_config.get('sfrxtgkcxd', '1'),
            'tykczgxdcs':    tab_config.get('tykczgxdcs', '10'),
            'bbhzxjxb':      tab_config.get('bbhzxjxb', '0'),
            'xkzgbj':        tab_config.get('xkzgbj', '0'),
            'gnjkxdnj':      tab_config.get('gnjkxdnj', '0'),
            'rlkz':          tab_config.get('rlkz', '0'),
        })

        # 全局 Index 页面参数（学生身份信息等）
        data.update({
            'xqh_id':     p.get('xqh_id', ''),
            'jg_id':      p.get('jg_id_1', ''),
            'njdm_id_1':  p.get('njdm_id_1', ''),
            'zyh_id_1':   p.get('zyh_id_1', ''),
            'zyh_id':     p.get('zyh_id', ''),
            'zyfx_id':    p.get('zyfx_id', ''),
            'njdm_id':    p.get('njdm_id', ''),
            'bh_id':      p.get('bh_id', ''),
            'xbm':        p.get('xbm', ''),
            'xslbdm':     p.get('xslbdm', ''),
            'mzm':        p.get('mzm', ''),
            'xz':         p.get('xz', ''),
            'ccdm':       p.get('ccdm', ''),
            'xsbj':       p.get('xsbj', ''),
            'xkxnm':      p.get('xkxnm', ''),
            'xkxqm':      p.get('xkxqm', ''),
        })

        # Tab 标识 + 分页
        data.update({
            'kklxdm':  tab['kklxdm'],
            'xkkz_id': tab['xkkz_id'],
            'kspage':  kspage,
            'jspage':  jspage,
        })

        return data

    def _build_class_detail_params(self, tab: dict, tab_config: dict,
                                   course_info: dict,
                                   keyword: str,
                                   filters: t.Optional[dict]) -> dict:
        """构建接口二（查询教学班详情）的完整请求参数"""
        p = self._index_params
        data = {}

        # 搜索与筛选（接口二同样需要携带，与前端行为一致）
        data.update(self._build_filter_params(keyword, filters))

        # per-Tab 配置参数
        data.update({
            'rwlx':          tab_config.get('rwlx', ''),
            'xklc':          tab_config.get('xklc', ''),
            'xkly':          tab_config.get('xkly', '0'),
            'bklx_id':       tab_config.get('bklx_id', '0'),
            'sfkkjyxdxnxq':  tab_config.get('sfkkjyxdxnxq', '0'),
            'kzkcgs':        tab_config.get('kzkcgs', '0'),
            'sfkknj':        tab_config.get('sfkknj', '0'),
            'sfkkzy':        tab_config.get('sfkkzy', '0'),
            'kzybkxy':       tab_config.get('kzybkxy', '0'),
            'sfznkx':        tab_config.get('sfznkx', '0'),
            'zdkxms':        tab_config.get('zdkxms', '0'),
            'sfkxq':         tab_config.get('sfkxq', '1'),
            'bhbcyxkjxb':    tab_config.get('bhbcyxkjxb', '0'),
            'sfkcfx':        tab_config.get('sfkcfx', '0'),
            'kkbk':          tab_config.get('kkbk', '0'),
            'kkbkdj':        tab_config.get('kkbkdj', '0'),
            'bklbkcj':       tab_config.get('bklbkcj', '0'),
            'bbhzxjxb':      tab_config.get('bbhzxjxb', '0'),
            'gnjkxdnj':      tab_config.get('gnjkxdnj', '0'),
            'rlkz':          tab_config.get('rlkz', '0'),
            # 接口二特有
            'txbsfrl':       tab_config.get('txbsfrl', '1'),
            'xkxskcgskg':    tab_config.get('xkxskcgskg', '0'),
            'cdrlkz':        tab_config.get('cdrlkz', '0'),
            'rlzlkz':        tab_config.get('rlzlkz', '1'),
            'jxbzcxskg':     tab_config.get('jxbzcxskg', '0'),
        })

        # 全局 Index 页面参数
        data.update({
            'xqh_id':     p.get('xqh_id', ''),
            'jg_id':      p.get('jg_id_1', ''),
            'zyh_id':     p.get('zyh_id', ''),
            'zyfx_id':    p.get('zyfx_id', ''),
            'njdm_id':    p.get('njdm_id', ''),
            'bh_id':      p.get('bh_id', ''),
            'xbm':        p.get('xbm', ''),
            'xslbdm':     p.get('xslbdm', ''),
            'mzm':        p.get('mzm', ''),
            'xz':         p.get('xz', ''),
            'ccdm':       p.get('ccdm', ''),
            'xsbj':       p.get('xsbj', ''),
            'xkxnm':      p.get('xkxnm', ''),
            'xkxqm':      p.get('xkxqm', ''),
        })

        # Tab 标识
        data.update({
            'kklxdm':  tab['kklxdm'],
            'xkkz_id': tab['xkkz_id'],
        })

        # 接口二特有：课程标识 + 课程属性标记
        data.update({
            'kch_id': course_info['kch_id'],
            'cxbj':   course_info.get('cxbj', '0'),
            'fxbj':   course_info.get('fxbj', '0'),
        })

        return data

    #  内部方法 - 接口调用

    def _fetch_all_courses(self, tab: dict, tab_config: dict,
                           keyword: str, filters: t.Optional[dict],
                           **kwargs) -> list:
        """自动翻页调用接口一，获取全部课程数据

        采用瀑布流分页（kspage/jspage 行号范围），持续请求直到
        服务端返回的最大 kcrow 不足一页为止。
        """
        url = self.endpoints.get('COURSE_SELECTION', {}).get(
            'COURSE_LIST', '/xsxk/zzxkyzb_cxZzxkYzbPartDisplay.html'
        )
        step = int(
            self._index_params.get('xkmcjzxskcs', '') or self.DEFAULT_PAGE_STEP
        )
        all_items: list = []
        kspage = 1
        jspage = step

        while True:
            data = self._build_course_list_params(
                tab, tab_config, keyword, filters, kspage, jspage
            )
            resp = self.post(
                url, params={'gnmkdm': self.GNMKDM}, data=data, **kwargs
            )

            # 响应为 "0" 表示会话失效或非法访问
            try:
                result = resp.json()
            except Exception:
                break

            if result == 0 or result == '0':
                break

            items = result.get('tmpList') or []
            if not items:
                break

            all_items.extend(items)

            # 若本页返回的最大 kcrow < jspage，说明已到最后
            max_kcrow = max(int(item.get('kcrow', 0)) for item in items)
            if max_kcrow < jspage:
                break

            kspage = jspage + 1
            jspage = kspage + step - 1

        return all_items

    def _fetch_class_details(self, tab: dict, tab_config: dict,
                             course_info: dict, keyword: str,
                             filters: t.Optional[dict],
                             **kwargs) -> list:
        """调用接口二，获取指定课程的教学班详情列表"""
        url = self.endpoints.get('COURSE_SELECTION', {}).get(
            'CLASS_DETAIL', '/xsxk/zzxkyzbjk_cxJxbWithKchZzxkYzb.html'
        )
        data = self._build_class_detail_params(
            tab, tab_config, course_info, keyword, filters
        )
        resp = self.post(
            url, params={'gnmkdm': self.GNMKDM}, data=data, **kwargs
        )

        try:
            result = resp.json()
        except Exception:
            return []

        # 响应为 "0" 表示非法访问
        if result == 0 or result == '0':
            return []

        # 接口二返回的是 JSON 数组（教学班列表）
        if isinstance(result, list):
            return result
        return []

    #  内部方法 - 数据处理与格式化

    @staticmethod
    def _group_courses(raw_items: list) -> list:
        """将接口一返回的扁平教学班列表按课程 (kch_id) 分组

        接口一的 tmpList 中，同一门课程的多个教学班共享相同的 kch_id
        和 kcrow。此方法将它们聚合为课程级别的信息。
        """
        courses: 'OrderedDict[str, dict]' = OrderedDict()
        for item in raw_items:
            kch_id = item.get('kch_id', '')
            if kch_id not in courses:
                courses[kch_id] = {
                    'kch_id': kch_id,
                    'kch':    item.get('kch', ''),
                    'kcmc':   item.get('kcmc', ''),
                    'xf':     item.get('xf', ''),
                    'kzmc':   item.get('kzmc', ''),
                    'cxbj':   item.get('cxbj', '0'),
                    'fxbj':   item.get('fxbj', '0'),
                    'xxkbj':  item.get('xxkbj', '0'),
                    'sftj':   item.get('sftj', ''),
                    'kklxdm': item.get('kklxdm', ''),
                    'class_count': 0,
                }
            courses[kch_id]['class_count'] += 1
        return list(courses.values())

    @staticmethod
    def _format_course(course_info: dict) -> dict:
        """将内部课程分组数据格式化为用户友好的结构"""
        return {
            'course_code':      course_info.get('kch', ''),
            'course_name':      course_info.get('kcmc', ''),
            'credit':           course_info.get('xf', ''),
            'course_group':     course_info.get('kzmc', ''),
            'kch_id':           course_info.get('kch_id', ''),
            'is_retake':        course_info.get('cxbj') == '1',
            'has_prerequisite':  course_info.get('xxkbj') == '1',
            'is_recommended':   course_info.get('sftj') == '1',
            'class_count':      course_info.get('class_count', 0),
            'teaching_classes': [],
        }

    @staticmethod
    def _parse_teachers(jsxx: str) -> list:
        """解析教师信息字符串

        教师信息格式: "工号/姓名/职称"，多教师以 ";" 分隔。
        """
        if not jsxx:
            return []
        teachers = []
        for teacher_str in jsxx.split(';'):
            teacher_str = teacher_str.strip()
            if not teacher_str:
                continue
            parts = teacher_str.split('/')
            if len(parts) >= 3:
                teachers.append({
                    'id': parts[0],
                    'name': parts[1],
                    'title': parts[2],
                })
            elif len(parts) == 2:
                teachers.append({
                    'id': parts[0],
                    'name': parts[1],
                    'title': '',
                })
            elif parts[0]:
                teachers.append({
                    'id': '',
                    'name': parts[0],
                    'title': '',
                })
        return teachers

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """安全转换为整数"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _format_class(self, class_data: dict,
                      jxb_fallback: t.Optional[dict] = None) -> dict:
        """将接口二返回的教学班原始数据格式化为用户友好的结构

        Args:
            class_data: 接口二返回的单个教学班 JSON 对象。
            jxb_fallback: jxb_id → 接口一原始数据 的映射字典，
                用于补充接口二缺失的字段（如 yxzrs 已选人数）。
        """
        jxb_id = class_data.get('jxb_id', '')
        fallback = (jxb_fallback or {}).get(jxb_id, {})

        # yxzrs（已选人数）在部分正方版本的接口二中不返回，
        # 需从接口一的 tmpList 数据中回退获取
        enrolled_val = class_data.get('yxzrs')
        if enrolled_val is None:
            enrolled_val = fallback.get('yxzrs')

        capacity_val = class_data.get('jxbrl')
        if capacity_val is None:
            capacity_val = fallback.get('jxbrl')

        return {
            'jxb_id':          jxb_id,
            'do_jxb_id':       class_data.get('do_jxb_id', ''),
            'class_name':      class_data.get('jxbmc', '') or fallback.get('jxbmc', ''),
            'teachers':        self._parse_teachers(class_data.get('jsxx', '')),
            'schedule':        class_data.get('sksj', ''),
            'location':        class_data.get('jxdd', ''),
            'capacity':        self._safe_int(capacity_val),
            'enrolled':        self._safe_int(enrolled_val),
            'credit':          class_data.get('xf', ''),
            'course_nature':   class_data.get('kcxzmc', ''),
            'course_type':     class_data.get('kclbmc', ''),
            'college':         class_data.get('kkxymc', ''),
            'campus':          class_data.get('xqumc', ''),
            'teaching_mode':   class_data.get('jxms', ''),
            'language':        class_data.get('skfsmc', ''),
            'course_category': class_data.get('kcgsmc', ''),
            'remark':          class_data.get('xkbz', ''),
        }
