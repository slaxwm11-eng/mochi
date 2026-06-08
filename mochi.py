from animal_cam import AnimalLiveCamera
import random
from flask import Flask, request, jsonify
from openai import OpenAI
import requests
import threading
import time
import random
import json
import os
import urllib3
import re
import textwrap
import uuid
import asyncio
import edge_tts
from datetime import datetime
from collections import Counter
import queue
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====================== Dota知识库加载 ======================
try:
    from dota_knowledge import get_retriever
    dota_retriever = get_retriever()
    print("✅ Dota知识库已就绪")
except Exception as e:
    print(f"⚠️ Dota知识库未加载: {e}")
    dota_retriever = None

app = Flask(__name__)

# ====================== 核心配置 ======================
class Config:
    API_KEY = "sk-4e45ca052e2d45f0b1d2e8a6c04c2782"
    BASE_URL = "https://api.deepseek.com"
    MODEL_SMART = "deepseek-v4-pro"
    MODEL_QUICK = "deepseek-v4-flash"

    NAPCAT_URL = "http://127.0.0.1:3000"
    NAPCAT_TOKEN = "fKzMS44OIMwQb1cq"

    # 落实理论：唯一的虚拟上下文外部存储（硬盘 Disk），彻底废弃双线记忆
    MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intelligent_memory.json")
    STRATZ_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJTdWJqZWN0IjoiNjYzOTllYjctMTM3Ny00NWE2LWI2NDUtMDhhMjMyY2E2ZTUyIiwiU3RlYW1JZCI6IjEyNjMxNTI5MDYiLCJBUElVc2VyIjoidHJ1ZSIsIm5iZiI6MTc3ODcyMzA1MiwiZXhwIjoxODEwMjU5MDUyLCJpYXQiOjE3Nzg3MjMwNTIsImlzcyI6Imh0dHBzOi8vYXBpLnN0cmF0ei5jb20ifQ.TVZRy_pgKssaZe9mLtMrVDFUP0ZowOk0c-Mi2w7em-Y"

    MEMBERS = {
        1678816714: {"name": "阎", "call": "捞盐", "roasts": ["捞盐", "阎丑"]},
        812292462:  {"name": "浩", "call": "捞浩", "roasts": ["捞浩"]},
        1741231405: {"name": "周", "call": "捞周", "roasts": ["捞周"]},
        1263620238: {"name": "骆", "call": "骆哥", "roasts": ["骆哥", "骆丑"]},
        1403913257: {"name": "葛", "call": "捞葛", "roasts": ["捞葛"]},
        3036561506: {"name": "何", "call": "捞何", "roasts": ["何丑"]},
        344407517:  {"name": "赵", "call": "捞赵", "roasts": ["赵丑"]},
        2402375990: {"name": "戴", "call": "老戴", "roasts": ["兵哥"]},
    }

    DOTA_KEYWORDS = ["dota", "刀塔", "一号位", "二号位", "三号位", "四号位", "五号位"]
    VOICE_PROBABILITY = 0.8  # 触发语音的概率
    AUDIO_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_cache")
    # NASA 官方给极客提供的免费 DEMO KEY（每天有少量限制，正式用可以去 api.nasa.gov 免费秒申一个专属的）
    NASA_API_KEY = "DEMO_KEY"
    NASA_URL = "https://api.nasa.gov/planetary/apod"
def clean_bot_text(text: str) -> str:
    """
    【晓晓定制增强版】TTS 读音修正与清洗引擎
    """
    if not text:
        return ""

    # 1. 物理清洗：干掉括号及动作描写
    cleaned = re.sub(r'^[\(（].*?[\)）]', '', text).strip()

    # 2. 字母黑话与游戏缩写强制汉化/修正发音
    slang_map = {
        # 常见骂人与情绪缩写
        r'(?i)\bcnm\b': '草泥马',
        r'(?i)\bsb\b': '傻逼',
        r'(?i)\bnt\b': '脑瘫',
        r'(?i)\bfw\b': '废物',
        r'(?i)\brz\b': '弱智',
        r'(?i)\bmd\b': '妈的',
        r'(?i)\btmd\b': '他妈的',
        r'(?i)\bwc\b': '卧槽',
        r'(?i)\bnb\b': '牛逼',
        r'(?i)\bgg\b': '寄了',  # 把GG替换成更接地气的“寄了”

        # 针对 Dota 常见字母强制拆分，防止引擎连读成奇怪的单词
        r'(?i)\bkda\b': 'K D A',
        r'(?i)\bgpm\b': 'G P M',
        r'(?i)\bbkb\b': 'B K B',
        r'(?i)\bdps\b': 'D P S',
    }
    for pattern, replacement in slang_map.items():
        cleaned = re.sub(pattern, replacement, cleaned)

    # 3. 语气词与标点符号强制纠偏（核心灵魂区）
    voice_tweaks = {
        # 不屑/冷漠系列
        "啧啧": "切——，切——，",
        "啧": "切——，",
        "呵呵": "呵，",
        "无语": "真是无语，",
        "草": "靠",
        "唉": "哎——，",          # 强迫拉长音的叹气
        "哎": "哎——，",

        # 惊讶/嘲讽系列
        "啊？": "啊？？",
        "啥？": "啥？？",
        "不是吧": "不是吧？？",
        "怎么说": "怎么说——，",

        # 情绪拉长音 (破折号是微软 TTS 的神器)
        "尽力了": "尽——力——了，",
        "拉跨": "拉——跨——，",
        "菜狗": "菜——狗，",
        "绝了": "绝——了，",
        "我去": "我——去——，",

        # 笑声修正 (防止连续读“哈哈哈”像机器枪，用逗号强行断句制造冷笑感)
        "哈哈哈": "哈，哈，哈，",
        "哈哈": "哈，哈，",

        # 停顿与呼吸感
        "...": "，，，",
        "。。。": "，，，",
        "~": "——",               # 微软有时不读波浪号，换成破折号拉长音
    }

    for old_word, new_word in voice_tweaks.items():
        cleaned = cleaned.replace(old_word, new_word)

    # 4. 终极标点强化：强行拉高所有问句的声调
    # 负向先行断言，把所有单独的问号替换成双问号，逼迫晓晓声调上扬
    cleaned = re.sub(r'(?<!\?)\?(?!\?)', '？？', cleaned)
    cleaned = re.sub(r'(?<!？)？(?!？)', '？？', cleaned)

    return cleaned.strip()

# ====================== 记忆模型定义 (Pydantic Schema) ======================
class MemoryFact(BaseModel):
    trait_type: str = Field(description="记忆类别，例如：人际关系, 性格特点, 长期偏好, 历史事件")
    content: str = Field(description="详细的、经过高度总结的记忆内容")
    confidence: str = Field(description="置信度评估：High, Medium, Low。明确陈述为高，推测为低。")
    context_note: str = Field(description="简短的情境说明：记录该记忆是在什么聊天场景下产生的，以防断章取义。")

class UserMemoryProfile(BaseModel):
    user_id: int = Field(description="用户的唯一QQ ID")
    core_name: str = Field(description="用户的核心称呼或名字")
    facts: List[MemoryFact] = Field(description="关于该用户的所有结构化记忆事实列表")
    last_updated: str = Field(description="ISO 8601格式的最后更新时间戳")


# ====================== 智能记忆引擎 (单一硬盘控制器) ======================
class IntelligentMemoryEngine:
    def __init__(self, client):
        self.client = client
        self.lock = threading.Lock()

        # 统一从唯一文件加载所有数据
        loaded_data = self._load_data()
        self.steam_bindings = loaded_data.get("steam_bindings", {})
        self.bot_recent_says = loaded_data.get("bot_recent_says", [])
        self.profiles = loaded_data.get("profiles", {})

    def _load_data(self) -> Dict:
        if os.path.exists(Config.MEMORY_FILE):
            try:
                with open(Config.MEMORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 记忆文件损坏或解析失败: {e}，将初始化空环境。")
        return {"steam_bindings": {}, "bot_recent_says": [], "profiles": {}}

    def _save_data(self):
        """内部保存，调用方须自持锁"""
        payload = {
            "steam_bindings": self.steam_bindings,
            "bot_recent_says": self.bot_recent_says,
            "profiles": self.profiles
        }
        with open(Config.MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)

    def save_data_safe(self):
        """外部调用的带锁版本"""
        with self.lock:
            self._save_data()

    def get_user_context(self, user_id: int) -> str:
        """极速获取该用户的长线记忆，作为前台上下文"""
        with self.lock:
            user_mem = self.profiles.get(str(user_id))

        if not user_mem or not user_mem.get("facts"):
            return ""

        formatted_context = ""
        for fact in user_mem["facts"]:
            formatted_context += f"- [{fact.get('trait_type', '特征')}] {fact.get('content', '')}\n"
        return formatted_context

    def consolidate_memory(self, user_id: int, user_name: str, recent_dialogue: str):
        """后台核心：调用大模型执行逻辑合并，带有暴力正则提取防崩溃"""
        with self.lock:
            existing_profile = self.profiles.get(str(user_id), {
                "user_id": int(user_id) if str(user_id).isdigit() else user_id,
                "core_name": user_name,
                "facts": [],
                "last_updated": ""
            })

        # [修复] 原代码 textwrap.dedent(f"""...) 缺少闭合的 """)，此处补全
        system_prompt = textwrap.dedent(f"""
        你是一个专门负责"记忆整合与逻辑合并"的高级AI大脑。
        任务是分析最新发生的对话日志，并将其与该用户的【现有旧档案】进行对比、合并和优化。

        【极其严格的铁律】：
        1. 必须返回合法的、完整的 JSON，严禁截断！
        2. 结构必须包含 user_id, core_name, facts 列表。
        3. 即使记忆很长，也必须闭合所有括号 }} 和 ]。
        4. 说话者归因：务必分清谁说了什么。你只能提取用户 {user_name} 本人表达的观点或事实。绝对不可以将"麻薯"的话当成该用户的特征记录！
        5. 拒绝无脑替换：如果新对话包含了相似内容，丰富原有记录；如果产生矛盾，请用时间线演变覆盖。
        6. 领域噪声过滤：忽略一切游戏瞬时战绩。看到 Dota 2、GPM、KDA、胜率等数据【一律忽略】。只关心理学特征、人际关系和独特的说话习惯。
        7. 格式必须绝对统一：必须且只能返回纯 JSON 数据，严禁输出任何 Markdown 标记或"好的"等废话。

        【强制返回的 JSON 格式】：
        {{
            "user_id": {user_id},
            "core_name": "{user_name}",
            "facts": [
                {{
                    "trait_type": "记忆类别(如性格特点/长期偏好)",
                    "content": "详细的记忆内容",
                    "confidence": "High/Medium/Low",
                    "context_note": "产生这段记忆的聊天情境"
                }}
            ]
        }}

        【现有旧档案】：
        {json.dumps(existing_profile, ensure_ascii=False)}

        【最新对话日志】：
        {recent_dialogue}
        """)

        try:
            response = self.client.chat.completions.create(
                model=Config.MODEL_QUICK,
                messages=[{"role": "system", "content": system_prompt}],
                temperature=0.1,
                max_tokens=4096  # [修复] 防止JSON被截断导致解析失败
            )
            raw_text = response.choices[0].message.content.strip()
            print(f"DEBUG: 模型原始返回内容(前200字符): {raw_text[:200]}")
            print(f"DEBUG: 模型原始返回内容(后100字符): {raw_text[-100:]}")

            match = re.search(r'\{[\s\S]*', raw_text)
            if not match:
                raise ValueError(f"无法从返回文本中提取JSON起始位置: {raw_text}")
            raw_json = match.group(0)

            # [修复] 鲁棒的括号补全：逐字符追踪层级，在正确位置闭合
            stack = []
            for ch in raw_json:
                if ch in ('{', '['):
                    stack.append(ch)
                elif ch == '}' and stack and stack[-1] == '{':
                    stack.pop()
                elif ch == ']' and stack and stack[-1] == '[':
                    stack.pop()

            for opener in reversed(stack):
                raw_json += ']' if opener == '[' else '}'

            updated_profile = json.loads(raw_json)
            print(f"DEBUG: 解析后的facts数量: {len(updated_profile.get('facts', []))}")
            print(f"DEBUG: 解析后完整profile: {json.dumps(updated_profile, ensure_ascii=False)}")
            updated_profile["last_updated"] = datetime.now().isoformat()
            updated_profile["last_updated"] = datetime.now().isoformat()

            with self.lock:
                self.profiles[str(user_id)] = updated_profile
                self._save_data()
                print(f"✅ [智能记忆系统] ID: {user_id} 整合成功并保存。")
        except Exception as e:
            print(f"❌ [智能记忆系统] ID: {user_id} 整合失败: {e}")
            print(f"❌ 原始返回完整内容: {raw_text}")  # 加这行


# ====================== 职业选手与API模块 ======================
class ProData:
    _cache = {}

    @staticmethod
    def sync():
        try:
            r = requests.get("https://api.opendota.com/api/proPlayers", timeout=10)
            if r.status_code == 200:
                ProData._cache = {p['name'].lower(): p['account_id'] for p in r.json() if p.get('name')}
                print(f"✅ 已同步 {len(ProData._cache)} 名职业选手")
        except:
            print("⚠️ 职业选手同步失败")


class DotaAPI:
    HEADERS = {
        "Authorization": f"Bearer {Config.STRATZ_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0"
    }
    # [修复] 原代码 URL 被错误包裹为 Markdown 链接格式，已还原为纯字符串
    URL = "https://api.stratz.com/graphql"

    @staticmethod
    def _post(query):
        try:
            resp = requests.post(DotaAPI.URL, json={'query': query}, headers=DotaAPI.HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"❌ Stratz HTTP {resp.status_code}: {resp.text[:300]}")
                return None
            result = resp.json()
            if result.get('errors'):
                print(f"❌ Stratz GraphQL错误: {result['errors']}")
                return None
            return result
        except Exception as e:
            print(f"❌ Stratz请求异常: {e}")
            return None

    @staticmethod
    def get_match_single(steam_id):
        """查最近1把战绩"""
        query = """
        {
          player(steamAccountId: %s) {
            matches(request: {take: 1}) {
              didRadiantWin
              durationSeconds
              players {
                steamAccountId
                isRadiant
                kills
                deaths
                assists
                goldPerMinute
                hero { displayName }
              }
            }
          }
        }
        """ % steam_id
        data = DotaAPI._post(query)
        if not data:
            return None
        try:
            m = data['data']['player']['matches'][0]
            ps = m['players']
            me = next(p for p in ps if str(p['steamAccountId']) == str(steam_id))
            my_team = [p for p in ps if p['isRadiant'] == me['isRadiant']]

            def score(p):
                return (p['kills'] * 2 + p['assists']) / (p['deaths'] + 1) + (p['goldPerMinute'] / 100)

            sorted_team = sorted(my_team, key=score)
            return {
                "hero": me['hero']['displayName'],
                "result": "胜利" if me['isRadiant'] == m['didRadiantWin'] else "落败",
                "kda": f"{me['kills']}/{me['deaths']}/{me['assists']}",
                "gpm": me['goldPerMinute'],
                "duration": f"{m['durationSeconds'] // 60}min",
                "mvp": sorted_team[-1]['hero']['displayName'],
                "svp": sorted_team[0]['hero']['displayName'],
                "team_data": [{"h": p['hero']['displayName'], "kda": f"{p['kills']}/{p['deaths']}/{p['assists']}"} for p in my_team]
            }
        except:
            return None

    @staticmethod
    def get_match_recent(steam_id):
        """查最近10把战绩，返回汇总数据"""
        query = """
        {
          player(steamAccountId: %s) {
            matches(request: {take: 10}) {
              didRadiantWin
              durationSeconds
              players {
                steamAccountId
                isRadiant
                kills
                deaths
                assists
                goldPerMinute
                hero { displayName }
              }
            }
          }
        }
        """ % steam_id
        data = DotaAPI._post(query)
        if not data:
            return None
        try:
            matches = data['data']['player']['matches']
            hero_stats = {}
            total_kills = total_deaths = total_assists = wins = 0

            for m in matches:
                ps = m['players']
                me = next((p for p in ps if str(p['steamAccountId']) == str(steam_id)), None)
                if not me:
                    continue
                hero = me['hero']['displayName']
                won = me['isRadiant'] == m['didRadiantWin']
                if won:
                    wins += 1
                total_kills += me['kills']
                total_deaths += me['deaths']
                total_assists += me['assists']

                if hero not in hero_stats:
                    hero_stats[hero] = {"games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0}
                hero_stats[hero]["games"] += 1
                hero_stats[hero]["wins"] += (1 if won else 0)
                hero_stats[hero]["kills"] += me['kills']
                hero_stats[hero]["deaths"] += me['deaths']
                hero_stats[hero]["assists"] += me['assists']

            total = len(matches)
            sorted_heroes = sorted(hero_stats.items(), key=lambda x: x[1]["games"], reverse=True)[:3]
            hero_list = []
            for hero, s in sorted_heroes:
                avg_k = round(s["kills"] / s["games"], 1)
                avg_d = round(s["deaths"] / s["games"], 1)
                avg_a = round(s["assists"] / s["games"], 1)
                hero_list.append({
                    "hero": hero,
                    "games": s["games"],
                    "wins": s["wins"],
                    "losses": s["games"] - s["wins"],
                    "kda": f"{avg_k}/{avg_d}/{avg_a}"
                })

            return {
                "total": total,
                "wins": wins,
                "losses": total - wins,
                "winrate": round(wins / total * 100, 1) if total else 0,
                "avg_kda": f"{round(total_kills/total,1)}/{round(total_deaths/total,1)}/{round(total_assists/total,1)}" if total else "0/0/0",
                "heroes": hero_list
            }
        except:
            return None

    @staticmethod
    def get_hero_stats(hero_name_hint):
        """查英雄胜率/出装"""
        try:
            # [修复] 原代码 URL 被错误包裹为 Markdown 链接格式，已还原为纯字符串
            r = requests.get("https://api.stratz.com/api/v1/Hero", headers=DotaAPI.HEADERS, timeout=10)
            heroes = r.json()
            hero_id = None
            hero_display = hero_name_hint
            hero_list = heroes.values() if isinstance(heroes, dict) else heroes
            for h in hero_list:
                name = (h.get('displayName') or h.get('name') or '').lower()
                if hero_name_hint.lower() in name:
                    hero_id = h.get('id')
                    hero_display = h.get('displayName', hero_name_hint)
                    break
            if not hero_id:
                return None
        except:
            return None

        win_data_raw = DotaAPI._post("""
        {
          heroStats {
            winWeek(heroIds: [%s], bracketIds: [ANCIENT, DIVINE, IMMORTAL]) {
              heroId
              winCount
              matchCount
            }
          }
        }
        """ % hero_id)

        item_data_raw = DotaAPI._post("""
        {
          heroStats {
            itemBootPurchase(heroId: %s) {
              matchCount
              winCount
              item { displayName }
            }
          }
        }
        """ % hero_id)

        try:
            win_data = win_data_raw['data']['heroStats'].get('winWeek', []) if win_data_raw else []
            item_data = item_data_raw['data']['heroStats'].get('itemBootPurchase', []) if item_data_raw else []

            winrate = pickrate = None
            if win_data:
                w = win_data[0]
                winrate = round(w['winCount'] / w['matchCount'] * 100, 1) if w['matchCount'] else None
                pickrate = w['matchCount']

            top_items = sorted(item_data, key=lambda x: x['matchCount'], reverse=True)[:6]
            item_names = [i['item']['displayName'] for i in top_items if i.get('item')]

            return {
                "hero": hero_display,
                "winrate": winrate,
                "pickrate": pickrate,
                "items": item_names,
            }
        except:
            return None

    @staticmethod
    def get_top_heroes():
        """查万古以上全位置强势英雄TOP10"""
        try:
            # [修复] 原代码 URL 被错误包裹为 Markdown 链接格式，已还原为纯字符串
            r = requests.get("https://api.stratz.com/api/v1/Hero", headers=DotaAPI.HEADERS, timeout=10)
            raw = r.json()
            hero_map = {}
            hero_list = raw.values() if isinstance(raw, dict) else raw
            for h in hero_list:
                hid = h.get("id")
                if not hid:
                    continue
                hero_map[hid] = h.get("displayName", f"Hero{hid}")
        except Exception as e:
            print(f"❌ Hero列表获取失败: {e}")
            return None

        query = """
        {
          heroStats {
            winWeek(bracketIds: [ANCIENT, DIVINE, IMMORTAL]) {
              heroId
              winCount
              matchCount
            }
          }
        }
        """
        data = DotaAPI._post(query)
        if not data:
            return None

        try:
            entries = data['data']['heroStats']['winWeek']
            result = []
            for e in entries:
                matches = e.get('matchCount', 0)
                if matches < 100:
                    continue
                hero_id = e.get('heroId')
                hero_name = hero_map.get(hero_id, f"Hero{hero_id}")
                winrate = round(e['winCount'] / matches * 100, 1)
                result.append({
                    "hero": hero_name,
                    "winrate": winrate,
                    "matchCount": matches
                })

            dedup = {}
            for h in result:
                name = h["hero"]
                if name not in dedup:
                    dedup[name] = h
                else:
                    if h["winrate"] > dedup[name]["winrate"]:
                        dedup[name] = h

            final_list = sorted(dedup.values(), key=lambda x: x['winrate'], reverse=True)[:10]
            return final_list
        except Exception as e:
            print(f"❌ get_top_heroes解析失败: {e}")
            return None


# ====================== 机器人核心 ======================
class MashuBot:
    def __init__(self):
        self.client = OpenAI(api_key=Config.API_KEY, base_url=Config.BASE_URL)

        # 挂载新版独立硬盘控制引擎
        self.memory_engine = IntelligentMemoryEngine(self.client)
        self.consolidation_queue = queue.Queue()

        self.recent_messages = []
        self.processed_events = {}
        self.conversation_state = {}
        self.last_at_time = {}
        self.last_auto_reply_time = {}
        self.last_msg_time = time.time()
        self.last_match_cache = {}
        self.animal_cam = AnimalLiveCamera()
        self.annoyance_level = {}

        # 启动后台线程
        threading.Thread(target=self._auto_speak_loop, daemon=True).start()
        threading.Thread(target=self._memory_worker_loop, daemon=True).start()

    # ---------------- 后台异步记忆管理 ----------------
    def _memory_worker_loop(self):
        print("🧠 [智能记忆就绪] 后台非阻塞整合队列已启动...")
        while True:
            try:
                print("⏳ [记忆系统] 等待任务中...")
                task = self.consolidation_queue.get(block=True)
                print(f"🔥 [记忆系统] 收到任务！正在处理用户: {task['user_name']}")
                if task is None:
                    break
                self.memory_engine.consolidate_memory(task['user_id'], task['user_name'], task['interaction_log'])
                self.consolidation_queue.task_done()
                print(f"✅ [记忆系统] 处理完成！")
            except Exception as e:
                print(f"⚠️ 后台整合工作线程异常: {e}")

    def _get_mood_desc(self, annoyance=0):
        hour = datetime.now().hour
        mood = "心情还不错，比较愿意和群友闲聊。"
        if 9 <= hour <= 18:
            mood = "现在是上班时间，你有点疲惫和敷衍，想摸鱼。"
        elif 23 <= hour or hour <= 4:
            mood = "深夜了，你变得感性且慵懒，说话比较随性。"

        if annoyance > 3:
            mood += " 但是，你现在极其烦躁，因为群友一直在疯狂刷屏艾特你，你的耐心已经耗尽，语气要变得极其暴躁、充满攻击性，甚至直接开骂。"
        elif annoyance > 1:
            mood += " 你现在有点心烦，群友说话太多了，你的语气变得敷衍、不耐烦，带着明显的阴阳怪气。"

        return mood

    # ---------------- 意图识别与数据提取 ----------------
    def _classify_intent(self, text):
            prompt = """判断这句话的意图，只回复以下选项之一，不要有任何其他内容。

        严格规则：
        1. 含有"看看+地名"、"上班"、"下班"、"出差"、"打卡"、"涉谷"，判定为 camera。
        2. 含有"nasa"、"宇宙"、"星空"、"看天"、"守护星"，判定为 nasa。
        3. 含有"说日语"、"用日语"、"日语说"、"日文说"，判定为 speak_japanese。
        4. 除非含有明确查询动词（查、看战绩、上一把、这局、数据、表演），否则不判定为 dota 查询意图。
        5. 单纯"人名+评价"没有查询动词，判定为 chat。
        6. 涉及dota英雄技能/版本/机制/知识的，判定为 dota_knowledge。
        7. "看看"后面跟动物、生物、自然景观、野生场景类词汇（如鸟、猫、狗、老鹰、鱼、大草原、沙漠、森林、野生动物等），判定为 animal_camera。
        8. "看看"后面跟地名/城市/国家，判定为 camera。
        9. "看看"后面跟人名或玩家ID，判定为对应dota查询意图。



        意图选项：
        - camera           （看摄像头/上下班打卡/出差）
        - animal_camera    （看野生动物/自然实况直播）
        - nasa             （宇宙/星空/NASA图片）
        - speak_japanese   （让麻薯说日语）
        - roast            （嘲讽最近比赛表现）
        - dota_query_single（查某个玩家单场战绩）
        - dota_query_recent（查某个玩家最近战绩）
        - hero_stats_single（查某英雄某玩家数据）
        - hero_stats_top   （查英雄全服榜单）
        - dota_knowledge   （dota知识/机制/英雄问题）
        - chat             （日常聊天，兜底）

        消息：""" + text
            try:
                r = self.client.chat.completions.create(
                    model=Config.MODEL_QUICK,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )
                result = r.choices[0].message.content.strip()
                # 防止模型返回不在列表里的值
                valid = {
                    "camera", "animal_camera", "nasa", "speak_japanese", "roast",
                    "dota_query_single", "dota_query_recent",
                    "hero_stats_single", "hero_stats_top",
                    "dota_knowledge", "chat"
                }
                return result if result in valid else "chat"
            except:
                return "chat"

    def _extract_hero_name(self, text):
        prompt = f"从这句话里提取Dota2英雄名，只回复英雄的英文名或中文名，没有就回复none：\n消息：{text}"
        try:
            r = self.client.chat.completions.create(
                model=Config.MODEL_QUICK,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            result = r.choices[0].message.content.strip()
            return None if result.lower() == "none" else result
        except:
            return None

    def _resolve_target(self, user_id, text):
        """从文本或绑定里找到 steam_id。"""
        for name, sid in ProData._cache.items():
            if name in text.lower():
                return sid, name
        target_id = self.memory_engine.steam_bindings.get(str(user_id))
        return target_id, None

    def _recognize_members(self, text):
        recognized = []
        for uid, info in Config.MEMBERS.items():
            keywords = [info['name'], info['call']] + info['roasts']
            if any(kw in text for kw in keywords):
                profile = self.memory_engine.get_user_context(uid)
                if not profile:
                    profile = "麻薯的老朋友"
                recognized.append(f"【关于{info['call']}】这是你的熟人，外号有{', '.join(info['roasts'])}。印象：\n{profile}")
        return "\n".join(recognized) if recognized else "当前对话未提及特定熟人。"

    def _build_prompt(self, user_id, user_text, annoyance=0):
        mood = self._get_mood_desc(annoyance)
        member_knowledge = self._recognize_members(user_text)
        recent_bot = "、".join(self.memory_engine.bot_recent_says[-5:])

        uid_int = int(user_id) if str(user_id).isdigit() else user_id
        speaker_info = Config.MEMBERS.get(uid_int)
        speaker_name = speaker_info["call"] if speaker_info else "某群友"

        # 挂载群聊上下文
        group_context = "暂无"
        if self.recent_messages:
            group_context = "\n".join([f"[{m['name']}] 说: {m['text']}" for m in self.recent_messages[-10:]])

        # 挂载长线记忆
        long_term_memory = self.memory_engine.get_user_context(user_id)
        memory_block = f"【关于{speaker_name}的长期记忆，请活用这些信息自然地回应】\n{long_term_memory}" if long_term_memory else ""
        return f"""【麻薯人设】
23岁在日社畜，高冷心软，资深玩家。禁止括号和动作描写。口语化，不带句号。
【当前情境：核心指令】
现在正在和你说话的人是：{speaker_name}。
无论他说什么，你都要牢记这是 {speaker_name} 发给你的消息。
{memory_block}
【近期群聊上下文】
{group_context}
【麻薯当前状态】
{mood}
【麻薯的社交圈（关键认知）】
{member_knowledge}
【最近回复过】
{recent_bot}

回复准则：
1. 清楚认识当前对话对象是 {speaker_name}，如果他提到了别人（比如社交圈里的外号），那是他在吐槽别人，绝对不要把他误认成别人。
2. 看到熟人外号要能立刻反应过来是谁。
3. 像真人一样接话，不要表现得像个百科全书。
4. 严禁说"不记得、没印象"如果是配置里有的熟人。
5. 请参考【近期群聊上下文】，了解大家正在聊什么，不要像失忆一样接不上话。"""

    # ---------------- 核心业务处理路由 ----------------
    def handle_webhook(self, data):
        if data.get("post_type") != "message":
            return jsonify({"status": "ok"})

        msg_text = "".join([s["data"].get("text", "") for s in data.get("message", []) if s["type"] == "text"]).strip()
        user_id = str(data.get("user_id"))
        group_id = data.get("group_id")
        self_id = str(data.get("self_id"))

        if user_id == self_id:
            return jsonify({"status": "ignore"})

        event_key = f"{user_id}_{hash(msg_text)}_{int(time.time()/5)}"
        if event_key in self.processed_events:
            return jsonify({"status": "duplicate"})
        self.processed_events[event_key] = time.time()

        if len(self.processed_events) > 500:
            now = time.time()
            self.processed_events = {k: v for k, v in self.processed_events.items() if now - v < 60}

        def async_task():
            nickname = data.get("sender", {}).get("nickname", "有人")
            call_name = Config.MEMBERS.get(int(user_id) if user_id.isdigit() else user_id, {}).get("call") or nickname

            self.recent_messages.append({"name": call_name, "text": msg_text})
            if len(self.recent_messages) > 30:
                self.recent_messages.pop(0)

            at_me = any(s["type"] == "at" and str(s["data"].get("qq")) == self_id for s in data.get("message", []))

            # A. 强匹配指令：绑定
            if msg_text.startswith("绑定"):
                sid = "".join(re.findall(r'\d+', msg_text))
                if sid:
                    self.memory_engine.steam_bindings[user_id] = sid
                    self.memory_engine.save_data_safe()
                    self._send(group_id, f"绑定成功(ID:{sid})，以后直接说查战绩就行")
                return

            # B. 核心业务流：被@ 或 提到名字
            if at_me or "麻薯" in msg_text:
                            intent = self._classify_intent(msg_text)

                            # ── 1. 正常的城市/打卡摄像头 ──
                            if intent == "camera":
                                if "出差" in msg_text:
                                    self._handle_live_camera(group_id, scene_type="trip")
                                elif "看看" in msg_text:
                                    import re
                                    city_match = re.search(r"看看\s*(.{2,5}?)(?:$|[\s，。？！])", msg_text)
                                    city = city_match.group(1).strip() if city_match else "东京"
                                    self._handle_live_camera(group_id, scene_type="city_view", city=city)
                                elif "下班" in msg_text:
                                    self._handle_live_camera(group_id, scene_type="off_work")
                                else:
                                    self._handle_live_camera(group_id, scene_type="work")

                            # ── 2. 【新增】野生动物专属监控通道 ──
                            elif intent == "animal_camera":
                                threading.Thread(target=self._animal_worker, args=(group_id, msg_text), daemon=True).start()
                            # ── 3. 其他原有业务分支 ──
                            elif intent == "nasa":
                                self._handle_nasa_space(group_id, msg_text, is_auto=False)
                            elif intent == "speak_japanese":
                                self._handle_speak_japanese(group_id, msg_text)
                            elif intent == "roast" and group_id in self.last_match_cache:
                                self._handle_roast(group_id, msg_text)
                            elif intent == "dota_query_single":
                                self._handle_dota_single(user_id, group_id, msg_text)
                            elif intent == "dota_query_recent":
                                self._handle_dota_recent(user_id, group_id, msg_text)
                            elif intent == "hero_stats_single":
                                self._handle_hero_stats_single(group_id, msg_text)
                            elif intent == "hero_stats_top":
                                self._handle_hero_stats_top(group_id)
                            elif intent == "dota_knowledge":
                                self._do_dota_reply(group_id, msg_text)
                            else:
                                self._do_at_reply(user_id, group_id, call_name, msg_text)
                            return

            # C. 概率插嘴逻辑
            if random.random() < 0.08:
                self._do_random_interject(group_id, call_name, msg_text)

        threading.Thread(target=async_task).start()
        return jsonify({"status": "ok"})

# ---------------- 业务处理器件 (战绩查询功能完美复活版) ----------------
    def _handle_dota_single(self, user_id, group_id, text):
        """处理查上一把战绩的请求"""
        # 1. 解析要查询的目标（优先查提到的职业选手，其次查发言人绑定的账号）
        steam_id, target_name = self._resolve_target(user_id, text)
        if not steam_id:
            self._send_and_record(group_id, "你谁啊？先说【绑定+你的Steam数字ID】或者直接让我查职业选手的名字")
            return

        name_to_show = target_name if target_name else "你"
        self._send(group_id, f"正在给大佬去扒 {name_to_show} 的上一局内裤，等我一下...")

        # 2. 调用已有的 Stratz API 抓取数据
        match_data = DotaAPI.get_match_single(steam_id)
        if not match_data:
            self._send_and_record(group_id, f"居然没查到 {name_to_show} 的战绩，Stratz服务器多半又挺尸了")
            return

        # 3. 缓存最近一把的战绩，方便触发“roast（锐评/嘲讽）”意图
        self.last_match_cache[group_id] = match_data

        # 4. 让大模型根据战绩数据，用麻薯的语气进行有血有肉的播报
        messages = [
            {"role": "system", "content": self._build_prompt(user_id, text) + "\n你现在需要播报这段Dota2单场战绩，用玩家口吻犀利点评，禁止复述纯数字，多吐槽MVP或SVP。"},
            {"role": "user", "content": f"战绩数据：{json.dumps(match_data, ensure_ascii=False)}"}
        ]

        reply = self._call_llm(messages, model=Config.MODEL_QUICK)
        if reply:
            # 同样享受我们刚刚搭建好的 100% 语音/文本分流表现层！
            if random.random() < Config.VOICE_PROBABILITY:
                tts_script = clean_bot_text(reply)
                threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()
            else:
                self._send_and_record(group_id, reply)

    def _handle_dota_recent(self, user_id, group_id, text):
        """处理查最近10把总战绩的请求"""
        steam_id, target_name = self._resolve_target(user_id, text)
        if not steam_id:
            self._send_and_record(group_id, "查战绩好歹给我个Steam ID或者名字啊？")
            return

        name_to_show = target_name if target_name else "你"
        self._send(group_id, f"正在算 {name_to_show} 最近10把的胜率，别急...")

        # 调用已有的最近10场聚合 API
        recent_data = DotaAPI.get_match_recent(steam_id)
        if not recent_data:
            self._send_and_record(group_id, "最近10把的数据空空如也，API又抽风了")
            return

        messages = [
            {"role": "system", "content": self._build_prompt(user_id, text) + "\n你现在需要点评对方最近10场比赛的综合表现（胜率、常用英雄）。如果胜率很惨，直接开喷；表现好就傲娇地夸一句。"},
            {"role": "user", "content": f"近10场聚合数据：{json.dumps(recent_data, ensure_ascii=False)}"}
        ]

        reply = self._call_llm(messages, model=Config.MODEL_QUICK)
        if reply:
            if random.random() < Config.VOICE_PROBABILITY:
                tts_script = clean_bot_text(reply)
                threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()
            else:
                self._send_and_record(group_id, reply)

    def _handle_hero_stats_single(self, group_id, text):
        """处理查某个英雄胜率出装的请求"""
        hero_hint = self._extract_hero_name(text)
        if not hero_hint:
            self._send_and_record(group_id, "你想查哪个英雄？名字说明白点")
            return

        stats = DotaAPI.get_hero_stats(hero_hint)
        if not stats:
            self._send_and_record(group_id, f"没找到【{hero_hint}】这个英雄的数据，你是不是拼错了")
            return

        messages = [
            {"role": "system", "content": "你是重度Dota2玩家麻薯，用不耐烦但专业的语气，点评这个英雄当前版本的胜率和出装推荐。"},
            {"role": "user", "content": f"英雄高分段数据：{json.dumps(stats, ensure_ascii=False)}"}
        ]
        reply = self._call_llm(messages, model=Config.MODEL_QUICK)
        if reply:
            if random.random() < Config.VOICE_PROBABILITY:
                tts_script = clean_bot_text(reply)
                threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()
            else:
                self._send_and_record(group_id, reply)

    def _handle_hero_stats_top(self, group_id):
        """处理查当前版本强势英雄TOP10的请求"""
        top_list = DotaAPI.get_top_heroes()
        if not top_list:
            self._send_and_record(group_id, "高分段天梯榜单离家出走了，等会再试吧")
            return

        # 英雄榜单属于结构化干货，强制走文本发送，不发语音（不然念10个英雄群友会听睡着）
        report = "【万古/神圣/冠位】当前版本胜率狂魔：\n"
        for i, h in enumerate(top_list, 1):
            report += f"{i}. {h['hero']} (胜率: {h['winrate']}%)\n"
        self._send_and_record(group_id, report.strip())

    def _handle_roast(self, group_id, text):
        """针对缓存的上一把战绩进行高强度专门嘲讽"""
        match_data = self.last_match_cache.get(group_id)
        if not match_data:
            self._send_and_record(group_id, "刚才没人查过战绩，我无从喷起啊？先查个战绩来看看")
            return

        messages = [
            {"role": "system", "content": "你是麻薯。群友让你开喷。请根据传入的单场战绩，火力全开，用最刻薄的玩家黑话无情嘲讽本局表现最差的败家子（SVP或数据最差的人）。"},
            {"role": "user", "content": f"上一局战绩详情：{json.dumps(match_data, ensure_ascii=False)}"}
        ]
        reply = self._call_llm(messages, model=Config.MODEL_SMART) # 动用Pro模型进行精妙开喷
        if reply:
            if random.random() < Config.VOICE_PROBABILITY:
                tts_script = clean_bot_text(reply)
                threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()
            else:
                self._send_and_record(group_id, reply)

    # ---------------- 底层接口封装 ----------------
    def _call_llm(self, messages, model=Config.MODEL_QUICK):
        try:
            # 注入 CoT 提示词
            cot_prompt = {"role": "system", "content": "IMPORTANT: You MUST first think about your response internally. Wrap your internal thoughts entirely inside <think>...</think> XML tags. After the closing </think> tag, provide your actual spoken reply to the user. Do not include any thoughts outside the tags."}
            messages = [cot_prompt] + messages

            resp = self.client.chat.completions.create(model=model, messages=messages, temperature=0.8)
            raw_content = resp.choices[0].message.content.strip()

            # 解析并剔除 <think> 块
            content = raw_content
            think_match = re.search(r'<think>([\s\S]*?)</think>', raw_content)
            if think_match:
                print(f"💭 [内部思考]: {think_match.group(1).strip()}")
                content = raw_content.replace(think_match.group(0), "").strip()
            else:
                print(f"⚠️ [未检测到思考块]: 模型直接输出了内容。")

            # 物理层面彻底屏蔽星号和括号动作描写
            content = re.sub(r'[（\(].*?[）\)]', '', content)
            content = re.sub(r'\*.*?\*', '', content)
            for word in ["叹气", "微笑", "叼着吸管", "揉揉头"]:
                content = content.replace(word, "")
            return content.rstrip("。").rstrip("！")
        except Exception as e:
            print(f"❌ LLM Error (Model={model}): {e}")
            return "脑子抽了，等会再说"

    def _send(self, group_id, msg):
        requests.post(
            f"{Config.NAPCAT_URL}/send_group_msg",
            headers={"Authorization": f"Bearer {Config.NAPCAT_TOKEN}"},
            json={"group_id": group_id, "message": msg}
        )


    def _send_and_record(self, group_id, msg):
        self._send(group_id, msg)
        self.memory_engine.bot_recent_says.append(msg[:30])
        if len(self.memory_engine.bot_recent_says) > 10:
            self.memory_engine.bot_recent_says.pop(0)
        self.memory_engine.save_data_safe()

# ---------------- 语音引擎与发送 ----------------
    async def _edge_tts_generator(self, text, voice, output_path, rate, pitch):
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)

    def _voice_worker(self, group_id, text, voice="zh-CN-XiaoxiaoNeural", rate="+10%", pitch="+5Hz"):
        """后台独立线程运行的语音合成与投递"""
        try:
            if not os.path.exists(Config.AUDIO_CACHE_DIR):
                os.makedirs(Config.AUDIO_CACHE_DIR)

            audio_filename = f"tts_{uuid.uuid4().hex}.mp3"
            audio_path = os.path.join(Config.AUDIO_CACHE_DIR, audio_filename)

            # 在后台线程启动独立事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._edge_tts_generator(text, voice, audio_path, rate, pitch))
            finally:
                loop.close()

            # 投递给 NapCat
            if os.path.exists(audio_path):
                payload = {
                    "group_id": group_id,
                    "message": [{"type": "record", "data": {"file": f"file://{audio_path}"}}]
                }
                requests.post(
                    f"{Config.NAPCAT_URL}/send_group_msg",
                    headers={"Authorization": f"Bearer {Config.NAPCAT_TOKEN}"},
                    json=payload,
                    timeout=10
                )
        except Exception as e:
            print(f"❌ [VoiceError] 语音合成投递异常: {e}")


    # ---------------- 记忆与任务循环 ----------------
    def _update_profile(self, call_name, q, a):
        """
        无缝重构你的老函数！
        不删减任何逻辑调用，将原先的同步大模型修改为直接投递到异步队列！
        """
        user_id = None
        for uid, info in Config.MEMBERS.items():
            if info['call'] == call_name or info['name'] == call_name:
                user_id = str(uid)
                break

        if not user_id:
            return

        interaction_log = f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n说话人 [{call_name}]: {q}\n回应人 [麻薯]: {a}"

        self.consolidation_queue.put({
            "user_id": user_id,
            "user_name": call_name,
            "interaction_log": interaction_log
        })

    def _auto_speak_loop(self):
            print("⏰ 麻薯主动冲浪带节奏时钟（宇宙+社畜打卡合体版）已启动...")
            import random
            from datetime import datetime

            # 状态锁：确保每天每个场景只会触发一次，绝对不刷屏
            last_checked_day = None
            has_sent_morning = False
            has_sent_evening = False
            has_sent_trip = False
            has_sent_nasa_today = False

            # ⚠️ 记得把 721815671 改成你们群的真实 QQ 群号！
            TARGET_GROUP = 721815671

            while True:
                # 每隔 15 分钟（900秒）在后台探一次头
                time.sleep(900)

                now = datetime.now()
                current_hour = now.hour
                current_day = now.date()
                current_weekday = now.weekday() # 0-4 是工作日，5-6 是周末

                # 日期变了，自动重置今天所有主动技能的状态
                if current_day != last_checked_day:
                    last_checked_day = current_day
                    has_sent_morning = False
                    has_sent_evening = False
                    has_sent_nasa_today = False
                    # 每天下午有 5% 的低概率被阎老板临时安排跨国出差
                    has_sent_trip = random.random() > 0.05

                # ================= [ 场景 1：工作日早上上班打卡 ] =================
                if current_weekday < 5 and current_hour == 8 and not has_sent_morning:
                    if random.random() < 0.40:  # 40% 概率在这个 15 分钟切片里触发
                        self._handle_live_camera(TARGET_GROUP, scene_type="work")
                        has_sent_morning = True
                        continue  # 触发了打卡，这 15 分钟就不重复干别的事了

                # ================= [ 场景 2：工作日傍晚下班打卡 ] =================
                if current_weekday < 5 and (18 <= current_hour <= 19) and not has_sent_evening:
                    if random.random() < 0.30:
                        self._handle_live_camera(TARGET_GROUP, scene_type="off_work")
                        has_sent_evening = True
                        continue

                # ================= [ 场景 3：下午突发出差盲盒 ] =================
                if (14 <= current_hour <= 16) and not has_sent_trip:
                    self._handle_live_camera(TARGET_GROUP, scene_type="trip")
                    has_sent_trip = True
                    continue

                # ================= [ 场景 4：白天随机冲浪发宇宙图 ] =================
                # 设定在上午 10 点到傍晚 17 点之间，如果今天还没发过宇宙图
                if (10 <= current_hour <= 17) and not has_sent_nasa_today:
                    # 每次探头有 8% 的概率主动去 NASA 官网捞图和群友分享
                    if random.random() < 0.08:
                        self._handle_nasa_space(TARGET_GROUP, text="", is_auto=True)
                        has_sent_nasa_today = True
                        continue

                # ================= [ 场景 5：深夜绝对保底机制 ] =================
                # 运气差到极点，到了晚上 22 点还没摇到号发过宇宙图，强制出来刷存在感
                if current_hour >= 22 and not has_sent_nasa_today:
                    print("🚨 警告：今天快过完了还没发宇宙图，触发全自动保底发图！")
                    self._handle_nasa_space(TARGET_GROUP, text="", is_auto=True)
                    has_sent_nasa_today = True

    # ---------------- 你原有的独立/预留功能区 ----------------
    def _do_random_interject(self, group_id, call_name, text):
        if time.time() - self.last_auto_reply_time.get(group_id, 0) < 300:
            return

        ctx = " / ".join([f"{m['name']}:{m['text']}" for m in self.recent_messages[-5:]])
        prompt = f"群聊背景：{ctx}\n{call_name}说：{text}\n你作为麻薯顺着聊一句，别硬杠。"
        reply = self._call_llm([
            {"role": "system", "content": self._get_mood_desc() + "禁止加括号和动作描写。"},
            {"role": "user", "content": prompt}
        ])
        if reply:
            self._send_and_record(group_id, reply)
            self.last_auto_reply_time[group_id] = time.time()

    def _do_at_reply(self, user_id, group_id, call_name, text):
        now = time.time()

        last_time = self.last_at_time.get(user_id, 0)
        time_diff = now - last_time

        current_annoyance = self.annoyance_level.get(user_id, 0)
        decay = int(time_diff / 30)
        current_annoyance = max(0, current_annoyance - decay)

        if time_diff < 8:
            current_annoyance += 1

        self.annoyance_level[user_id] = current_annoyance
        self.last_at_time[user_id] = now

        messages = [
            {"role": "system", "content": self._build_prompt(user_id, text, annoyance=current_annoyance)},
            # 明确打上说话人标签，杜绝误归因
            {"role": "user", "content": f"说话人 [{call_name}]: {text}"}
        ]
        print(f"DEBUG FULL PROMPT:\n{messages[0]['content']}")  # 加这行

# 执行研究文章要求的 10% Pro 模型调用
        reply = self._call_llm(messages, model=Config.MODEL_SMART if random.random() < 0.10 else Config.MODEL_QUICK)
        if reply:
            # === 新增：语音与文本分流逻辑 ===
            # (注：如果你现在想把所有闲聊都变语音测试，记得把 len(reply) < 50 and 这个字数限制删掉)
            if len(reply) < 50 and random.random() < Config.VOICE_PROBABILITY:

                # [核心修改 1]：命中语音后，临时生成专用的发音剧本
                tts_script = clean_bot_text(reply)

                # [核心修改 2]：打印出来对比一下，方便你调试
                print(f"🔊 原生回复: {reply} | 语音剧本: {tts_script}")

                # 手动记录最近发言到内存（保持记忆连贯性），但不发文本
                # 注意：这里存入记忆的依然是原本的 reply，没有被污染
                self.memory_engine.bot_recent_says.append(reply[:30])
                if len(self.memory_engine.bot_recent_says) > 10:
                    self.memory_engine.bot_recent_says.pop(0)
                self.memory_engine.save_data_safe()

                # [核心修改 3]：在后台线程发语音时，传进去的是 tts_script！
                threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()
            else:
                self._send_and_record(group_id, reply)

            # 无缝衔接：开启线程调用你自己的 _update_profile
            threading.Thread(target=self._update_profile, args=(call_name, text, reply)).start()

    def _do_dota_reply(self, group_id, text):
        if not dota_retriever:
            self._send_and_record(group_id, "我还没下好Dota，你等我更新完")
            return

        docs = dota_retriever.invoke(text)
        context = "\n".join([d.page_content for d in docs])
        messages = [
            {"role": "system", "content": "你是Dota2专业导师，直接给干货，禁止废话，禁止星号加粗。"},
            {"role": "user", "content": f"背景知识：{context}\n问题：{text}"}
        ]
        reply = self._call_llm(messages, model=Config.MODEL_SMART)
        if reply:
            for part in re.split(r'\n+', reply):
                if part.strip():
                    self._send_and_record(group_id, part.strip())
                    time.sleep(0.5)

    def _handle_speak_japanese(self, group_id, text):
        """【群友流·日语营业】根据语境生成日语语音"""
        self._send(group_id, "等下，我找找语感...")

        messages = [
            {"role": "system", "content": "你叫麻薯，一个23岁在日打工的重度网瘾少女。现在有人让你说句日语，你要根据群友的内容，用口语化、随性、傲娇的语气说一句简短的日语。只返回日语原文，不要罗马音，不要翻译，不要标点符号，不要括号动作描写。"},
            {"role": "user", "content": f"群友的话：{text}"}
        ]

        reply = self._call_llm(messages, model=Config.MODEL_QUICK)
        if reply:
            threading.Thread(target=self._voice_worker, args=(group_id, reply, "ja-JP-NanamiNeural", "+0%", "+0Hz"), daemon=True).start()

    def _handle_nasa_space(self, group_id, text, is_auto=False):
            """【群友流·宇宙大新闻】NASA天文图真人化分享"""
            import requests
            import random
            from datetime import datetime

            # 1. 判定触发场景，生成开头
            if is_auto:
                print("🎲 命中定时/随机主动分享，麻薯准备在群里发张宇宙图...")
            else:
                self._send(group_id, "等我会，我用梯子去翻一下NASA的官网...")

            # 2. 日期选择逻辑
            date_param = ""
            # 允许群友查历史（比如：@麻薯 看看 2024-10-01 的宇宙）
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', text) if text else None

            if date_match:
                date_param = f"&date={date_match.group(0)}"
            else:
                # 如果是主动分享，或者今天没指定日期，有 50% 概率随机历史某天，50% 拿今天最新的
                if is_auto or random.random() < 0.5:
                    year = random.randint(2018, 2025)
                    month = random.randint(1, 12)
                    day = random.randint(1, 28)
                    date_param = f"&date={year}-{month:02d}-{day:02d}"

            # 3. 请求 NASA
            api_url = f"{Config.NASA_URL}?api_key={Config.NASA_API_KEY}{date_param}"
            try:
                res = requests.get(api_url, timeout=10)
                if res.status_code != 200:
                    if not is_auto: self._send_and_record(group_id, "草，NASA这破网站又挂了，根本刷不出来")
                    return

                data = res.json()
                img_url = data.get("hdurl") or data.get("url")
                explanation_en = data.get("explanation", "")
                title_en = data.get("title", "未知星体")

                if not img_url or data.get("media_type") != "image":
                    return  # 没图或者是视频就静默退出

                # 4. 【核心重构】群友化洗脑 Prompt
                # 区分被动回答和主动安利的开场白
                context_style = "你在群里看到有人问你今天NASA发了啥，你顺手甩给他。" if not is_auto else "你在刷推特刚好刷到一张震撼的太空图，你忍不住主动扔到QQ群里跟大伙分享。"

                messages = [
                    {"role": "system", "content": f"""
    你叫麻薯，一个23岁在日打工的重度网瘾少女。现在你正在QQ群里跟老朋友们水群。
    【任务】：
    你手头刚拿到一张NASA拍的宇宙深空高清图，请把下面这段英文的星空简介，用你平时和群友聊天时的【高冷、口语化、偶尔嘴硬】的语调说出来。

    【极其严格的群友规矩】：
    1. 绝对不要像个百科全书或者AI助手在背书！严禁出现“根据NASA报道”、“这张图片展示了”这种客服废话。
    2. 要用最自然的聊天开头！比如：“卧槽你们看这个图……”、“今天NASA整了个绝的……”、“刷推看到个星云长得好像……”
    3. 允许你对这个星体进行瞎扯或主观吐槽（比如：这长得像个烂西瓜、这光污染绝了、这恒星看着像要炸了）。
    4. 严禁出现任何结尾句和标点符号，字数控制在50字内，越口语、越像真人在网上面基越好。
    """},
                    {"role": "user", "content": f"当前场景: {context_style}\n太空图英文名: {title_en}\n英文背景描述: {explanation_en}"}
                ]

                reply = self._call_llm(messages, model=Config.MODEL_QUICK)

                # 5. 发送高清图与语音
                if reply:
                    self._send(group_id, f"[CQ:image,file={img_url}]")
                    tts_script = clean_bot_text(reply)
                    threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()

            except Exception as e:
                print(f"❌ NASA 引擎异常: {e}")

    def _resolve_city_coords(self, city: str):
        """让大模型返回城市经纬度，无需维护坐标字典"""
        try:
            resp = self.client.chat.completions.create(
                model=Config.MODEL_QUICK,
                messages=[{
                    "role": "user",
                    "content": f'返回"{city}"市中心的经纬度，只返回JSON，格式：{{"lat": 35.67, "lon": 139.65}}，不要任何其他内容。'
                }],
                temperature=0
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r'```[^\n]*\n?', '', raw).strip()
            data = json.loads(raw)
            return float(data["lat"]), float(data["lon"])
        except Exception as e:
            print(f"❌ 坐标解析失败 [{city}]: {e}")
            return None, None

    def _resolve_trip_city(self):
        """让大模型随机想一个适合出差的海外城市"""
        try:
            resp = self.client.chat.completions.create(
                model=Config.MODEL_QUICK,
                messages=[{
                    "role": "user",
                    "content": '随机想一个适合出差的海外城市（不要日本城市），只返回城市中文名，不要任何其他内容。'
                }],
                temperature=1.2
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ 出差城市生成失败: {e}")
            return "纽约"

    def _animal_worker(self, group_id, msg_text):
        # 从消息里匹配动物名
        target_animal = None
        for animal in self.animal_cam.animal_map.keys():
            if animal in msg_text:
                target_animal = animal
                break

        # 没匹配到就让大模型从消息里提取，再模糊匹配最接近的
        if not target_animal:
            try:
                resp = self.client.chat.completions.create(
                    model=Config.MODEL_QUICK,
                    messages=[{"role": "user", "content":
                        f"从这句话里提取动物或自然场景关键词，只回复一个词：{msg_text}"
                    }],
                    temperature=0
                )
                keyword = resp.choices[0].message.content.strip()
                # 用关键词再匹配一次
                for animal in self.animal_cam.animal_map.keys():
                    if animal in keyword or keyword in animal:
                        target_animal = animal
                        break
            except:
                pass

        if not target_animal:
            menu = "、".join(self.animal_cam.animal_map.keys())
            self._send(group_id, f"这个我监控里没有，现在只有：{menu}，你选一个")
            return

        try:
            self._send(group_id, f"知道了，正在调{target_animal}的监控录像，别催...")
            gif_path = self.animal_cam.get_animal_gif(target_animal)

            if gif_path:
                safe_path = gif_path.replace("\\", "/")
                self._send(group_id, f"[CQ:image,file=file:///{safe_path}]")

                messages = [
                    {"role": "system", "content":
                        f"你叫麻薯，23岁在日打工社畜。阎老板让你去调【{target_animal}】的监控，你拍到了发到群里。"
                        "用高冷随意的语气随口评论一句，像个活人在群里发图，不要像解说员，50%概率什么都不说只回复一个句号。"
                        "严禁括号动作描写。字数20字以内。"
                    },
                    {"role": "user", "content": f"【{target_animal}】监控画面已就绪。"}
                ]
                reply = self._call_llm(messages, model=Config.MODEL_QUICK)
                if reply and reply.strip() != "。":
                    if random.random() < Config.VOICE_PROBABILITY:
                        tts_script = clean_bot_text(reply)
                        threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()
                    else:
                        self._send_and_record(group_id, reply)
            else:
                self._send(group_id, f"{target_animal}那边信号断了，监控挂了")
        except Exception as e:
            print(f"❌ animal_worker 异常: {e}")
            self._send(group_id, "监控系统崩了，阎老板又没交服务器的钱")


    def _handle_live_camera(self, group_id, scene_type="work", city: str = None):
            """
            通过 Windy API + CDN 直连获取实况摄像头图片。
            scene_type: "work" | "off_work" | "trip" | "city_view"
            city: scene_type="city_view" 时由调用方传入城市名
            """
            import random
            import os
            import time
            import threading
            import requests

            WINDY_API_KEY = "WmOKz8XYr3aWe2cM9CrbD6oFkfn6tYVy"

            # ── 1. 根据场景确定城市名和 prompt ────────────────────────────
            if scene_type == "work":
                target_city = "东京"
                context_prompt = (
                    "你现在正在早高峰通勤路上，挤东京的地铁快挤断气了。"
                    "你顺手拍了一张现在的街头监控画面发到群里，"
                    "疯狂吐槽早八和恶心的通勤，语气要极度暴躁、红温。"
                )

            elif scene_type == "off_work":
                target_city = "东京"
                context_prompt = (
                    "你现在终于熬到下班了！你拍了一张现在东京夜景/街头的画面发到群里。"
                    "虽然下班了但你感觉身体被掏空，只想赶紧回家躺平，"
                    "语气是那种敷衍、虚脱、高冷的感觉。"
                )

            elif scene_type == "trip":
                target_city = self._resolve_trip_city()
                context_prompt = (
                    f"老板竟然把你派到【{target_city}】去出差了！你刚下飞机，"
                    "顺手拍了一张当地的实时街景发到群里。"
                    "你极其不爽为什么出差的总是你，在群里一边发图一边疯狂阴阳怪气老板，"
                    "顺便跟群友显摆。"
                )

            elif scene_type == "city_view" and city:
                target_city = city
                context_prompt = (
                    f"群友让你看看{target_city}。"
                    f"你有50%概率完全不说话只发图，有50%概率随口编一个你和{target_city}的关系："
                    f"可能是出差路过、可能是之前旅游去过、可能是朋友在那边。"
                    f"如果要说话，就一句话带过，口语化，高冷随意，不要介绍景点，不要吐槽上班。"
                    f"如果选择不说话，只回复一个句号'。'作为占位，不要任何其他内容。"
                )

            else:
                print(f"❌ 未知 scene_type: {scene_type}")
                return

            # ── 2. 判断是否为国家名（拦截器：解决搜“日本”变成搜东京周边的问题） ─────
            COUNTRY_MAP = {
                "日本": "JP", "美国": "US", "英国": "GB", "法国": "FR",
                "冰岛": "IS", "意大利": "IT", "瑞士": "CH", "韩国": "KR",
                "俄罗斯": "RU", "越南": "VN", "中国": "CN", "泰国": "TH"
            }
            country_code = COUNTRY_MAP.get(target_city)

            # ── 3. 解析城市坐标 (若是具体城市则查坐标，国家名则免查) ────────────────
            lat, lon = None, None
            if not country_code:
                lat, lon = self._resolve_city_coords(target_city)
                if lat is None:
                    self._send(group_id, f"我去查了一下，{target_city}这地方我完全不知道在哪，你确定这是个地方？")
                    return

            # ── 4. 拉取摄像头，找不到时自动扩大半径重试 ──────────────────────────────
            def fetch_active_ids(lat, lon, radius, c_code=None):
                api_url = "https://api.windy.com/webcams/api/v3/webcams"
                headers = {"x-windy-api-key": WINDY_API_KEY}
                all_active_ids = []

                # 【新增兼容】如果是国家级扫描，抛弃经纬度，直接用 countries 参数一把梭
                if c_code:
                    params = {"countries": c_code, "limit": 50}
                    try:
                        resp = requests.get(api_url, headers=headers, params=params, timeout=10)
                        if resp.status_code == 401:
                            print("❌ Windy API Key 无效")
                            return None
                        if resp.status_code == 200:
                            data = resp.json()
                            cam_list = data.get("webcams", data) if isinstance(data, dict) else data
                            for cam in cam_list:
                                if isinstance(cam, dict) and cam.get("status") == "active":
                                    all_active_ids.append(str(cam["webcamId"]))
                    except Exception as e:
                        print(f"❌ Windy API 国家扫描异常: {e}")
                    return list(dict.fromkeys(all_active_ids))

                # 【原汁原味】如果是具体城市，走你原有的 nearby 画圈+循环偏移量逻辑
                for offset in [0, 10, 20]:
                    params = {"nearby": f"{lat},{lon},{radius}", "limit": 10, "offset": offset}
                    try:
                        resp = requests.get(api_url, headers=headers, params=params, timeout=10)
                    except requests.exceptions.RequestException as e:
                        print(f"❌ Windy API 网络异常: {e}")
                        break
                    if resp.status_code == 401:
                        print("❌ Windy API Key 无效")
                        return None
                    if resp.status_code != 200:
                        print(f"❌ Windy API 失败 HTTP {resp.status_code}")
                        break
                    data = resp.json()
                    cam_list = data.get("webcams", data) if isinstance(data, dict) else data
                    for cam in cam_list:
                        if isinstance(cam, dict) and cam.get("status") == "active":
                            all_active_ids.append(str(cam["webcamId"]))
                    if len(cam_list) < 10:
                        break
                return list(dict.fromkeys(all_active_ids))

            # 执行拉取
            active_ids = fetch_active_ids(lat, lon, 25, country_code)
            if active_ids is None:
                return

            # 只有在非国家级扫描且 25km 没找到时，才扩大到 80km
            if not active_ids and not country_code:
                print(f"⚠️ [{target_city}] 25km 内无摄像头，扩大到 80km 重试...")
                active_ids = fetch_active_ids(lat, lon, 500, country_code)

            print(f"📡 [{target_city}] 活跃机位池：{len(active_ids) if active_ids else 0} 个")

            # ── 5. 随机抽取并下载图片 ─────────────────────────────────────
            local_img_path = None
            if active_ids:
                chosen_id = random.choice(active_ids)
                last_two = chosen_id[-2:]
                img_url = f"https://images-webcams.windy.com/{last_two}/{chosen_id}/current/full/{chosen_id}.jpg"
                print(f"🎯 抽中机位 {chosen_id}，下载中...")
                try:
                    img_resp = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    if img_resp.status_code == 200:
                        cache_dir = getattr(Config, "AUDIO_CACHE_DIR", os.path.dirname(os.path.abspath(__file__)))
                        os.makedirs(cache_dir, exist_ok=True)
                        local_img_path = os.path.join(cache_dir, f"webcam_{chosen_id}_{int(time.time())}.jpg")
                        with open(local_img_path, "wb") as f:
                            f.write(img_resp.content)
                        print(f"✅ 图片已保存: {local_img_path}")
                    else:
                        print(f"❌ 图片下载失败 HTTP {img_resp.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"❌ 图片下载异常: {e}")
            else:
                print(f"⚠️ [{target_city}] 范围/国家内仍无摄像头，仅发文字")

            # ── 6. LLM 生成文案并发送 ─────────────────────────────────────
            messages = [
                {"role": "system", "content": f"""
    你叫麻薯，一个23岁在日打工的重度网瘾少女、高冷傲娇社畜。
    【当前场景】：{context_prompt}

    【规矩】：
    1. 绝对不要像机器人！像个活人在群里发上班/下班/出差打卡照。
    2. 严禁出现"根据监控显示"、"画面中"这种废话。直接开头就喷。
    3. 严禁在开头或中间加任何括号动作描写或颜文字。
    4. 字数限制在50字内，越口语化越好，最后用"CNM"、"无语"或"切——"收尾。
    """},
                {"role": "user", "content": f"当前物理世界位置: {target_city}，实时打卡拍照完毕。"}
            ]

            try:
                reply = self._call_llm(messages, model=Config.MODEL_QUICK)
                if reply:
                    if local_img_path and os.path.exists(local_img_path):
                        safe_path = local_img_path.replace("\\", "/")
                        self._send(group_id, f"[CQ:image,file=file:///{safe_path}]")
                    else:
                        self._send(group_id, f"（{target_city}这边没找到摄像头，光秃秃的）")
                    if random.random() < Config.VOICE_PROBABILITY:
                        tts_script = clean_bot_text(reply)
                        threading.Thread(target=self._voice_worker, args=(group_id, tts_script), daemon=True).start()
                    else:
                        self._send_and_record(group_id, reply)
            except Exception as e:
                print(f"❌ 大模型异常: {e}")
# ====================== 启动 ======================
bot = MashuBot()
ProData.sync()


@app.route("/", methods=["POST"])
def main():
    bot.handle_webhook(request.json)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(port=5000)
