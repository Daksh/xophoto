import platform
import sys
from ctypes import cdll

if platform.machine().startswith('arm'):
    from wnck_arm7 import *
else:
    if platform.architecture()[0] == '64bit':
        #from wnck_64 import *
        wnck_path = "wnck_64"
    else:
        from wnck_32 import *
    wnck = cdll.LoadLibrary("lib/%s/wnck.so" % wnck_path)
sys.path.append("lib/%s" % wnck_path)
