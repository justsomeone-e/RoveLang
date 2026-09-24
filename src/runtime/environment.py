from typing import Any, Dict, List, Optional
import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
import os
import sys
import time
import math
import queue
import threading
import urllib.request
import urllib.parse
import json

# =========================================================
# 1. OPTION & RESULT TYPES
# =========================================================
class Result:
    def __init__(self, is_ok: bool, value: Any):
        self.is_ok = is_ok
        self.value = value

    def unwrap(self):
        if not self.is_ok:
            raise Exception(f"Called unwrap on an Err: {self.value}")
        return self.value

    def __repr__(self):
        return f"Ok({repr(self.value)})" if self.is_ok else f"Err({repr(self.value)})"

def Ok(val): return Result(True, val)
def Err(err): return Result(False, err)

# =========================================================
# 2. FILE SYSTEM API (fs)
# =========================================================
class FileSystemAPI:
    @staticmethod
    def read(path: str) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return ""

    @staticmethod
    def write(path: str, data: str) -> bool:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(str(data))
            return True
        except Exception:
            return False

    @staticmethod
    def exists(path: str) -> bool:
        return os.path.exists(path)

    @staticmethod
    def delete(path: str) -> bool:
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
            return False
        except Exception:
            return False

# =========================================================
# 3. OPERATING SYSTEM API (os)
# =========================================================
class OperatingSystemAPI:
    @staticmethod
    def args() -> list:
        return sys.argv

    @staticmethod
    def env(key: str) -> str:
        return os.environ.get(key, "")

    @staticmethod
    def cwd() -> str:
        return os.getcwd()

    @staticmethod
    def platform() -> str:
        return sys.platform

# =========================================================
# 4. NETWORK API (http)
# =========================================================
class HttpResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body

class HttpAPI:
    @staticmethod
    def get(url: str) -> HttpResponse:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Rove/5'})
            with urllib.request.urlopen(req, timeout=5) as response:
                body = response.read().decode('utf-8')
                return HttpResponse(response.status, body)
        except Exception as e:
            return HttpResponse(500, str(e))

    @staticmethod
    def post(url: str, data: str) -> HttpResponse:
        try:
            req = urllib.request.Request(url, data=str(data).encode('utf-8'), headers={'User-Agent': 'Rove/5'})
            with urllib.request.urlopen(req, timeout=5) as response:
                body = response.read().decode('utf-8')
                return HttpResponse(response.status, body)
        except Exception as e:
            return HttpResponse(500, str(e))

# =========================================================
# 5. CONCURRENCY & CHANNELS
# =========================================================
class Channel:
    def __init__(self):
        self.q = queue.Queue()

    def send(self, val: Any):
        self.q.put(val)

    def receive(self) -> Any:
        return self.q.get()

def channel():
    return Channel()

def spawn(fn, *args):
    th = threading.Thread(target=fn, args=args, daemon=True)
    th.start()
    return th

# =========================================================
# 6. MEMORY & UNCHECKED SYSTEM
# =========================================================
def addr(x):
    return id(x)

def peek(a):
    return 1337

def memdump(a, length=16):
    print(f"0x{a:016X}: 52 6F 76 65                                      | Rove")

def delay_ms(ms):
    time.sleep(ms / 1000.0)

# =========================================================
# 7. EXPORTED RUNTIME DICTIONARY
# =========================================================
def get_runtime_env():
    return {
        "print": print,
        "input": input,
        "fs": FileSystemAPI,
        "os": OperatingSystemAPI,
        "http": HttpAPI,
        "channel": channel,
        "spawn": spawn,
        "addr": addr,
        "peek": peek,
        "memdump": memdump,
        "delay_ms": delay_ms,
        "Result": Result,
        "Ok": Ok,
        "Err": Err,
        "to_int": lambda s: int(s) if str(s).strip().isdigit() else 0,
        "to_string": str,
        "to_str": str,
        "is_number": lambda s: str(s).strip().isdigit() if s else False,
        "contains": lambda s, sub: str(sub) in str(s),
        "Map": dict,
        "Set": set,
        "Array": list,
        "math": math,
        "time": time
    }
