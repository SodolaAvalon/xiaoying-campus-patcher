# 逆向笔记：Flutter AOT 改包方法论

记录这次改包从头到尾的路径，以及踩过的坑，给后来者省时间。

---

## 1. 先判断技术栈，别急着 jadx

```bash
unzip -l base.apk | grep -E "lib/|assets/"
```

看到 `lib/arm64-v8a/libflutter.so` + `libapp.so` + `assets/flutter_assets/`，就是 **Flutter 应用**。

结论：**业务逻辑不在 dex 里**。Dart AOT 编译进 `libapp.so`，jadx 只能看到通道插件那点 Java 壳，
改 UI、改逻辑、改解析都不要指望 Java 层。

---

## 2. 关键前提：符号是否保留

Flutter 默认 **不做符号混淆**。`strings libapp.so` 就能看到完整的 `package:xxx/yyy.dart` 路径。

本次统计到 **3441 个源文件路径**、完整的类名与字段名：

```
package:xiaoying/page/layout.dart
package:xiaoying/page/school/page.dart
package:xiaoying_10259/ug_student_reg/timetable/parse.dart
...
```

只要符号在，逆向难度从「读裸汇编」降到「照着函数名找」。

检查方法：

```python
data = open('libapp.so','rb').read().decode('latin-1')
print(len(re.findall(r'package:[a-z0-9_]+/', data)))   # 0 就是被混淆了
```

> 若为 0，只能靠 blutter 的启发式 + 手工定位，成本高一个数量级。

---

## 3. blutter：把 AOT 快照还原成可读反汇编

<https://github.com/worawit/blutter>

它干三件事：解析 Dart 快照 → 复原类/函数符号 → 输出带注释的 ARM64 反汇编 + 对象池。

```bash
python3 blutter.py path/to/lib/arm64-v8a out_dir
```

产物里最有用的：

| 文件 | 用途 |
|---|---|
| `asm/<package>/<file>.dart` | 按源文件组织的反汇编，函数名/地址/指令齐全 |
| `pp.txt` / `objs.txt` | 对象池与常量对象，能直接看到 `"课表"`、`Obj!IconData@...` |
| `blutter_frida.js` | 现成的 Frida 脚本骨架（本项目没用上） |

输出示例（真实片段）：

```
class _AppLayoutState extends ConsumerState<dynamic> {
  _ buildDestinations(/* No info */) {
    // ** addr: 0xe03c60, size: 0x16c
    0xe03c9c: bl  #0xe03dcc  ; AllocateFloatingNavigationDestinationStub
    0xe03cb4: r0 = "校园"
    0xe03cb4: add x0, PP, #0x1b, lsl #12  ; [pp+0x1bfb0] "校园"
    0xe03cb8: ldr x0, [x0, #0xfb0]
```

编译踩坑（Ubuntu 24.04）：

* 需要 `cmake ninja-build libcapstone-dev pkg-config libicu-dev python3-pyelftools`，**clang 不是必须的**（gcc 13 够）；
* 首次运行会按 App 的 Dart 版本 clone 一份 `dart-lang/sdk` 并编译 VM 工具，约 200+ 个编译单元；
* 会有一条 `Analysis error at line 1510 ... handleOptionalNamedParameters` —— **不影响产出**，可以忽略。

---

## 4. Dart AOT 的读法要点

### 4.1 对象池（PP 寄存器）

常量（字符串、IconData、闭包）都在对象池里，代码用两条指令取：

```
add  x0, PP, #0x1b, lsl #12   ; 页 0x1b
ldr  x0, [x0, #0xfb0]         ; 页内偏移
```

**同一页内的常量互换，只改 `ldr` 的 imm 就够**——这是 C 组补丁能只改一条指令的原因。

### 4.2 Smi 编码

指针压缩下整数 `n` 存成 `n << 1`。所以：

* 列表长度 5 → 指令里是 `movz #0xa`
* 列表长度 3 → `movz #0x6`
* 长度 0 → `movz #0x0`

看反汇编时别把 `0xa` 当 10 读。

### 4.3 列表字面量的形态

```asm
movz x2, #0xa          ; Smi(5) —— 元素个数
bl   AllocateArrayStub
stur w16, [x0, #0xf]   ; arr[0]
stur w1,  [x0, #0x13]  ; arr[1]
...
movz x1, #0xa          ; GrowableArray 的 length = Smi(5)
stur w1,  [x0, #0xb]
```

想删元素不要只 NOP 掉 store —— **必须同时把末尾的 length 改小**，否则列表里会留空洞。

---

## 5. 定位与改写的工程化

### 5.1 地址换算

反汇编里的地址是 **vaddr**。用 ELF 段表换文件偏移，不要假设 `vaddr == offset`：

```python
def vaddr_to_off(elf, vaddr):
    for seg in elf.iter_segments():
        if seg['p_type'] == 'PT_LOAD' and seg['p_vaddr'] <= vaddr < seg['p_vaddr'] + seg['p_filesz']:
            return seg['p_offset'] + (vaddr - seg['p_vaddr'])
```

### 5.2 改指令：只动需要的位域

不要硬编码新指令字，**在原始字上改位域**，这样版本小更新后仍可用：

```python
def ldur_imm9(word, new_imm9):
    return (word & ~(0x1FF << 12)) | ((new_imm9 & 0x1FF) << 12)

def movz_imm16(word, new_imm16):
    return (word & ~(0xFFFF << 5)) | ((new_imm16 & 0xFFFF) << 5)

def ldr_imm12(word, new_byte_off):          # 64 位 LDR，比例 8
    return (word & ~(0xFFF << 10)) | (((new_byte_off // 8) & 0xFFF) << 10)
```

### 5.3 先断言再改

```python
assert (old & 0xFFC00000) == 0xF8400000, "not LDUR"   # LDUR
assert (old & 0xFF800000) == 0xD2800000, "not MOVZ"   # MOVZ(64)
assert (old & 0xFFC00000) == 0xF9400000, "not LDR"    # LDR(64,unsigned)
assert (old & 0xFF00001F) == 0x54000000, "not B.cond" # B.cond
```

App 一更新，地址就会漂移；**宁可脚本报错退出，也不要改到别的函数里**。

---

## 6. 重打包的两个硬约束

1. **`libapp.so` 必须保持 stored（不压缩）**
   `AndroidManifest` 里 `extractNativeLibs="false"`，库直接从 APK 内 mmap，压缩了会加载失败。
   `repack.py` 里写回时用 `ZIP_STORED`。
2. **必须 4K 对齐**
   ```bash
   zipalign -p -f 4 in.apk out.apk      # -p 专管 .so 的页对齐
   apksigner sign --ks ... out.apk
   ```
   顺序不能反：先对齐再签名（v2 签名覆盖整个文件）。

验证：`zipalign -c -p -v 4 modded.apk` 应看到 `lib/.../libapp.so (OK)`。

---

## 7. 坑位清单

| 坑 | 现象 | 结论 |
|---|---|---|
| `distinctByKey()` 的语义 | 删 A 却把 B 删了 | 它是**后者覆盖前者**；碰撞目标必须排在待删项之后 |
| 路由与导航两套列表 | 底部只剩 3 个 tab，但点「我的」进的是广场 | 导航目的地列表、`StatefulShellRoute` 分支列表**必须同步裁剪** |
| 根路由 redirect | 砍掉 `/social` 后启动直接 404「找不到页面」 | 根路由 redirect 把 `/social` 写死在闭包里，要一起改 |
| 进程被杀后重启 | 恢复的旧路由已不存在 → 404，按返回才恢复 | go_router 的状态恢复会带回已删路由，属已知副作用 |
| `mapChinesePunctuations` 是共享函数 | 想丢「周」却发现单双周崩了 | 单/双周分支靠 `contains("周(单)")` 触发，且长度硬编码 `len-4` |
| blutter 的 `SubstringMatches` 标注 | 以为是模糊匹配 | 其实是 `String.contains/indexOf` 的内部实现 |

---

## 8. 边界

* 这套方法**只能改代码里已有的东西**：改常量、改跳转、NOP 调用。**不能注入新逻辑**。
  想加功能就得重编译 Dart，而 AOT 快照无法还原成源码。
* 服务端下发的内容（本次的「应援计划」等）只能通过「不合并服务端数据」这类**粗粒度开关**绕过，
  想精细过滤就得在 Dart 层写过滤代码——超出静态补丁的能力范围。
* 每次 App 升级都要重新跑一遍：重新 blutter、核对符号、确认地址。脚本里的断言就是为这个准备的。
