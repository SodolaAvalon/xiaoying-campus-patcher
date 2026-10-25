# 补丁明细

所有地址都是 `libapp.so` 内的 **vaddr**（与该库加载基址无关，用 ELF 段表换算文件偏移）。
原始/补丁列均为 4 字节指令的字面值。

换算方法：

```python
for seg in ELFFile(f).iter_segments():
    if seg['p_type'] == 'PT_LOAD' and seg['p_vaddr'] <= addr < seg['p_vaddr'] + seg['p_filesz']:
        off = seg['p_offset'] + (addr - seg['p_vaddr'])
```

---

## A 组 · 底部导航 5 → 3

函数：`_AppLayoutState::buildDestinations` @ `0xe03c60`
源文件：`package:xiaoying/page/layout.dart`

原逻辑构造 5 个 `FloatingNavigationDestination`：`课表`(池中常量) / `校园` / `广场` / `消息` / `我的`，
再一次性写进长度 5 的 `GrowableArray`（Dart 的 Smi 编码：长度 5 存为 `0xa`）。

目标：`课表 / 校园 / 我的`。做法是把「我的」上移到第 3 槽，抹掉后两个的读写，再把长度改成 3。

| 地址 | 原始 | 补丁 | 说明 |
|---|---|---|---|
| `0xe03d8c` | `0xf85e83a1` `ldur x1,[fp,#-0x18]` | `0xf85f03a1` `ldur x1,[fp,#-0x10]` | 第 3 槽改读「我的」 |
| `0xe03d94` | `0xf85e03a1` | `0xd503201f` NOP | 去掉「消息」load |
| `0xe03d98` | `0xb801b001` | `0xd503201f` NOP | 去掉「消息」store |
| `0xe03d9c` | `0xf85f03a1` | `0xd503201f` NOP | 「我的」load 已上移 |
| `0xe03da0` | `0xb801f001` | `0xd503201f` NOP | 「我的」store 已上移 |
| `0xe03db8` | `0xd2800141` `movz x1,#0xa` | `0xd28000c1` `movz x1,#0x6` | 列表长度 Smi(5) → Smi(3) |

> Smi 编码：Dart 指针压缩下，整数 `n` 存为 `n << 1`。所以长度 5 是 `0xa`，长度 3 是 `0x6`。

---

## B 组 · 路由分支 5 → 3

函数：`::buildAppRouteRoots` @ `0xd6473c`
源文件：`package:xiaoying/router.dart`

go_router 的 `StatefulShellRoute` 有 5 个分支：`/timetable` `/school` `/social` `/chat` `/me`，
与 A 组一一对应。**两个列表必须同步裁剪**，否则索引错位。

| 地址 | 原始 | 补丁 | 说明 |
|---|---|---|---|
| `0xd64ae0` | `0xf85d03a0` `ldur x0,[fp,#-0x30]` | `0xf85c03a0` `ldur x0,[fp,#-0x40]` | 第 3 分支改取 `/me` |
| `0xd64ae8` | `0xf85c83a0` | NOP | 去掉 `/chat` load |
| `0xd64aec` | `0xb801b040` | NOP | 去掉 `/chat` store |
| `0xd64af0` | `0xf85c03a0` | NOP | `/me` load 已上移 |
| `0xd64af4` | `0xb801f040` | NOP | `/me` store 已上移 |
| `0xd64b14` | `0xd2800140` `movz x0,#0xa` | `0xd28000c0` `movz x0,#0x6` | 分支数 5 → 3 |

---

## C 组 · 启动默认页

函数：匿名闭包 @ `0xd64edc`（根路由 `/` 的 redirect）
源文件：`package:xiaoying/router.dart`

原实现直接返回池中的 `"/social"` 字符串。改成指向同页池里的 `"/timetable"`。

| 地址 | 原始 | 补丁 | 说明 |
|---|---|---|---|
| `0xd64ee0` | `0xf944dc00` `ldr x0,[x0,#0x9b8]` | `0xf944cc00` `ldr x0,[x0,#0x998]` | `/social` → `/timetable` |

> 这两个字符串在同一个对象池页（`PP + 0x12000`），只差低 12 位偏移，所以一条 `ldr` 就够，
> 不用动前面的 `add x0, PP, #0x12, lsl #12`。

---

## D 组 · 校园页精简

### D1 不合并服务端 portal

函数：`$availablePortals` 的闭包 @ `0xe0bb80`
源文件：`package:xiaoying_xy_app/portal/catalog.dart`

```dart
final local  = watch($xyAppRegisteredPortals);
final remote = watch($appPortals).valueOrNull;   // 服务端下发
final all    = List<Portal>.of(local);
if (remote != null) all.addAll(remote.map((p) => p.toPortal()));
return filterAvailablePortals(all.distinctByKey(), ...);
```

把 `if (remote != null)` 的条件跳转改成无条件跳转，直接跳过服务端合并：

| 地址 | 原始 | 补丁 |
|---|---|---|
| `0xe0bc90` | `0x540002e0` `b.eq 0xe0bcec` | `0x14000017` `b 0xe0bcec` |

影响：服务端下发的「应援计划」整组、四六级查分、万能互助群、课表共享、倒数日、像素拼豆、情侣课表、校园腾讯频道全部消失。

### D2 / D3 清空本地「小应」分组

| 地址 | 原始 | 补丁 | 说明 |
|---|---|---|---|
| `0xd66040` | `0xd28000c0` `movz x0,#0x6` | `0xd2800000` `movz x0,#0x0` | `package:xiaoying/xiaoying.dart` 里 3 个「小应」portal → 0 |
| `0xdaa804` | `0xd2800042` `movz x2,#0x2` | `0xd2800002` `movz x2,#0x0` | `xiaoying_bulletin` 的 1 个「小应」portal → 0 |

两个列表清空后，`groupPortalsByCat()` 不再产生 `小应` 这个分组，表头一并消失。

### D4 靠去重丢掉指定宫格项

`Portal::distinctByKey()` @ `0xe0c488` 按 `Portal.field_b`（hookId）建 `Map<String, Portal>`。

> **坑**：它实际是**后者覆盖前者**（不是"保留第一个"）。

于是把待删项的 hookId 指向一个**排在它们之后**的保留项，它们就被覆盖掉。
本轮以 `10259@本科生.绩点计算器`（列表第 18 项）为碰撞目标：

| 地址 | 原始 | 补丁 | 删掉 |
|---|---|---|---|
| `0xdb139c` | `0xf9457c00` `ldr x0,[x0,#0xaf8]` | `0xf9452800` `ldr x0,[x0,#0xc80]` | 校园地图 |
| `0xdb176c` | `0xf945c800` | `0xf9452800` | 应网办 |
| `0xdb1948` | `0xf945ec00` | `0xf9452800` | 申飞购票 |
| `0xdb1a20` | `0xf945fc00` | `0xf9452800` | 自助洗衣 |
| `0xdb1cfc` | `0xf9463000` | `0xf9452800` | 网络检测 |

> 第一次尝试用了列表第 1 项（`校园一卡通@账户`，偏移 `0xa50`）当碰撞目标，
> 结果「网络检测」反过来把「校园一卡通」顶掉了——这就是"后者覆盖前者"的直接证据。
> 碰撞目标必须排在**所有**待删项之后。

### D5 去掉顶部公告栏

函数：`_SchoolPageState::build` @ `0xe0a5f0`
源文件：`package:xiaoying/page/school/page.dart`

slivers 列表初始两项 `[XySliverAppBar, BulletinAppCard]`，长度 Smi(2) 缩到 Smi(1)：

| 地址 | 原始 | 补丁 |
|---|---|---|
| `0xe0aa0c` | `0xd2800080` `movz x0,#0x4` | `0xd2800040` `movz x0,#0x2` |

公告卡带滚动跑马灯，「推荐 / 公告 / 校园」切换条与广告位也在这块 sliver 里，一并消失。

---

## E 组 · 修「导入课表失败」

### 崩溃事实

```
FormatException: Invalid radix-10 number (at character 1)
第18
^
#4 rangeFromString            (xiaoying_timetable_common/utils.dart:21)
#5 parseWeekText2RangedNumbers(...utils.dart:84)
#6 _parseUgCourseFromRaw      (xiaoying_10259/ug_student_reg/timetable/parse.dart:27)
#7 parseUgTimetableFromRaw    (...parse.dart:69)
#8 Timetable10259UgScraper.scrape (...scraper.dart:68)
```

教务的周次字段从 `18` 变成了 `第18`（"周"字在另一个 HTML 节点里，取不到），
`rangeFromString` 里 `int.parse("第18")` 直接抛异常。**与网络、权限无关。**

### 为什么只丢「第」、不丢「周」

`parseWeekText2RangedNumbers` 本身已有三条分支（反汇编原样对应）：

| 判定 | 截断 | 周类型 |
|---|---|---|
| `contains("周(单)")` | `substring(0, len-4)` ← `0x16a83e4`: `x2 = len - 4` | ODD |
| `contains("周(双)")` | `substring(0, len-4)` | EVEN |
| `contains("周")` | `substring(0, len-1)` ← `0x16a8694` | ALL |
| 都不含 | 原样 | ALL |

所以「周」本来就会被截掉。**如果在字符映射器里也丢「周」，会立刻打断单双周判断**：

```
18周(单)   -> 18(单)  -> contains("周(单)") 失配 -> int.parse("18(单)") 崩
1-18周(双) -> 18(双)  -> 同样崩
```

这正是本项目的取舍依据，`week_parse_model.py` 里有反事实对照。

### 补丁位置

`mapChinesePunctuations` @ `0x16a88a4`（`package:xiaoying_school_common/src/utils/format.dart`）
是逐 rune 的区间比较 + `StringBuffer::writeCharCode`，其中 `【`(U+3010) 分支只做一次写出。
把该分支的阈值改成 `第`(U+7B2C)，并把写出改成跳到循环尾（不输出）：

| 地址 | 原始 | 补丁 | 说明 |
|---|---|---|---|
| `0x16a8918` | `0xd2860211` `movz x17,#0x3010` | `0xd28f6591` `movz x17,#0x7b2c` | 外层阈值 |
| `0x16a8964` | `0xd2860211` | `0xd28f6591` | 内层阈值 |
| `0x16a8974` | `0xd2800b62` `movz x2,#0x5b`（写 `[`） | `0x1400002d` `b 0x16a8a28` | 命中即丢弃 |

副作用：`【` 不再被归一化成 `[`。该函数只有两个调用方——课表周次解析、应网办 `application.dart` 的
`EmpFrom` / `EmpFromT` 字段值（申请单位一类字符串），公告正文走 bulletin 模块不受影响。

---

## 验证方法

1. **每条补丁都断言指令类型**：`patch_libapp.py` 在改之前会校验原始字的 opcode 掩码
   （如 `old & 0xFFC00000 == 0xF8400000` 才是 `LDUR`），不匹配直接报错退出，避免版本漂移后改错地方。
2. **改完回读反汇编**：脚本用 capstone 把补丁点前后各若干条指令反汇编打印，人工核对控制流。
3. **离线模型**：`week_parse_model.py` 按反汇编还原解析逻辑，跑格式矩阵。
4. **真机验证**：导入真实课表后直接读 hive box，看解析结果——
   例如「无机化学B」第二段 `weeks:[2,4,6,8,10,12,14,16]`（双周）、
   「仪器分析」`weeks:[0..15]`（连续 16 周），证明确实走通了区间与单双周两条路径。
