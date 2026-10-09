from __future__ import annotations

import argparse
import ctypes
import datetime
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import uuid
from collections import deque
from contextlib import contextmanager
from pathlib import Path

from . import __version__
from .steam import GameProcess, running_games, steam_roots, validate_tf_directory
from .storage import atomic_bytes, read_json, write_json


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def clean_text(text):
    text = re.sub(r'(?im)(\b(?:rcon_password|sv_password|token|secret|password)\b\s*[=:]?\s*)"[^"\n]*"', r'\1"[redacted]"', text)
    return re.sub(r'(?i)\b[a-f0-9]{64}\b', '[redacted]', text)


def read_tail(path, maximum=512 * 1024):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        with path.open('rb') as file:
            file.seek(max(0, path.stat().st_size - maximum))
            return clean_text(file.read(maximum).decode('utf-8', errors='replace'))
    except OSError:
        return None


class ProcessProbe:
    def __init__(self, game):
        self.game = game; self.handle = None; self.start_ticks = None
        if sys.platform == 'win32':
            from ctypes import wintypes as w
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.OpenProcess.argtypes = (w.DWORD, w.BOOL, w.DWORD); self.kernel.OpenProcess.restype = w.HANDLE
            self.kernel.GetExitCodeProcess.argtypes = (w.HANDLE, ctypes.POINTER(w.DWORD)); self.kernel.GetExitCodeProcess.restype = w.BOOL
            self.kernel.WaitForSingleObject.argtypes = (w.HANDLE, w.DWORD); self.kernel.WaitForSingleObject.restype = w.DWORD
            self.kernel.CloseHandle.argtypes = (w.HANDLE,)
            self.handle = self.kernel.OpenProcess(0x1000 | 0x100000, False, game.pid)
            self.user = ctypes.WinDLL('user32', use_last_error=True)
            self.callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
            self.user.EnumWindows.argtypes = (self.callback_type, w.LPARAM)
            self.user.GetWindowThreadProcessId.argtypes = (w.HWND, ctypes.POINTER(w.DWORD))
            self.user.IsWindowVisible.argtypes = (w.HWND,); self.user.IsWindowVisible.restype = w.BOOL
            self.user.SendMessageTimeoutW.argtypes = (w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT, ctypes.POINTER(ctypes.c_size_t))
            self.user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        else:
            value = self._linux_stat()
            self.start_ticks = value[19] if value and len(value) > 19 else None

    def _linux_stat(self):
        try:
            text = Path(f'/proc/{self.game.pid}/stat').read_text()
            return text[text.rfind(')') + 2:].split()
        except OSError:
            return None

    def status(self):
        if sys.platform != 'win32':
            value = self._linux_stat()
            if not value or len(value) < 20 or value[19] != self.start_ticks or value[0] == 'Z':
                return False, None, None
            return True, None, None
        from ctypes import wintypes as w
        if not self.handle:
            return None, None, None
        wait = self.kernel.WaitForSingleObject(self.handle, 0)
        if wait == 0:
            code = w.DWORD()
            return False, int(code.value) if self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)) else None, None
        if wait != 258:
            return None, None, None
        windows = []
        @self.callback_type
        def enum_window(hwnd, _):
            pid = w.DWORD(); self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.game.pid and self.user.IsWindowVisible(hwnd):
                windows.append(hwnd)
            return len(windows) < 4
        self.user.EnumWindows(enum_window, 0)
        responses = []
        for hwnd in windows:
            reply = ctypes.c_size_t()
            ctypes.set_last_error(0)
            answered = bool(self.user.SendMessageTimeoutW(hwnd, 0, 0, 0, 0x2 | 0x20, 150, ctypes.byref(reply)))
            if answered or ctypes.get_last_error() in (0, 1460):responses.append(answered)
        return True, None, all(responses) if responses else None

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle); self.handle = None


def dump_process(path):
    try:
        with path.open('rb') as file:
            header = file.read(32)
            if len(header) != 32 or header[:4] != b'MDMP': return None
            count, directory = struct.unpack_from('<II', header, 8)
            if count > 128 or directory > path.stat().st_size - count * 12: return None
            file.seek(directory); streams = file.read(count * 12)
            for offset in range(0, len(streams), 12):
                kind, size, address = struct.unpack_from('<III', streams, offset)
                if kind == 15 and size >= 12:
                    file.seek(address); misc = file.read(12)
                    if len(misc) == 12:
                        _, flags, pid = struct.unpack('<III', misc)
                        return pid if flags & 1 else None
    except (OSError, struct.error):
        pass
    return None


def collect_dumps(tf, folder, pid, since):
    roots = [tf.parent, tf, tf.parent/'dumps', tf/'dumps']
    roots += [root/'dumps' for root in steam_roots()]
    roots.append(Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))/'CrashDumps' if sys.platform == 'win32' else Path('/tmp/dumps'))
    copied = []; budget = 32 * 1024 * 1024; seen = set()
    for root in dict.fromkeys(roots):
        try:
            candidates = sorted(root.glob('*.dmp'), key=lambda p:p.stat().st_mtime, reverse=True)[:20]
        except OSError:
            continue
        for path in candidates:
            try:
                if path.is_symlink() or path.resolve() in seen: continue
                seen.add(path.resolve()); stat = path.stat()
                if stat.st_mtime < since - 5 or stat.st_mtime > time.time()+5: continue
                dump_pid = dump_process(path)
                named = re.match(rf'^(?:tf_win64|tf|hl2)\.exe\.{pid}\.', path.name, re.I)
                if dump_pid != pid and not named: continue
                item = {'source':str(path), 'bytes':stat.st_size}
                if stat.st_size <= budget:
                    target = folder/('dump-'+str(len(copied))+'-'+path.name)
                    with path.open('rb') as stream:contents=stream.read(stat.st_size+1)
                    if len(contents)!=stat.st_size or path.stat().st_size!=stat.st_size:continue
                    atomic_bytes(target,contents)
                    item['saved'] = target.name; budget -= stat.st_size
                else: item['saved'] = False
                copied.append(item)
            except OSError:
                continue
    return copied


def collect_logs(tf, data, folder):
    paths = [(tf/'mgebot-console.log','console-tail.log'), (tf/'console.log','console-legacy-tail.log'),
             (data/'application.log','launcher-tail.log')]
    logs = tf/'addons/sourcemod/logs'
    try:
        for path in sorted(logs.glob('errors_*.log'), key=lambda p:p.stat().st_mtime, reverse=True)[:3]:
            paths.append((path,path.name))
    except OSError:
        pass
    saved = []
    for path,name in paths:
        text = read_tail(path)
        if text is not None:
            atomic_bytes(folder/name,text.encode()); saved.append(name)
    for path,name in [(tf/'addons/sourcemod/data/mgebot_companion/heartbeat.json','last-heartbeat.json'),
                      (data/'watch/latest-session.json','last-session.json')]:
        try:
            value=read_json(path)
            if isinstance(value,dict): write_json(folder/name,value); saved.append(name)
        except (OSError,ValueError):
            pass
    return saved


def write_report(tf, data, game, kind, since, events, exit_code=None, recovered=False, folder=None):
    folder = folder or data/'crashlogs'/('tf2-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(game.pid)+'-'+uuid.uuid4().hex[:6])
    folder.mkdir(parents=True,exist_ok=True)
    try:previous=read_json(folder/'report.json',{})
    except (OSError,ValueError):previous={}
    record = {'schema':1,'recorder':'mgebot duel','launcher_version':__version__,'at':timestamp(),'kind':kind,
              'first_kind':previous.get('first_kind',kind),'first_at':previous.get('first_at',timestamp()),
              'pid':game.pid,'executable':game.executable,'tf_directory':str(tf),'platform':sys.platform,
              'observed_since':since,'exit_code':exit_code,'exit_hex':f'0x{exit_code:08X}' if exit_code is not None else None,
              'recovered':recovered,'events':list(events),
              'logs':collect_logs(tf,data,folder),'dumps':collect_dumps(tf,folder,game.pid,since)}
    write_json(folder/'report.json',record)
    reports=[]
    for path in (data/'crashlogs').glob('tf2-*/report.json'):
        try:
            if not path.parent.is_symlink() and read_json(path,{}).get('recorder')=='mgebot duel':reports.append(path)
        except (OSError,ValueError):pass
    for path in sorted(reports,key=lambda p:p.stat().st_mtime,reverse=True)[10:]:
        if path.parent!=folder:shutil.rmtree(path.parent)
    return folder


@contextmanager
def watcher_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as file:
        file.seek(0)
        if sys.platform=='win32':
            import msvcrt
            if path.stat().st_size==0:file.write(b'0');file.flush();file.seek(0)
            try:msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:yield False;return
        else:
            import fcntl
            try:fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:yield False;return
        yield True


def monitor(game, tf, data):
    with watcher_lock(data/'watch'/f'pid-{game.pid}.lock') as acquired:
        if not acquired:return
        probe=ProcessProbe(game);since=time.time();events=deque(maxlen=60)
        unresponsive=None;hang=None;recovered=False
        try:
            while True:
                alive,code,responsive=probe.status()
                try:
                    heartbeat=read_json(tf/'addons/sourcemod/data/mgebot_companion/heartbeat.json',{})
                    at=float(heartbeat.get('at',0)) if isinstance(heartbeat,dict) else 0
                    age=max(0,time.time()-at) if at>=since-5 else None
                except (OSError,ValueError,TypeError):age=None
                events.append({'at':timestamp(),'alive':alive,'window_responding':responsive,'heartbeat_age':round(age,1) if age is not None else None})
                if alive is None:
                    write_report(tf,data,game,'monitor_unavailable',since,events);return
                if not alive:
                    time.sleep(3)
                    kind='abnormal_exit' if code not in (None,0) else 'process_exited'
                    folder=write_report(tf,data,game,kind,since,events,code,recovered,hang)
                    time.sleep(5)
                    write_report(tf,data,game,kind,since,events,code,recovered,folder)
                    return
                stalled=responsive is False or (responsive is None and age is not None and age>30)
                if stalled:
                    if unresponsive is None:unresponsive=time.monotonic()
                    if hang is None and time.monotonic()-unresponsive>=20:
                        kind='window_unresponsive' if responsive is False else 'heartbeat_stalled'
                        hang=write_report(tf,data,game,kind,since,events)
                else:
                    unresponsive=None
                    if hang is not None and not recovered:
                        recovered=True;write_report(tf,data,game,'recovered',since,events,recovered=True,folder=hang)
                time.sleep(2)
        finally:
            probe.close()


def start_watch(data, tf, game=None):
    python=Path(sys.executable)
    if sys.platform=='win32' and (python.parent/'pythonw.exe').exists():python=python.parent/'pythonw.exe'
    arguments=[str(python),'-B','-m','mgebot_launcher.crashlog','--tf',str(tf),'--data',str(data),'--pid',str(game.pid if game else 0)]
    options={'cwd':str(Path(__file__).resolve().parents[1]),'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,'close_fds':True}
    if sys.platform=='win32':options['creationflags']=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)
    else:options['start_new_session']=True
    subprocess.Popen(arguments,**options)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tf',required=True,type=Path);parser.add_argument('--data',required=True,type=Path);parser.add_argument('--pid',required=True,type=int)
    args=parser.parse_args();tf=validate_tf_directory(args.tf);data=args.data.resolve()
    key=str(args.pid) if args.pid else hashlib.sha256(str(tf).encode()).hexdigest()[:12]
    with watcher_lock(data/'watch'/('starting-'+key+'.lock')) as acquired:
        if not acquired:return
        for _ in range(60):
            games=running_games();game=next((g for g in games if g.tf_directory==tf and (not args.pid or g.pid==args.pid)),None)
            if game:
                monitor(game,tf,data);return
            if args.pid:return
            time.sleep(2)


if __name__=='__main__':
    try:main()
    except Exception:
        parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--data',type=Path)
        args,_=parser.parse_known_args()
        if args.data:
            (args.data/'crashlogs').mkdir(parents=True,exist_ok=True)
            logging.basicConfig(filename=args.data/'crashlogs/recorder-error.log',level=logging.INFO)
            logging.exception('Crash recorder stopped')
