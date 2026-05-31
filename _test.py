import sys, importlib.util, re

spec = importlib.util.spec_from_file_location("main", "main.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["main"] = mod
spec.loader.exec_module(mod)

url_re = re.compile(r"https?://[^\s]+|qq\s*\d+|微信号|wx|vx")

tests = [
    ("http://bad.com", True),
    ("https://example.com/path", True),
    ("qq123456789", True),
    ("微信号 mywechat", True),
    ("wx12345", True),
    ("vx", True),
    ("正常聊天内容", False),
    ("今天天气真好", False),
    ("hello world", False),
]

all_ok = True
for text, should_match in tests:
    result = bool(url_re.search(text))
    ok = result == should_match
    if not ok:
        all_ok = False
    print(f"  {'OK' if ok else 'FAIL'}: {text} -> {result}")
print(f"URL regex: {'PASS' if all_ok else 'FAIL'}")

src = open("main.py", encoding="utf-8").read()
url_section = src.split("_group_url_enabled.get")[1].split("return")[0]
assert "url_trigger" not in url_section, "still has url_trigger"
assert "URL_REGEX.search(text)" in url_section
print("Plugin URL detection: PASS")
print("\nALL PASS")
