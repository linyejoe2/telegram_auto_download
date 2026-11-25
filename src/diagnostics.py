"""
src/diagnostics.py — find out what uses the CPU (Windows app "Diagnostics" tab, v3.6.1).

CpuMonitor.sample() measures, between two calls, the CPU time of
  - every thread of this process (Windows Toolhelp + GetThreadTimes); Python threads are shown by
    their name (bot, web library, library workers, people database, AI 辨識 …), native threads
    (OpenCV, ffmpeg pipes, Tk, the C runtime) as "native";
  - every child / grandchild process (ffmpeg, Playwright's node, …).
profile() samples the Python stacks of all threads for a few seconds and, together with the CPU
measured over the same time, writes a report of where the busy threads spend it.
No extra dependencies: ctypes only (Windows); elsewhere only the Python stacks are available.
"""

import collections
import ctypes
import os
import sys
import threading
import time
import traceback
from typing import Dict, List, Optional

IS_WINDOWS = os.name == 'nt'
CORES = os.cpu_count() or 1

if IS_WINDOWS:
    from ctypes import wintypes

    # PyDLL keeps the GIL during the call: WinDLL releases it, and walking the system's thread list
    # (thousands of calls) then waits ~5 ms per call for a busy Python thread to give the GIL back.
    # On 64-bit Windows there is one calling convention, so PyDLL is fine; 32-bit needs stdcall.
    kernel32 = (ctypes.PyDLL('kernel32', use_last_error=True) if ctypes.sizeof(ctypes.c_void_p) == 8
                else ctypes.WinDLL('kernel32', use_last_error=True))

    class FILETIME(ctypes.Structure):
        _fields_ = [('lo', wintypes.DWORD), ('hi', wintypes.DWORD)]

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ThreadID', wintypes.DWORD),
                    ('th32OwnerProcessID', wintypes.DWORD), ('tpBasePri', wintypes.LONG),
                    ('tpDeltaPri', wintypes.LONG), ('dwFlags', wintypes.DWORD)]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD),
                    ('szExeFile', wintypes.WCHAR * 260)]

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _times_args = [wintypes.HANDLE] + [ctypes.POINTER(FILETIME)] * 4
    kernel32.GetThreadTimes.argtypes = _times_args
    kernel32.GetProcessTimes.argtypes = _times_args

    TH32CS_SNAPPROCESS, TH32CS_SNAPTHREAD = 0x2, 0x4
    THREAD_QUERY_LIMITED_INFORMATION = 0x0800
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    INVALID_HANDLE = ctypes.c_void_p(-1).value


def _ft(ft) -> float:
    return ((ft.hi << 32) | ft.lo) / 1e7          # 100 ns units -> seconds


def _times(fn, handle) -> Optional[float]:
    c, e, k, u = FILETIME(), FILETIME(), FILETIME(), FILETIME()
    if not fn(handle, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
        return None
    return _ft(k) + _ft(u)


def _thread_ids(pid: int) -> List[int]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if not snap or snap == INVALID_HANDLE:
        return []
    out = []
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(THREADENTRY32)
        ok = kernel32.Thread32First(snap, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                out.append(entry.th32ThreadID)
            ok = kernel32.Thread32Next(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return out


def _descendants(pid: int) -> Dict[int, str]:
    """Child, grandchild … processes of `pid`: {pid: exe name}."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE:
        return {}
    parent, names = {}, {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            parent[entry.th32ProcessID] = entry.th32ParentProcessID
            names[entry.th32ProcessID] = entry.szExeFile
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    out, todo = {}, [pid]
    while todo:
        current = todo.pop()
        for child, par in parent.items():
            if par == current and child not in out and child != pid:
                out[child] = names.get(child, '?')
                todo.append(child)
    return out


def _thread_cpu(tid: int) -> Optional[float]:
    handle = kernel32.OpenThread(THREAD_QUERY_LIMITED_INFORMATION, False, tid)
    if not handle:
        return None
    try:
        return _times(kernel32.GetThreadTimes, handle)
    finally:
        kernel32.CloseHandle(handle)


def _process_cpu(pid: Optional[int] = None) -> Optional[float]:
    if pid is None:
        return _times(kernel32.GetProcessTimes, kernel32.GetCurrentProcess())
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        return _times(kernel32.GetProcessTimes, handle)
    finally:
        kernel32.CloseHandle(handle)


def python_threads() -> Dict[int, threading.Thread]:
    """native thread id -> Python thread."""
    return {t.native_id: t for t in threading.enumerate() if getattr(t, 'native_id', None)}


class CpuMonitor:
    """CPU use between two sample() calls. Percentages are of ONE core (100 % = one core busy);
    `machine` is the Task Manager figure (all cores = 100 %)."""

    def __init__(self):
        self._last = None

    def _raw(self) -> dict:
        pid = os.getpid()
        threads = {tid: _thread_cpu(tid) for tid in _thread_ids(pid)}
        children = {cpid: (name, _process_cpu(cpid)) for cpid, name in _descendants(pid).items()}
        return {'time': time.perf_counter(), 'process': _process_cpu(), 'threads': threads, 'children': children}

    def sample(self) -> Optional[dict]:
        if not IS_WINDOWS:
            return None
        now = self._raw()
        last, self._last = self._last, now
        if not last:
            return {'ready': False}
        span = max(now['time'] - last['time'], 1e-3)
        pct = lambda a, b: max(0.0, (a - b) / span * 100) if a is not None and b is not None else 0.0
        names = python_threads()
        rows = []
        for tid, cpu in now['threads'].items():
            t = names.get(tid)
            rows.append({'kind': 'python' if t else 'native', 'id': tid,
                         'name': (t.name if t else f'native thread {tid}') + (' (main / Tk)' if t is threading.main_thread() else ''),
                         'cpu': pct(cpu, last['threads'].get(tid)) if tid in last['threads'] else 0.0,
                         'total': cpu or 0.0})
        for cpid, (name, cpu) in now['children'].items():
            prev = last['children'].get(cpid)
            rows.append({'kind': 'process', 'id': cpid, 'name': f'{name} (pid {cpid})',
                         'cpu': pct(cpu, prev[1]) if prev else 0.0, 'total': cpu or 0.0})
        # busiest first; at equal CPU the named Python threads and child processes before the anonymous
        # native ones, then by CPU used since they started
        rank = {'python': 0, 'process': 1, 'native': 2}
        rows.sort(key=lambda r: (-round(r['cpu'], 1), rank[r['kind']], -r['total']))
        process = pct(now['process'], last['process'])
        children = sum(r['cpu'] for r in rows if r['kind'] == 'process')
        return {'ready': True, 'span': span, 'process': process, 'children': children,
                'machine': (process + children) / CORES, 'cores': CORES, 'rows': rows,
                'threads': len(now['threads'])}


def _frame_text(frame) -> str:
    code = frame.f_code
    return f"{os.path.basename(code.co_filename)}:{frame.f_lineno} {code.co_name}"


def _stack(frame, depth: int = 8) -> tuple:
    out = []
    while frame is not None and len(out) < depth:
        out.append(_frame_text(frame))
        frame = frame.f_back
    return tuple(out)


def profile(seconds: float = 10, hz: int = 100, state: str = '', stop=None) -> str:
    """Sample every Python thread's stack `hz` times a second for `seconds`, measure CPU per thread
    over the same time, and return a text report (busiest threads first, with their most common stacks)."""
    monitor = CpuMonitor()
    monitor.sample()
    me = threading.get_ident()
    counts: Dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    samples = 0
    end = time.perf_counter() + seconds
    while time.perf_counter() < end and not (stop and stop()):
        for ident, frame in sys._current_frames().items():
            if ident != me:
                counts[ident][_stack(frame)] += 1
        samples += 1
        time.sleep(1 / hz)
    cpu = monitor.sample() or {}

    by_ident = {t.ident: t for t in threading.enumerate()}
    native_cpu = {r['id']: r['cpu'] for r in cpu.get('rows', []) if r['kind'] != 'process'}
    lines = [f"Telegram Auto Download — CPU profile {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Sampled {samples} times over {seconds:g} s ({hz} Hz), {CORES} CPU cores"]
    if cpu.get('ready'):
        lines.append(f"Process: {cpu['process']:.1f} % of one core, child processes {cpu['children']:.1f} %, "
                     f"= {cpu['machine']:.1f} % of the whole machine (Task Manager)")
    if state:
        lines += ['', 'App state:', state]
    lines += ['', 'CPU by thread / process (% of one core):']
    for r in cpu.get('rows', [])[:25]:
        lines.append(f"  {r['cpu']:6.1f} %  {r['kind']:<8} {r['name']}")

    threads = []
    for ident, counter in counts.items():
        t = by_ident.get(ident)
        threads.append((native_cpu.get(getattr(t, 'native_id', None), 0.0), ident, t, counter))
    threads.sort(key=lambda x: -x[0])
    lines += ['', 'Where each Python thread was (most common stacks, innermost call first):']
    for usage, ident, t, counter in threads:
        name = t.name if t else f'thread {ident}'
        lines.append('')
        lines.append(f"== {name}  —  {usage:.1f} % CPU")
        for stack, n in counter.most_common(3):
            lines.append(f"   {n / max(samples, 1) * 100:5.1f} % of samples:")
            lines += [f"        {f}" for f in stack]
    return '\n'.join(lines)


def dump_stacks() -> str:
    """Current stack of every Python thread (like faulthandler, but with thread names)."""
    by_ident = {t.ident: t for t in threading.enumerate()}
    out = []
    for ident, frame in sys._current_frames().items():
        t = by_ident.get(ident)
        out.append(f"== {t.name if t else ident} (native id {getattr(t, 'native_id', '?')})")
        out += [line.rstrip() for line in traceback.format_stack(frame)]
        out.append('')
    return '\n'.join(out)
