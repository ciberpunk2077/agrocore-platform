"""Private Windows DACLs for disposable encrypted delivery; fail closed."""
import ctypes
from ctypes import wintypes
import os

from .errors import D2Error


def _api():
    if os.name != 'nt':
        raise D2Error('Private delivery requires Windows ACL support.')
    api = ctypes.WinDLL('advapi32', use_last_error=True)
    signatures = {
        'OpenProcessToken': ([wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)], wintypes.BOOL),
        'GetTokenInformation': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        'ConvertSidToStringSidW': ([ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)], wintypes.BOOL),
        'ConvertStringSecurityDescriptorToSecurityDescriptorW': ([wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p], wintypes.BOOL),
        'SetFileSecurityW': ([wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
        'GetFileSecurityW': ([wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        'GetSecurityDescriptorDacl': ([ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        'GetAce': ([ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        getattr(api, name).argtypes = args
        getattr(api, name).restype = result
    return api


def _kernel():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.LocalFree.argtypes = [ctypes.c_void_p]
    return api


def _sid(api, pointer):
    value = wintypes.LPWSTR()
    if not api.ConvertSidToStringSidW(pointer, ctypes.byref(value)):
        raise D2Error('Unable to inspect delivery ACL identity.')
    try:
        return value.value
    finally:
        _kernel().LocalFree(ctypes.cast(value, ctypes.c_void_p))


def current_sid():
    api = _api(); kernel = _kernel(); token = wintypes.HANDLE()
    if not api.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise D2Error('Unable to inspect Windows process identity.')
    try:
        size = wintypes.DWORD()
        api.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not api.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise D2Error('Unable to inspect Windows process token.')
        return _sid(api, ctypes.c_void_p.from_buffer(buffer).value)
    finally:
        kernel.CloseHandle(token)


def restrict_directory(path):
    api = _api(); descriptor = ctypes.c_void_p()
    sddl = f'D:P(A;OICI;FA;;;{current_sid()})(A;OICI;FA;;;SY)'
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
        raise D2Error('Unable to construct private delivery ACL.')
    try:
        if not api.SetFileSecurityW(str(path), 0x80000004, descriptor):
            raise D2Error('Unable to enforce private delivery ACL.')
    finally:
        _kernel().LocalFree(descriptor)
    verify_private(path)


def verify_private(path):
    api = _api(); size = wintypes.DWORD()
    api.GetFileSecurityW(str(path), 4, None, 0, ctypes.byref(size))
    buffer = ctypes.create_string_buffer(size.value)
    if not api.GetFileSecurityW(str(path), 4, buffer, size, ctypes.byref(size)):
        raise D2Error('Unable to read delivery ACL.')
    present = wintypes.BOOL(); defaulted = wintypes.BOOL(); acl = ctypes.c_void_p()
    if not api.GetSecurityDescriptorDacl(buffer, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)) or not present or not acl.value:
        raise D2Error('Missing private delivery DACL.')
    # ACL header: revision/zero/size/ACE-count/zero (8 bytes).
    count = ctypes.c_ushort.from_address(acl.value + 4).value
    expected = {current_sid(), 'S-1-5-18'}; seen = set()
    for index in range(count):
        ace = ctypes.c_void_p()
        if not api.GetAce(acl, index, ctypes.byref(ace)):
            raise D2Error('Unable to inspect delivery ACE.')
        kind = ctypes.c_ubyte.from_address(ace.value).value
        mask = ctypes.c_uint32.from_address(ace.value + 4).value
        if kind != 0 or mask != 0x1F01FF:
            raise D2Error('Unexpected delivery access rule.')
        seen.add(_sid(api, ace.value + 8))
    if count != 2 or seen != expected:
        raise D2Error('Delivery grants access beyond the process identity and SYSTEM.')
