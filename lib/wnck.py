import platform

if platform.machine().startswith('arm'):
    from wnck_arm7 import *
else:
    if platform.architecture()[0] == '64bit':
        from wnck_64 import *
    else:
        from wnck_32 import *
