#!/usr/bin/env python3
"""Replace lib/arm64-v8a/libapp.so inside the APK, preserving entry order/compression."""
import sys
import zipfile

src, newso, dst = sys.argv[1], sys.argv[2], sys.argv[3]
target = 'lib/arm64-v8a/libapp.so'
data = open(newso, 'rb').read()

zin = zipfile.ZipFile(src, 'r')
zout = zipfile.ZipFile(dst, 'w')
replaced = False
for info in zin.infolist():
    buf = zin.read(info.filename)
    if info.filename == target:
        buf = data
        replaced = True
        print(f"  replaced {target}: {info.file_size} -> {len(buf)} bytes (stored)")
        zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        zi.compress_type = zipfile.ZIP_STORED
        zi.external_attr = info.external_attr
        zi.internal_attr = info.internal_attr
        zi.create_system = info.create_system
        zout.writestr(zi, buf)
    else:
        zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        zi.compress_type = info.compress_type
        zi.external_attr = info.external_attr
        zi.internal_attr = info.internal_attr
        zi.create_system = info.create_system
        zout.writestr(zi, buf)
zout.close()
zin.close()
if not replaced:
    sys.exit(f"!! {target} not found")
print("ok")
