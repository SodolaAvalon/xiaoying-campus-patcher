#!/usr/bin/env python3
"""Patch libapp.so (Dart AOT) to drop 广场/消息 tabs from 小应校园.

Patch sites (ARM64, addresses are vaddr inside libapp.so):
  buildDestinations @0xe03c60  -> keep [课表, 校园, 我的]
  buildAppRouteRoots @0xd6473c -> keep [timetable, school, me] branches
"""
import sys
import struct
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

NOP = 0xD503201F

def vaddr_to_off(elf, vaddr):
    for seg in elf.iter_segments():
        if seg['p_type'] != 'PT_LOAD':
            continue
        start = seg['p_vaddr']
        end = start + seg['p_filesz']
        if start <= vaddr < end:
            return seg['p_offset'] + (vaddr - start)
    raise ValueError(f"vaddr 0x{vaddr:x} not mapped")

def ldur_imm9(word, new_imm9):
    return (word & ~(0x1FF << 12)) | ((new_imm9 & 0x1FF) << 12)

def movz_imm16(word, new_imm16):
    return (word & ~(0xFFFF << 5)) | ((new_imm16 & 0xFFFF) << 5)

def ldr_imm12(word, new_byte_off):
    imm12 = new_byte_off // 8            # LDR (64-bit) scales by 8
    return (word & ~(0xFFF << 10)) | ((imm12 & 0xFFF) << 10)

def b_imm26(word, addr, target):
    return 0x14000000 | (((target - addr) // 4) & 0x03FFFFFF)

def main(src, dst):
    data = bytearray(open(src, 'rb').read())
    with open(src, 'rb') as f:
        elf = ELFFile(f)
        patches = []

        def add(addr, kind, arg, note):
            off = vaddr_to_off(elf, addr)
            old = struct.unpack_from('<I', data, off)[0]
            if kind == 'nop':
                new = NOP
            elif kind == 'ldur':
                assert (old & 0xFFC00000) == 0xF8400000, f"0x{addr:x} not LDUR: 0x{old:08x}"
                new = ldur_imm9(old, arg)
            elif kind == 'movz':
                assert (old & 0xFF800000) == 0xD2800000, f"0x{addr:x} not MOVZ(64): 0x{old:08x}"
                new = movz_imm16(old, arg)
            elif kind == 'ldr':
                assert (old & 0xFFC00000) == 0xF9400000, f"0x{addr:x} not LDR(64,unsigned): 0x{old:08x}"
                new = ldr_imm12(old, arg)
            elif kind == 'b':
                new = b_imm26(old, addr, arg)
            elif kind == 'beq2b':
                assert (old & 0xFF00001F) == 0x54000000, f"0x{addr:x} not B.cond: 0x{old:08x}"
                new = b_imm26(old, addr, arg)
            elif kind == 'raw':
                new = arg
            else:
                raise ValueError(kind)
            patches.append((addr, off, old, new, note))

        # --- A: buildDestinations ---
        add(0xE03D8C, 'ldur', -0x10, 'arr[2] = 我的 (was 广场)')
        add(0xE03D94, 'nop',  None, 'drop 消息 load')
        add(0xE03D98, 'nop',  None, 'drop 消息 store')
        add(0xE03D9C, 'nop',  None, 'drop 我的 load (moved up)')
        add(0xE03DA0, 'nop',  None, 'drop 我的 store (moved up)')
        add(0xE03DB8, 'movz', 3 * 2, 'list length 5 -> 3 (Smi)')

        # --- B: buildAppRouteRoots branches ---
        add(0xD64AE0, 'ldur', -0x40, 'branch[2] = me (was social)')
        add(0xD64AE8, 'nop',  None, 'drop chat load')
        add(0xD64AEC, 'nop',  None, 'drop chat store')
        add(0xD64AF0, 'nop',  None, 'drop me load (moved up)')
        add(0xD64AF4, 'nop',  None, 'drop me store (moved up)')
        add(0xD64B14, 'movz', 3 * 2, 'branches length 5 -> 3 (Smi)')

        # --- C: root redirect "/" -> "/timetable" (was "/social") ---
        add(0xD64EE0, 'ldr', 0x998, 'root redirect: /social -> /timetable')

        # --- D: 校园页 portal 清理 ---
        # D1: 不合并服务端 portal（应援计划/万能互助群/四六级查分 等全部来自服务端）
        add(0xE0BC90, 'beq2b', 0xE0BCEC, 'skip remote portals (b.eq -> b)')
        # D2/D3: 清空本地「小应」分类的 portal 列表 -> 该分组消失
        add(0xD66040, 'movz', 0x0, 'xiaoying.dart 小应 portals 3 -> 0')
        add(0xDAA804, 'movz', 0x0, 'bulletin 小应 portal 1 -> 0')
        # D4: 把不要的 portal 的 hookId 指向「绩点计算器」(#17)。distinctByKey 是后者覆盖前者，
        # 碰撞目标必须排在所有待删项之后，否则会顶掉保留项（实测 0xa50 会把「校园一卡通」顶掉）
        KEEP_HOOKID = 0xC80                 # [pp+0x1f000 + 0xc80] = "10259@本科生.绩点计算器"
        add(0xDB139C, 'ldr', KEEP_HOOKID, 'drop 校园地图 (dedupe)')
        add(0xDB176C, 'ldr', KEEP_HOOKID, 'drop 应网办 (dedupe)')
        add(0xDB1948, 'ldr', KEEP_HOOKID, 'drop 申飞购票 (dedupe)')
        add(0xDB1A20, 'ldr', KEEP_HOOKID, 'drop 自助洗衣 (dedupe)')
        add(0xDB1CFC, 'ldr', KEEP_HOOKID, 'drop 网络检测 (dedupe)')
        # D5: 校园页顶部「公告栏」卡片（带滚动跑马灯）—— slivers 列表 2 项缩到 1 项
        add(0xE0AA0C, 'movz', 1 * 2, 'drop bulletin card (slivers 2 -> 1)')

        # --- E: 修「导入课表失败」---
        # 教务周次字段从 "18" 变成 "第18"，解析器 int.parse('第18') 直接抛 FormatException。
        # mapChinesePunctuations 是一串区间比较，其中【(U+3010) 分支只做 writeCharCode。
        # 做法：把该分支的判定阈值改成 '第'(U+7B2C)，并把它的输出改成跳转到「不输出」路径，
        # 于是 '第' 被整字丢弃，其他字符仍走原有映射。
        add(0x16A8918, 'movz', 0x7B2C, 'punct map: outer threshold U+3010 -> 第')
        add(0x16A8964, 'movz', 0x7B2C, 'punct map: inner threshold U+3010 -> 第')
        add(0x16A8974, 'raw', 0x1400002D, 'punct map: drop 第 instead of writing [')

        md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        print(f"{'addr':>10}  {'old':>10}  {'new':>10}  note")
        for addr, off, old, new, note in patches:
            struct.pack_into('<I', data, off, new)
            print(f"0x{addr:08x}  0x{old:08x}  0x{new:08x}  {note}")

        print("\n=== verify (patched region) ===")
        for addr, off, old, new, note in patches:
            ctx_off = off - 8
            code = bytes(data[ctx_off:ctx_off + 24])
            insns = list(md.disasm(code, addr - 8))
            print(f"-- around 0x{addr:x}")
            for i in insns:
                mark = ' <==' if i.address == addr else ''
                print(f"   0x{i.address:x}: {i.mnemonic:<8} {i.op_str}{mark}")

    open(dst, 'wb').write(data)
    print(f"\nwritten {dst} ({len(data)} bytes)")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
