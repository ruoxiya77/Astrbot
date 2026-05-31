import datetime
import json
import os
import random
import re
import asyncio
from collections import defaultdict, deque
from typing import Dict, Optional

from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image, Face
from astrbot.api import logger

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

try:
    _FONT_PATH = next(p for p in ["C:/Windows/Fonts/msyh.ttc","C:/Windows/Fonts/simhei.ttf","C:/Windows/Fonts/simsun.ttc"] if os.path.exists(p))
except StopIteration:
    _FONT_PATH = None

PLUGIN_VERSION = "1.0.0"
URL_REGEX = re.compile(r"https?://[^\s]+")


@register("astrbot_plugin_anti_spam_simple", "YourName", "刷屏检测", PLUGIN_VERSION)
class AntiSpamPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self._timestamps: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=30)))
        self._whitelist: set = set()
        self._admins: set = set()
        self._violations: Dict[str, Dict[str, dict]] = defaultdict(dict)
        self._data_dir = None
        self._load_config()
        self._load_whitelist()

    def _load_config(self):
        self.enabled_groups = self.config.get("enabled_groups", [])
        self.spam_trigger = self.config.get("spam_trigger", 5)
        self.spam_window = self.config.get("spam_window", 1)
        self.spam_mute = self.config.get("spam_mute_seconds", 60)
        self.url_mute = self.config.get("url_mute_seconds", 120)
        self.private_notify = self.config.get("private_notify", True)
        self.funny_mute = self.config.get("funny_mute", True)
        self.funny_mute_words = self.config.get("funny_mute_words", [
            "{name} 被神秘力量静音，先去喝杯茶吧~",
            "{name} 你发得太快了，先歇一会儿~",
            "{name} 已被禁言套餐安排上了，请耐心等待",
        ])
        self._admins = set(str(a).strip() for a in self.config.get("admins", []))

    def _get_data_file(self):
        if self._data_dir is None:
            self._data_dir = os.path.join(os.path.dirname(__file__), "_data")
            os.makedirs(self._data_dir, exist_ok=True)
        return os.path.join(self._data_dir, "violations.json")

    def _load_whitelist(self):
        self._whitelist = set()
        for uid in self.config.get("whitelist", []):
            self._whitelist.add(str(uid).strip())

    def _save_whitelist(self):
        self.config["whitelist"] = sorted(list(self._whitelist))
        self.config.save_config()

    def _is_whitelisted(self, user_id):
        return str(user_id).strip() in self._whitelist

    def _is_admin(self, event):
        return str(event.get_sender_id()).strip() in self._admins

    def _save_violations(self):
        try:
            with open(self._get_data_file(), "w", encoding="utf-8") as f:
                json.dump(dict(self._violations), f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存违规记录失败: {e}")

    def _load_violations(self):
        try:
            if os.path.exists(self._get_data_file()):
                with open(self._get_data_file(), "r", encoding="utf-8") as f:
                    self._violations = json.load(f)
                    for gid in self._violations:
                        if not isinstance(self._violations[gid], dict):
                            self._violations[gid] = {}
        except Exception as e:
            logger.error(f"读取违规记录失败: {e}")

    def _is_enabled(self, group_id):
        if not self.enabled_groups:
            return False
        return str(group_id) in self.enabled_groups

    def _get_text(self, event):
        return "".join(c.text for c in event.get_messages() if isinstance(c, Plain)).strip()

    async def _mute(self, event, group_id, user_id, duration):
        bot = getattr(event, "bot", None)
        if not bot:
            return
        try:
            await bot.call_action("set_group_ban", group_id=int(group_id), user_id=int(user_id), duration=duration)
            if self.funny_mute and duration > 0:
                word = random.choice(self.funny_mute_words).replace("{name}", event.get_sender_name())
                try:
                    await bot.call_action("send_group_msg", group_id=int(group_id), message=word)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"禁言失败: {e}")

    async def _recall(self, event):
        bot = getattr(event, "bot", None)
        if not bot:
            return
        try:
            mid = getattr(event.message_obj, "message_id", None)
            if mid:
                await bot.call_action("delete_msg", message_id=int(mid))
        except Exception as e:
            logger.error(f"撤回失败: {e}")

    async def _send_private(self, event, user_id, text):
        try:
            await self.context.send_message(f"{event.get_platform_name()}:FriendMessage:{user_id}", MessageChain().message(text))
        except Exception as e:
            logger.error(f"发送私聊失败: {e}")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event):
        group_id = event.get_group_id()
        if not group_id or not self._is_enabled(group_id):
            return
        user_id = event.get_sender_id()
        if self._is_whitelisted(user_id):
            return

        now = datetime.datetime.now().timestamp()
        text = self._get_text(event)
        emoji_count = sum(1 for c in event.get_messages() if isinstance(c, (Image, Face)))

        if text and URL_REGEX.search(text):
            if user_id not in self._violations[group_id]:
                self._violations[group_id][user_id] = {"name": event.get_sender_name(), "count": 0}
            self._violations[group_id][user_id]["count"] += 1
            self._save_violations()
            await self._recall(event)
            await self._mute(event, group_id, user_id, self.url_mute)
            if self.private_notify:
                await self._send_private(event, user_id, f"检测到网页链接，已被禁言 {self.url_mute} 秒。")
            return

        if emoji_count >= self.spam_trigger:
            if user_id not in self._violations[group_id]:
                self._violations[group_id][user_id] = {"name": event.get_sender_name(), "count": 0}
            self._violations[group_id][user_id]["count"] += 1
            self._save_violations()
            await self._recall(event)
            await self._mute(event, group_id, user_id, self.spam_mute)
            if self.private_notify:
                await self._send_private(event, user_id, f"检测到表情包刷屏，已被禁言 {self.spam_mute} 秒。")
            return

        ts = self._timestamps[group_id][user_id]
        ts.append(now)
        count = sum(1 for t in ts if t > now - self.spam_window)
        if count >= self.spam_trigger:
            ts.clear()
            if user_id not in self._violations[group_id]:
                self._violations[group_id][user_id] = {"name": event.get_sender_name(), "count": 0}
            self._violations[group_id][user_id]["count"] += 1
            self._save_violations()
            await self._recall(event)
            await self._mute(event, group_id, user_id, self.spam_mute)
            if self.private_notify:
                await self._send_private(event, user_id, f"检测到刷屏，已被禁言 {self.spam_mute} 秒。")

    @filter.command("防刷屏状态")
    async def status(self, event):
        group_id = event.get_group_id()
        if not group_id:
            return
        yield event.plain_result(
            f"刷屏检测：{'开' if self._is_enabled(group_id) else '关'}\n"
            f"阈值：{self.spam_trigger}条/{self.spam_window}秒 禁言{self.spam_mute}秒\n"
            f"链接检测：{'开' if self._is_enabled(group_id) else '关'}\n"
            f"白名单：{len(self._whitelist)}人"
        )

    @filter.command("全员解禁")
    async def unmute_all(self, event):
        group_id = event.get_group_id()
        if not group_id:
            return
        bot = getattr(event, "bot", None)
        if not bot:
            yield event.plain_result("当前平台不支持此操作。")
            return
        try:
            await bot.call_action("set_group_whole_ban", group_id=int(group_id), enable=False)
            self._violations[group_id].clear()
            self._save_violations()
            yield event.plain_result("已关闭全员禁言。")
        except Exception as e:
            yield event.plain_result(f"操作失败: {e}")

    @filter.command("全体禁言")
    async def mute_all(self, event):
        group_id = event.get_group_id()
        if not group_id:
            return
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可操作。")
            return
        bot = getattr(event, "bot", None)
        if not bot:
            yield event.plain_result("当前平台不支持此操作。")
            return
        try:
            await bot.call_action("set_group_whole_ban", group_id=int(group_id), enable=True)
            yield event.plain_result("已开启全员禁言，仅群主和管理员可发言。发送「全员解禁」可关闭。")
        except Exception as e:
            yield event.plain_result(f"操作失败: {e}")

    @filter.command("加白")
    async def whitelist_add(self, event, qq: str):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可操作。")
            return
        self._whitelist.add(str(qq).strip())
        self._save_whitelist()
        yield event.plain_result(f"已将 {qq} 加入白名单。")

    @filter.command("移白")
    async def whitelist_remove(self, event, qq: str):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可操作。")
            return
        qq = str(qq).strip()
        if qq in self._whitelist:
            self._whitelist.remove(qq)
            self._save_whitelist()
            yield event.plain_result(f"已将 {qq} 移出白名单。")
        else:
            yield event.plain_result(f"{qq} 不在白名单中。")

    @filter.command("白名单")
    async def whitelist_list(self, event):
        if not self._is_admin(event):
            yield event.plain_result("仅管理员可操作。")
            return
        if self._whitelist:
            yield event.plain_result(f"白名单（{len(self._whitelist)}人）：\n" + "、".join(sorted(self._whitelist)))
        else:
            yield event.plain_result("白名单为空。")

    @filter.command("刷屏日报")
    async def daily_report(self, event):
        group_id = event.get_group_id()
        if not group_id:
            return
        group_name = await self._get_group_name(event, group_id)
        path = await self._generate_report_image(group_id, group_name, "日报")
        if path:
            yield event.image_result(path)
        else:
            yield event.plain_result(self._build_report_text(group_id, "日报"))

    @filter.command("刷屏周报")
    async def weekly_report(self, event):
        group_id = event.get_group_id()
        if not group_id:
            return
        group_name = await self._get_group_name(event, group_id)
        path = await self._generate_report_image(group_id, group_name, "周报")
        if path:
            yield event.image_result(path)
        else:
            yield event.plain_result(self._build_report_text(group_id, "周报"))

    async def _get_group_name(self, event, group_id):
        try:
            group = await event.get_group(group_id)
            if group and group.group_name:
                return group.group_name
        except Exception:
            pass
        return group_id

    def _build_report_text(self, group_id, report_type):
        v = self._violations.get(group_id, {})
        if not v:
            return f"{report_type}：今日暂无违规记录。"
        top = sorted(v.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
        lines = [f"刷屏{report_type}", f"总触发：{sum(d['count'] for d in v.values())}次"]
        for uid, data in top:
            lines.append(f"  {data['name']}：{data['count']}次")
        return "\n".join(lines)

    async def _generate_report_image(self, group_id, group_name, report_type):
        if not _HAS_PIL or not _FONT_PATH:
            return None
        v = self._violations.get(group_id, {})
        top5 = sorted(v.items(), key=lambda x: x[1]["count"], reverse=True)[:5]
        total = sum(d["count"] for d in v.values())
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        W, H = 600, 400
        img = PILImage.new("RGB", (W, H), (255, 240, 245))
        draw = ImageDraw.Draw(img)
        try:
            ft = ImageFont.truetype(_FONT_PATH, 28)
            fh = ImageFont.truetype(_FONT_PATH, 16)
            fb = ImageFont.truetype(_FONT_PATH, 20)
            fs = ImageFont.truetype(_FONT_PATH, 14)
        except Exception:
            return None
        draw.rectangle([(0, 0), (W, 60)], fill=(255, 150, 180))
        title = f"{group_name} - 刷屏 {report_type}"
        tw = draw.textbbox((0, 0), title, font=ft)[2]
        draw.text(((W - tw) / 2, 14), title, fill="white", font=ft)
        draw.text((20, 70), f"统计时间：{now_str}", fill=(120, 120, 120), font=fs)
        draw.text((20, 100), "总触发次数", fill=(100, 100, 100), font=fh)
        tw = draw.textbbox((0, 0), str(total), font=ft)[2]
        draw.text((40, 120), str(total), fill=(255, 80, 80), font=ft)
        draw.text((20, 170), "刷屏 Top 5", fill=(100, 100, 100), font=fh)
        x, y = 20, 195
        for cn, cw in [("排名", 30), ("用户ID", 120), ("次数", 80), ("趋势", 100)]:
            draw.text((x, y), cn, fill=(150, 150, 150), font=fs)
            x += cw
        draw.line([(20, 218), (580, 218)], fill=(220, 220, 220), width=1)
        colors = [(255, 80, 80), (255, 160, 80), (255, 200, 80), (120, 180, 120), (100, 150, 200)]
        for i, (uid, data) in enumerate(top5):
            y = 225 + i * 30
            bg = (235, 245, 255) if i % 2 == 0 else (245, 247, 250)
            draw.rectangle([(20, y), (580, y + 28)], fill=bg)
            draw.text((22, y+2), ["🥇","🥈","🥉","4","5"][i], fill=colors[i], font=fb)
            draw.text((50, y+2), data["name"][:10], fill=(60,60,60), font=fb)
            draw.text((150, y+2), str(data["count"]), fill=(255,80,80), font=fb)
            bw = int(200 * data["count"] / max(1, top5[0][1]["count"]))
            draw.rectangle([(280, y+6), (280+bw, y+22)], fill=(64,128,255))
        draw.text((20, 375), "发送「刷屏日报/刷屏周报」查看", fill=(180, 180, 180), font=fs)
        out_dir = os.path.join(os.path.dirname(__file__), "_reports")
        os.makedirs(out_dir, exist_ok=True)
        tag = "daily" if report_type == "日报" else "weekly"
        path = os.path.join(out_dir, f"report_{group_id}_{tag}_{int(datetime.datetime.now().timestamp())}.png")
        img.save(path)
        return path

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        self._load_violations()
        logger.info("刷屏检测插件已加载。")
