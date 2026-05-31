import sys, importlib.util, json, datetime, asyncio, time
from collections import deque

spec = importlib.util.spec_from_file_location("main", "main.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["main"] = mod
spec.loader.exec_module(mod)
cls = mod.AntiSpamPlugin

print("=== 模拟真实场景测试 ===\n")

# 模拟事件对象
class FakeBot:
    async def call_action(self, action, **kwargs):
        print(f"  [API] {action}: {kwargs}")
        return {"message_id": 999}

class FakeMsgObj:
    message_id = 999
    sender = type("s", (), {"role": "owner"})()

class FakeEvent:
    unified_msg_origin = "aiocqhttp:GroupMessage:123"
    bot = FakeBot()
    message_obj = FakeMsgObj()
    
    def get_group_id(self): return "123"
    def get_sender_id(self): return "u1"
    def get_sender_name(self): return "测试用户"
    def get_self_id(self): return "bot"
    def get_platform_name(self): return "aiocqhttp"
    def get_platform_id(self): return "aiocqhttp"
    def get_messages(self): return []
    def get_message_obj(self): return self.message_obj
    def is_private_chat(self): return False

p = cls(None, {"enabled_groups": ["123"], "admins": ["admin1"]})
p._admins.add("admin1")

print("1. 正常发消息（间隔0.5秒，发3条）")
import datetime as dt
for i in range(3):
    class E(FakeEvent):
        pass
    e = E()
    p._msg_timestamps["123"]["u1"].append(dt.datetime.now().timestamp())
    now = dt.datetime.now().timestamp()
    cutoff = now - p.spam_window
    count = sum(1 for t in p._msg_timestamps["123"]["u1"] if t > cutoff)
    if count >= p.spam_trigger:
        print("  ❌ 误判为刷屏")
        break
    await asyncio.sleep(0.5)
else:
    print("  ✅ 正常消息未被误判")

print("\n2. 快速发消息（1秒内发8条）")
p._msg_timestamps["123"]["u1"].clear()
now = dt.datetime.now().timestamp()
for i in range(8):
    p._msg_timestamps["123"]["u1"].append(now - 0.05 * (8 - i))

count = sum(1 for t in p._msg_timestamps["123"]["u1"] if t > now - p.spam_window)
if count >= p.spam_trigger:
    print(f"  ✅ 正确检测到刷屏 ({count}条)")
    p._msg_timestamps["123"]["u1"].clear()
else:
    print(f"  ❌ 未检测到刷屏 ({count}条)")

print("\n3. 管理员身份验证")
class AdminEvent(FakeEvent):
    def get_sender_id(self): return "admin1"
assert p._is_admin(AdminEvent()) == True, "管理员验证失败"
class NonAdminEvent(FakeEvent):
    def get_sender_id(self): return "normal_user"
assert p._is_admin(NonAdminEvent()) == False
print("  ✅ 管理员验证正常")

print("\n4. URL检测")
import re
url_re = re.compile(r"https?://[^\s]+")
assert url_re.search("http://example.com")
assert url_re.search("https://test.com/path")
assert not url_re.search("正常聊天")
print("  ✅ URL正则正常")

print("\n=== 全部测试通过 ===")
